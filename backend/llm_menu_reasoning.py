"""General live-menu intelligence pipeline using LLM reasoning.

Provides a category-agnostic LLM reasoning layer over real menu text.
Works across any restaurant type — juice bar, Indian, burger chain, sushi,
cafe, pizza, Mexican, fried chicken, local independent, dessert, etc. —
by letting the model identify actual menu items and reason about their
macro fit, rather than matching cuisine keywords against static rule tables.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHITECTURE: STRUCTURAL vs CONTEXTUAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The pipeline is intentionally split into two stages:

  Stage 1 — Structural menu reasoning (LLM, cached)
  ─────────────────────────────────────────────────
  Input : menu text + place_name + goal + cut_mode
  Output: stable, menu-level candidates that are the same for every user
          visiting the same restaurant with the same goal:
            menu_summary, reasoning_confidence,
            best_choice_here, better_swap, avoid_if_cutting,
            typical_order, ranked_candidates

  Cache key: (menu_text_hash, goal, cut_mode)
  remaining_calories / remaining_protein_g are deliberately excluded from
  the cache key AND from the structural prompt because the menu's best
  macro choices do not change based on an individual user's daily totals.

  Stage 2 — Contextual decision overlay (deterministic, never cached)
  ────────────────────────────────────────────────────────────────────
  Input : structural result + remaining_calories + remaining_protein_g
          + cut_mode + meal_window + current_hour
  Output: user-specific picks derived from the cached ranked_candidates:
            protein_catchup_option — highest-protein candidate when user
                                     still needs significant protein today
            lighter_recovery_option — lowest-calorie candidate when user
                                      is low on calories

  This stage is deterministic: no LLM call, no caching needed.
  Different users seeing the same menu at different macro states get
  genuinely different protein_catchup / lighter_recovery outputs.

Public API:
  reason_over_menu(menu_text, place_name, goal, cut_mode,
                   remaining_calories, remaining_protein_g)
      → calls Stage 1 (cached) then Stage 2 (live)
      → returns combined result

  apply_contextual_overlay(structural_result, remaining_calories,
                           remaining_protein_g, cut_mode, meal_window,
                           current_hour)
      → Stage 2 only — useful when structural result is already in hand

Integration points:
  - menu_scan.py        : called after OCR; passes remaining macros
  - menu_item_scoring.py: called when ingested menu text is available
  - lunch_decision.py   : candidates passed through to reality check
  - restaurant_reality_check.py: uses typical_order / best_choice_here

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CENTRALIZED CONFIDENCE POLICY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All confidence thresholds live here. Import the constants in consumers
rather than hardcoding floats.

Per-candidate confidence (candidate["confidence"]):
  CONF_EXACT_ITEM     = 0.65  → exact item name allowed (matches prompt rule)
  CONF_SOFT_ITEM      = 0.55  → soft/menu-aware name allowed
  CONF_MIN_ITEM       = 0.45  → absolute floor — discard below this

Overall reasoning_confidence gate (result["reasoning_confidence"]):
  CONF_REASONING_FULL = 0.65  → full LLM override (best_choice promoted to card)
  CONF_REASONING_USE  = 0.55  → partial use (swap, avoid, reality-check ok)
  CONF_REASONING_MIN  = 0.45  → only typical_order usable; skip best_choice

Reality check distinction minimum:
  CONF_REALITY_CALORIE_DIFF = 80  → min kcal difference for a meaningful comparison
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

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

# Contextual overlay thresholds (deterministic, no LLM)
# Remaining protein >= this value → show protein_catchup_option
_PROTEIN_CATCHUP_THRESHOLD_G: float = 30.0
# Remaining calories <= this value → show lighter_recovery_option
_LIGHTER_RECOVERY_THRESHOLD_KCAL: float = 500.0

# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_REASONING_VERSION = "v4"
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MAX_MENU_TEXT_CHARS = 4000
_CACHE_MAX_ENTRIES = 256

# ── ranked_candidates validation constants ───────────────────────────────────
# Plausible per-item calorie range.  Drinks (e.g. espresso = 5 kcal) and large
# combo plates (2200 kcal) are genuine outliers; use a generous but not infinite
# window so we catch nonsensical LLM fabrications like "10 kcal burger".
_CAND_CALORIE_MIN = 30
_CAND_CALORIE_MAX = 2500
_CAND_PROTEIN_MIN = 0
_CAND_PROTEIN_MAX = 160

# Minimum word overlap fraction to consider two candidate names near-duplicates.
_NEAR_DUP_WORD_OVERLAP = 0.75

# Generic fallback names the LLM may hallucinate — these are banned from
# appearing in ranked_candidates because they provide no useful signal for
# contextual overlay selection.
_BANNED_GENERIC_NAMES: frozenset = frozenset(
    {
        "lighter menu option",
        "lighter option",
        "lighter meal",
        "lighter choice",
        "light option",
        "protein bowl",
        "grilled protein bowl",
        "protein plate",
        "lean wrap",
        "protein wrap",
        "suggested lighter option",
        "healthier option",
        "balanced meal",
        "healthy option",
        "best menu item",
        "better choice",
        "smart choice",
        "smart order",
        "meal option",
        "menu item",
        "typical meal",
        "lighter item",
        "lighter pick",
        "high protein option",
        "high protein item",
        "low calorie option",
        "low calorie item",
        "recommended item",
        "recommended option",
        "best choice",
        "best option",
        "better option",
    }
)


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
# IN-PROCESS LRU CACHE  (structural results only)
# ─────────────────────────────────────────────────────────────────────────────

_cache: Dict[tuple, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_cache_order: List[tuple] = []


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
            if _cache_order:
                oldest = _cache_order.pop(0)
                _cache.pop(oldest, None)
        _cache[key] = result
        _cache_order.append(key)


def clear_reasoning_cache() -> None:
    """Clear the in-process structural reasoning cache. Useful for testing."""
    with _cache_lock:
        _cache.clear()
        _cache_order.clear()


def reasoning_cache_stats() -> Dict[str, Any]:
    """Return basic cache statistics for diagnostics."""
    with _cache_lock:
        return {"size": len(_cache), "max": _CACHE_MAX_ENTRIES}


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL PROMPT  (no per-user macro context — stable for caching)
# ─────────────────────────────────────────────────────────────────────────────

_STRUCTURAL_PROMPT = """\
You are a menu nutrition analyst. Given real restaurant menu text, reason \
over the actual items and return structured recommendations as JSON.

Work across any restaurant category: juice/smoothie bar, Indian, burger, \
sushi, cafe, pizza, Mexican, fried chicken, dessert, local restaurant, etc.
Do NOT use cuisine stereotypes — reason from the actual menu text provided.

Restaurant: {place_name}
User goal: {goal}
Strict cut mode (low-calorie priority): {cut_mode}

MENU TEXT:
---
{menu_text}
---

Return ONLY valid JSON matching this exact structure:

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
    "name": "A DIFFERENT item from best_choice_here — lighter or macro-friendlier",
    "swap_tip": "Specific actionable swap or customisation tip for this item",
    "why": "Why this swap improves calorie or protein balance here",
    "estimated_calories": 460,
    "estimated_protein_g": 34,
    "confidence": 0.78
  }},
  "avoid_if_cutting": {{
    "name": "The highest-calorie or least macro-efficient item on this menu",
    "why": "Why it is hard to fit when cutting",
    "estimated_calories": 980,
    "confidence": 0.80
  }},
  "typical_order": {{
    "name": "What most customers probably order here (NOT the healthiest pick)",
    "estimated_calories": 860,
    "confidence": 0.68
  }},
  "ranked_candidates": [
    {{
      "name": "Item name exactly as written in the menu above",
      "estimated_calories": 320,
      "estimated_protein_g": 35,
      "notes": "highest protein on this menu",
      "confidence": 0.85
    }},
    {{
      "name": "Second distinct item name from the menu",
      "estimated_calories": 180,
      "estimated_protein_g": 8,
      "notes": "lowest calorie option",
      "confidence": 0.82
    }}
  ]
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RANKED CANDIDATES RULES — follow carefully
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ranked_candidates is REQUIRED. Include between 4 and 6 items.

REQUIRED COVERAGE (include all of these if the menu supports them):
  1. The item with the most protein — notes: "highest protein"
  2. The item with the fewest calories — notes: "lowest calorie"
  3. A balanced moderate-calorie item — notes: "balanced choice"
  4. The item most customers would typically order — notes: "typical popular order"
  5. One or two additional notable items if the menu has them

MANDATORY RULES:
- Every item in ranked_candidates must come from the actual menu text above
- estimated_calories and estimated_protein_g are REQUIRED for each candidate
  (estimate if not stated — typical ranges: calories 100–2000, protein 0–120g)
- No item name may appear more than once anywhere in the entire output
- No generic fallback labels such as "Lighter menu option", "Protein bowl",
  "Best choice", "Healthy option", "Recommended item" — use actual item names
- Candidates must be DISTINCT — do not list the same item under different slots
- notes must identify the candidate's nutritional role (e.g. "highest protein",
  "lowest calorie", "balanced", "popular combo", "vegetarian option")

CONFIDENCE RULES (apply to all candidates including ranked_candidates):
- confidence >= 0.65 → use exact item name as written in the menu
- confidence 0.55–0.64 → use menu-informed but slightly softer phrasing
- confidence < 0.55 → generic category wording only; do not fabricate names
- If the menu has fewer than 3 readable items, set reasoning_confidence < 0.50

DISTINCTNESS RULES:
- best_choice_here, better_swap, avoid_if_cutting, and typical_order must all
  be different items
- ranked_candidates should not repeat any of the named items above unless there
  are genuinely fewer distinct items on the menu

Return ONLY valid JSON — no markdown fences, no prose before or after.
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
        "ranked_candidates": [],
        "ranked_candidates_count": 0,
        "ranked_candidates_raw_count": 0,
        "ranked_candidates_macros_identical": False,
        "used_seeded_ranked_candidates": False,
        "protein_catchup_option": None,
        "lighter_recovery_option": None,
        "contextual_overlay_applied": False,
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
# CANDIDATE VALIDATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    """Normalize a candidate name for comparison (lowercase, collapse whitespace,
    strip punctuation)."""
    return " ".join(re.sub(r"[^\w\s]", " ", str(name or "").lower()).split())


def _is_banned_generic(name: str) -> bool:
    """Return True if the name is a known generic placeholder that the LLM uses
    as a fallback when it cannot identify a real menu item."""
    norm = _norm_name(name)
    # Exact match
    if norm in _BANNED_GENERIC_NAMES:
        return True
    # Prefix match — e.g. "lighter menu option with water"
    for banned in _BANNED_GENERIC_NAMES:
        if norm.startswith(banned):
            return True
    return False


def _are_near_duplicates(a: str, b: str) -> bool:
    """Return True if two candidate names refer to the same item (exact match,
    one is a substring of the other, or they share >= 75 % of words)."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Substring containment (e.g. "Protein Shake" vs "Large Protein Shake")
    if na in nb or nb in na:
        return True
    words_a = set(na.split())
    words_b = set(nb.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
    return overlap >= _NEAR_DUP_WORD_OVERLAP


def _macros_plausible(candidate: Dict[str, Any]) -> bool:
    """Return True if estimated_calories and estimated_protein_g (when present)
    fall within a plausible range for a single menu item."""
    cal = candidate.get("estimated_calories")
    prot = candidate.get("estimated_protein_g")
    if cal is not None:
        try:
            v = float(cal)
            if not (_CAND_CALORIE_MIN <= v <= _CAND_CALORIE_MAX):
                return False
        except (TypeError, ValueError):
            return False
    if prot is not None:
        try:
            v = float(prot)
            if not (_CAND_PROTEIN_MIN <= v <= _CAND_PROTEIN_MAX):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _all_macros_identical(candidates: List[Dict[str, Any]]) -> bool:
    """Return True if ≥ 3 candidates share identical non-zero calorie OR protein
    values, which suggests the LLM fabricated macros uniformly."""
    if len(candidates) < 3:
        return False
    cals = [c.get("estimated_calories") for c in candidates if c.get("estimated_calories") is not None]
    prots = [c.get("estimated_protein_g") for c in candidates if c.get("estimated_protein_g") is not None]
    if len(cals) >= 3 and len(set(cals)) == 1:
        return True
    if len(prots) >= 3 and len(set(prots)) == 1:
        return True
    return False


def _validate_and_repair_ranked_candidates(
    raw_candidates: List[Any],
    all_named_candidates: List[str],
    reasoning_confidence: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Validate, deduplicate, sanity-check, and repair the raw ranked_candidates
    list returned by the LLM.

    Returns
    -------
    (validated_list, diagnostics_dict)
        validated_list : cleaned, deduplicated, trust-safe candidates
        diagnostics_dict : {raw_count, valid_count, rejected_reasons: [str]}
    """
    diagnostics: Dict[str, Any] = {
        "raw_count": 0,
        "valid_count": 0,
        "rejected_reasons": [],
        "macros_identical_penalty": False,
    }

    if not isinstance(raw_candidates, list):
        return [], diagnostics

    diagnostics["raw_count"] = len(raw_candidates)

    # First pass: per-item validation
    stage1: List[Dict[str, Any]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            diagnostics["rejected_reasons"].append("not_a_dict")
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            diagnostics["rejected_reasons"].append("empty_name")
            continue
        if _is_banned_generic(name):
            diagnostics["rejected_reasons"].append(f"banned_generic:{name[:40]}")
            continue
        conf = float(_safe_float(raw.get("confidence"), 0.0))
        if conf < CONF_MIN_ITEM:
            diagnostics["rejected_reasons"].append(f"low_confidence:{conf:.2f}:{name[:30]}")
            continue
        if not _macros_plausible(raw):
            # Repair: strip implausible macro values rather than discarding
            repaired = {k: v for k, v in raw.items() if k not in ("estimated_calories", "estimated_protein_g")}
            repaired["name"] = name
            repaired["confidence"] = round(_clamp(conf * 0.85, CONF_MIN_ITEM, 0.95), 2)
            repaired["_macro_repaired"] = True
            diagnostics["rejected_reasons"].append(f"implausible_macros_repaired:{name[:30]}")
            stage1.append(repaired)
        else:
            row = {k: v for k, v in raw.items() if k != "name"} | {"name": name}
            stage1.append(row)

    # Second pass: deduplication (exact + near-duplicate + cross-field)
    seen_names: List[str] = list(all_named_candidates)  # already-committed names
    stage2: List[Dict[str, Any]] = []
    for item in stage1:
        name = str(item.get("name") or "").strip()
        is_dup = any(_are_near_duplicates(name, s) for s in seen_names)
        if is_dup:
            diagnostics["rejected_reasons"].append(f"near_duplicate:{name[:40]}")
            continue
        seen_names.append(name)
        stage2.append(item)

    # Third pass: penalise if all macros are suspiciously identical
    if _all_macros_identical(stage2):
        diagnostics["macros_identical_penalty"] = True
        for item in stage2:
            item["confidence"] = round(_clamp(
                float(_safe_float(item.get("confidence"), CONF_SOFT_ITEM)) * 0.80,
                CONF_MIN_ITEM, 0.92,
            ), 2)

    # If overall reasoning_confidence is low, cap individual candidate confidence
    if reasoning_confidence < CONF_REASONING_USE:
        for item in stage2:
            item["confidence"] = round(min(
                float(_safe_float(item.get("confidence"), CONF_SOFT_ITEM)),
                reasoning_confidence + 0.10,
            ), 2)

    diagnostics["valid_count"] = len(stage2)
    return stage2, diagnostics


def _clean_ranked_candidate(candidate: Any) -> Optional[Dict[str, Any]]:
    """Light per-candidate clean used before the batch validation pass.
    Full quality checking is done in _validate_and_repair_ranked_candidates()."""
    if not isinstance(candidate, dict):
        return None
    name = str(candidate.get("name") or "").strip()
    if not name:
        return None
    return {k: v for k, v in candidate.items() if k != "name"} | {"name": name}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — STRUCTURAL REASONING  (LLM, cached)
# ─────────────────────────────────────────────────────────────────────────────

def _structural_reason_over_menu(
    *,
    text_clean: str,
    place_name: str,
    goal: str,
    cut_mode: bool,
    api_key: str,
) -> Dict[str, Any]:
    """Internal: run structural LLM reasoning and cache the result.

    Only called by reason_over_menu(). Returns the cached structural result
    which includes ranked_candidates for downstream contextual overlay.
    Does NOT include protein_catchup_option or lighter_recovery_option —
    those are derived contextually in apply_contextual_overlay().
    """
    cache_key = _make_cache_key(text_clean, goal, cut_mode)
    cached = _cache_get(cache_key)
    if cached is not None:
        hit = dict(cached)
        hit["cache_hit"] = True
        hit["reasoning_source"] = "cache"
        return hit

    text_truncated = text_clean[:_MAX_MENU_TEXT_CHARS]
    if len(text_clean) > _MAX_MENU_TEXT_CHARS:
        text_truncated += "\n... (menu continues)"

    goal_str = (
        str(goal or "general healthy eating").strip().replace("_", " ")
        or "general healthy eating"
    )

    prompt = _STRUCTURAL_PROMPT.format(
        place_name=str(place_name or "this restaurant").strip() or "this restaurant",
        goal=goal_str,
        cut_mode=str(bool(cut_mode)),
        menu_text=text_truncated,
    )

    try:
        import google.generativeai as genai  # type: ignore[import]

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

        for key in ("best_choice_here", "better_swap", "avoid_if_cutting", "typical_order"):
            cleaned = _clean_candidate(parsed.get(key))
            if cleaned is not None:
                result[key] = cleaned

        # ── ranked_candidates: validate, deduplicate, repair ──────────────────
        # Collect names already committed to main named slots so the validator
        # can detect cross-field near-duplicates.
        main_candidate_names: List[str] = [
            str((result.get(k) or {}).get("name") or "")
            for k in ("best_choice_here", "better_swap", "avoid_if_cutting", "typical_order")
            if result.get(k) and str((result.get(k) or {}).get("name") or "").strip()
        ]

        raw_ranked = parsed.get("ranked_candidates")
        pre_cleaned = (
            [_clean_ranked_candidate(c) for c in raw_ranked if isinstance(c, dict)]
            if isinstance(raw_ranked, list) else []
        )
        pre_cleaned = [c for c in pre_cleaned if c is not None]

        validated, diag = _validate_and_repair_ranked_candidates(
            raw_candidates=pre_cleaned,
            all_named_candidates=main_candidate_names,
            reasoning_confidence=result["reasoning_confidence"],
        )
        result["ranked_candidates"] = validated
        result["ranked_candidates_count"] = diag["valid_count"]
        result["ranked_candidates_raw_count"] = diag["raw_count"]
        result["ranked_candidates_macros_identical"] = diag["macros_identical_penalty"]

        # Seed from main named candidates when the validated set is too sparse
        # to provide meaningful protein/calorie diversity for the overlay.
        seeded_before = len(result["ranked_candidates"])
        _seed_ranked_from_main_candidates(result)
        result["used_seeded_ranked_candidates"] = (
            len(result["ranked_candidates"]) > seeded_before
        )

        # Cache only successful structural results
        if result["llm_reasoning_used"]:
            _cache_put(cache_key, dict(result))

        return result

    except Exception as exc:
        logger.info(
            "llm_menu_reasoning (structural) failed for %s: %s",
            place_name or "?",
            str(exc)[:160],
        )
        return _empty_result(str(exc or "llm_structural_failed")[:160], reasoning_source="error")


def _seed_ranked_from_main_candidates(result: Dict[str, Any]) -> None:
    """Backfill ranked_candidates from the main named candidates when the
    validated set is too sparse for the contextual overlay.

    Seeding is additive: items already present in ranked_candidates are never
    duplicated. Near-duplicate matching prevents cross-field pollution.

    Strategy:
    - Always try to seed from best_choice_here and better_swap first
      (these are highest-quality structural picks)
    - Avoid seeding from avoid_if_cutting unless the set is very sparse (< 2)
      since avoid candidates have high calories and would distort protein/calorie
      selection in the contextual overlay
    """
    existing = list(result.get("ranked_candidates") or [])
    existing_names = [str(c.get("name") or "").strip() for c in existing]

    def _already_present(name: str) -> bool:
        return any(_are_near_duplicates(name, n) for n in existing_names)

    seeded = list(existing)

    # Priority seed order: best macro picks first; avoid calorie-dense "avoid" slot
    seed_keys = ["best_choice_here", "better_swap", "typical_order"]
    if len(seeded) < 2:
        seed_keys.append("avoid_if_cutting")

    for src_key in seed_keys:
        c = result.get(src_key)
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        if _is_banned_generic(name):
            continue
        if _already_present(name):
            continue
        row: Dict[str, Any] = {"name": name}
        if c.get("estimated_calories") is not None:
            row["estimated_calories"] = c["estimated_calories"]
        if c.get("estimated_protein_g") is not None:
            row["estimated_protein_g"] = c["estimated_protein_g"]
        # Lower confidence for seeded entries since they lack notes/roles
        row["confidence"] = round(
            _clamp(float(_safe_float(c.get("confidence"), CONF_SOFT_ITEM)) * 0.90, CONF_MIN_ITEM, 0.92),
            2,
        )
        row["notes"] = {
            "best_choice_here": "best macro-fit choice",
            "better_swap": "lighter or macro-friendlier swap",
            "typical_order": "typical popular order",
            "avoid_if_cutting": "higher calorie option",
        }.get(src_key, "")
        row["_seeded"] = True
        existing_names.append(name)
        seeded.append(row)

    result["ranked_candidates"] = seeded


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — CONTEXTUAL DECISION OVERLAY  (deterministic, never cached)
# ─────────────────────────────────────────────────────────────────────────────

def apply_contextual_overlay(
    structural: Dict[str, Any],
    *,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    cut_mode: bool = False,
    meal_window: str = "",
    current_hour: Optional[int] = None,
) -> Dict[str, Any]:
    """Derive user-specific contextual outputs from cached structural candidates.

    This is a pure deterministic function — no LLM call, no caching.
    It selects protein_catchup_option and lighter_recovery_option from the
    structural ranked_candidates based on the current user macro state.

    Different users (or the same user at different times of day) will get
    genuinely different outputs from the same cached structural result.

    Parameters
    ----------
    structural:
        Result from _structural_reason_over_menu() (cached or live).
    remaining_calories:
        Kcal the user can still eat today. If <= _LIGHTER_RECOVERY_THRESHOLD_KCAL
        (500 kcal), a lighter option is selected.
    remaining_protein_g:
        Grams of protein the user still needs today. If >= _PROTEIN_CATCHUP_THRESHOLD_G
        (30g), the highest-protein ranked candidate is selected.
    cut_mode:
        Whether the user is in a strict cut. Tightens lighter-recovery logic.
    meal_window:
        One of "breakfast", "lunch", "snack", "dinner". Used for framing copy.
    current_hour:
        Current local hour (0-23). Used to infer meal_window when not provided.

    Returns a copy of `structural` with protein_catchup_option and
    lighter_recovery_option populated (or None if not applicable).
    """
    result = dict(structural)
    # Ensure these keys exist in the output
    result.setdefault("protein_catchup_option", None)
    result.setdefault("lighter_recovery_option", None)

    if not structural.get("llm_reasoning_used"):
        return result

    candidates: List[Dict[str, Any]] = [
        c for c in (result.get("ranked_candidates") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    if not candidates:
        return result

    window = _resolve_meal_window(meal_window, current_hour)
    best_choice_name = str((result.get("best_choice_here") or {}).get("name") or "").strip().lower()

    # ── protein_catchup_option ────────────────────────────────────────────────
    rem_protein = float(_safe_float(remaining_protein_g, -1.0))
    if rem_protein >= _PROTEIN_CATCHUP_THRESHOLD_G:
        # Find the globally highest-protein candidate (may be best_choice itself).
        # If best_choice IS the top-protein item, we reinforce it with protein
        # framing rather than pointing to a weaker alternative.
        protein_candidate = _pick_highest_protein_candidate(candidates)
        if protein_candidate is not None:
            prot_g = candidate_protein(protein_candidate) or 0
            conf = float(_safe_float(protein_candidate.get("confidence"), CONF_SOFT_ITEM))
            name = candidate_item_name(protein_candidate, min_confidence=CONF_SOFT_ITEM)
            if name:
                why = _protein_catchup_why(
                    item_name=name,
                    estimated_protein_g=prot_g,
                    remaining_protein_g=int(rem_protein),
                    meal_window=window,
                )
                result["protein_catchup_option"] = {
                    "name": name,
                    "why": why,
                    "estimated_protein_g": prot_g,
                    "estimated_calories": candidate_calories(protein_candidate),
                    "confidence": round(_clamp(conf, CONF_MIN_ITEM, 0.97), 2),
                    "derived_from": "contextual_overlay",
                }

    # ── lighter_recovery_option ───────────────────────────────────────────────
    rem_cal = float(_safe_float(remaining_calories, -1.0))
    # Show lighter option when: calories are tight OR cut_mode is active with
    # meaningful macro state data.
    low_cal_state = (rem_cal >= 0 and rem_cal <= _LIGHTER_RECOVERY_THRESHOLD_KCAL)
    cut_mode_tight = (cut_mode and rem_cal >= 0 and rem_cal <= 700)
    if low_cal_state or cut_mode_tight:
        light_candidate = _pick_lowest_calorie_candidate(
            candidates, exclude_name=best_choice_name
        )
        if light_candidate is None:
            light_candidate = _pick_lowest_calorie_candidate(candidates)
        if light_candidate is not None:
            cal = candidate_calories(light_candidate) or 0
            conf = float(_safe_float(light_candidate.get("confidence"), CONF_SOFT_ITEM))
            name = candidate_item_name(light_candidate, min_confidence=CONF_SOFT_ITEM)
            if name:
                why = _lighter_recovery_why(
                    item_name=name,
                    estimated_calories=cal,
                    remaining_calories=int(rem_cal) if rem_cal >= 0 else None,
                    meal_window=window,
                    cut_mode=cut_mode,
                )
                result["lighter_recovery_option"] = {
                    "name": name,
                    "why": why,
                    "estimated_calories": cal,
                    "estimated_protein_g": candidate_protein(light_candidate),
                    "confidence": round(_clamp(conf, CONF_MIN_ITEM, 0.97), 2),
                    "derived_from": "contextual_overlay",
                }

    result["contextual_overlay_applied"] = True
    return result


# ─── overlay helpers ────────────────────────────────────────────────────────

def _resolve_meal_window(meal_window: str, current_hour: Optional[int]) -> str:
    token = str(meal_window or "").strip().lower()
    if token in {"breakfast", "lunch", "snack", "dinner"}:
        return token
    if current_hour is not None:
        h = int(max(0, min(23, int(current_hour))))
        if 5 <= h <= 10:
            return "breakfast"
        if 11 <= h <= 14:
            return "lunch"
        if 15 <= h <= 17:
            return "snack"
        if 18 <= h <= 22:
            return "dinner"
    return ""


def _pick_highest_protein_candidate(
    candidates: List[Dict[str, Any]],
    exclude_name: str = "",
) -> Optional[Dict[str, Any]]:
    pool = [
        c for c in candidates
        if str(c.get("name") or "").strip().lower() != exclude_name.lower()
        and float(_safe_float(c.get("estimated_protein_g"), 0.0)) > 0
    ]
    if not pool:
        return None
    return max(pool, key=lambda c: float(_safe_float(c.get("estimated_protein_g"), 0.0)))


def _pick_lowest_calorie_candidate(
    candidates: List[Dict[str, Any]],
    exclude_name: str = "",
) -> Optional[Dict[str, Any]]:
    pool = [
        c for c in candidates
        if str(c.get("name") or "").strip().lower() != exclude_name.lower()
        and float(_safe_float(c.get("estimated_calories"), 0.0)) > 0
    ]
    if not pool:
        return None
    return min(pool, key=lambda c: float(_safe_float(c.get("estimated_calories"), 9999.0)))


def _protein_catchup_why(
    *,
    item_name: str,
    estimated_protein_g: int,
    remaining_protein_g: int,
    meal_window: str,
) -> str:
    protein_str = f"{estimated_protein_g}g protein" if estimated_protein_g > 0 else "strong protein content"
    gap_str = f"you still need {remaining_protein_g}g today" if remaining_protein_g > 0 else "you have a protein gap today"
    window_prefix = {
        "breakfast": "Good protein start",
        "lunch": "Best protein option for lunch",
        "dinner": "Strong protein option for dinner",
        "snack": "Best protein snack here",
    }.get(meal_window, "Best protein pick here")
    return f"{window_prefix} — {protein_str} on this menu, and {gap_str}."


def _lighter_recovery_why(
    *,
    item_name: str,
    estimated_calories: int,
    remaining_calories: Optional[int],
    meal_window: str,
    cut_mode: bool,
) -> str:
    cal_str = f"{estimated_calories} kcal" if estimated_calories > 0 else "lowest calorie option"
    if remaining_calories is not None and remaining_calories >= 0:
        budget_str = f"you have about {remaining_calories} kcal left today"
    elif cut_mode:
        budget_str = "you are in cut mode"
    else:
        budget_str = "calories are tight"
    window_prefix = {
        "snack": "Lightest snack option",
        "breakfast": "Light breakfast option",
        "dinner": "Lighter dinner choice",
        "lunch": "Lighter lunch option",
    }.get(meal_window, "Lightest option here")
    return f"{window_prefix} — {cal_str} on this menu, and {budget_str}."


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
    meal_window: str = "",
    current_hour: Optional[int] = None,
) -> Dict[str, Any]:
    """Use an LLM to reason over real menu text and return structured candidates.

    Combines Stage 1 (structural, cached) with Stage 2 (contextual, live):

    Stage 1 — LLM structural reasoning (cached per menu_text + goal + cut_mode):
      Returns menu_summary, reasoning_confidence, best_choice_here, better_swap,
      avoid_if_cutting, typical_order, ranked_candidates.

    Stage 2 — Deterministic contextual overlay (never cached):
      Derives protein_catchup_option and lighter_recovery_option from the
      structural ranked_candidates using the current user macro state.
      Different users or different macro states produce different outputs.

    Returns a combined dict with all fields.

    reasoning_source values:
      "live_llm"  — fresh LLM call for structural part
      "cache"     — structural part served from in-process cache
      "disabled"  — feature flag off
      "error"     — LLM call failed
    """
    if not _is_enabled():
        return _empty_result("disabled", reasoning_source="disabled")

    text_clean = str(menu_text or "").strip()
    if len(text_clean) < 20:
        return _empty_result("menu_text_too_short", reasoning_source="error")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _empty_result("no_api_key", reasoning_source="error")

    try:
        import google.generativeai as genai  # type: ignore[import] # noqa: F401
    except Exception:
        return _empty_result("genai_unavailable", reasoning_source="error")

    # Stage 1: structural (cached)
    structural = _structural_reason_over_menu(
        text_clean=text_clean,
        place_name=place_name,
        goal=goal,
        cut_mode=cut_mode,
        api_key=api_key,
    )

    if not structural.get("llm_reasoning_used"):
        return structural

    # Stage 2: contextual overlay (live, deterministic)
    return apply_contextual_overlay(
        structural,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        cut_mode=cut_mode,
        meal_window=meal_window,
        current_hour=current_hour,
    )


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
# OPTION B — PLACE CONTEXT REASONING  (no real menu text available)
# ─────────────────────────────────────────────────────────────────────────────
# When no menu text can be retrieved (no website, no OCR, no chain match),
# the LLM can still produce category-appropriate low-confidence candidates
# from the restaurant's name and type.  These are better than pure keyword
# heuristics because the model can reason about what dishes are typical for
# that restaurant category.
#
# Confidence is intentionally capped at 0.55 so:
#  - candidates never show as "Best Menu Item" (requires CONF_EXACT_ITEM 0.65)
#  - candidates show as "Estimated Best Fit" — honest about the uncertainty
#  - items are still specific (e.g. "Tandoori Chicken") not generic ("Lighter option")
#
# Cached by (context_text_hash, goal, cut_mode) — same mechanism as real menu.

_PLACE_CONTEXT_PROMPT = """\
You are a nutrition analyst helping a health-conscious user decide what to eat.
No menu is available for this restaurant — only its name and type are known.
Make reasonable, category-appropriate suggestions based on what is typically
served at this style of restaurant.

Restaurant context:
{place_context}

User goal: {goal}
Strict cut mode (low-calorie priority): {cut_mode}

Return ONLY valid JSON with this structure. All fields optional — omit what
you cannot support from the restaurant type alone:

{{
  "menu_summary": "One sentence: what kind of food does this restaurant typically serve?",
  "reasoning_confidence": 0.48,
  "best_choice_here": {{
    "name": "Well-known dish name typical for this restaurant type",
    "why": "Why this style of dish is usually the best macro-fit here",
    "estimated_calories": 440,
    "estimated_protein_g": 32,
    "confidence": 0.50
  }},
  "better_swap": {{
    "name": "Lighter variant or smarter customisation for this restaurant type",
    "swap_tip": "Specific tip that applies to this kind of restaurant",
    "why": "Why this swap helps",
    "confidence": 0.47
  }},
  "avoid_if_cutting": {{
    "name": "Typically heaviest / most calorie-dense order at this type of place",
    "why": "Why it is hard to fit when the user is cutting",
    "estimated_calories": 880,
    "confidence": 0.46
  }},
  "typical_order": {{
    "name": "What most customers probably order at this kind of restaurant",
    "estimated_calories": 720,
    "confidence": 0.44
  }},
  "ranked_candidates": [
    {{
      "name": "Best protein option typical for this restaurant type",
      "estimated_calories": 440,
      "estimated_protein_g": 34,
      "notes": "highest protein",
      "confidence": 0.50
    }},
    {{
      "name": "Lowest calorie option typical for this restaurant type",
      "estimated_calories": 280,
      "estimated_protein_g": 14,
      "notes": "lowest calorie",
      "confidence": 0.48
    }}
  ]
}}

STRICT RULES:
- reasoning_confidence MUST be between 0.40 and 0.55 (no real menu — honest uncertainty)
- All candidate confidence values MUST be between 0.40 and 0.55
- Use well-known dish CATEGORY names that are genuinely typical for this restaurant type
  e.g. Indian → "Tandoori Chicken", "Dal Makhani", "Butter Chicken"
       Sushi  → "Salmon Sashimi Set", "Edamame + Miso Soup"
       Subway → "6-inch Chicken Sub", "Veggie Delite"
       Cafe   → "Eggs on Toast", "Chicken and Avocado Wrap"
- Do NOT use generic labels: "Lighter menu option", "Protein bowl", "Healthy option", "Best choice"
- Do NOT fabricate unique restaurant-specific dish names that may not exist
- Include estimated_calories and estimated_protein_g where known for the category
- ranked_candidates: include 3–5 typical items covering protein-rich and lighter options
- Return ONLY valid JSON — no markdown fences, no prose before or after
"""

# Generic type tokens that add no cuisine signal — skip when building context
_SKIP_PLACE_TYPES = frozenset(
    {
        "restaurant",
        "food",
        "point of interest",
        "establishment",
        "store",
        "local business",
        "meal takeaway",
        "meal delivery",
    }
)


def build_place_context_text(place: Dict[str, Any]) -> str:
    """Build a minimal restaurant identity string for metadata-based LLM reasoning.

    Used by reason_from_place_context() when no real menu text is available.
    Returns a short multi-line string like:
        Restaurant name: Curry Palace
        Type: indian restaurant
        Location: Wentworthville NSW
    """
    payload = place if isinstance(place, dict) else {}

    name = str(payload.get("name") or "").strip()
    primary = (
        str(payload.get("primary_type") or payload.get("primaryType") or "")
        .strip()
        .replace("_", " ")
    )
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    cuisine_types = [
        str(t or "").replace("_", " ").strip()
        for t in types
        if str(t or "").replace("_", " ").strip().lower() not in _SKIP_PLACE_TYPES
    ]
    vicinity = str(payload.get("vicinity") or payload.get("address") or "").strip()

    parts: List[str] = []
    if name:
        parts.append(f"Restaurant name: {name}")
    if primary and primary.lower() not in _SKIP_PLACE_TYPES:
        parts.append(f"Type: {primary}")
    elif cuisine_types:
        parts.append(f"Type: {', '.join(cuisine_types[:3])}")
    if vicinity:
        parts.append(f"Location: {vicinity}")

    return "\n".join(parts)


def reason_from_place_context(
    place: Dict[str, Any],
    *,
    goal: str = "",
    cut_mode: bool = False,
) -> Dict[str, Any]:
    """Option B: LLM reasoning from place metadata when no menu text exists.

    Returns low-confidence (0.40–0.55) but category-appropriate candidates.
    These are better than pure keyword heuristics because the LLM can reason
    about what dishes are typical for the restaurant type.

    Confidence is capped at 0.55 so items show as "Estimated Best Fit"
    (not "Best Menu Item") — accurate about the uncertainty.

    Results are cached by (context_text_hash, goal, cut_mode) using the same
    in-process LRU cache as real menu reasoning.
    """
    if not _is_enabled():
        return _empty_result("disabled", reasoning_source="disabled")

    context_text = build_place_context_text(place)
    if len(context_text) < 20:
        return _empty_result("insufficient_place_context", reasoning_source="error")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _empty_result("no_api_key", reasoning_source="error")

    try:
        import google.generativeai as genai  # type: ignore[import]
    except Exception:
        return _empty_result("genai_unavailable", reasoning_source="error")

    cache_key = _make_cache_key(context_text, goal, cut_mode)
    cached = _cache_get(cache_key)
    if cached is not None:
        hit = dict(cached)
        hit["cache_hit"] = True
        hit["reasoning_source"] = "cache_context"
        return hit

    goal_str = (
        str(goal or "general healthy eating").strip().replace("_", " ")
        or "general healthy eating"
    )
    prompt = _PLACE_CONTEXT_PROMPT.format(
        place_context=context_text,
        goal=goal_str,
        cut_mode=str(bool(cut_mode)),
    )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=_get_model_name(),
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        response = model.generate_content(
            prompt,
            request_options={"timeout": min(_get_timeout_sec(), 10.0)},
        )
        raw_text = str(getattr(response, "text", "") or "").strip()
        if not raw_text:
            return _empty_result("empty_llm_response", reasoning_source="error")

        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            return _empty_result("invalid_json_structure", reasoning_source="error")

        result = _empty_result()
        result["llm_reasoning_used"] = True
        result["reasoning_source"] = "live_llm_context"
        result["cache_hit"] = False
        result["menu_summary"] = str(parsed.get("menu_summary") or "").strip()

        # Clamp to the metadata-only confidence range.
        raw_conf = _safe_float(parsed.get("reasoning_confidence"), 0.48)
        result["reasoning_confidence"] = float(_clamp(raw_conf, 0.40, 0.55))

        def _clamp_candidate_conf(c: Dict[str, Any]) -> Dict[str, Any]:
            c["confidence"] = float(_clamp(_safe_float(c.get("confidence"), 0.48), 0.40, 0.55))
            return c

        for key in ("best_choice_here", "better_swap", "avoid_if_cutting", "typical_order"):
            cleaned = _clean_candidate(parsed.get(key))
            if cleaned is not None:
                result[key] = _clamp_candidate_conf(cleaned)

        raw_ranked = parsed.get("ranked_candidates")
        if isinstance(raw_ranked, list):
            pre_cleaned = [_clean_ranked_candidate(c) for c in raw_ranked if isinstance(c, dict)]
            pre_cleaned = [c for c in pre_cleaned if c is not None]
            main_names = [
                str((result.get(k) or {}).get("name") or "")
                for k in ("best_choice_here", "better_swap", "avoid_if_cutting", "typical_order")
                if result.get(k)
            ]
            validated, _ = _validate_and_repair_ranked_candidates(
                raw_candidates=pre_cleaned,
                all_named_candidates=main_names,
                reasoning_confidence=result["reasoning_confidence"],
            )
            for c in validated:
                c["confidence"] = float(_clamp(_safe_float(c.get("confidence"), 0.48), 0.40, 0.55))
            result["ranked_candidates"] = validated

        _seed_ranked_from_main_candidates(result)

        if result["llm_reasoning_used"]:
            _cache_put(cache_key, dict(result))

        return result

    except Exception as exc:
        logger.info(
            "reason_from_place_context failed for %s: %s",
            str(place.get("name") or "?")[:40],
            str(exc)[:120],
        )
        return _empty_result(str(exc or "context_reasoning_failed")[:120], reasoning_source="error")


# ─────────────────────────────────────────────────────────────────────────────
# TEXT EXTRACTION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def extract_menu_text_for_reasoning(
    place: Dict[str, Any],
    ingestion_bundle: Optional[Dict[str, Any]] = None,
) -> str:
    """Extract the best available menu text from a place dict and/or ingestion bundle."""
    payload = place if isinstance(place, dict) else {}
    bundle = ingestion_bundle if isinstance(ingestion_bundle, dict) else {}

    for key in ("raw_menu_text", "raw_text", "menu_raw_text"):
        text = str(bundle.get(key) or "").strip()
        if len(text) >= 40:
            return text

    for key in ("menu_text", "menuText", "raw_menu_text", "menu_description", "menuDescription"):
        text = str(payload.get(key) or "").strip()
        if len(text) >= 40:
            return text

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
