import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


COACH_DISCLAIMER = "Informational only. This is general wellness guidance, not medical advice."

_DEFAULT_GOALS = {
    "kcal": 2000.0,
    "protein_g": 150.0,
    "carbs_g": 200.0,
    "fat_g": 70.0,
    "fiber_g": 30.0,
}

_METRIC_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")
_ALERT_LEVELS = ("low", "medium", "high")

_FORBIDDEN_MEDICAL = (
    "diabetes",
    "pcos",
    "thyroid",
    "hypertension",
    "blood pressure",
    "insulin resistance",
    "metformin",
    "statin",
    "treat",
    "treatment",
    "prescribe",
    "prescription",
    "cure",
)

_FORBIDDEN_SUPPLEMENT = (
    "supplement",
    "capsule",
    "tablet",
    "pill",
    "powder",
    "dose",
    "mg ",
    " iu",
)

_METRIC_HINT_WORDS = (
    "protein",
    "fiber",
    "calorie",
    "kcal",
    "glycemic",
    "gl",
    "upf",
    "processed",
    "leucine",
    "late",
    "dinner",
    "carb",
    "fat",
)

_FORBIDDEN_WEIGHT_PROMISE_RE = re.compile(
    r"\b(?:you(?:'ll| will)?|will)\s+(?:lose|gain)\s+\d+(?:\.\d+)?\s*(?:kg|kgs|kilogram|kilograms|lb|lbs|pound|pounds)\b",
    re.IGNORECASE,
)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def round1(x: float) -> float:
    return float(f"{float(x):.1f}")


def _obj(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def normalize_daily_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    goals_src = _obj(src.get("goals"))
    consumed_src = _obj(src.get("consumed"))
    signals_src = _obj(src.get("signals"))
    timing_src = _obj(src.get("meal_timing"))
    constraints_src = _obj(src.get("constraints"))
    profile_src = _obj(src.get("profile"))
    health_src = _obj(src.get("health_context"))

    goals = {
        k: _safe_float(goals_src.get(k), _DEFAULT_GOALS[k]) for k in _METRIC_KEYS
    }
    consumed = {k: max(0.0, _safe_float(consumed_src.get(k), 0.0)) for k in _METRIC_KEYS}

    leucine_obj = _obj(signals_src.get("leucine_triggers"))
    leucine_target = max(0.0, _safe_float(leucine_obj.get("target"), 0.0))
    leucine_hit = max(0.0, _safe_float(leucine_obj.get("hit"), 0.0))
    leucine_hit = min(leucine_hit, leucine_target) if leucine_target > 0 else leucine_hit

    signals = {
        "leucine_triggers": {"target": leucine_target, "hit": leucine_hit},
        "avg_satiety": clamp(_safe_float(signals_src.get("avg_satiety"), 0.0), 0.0, 100.0),
        "avg_glycemic_load": max(0.0, _safe_float(signals_src.get("avg_glycemic_load"), 0.0)),
        "ultra_processed_avg": clamp(_safe_float(signals_src.get("ultra_processed_avg"), 0.0), 0.0, 10.0),
    }

    meal_timing = {
        "late_calories_pct": clamp(_safe_float(timing_src.get("late_calories_pct"), 0.0), 0.0, 100.0),
        "biggest_meal": str(timing_src.get("biggest_meal") or "").strip().lower(),
    }

    constraints = {
        "diet": str(constraints_src.get("diet") or "non-veg").strip().lower(),
        "allergies": constraints_src.get("allergies") if isinstance(constraints_src.get("allergies"), list) else [],
        "region": str(constraints_src.get("region") or "").strip().upper(),
    }

    profile = {
        "goal_type": str(profile_src.get("goal_type") or "fat_loss").strip().lower(),
        "diet_style": str(profile_src.get("diet_style") or constraints["diet"]).strip().lower(),
        "training_days_per_week": max(0, int(_safe_float(profile_src.get("training_days_per_week"), 0.0))),
        "training_time": str(profile_src.get("training_time") or "").strip().lower(),
    }

    health_context = {
        "source": str(health_src.get("source") or "").strip().lower(),
        "steps_count": max(0.0, _safe_float(health_src.get("steps_count"), 0.0)),
        "sleep_hours": max(0.0, _safe_float(health_src.get("sleep_hours"), 0.0)),
        "hydration_l": max(0.0, _safe_float(health_src.get("hydration_l"), 0.0)),
        "poor_sleep_flag": bool(health_src.get("poor_sleep_flag")),
        "low_hydration_flag": bool(health_src.get("low_hydration_flag")),
        "low_steps_flag": bool(health_src.get("low_steps_flag")),
        "low_hrv_flag": bool(health_src.get("low_hrv_flag")),
        "elevated_resting_hr_flag": bool(health_src.get("elevated_resting_hr_flag")),
        "resting_heart_rate_bpm": max(0.0, _safe_float(health_src.get("resting_heart_rate_bpm"), 0.0)),
        "hrv_rmssd_ms_avg": max(0.0, _safe_float(health_src.get("hrv_rmssd_ms_avg"), 0.0)),
        "heart_rate_avg_bpm": max(0.0, _safe_float(health_src.get("heart_rate_avg_bpm"), 0.0)),
        "active_energy_kcal": max(0.0, _safe_float(health_src.get("active_energy_kcal"), 0.0)),
        "distance_walking_running_km": max(0.0, _safe_float(health_src.get("distance_walking_running_km"), 0.0)),
        "floors_climbed": max(0.0, _safe_float(health_src.get("floors_climbed"), 0.0)),
    }

    date_raw = str(src.get("date") or "").strip()
    date_iso = date_raw[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", date_raw) else ""

    meal_snapshot = str(src.get("meal_snapshot") or "").strip()

    out = {
        "date": date_iso,
        "goals": goals,
        "consumed": consumed,
        "signals": signals,
        "meal_timing": meal_timing,
        "constraints": constraints,
        "profile": profile,
        "health_context": health_context,
    }
    if meal_snapshot:
        out["meal_snapshot"] = meal_snapshot
    return out


def payload_hash(norm_payload: Dict[str, Any]) -> str:
    canonical = json.dumps(norm_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ratio(consumed: float, goal: float) -> float:
    if goal <= 0:
        return 1.0
    return clamp(consumed / goal, 0.0, 2.0)


def compute_fat_loss_score(norm_payload: Dict[str, Any]) -> int:
    goals = _obj(norm_payload.get("goals"))
    consumed = _obj(norm_payload.get("consumed"))
    signals = _obj(norm_payload.get("signals"))
    timing = _obj(norm_payload.get("meal_timing"))
    health = _obj(norm_payload.get("health_context"))

    kcal_goal = _safe_float(goals.get("kcal"), _DEFAULT_GOALS["kcal"])
    kcal_used = _safe_float(consumed.get("kcal"), 0.0)

    protein_ratio = min(1.0, _ratio(_safe_float(consumed.get("protein_g"), 0.0), _safe_float(goals.get("protein_g"), _DEFAULT_GOALS["protein_g"])))
    fiber_ratio = min(1.0, _ratio(_safe_float(consumed.get("fiber_g"), 0.0), _safe_float(goals.get("fiber_g"), _DEFAULT_GOALS["fiber_g"])))

    if kcal_goal <= 0:
        kcal_component = 0.6
    else:
        delta_pct = (kcal_used - kcal_goal) / kcal_goal
        if delta_pct <= 0:
            # Best around 5-15% below goal for fat-loss intent.
            target = 0.10
            kcal_component = clamp(1.0 - abs(delta_pct - target) * 2.2, 0.0, 1.0)
        else:
            kcal_component = clamp(1.0 - (delta_pct * 1.8), 0.0, 1.0)

    leucine_obj = _obj(signals.get("leucine_triggers"))
    l_target = _safe_float(leucine_obj.get("target"), 0.0)
    l_hit = _safe_float(leucine_obj.get("hit"), 0.0)
    leucine_component = 1.0 if l_target <= 0 else clamp(l_hit / l_target, 0.0, 1.0)

    satiety_component = clamp(_safe_float(signals.get("avg_satiety"), 0.0) / 100.0, 0.0, 1.0)
    gl = _safe_float(signals.get("avg_glycemic_load"), 0.0)
    gl_component = clamp(1.0 - ((gl - 12.0) / 28.0), 0.0, 1.0)
    upf = _safe_float(signals.get("ultra_processed_avg"), 0.0)
    upf_component = clamp(1.0 - (upf / 10.0), 0.0, 1.0)
    late_pct = _safe_float(timing.get("late_calories_pct"), 0.0)
    late_component = clamp(1.0 - ((late_pct - 35.0) / 40.0), 0.0, 1.0)

    sleep_hours = _safe_float(health.get("sleep_hours"), 0.0)
    hydration_l = _safe_float(health.get("hydration_l"), 0.0)
    steps_count = _safe_float(health.get("steps_count"), 0.0)
    recovery_component = 1.0 if sleep_hours <= 0 else clamp((sleep_hours - 5.0) / 3.0, 0.0, 1.0)
    hydration_component = 1.0 if hydration_l <= 0 else clamp(hydration_l / 2.2, 0.0, 1.0)
    activity_component = 1.0 if steps_count <= 0 else clamp(steps_count / 8000.0, 0.0, 1.0)

    score = (
        protein_component(protein_ratio) * 0.24
        + kcal_component * 0.20
        + fiber_ratio * 0.14
        + leucine_component * 0.10
        + satiety_component * 0.08
        + gl_component * 0.08
        + upf_component * 0.08
        + late_component * 0.05
        + recovery_component * 0.07
        + hydration_component * 0.05
        + activity_component * 0.04
    ) * 100.0

    return int(round(clamp(score, 0.0, 100.0)))


def protein_component(protein_ratio: float) -> float:
    if protein_ratio >= 1.0:
        return 1.0
    if protein_ratio >= 0.8:
        return clamp(0.85 + (protein_ratio - 0.8) * 0.75, 0.0, 1.0)
    if protein_ratio >= 0.6:
        return clamp(0.55 + (protein_ratio - 0.6) * 1.5, 0.0, 1.0)
    return clamp(protein_ratio * 0.9, 0.0, 1.0)


def build_rule_risk_alerts(norm_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    goals = _obj(norm_payload.get("goals"))
    consumed = _obj(norm_payload.get("consumed"))
    signals = _obj(norm_payload.get("signals"))
    timing = _obj(norm_payload.get("meal_timing"))
    health = _obj(norm_payload.get("health_context"))

    alerts: List[Dict[str, str]] = []
    p_ratio = _ratio(_safe_float(consumed.get("protein_g"), 0.0), _safe_float(goals.get("protein_g"), _DEFAULT_GOALS["protein_g"]))
    f_ratio = _ratio(_safe_float(consumed.get("fiber_g"), 0.0), _safe_float(goals.get("fiber_g"), _DEFAULT_GOALS["fiber_g"]))
    gl = _safe_float(signals.get("avg_glycemic_load"), 0.0)
    upf = _safe_float(signals.get("ultra_processed_avg"), 0.0)
    late_pct = _safe_float(timing.get("late_calories_pct"), 0.0)

    leucine = _obj(signals.get("leucine_triggers"))
    l_target = _safe_float(leucine.get("target"), 0.0)
    l_hit = _safe_float(leucine.get("hit"), 0.0)
    l_ratio = 1.0 if l_target <= 0 else clamp(l_hit / l_target, 0.0, 1.0)

    if p_ratio < 0.8:
        alerts.append({
            "type": "protein_gap_risk",
            "level": "high" if p_ratio < 0.6 else "medium",
            "reason": f"Protein hit is {int(round(p_ratio * 100))}% of target.",
        })
    if f_ratio < 0.65:
        alerts.append({
            "type": "satiety_crash_risk",
            "level": "high" if f_ratio < 0.45 else "medium",
            "reason": f"Fiber hit is {int(round(f_ratio * 100))}% of target.",
        })
    if gl >= 25:
        alerts.append({
            "type": "glycemic_spike_risk",
            "level": "high" if gl >= 35 else "medium",
            "reason": f"Average glycemic load is {round1(gl)}.",
        })
    if upf >= 6.5:
        alerts.append({
            "type": "ultra_processed_risk",
            "level": "high" if upf >= 8 else "medium",
            "reason": f"Ultra-processed score average is {round1(upf)}/10.",
        })
    if late_pct >= 45:
        alerts.append({
            "type": "evening_hunger_risk",
            "level": "high" if late_pct >= 60 else "medium",
            "reason": f"{int(round(late_pct))}% of calories were late in the day.",
        })
    if l_ratio < 0.7 and l_target > 0:
        alerts.append({
            "type": "muscle_signal_gap",
            "level": "high" if l_ratio < 0.35 else "medium",
            "reason": f"Leucine triggers hit {int(round(l_hit))}/{int(round(l_target))}.",
        })

    sleep_hours = _safe_float(health.get("sleep_hours"), 0.0)
    hydration_l = _safe_float(health.get("hydration_l"), 0.0)
    steps_count = _safe_float(health.get("steps_count"), 0.0)
    if bool(health.get("poor_sleep_flag")) or (sleep_hours and sleep_hours < 6.5):
        alerts.append({
            "type": "recovery_risk",
            "level": "high" if sleep_hours and sleep_hours < 5.5 else "medium",
            "reason": f"Sleep looks low at {round1(sleep_hours)}h, which can raise hunger and lower recovery quality.",
        })
    if bool(health.get("low_hydration_flag")) or (hydration_l and hydration_l < 1.8):
        alerts.append({
            "type": "hydration_gap",
            "level": "medium",
            "reason": f"Hydration looks light at {round1(hydration_l)}L so far.",
        })
    if bool(health.get("low_steps_flag")) or (steps_count and steps_count < 4500):
        alerts.append({
            "type": "activity_dip",
            "level": "medium",
            "reason": f"Steps are only around {int(round(steps_count))}, so appetite and energy may feel flatter today.",
        })

    return alerts


def normalize_diet_style(raw: Any) -> str:
    v = str(raw or "non-veg").strip().lower()
    aliases = {
        "nonveg": "non_veg",
        "non-veg": "non_veg",
        "non_veg": "non_veg",
        "omnivore": "non_veg",
        "veg": "veg",
        "vegetarian": "veg",
        "eggetarian": "eggetarian",
        "egg_veg": "eggetarian",
        "vegan": "vegan",
    }
    return aliases.get(v, "non_veg")


def allowed_protein_sources(diet_style: Any) -> List[str]:
    diet = normalize_diet_style(diet_style)
    if diet == "vegan":
        return ["tofu", "tempeh", "soy chunks", "lentils", "chickpeas", "beans", "pea protein"]
    if diet == "veg":
        return ["paneer", "curd/Greek yogurt", "milk", "tofu", "soy chunks", "lentils", "chickpeas", "beans"]
    if diet == "eggetarian":
        return ["eggs", "paneer", "curd/Greek yogurt", "milk", "tofu", "soy chunks", "lentils", "beans"]
    return ["eggs", "chicken", "fish", "paneer", "curd/Greek yogurt", "milk", "tofu", "lentils", "beans"]


def _human_join(items: List[str]) -> str:
    vals = [str(x or "").strip() for x in (items or []) if str(x or "").strip()]
    if not vals:
        return "high-quality protein sources"
    if len(vals) == 1:
        return vals[0]
    if len(vals) == 2:
        return f"{vals[0]} and {vals[1]}"
    return f"{', '.join(vals[:-1])}, and {vals[-1]}"


def allowed_suggestion_palette(norm_payload: Dict[str, Any]) -> List[str]:
    constraints = _obj(norm_payload.get("constraints"))
    diet = normalize_diet_style(constraints.get("diet") or "non-veg")
    protein_text = _human_join(allowed_protein_sources(diet)[:6])

    base = [
        "Swap refined carbs for higher-fiber choices",
        "Front-load protein earlier in the day",
        "Reduce late-night calories by shifting dinner earlier",
        "Choose minimally processed versions of similar foods",
    ]

    if diet == "vegan":
        base.extend([
            f"Use {protein_text} for protein",
            "Pair legumes + grains for better amino acid coverage",
        ])
    elif diet == "veg":
        base.extend([
            f"Use {protein_text} for protein",
            "Add a high-protein breakfast anchor",
        ])
    elif diet == "eggetarian":
        base.extend([
            f"Use {protein_text} for protein",
            "Build each main meal around an egg or dairy + legume protein anchor",
        ])
    else:
        base.extend([
            f"Use {protein_text} for protein",
            "Build each main meal around a lean protein anchor",
        ])

    return base


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    s = (text or "").strip()
    if not s:
        return None

    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s).strip()
        s = re.sub(r"\n?```$", "", s).strip()

    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def contains_forbidden_claims(text: str) -> bool:
    t = f" {str(text or '').lower()} "
    for k in _FORBIDDEN_MEDICAL:
        if k in t:
            return True
    for k in _FORBIDDEN_SUPPLEMENT:
        if k in t:
            return True
    if _FORBIDDEN_WEIGHT_PROMISE_RE.search(str(text or "")):
        return True
    return False


def response_text_blob(resp: Dict[str, Any]) -> str:
    if not isinstance(resp, dict):
        return ""
    parts: List[str] = []
    summary = resp.get("one_sentence_summary")
    if isinstance(summary, str):
        parts.append(summary)
    pattern = resp.get("pattern_detected")
    if isinstance(pattern, str):
        parts.append(pattern)
    projection_explained = resp.get("projection_explained")
    if isinstance(projection_explained, str):
        parts.append(projection_explained)
    biggest = resp.get("biggest_risk_lever")
    if isinstance(biggest, dict):
        parts.extend([str(biggest.get("title") or ""), str(biggest.get("reason") or "")])
    roi = resp.get("highest_roi_change")
    if isinstance(roi, dict):
        parts.extend([str(roi.get("title") or ""), str(roi.get("why") or ""), str(roi.get("how") or "")])
    one_thing = resp.get("if_you_do_one_thing")
    if isinstance(one_thing, str):
        parts.append(one_thing)
    proj = resp.get("projection_7d")
    if isinstance(proj, dict):
        parts.extend([str(proj.get("if_unchanged") or ""), str(proj.get("if_improved") or "")])
    for k in ("diagnosis", "tomorrow_focus"):
        v = resp.get(k)
        if isinstance(v, list):
            parts.extend([str(x) for x in v])
    actions = resp.get("actions")
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict):
                parts.extend([str(a.get("title") or ""), str(a.get("why") or ""), str(a.get("how") or "")])
    risks = resp.get("risk_alerts")
    if isinstance(risks, list):
        for r in risks:
            if isinstance(r, dict):
                parts.extend([str(r.get("type") or ""), str(r.get("reason") or "")])
    return " ".join(parts).strip()


def action_references_metrics(action: Dict[str, Any]) -> bool:
    blob = f"{str(action.get('title') or '')} {str(action.get('why') or '')} {str(action.get('how') or '')}".lower()
    return any(k in blob for k in _METRIC_HINT_WORDS)


def validate_llm_response_shape(obj: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "response is not an object"

    summary = obj.get("one_sentence_summary")
    pattern = obj.get("pattern_detected")
    projection_explained = obj.get("projection_explained")
    risk_lever = obj.get("biggest_risk_lever")
    roi = obj.get("highest_roi_change")
    one_thing = obj.get("if_you_do_one_thing")
    projection = obj.get("projection_7d")
    diagnosis = obj.get("diagnosis")
    focus = obj.get("tomorrow_focus")
    actions = obj.get("actions")
    risks = obj.get("risk_alerts")

    if not isinstance(diagnosis, list) or not diagnosis:
        return False, "diagnosis must be a non-empty array"
    if not isinstance(focus, list) or not focus:
        return False, "tomorrow_focus must be a non-empty array"
    if not isinstance(actions, list) or not actions:
        return False, "actions must be a non-empty array"
    if len(actions) > 3:
        return False, "actions must be <= 3"

    if not isinstance(summary, str) or not summary.strip():
        return False, "one_sentence_summary is required"
    if len([w for w in summary.strip().split() if w]) > 18:
        return False, "one_sentence_summary must be <= 18 words"
    if not isinstance(projection_explained, str) or not projection_explained.strip():
        return False, "projection_explained is required"
    if not any(k in projection_explained.lower() for k in ("low", "medium", "high")):
        return False, "projection_explained must mention confidence band"
    if not isinstance(one_thing, str) or not one_thing.strip():
        return False, "if_you_do_one_thing is required"

    for line in diagnosis[:4]:
        if not isinstance(line, str) or not line.strip():
            return False, "diagnosis lines must be non-empty strings"
    for line in focus[:4]:
        if not isinstance(line, str) or not line.strip():
            return False, "focus lines must be non-empty strings"

    if pattern is not None and (not isinstance(pattern, str) or not pattern.strip()):
        return False, "pattern_detected must be a non-empty string when provided"
    if risk_lever is not None:
        if not isinstance(risk_lever, dict):
            return False, "biggest_risk_lever must be an object"
        if not str(risk_lever.get("title") or "").strip():
            return False, "biggest_risk_lever.title required"
        if not str(risk_lever.get("reason") or "").strip():
            return False, "biggest_risk_lever.reason required"
    if roi is not None:
        if not isinstance(roi, dict):
            return False, "highest_roi_change must be an object"
        if not str(roi.get("title") or "").strip():
            return False, "highest_roi_change.title required"
        if not str(roi.get("why") or "").strip():
            return False, "highest_roi_change.why required"
        if not str(roi.get("how") or "").strip():
            return False, "highest_roi_change.how required"
        if not action_references_metrics(roi):
            return False, "highest_roi_change must reference at least one metric"
    if projection is not None:
        if not isinstance(projection, dict):
            return False, "projection_7d must be an object"
        if not str(projection.get("if_unchanged") or "").strip():
            return False, "projection_7d.if_unchanged required"
        if not str(projection.get("if_improved") or "").strip():
            return False, "projection_7d.if_improved required"

    for a in actions:
        if not isinstance(a, dict):
            return False, "each action must be an object"
        if not str(a.get("title") or "").strip():
            return False, "action.title required"
        if not str(a.get("why") or "").strip():
            return False, "action.why required"
        if not str(a.get("how") or "").strip():
            return False, "action.how required"
        if not action_references_metrics(a):
            return False, "each action must reference at least one metric"

    if risks is not None:
        if not isinstance(risks, list):
            return False, "risk_alerts must be an array"
        for r in risks:
            if not isinstance(r, dict):
                return False, "risk_alert items must be objects"
            if not str(r.get("type") or "").strip():
                return False, "risk_alert.type required"
            lvl = str(r.get("level") or "").strip().lower()
            if lvl not in _ALERT_LEVELS:
                return False, "risk_alert.level must be low/medium/high"
            if not str(r.get("reason") or "").strip():
                return False, "risk_alert.reason required"

    if contains_forbidden_claims(response_text_blob(obj)):
        return False, "forbidden medical/supplement claim detected"

    return True, ""


def merge_risk_alerts(primary: List[Dict[str, str]], secondary: List[Dict[str, str]], limit: int = 4) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for source in (primary or [], secondary or []):
        if not isinstance(source, dict):
            continue
        t = str(source.get("type") or "").strip().lower()
        if not t or t in seen:
            continue
        lvl = str(source.get("level") or "medium").strip().lower()
        if lvl not in _ALERT_LEVELS:
            lvl = "medium"
        out.append({
            "type": t,
            "level": lvl,
            "reason": str(source.get("reason") or "").strip() or "Pattern flagged by coaching rules.",
        })
        seen.add(t)
        if len(out) >= limit:
            break
    return out


def _recent_fiber_emphasis_count(recent_advice_keys: Optional[Sequence[str]]) -> int:
    n = 0
    for k in recent_advice_keys or []:
        s = str(k or "").lower()
        if "fiber" in s or "veg" in s:
            n += 1
    return n


def build_fallback_coach_response(
    norm_payload: Dict[str, Any],
    fat_loss_score: int,
    rule_alerts: List[Dict[str, str]],
    recent_advice_keys: Optional[List[str]] = None,
    client_memory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    goals = _obj(norm_payload.get("goals"))
    consumed = _obj(norm_payload.get("consumed"))
    signals = _obj(norm_payload.get("signals"))
    timing = _obj(norm_payload.get("meal_timing"))
    constraints = _obj(norm_payload.get("constraints"))
    health = _obj(norm_payload.get("health_context"))
    cm = client_memory if isinstance(client_memory, dict) else {}
    food_prefs = [str(x).strip() for x in (cm.get("food_preferences") or []) if str(x).strip()][:6]
    goal_hints = [str(x).strip() for x in (cm.get("goal_reminders") or []) if str(x).strip()][:4]

    p_goal = max(1.0, _safe_float(goals.get("protein_g"), _DEFAULT_GOALS["protein_g"]))
    p_used = _safe_float(consumed.get("protein_g"), 0.0)
    p_left = max(0.0, p_goal - p_used)
    f_goal = max(1.0, _safe_float(goals.get("fiber_g"), _DEFAULT_GOALS["fiber_g"]))
    f_used = _safe_float(consumed.get("fiber_g"), 0.0)
    f_left = max(0.0, f_goal - f_used)

    gl = _safe_float(signals.get("avg_glycemic_load"), 0.0)
    upf = _safe_float(signals.get("ultra_processed_avg"), 0.0)
    late_pct = _safe_float(timing.get("late_calories_pct"), 0.0)
    leucine_obj = _obj(signals.get("leucine_triggers"))
    l_target = int(round(_safe_float(leucine_obj.get("target"), 0.0)))
    l_hit = int(round(_safe_float(leucine_obj.get("hit"), 0.0)))
    p_ratio = _ratio(p_used, p_goal)
    f_ratio = _ratio(f_used, f_goal)

    diagnosis = [
        f"Fat-loss score is {int(fat_loss_score)}/100 based on calories, protein, fiber, glycemic load, UPF, and meal timing.",
        f"Protein is {round1(p_used)}g vs target {round1(p_goal)}g, and fiber is {round1(f_used)}g vs target {round1(f_goal)}g.",
    ]
    sleep_h = _safe_float(health.get("sleep_hours"), 0.0)
    hyd_l = _safe_float(health.get("hydration_l"), 0.0)
    steps_n = _safe_float(health.get("steps_count"), 0.0)
    if bool(health.get("poor_sleep_flag")) or (sleep_h and sleep_h < 6.5):
        diagnosis.append(
            f"Recovery context: sleep near {round1(sleep_h)}h—earlier protein and calmer evenings usually help appetite the next day."
        )
    if bool(health.get("low_hydration_flag")) or (hyd_l and hyd_l < 1.8 and hyd_l > 0):
        diagnosis.append(f"Hydration context: about {round1(hyd_l)}L logged—light fluids can stack with cravings later.")
    if bool(health.get("low_steps_flag")) or (steps_n and steps_n < 4500 and steps_n > 0):
        diagnosis.append(f"Movement context: ~{int(round(steps_n))} steps so far—short walks often blunt mindless snacking.")
    rhr = _safe_float(health.get("resting_heart_rate_bpm"), 0.0)
    hrv_ms = _safe_float(health.get("hrv_rmssd_ms_avg"), 0.0)
    act_kcal = _safe_float(health.get("active_energy_kcal"), 0.0)
    dist_km = _safe_float(health.get("distance_walking_running_km"), 0.0)
    if rhr > 0:
        if bool(health.get("elevated_resting_hr_flag")) or rhr >= 80:
            diagnosis.append(
                f"Cardio context: resting HR around {int(round(rhr))} bpm is elevated—prioritize sleep, hydration, and steady recovery this week."
            )
        else:
            diagnosis.append(f"Cardio context: resting HR near {int(round(rhr))} bpm from your tracker.")
    if hrv_ms > 0:
        if bool(health.get("low_hrv_flag")) or hrv_ms < 30:
            diagnosis.append(
                f"Recovery context: HRV (RMSSD) near {int(round(hrv_ms))} ms looks stressed—lighter training and consistent sleep help."
            )
        else:
            diagnosis.append(f"Recovery context: HRV (RMSSD) near {int(round(hrv_ms))} ms from your tracker.")
    if act_kcal > 0:
        diagnosis.append(f"Activity burn from tracker: about {int(round(act_kcal))} kcal active energy today.")
    if dist_km > 0:
        diagnosis.append(f"Distance from tracker: about {round1(dist_km)} km walked/run today.")
    if gl >= 25:
        diagnosis.append(f"Average glycemic load is elevated at {round1(gl)}, which may increase hunger swings.")
    if upf >= 6.5:
        diagnosis.append(f"Ultra-processed intake is high (score {round1(upf)}/10), which can reduce satiety quality.")
    if food_prefs:
        diagnosis.append(f"You've noted these foods/preferences: {_human_join(food_prefs[:4])}.")
    if goal_hints:
        diagnosis.append(f"Goal reminders saved: {_human_join(goal_hints[:3])}.")

    tomorrow_focus = [
        f"Close the protein gap early: aim to recover {round1(p_left)}g over breakfast and lunch.",
        f"Lift fiber by about {round1(f_left)}g using whole-food sources.",
    ]
    if late_pct >= 45:
        tomorrow_focus.append(f"Shift calories earlier; late calories are currently {int(round(late_pct))}%.")
    if l_target > 0 and l_hit < l_target:
        tomorrow_focus.append(f"Hit at least {l_target} leucine triggers (today {l_hit}).")
    tomorrow_focus = tomorrow_focus[:3]

    diet = normalize_diet_style(constraints.get("diet") or "non-veg")
    protein_sources = allowed_protein_sources(diet)
    protein_example = " + ".join(protein_sources[:3]) if protein_sources else "protein-rich whole foods"

    # Balance levers: do not let glycemic dominate when protein/fiber gaps are significant.
    protein_gap_score = clamp(1.0 - p_ratio, 0.0, 1.0)
    fiber_gap_score = clamp(1.0 - f_ratio, 0.0, 1.0)
    fiber_repeat_fatigue = _recent_fiber_emphasis_count(recent_advice_keys)
    if fiber_repeat_fatigue >= 2:
        fiber_gap_score *= 0.42
    glycemic_score = clamp((gl - 15.0) / 25.0, 0.0, 1.0)  # slightly reduced weight vs protein/fiber
    upf_score = clamp((upf - 4.0) / 4.0, 0.0, 1.0)
    timing_score = clamp((late_pct - 35.0) / 35.0, 0.0, 1.0)
    # When protein or fiber gap is large (e.g. >20g), boost that lever so it competes with glycemic.
    if p_left >= 20:
        protein_gap_score = max(protein_gap_score, 0.75)
    if f_left >= 15:
        fiber_gap_score = max(fiber_gap_score, 0.7)
    bottlenecks: List[Tuple[str, float]] = []
    bottlenecks.append(("protein", protein_gap_score))
    bottlenecks.append(("fiber", fiber_gap_score))
    bottlenecks.append(("glycemic", glycemic_score))
    bottlenecks.append(("upf", upf_score))
    bottlenecks.append(("timing", timing_score))
    bottlenecks.sort(key=lambda x: x[1], reverse=True)
    top_key = bottlenecks[0][0] if bottlenecks else "protein"
    second_key = bottlenecks[1][0] if len(bottlenecks) > 1 else ""

    recovery_tune = bool(health.get("poor_sleep_flag")) or (sleep_h > 0 and sleep_h < 6.5)
    if recovery_tune and top_key == "fiber" and second_key:
        top_key, second_key = second_key, top_key
    if (bool(health.get("low_hydration_flag")) or (hyd_l > 0 and hyd_l < 1.5)) and top_key == "fiber":
        if protein_gap_score >= fiber_gap_score * 0.85:
            top_key = "protein"

    actions = [
        {
            "title": "Anchor first two meals with protein",
            "why": f"Protein gap is {round1(p_left)}g and leucine triggers are {l_hit}/{l_target or 0}.",
            "how": f"Add one palm-size protein source in breakfast and lunch ({protein_example}).",
        },
        {
            "title": "Add one fiber booster to lunch and dinner",
            "why": f"Fiber is {round1(f_used)}g vs target {round1(f_goal)}g, which can hurt satiety.",
            "how": "Include salad/vegetables plus beans or whole grains in both meals.",
        },
        {
            "title": "Flatten glycemic spikes at the evening meal",
            "why": f"GL is {round1(gl)} and late calories are {int(round(late_pct))}%.",
            "how": "Reduce refined carbs at dinner and pair carbs with protein + vegetables.",
        },
    ]
    health_action = None
    if bool(health.get("poor_sleep_flag")) or (sleep_h > 0 and sleep_h < 6.5):
        health_action = {
            "title": "Support recovery with earlier, calmer fuel tonight",
            "why": f"Sleep is around {round1(sleep_h)}h—skimping on rest often raises appetite noise the next day.",
            "how": "Shift dinner slightly earlier, keep protein steady, and dial back late heavy fat kcal when you can.",
        }
    elif bool(health.get("low_hydration_flag")) or (hyd_l > 0 and hyd_l < 1.8):
        health_action = {
            "title": "Catch up on fluids without overthinking it",
            "why": f"You are near {round1(hyd_l)}L—low fluids can stack with fatigue-driven cravings.",
            "how": "Pair one glass of water with each meal until you are in a comfortable range for you.",
        }
    elif bool(health.get("low_steps_flag")) or (steps_n > 0 and steps_n < 4500):
        health_action = {
            "title": "Add two short movement snacks",
            "why": f"Steps are near {int(round(steps_n))}—light kcal movement can settle appetite between meals.",
            "how": "After lunch and dinner, take an 8–12 minute easy walk before reaching for snacks.",
        }
    if health_action and fiber_repeat_fatigue >= 2:
        actions[1] = health_action
    elif health_action and (recovery_tune or top_key in {"protein", "glycemic", "timing"}):
        actions.insert(1, health_action)
    actions = actions[:3]

    if top_key == "protein":
        risk_lever = {
            "title": "Protein distribution is the top bottleneck",
            "reason": f"Only {int(round(p_ratio * 100))}% of protein target is hit, which can raise evening hunger and reduce recovery quality.",
        }
    elif top_key == "fiber":
        risk_lever = {
            "title": "Fiber gap is driving appetite instability",
            "reason": f"Only {int(round(f_ratio * 100))}% of fiber target is hit, making satiety and calorie control harder.",
        }
    elif top_key == "glycemic":
        risk_lever = {
            "title": "Glycemic load pattern is too spiky",
            "reason": f"Average glycemic load is {round1(gl)}, which can increase appetite swings later in the day.",
        }
    elif top_key == "upf":
        risk_lever = {
            "title": "Ultra-processed load is limiting satiety quality",
            "reason": f"Ultra-processed score is {round1(upf)}/10, which can reduce fullness and increase cravings.",
        }
    else:
        risk_lever = {
            "title": "Late calorie distribution is the top risk",
            "reason": f"Late calories are {int(round(late_pct))}%, which can make appetite control less stable the next day.",
        }

    if late_pct >= 55:
        pattern_detected = (
            f"Calories are heavily back-loaded ({int(round(late_pct))}% late), with protein/fiber gaps earlier in the day."
        )
    elif gl >= 25 and upf >= 6.5:
        pattern_detected = (
            f"Food quality pattern is mixed: glycemic load is {round1(gl)} and ultra-processed score is {round1(upf)}/10."
        )
    else:
        pattern_detected = "Intake is progressing, but closing protein and fiber gaps earlier would improve consistency."

    highest_roi_change = {
        "title": "Front-load protein and fiber before dinner",
        "why": f"Protein gap is {round1(p_left)}g and fiber gap is {round1(f_left)}g, which lowers satiety control later.",
        "how": "Add one protein anchor plus one fiber booster at breakfast and lunch before evening meals.",
    }
    projection = {
        "if_unchanged": "If this pattern repeats for 7 days, evening hunger and adherence risk will likely stay high.",
        "if_improved": "If protein/fiber are front-loaded for 7 days, satiety and score stability should improve noticeably.",
    }
    if top_key == "protein" and second_key == "fiber":
        one_sentence_summary = (
            f"Protein gap {round1(p_left)}g and fiber gap {round1(f_left)}g are the biggest levers today."
        )
    elif top_key == "protein":
        one_sentence_summary = f"Protein is short by {round1(p_left)}g today, your main limiter for satiety and recovery."
    elif top_key == "fiber":
        one_sentence_summary = f"Fiber is short by {round1(f_left)}g today, which is hurting appetite stability."
    elif top_key == "glycemic":
        one_sentence_summary = f"Glycemic load is elevated ({round1(gl)}), so carb quality is the key lever today."
    elif top_key == "upf":
        one_sentence_summary = f"Ultra-processed load ({round1(upf)}/10) is the main lever to improve appetite control."
    else:
        one_sentence_summary = f"Late calories are high ({int(round(late_pct))}%), so shifting intake earlier is the key lever."
    projection_explained = "Current 7-day direction has medium confidence based on available weekly data."
    if_you_do_one_thing = highest_roi_change["how"]

    return {
        "one_sentence_summary": one_sentence_summary,
        "pattern_detected": pattern_detected,
        "projection_explained": projection_explained,
        "biggest_risk_lever": risk_lever,
        "highest_roi_change": highest_roi_change,
        "if_you_do_one_thing": if_you_do_one_thing,
        "projection_7d": projection,
        "diagnosis": diagnosis[:6],
        "tomorrow_focus": tomorrow_focus[:3],
        "actions": actions,
        "risk_alerts": merge_risk_alerts(rule_alerts, []),
        "disclaimer": COACH_DISCLAIMER,
    }

