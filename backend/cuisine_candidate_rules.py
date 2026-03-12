"""
Cuisine-specific candidate meal archetypes for Healthy Nearby.
Single source for heuristic candidate generation; no LLM.
Used by menu_item_scoring and healthy_order_recommender for consistent,
realistic candidates (Indian, South Indian, cafe, juice, pizza, Subway, etc.).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from diet_filters import filter_candidates_for_diet, normalize_diet_preference

# Source labels for heuristic candidates
SOURCE_HEURISTIC_CUISINE_STRONG = "heuristic_cuisine_match_strong"
SOURCE_HEURISTIC_CUISINE_WEAK = "heuristic_cuisine_match_weak"
SOURCE_MENU_INFERRED = "menu_inferred"
SOURCE_REAL_MENU = "real_menu"
SOURCE_USER_CONFIRMED = "user_confirmed"

# Bad fallback name tokens: do not choose as primary candidate
BAD_FALLBACK_SUPPRESS_TOKENS: Tuple[str, ...] = (
    "egg + chicken plate",
    "egg and chicken plate",
    "salad + chicken plate",
    "chicken plate and salad",
    "grilled protein bowl",  # when venue type does not support it
    "protein bowl",
    "protein plate",
    "lean wrap",
    "protein wrap",
    "lighter menu option",
    "lighter option",
    "healthy option",
    "balanced meal",
    "smart choice",
    "recommended item",
    "best menu item",
    "better choice",
    "low calorie option",
    "high protein option",
    "lighter choice",
    "lighter meal",
    "greek yogurt protein bowl",  # only if venue signals protein
    "needs menu check",
)

# Generic fallbacks that must not be labeled "Best pick" (handled in meal_ranking/ranked_place_builder)
GENERIC_FALLBACK_TOKENS_FOR_LABEL: Tuple[str, ...] = (
    "lighter menu option",
    "lighter option",
    "healthy option",
    "balanced meal",
    "egg + chicken plate",
    "egg and chicken plate",
)


def _candidate(
    candidate_name: str,
    estimated_calories: int,
    estimated_protein_g: int,
    *,
    food_quality_tags: Tuple[str, ...] = (),
    satiety_tags: Tuple[str, ...] = ("medium",),
    cut_friendly: bool = True,
    notes: str = "",
    source_label: str = SOURCE_HEURISTIC_CUISINE_STRONG,
    negative_flags: Tuple[str, ...] = (),
    contains_meat: bool = False,
    contains_chicken: bool = False,
    contains_fish: bool = False,
    contains_egg: bool = False,
    contains_dairy: bool = False,
    contains_whey: bool = False,
    vegetarian_possible: bool = False,
    vegan_possible: bool = False,
) -> Dict[str, Any]:
    return {
        "candidate_name": candidate_name,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "food_quality_tags": list(food_quality_tags),
        "satiety_tags": list(satiety_tags),
        "cut_friendly": cut_friendly,
        "notes": notes,
        "source_label": source_label,
        "negative_flags": list(negative_flags),
        "contains_meat": contains_meat,
        "contains_chicken": contains_chicken,
        "contains_fish": contains_fish,
        "contains_egg": contains_egg,
        "contains_dairy": contains_dairy,
        "contains_whey": contains_whey,
        "vegetarian_possible": vegetarian_possible,
        "vegan_possible": vegan_possible,
    }


# Cuisine groups: tokens (match on place name/address/types), candidates (primary first), avoid_as_primary
CUISINE_GROUPS: List[Dict[str, Any]] = [
    # 1. North Indian / Indian restaurant
    {
        "cuisine_id": "north_indian",
        "tokens": ("indian", "tandoori", "curry", "biryani", "paneer", "dal", "naan", "roti", "north indian"),
        "priority": 10,
        "candidates": [
            _candidate("Tandoori chicken + dal", 580, 42, food_quality_tags=("tandoori", "dal"), satiety_tags=("high",), notes="Strong protein, minimal cream", contains_chicken=True),
            _candidate("Chicken tikka + salad", 520, 38, food_quality_tags=("grilled", "salad"), satiety_tags=("high",), contains_chicken=True),
            _candidate("Paneer tikka + dal", 540, 28, food_quality_tags=("paneer", "dal"), satiety_tags=("high",), contains_dairy=True, vegetarian_possible=True),
            _candidate("Dal + roti", 480, 18, food_quality_tags=("dal", "roti"), satiety_tags=("high",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Chana masala + roti", 520, 16, food_quality_tags=("chana", "roti"), satiety_tags=("high",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Egg bhurji + roti", 450, 26, food_quality_tags=("egg", "roti"), satiety_tags=("medium",), contains_egg=True, vegetarian_possible=True),
            _candidate("Dal + roti + grilled chicken", 560, 40, food_quality_tags=("dal", "grilled"), satiety_tags=("high",), contains_chicken=True),
        ],
        "avoid_as_primary": ("butter chicken", "creamy curry", "biryani combo", "samosa", "pakora", "kheer", "gulab jamun"),
        "base_confidence": 0.62,
        "confidence_note": "Indian restaurant: tandoori/dal candidates are plausible",
    },
    # 2. South Indian / dosa / filter coffee cafe
    {
        "cuisine_id": "south_indian",
        "tokens": ("south indian", "idli", "dosa", "sambar", "udupi", "temple", "canteen", "filter coffee", "chennai", "cfc", "filter coffee"),
        "priority": 11,
        "candidates": [
            _candidate("Egg dosa + sambar", 420, 18, food_quality_tags=("egg", "dosa", "sambar"), satiety_tags=("medium",), notes="Good protein for South Indian", contains_egg=True, vegetarian_possible=True),
            _candidate("Plain dosa + sambar", 380, 12, food_quality_tags=("dosa", "sambar"), satiety_tags=("medium",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Idli + sambar", 360, 13, food_quality_tags=("idli", "sambar"), satiety_tags=("medium",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Uthappam + sambar", 400, 14, food_quality_tags=("uthappam", "sambar"), satiety_tags=("medium",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Omelette + toast", 380, 20, food_quality_tags=("egg", "toast"), satiety_tags=("medium",), contains_egg=True, vegetarian_possible=True),
        ],
        "avoid_as_primary": ("vada combo", "sweet beverage", "coffee only", "banana bread", "only coffee"),
        "base_confidence": 0.58,
        "confidence_note": "South Indian: idli/dosa/egg dosa plausible; avoid coffee-only as meal",
    },
    # 3. General cafe
    {
        "cuisine_id": "cafe",
        "tokens": ("cafe", "coffee", "brunch", "bakery", "espresso", "roastery"),
        "priority": 8,
        "candidates": [
            _candidate("Eggs on toast", 410, 22, food_quality_tags=("egg", "toast"), satiety_tags=("medium",), contains_egg=True, vegetarian_possible=True),
            _candidate("Omelette with vegetables", 420, 24, food_quality_tags=("egg", "vegetables"), satiety_tags=("medium",), contains_egg=True, vegetarian_possible=True),
            _candidate("Avocado toast", 420, 10, food_quality_tags=("avocado", "toast"), satiety_tags=("medium",), vegan_possible=True),
            _candidate("Veggie wrap with hummus", 380, 12, food_quality_tags=("veg", "wrap", "hummus"), satiety_tags=("medium",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Grilled chicken wrap", 480, 28, food_quality_tags=("grilled", "chicken", "wrap"), satiety_tags=("medium",), contains_chicken=True),
            _candidate("Grilled chicken sandwich", 460, 26, food_quality_tags=("grilled", "chicken"), satiety_tags=("medium",), contains_chicken=True),
            _candidate("Yogurt bowl with nuts", 350, 16, food_quality_tags=("yogurt", "nuts"), satiety_tags=("medium",), notes="Only if protein is credible", contains_dairy=True, vegetarian_possible=True),
        ],
        "avoid_as_primary": ("banana bread", "muffin", "pastry", "sweet smoothie", "croissant"),
        "base_confidence": 0.60,
        "confidence_note": "Cafe: eggs/wrap/sandwich plausible; avoid pastry as meal",
    },
    # 4. Juice / smoothie / acai
    {
        "cuisine_id": "juice_smoothie",
        "tokens": ("juice", "smoothie", "smoothie bar", "acai", "juice bar", "fresh juice"),
        "priority": 5,
        "candidates": [
            _candidate("Protein smoothie (lower sugar)", 320, 24, food_quality_tags=("protein", "smoothie"), satiety_tags=("low",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK, notes="Only if menu/category suggests protein add-on", contains_whey=True),
            _candidate("Plant protein smoothie", 300, 20, food_quality_tags=("protein", "smoothie"), satiety_tags=("low",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK, vegan_possible=True),
            _candidate("Greek yogurt bowl", 280, 18, food_quality_tags=("yogurt", "protein"), satiety_tags=("medium",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK, notes="Only if protein is plausible", contains_dairy=True, vegetarian_possible=True),
            _candidate("Green smoothie with protein add-on", 260, 20, food_quality_tags=("smoothie", "protein"), satiety_tags=("low",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK),
        ],
        "avoid_as_primary": ("fruit juice", "acai bowl", "sweet smoothie", "high sugar smoothie"),
        "base_confidence": 0.42,
        "confidence_note": "Juice center: low confidence unless protein is clearly available",
    },
    # 5. Pizza
    {
        "cuisine_id": "pizza",
        "tokens": ("pizza", "pizzeria", "slice"),
        "priority": 6,
        "candidates": [
            _candidate("2 thin-crust slices, veggie or chicken", 560, 26, food_quality_tags=("thin crust", "portion control"), satiety_tags=("medium",), notes="No sides, no drink"),
            _candidate("Thin-crust personal, light toppings", 580, 28, food_quality_tags=("thin crust", "light toppings"), satiety_tags=("medium",)),
            _candidate("1 slice + side salad", 480, 22, food_quality_tags=("portion control", "salad"), satiety_tags=("medium",)),
        ],
        "avoid_as_primary": ("combo meal", "garlic bread", "loaded crust", "dessert bundle", "stuffed crust"),
        "base_confidence": 0.58,
        "confidence_note": "Pizza: controlled portion plausible; combo/sides suppressed",
    },
    # 6. Sandwich / Subway-style
    {
        "cuisine_id": "sandwich_sub",
        "tokens": ("subway", "sub", "footlong", "deli", "sub sandwich", "sandwich bar"),
        "priority": 9,
        "candidates": [
            _candidate("6-inch grilled chicken sub, extra salad, light sauce", 390, 30, food_quality_tags=("grilled", "chicken", "salad"), satiety_tags=("high",), contains_chicken=True),
            _candidate("Veggie sub, extra salad, light sauce", 320, 14, food_quality_tags=("veg", "salad"), satiety_tags=("medium",), vegetarian_possible=True, vegan_possible=True),
            _candidate("Grilled chicken salad bowl (no bread)", 310, 34, food_quality_tags=("grilled", "chicken", "salad"), satiety_tags=("high",), contains_chicken=True),
            _candidate("6-inch turkey sub, extra salad, no mayo", 350, 26, food_quality_tags=("turkey", "salad"), satiety_tags=("medium",), contains_meat=True),
        ],
        "avoid_as_primary": ("meatball", "heavy sauce", "loaded combo", "footlong with mayo"),
        "base_confidence": 0.68,
        "confidence_note": "Subway-style: grilled chicken sub is high-confidence heuristic",
    },
]


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, type_text] if x)


def _match_cuisine_group(place_text: str) -> Tuple[Dict[str, Any] | None, int]:
    """Return (group, hit_count). Higher priority wins on tie; then more hits."""
    best = None
    best_hits = 0
    best_priority = -1
    for group in CUISINE_GROUPS:
        hits = sum(1 for t in group.get("tokens", ()) if t in place_text)
        if hits <= 0:
            continue
        priority = int(group.get("priority", 0))
        if hits > best_hits or (hits == best_hits and priority > best_priority):
            best_hits = hits
            best = group
            best_priority = priority
    return best, best_hits


def _is_bad_fallback(candidate_name: str) -> bool:
    lower = str(candidate_name or "").strip().lower()
    return any(t in lower for t in BAD_FALLBACK_SUPPRESS_TOKENS)


def _should_suppress_primary(candidate_name: str, avoid_as_primary: Tuple[str, ...]) -> bool:
    if _is_bad_fallback(candidate_name):
        return True
    lower = str(candidate_name or "").strip().lower()
    return any(t in lower for t in (avoid_as_primary or ()))


def get_candidates_for_place(
    place: Dict[str, Any],
    *,
    max_candidates: int = 3,
    cut_mode: bool = False,
    diet_preference: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str | None, float, str]:
    """
    Return (candidates, matched_cuisine_id, confidence, source_label).
    Candidates are ordered: primary (best for CUT), secondary, tertiary.
    diet_preference filters candidates for vegetarian/vegan users.
    """
    place_text = _place_text(place)
    if not place_text:
        return [], None, 0.42, SOURCE_HEURISTIC_CUISINE_WEAK

    group, hits = _match_cuisine_group(place_text)
    if not group:
        return [], None, 0.42, SOURCE_HEURISTIC_CUISINE_WEAK

    raw = list(group.get("candidates") or [])
    avoid = tuple(group.get("avoid_as_primary") or ())
    base_conf = float(group.get("base_confidence", 0.52))
    # Slightly higher confidence when match is strong (more tokens)
    if hits >= 2:
        base_conf = min(0.78, base_conf + 0.08)
    elif hits >= 1:
        base_conf = min(0.70, base_conf + 0.04)

    # Filter by diet preference (vegetarian/vegan)
    diet = normalize_diet_preference(diet_preference)
    diet_excluded = 0
    if diet != "omnivore":
        raw, diet_excluded = filter_candidates_for_diet(raw, diet)
        if not raw:
            base_conf = min(base_conf, 0.48)
            # Diet-safe generic fallback when no cuisine-specific candidates pass
            if diet == "vegan":
                raw = [_candidate("Dal + roti (needs menu check)", 480, 16, food_quality_tags=("dal", "roti"), satiety_tags=("high",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK, vegan_possible=True)]
            else:
                raw = [_candidate("Vegetarian option (needs menu check)", 450, 16, food_quality_tags=("veg",), satiety_tags=("medium",), source_label=SOURCE_HEURISTIC_CUISINE_WEAK, vegetarian_possible=True)]

    # Filter out suppressed-as-primary; they can still be secondary/tertiary if we have others
    allowed = [c for c in raw if not _should_suppress_primary(c.get("candidate_name") or "", avoid)]
    if not allowed:
        allowed = raw

    # Take up to max_candidates
    selected = allowed[:max_candidates]
    source = SOURCE_HEURISTIC_CUISINE_STRONG if base_conf >= 0.58 else SOURCE_HEURISTIC_CUISINE_WEAK
    return selected, str(group.get("cuisine_id") or ""), round(base_conf, 2), source


def _candidate_score_for_selection(
    candidate: Dict[str, Any],
    cut_mode: bool,
    remaining_calories: float | None = None,
    remaining_protein_g: float | None = None,
) -> float:
    """
    Deterministic local score for choosing best of N heuristic candidates.
    Higher = better. Uses protein density, calorie fit, food quality, satiety, penalties.
    """
    name = str(candidate.get("candidate_name") or "").strip().lower()
    cal = int(candidate.get("estimated_calories") or 520)
    pro = int(candidate.get("estimated_protein_g") or 28)
    cut_friendly = bool(candidate.get("cut_friendly", True))
    neg_flags = candidate.get("negative_flags") or []

    score = 50.0
    # Protein density (protein per 100 kcal) — prefer 6+ g/100kcal in CUT
    if cal > 0:
        density = (pro / cal) * 100
        if density >= 7:
            score += 20.0
        elif density >= 5:
            score += 12.0
        elif density >= 4:
            score += 5.0
        elif density < 3 and cut_mode:
            score -= 15.0
    # Calorie fit
    if remaining_calories is not None and remaining_calories > 0:
        if cal <= remaining_calories * 1.05:
            score += 10.0
        elif cal <= remaining_calories * 1.25:
            score += 2.0
        elif cal > remaining_calories * 1.5 and cut_mode:
            score -= 12.0
    # Protein fit
    if remaining_protein_g is not None and remaining_protein_g > 0 and pro >= remaining_protein_g * 0.5:
        score += 8.0
    # Cut-friendly tag
    if cut_mode and cut_friendly:
        score += 6.0
    # Satiety
    satiety = (candidate.get("satiety_tags") or ["medium"])[0] if candidate.get("satiety_tags") else "medium"
    if satiety == "high":
        score += 6.0
    elif satiety == "medium":
        score += 2.0
    # Penalties
    if any("sugar" in str(f).lower() for f in neg_flags):
        score -= 10.0
    if any("fried" in str(f).lower() for f in neg_flags):
        score -= 8.0
    if any("combo" in str(f).lower() for f in neg_flags):
        score -= 6.0
    if _is_bad_fallback(candidate.get("candidate_name") or ""):
        score -= 25.0
    return score


def select_best_candidate(
    candidates: List[Dict[str, Any]],
    place: Dict[str, Any],
    *,
    cut_mode: bool = False,
    remaining_calories: float | None = None,
    remaining_protein_g: float | None = None,
) -> Tuple[Dict[str, Any] | None, str]:
    """
    Pick the single best candidate from the list. Returns (candidate, why_kept).
    """
    if not candidates:
        return None, "no_candidates"
    place_text = _place_text(place)
    scored = []
    for c in candidates:
        s = _candidate_score_for_selection(c, cut_mode, remaining_calories, remaining_protein_g)
        scored.append((s, c))
    scored.sort(key=lambda x: (-x[0], (x[1].get("estimated_calories") or 999), -(x[1].get("estimated_protein_g") or 0)))
    best = scored[0][1] if scored else None
    why = "selected_as_primary"
    if best and len(scored) > 1:
        why = "best_cut_fit" if cut_mode else "best_balanced"
    return best, why


def get_best_order_for_place_heuristic(
    place: Dict[str, Any],
    *,
    cut_mode: bool = False,
    remaining_calories: float | None = None,
    remaining_protein_g: float | None = None,
    diet_preference: Optional[str] = None,
) -> Tuple[str, int, int, float, str, List[Dict[str, Any]]]:
    """
    Return (best_order_name, estimated_calories, estimated_protein_g, confidence, source_label, all_candidates_for_debug).
    Used by healthy_order_recommender and menu_item_scoring.
    """
    candidates, cuisine_id, confidence, source_label = get_candidates_for_place(
        place, max_candidates=3, cut_mode=cut_mode, diet_preference=diet_preference
    )
    if not candidates:
        return "Lighter menu option", 520, 28, 0.42, SOURCE_HEURISTIC_CUISINE_WEAK, []

    best, why = select_best_candidate(
        candidates, place, cut_mode=cut_mode, remaining_calories=remaining_calories, remaining_protein_g=remaining_protein_g
    )
    if not best:
        c = candidates[0]
        return (
            str(c.get("candidate_name") or "Lighter menu option"),
            int(c.get("estimated_calories") or 520),
            int(c.get("estimated_protein_g") or 28),
            confidence,
            source_label,
            candidates,
        )
    return (
        str(best.get("candidate_name") or "Lighter menu option"),
        int(best.get("estimated_calories") or 520),
        int(best.get("estimated_protein_g") or 28),
        confidence,
        source_label,
        candidates,
    )


def is_generic_fallback_for_label(item_name: str) -> bool:
    """True if this name should never get 'Best pick' (heuristic)."""
    lower = str(item_name or "").strip().lower()
    return any(t in lower for t in GENERIC_FALLBACK_TOKENS_FOR_LABEL)
