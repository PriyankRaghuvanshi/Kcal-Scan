// Personal learning API helpers for CalorieClick mobile.
// Non-blocking, safe on network failure. No ranking changes here.

import { Platform } from "react-native";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

function devLog(...args) {
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    // eslint-disable-next-line no-console
    console.log("[PersonalLearningApi]", ...args);
  }
}

async function safePost(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      devLog("non-200", path, res.status);
      return null;
    }
    const data = await res.json().catch(() => null);
    return data;
  } catch (e) {
    devLog("network error", path, String(e && e.message ? e.message : e || ""));
    return null;
  }
}

export function postMealDecisionEvent(payload) {
  if (!payload || !payload.user_id) return;
  // Fire and forget; do not block UI.
  safePost("/meal-decision-event", payload);
}

export function postMealFeedback(payload) {
  if (!payload || !payload.user_id) return;
  safePost("/meal-feedback", payload);
}

export function buildDecisionEventPayload(place, eventType, ctx) {
  const p = place || {};
  const c = ctx || {};
  return {
    user_id: c.userId || "",
    event_type: eventType,
    place_id: String(p.place_id || p.id || "").trim(),
    place_name: String(p.name || "").trim(),
    best_item_name: String(p.best_item_name || p.best_order || "").trim(),
    selected_candidate_source: String(
      p.selected_candidate_source || p.menu_item_source || ""
    ).trim(),
    recommendation_label: String(p.recommendation_label || "").trim(),
    confidence_label: String(p.confidence_label || "").trim(),
    display_rank_score_100:
      typeof p.display_rank_score_100 === "number"
        ? p.display_rank_score_100
        : null,
    goal: String(c.goal || "").trim(),
    time_of_day: String(c.timeOfDay || "").trim(),
    metadata: {
      platform: Platform.OS,
      tab: c.tab || "healthy_nearby",
    },
  };
}

export function buildMealFeedbackPayload(pending, answers, ctx) {
  const base = pending || {};
  const a = answers || {};
  const c = ctx || {};
  return {
    user_id: c.userId || "",
    place_id: String(base.place_id || "").trim(),
    place_name: String(base.place_name || "").trim(),
    best_item_name: String(base.best_item_name || "").trim(),
    selected_item_name: String(base.selected_item_name || base.best_item_name || "").trim(),
    selected_candidate_source: String(
      base.selected_candidate_source || ""
    ).trim(),
    swap_accepted: !!base.swap_accepted,
    accepted_swap_label: String(base.accepted_swap_label || "").trim(),
    estimated_calories: base.estimated_calories ?? null,
    estimated_protein_g: base.estimated_protein_g ?? null,
    goal: String(base.goal || c.goal || "").trim(),
    time_of_day: String(base.time_of_day || c.timeOfDay || "").trim(),
    fullness_score: a.fullnessScore ?? null,
    craving_score: a.cravingScore ?? null,
    energy_score: a.energyScore ?? null,
    repeat_intent: a.repeatIntent ?? null,
    helped_on_target: a.helpedOnTarget ?? null,
    notes: String(a.notes || "").trim(),
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    postMealDecisionEvent,
    postMealFeedback,
    buildDecisionEventPayload,
    buildMealFeedbackPayload,
  };
}

