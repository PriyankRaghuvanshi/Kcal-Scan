"""General live-menu intelligence pipeline using LLM reasoning.

Provides a category-agnostic LLM reasoning layer over real menu text.
Works across any restaurant type — juice bar, Indian, burger chain, sushi,
cafe, pizza, Mexican, fried chicken, local independent, dessert, etc. —
by letting the model identify actual menu items and reason about their
macro fit, rather than matching cuisine keywords against static rule tables.

The output feeds into the existing scoring engine and card builders; it
does NOT replace scoring but enriches it with menu-aware structured
candidates that the heuristic pipeline cannot produce reliably.

Integration points:
  - menu_scan.py        : called after OCR to get structured candidates
  - menu_item_scoring.py: called when ingested menu text is available
  - lunch_decision.py   : candidates passed through to reality check
  - restaurant_reality_check.py: uses typical_order / best_choice_here

Controlled by ENABLE_LLM_MENU_REASONING env var (default: True when
GEMINI_API_KEY is configured).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CENTRALIZED CONFIDENCE POLICY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All confidence thresholds for LLM reasoning output live here so that
every consumer — menu scan, lunch decision, reality check, scoring —
uses the same rules. Import the constants rather than hard-coding floats.

Per-candidate confidence (candidate["confidence"]):
  CONF_EXACT_ITEM     = 0.65  → exact item name allowed (matches prompt rule)
  CONF_SOFT_ITEM      = 0.55  → soft/menu-aware name allowed (typical_order)
  CONF_MIN_ITEM       = 0.45  → absolute floor — discard below this

Overall reasoning_confidence gate (result["reasoning_confidence"]):
  CONF_REASONING_FULL = 0.65  → full LLM override (best_choice promoted to card)
  CONF_REASONING_USE  = 0.55  → partial use (swap, avoid, reality-check ok)
  CONF_REASONING_MIN  = 0.45  → only typical_order usable; skip best_choice

Reality check distinction minimum:
  CONF_REALITY_CALORIE_DIFF = 80  → min kcal difference for a meaningful comparison

Cache:
  Results are cached in-process keyed on (menu_text_hash, goal, cut_mode).
  remaining_calories / remaining_protein_g are intentionally excluded from the
  cache key because they change per user session while the menu does not.
  The structural candidates (best_choice, swap, avoid, typical_order) are
  independent of per-session macro totals.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CENTRALIZED CONFIDENCE POLICY  (import these everywhere — do not hardcode)
# ─────────────────────────────────────────────────────────────────────────────

# Per-candidate confidence thresholds
CONF_EXACT_ITEM: float = 0.65   # Exact item name from menu is allowed
CONF_SOFT_ITEM: float = 0.55    # Soft/menu-aware wording is allowed
CONF_MIN_ITEM: float = 0.45     # Below this, discard the candidate entirely

# Overall reasoning_confidence (how readable/complete the menu text was)
CONF_REASONING_FULL: float = 0.65   # Full LLM override: promote best_choice to card
CONF_REASONING_USE: float = 0.55    # Partial use: swap, avoid, reality-check
CONF_REASONING_MIN: float = 0.45    # Absolute minimum: only typical_order

# Reality check: minimum kcal gap to show a meaningful "You saved X kcal" line
CONF_REALITY_CALORIE_DIFF: int = 80

# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_REASONING_VERSION = "v2"
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MAX_MENU_TEXT_CHARS = 4000
_CACHE_MAX_ENTRIES = 256


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in _TRUE_VALUES


def _is_enabled() -> bool:
    return _env_bool("ENABLE_LLM_MENU_REASONING", default=True)


def _get_model_name() -> str:
    return (
        os.getenv("MENU_REASONING_LLM_MODEL", "").strip()
        or os.getenv("MENU_PARSER_LLM_MODEL", "").strip()
        or os.getenv("SCAN_LLM_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or "gemini-2.5-flash"
    )


def _get_timeout_sec() -> float:
    try:
        return float(os.getenv("MENU_REASONING_LLM_TIMEOUT_SEC", "12") or "12")
    except Exception:
        return 12.0


# ─────────────────────────────────────────────────────────────────────────────
# IN-PROCESS LRU CACHE
# ─────────────────────────────────────────────────────────────────────────────
# Keyed on (menu_text_hash, goal, cut_mode).
# remaining_calories / remaining_protein_g are deliberately excluded: they vary
# per session while the menu's structural candidates do not. The cache stores
# the full result; callers may still use the remaining-macro context for
# post-processing (e.g. choosing protein_catchup vs lighter_recovery).
#
# Only successful results (llm_reasoning_used=True) are cached. Failures are
# never cached so transient API errors do not poison future calls.

_cache: Dict[tuple, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_cache_order: List[tuple] = []  # insertion-order list for eviction


def _menu_text_hash(text: str) -> str:
    canonical = text[:_MAX_MENU_TEXT_CHARS].strip()
    return hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _normalize_goal(goal: str) -> str:
    return str(goal or "").strip().lower().replace(" ", "_")[:32]


def _make_cache_key(menu_text: str, goal: str, cut_mode: bool) -> tuple:
    return (_menu_text_hash(menu_text), _normalize_goal(goal), bool(cut_mode))


def _cache_get(key: tuple) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        return _cache.get(key)


def _cache_put(key: tuple, result: Dict[str, Any]) -> None:
    with _cache_lock:
        if key in _cache:
            _cache[key] = result
            return
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            # Evict the oldest entry
            if _cache_order:
                oldest = _cache_order.pop(0)
                _cache.pop(oldest, None)
        _cache[key] = result
        _cache_order.append(key)


def clear_reasoning_cache() -> None:
    """Clear the in-process reasoning cache. Useful for testing."""
    with _cache_lock:
        _cache.clear()
        _cache_order.clear()


def reasoning_cache_stats() -> Dict[str, Any]:
    """Return basic cache statistics for diagnostics."""
    with _cache_lock:
        return {"size": len(_cache), "max": _CACHE_MAX_ENTRIES}


# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

_REASONING_PROMPT = """\
You are a menu nutrition analyst. Given real restaurant menu text, reason \
over the actual items and return structured recommendations as JSON.

Work across any restaurant category: juice/smoothie bar, Indian, burger, \
sushi, cafe, pizza, Mexican, fried chicken, dessert, local restaurant, etc.
Do NOT use cuisine stereotypes — reason from the actual menu text provided.

Restaurant: {place_name}
User goal: {goal}
Remaining calories today: {remaining_calories_str}
Remaining protein today: {remaining_protein_str}
Strict cut mode (low-calorie priority): {cut_mode}

MENU TEXT:
---
{menu_text}
---

Return ONLY valid JSON with this exact structure. All candidate fields are \
optional — omit any you cannot support from the menu text:

{{
  "menu_summary": "One-sentence description of this restaurant's menu type",
  "reasoning_confidence": 0.82,
  "best_choice_here": {{
    "name": "Exact item name from the menu above",
    "why": "Why this is the best macro-fit pick from this specific menu",
    "estimated_calories": 520,
    "estimated_protein_g": 38,
    "confidence": 0.85
  }},
  "better_swap": {{
    "name": "A different item OR a lighter variant of the most popular choice",
    "swap_tip": "Specific actionable swap or customisation tip for this item",
    "why": "Why this swap improves calorie or protein balance here",
    "estimated_calories": 460,
    "estimated_protein_g": 34,
    "confidence": 0.78
  }},
  "avoid_if_cutting": {{
    "name": "The highest-calorie or least macro-efficient item on this menu",
    "why": "Why it is hard to fit when the user is cutting",
    "estimated_calories": 980,
    "confidence": 0.80
  }},
  "typical_order": {{
    "name": "What most customers probably order here (not the healthiest pick)",
    "estimated_calories": 860,
    "confidence": 0.68
  }},
  "protein_catchup_option": {{
    "name": "Best item if the user still needs a lot of protein today",
    "why": "Highest usable protein on this specific menu",
    "estimated_protein_g": 45,
    "confidence": 0.82
  }},
  "lighter_recovery_option": {{
    "name": "Best item when the user's calories are already tight",
    "why": "Lowest calorie density while still filling on this menu",
    "estimated_calories": 380,
    "confidence": 0.72
  }}
}}

Confidence rules — follow strictly:
- Use EXACT item names (as written in the menu) when confidence >= 0.65
- Use category-aware but still menu-informed wording when confidence is 0.55-0.64
- Use generic wording only when confidence < 0.55 or menu is unreadable
- Do NOT fabricate calorie/protein numbers unless strongly supported
- Make best_choice_here, better_swap, and avoid_if_cutting DISTINCT from each other
- If the menu has fewer than 3 readable items, set reasoning_confidence < 0.50
- Return ONLY valid JSON — no markdown fences, no prose before or after
"""


# ─────────────────────────────────────────────────────────────────────────────
# RESULT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _empty_result(
    error: str = "",
    reasoning_source: str = "error",
) -> Dict[str, Any]:
    return {
        "menu_summary": "",
        "reasoning_confidence": 0.0,
        "best_choice_here": None,
        "better_swap": None,
        "avoid_if_cutting": None,
        "typical_order": None,
        "protein_catchup_option": None,
        "lighter_recovery_option": None,
        "llm_reasoning_used": False,
        "llm_reasoning_error": error,
        "reasoning_source": reasoning_source,
        "cache_hit": False,
        "reasoning_version": _REASONING_VERSION,
    }


def _clean_candidate(candidate: Any) -> Optional[Dict[str, Any]]:
    """Validate and clean a single LLM candidate dict."""
    if not isinstance(candidate, dict):
        return None
    name = str(candidate.get("name") or "").strip()
    if not name:
        return None
    conf = float(_safe_float(candidate.get("confidence"), 0.0))
    if conf < CONF_MIN_ITEM:
        return None
    return {k: v for k, v in candidate.items() if k != "name"} | {"name": name}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def reason_over_menu(
    *,
    menu_text: str,
    place_name: str = "",
    goal: str = "",
    cut_mode: bool = False,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
) -> Dict[str, Any]:
    """Use an LLM to reason over real menu text and return structured candidates.

    This is the core of the general menu intelligence pipeline. It works across
    any restaurant category without relying on cuisine-specific keyword rules.

    Results are cached in-process keyed on (menu_text_hash, goal, cut_mode).
    remaining_calories / remaining_protein_g are used in the prompt for context
    but are intentionally excluded from the cache key (they vary per session;
    the menu's structural candidates do not).

    Returns a dict with keys:
      menu_summary, reasoning_confidence,
      best_choice_here, better_swap, avoid_if_cutting, typical_order,
      protein_catchup_option, lighter_recovery_option,
      llm_reasoning_used, llm_reasoning_error, reasoning_source, cache_hit,
      reasoning_version.

    Check llm_reasoning_used before trusting the candidates. When False,
    fall back to the existing heuristic pipeline.

    reasoning_source values:
      "live_llm"  — fresh call to the LLM
      "cache"     — returned from in-process cache
      "disabled"  — feature flag off
      "error"     — LLM call failed
    """
    if not _is_enabled():
        return _empty_result("disabled", reasoning_source="disabled")

    text_clean = str(menu_text or "").strip()
    if len(text_clean) < 20:
        return _empty_result("menu_text_too_short", reasoning_source="error")

    try:
        import google.generativeai as genai  # type: ignore[import]
    except Exception:
        return _empty_result("genai_unavailable", reasoning_source="error")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _empty_result("no_api_key", reasoning_source="error")

    # ── Cache lookup ─────────────────────────────────────────────────────────
    cache_key = _make_cache_key(text_clean, goal, cut_mode)
    cached = _cache_get(cache_key)
    if cached is not None:
        hit = dict(cached)
        hit["cache_hit"] = True
        hit["reasoning_source"] = "cache"
        return hit

    # ── Build prompt ─────────────────────────────────────────────────────────
    text_truncated = text_clean[:_MAX_MENU_TEXT_CHARS]
    if len(text_clean) > _MAX_MENU_TEXT_CHARS:
        text_truncated += "\n... (menu continues)"

    remaining_calories_str = (
        f"{int(remaining_calories)} kcal" if remaining_calories is not None else "unknown"
    )
    remaining_protein_str = (
        f"{int(remaining_protein_g)}g" if remaining_protein_g is not None else "unknown"
    )
    goal_str = (
        str(goal or "general healthy eating").strip().replace("_", " ")
        or "general healthy eating"
    )

    prompt = _REASONING_PROMPT.format(
        place_name=str(place_name or "this restaurant").strip() or "this restaurant",
        goal=goal_str,
        remaining_calories_str=remaining_calories_str,
        remaining_protein_str=remaining_protein_str,
        cut_mode=str(bool(cut_mode)),
        menu_text=text_truncated,
    )

    # ── LLM call ─────────────────────────────────────────────────────────────
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=_get_model_name(),
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        response = model.generate_content(
            prompt,
            request_options={"timeout": _get_timeout_sec()},
        )
        raw_text = str(getattr(response, "text", "") or "").strip()
        if not raw_text:
            return _empty_result("empty_llm_response", reasoning_source="error")

        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            return _empty_result("invalid_json_structure", reasoning_source="error")

        result = _empty_result()
        result["llm_reasoning_used"] = True
        result["reasoning_source"] = "live_llm"
        result["cache_hit"] = False
        result["menu_summary"] = str(parsed.get("menu_summary") or "").strip()
        result["reasoning_confidence"] = float(
            _clamp(_safe_float(parsed.get("reasoning_confidence"), 0.6), 0.0, 1.0)
        )

        for key in (
            "best_choice_here",
            "better_swap",
            "avoid_if_cutting",
            "typical_order",
            "protein_catchup_option",
            "lighter_recovery_option",
        ):
            cleaned = _clean_candidate(parsed.get(key))
            if cleaned is not None:
                result[key] = cleaned

        # Only cache successful results
        if result["llm_reasoning_used"]:
            _cache_put(cache_key, dict(result))

        return result

    except Exception as exc:
        logger.info(
            "llm_menu_reasoning failed for %s: %s",
            place_name or "?",
            str(exc)[:160],
        )
        return _empty_result(str(exc or "llm_reasoning_failed")[:160], reasoning_source="error")


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE HELPERS (use centralized thresholds — do not hardcode in callers)
# ─────────────────────────────────────────────────────────────────────────────

def candidate_item_name(
    candidate: Optional[Dict[str, Any]],
    min_confidence: float = CONF_EXACT_ITEM,
) -> str:
    """Return the item name from a reasoning candidate if per-candidate confidence
    meets the threshold.

    Default threshold is CONF_EXACT_ITEM (0.65), matching the prompt rule.
    Pass CONF_SOFT_ITEM (0.55) for lower-stakes fields like typical_order.
    """
    if not isinstance(candidate, dict):
        return ""
    conf = float(_safe_float(candidate.get("confidence"), 0.0))
    if conf < min_confidence:
        return ""
    return str(candidate.get("name") or "").strip()


def candidate_calories(candidate: Optional[Dict[str, Any]]) -> Optional[int]:
    """Return estimated_calories from a candidate if present and positive."""
    if not isinstance(candidate, dict):
        return None
    raw = candidate.get("estimated_calories")
    if raw is None:
        return None
    try:
        val = int(float(raw))
        return val if val > 0 else None
    except Exception:
        return None


def candidate_protein(candidate: Optional[Dict[str, Any]]) -> Optional[int]:
    """Return estimated_protein_g from a candidate if present and positive."""
    if not isinstance(candidate, dict):
        return None
    raw = candidate.get("estimated_protein_g")
    if raw is None:
        return None
    try:
        val = int(float(raw))
        return val if val > 0 else None
    except Exception:
        return None


def reality_check_candidates_valid(
    typical: Optional[Dict[str, Any]],
    smarter: Optional[Dict[str, Any]],
) -> bool:
    """Return True if typical and smarter candidates are distinct enough to produce
    a meaningful reality-check calorie comparison.

    Uses CONF_REALITY_CALORIE_DIFF as the minimum meaningful calorie difference.
    """
    if not isinstance(typical, dict) or not isinstance(smarter, dict):
        return False
    typ_name = str(typical.get("name") or "").strip().lower()
    smt_name = str(smarter.get("name") or "").strip().lower()
    if not typ_name or not smt_name:
        return False
    if typ_name == smt_name:
        return False
    typ_cal = candidate_calories(typical) or 0
    smt_cal = candidate_calories(smarter) or 0
    if typ_cal > 0 and smt_cal > 0 and abs(typ_cal - smt_cal) < CONF_REALITY_CALORIE_DIFF:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# TEXT EXTRACTION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def extract_menu_text_for_reasoning(
    place: Dict[str, Any],
    ingestion_bundle: Optional[Dict[str, Any]] = None,
) -> str:
    """Extract the best available menu text from a place dict and/or ingestion bundle.

    Prefers explicit raw text from the ingestion bundle (fetched from web/chain),
    falls back to embedded text on the place dict, then reconstructs from item
    name + snippet fields stored by the ingestion pipeline.
    """
    payload = place if isinstance(place, dict) else {}
    bundle = ingestion_bundle if isinstance(ingestion_bundle, dict) else {}

    # Ingestion bundle raw text (highest quality — actual fetched content)
    for key in ("raw_menu_text", "raw_text", "menu_raw_text"):
        text = str(bundle.get(key) or "").strip()
        if len(text) >= 40:
            return text

    # Embedded text directly on the place dict
    for key in (
        "menu_text",
        "menuText",
        "raw_menu_text",
        "menu_description",
        "menuDescription",
    ):
        text = str(payload.get(key) or "").strip()
        if len(text) >= 40:
            return text

    # Reconstruct from ingested item names + raw_text_snippet fields
    items: List[Dict[str, Any]] = []
    for src in (bundle, payload):
        candidate = src.get("menu_items") if isinstance(src.get("menu_items"), list) else []
        if candidate:
            items = candidate  # type: ignore[assignment]
            break

    if items:
        lines: List[str] = []
        for item in items[:40]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("item_name") or item.get("name") or "").strip()
            snippet = str(item.get("raw_text_snippet") or "").strip()
            if snippet and snippet != name:
                lines.append(snippet)
            elif name:
                lines.append(name)
        if lines:
            return "\n".join(lines)

    return ""
