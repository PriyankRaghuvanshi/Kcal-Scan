"""
Scan food rules: deterministic overrides for common high-risk nutrition mismatches.

Primary use: protein powders / supplements.
- Do NOT trust generic USDA mapping for powders.
- Use structured supplement macro fallbacks.
- Allow user confirmation via rerun edits (swap_item + set_item_grams).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


SENTINEL_PREFIX = "supplement_powder:"

# Powder types exposed to UI
POWDER_TYPES = (
    "whey",
    "whey_isolate",
    "plant_protein",
    "mass_gainer",
    "cocoa_powder",
    "pre_workout",
    "other_powder",
)

SCOOP_SIZES_G = (25, 30, 40)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def build_powder_sentinel(powder_type: str) -> str:
    pt = _norm(powder_type).replace(" ", "_")
    if pt not in POWDER_TYPES:
        pt = "other_powder"
    return f"{SENTINEL_PREFIX}{pt}"


def parse_powder_sentinel(name: str) -> Optional[str]:
    n = _norm(name)
    if not n.startswith(SENTINEL_PREFIX):
        return None
    pt = n[len(SENTINEL_PREFIX):].strip()
    pt = pt.replace(" ", "_")
    return pt if pt in POWDER_TYPES else "other_powder"


def detect_powder_like(name: str, alternatives: Optional[list] = None) -> Tuple[bool, Optional[str], bool]:
    """
    Returns (is_powder, powder_type_guess, needs_confirmation).
    needs_confirmation True when we think it's powder but type is ambiguous.
    """
    n = _norm(name)
    alts = [_norm(x) for x in (alternatives or []) if str(x or "").strip()]
    text = " | ".join([n] + alts)

    # Sentinel means confirmed.
    sentinel = parse_powder_sentinel(n)
    if sentinel:
        return True, sentinel, False

    powder_hints = ("protein powder", "whey", "isolate", "plant protein", "powdered", "supplement", "drink mix")
    cocoa_hints = ("cocoa powder", "cacao powder", "unsweetened cocoa")
    gainer_hints = ("mass gainer", "weight gainer")
    preworkout_hints = ("pre workout", "pre-workout", "preworkout")

    if any(h in text for h in cocoa_hints):
        return True, "cocoa_powder", False
    if any(h in text for h in gainer_hints):
        return True, "mass_gainer", False
    if any(h in text for h in preworkout_hints):
        # Keep distinct: do NOT treat as protein powder.
        return True, "pre_workout", False
    if any(h in text for h in powder_hints):
        # Try to guess type
        if "isolate" in text:
            return True, "whey_isolate", False
        if "plant" in text or "pea" in text or "soy" in text:
            return True, "plant_protein", False
        if "whey" in text:
            # Whey vs isolate ambiguity => ask confirm if isolate not seen
            return True, "whey", True
        if "protein powder" in text or "supplement" in text or "powdered" in text:
            return True, "other_powder", True
    return False, None, False


def powder_macros_per_30g(powder_type: str) -> Dict[str, float]:
    """
    Structured supplement macro table defaults for 30g serving.
    Values are intentionally conservative and realistic.
    """
    pt = _norm(powder_type).replace(" ", "_")
    if pt == "whey_isolate":
        return {"kcal": 115.0, "protein_g": 26.0, "carbs_g": 2.0, "fat_g": 1.0}
    if pt == "plant_protein":
        return {"kcal": 120.0, "protein_g": 22.0, "carbs_g": 4.0, "fat_g": 2.5}
    if pt == "mass_gainer":
        # Gainers are calorie-heavy and should not be treated as whey.
        return {"kcal": 190.0, "protein_g": 12.0, "carbs_g": 24.0, "fat_g": 3.0}
    if pt == "pre_workout":
        # Pre-workout: typically low/no protein; treat as near-zero macros.
        return {"kcal": 10.0, "protein_g": 0.0, "carbs_g": 2.0, "fat_g": 0.0}
    if pt == "cocoa_powder":
        # Cocoa powder is distinct: low protein per 30g relative to whey.
        return {"kcal": 70.0, "protein_g": 5.0, "carbs_g": 16.0, "fat_g": 4.0}
    if pt in ("whey", "other_powder"):
        return {"kcal": 120.0, "protein_g": 24.0, "carbs_g": 3.0, "fat_g": 2.0}
    return {"kcal": 120.0, "protein_g": 20.0, "carbs_g": 4.0, "fat_g": 2.0}


def is_likely_supplement_powder(top_candidates: list[dict], items: Optional[list[dict]] = None) -> bool:
    """Dashboard/helper: detect likely supplement powder from scan top_candidates and/or item names."""
    tc = top_candidates if isinstance(top_candidates, list) else []
    its = items if isinstance(items, list) else []
    labels = [str(c.get("label") or c.get("name") or "").strip() for c in tc if isinstance(c, dict)]
    names = [str(it.get("name") or "").strip() for it in its if isinstance(it, dict)]
    for s in (labels + names):
        is_powder, _, _ = detect_powder_like(s, [])
        if is_powder:
            return True
    return False


def classify_powder_type(name: str, alternatives: Optional[list] = None) -> str:
    """Return powder type key or empty string if not powder-like."""
    is_powder, guess, _ = detect_powder_like(name, alternatives)
    return str(guess or "") if is_powder and guess else ""


def resolve_powder_nutrition(
    *,
    powder_type: str,
    grams: float,
) -> Dict[str, Any]:
    """
    Return a pseudo 'resolved' nutrition payload compatible with scan pipeline.
    Provides macros100 (per 100g) so downstream scaling stays consistent.
    """
    g = max(0.0, float(grams or 0.0))
    base = powder_macros_per_30g(powder_type)
    # Convert 30g serving macros to per-100g macros.
    factor_100 = (100.0 / 30.0)
    macros100 = {
        "kcal_per_100g": round(base["kcal"] * factor_100, 4),
        "protein_g_per_100g": round(base["protein_g"] * factor_100, 4),
        "carbs_g_per_100g": round(base["carbs_g"] * factor_100, 4),
        "fat_g_per_100g": round(base["fat_g"] * factor_100, 4),
    }
    return {
        "macros100": macros100,
        "micros100": {},
        "fdc_id": None,
        "description": f"Supplement powder ({powder_type})",
        "dataType": "supplement_table",
        "source": "supplement_table",
        "resolved_name": f"{build_powder_sentinel(powder_type)}",
        "needs_powder_confirmation": bool(powder_type in {"whey", "other_powder"}),
        "powder_confirmation": {
            "powder_types": list(POWDER_TYPES),
            "scoop_sizes_g": list(SCOOP_SIZES_G),
            "default_scoop_g": 30,
        },
    }

