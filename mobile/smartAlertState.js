/**
 * Local Smart Food Alerts state: settings, suppression, dedupe.
 * Uses AsyncStorage for persistence. Lightweight local anti-spam layer.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "kcal_smart_alerts_v1";
const DISMISSED_IDS_MAX = 50;
const OPENED_IDS_MAX = 100;
const VENUE_SUPPRESS_MS = 4 * 60 * 60 * 1000; // 4 hours
const SAME_ALERT_DEDUPE_MS = 60 * 60 * 1000; // 1 hour

const DEFAULT_CATEGORIES = {
  protein_rescue: true,
  post_workout_recovery: true,
  late_night_damage_control: true,
  worked_before_repeat: true,
  habit_rescue: true,
};

const DEFAULT_STATE = {
  enabled: false,
  categories: { ...DEFAULT_CATEGORIES },
  frequency_mode: "smart_only",
  dismissed_alert_ids: [],
  opened_alert_ids: [],
  last_alert_opened_at: null,
  last_alert_dismissed_at: null,
  suppressed_venues_recent: {},
  ignored_streak_local: 0,
};

let inMemoryState = null;

async function load() {
  if (inMemoryState) return inMemoryState;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed && typeof parsed === "object") {
      inMemoryState = {
        ...DEFAULT_STATE,
        ...parsed,
        categories: { ...DEFAULT_CATEGORIES, ...(parsed.categories || {}) },
      };
    } else {
      inMemoryState = { ...DEFAULT_STATE };
    }
    return inMemoryState;
  } catch {
    inMemoryState = { ...DEFAULT_STATE };
    return inMemoryState;
  }
}

async function save(state) {
  try {
    inMemoryState = state;
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {}
}

/**
 * Deterministic alert ID for dedupe. Must match backend format for push/inbox consistency.
 * Backend: alert_type::place_id::best_item_name
 * @param {object} c - Alert candidate
 * @returns {string}
 */
export function getAlertId(c) {
  if (!c || typeof c !== "object") return "";
  const type = String(c.alert_type || "").trim();
  const placeId = String(c.place_id || "").trim();
  const item = String(c.best_item_name || "").trim();
  return [type, placeId || "?", item || "?"].join("::");
}

/**
 * Get full state (async).
 */
export async function getSmartAlertState() {
  return load();
}

/**
 * Update settings.
 */
export async function updateSmartAlertSettings(updates) {
  const state = await load();
  const next = { ...state };
  if (typeof updates.enabled === "boolean") next.enabled = updates.enabled;
  if (updates.categories && typeof updates.categories === "object") {
    next.categories = { ...next.categories, ...updates.categories };
  }
  if (updates.frequency_mode) next.frequency_mode = updates.frequency_mode;
  await save(next);
  return next;
}

/**
 * Record alert opened.
 */
export async function recordAlertOpened(alertId, placeId) {
  const state = await load();
  const opened = [...(state.opened_alert_ids || [])];
  if (alertId && !opened.includes(alertId)) {
    opened.push(alertId);
    if (opened.length > OPENED_IDS_MAX) opened.shift();
  }
  const suppressed = { ...(state.suppressed_venues_recent || {}) };
  if (placeId) {
    suppressed[placeId] = Date.now();
  }
  await save({
    ...state,
    opened_alert_ids: opened,
    last_alert_opened_at: Date.now(),
    suppressed_venues_recent: suppressed,
  });
}

/**
 * Record alert dismissed.
 */
export async function recordAlertDismissed(alertId, placeId) {
  const state = await load();
  const dismissed = [...(state.dismissed_alert_ids || [])];
  if (alertId && !dismissed.includes(alertId)) {
    dismissed.push(alertId);
    if (dismissed.length > DISMISSED_IDS_MAX) dismissed.shift();
  }
  const suppressed = { ...(state.suppressed_venues_recent || {}) };
  if (placeId) {
    suppressed[placeId] = Date.now();
  }
  const streak = (state.ignored_streak_local || 0) + 1;
  await save({
    ...state,
    dismissed_alert_ids: dismissed,
    last_alert_dismissed_at: Date.now(),
    ignored_streak_local: streak,
    suppressed_venues_recent: suppressed,
  });
}

/**
 * Check if alert should be shown (local filtering).
 * @param {object} candidate - Alert candidate
 * @param {object} state - From getSmartAlertState
 * @returns {boolean}
 */
export function shouldShowAlert(candidate, state) {
  if (!candidate || !state) return false;
  if (!state.enabled) return false;

  const cat = String(candidate.alert_type || "").trim();
  if (!state.categories[cat]) return false;

  const alertId = getAlertId(candidate);
  if ((state.dismissed_alert_ids || []).includes(alertId)) return false;
  if ((state.opened_alert_ids || []).includes(alertId)) {
    const openedAt = state.last_alert_opened_at;
    if (openedAt && Date.now() - openedAt < SAME_ALERT_DEDUPE_MS) return false;
  }

  const placeId = String(candidate.place_id || "").trim();
  if (placeId) {
    const supTs = (state.suppressed_venues_recent || {})[placeId];
    if (supTs && Date.now() - supTs < VENUE_SUPPRESS_MS) return false;
  }

  if (state.frequency_mode === "low") {
    const lastDismiss = state.last_alert_dismissed_at;
    if (lastDismiss && Date.now() - lastDismiss < 2 * 60 * 60 * 1000) return false;
  }

  return true;
}

/**
 * Filter candidates by local settings and dedupe.
 */
export function filterCandidatesForDisplay(candidates, state) {
  if (!Array.isArray(candidates)) return [];
  if (!state) return candidates;
  return candidates.filter((c) => shouldShowAlert(c, state));
}

/**
 * Build fatigue params from local state for API.
 */
export function buildFatigueParams(state) {
  if (!state) return {};
  return {
    recentAlerts6h: 0,
    recentAlerts24h: 0,
    weeklyAlertCount: 0,
    ignoredStreak: state.ignored_streak_local || 0,
  };
}

/**
 * Reset in-memory cache (e.g. for tests).
 */
export function _resetCache() {
  inMemoryState = null;
}
