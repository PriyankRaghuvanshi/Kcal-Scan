/**
 * Let's Go Goal Coach – API and helpers.
 * All endpoints are deterministic; no LLM on hot path.
 */

const GOAL_TYPES = ["fat_loss", "muscle_gain", "recomp", "maintain"];
const PACE_MODES = ["easy", "balanced", "serious"];
const KICKOFF_DAYS_TOTAL = 21;

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function safeStr(v) {
  return v != null ? String(v).trim() : "";
}

/**
 * Build query string for tz (optional). Call with same tz/tz_offset_min as rest of app.
 */
function withTzQuery(params = {}, tz, tzOffsetMin) {
  const p = { ...params };
  if (safeStr(tz)) p.tz = tz;
  if (num(tzOffsetMin) != null) p.tz_offset_min = tzOffsetMin;
  return p;
}

/**
 * POST /goal-coach/plan/create
 * @param {string} apiBase
 * @param {string} userId
 * @param {object} body - { goal_type, timeframe_weeks?, target_date?, pace_mode?, training_days_per_week?, diet_preference?, current_weight?, target_weight? }
 * @returns {Promise<{ ok: boolean, plan?: object, kickoff_day?: number, kickoff_days_total?: number, kickoff_active?: boolean, subscription_required?: boolean }>}
 */
export async function createGoalPlan(apiBase, userId, body) {
  const url = `${apiBase}/goal-coach/plan/create`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({ user_id: userId, ...body }),
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * GET /goal-coach/plan
 */
export async function getGoalPlan(apiBase, userId) {
  const url = `${apiBase}/goal-coach/plan?user_id=${encodeURIComponent(userId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", "X-User-Id": userId },
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * GET /goal-coach/daily
 */
export async function getGoalCoachDaily(apiBase, userId, day, tz, tzOffsetMin) {
  const params = new URLSearchParams({ user_id: userId });
  if (safeStr(day)) params.set("day", day);
  if (safeStr(tz)) params.set("tz", tz);
  if (num(tzOffsetMin) != null) params.set("tz_offset_min", String(tzOffsetMin));
  const url = `${apiBase}/goal-coach/daily?${params.toString()}`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", "X-User-Id": userId },
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * GET /goal-coach/weekly
 */
export async function getGoalCoachWeekly(apiBase, userId, weekStart, day, tz, tzOffsetMin) {
  const params = new URLSearchParams({ user_id: userId });
  if (safeStr(weekStart)) params.set("week_start", weekStart);
  if (safeStr(day)) params.set("day", day);
  if (safeStr(tz)) params.set("tz", tz);
  if (num(tzOffsetMin) != null) params.set("tz_offset_min", String(tzOffsetMin));
  const url = `${apiBase}/goal-coach/weekly?${params.toString()}`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", "X-User-Id": userId },
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * POST /goal-coach/check-in
 * @param {string} apiBase
 * @param {string} userId
 * @param {{ day?: string, analysis_id?: string, meal?: string, meal_label?: string }} body
 * @returns {Promise<{ ok: boolean, entry?: object }>} Resolves with response; throws if 402 (upgrade required) with status 402.
 */
export async function submitGoalCoachCheckIn(apiBase, userId, body) {
  const url = `${apiBase}/goal-coach/check-in`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({ user_id: userId, ...body }),
  });
  if (res.status === 402) {
    const e = new Error("Upgrade to Advanced to continue");
    e.status = 402;
    throw e;
  }
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * POST /goal-coach/weight
 * @param {string} apiBase
 * @param {string} userId
 * @param {{ value_kg: number, day?: string }} body
 * @returns {Promise<{ ok: boolean, entry?: object }>} Throws with e.status === 402 if upgrade required.
 */
export async function submitWeightEntry(apiBase, userId, body) {
  const url = `${apiBase}/goal-coach/weight`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({ user_id: userId, ...body }),
  });
  if (res.status === 402) {
    const e = new Error("Upgrade to Advanced to continue");
    e.status = 402;
    throw e;
  }
  if (!res.ok) throw new Error(res.status === 422 ? "Invalid weight or day" : "Failed to log weight");
  return res.json().catch(() => ({}));
}

/**
 * POST /goal-coach/photo
 * @param {string} apiBase
 * @param {string} userId
 * @param {{ week_start: string, uri_or_ref: string, note?: string }} body
 * @returns {Promise<{ ok: boolean, entry?: object }>} Throws with e.status === 402 if upgrade required.
 */
export async function submitPhotoEntry(apiBase, userId, body) {
  const url = `${apiBase}/goal-coach/photo`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({ user_id: userId, ...body }),
  });
  if (res.status === 402) {
    const e = new Error("Upgrade to Advanced to continue");
    e.status = 402;
    throw e;
  }
  if (!res.ok) throw new Error(res.status === 422 ? "week_start and uri required" : "Failed to log photo");
  return res.json().catch(() => ({}));
}

/**
 * GET /goal-coach/journey
 * @param {string} apiBase
 * @param {string} userId
 * @param {{ day?: string }} params
 */
export async function getJourney(apiBase, userId, params = {}) {
  const search = new URLSearchParams({ user_id: userId });
  if (params.day) search.set("day", params.day);
  const url = `${apiBase}/goal-coach/journey?${search.toString()}`;
  const res = await fetch(url, { method: "GET", headers: { Accept: "application/json", "X-User-Id": userId } });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * POST /goal-coach/plan/pause
 */
export async function pauseGoalPlan(apiBase, userId) {
  const url = `${apiBase}/goal-coach/plan/pause`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({}),
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

/**
 * POST /goal-coach/plan/resume
 */
export async function resumeGoalPlan(apiBase, userId) {
  const url = `${apiBase}/goal-coach/plan/resume`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-Id": userId },
    body: JSON.stringify({}),
  });
  const data = res.ok ? await res.json().catch(() => ({})) : {};
  return data;
}

// Action types (must match backend goal_coach.py)
export const ACTION_OPEN_HEALTHY_NEARBY = "open_healthy_nearby";
export const ACTION_OPEN_SCAN_CAMERA = "open_scan_camera";
export const ACTION_OPEN_SUPPLEMENT_SCAN = "open_supplement_scan";
export const ACTION_OPEN_DAILY_SUMMARY = "open_daily_summary";
export const ACTION_OPEN_GOAL_PLAN = "open_goal_plan";

/**
 * Get primary and optional secondary action from daily response.
 * Uses server suggested_actions when present; otherwise derives from state (fallback).
 */
export function getDailyActions(daily) {
  if (!daily || typeof daily !== "object") return { primaryAction: null, secondaryAction: null };
  const suggested = daily.suggested_actions || {};
  const primary = suggested.primary_action || null;
  const secondary = suggested.secondary_action || null;
  if (primary && primary.action_type && primary.label) {
    return { primaryAction: primary, secondaryAction: secondary || null };
  }
  return deriveDailyActions(daily);
}

/**
 * Client-side fallback when server does not return suggested_actions.
 */
function deriveDailyActions(daily) {
  const targets = daily.today_targets || {};
  const consumed = daily.consumed_so_far || {};
  const remainingCal = Math.max(0, (num(targets.calories) || 0) - (num(consumed.calories) || 0));
  const remainingProtein = Math.max(0, (num(targets.protein_g) || 0) - (num(consumed.protein_g) || 0));
  const riskFlags = Array.isArray(daily.risk_flags) ? daily.risk_flags : [];
  const coachFocus = safeStr(daily.coach_focus);
  const context = {
    goal: safeStr(daily.goal_type) || "fat_loss",
    remaining_protein_g: Math.round(remainingProtein),
    remaining_calories: Math.round(remainingCal),
  };

  if (remainingCal <= 350 && remainingProtein >= 25) {
    return {
      primaryAction: { action_type: ACTION_OPEN_DAILY_SUMMARY, label: "Check today's totals", reason: "Calories are tight.", context },
      secondaryAction: { action_type: ACTION_OPEN_HEALTHY_NEARBY, label: "Find a lighter option nearby", reason: "Protein still matters.", context },
    };
  }
  if ((coachFocus === "protein_first" || riskFlags.includes("protein_gap")) && remainingProtein >= 35) {
    return {
      primaryAction: { action_type: ACTION_OPEN_HEALTHY_NEARBY, label: "Find a high-protein meal nearby", reason: "Protein is behind today.", context },
      secondaryAction: remainingProtein >= 40 ? { action_type: ACTION_OPEN_SUPPLEMENT_SCAN, label: "Add protein (e.g. shake)", reason: "Quick way to close the gap.", context } : null,
    };
  }
  if ((num(consumed.calories) || 0) < 400) {
    return {
      primaryAction: { action_type: ACTION_OPEN_SCAN_CAMERA, label: "Log your meal", reason: "Log what you're eating to stay on track.", context },
      secondaryAction: null,
    };
  }
  return {
    primaryAction: { action_type: ACTION_OPEN_SCAN_CAMERA, label: "Log your next meal", reason: "Stay on track by logging.", context },
    secondaryAction: remainingProtein >= 30 ? { action_type: ACTION_OPEN_HEALTHY_NEARBY, label: "Find a better option nearby", reason: safeStr(daily.coach_summary) || "See what fits your plan.", context } : null,
  };
}

/**
 * Get next-step action from weekly response.
 * Uses server next_step_action when present; otherwise derives from review.
 */
export function getWeeklyNextStepAction(weeklyResponse) {
  if (!weeklyResponse || typeof weeklyResponse !== "object") return null;
  const action = weeklyResponse.next_step_action;
  if (action && action.action_type && action.label) return action;
  const review = weeklyResponse.review || {};
  const nextFocus = review.next_week_focus || {};
  return {
    action_type: ACTION_OPEN_SCAN_CAMERA,
    label: safeStr(nextFocus.headline) || "Log meals more consistently this week",
    reason: safeStr(nextFocus.supporting_text) || "Consistency drives results.",
    context: { goal: safeStr(review.goal_type) || "fat_loss" },
  };
}

/** Preferred Healthy Nearby mode for preselection (no new ranking). */
export const PREFERRED_MODES = {
  PROTEIN_RESCUE: "protein_rescue",
  LIGHTER_OPTION: "lighter_option",
  DINNER_RECOVERY: "dinner_recovery",
  LOGGING_SUPPORT: "logging_support",
  BEST_FIT_TODAY: "best_fit_today",
};

/**
 * Derive preferred_mode from action context for Healthy Nearby preselection.
 * Deterministic: high remaining protein + calories → protein_rescue; tight calories + need protein → lighter_option; etc.
 */
export function derivePreferredModeFromContext(context, actionType) {
  if (!context || typeof context !== "object") return PREFERRED_MODES.BEST_FIT_TODAY;
  if (actionType !== ACTION_OPEN_HEALTHY_NEARBY) return PREFERRED_MODES.BEST_FIT_TODAY;

  const remainingProtein = num(context.remaining_protein_g) ?? 0;
  const remainingCal = num(context.remaining_calories) ?? 0;
  const reason = safeStr(context.reason || context.coach_focus).toLowerCase();

  if (remainingCal <= 400 && remainingProtein >= 20) return PREFERRED_MODES.LIGHTER_OPTION;
  if (remainingProtein >= 35 && remainingCal >= 300) return PREFERRED_MODES.PROTEIN_RESCUE;
  if (reason.includes("dinner") || reason.includes("evening")) return PREFERRED_MODES.DINNER_RECOVERY;
  if (reason.includes("log") || reason.includes("track")) return PREFERRED_MODES.LOGGING_SUPPORT;
  return PREFERRED_MODES.BEST_FIT_TODAY;
}

/**
 * Map preferred_mode to Healthy Nearby filter chip key (same source of truth; bias UI only).
 */
export function preferredModeToFilterKey(preferredMode) {
  switch (preferredMode) {
    case PREFERRED_MODES.PROTEIN_RESCUE:
    case PREFERRED_MODES.DINNER_RECOVERY:
      return "high_protein";
    case PREFERRED_MODES.LIGHTER_OPTION:
      return "under_600";
    case PREFERRED_MODES.LOGGING_SUPPORT:
      return "best_right_now";
    case PREFERRED_MODES.BEST_FIT_TODAY:
    default:
      return "fits_today";
  }
}

/** Fire-and-forget log Goal Coach funnel event. */
async function postGoalCoachEvent(apiBase, eventType, payload) {
  const url = `${apiBase}/goal-coach/events`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ event_type: eventType, ...payload }),
    });
  } catch (_) {
    // best-effort; do not block UI
  }
}

/**
 * Track daily/weekly action shown. Call when actions are rendered.
 * @param {string} apiBase
 * @param {string} userId
 * @param {{ source_surface: 'daily_coach'|'weekly_review'|'goal_plan', action_type: string, goal_type?: string, reason?: string, remaining_protein_g?: number, remaining_calories?: number, kickoff_active?: boolean, subscription_required?: boolean }} meta
 */
export function trackGoalCoachActionShown(apiBase, userId, meta) {
  if (!apiBase || !userId) return;
  const eventType = meta.source_surface === "weekly_review" ? "goal_coach_weekly_action_shown" : "goal_coach_daily_action_shown";
  void postGoalCoachEvent(apiBase, eventType, { user_id: userId, ...meta });
}

/**
 * Track CTA clicked. Call before navigating.
 */
export function trackGoalCoachActionClicked(apiBase, userId, meta) {
  if (!apiBase || !userId) return;
  const eventType = meta.source_surface === "weekly_review" ? "goal_coach_weekly_action_clicked" : "goal_coach_daily_action_clicked";
  void postGoalCoachEvent(apiBase, eventType, { user_id: userId, ...meta });
}

/**
 * Track destination screen opened (e.g. Healthy Nearby, camera, daily summary).
 */
export function trackGoalCoachDestinationOpened(apiBase, userId, meta) {
  if (!apiBase || !userId) return;
  void postGoalCoachEvent(apiBase, "goal_coach_destination_opened", { user_id: userId, ...meta });
}

/**
 * Track action completed (scan result returned, place selected, directions opened, feedback, etc.).
 */
export function trackGoalCoachActionCompleted(apiBase, userId, meta) {
  if (!apiBase || !userId) return;
  void postGoalCoachEvent(apiBase, "goal_coach_action_completed", { user_id: userId, ...meta });
}

export { GOAL_TYPES, PACE_MODES, KICKOFF_DAYS_TOTAL, withTzQuery, num, safeStr };
