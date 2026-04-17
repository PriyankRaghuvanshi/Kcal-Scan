from __future__ import annotations

from typing import Any, Dict, List


GUARDRAIL_BLOCK = (
    "Guardrails: keep the tone calm, practical, and parent-first. "
    "Do not mention calories, weight loss, body size, dieting, or finishing the plate. "
    "Do not make medical, feeding disorder, or diagnostic claims. "
    "Keep the scope on food routines only, not broader family health, prevention, monitoring, or wellbeing. "
    "Prefer low-pressure language, routines, and repeatable next steps."
)


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def build_one_meal_tonight_prompt(payload: Dict[str, Any]) -> str:
    return (
        f"Write calm parent-friendly copy for CalorieClick Family Habits: One Meal Tonight. {GUARDRAIL_BLOCK}\n"
        f"Meal: {_safe_str(payload.get('meal_name'))}\n"
        f"Safe component: {_safe_str(payload.get('safe_component'))}\n"
        f"Exposure component: {_safe_str(payload.get('exposure_component'))}\n"
        f"Child tweak: {_safe_str(payload.get('child_tweak'))}\n"
        f"Adult upgrade: {_safe_str(payload.get('adult_upgrade'))}\n"
        "Keep it to 3 short paragraphs or bullets."
    )



def build_rescue_mode_prompt(payload: Dict[str, Any]) -> str:
    return (
        f"Turn this deterministic Parent Rescue Mode plan into calm, low-pressure wording for a parent. {GUARDRAIL_BLOCK}\n"
        f"Issue type: {_safe_str(payload.get('issue_type'))}\n"
        f"What to say: {_safe_str(payload.get('what_to_say'))}\n"
        f"What to do tonight: {_safe_str(payload.get('what_to_do_tonight'))}\n"
        f"What to avoid: {_safe_str(payload.get('what_to_avoid'))}\n"
        f"Tomorrow reset: {_safe_str(payload.get('tomorrow_reset'))}\n"
        "Avoid sounding robotic or judgmental."
    )



def build_weekly_reset_prompt(payload: Dict[str, Any]) -> str:
    return (
        f"Write a short Weekly Family Reset summary for parents inside CalorieClick Family Habits. {GUARDRAIL_BLOCK}\n"
        f"Strongest win: {_safe_str(payload.get('strongest_win'))}\n"
        f"Strongest drift: {_safe_str(payload.get('strongest_drift'))}\n"
        f"Meal to repeat: {_safe_str(payload.get('meal_to_repeat'))}\n"
        f"Exposure to retry: {_safe_str(payload.get('exposure_to_retry'))}\n"
        f"Habit to restore: {_safe_str(payload.get('habit_to_restore'))}\n"
        "Keep it brief, encouraging, and specific."
    )



def build_exposure_next_step_prompt(summary: Dict[str, Any]) -> str:
    return (
        f"Write one calm next-step suggestion for Exposure Tracker in CalorieClick Family Habits. {GUARDRAIL_BLOCK}\n"
        f"Food: {_safe_str(summary.get('food_name'))}\n"
        f"Progress state: {_safe_str(summary.get('progress_state'))}\n"
        f"Best format: {_safe_str(summary.get('best_format'))}\n"
        f"Best pairing: {_safe_str(summary.get('best_pairing'))}\n"
        f"Base recommendation: {_safe_str(summary.get('next_recommendation'))}\n"
        "Keep it to one or two sentences."
    )
