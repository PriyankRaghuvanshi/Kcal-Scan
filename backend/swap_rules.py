"""
Deterministic swap intelligence for a chosen menu item.

Outputs structured swaps with deltas. No LLM. No web scraping.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    return _norm(" ".join([name, " ".join(str(t or "") for t in types)]))


def _swap(
    swap_label: str,
    modified_item_name: str,
    calories_delta: int,
    protein_delta: int,
    reason: str,
    swap_type: str,
    *,
    score: float = 0.0,
) -> Dict[str, Any]:
    return {
        "swap_label": swap_label,
        "modified_item_name": modified_item_name,
        "calories_delta": int(calories_delta),
        "protein_delta": int(protein_delta),
        "reason": reason,
        "swap_type": swap_type,
        "_score": float(score),
    }


def _score_swap(swap: Dict[str, Any], *, cut_mode: bool) -> float:
    cal_delta = int(swap.get("calories_delta") or 0)
    pro_delta = int(swap.get("protein_delta") or 0)
    score = 0.0
    # Prefer calorie reductions; in CUT they matter more.
    score += max(0.0, min(30.0, (-cal_delta) / (6.0 if cut_mode else 8.0)))
    # Prefer protein retained/improved.
    score += max(-8.0, min(10.0, pro_delta / 2.0))
    # Penalize swaps that increase calories in CUT.
    if cut_mode and cal_delta > 0:
        score -= 12.0
    return score


def generate_swaps_for_item(
    *,
    place: Dict[str, Any],
    item_name: str,
    estimated_calories: int,
    estimated_protein_g: int,
    cuisine_hint: str = "",
    menu_item_source: str = "",
    menu_item_confidence: float | None = None,
    cut_mode: bool = False,
    max_swaps: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generate 1–3 plausible swaps. Returns (swaps, debug).
    """
    place_text = _place_text(place)
    name = _norm(item_name)
    cuisine = _norm(cuisine_hint) or place_text
    source = _norm(menu_item_source)
    try:
        conf = float(menu_item_confidence) if menu_item_confidence is not None else 0.0
    except Exception:
        conf = 0.0

    swaps: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    def add_if(reason_key: str, condition: bool, swap_obj: Dict[str, Any]) -> None:
        if condition:
            swaps.append(swap_obj)
        else:
            rej = dict(swap_obj)
            rej["_rejected_reason"] = reason_key
            rejected.append(rej)

    # Universal swaps
    add_if(
        "already_no_drink",
        True,
        _swap(
            "No sugary drink",
            f"{item_name} (no sugary drink)",
            calories_delta=-140,
            protein_delta=0,
            reason="Skipping sugary drinks saves calories without hurting protein.",
            swap_type="skip_sugary_drink",
        ),
    )

    # Subway / sandwich
    if any(t in place_text for t in ("subway", "sandwich", "deli", "sub")) or "sub" in name or "sandwich" in name:
        add_if(
            "mayo_present",
            "mayo" not in name and "aioli" not in name,
            _swap(
                "No mayo / light sauce",
                f"{item_name} (no mayo, light sauce)",
                calories_delta=-90,
                protein_delta=0,
                reason="Sauces can add hidden calories; keep it light.",
                swap_type="lighten_sauce",
            ),
        )
        add_if(
            "already_mentions_salad",
            "salad" not in name and "extra salad" not in name,
            _swap(
                "Extra salad",
                f"{item_name} (extra salad)",
                calories_delta=-10,
                protein_delta=0,
                reason="More volume helps satiety with minimal calories.",
                swap_type="add_veg",
            ),
        )
        add_if(
            "already_bowl",
            "bowl" not in name and "no bread" not in name,
            _swap(
                "Bowl instead of bread",
                f"{item_name} (salad bowl, no bread)",
                calories_delta=-120,
                protein_delta=0,
                reason="Dropping bread can reduce calories while keeping protein similar.",
                swap_type="lower_cal_base",
            ),
        )

    # Pizza
    if "pizza" in place_text or "pizza" in name or "slice" in name:
        add_if(
            "already_two_slices",
            "2" not in name and "two" not in name and "2 slices" not in name,
            _swap(
                "2 slices only",
                "2 thin-crust slices (no sides)",
                calories_delta=-180,
                protein_delta=-2,
                reason="Portion control is the easiest win at pizza places.",
                swap_type="portion_control",
            ),
        )
        add_if(
            "garlic_bread_not_present",
            True,
            _swap(
                "Skip garlic bread / sides",
                f"{item_name} (skip sides like garlic bread)",
                calories_delta=-220,
                protein_delta=0,
                reason="Sides add lots of calories with little protein.",
                swap_type="skip_side",
            ),
        )
        add_if(
            "already_thin_crust",
            "thin" not in name and "thin-crust" not in name and "thin crust" not in name,
            _swap(
                "Thin crust",
                f"{item_name} (thin crust)",
                calories_delta=-120,
                protein_delta=0,
                reason="Thin crust reduces base calories.",
                swap_type="lower_cal_base",
            ),
        )

    # Cafe
    if any(t in place_text for t in ("cafe", "coffee", "brunch", "bakery")) or any(t in cuisine for t in ("cafe", "coffee", "brunch")):
        add_if(
            "already_no_sauce",
            "aioli" not in name and "mayo" not in name and "creamy" not in name,
            _swap(
                "No aioli / light sauce",
                f"{item_name} (no aioli, light sauce)",
                calories_delta=-80,
                protein_delta=0,
                reason="Cafe sauces can be calorie dense; keep it light.",
                swap_type="lighten_sauce",
            ),
        )
        add_if(
            "skip_pastry_addon",
            True,
            _swap(
                "Skip pastry side",
                f"{item_name} (skip pastry side)",
                calories_delta=-220,
                protein_delta=0,
                reason="Pastry add-ons add calories without helping protein/satiety much.",
                swap_type="skip_side",
            ),
        )
        add_if(
            "eggs_extra_butter",
            "egg" in name or "omelette" in name,
            _swap(
                "No extra butter",
                f"{item_name} (no extra butter)",
                calories_delta=-60,
                protein_delta=0,
                reason="Reduces calories while keeping the same protein.",
                swap_type="lighten_fat",
            ),
        )

    # Indian
    if any(t in cuisine for t in ("indian", "tandoori", "dal", "paneer", "biryani")) or "indian" in place_text:
        add_if(
            "already_tandoori",
            "tandoori" not in name and "tikka" not in name,
            _swap(
                "Tandoori over creamy curry",
                "Tandoori chicken + dal",
                calories_delta=-160,
                protein_delta=6,
                reason="Tandoori + dal is usually higher protein and less creamy/oily.",
                swap_type="protein_forward_substitution",
            ),
        )
        add_if(
            "roti_over_naan",
            "naan" in name,
            _swap(
                "Roti over naan",
                name.replace("naan", "roti"),
                calories_delta=-90,
                protein_delta=0,
                reason="Roti is often a lighter bread option than naan.",
                swap_type="lower_cal_base",
            ),
        )
        add_if(
            "skip_fried_starter",
            True,
            _swap(
                "Skip fried starter",
                f"{item_name} (skip fried starters)",
                calories_delta=-260,
                protein_delta=0,
                reason="Fried starters add lots of calories with low protein density.",
                swap_type="skip_side",
            ),
        )

    # Juice / smoothie
    if any(t in place_text for t in ("juice", "smoothie", "acai")) or any(t in name for t in ("smoothie", "juice", "acai")):
        # Be conservative: don't propose protein add-on unless menu confidence is decent.
        add_if(
            "lower_sugar",
            True,
            _swap(
                "Lower sugar",
                f"{item_name} (no added sugar, smaller fruit portion)",
                calories_delta=-120,
                protein_delta=0,
                reason="Lower sugar improves calorie control without relying on guessy protein claims.",
                swap_type="lower_sugar",
            ),
        )
        add_if(
            "protein_addon_requires_conf",
            conf >= 0.65 and ("protein" in name or "whey" in name),
            _swap(
                "Add protein (only if available)",
                f"{item_name} (+ protein add-on)",
                calories_delta=+110,
                protein_delta=+20,
                reason="Only add protein if the venue clearly offers it.",
                swap_type="protein_addon",
            ),
        )

    # Score and select top swaps
    for s in swaps:
        s["_score"] = _score_swap(s, cut_mode=cut_mode)
    swaps.sort(key=lambda r: float(r.get("_score") or 0.0), reverse=True)

    # Remove unrealistic or net-worse swaps for CUT
    final: List[Dict[str, Any]] = []
    for s in swaps:
        if cut_mode and int(s.get("calories_delta") or 0) > 0 and int(s.get("protein_delta") or 0) < 10:
            rej = dict(s)
            rej["_rejected_reason"] = "cut_net_worse"
            rejected.append(rej)
            continue
        final.append(s)
        if len(final) >= max(0, min(3, int(max_swaps or 3))):
            break

    # Strip internal scoring keys
    for s in final:
        s.pop("_score", None)
    for s in rejected:
        s.pop("_score", None)

    debug = {
        "place_text": place_text,
        "item_name_norm": name,
        "cut_mode": bool(cut_mode),
        "source": source,
        "confidence": conf,
        "rejected": rejected[:8],
    }
    return final, debug

