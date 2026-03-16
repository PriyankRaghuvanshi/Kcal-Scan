/**
 * Smart Food Alerts API helper.
 * Fetches alert candidates from GET /smart-food-alerts/candidates.
 * Safe failure, no blocking UI, normalized response shape.
 */

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

function devLog(...args) {
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    // eslint-disable-next-line no-console
    console.log("[SmartAlertsApi]", ...args);
  }
}

function withLocalHour(url) {
  const hour = new Date().getHours();
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}local_hour=${encodeURIComponent(hour)}`;
}

async function safeFetch(url) {
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { accept: "application/json" },
    });
    if (!res.ok) {
      devLog("non-200", res.status);
      return null;
    }
    return await res.json();
  } catch (e) {
    devLog("network error", String(e?.message || e));
    return null;
  }
}

/**
 * Build params for /smart-food-alerts/candidates from app context.
 * @param {object} context - { userId, lat, lng, remainingCalories, remainingProteinG, goal, cutMode, postWorkout, lateNight, poorSleepFlag, highCravingRiskFlag, recentAlerts6h, recentAlerts24h, weeklyAlertCount, ignoredStreak, recentlyOpenedApp, recentlyViewedNearby }
 * @returns {object} Params for fetchSmartFoodAlertCandidates
 */
export function buildSmartAlertFetchParams(context = {}) {
  const ctx = context && typeof context === "object" ? context : {};
  const hour = new Date().getHours();
  return {
    user_id: ctx.userId || ctx.user_id || "",
    lat: ctx.lat,
    lng: ctx.lng,
    local_hour: ctx.local_hour ?? hour,
    remaining_calories: ctx.remainingCalories ?? ctx.remaining_calories ?? null,
    remaining_protein_g: ctx.remainingProteinG ?? ctx.remaining_protein_g ?? null,
    goal: ctx.goal ?? "",
    context_mode: ctx.contextMode ?? ctx.context_mode ?? "",
    post_workout: Boolean(ctx.postWorkout ?? ctx.post_workout),
    late_night: Boolean(ctx.lateNight ?? ctx.late_night),
    poor_sleep_flag: Boolean(ctx.poorSleepFlag ?? ctx.poor_sleep_flag),
    high_craving_risk_flag: Boolean(ctx.highCravingRiskFlag ?? ctx.high_craving_risk_flag),
    recent_alerts_count_6h: ctx.recentAlerts6h ?? ctx.recent_alerts_count_6h ?? 0,
    recent_alerts_count_24h: ctx.recentAlerts24h ?? ctx.recent_alerts_count_24h ?? 0,
    weekly_alert_count: ctx.weeklyAlertCount ?? ctx.weekly_alert_count ?? 0,
    ignored_streak: ctx.ignoredStreak ?? ctx.ignored_streak ?? 0,
    recently_opened_app: Boolean(ctx.recentlyOpenedApp ?? ctx.recently_opened_app),
    recently_viewed_nearby: Boolean(ctx.recentlyViewedNearby ?? ctx.recently_viewed_nearby),
  };
}

/**
 * Fetch smart food alert candidates.
 * @param {object} params - From buildSmartAlertFetchParams
 * @param {boolean} eligibleOnly - If true, use eligible_only=true (only sendable alerts)
 * @param {function} appendQuery - Optional (url) => url for tz etc. Pass your withTimezoneQuery.
 * @returns {Promise<{ candidates: object[], placesConsidered: number }>} Normalized shape
 */
export async function fetchSmartFoodAlertCandidates(params, eligibleOnly = false, appendQuery = null) {
  if (!params || typeof params !== "object") {
    return { candidates: [], placesConsidered: 0 };
  }
  const lat = params.lat;
  const lng = params.lng;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    devLog("missing lat/lng");
    return { candidates: [], placesConsidered: 0 };
  }

  const parts = [
    `lat=${encodeURIComponent(lat)}`,
    `lng=${encodeURIComponent(lng)}`,
    "radius=3000",
    "sort_mode=flat_score",
  ];
  if (params.user_id) parts.push(`user_id=${encodeURIComponent(params.user_id)}`);
  if (Number.isFinite(params.local_hour)) parts.push(`local_hour=${encodeURIComponent(params.local_hour)}`);
  if (params.remaining_calories != null) parts.push(`remaining_calories=${encodeURIComponent(params.remaining_calories)}`);
  if (params.remaining_protein_g != null) parts.push(`remaining_protein_g=${encodeURIComponent(params.remaining_protein_g)}`);
  if (params.goal) parts.push(`goal=${encodeURIComponent(params.goal)}`);
  if (params.context_mode) parts.push(`context_mode=${encodeURIComponent(params.context_mode)}`);
  if (params.post_workout) parts.push("post_workout=true");
  if (params.late_night) parts.push("late_night=true");
  if (params.poor_sleep_flag) parts.push("poor_sleep_flag=true");
  if (params.high_craving_risk_flag) parts.push("high_craving_risk_flag=true");
  if (params.recent_alerts_count_6h != null) parts.push(`recent_alerts_count_6h=${encodeURIComponent(params.recent_alerts_count_6h)}`);
  if (params.recent_alerts_count_24h != null) parts.push(`recent_alerts_count_24h=${encodeURIComponent(params.recent_alerts_count_24h)}`);
  if (params.weekly_alert_count != null) parts.push(`weekly_alert_count=${encodeURIComponent(params.weekly_alert_count)}`);
  if (params.ignored_streak != null) parts.push(`ignored_streak=${encodeURIComponent(params.ignored_streak)}`);
  if (params.recently_opened_app) parts.push("recently_opened_app=true");
  if (params.recently_viewed_nearby) parts.push("recently_viewed_nearby=true");
  if (eligibleOnly) parts.push("eligible_only=true");

  let url = `${API_BASE}/smart-food-alerts/candidates?${parts.join("&")}`;
  if (typeof appendQuery === "function") url = appendQuery(url);

  const data = await safeFetch(url);
  if (!data || typeof data !== "object") {
    return { candidates: [], placesConsidered: 0 };
  }

  const candidates = Array.isArray(data.candidates)
    ? data.candidates.filter((c) => c && typeof c === "object")
    : [];
  const placesConsidered = Number(data.places_considered) || 0;

  return {
    candidates,
    placesConsidered,
    query: data.query || null,
  };
}

/**
 * Convenience: fetch only eligible (sendable) alerts.
 */
export async function fetchEligibleSmartAlerts(params, appendQuery = null) {
  return fetchSmartFoodAlertCandidates(params, true, appendQuery);
}

/**
 * Request backend to send a Smart Food Alert push (if eligible).
 * Pass tone_preference so notification title/body match the user's coach tone.
 * Non-blocking; safe to call after loading healthy places.
 * @param {object} opts - { userId, lat, lng, tonePreference, goal?, fatigue?, dryRun?, headers? }
 * @returns {Promise<{ ok: boolean, notifications_attempted?: number, ... }>}
 */
export async function requestSmartAlertPush(opts = {}) {
  const {
    userId,
    lat,
    lng,
    tonePreference = "supportive",
    goal = "",
    fatigue = {},
    dryRun = false,
    headers: customHeaders = {},
  } = opts;
  if (!userId || !Number.isFinite(lat) || !Number.isFinite(lng)) {
    devLog("requestSmartAlertPush: missing userId, lat, or lng");
    return { ok: false };
  }
  const tone = ["supportive", "strict", "funny", "indian_coach"].includes(String(tonePreference || "").toLowerCase())
    ? String(tonePreference).toLowerCase()
    : "supportive";
  try {
    const res = await fetch(`${API_BASE}/push/send-smart-alerts`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...customHeaders,
      },
      body: JSON.stringify({
        user_id: userId,
        lat: Number(lat),
        lng: Number(lng),
        context: { tone_preference: tone },
        goal: goal || undefined,
        fatigue: fatigue && typeof fatigue === "object" ? fatigue : undefined,
        dry_run: Boolean(dryRun),
        eligible_only: true,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      devLog("requestSmartAlertPush non-200", res.status, data);
      return { ok: false, ...data };
    }
    return { ok: true, ...data };
  } catch (e) {
    devLog("requestSmartAlertPush error", String(e?.message || e));
    return { ok: false };
  }
}
