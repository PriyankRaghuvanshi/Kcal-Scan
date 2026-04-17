from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

FAMILY_HABITS_VERSION = "v1"
SUPPORTED_RESCUE_TYPES = {
    "refusing_dinner",
    "snack_obsession",
    "lunchbox_returned",
    "too_much_takeaway",
    "making_separate_meals",
}
EXPOSURE_RESPONSE_STAGES = [
    "offered",
    "touched",
    "smelled",
    "licked",
    "tasted",
    "ate_little",
    "accepted",
]


MEAL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "template_id": "build_your_own_taco_bowls",
        "meal_name": "Build-your-own taco bowls",
        "prep_time_min": 20,
        "energy_fit": ["low", "medium", "good"],
        "goals": ["one meal", "use pantry items", "easy exposure"],
        "safe_options": ["rice", "plain tortilla", "grated cheese", "avocado"],
        "exposure_options": ["beans", "corn salsa", "capsicum", "tomato"],
        "child_tweak": "Keep components separate and let each child choose one tiny add-on.",
        "adult_upgrade": "Add hot sauce, lime, crunchy slaw, or extra herbs.",
        "reasoning_tags": ["deconstructed", "repeatable", "low-friction", "pantry_friendly"],
    },
    {
        "template_id": "pasta_plus_plate",
        "meal_name": "Simple pasta + plate-style sides",
        "prep_time_min": 18,
        "energy_fit": ["low", "medium"],
        "goals": ["fast", "minimal cleanup", "safe first"],
        "safe_options": ["plain pasta", "butter", "parmesan", "toast"],
        "exposure_options": ["meat sauce", "peas", "zucchini ribbons", "lentil bolognese"],
        "child_tweak": "Serve the sauce on the side and keep a plain portion visible from the start.",
        "adult_upgrade": "Top with chilli oil, olives, rocket, or extra protein.",
        "reasoning_tags": ["familiar_base", "quick_win", "safe_food_coverage"],
    },
    {
        "template_id": "snack_plate_dinner",
        "meal_name": "Balanced snack plate dinner",
        "prep_time_min": 10,
        "energy_fit": ["low"],
        "goals": ["survival night", "no-cook", "reduce battles"],
        "safe_options": ["crackers", "fruit", "yoghurt", "cheese"],
        "exposure_options": ["cucumber", "boiled egg", "hummus", "turkey slices"],
        "child_tweak": "Use a tiny exposure portion and keep the rest of the plate very familiar.",
        "adult_upgrade": "Turn yours into a grown-up board with dip, salad, or smoked salmon.",
        "reasoning_tags": ["rescue_friendly", "high_acceptance", "minimal_prep"],
    },
    {
        "template_id": "sheet_pan_chicken_and_veg",
        "meal_name": "Sheet-pan chicken and roast veg",
        "prep_time_min": 30,
        "energy_fit": ["medium", "good"],
        "goals": ["one tray", "batch friendly", "family meal"],
        "safe_options": ["potato wedges", "plain chicken", "bread roll"],
        "exposure_options": ["roasted carrots", "broccoli", "capsicum", "seasoned chicken"],
        "child_tweak": "Pull one portion earlier with lighter seasoning if needed.",
        "adult_upgrade": "Add a yogurt sauce, chilli flakes, or a sharp salad.",
        "reasoning_tags": ["repeatable", "batch_friendly", "one_tray"],
    },
    {
        "template_id": "breakfast_for_dinner",
        "meal_name": "Breakfast-for-dinner plate",
        "prep_time_min": 15,
        "energy_fit": ["low", "medium"],
        "goals": ["use staples", "quick reset", "reduce refusal"],
        "safe_options": ["toast", "scrambled eggs", "banana", "yoghurt"],
        "exposure_options": ["spinach omelette", "tomato", "mushrooms", "turkey bacon"],
        "child_tweak": "Keep one familiar breakfast item unchanged.",
        "adult_upgrade": "Add chilli eggs, sautéed greens, or avocado.",
        "reasoning_tags": ["fast", "comfort_food", "low_pressure"],
    },
    {
        "template_id": "rice_bowl_stir_fry",
        "meal_name": "Rice bowl with quick stir-fry",
        "prep_time_min": 25,
        "energy_fit": ["medium", "good"],
        "goals": ["one meal", "leftover friendly", "veg exposure"],
        "safe_options": ["rice", "plain chicken", "edamame", "soy drizzle"],
        "exposure_options": ["mixed veg stir-fry", "sauce", "sesame greens"],
        "child_tweak": "Keep rice and protein plain; let the veg be the exposure lane.",
        "adult_upgrade": "Add kimchi, chilli crisp, or extra vegetables.",
        "reasoning_tags": ["modular", "veg_exposure", "leftovers"],
    },
]

RESCUE_TEMPLATES: Dict[str, Dict[str, str]] = {
    "refusing_dinner": {
        "what_to_say": "Dinner is what we have tonight. You do not have to eat it, and you can keep company with us.",
        "what_to_do": "Keep one familiar food on the plate, stay calm, and end the meal without negotiating bites.",
        "what_to_avoid": "Do not chase, bribe, or turn the meal into a long food conversation.",
        "tomorrow_reset": "Plan a predictable breakfast and repeat a familiar family meal rhythm tomorrow night.",
    },
    "snack_obsession": {
        "what_to_say": "Snacks are coming later. Right now this is the meal on offer.",
        "what_to_do": "Use a clear snack boundary, serve dinner, and keep the next snack time predictable.",
        "what_to_avoid": "Do not offer endless snack alternatives once dinner is served.",
        "tomorrow_reset": "Set a simple snack window and include protein + familiar carbs earlier in the day.",
    },
    "lunchbox_returned": {
        "what_to_say": "Looks like lunch was a hard one today. We will make tomorrow easier, not bigger.",
        "what_to_do": "Shrink lunchbox variety, keep one reliable safe food, and repeat one accepted format.",
        "what_to_avoid": "Do not overload tomorrow’s lunchbox with extra choice or guilt.",
        "tomorrow_reset": "Pack one safe base, one easy fruit, and one tiny exposure only if mornings stay calm.",
    },
    "too_much_takeaway": {
        "what_to_say": "We are making tonight simple, not perfect.",
        "what_to_do": "Choose one fallback home meal tonight and write down the two easiest repeat options.",
        "what_to_avoid": "Do not try to fix the whole week with an ambitious meal plan tonight.",
        "tomorrow_reset": "Restock two emergency dinners and decide tomorrow’s meal before 3 pm.",
    },
    "making_separate_meals": {
        "what_to_say": "We are practising one family meal with one small safe add-on.",
        "what_to_do": "Serve one main meal and add a familiar side instead of cooking separate dinners.",
        "what_to_avoid": "Do not build custom meals for each child unless there is a clear allergy, restriction, or other established feeding need.",
        "tomorrow_reset": "Repeat a deconstructed family meal and keep the same safe component visible from the start.",
    },
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(round(float(value)))
        except Exception:
            return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return " ".join(_safe_str(value).lower().split())


def _dedupe_text_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    seen = set()
    for raw in values:
        val = _safe_str(raw)
        key = val.lower()
        if not val or key in seen:
            continue
        seen.add(key)
        out.append(val)
    return out


def _today_iso() -> str:
    return dt.datetime.utcnow().date().isoformat()


def _score_template(
    template: Dict[str, Any],
    *,
    time_available_min: int,
    parent_energy_level: str,
    available_items: List[str],
    dinner_goal: str,
    children: List[Dict[str, Any]],
    safe_foods_by_child: Dict[str, List[str]],
    target_foods_by_child: Dict[str, List[str]],
    recent_exposures: List[Dict[str, Any]],
    family_memory: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    score = 0.0
    reasons: List[str] = []
    energy = _norm_lower(parent_energy_level or "medium")
    goal = _norm_lower(dinner_goal)
    available_tokens = {_norm_lower(x) for x in available_items}
    template_safe = {_norm_lower(x) for x in template.get("safe_options") or []}
    template_exposure = {_norm_lower(x) for x in template.get("exposure_options") or []}
    prep_time = _safe_int(template.get("prep_time_min"), 20)

    if energy in {_norm_lower(x) for x in template.get("energy_fit") or []}:
        score += 2.0
        reasons.append("fits_parent_energy")
    if prep_time <= max(10, time_available_min or 20):
        score += 2.0
        reasons.append("fits_time")
    else:
        score -= min(3.0, (prep_time - max(10, time_available_min or 20)) / 10.0)

    if goal and any(goal in _norm_lower(tag) for tag in template.get("goals") or []):
        score += 1.5
        reasons.append("matches_dinner_goal")

    if available_tokens:
        overlap = len((template_safe | template_exposure) & available_tokens)
        score += min(2.0, overlap * 0.5)
        if overlap:
            reasons.append("uses_available_items")

    coverage_hits = 0
    target_hits = 0
    recent_bad_formats = {_norm_lower(x.get("food_name")) for x in recent_exposures if _norm_lower(x.get("response_stage")) in {"offered", "touched"}}
    for child in children:
        child_id = _safe_str(child.get("child_id"))
        safe_foods = {_norm_lower(x) for x in safe_foods_by_child.get(child_id) or []}
        active_targets = {_norm_lower(x) for x in target_foods_by_child.get(child_id) or []}
        if template_safe & safe_foods:
            coverage_hits += 1
        if template_exposure & active_targets:
            target_hits += 1
        if template_exposure & recent_bad_formats:
            score -= 0.5

    if children:
        score += min(3.0, coverage_hits * 1.2)
        if coverage_hits:
            reasons.append("safe_food_coverage")
        score += min(2.0, target_hits * 0.6)
        if target_hits:
            reasons.append("target_food_exposure")

    successful_meals = {_norm_lower(x.get("meal_name")) for x in family_memory.get("successful_meals") or []}
    if _norm_lower(template.get("meal_name")) in successful_meals:
        score += 1.5
        reasons.append("worked_before")

    if "making_separate_meals" in {_norm_lower(x) for x in family_memory.get("risk_contexts") or []}:
        if "deconstructed" in {_norm_lower(x) for x in template.get("reasoning_tags") or []}:
            score += 0.8
            reasons.append("reduces_separate_meals")

    return score, {"reasoning_tags": reasons, "coverage_hits": coverage_hits, "target_hits": target_hits}


def recommend_one_meal_tonight(
    *,
    household: Dict[str, Any],
    children: List[Dict[str, Any]],
    safe_foods: List[Dict[str, Any]],
    target_foods: List[Dict[str, Any]],
    recent_exposures: List[Dict[str, Any]],
    family_memory: Optional[Dict[str, Any]],
    time_available_min: int,
    parent_energy_level: str,
    available_items: Optional[List[str]] = None,
    dinner_goal: Optional[str] = None,
) -> Dict[str, Any]:
    available = _dedupe_text_list(available_items or [])
    safe_by_child: Dict[str, List[str]] = defaultdict(list)
    for row in safe_foods or []:
        safe_by_child[_safe_str(row.get("child_id"))].append(_safe_str(row.get("food_name")))
    target_by_child: Dict[str, List[str]] = defaultdict(list)
    for row in target_foods or []:
        target_by_child[_safe_str(row.get("child_id"))].append(_safe_str(row.get("food_name")))

    scored: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    memory = family_memory if isinstance(family_memory, dict) else {}
    for template in MEAL_TEMPLATES:
        score, meta = _score_template(
            template,
            time_available_min=time_available_min,
            parent_energy_level=parent_energy_level,
            available_items=available,
            dinner_goal=_safe_str(dinner_goal),
            children=children,
            safe_foods_by_child=safe_by_child,
            target_foods_by_child=target_by_child,
            recent_exposures=recent_exposures,
            family_memory=memory,
        )
        scored.append((score, template, meta))

    scored.sort(key=lambda item: (item[0], -_safe_int(item[1].get("prep_time_min"), 99)), reverse=True)
    best_score, template, meta = scored[0]

    all_safe = [food for foods in safe_by_child.values() for food in foods]
    all_targets = [food for foods in target_by_child.values() for food in foods]
    safe_component = next((item for item in template.get("safe_options") or [] if _norm_lower(item) in {_norm_lower(x) for x in all_safe}), None)
    if not safe_component:
        safe_component = (template.get("safe_options") or ["familiar side"])[0]
    exposure_component = next((item for item in template.get("exposure_options") or [] if _norm_lower(item) in {_norm_lower(x) for x in all_targets}), None)
    if not exposure_component:
        exposure_component = (template.get("exposure_options") or ["tiny exposure portion"])[0]

    child_focus = []
    for child in children[:2]:
        child_focus.append(
            {
                "child_name": _safe_str(child.get("display_name") or child.get("name") or "Child"),
                "safe_food_hint": next(iter(safe_by_child.get(_safe_str(child.get("child_id")), []) or []), safe_component),
                "target_food_hint": next(iter(target_by_child.get(_safe_str(child.get("child_id")), []) or []), exposure_component),
            }
        )

    return {
        "version": FAMILY_HABITS_VERSION,
        "household_goal": _safe_str(household.get("goal") or "one family meal"),
        "meal_name": _safe_str(template.get("meal_name")),
        "safe_component": safe_component,
        "exposure_component": exposure_component,
        "child_tweak": _safe_str(template.get("child_tweak")),
        "adult_upgrade": _safe_str(template.get("adult_upgrade")),
        "prep_time_min": _safe_int(template.get("prep_time_min"), 0),
        "reasoning_tags": list(dict.fromkeys((template.get("reasoning_tags") or []) + (meta.get("reasoning_tags") or []))),
        "child_focus": child_focus,
        "score": round(best_score, 2),
    }


def build_exposure_summary(exposures: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in exposures or []:
        child_id = _safe_str(row.get("child_id"))
        food_name = _safe_str(row.get("food_name"))
        if not child_id or not food_name:
            continue
        grouped[(child_id, food_name)].append(row)

    summaries: List[Dict[str, Any]] = []
    for (child_id, food_name), rows in grouped.items():
        offered = len(rows)
        tasted = sum(1 for row in rows if _norm_lower(row.get("response_stage")) in {"tasted", "ate_little", "accepted"})
        accepted = sum(1 for row in rows if _norm_lower(row.get("response_stage")) == "accepted")
        formats = Counter(_safe_str(row.get("food_format") or row.get("format") or "unknown") for row in rows)
        pairings = Counter(_safe_str(row.get("paired_safe_food") or "") for row in rows if _safe_str(row.get("paired_safe_food")))
        accepted_formats = Counter(
            _safe_str(row.get("food_format") or row.get("format") or "unknown")
            for row in rows
            if _norm_lower(row.get("response_stage")) in {"ate_little", "accepted"}
        )
        last_offered = sorted((_safe_str(row.get("created_at") or row.get("offered_at")) for row in rows if _safe_str(row.get("created_at") or row.get("offered_at"))), reverse=True)
        best_format = accepted_formats.most_common(1)[0][0] if accepted_formats else (formats.most_common(1)[0][0] if formats else "")
        worst_format = formats.most_common()[-1][0] if formats else ""
        best_pairing = pairings.most_common(1)[0][0] if pairings else ""

        progress_state = "new"
        if accepted >= 2:
            progress_state = "accepted"
        elif accepted >= 1:
            progress_state = "accepted_in_some_formats"
        elif tasted >= 2:
            progress_state = "warming_up"
        elif tasted >= 1 and len(formats) >= 2:
            progress_state = "format_sensitive"
        elif offered >= 3 and tasted == 0:
            progress_state = "stalled"
        elif offered >= 2:
            progress_state = "early_exposure"

        if progress_state == "accepted":
            next_recommendation = "Keep this food in rotation once or twice a week in the format that works best."
        elif progress_state == "accepted_in_some_formats":
            next_recommendation = f"Repeat the accepted format{f' ({best_format})' if best_format else ''} before trying a new version."
        elif progress_state == "format_sensitive":
            next_recommendation = f"Stick with the best format{f' ({best_format})' if best_format else ''} and keep portions tiny."
        elif progress_state == "warming_up":
            next_recommendation = "Offer the same food again with a familiar safe pairing and no pressure to eat."
        elif progress_state == "stalled":
            next_recommendation = "Pause for a few days, then retry a smaller portion or a gentler format."
        else:
            next_recommendation = "Keep exposure tiny, visible, and predictable alongside a safe food."

        summaries.append(
            {
                "child_id": child_id,
                "food_name": food_name,
                "times_offered": offered,
                "times_tasted": tasted,
                "times_accepted": accepted,
                "last_offered_at": last_offered[0] if last_offered else "",
                "best_format": best_format,
                "worst_format": worst_format,
                "best_pairing": best_pairing,
                "progress_state": progress_state,
                "next_recommendation": next_recommendation,
            }
        )

    summaries.sort(key=lambda row: (row["child_id"], row["food_name"]))
    return {"version": FAMILY_HABITS_VERSION, "summaries": summaries}


def build_rescue_response(issue_type: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    issue_key = _norm_lower(issue_type)
    if issue_key not in SUPPORTED_RESCUE_TYPES:
        raise ValueError("unsupported_issue_type")
    template = RESCUE_TEMPLATES[issue_key]
    ctx = context if isinstance(context, dict) else {}
    child_name = _safe_str(ctx.get("child_name") or "your child")
    calming_note = _safe_str(ctx.get("calming_note") or "Keep the tone calm and low-pressure.")
    return {
        "issue_type": issue_key,
        "what_to_say": template["what_to_say"].replace("us", "us").replace("Your child", child_name),
        "what_to_do_tonight": template["what_to_do"],
        "what_to_avoid": template["what_to_avoid"],
        "tomorrow_reset": template["tomorrow_reset"],
        "confidence": 0.86,
        "guardrails": [
            "No pressure to eat.",
            "No guilt-heavy language.",
            "No calorie or weight-loss framing for children.",
            calming_note,
        ],
    }


def build_weekly_reset(
    *,
    meals_served: List[Dict[str, Any]],
    child_outcomes: List[Dict[str, Any]],
    exposures: List[Dict[str, Any]],
    rescue_sessions: List[Dict[str, Any]],
    routine_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    seven_days_ago = dt.datetime.utcnow() - dt.timedelta(days=7)

    def recent(row: Dict[str, Any]) -> bool:
        raw = _safe_str(row.get("created_at") or row.get("date_served") or row.get("signal_date"))
        if not raw:
            return True
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")) >= seven_days_ago.replace(tzinfo=dt.timezone.utc)
        except Exception:
            return True

    meals = [row for row in meals_served if recent(row)]
    outcomes = [row for row in child_outcomes if recent(row)]
    exposures_recent = [row for row in exposures if recent(row)]
    rescues = [row for row in rescue_sessions if recent(row)]
    signals = [row for row in routine_signals if recent(row)]

    one_meal_nights = sum(1 for row in meals if not bool(row.get("separate_meals_needed")))
    separate_meal_nights = sum(1 for row in meals if bool(row.get("separate_meals_needed")))
    takeaway_count = sum(1 for row in meals if bool(row.get("is_takeaway")))
    rescue_mode_frequency = len(rescues)
    lunchbox_issue_frequency = sum(1 for row in rescues if _norm_lower(row.get("issue_type")) == "lunchbox_returned")
    exposure_count_per_child = Counter(_safe_str(row.get("child_id")) for row in exposures_recent if _safe_str(row.get("child_id")))
    meal_counter = Counter(_safe_str(row.get("meal_name")) for row in meals if _safe_str(row.get("meal_name")))
    friction_counter = Counter(_safe_str(row.get("signal_type") or row.get("issue_type")) for row in signals + rescues)

    exposure_summary = build_exposure_summary(exposures_recent).get("summaries", [])
    stalled_foods = [row for row in exposure_summary if row.get("progress_state") in {"stalled", "format_sensitive"}]
    best_meal = meal_counter.most_common(1)[0][0] if meal_counter else "Build-your-own family meal"
    best_win = (
        f"You had {one_meal_nights} one-meal night{'s' if one_meal_nights != 1 else ''}."
        if one_meal_nights > 0
        else "You kept showing up for family meals even on messy days."
    )
    strongest_drift = (
        f"Separate meals showed up {separate_meal_nights} time{'s' if separate_meal_nights != 1 else ''}."
        if separate_meal_nights > 0
        else f"Takeaway happened {takeaway_count} time{'s' if takeaway_count != 1 else ''}."
        if takeaway_count > 0
        else "The main drift was inconsistency rather than one big problem."
    )
    exposure_to_retry = stalled_foods[0]["food_name"] if stalled_foods else (exposure_summary[0]["food_name"] if exposure_summary else "a familiar target food")
    habit_to_restore = friction_counter.most_common(1)[0][0] if friction_counter else "pre-deciding tomorrow's dinner"
    summary_text = (
        f"This week’s strongest win was {best_win.lower()} "
        f"The biggest drift was {strongest_drift.lower()} "
        f"Repeat {best_meal} next week, retry {exposure_to_retry}, and restore {habit_to_restore}."
    )

    return {
        "version": FAMILY_HABITS_VERSION,
        "week_start": (dt.date.today() - dt.timedelta(days=dt.date.today().weekday())).isoformat(),
        "strongest_win": best_win,
        "strongest_drift": strongest_drift,
        "meal_to_repeat": best_meal,
        "exposure_to_retry": exposure_to_retry,
        "habit_to_restore": habit_to_restore,
        "summary_text": summary_text,
        "weekly_features": {
            "one_meal_nights": one_meal_nights,
            "separate_meal_nights": separate_meal_nights,
            "takeaway_count": takeaway_count,
            "exposure_count_per_child": dict(exposure_count_per_child),
            "stalled_foods": [row.get("food_name") for row in stalled_foods],
            "rescue_mode_frequency": rescue_mode_frequency,
            "lunchbox_issue_frequency": lunchbox_issue_frequency,
            "best_performing_meals": [name for name, _count in meal_counter.most_common(3)],
            "most_common_friction_point": habit_to_restore,
        },
    }


def build_family_memory_snapshot(
    *,
    meals_served: List[Dict[str, Any]],
    exposures: List[Dict[str, Any]],
    rescue_sessions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    successful_meals = []
    risk_contexts = []
    pairing_counter = Counter()
    meal_counter = Counter(_safe_str(row.get("meal_name")) for row in meals_served if _safe_str(row.get("meal_name")))
    for meal_name, _count in meal_counter.most_common(5):
        successful_meals.append({"meal_name": meal_name})
    for row in rescue_sessions:
        issue = _safe_str(row.get("issue_type"))
        if issue:
            risk_contexts.append(issue)
    for row in exposures:
        food = _safe_str(row.get("food_name"))
        pairing = _safe_str(row.get("paired_safe_food"))
        if food and pairing:
            pairing_counter[(food, pairing)] += 1

    return {
        "version": FAMILY_HABITS_VERSION,
        "successful_meals": successful_meals,
        "risk_contexts": list(dict.fromkeys(risk_contexts))[:5],
        "successful_pairings": [
            {"food_name": food, "paired_safe_food": pairing, "count": count}
            for (food, pairing), count in pairing_counter.most_common(5)
        ],
        "updated_at": dt.datetime.utcnow().isoformat() + "Z",
    }
