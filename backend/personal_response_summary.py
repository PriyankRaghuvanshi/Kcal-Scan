from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from meal_feedback_store import list_meal_feedback_events
from meal_decision_event_store import list_meal_decision_events


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _norm_lower(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        try:
            return int(round(float(v)))
        except Exception:
            return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _item_key(item_name: Any) -> str:
    token = _norm_lower(item_name)
    return token if token else "__unknown_item__"


def _infer_cuisine_group(place_name: Any) -> str:
    text = _norm_lower(place_name)
    if any(t in text for t in ("subway", "sub ", "sandwich", "deli")):
        return "sandwich_sub"
    if "pizza" in text or "pizzeria" in text or "domino" in text:
        return "pizza"
    if any(t in text for t in ("filter coffee", "udupi", "idli", "dosa", "south indian", "chennai")):
        return "south_indian"
    if "indian" in text or "tandoori" in text or "biryani" in text or "dal" in text:
        return "north_indian"
    if any(t in text for t in ("juice", "smoothie", "acai")):
        return "juice_smoothie"
    if any(t in text for t in ("cafe", "coffee", "bakery", "brunch")):
        return "cafe"
    return "unknown"


@dataclass
class PersonalMemory:
    worked_before: bool
    personal_memory_label: str
    times_chosen: int
    repeat_success_rate: float
    swap_accept_rate: float
    avg_fullness: Optional[float]
    avg_craving_score: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worked_before": bool(self.worked_before),
            "personal_memory_label": str(self.personal_memory_label or ""),
            "times_chosen": int(self.times_chosen),
            "repeat_success_rate": round(float(self.repeat_success_rate), 3),
            "swap_accept_rate": round(float(self.swap_accept_rate), 3),
            "avg_fullness": None if self.avg_fullness is None else round(float(self.avg_fullness), 2),
            "avg_craving_score": None if self.avg_craving_score is None else round(float(self.avg_craving_score), 2),
        }


def compute_personal_memory_modifier(
    memory: PersonalMemory | Dict[str, Any] | None,
    *,
    base_score_100: float,
    food_quality_score_100: float,
    protein_density_score_100: float,
) -> Dict[str, Any]:
    """
    Deterministic bounded modifier for ranking.

    Returns dict with:
      - personal_history_bonus_100
      - personal_history_penalty_100
      - personal_history_net_100
      - personal_memory_reason
      - memory_sample_count
      - memory_applied
    """
    if memory is None:
        return {
            "personal_history_bonus_100": 0,
            "personal_history_penalty_100": 0,
            "personal_history_net_100": 0,
            "personal_memory_reason": "no_memory",
            "memory_sample_count": 0,
            "memory_applied": False,
        }

    if isinstance(memory, PersonalMemory):
        worked_before = memory.worked_before
        label = memory.personal_memory_label or ""
        times = int(memory.times_chosen or 0)
        avg_fullness = memory.avg_fullness
        avg_craving = memory.avg_craving_score
        repeat_rate = float(memory.repeat_success_rate or 0.0)
        swap_rate = float(memory.swap_accept_rate or 0.0)
    else:
        worked_before = bool(memory.get("worked_before"))
        label = str(memory.get("personal_memory_label") or "")
        times = int(memory.get("times_chosen") or 0)
        avg_fullness = _safe_int(memory.get("avg_fullness"))
        avg_craving = _safe_int(memory.get("avg_craving_score"))
        repeat_rate = float(memory.get("repeat_success_rate") or 0.0)
        swap_rate = float(memory.get("swap_accept_rate") or 0.0)

    # Strict evidence gate
    if times < 3:
        return {
            "personal_history_bonus_100": 0,
            "personal_history_penalty_100": 0,
            "personal_history_net_100": 0,
            "personal_memory_reason": "not_enough_data",
            "memory_sample_count": times,
            "memory_applied": False,
        }

    # Safeguard: only apply when core meal quality is reasonable.
    if base_score_100 < 55 or food_quality_score_100 < 50 or protein_density_score_100 < 45:
        return {
            "personal_history_bonus_100": 0,
            "personal_history_penalty_100": 0,
            "personal_history_net_100": 0,
            "personal_memory_reason": "weak_core_score",
            "memory_sample_count": times,
            "memory_applied": False,
        }

    label_norm = label.strip()
    reasons: List[str] = []
    pos = 0
    neg = 0

    # Positive signals
    if worked_before:
        pos += 2
        reasons.append("worked_before")
    if label_norm in {"Worked well before", "Usually keeps you fuller", "You often repeat this"}:
        pos += 2
        reasons.append("strong_label")
    if avg_fullness is not None and avg_fullness >= 4.0:
        pos += 1
        reasons.append("fullness_high")
    if avg_craving is not None and avg_craving <= 2.0:
        pos += 1
        reasons.append("craving_low")
    if repeat_rate >= 0.7:
        pos += 1
        reasons.append("repeat_high")
    if swap_rate >= 0.6:
        pos += 1
        reasons.append("swap_accept_high")

    if pos > 6:
        pos = 6

    # Negative signals
    if label_norm == "Often followed by cravings":
        neg += 3
        reasons.append("label_cravings")
    if avg_craving is not None and avg_craving >= 4.0:
        neg += 2
        reasons.append("craving_high")
    if avg_fullness is not None and avg_fullness <= 2.5:
        neg += 2
        reasons.append("fullness_low")
    if times >= 5 and repeat_rate <= 0.3:
        neg += 1
        reasons.append("repeat_low")

    if neg > 6:
        neg = 6

    net = pos - neg
    if net > 6:
        net = 6
    if net < -6:
        net = -6

    applied = net != 0
    reason = "neutral"
    if not applied:
        reason = "neutral_memory"
    elif net > 0:
        reason = "positive:" + ",".join(sorted(set(reasons))) if reasons else "positive"
    else:
        reason = "negative:" + ",".join(sorted(set(reasons))) if reasons else "negative"

    return {
        "personal_history_bonus_100": int(max(0, pos)),
        "personal_history_penalty_100": int(max(0, neg)),
        "personal_history_net_100": int(net),
        "personal_memory_reason": reason,
        "memory_sample_count": times,
        "memory_applied": bool(applied),
    }


def _memory_label(
    *,
    n: int,
    avg_fullness: Optional[float],
    avg_craving: Optional[float],
    repeat_rate: float,
    swap_accept_rate: float,
) -> Tuple[bool, str]:
    if n < 3:
        return False, "Not enough data yet"

    fullness = avg_fullness if avg_fullness is not None else 0.0
    craving = avg_craving if avg_craving is not None else 0.0

    # Strong signals
    if fullness >= 4.0 and craving <= 2.0 and repeat_rate >= 0.5:
        return True, "Worked well before"
    if fullness >= 4.2 and craving <= 2.5:
        return True, "Usually keeps you fuller"
    if craving >= 4.0:
        return False, "Often followed by cravings"
    if repeat_rate >= 0.65:
        return True, "You often repeat this"
    if swap_accept_rate >= 0.55:
        return True, "You prefer lighter versions here"
    return False, "Mixed results so far"


def _aggregate_from_feedback(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = 0
    fullness_sum = 0
    fullness_n = 0
    craving_sum = 0
    craving_n = 0
    repeat_yes = 0
    repeat_n = 0
    swap_yes = 0
    swap_n = 0

    for e in events:
        if not isinstance(e, dict):
            continue
        n += 1
        fs = _safe_int(e.get("fullness_score"))
        if fs is not None:
            fullness_sum += fs
            fullness_n += 1
        cs = _safe_int(e.get("craving_score"))
        if cs is not None:
            craving_sum += cs
            craving_n += 1
        if e.get("repeat_intent") is not None:
            repeat_n += 1
            if bool(e.get("repeat_intent")):
                repeat_yes += 1
        if e.get("swap_accepted") is not None:
            swap_n += 1
            if bool(e.get("swap_accepted")):
                swap_yes += 1

    avg_fullness = (fullness_sum / fullness_n) if fullness_n > 0 else None
    avg_craving = (craving_sum / craving_n) if craving_n > 0 else None
    repeat_rate = (repeat_yes / repeat_n) if repeat_n > 0 else 0.0
    swap_rate = (swap_yes / swap_n) if swap_n > 0 else 0.0

    worked, label = _memory_label(
        n=n,
        avg_fullness=avg_fullness,
        avg_craving=avg_craving,
        repeat_rate=repeat_rate,
        swap_accept_rate=swap_rate,
    )
    return {
        "n": n,
        "avg_fullness": avg_fullness,
        "avg_craving": avg_craving,
        "repeat_rate": repeat_rate,
        "swap_rate": swap_rate,
        "worked_before": worked,
        "label": label,
    }


def get_personal_meal_memory(
    *,
    user_id: Any,
    place_id: Any = "",
    place_name: Any = "",
    item_name: Any = "",
    goal: Any = "",
    time_of_day: Any = "",
    _feedback_events: Optional[List[Dict[str, Any]]] = None,
    _decision_events: Optional[List[Dict[str, Any]]] = None,
) -> PersonalMemory:
    """
    Deterministic lookup over stored feedback and decision events.
    Uses the most specific match available, then falls back:
      1) user+place+item
      2) user+place
      3) user+cuisine_group
    """
    uid = _normalize_space(user_id)
    if not uid:
        return PersonalMemory(False, "", 0, 0.0, 0.0, None, None)

    pid = _normalize_space(place_id)
    pname = _normalize_space(place_name)
    item_key = _item_key(item_name)
    goal_key = _norm_lower(goal)
    tod = _norm_lower(time_of_day)
    cuisine = _infer_cuisine_group(pname)

    feedback = (
        _feedback_events
        if isinstance(_feedback_events, list)
        else list_meal_feedback_events(user_id=uid, limit=2000)
    )

    def match(e: Dict[str, Any], *, mode: str) -> bool:
        if not isinstance(e, dict):
            return False
        if _normalize_space(e.get("user_id")) != uid:
            return False
        if goal_key and _norm_lower(e.get("goal")) != goal_key:
            return False
        if tod and _norm_lower(e.get("time_of_day")) != tod:
            return False
        if mode == "place_item":
            return _normalize_space(e.get("place_id")) == pid and _item_key(e.get("selected_item_name") or e.get("best_item_name")) == item_key
        if mode == "place":
            return _normalize_space(e.get("place_id")) == pid
        if mode == "cuisine":
            return _infer_cuisine_group(e.get("place_name")) == cuisine
        return False

    specific: List[Dict[str, Any]] = []
    if pid and item_key != "__unknown_item__":
        specific = [e for e in feedback if match(e, mode="place_item")]
    by_place: List[Dict[str, Any]] = [e for e in feedback if pid and match(e, mode="place")] if pid else []
    by_cuisine: List[Dict[str, Any]] = [e for e in feedback if cuisine != "unknown" and match(e, mode="cuisine")]

    chosen = specific or by_place or by_cuisine
    agg = _aggregate_from_feedback(chosen)

    # swap accept rate can be supplemented by decision events (swap_accepted events)
    decision = (
        _decision_events
        if isinstance(_decision_events, list)
        else list_meal_decision_events(user_id=uid, limit=4000)
    )
    relevant_decision = [
        e for e in decision
        if isinstance(e, dict)
        and (not pid or _normalize_space(e.get("place_id")) == pid)
        and (not goal_key or _norm_lower(e.get("goal")) == goal_key)
        and (not tod or _norm_lower(e.get("time_of_day")) == tod)
    ]
    swap_viewed = sum(1 for e in relevant_decision if _norm_lower(e.get("event_type")) == "swap_viewed")
    swap_accepted = sum(1 for e in relevant_decision if _norm_lower(e.get("event_type")) == "swap_accepted")
    if (swap_viewed + swap_accepted) > 0:
        swap_rate = _clamp(float(swap_accepted / float(swap_viewed + swap_accepted)), 0.0, 1.0)
    else:
        swap_rate = float(agg.get("swap_rate") or 0.0)

    return PersonalMemory(
        worked_before=bool(agg.get("worked_before")),
        personal_memory_label=str(agg.get("label") or ""),
        times_chosen=int(agg.get("n") or 0),
        repeat_success_rate=float(agg.get("repeat_rate") or 0.0),
        swap_accept_rate=float(swap_rate),
        avg_fullness=agg.get("avg_fullness"),
        avg_craving_score=agg.get("avg_craving"),
    )
