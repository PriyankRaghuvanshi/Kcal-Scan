/**
 * Push notification helpers: permission, Expo token, backend registration, listeners.
 * Uses expo-notifications. Safe failure, no blocking UI.
 */

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import * as Device from "expo-device";
import { postMealDecisionEvent, buildDecisionEventPayload } from "./personalLearningApi";

const isPhysicalDevice = () => Boolean(Device?.isDevice);
import AsyncStorage from "@react-native-async-storage/async-storage";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

const PUSH_STORAGE_KEY = "kcal_push_registration_v1";

function devLog(...args) {
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    // eslint-disable-next-line no-console
    console.log("[PushNotifications]", ...args);
  }
}

/**
 * Normalized permission result.
 * @returns {Promise<{ granted: boolean, canAskAgain: boolean, status: string }>}
 */
export async function requestPushPermissionsIfNeeded() {
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    const granted = finalStatus === "granted";
    let canAskAgain = true;
    if (Platform.OS === "android") {
      canAskAgain = finalStatus !== "denied";
    } else {
      canAskAgain = finalStatus !== "denied" && finalStatus !== "permanentlyDenied";
    }

    return {
      granted,
      canAskAgain: Boolean(canAskAgain),
      status: String(finalStatus || "undetermined"),
    };
  } catch (e) {
    devLog("requestPushPermissionsIfNeeded error", String(e?.message || e));
    return { granted: false, canAskAgain: false, status: "error" };
  }
}

/**
 * Get current permission status without prompting.
 */
export async function getPushPermissionStatus() {
  try {
    const { status } = await Notifications.getPermissionsAsync();
    return { granted: status === "granted", status: String(status || "undetermined") };
  } catch {
    return { granted: false, status: "error" };
  }
}

/**
 * Fetch Expo push token. Only call when permission is granted.
 * Returns null on simulator/emulator or error.
 * @returns {Promise<string|null>}
 */
export async function getExpoPushTokenSafe() {
  if (!isPhysicalDevice()) {
    devLog("push requires physical device");
    return null;
  }

  try {
    const projectId =
      Constants?.expoConfig?.extra?.eas?.projectId ??
      Constants?.easConfig?.projectId ??
      Constants?.manifest2?.extra?.eas?.projectId;
    if (!projectId) {
      devLog("projectId not found in app config");
      return null;
    }

    const pushTokenResult = await Notifications.getExpoPushTokenAsync({
      projectId: String(projectId),
    });
    const token = pushTokenResult?.data?.trim();
    return token || null;
  } catch (e) {
    devLog("getExpoPushTokenSafe error", String(e?.message || e));
    return null;
  }
}

/**
 * Register push token with backend. Non-blocking.
 * @param {{ userId: string, expoPushToken: string, platform?: string, deviceName?: string, appVersion?: string }} opts
 */
export async function registerPushTokenWithBackend(opts = {}) {
  const { userId, expoPushToken, platform, deviceName, appVersion } = opts;
  if (!userId || !expoPushToken) {
    devLog("registerPushTokenWithBackend: missing userId or token");
    return { ok: false };
  }

  try {
    const res = await fetch(`${API_BASE}/push/register`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        expo_push_token: expoPushToken,
        platform: platform || Platform.OS || "unknown",
        device_name: deviceName || undefined,
        app_version: appVersion || undefined,
      }),
    });
    if (!res.ok) {
      devLog("registerPushTokenWithBackend non-200", res.status);
      return { ok: false };
    }
    const data = await res.json().catch(() => null);
    return { ok: true, ...data };
  } catch (e) {
    devLog("registerPushTokenWithBackend error", String(e?.message || e));
    return { ok: false };
  }
}

/**
 * Unregister push token from backend. Non-blocking.
 * @param {{ userId: string, expoPushToken: string }} opts
 */
export async function unregisterPushTokenWithBackend(opts = {}) {
  const { userId, expoPushToken } = opts;
  if (!userId || !expoPushToken) {
    devLog("unregisterPushTokenWithBackend: missing userId or token");
    return { ok: false };
  }

  try {
    const res = await fetch(`${API_BASE}/push/unregister`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        expo_push_token: expoPushToken,
      }),
    });
    if (!res.ok) {
      devLog("unregisterPushTokenWithBackend non-200", res.status);
      return { ok: false };
    }
    return { ok: true };
  } catch (e) {
    devLog("unregisterPushTokenWithBackend error", String(e?.message || e));
    return { ok: false };
  }
}

/**
 * Setup notification listeners. Call cleanup on unmount.
 * @param {{ onNotificationReceived?: (notification) => void, onNotificationResponse?: (response) => void }} opts
 * @returns {{ received: Subscription, response: Subscription } | null}
 */
export function setupNotificationListeners(opts = {}) {
  const { onNotificationReceived, onNotificationResponse } = opts;
  const subs = { received: null, response: null };

  try {
    if (typeof onNotificationReceived === "function") {
      subs.received = Notifications.addNotificationReceivedListener(onNotificationReceived);
    }
    if (typeof onNotificationResponse === "function") {
      subs.response = Notifications.addNotificationResponseReceivedListener(onNotificationResponse);
    }
    return subs;
  } catch (e) {
    devLog("setupNotificationListeners error", String(e?.message || e));
    return null;
  }
}

/**
 * Cleanup notification listeners.
 * @param {{ received?: { remove: () => void }, response?: { remove: () => void } } | null} subs
 */
export function cleanupNotificationListeners(subs) {
  if (!subs) return;
  try {
    if (subs.received?.remove) subs.received.remove();
    if (subs.response?.remove) subs.response.remove();
  } catch {}
}

/**
 * Parse notification data payload. Expected shape for Smart Alerts:
 * alert_type, place_id, place_name, best_item_name, deep_link, alert_id, display_rank_score_100,
 * context_mode, route_target, place_lat, place_lng, plus trust metadata for inbox/card consistency.
 * @param {object} data
 * @returns {object}
 */
export function parseSmartAlertNotificationData(data) {
  if (!data || typeof data !== "object") return {};
  const out = {
    alert_type: String(data.alert_type || "").trim(),
    place_id: String(data.place_id || "").trim(),
    place_name: String(data.place_name || "").trim(),
    best_item_name: String(data.best_item_name || "").trim(),
    deep_link: String(data.deep_link || "").trim(),
    alert_id: String(data.alert_id || "").trim(),
    display_rank_score_100: data.display_rank_score_100 ?? null,
    context_mode: String(data.context_mode || "").trim(),
    route_target: String(data.route_target || "smart_alert_inbox").trim(),
    place_lat: typeof data.place_lat === "number" ? data.place_lat : null,
    place_lng: typeof data.place_lng === "number" ? data.place_lng : null,
  };
  if (data.confidence_label) out.confidence_label = String(data.confidence_label).trim();
  if (data.recommendation_label) out.recommendation_label = String(data.recommendation_label).trim();
  if (data.chosen_candidate_specificity_tier) out.chosen_candidate_specificity_tier = String(data.chosen_candidate_specificity_tier).trim();
  if (data.menu_item_source) out.menu_item_source = String(data.menu_item_source).trim();
  if (data.matched_local_profile === true) out.matched_local_profile = true;
  if (data.local_profile_source) out.local_profile_source = String(data.local_profile_source).trim();
  if (data.used_venue_intelligence_cache === true) out.used_venue_intelligence_cache = true;
  if (data.best_item_is_generic_fallback === true) out.best_item_is_generic_fallback = true;
  return out;
}

/**
 * Handle notification tap/open. Updates local state and optionally posts backend event.
 * @param {object} response - Expo notification response
 * @param {{ userId?: string, recordAlertOpened?: (alertId, placeId) => Promise<void> }} opts
 */
export async function handleNotificationOpen(response, opts = {}) {
  if (!response?.notification?.request?.content) return;

  const data = response.notification.request.content.data || {};
  const parsed = parseSmartAlertNotificationData(data);
  const { userId, recordAlertOpened } = opts;

  const alertId = parsed.alert_id || (parsed.place_id && parsed.alert_type
    ? `${parsed.alert_type}::${parsed.place_id}::${parsed.best_item_name || "?"}`
    : null);
  const placeId = parsed.place_id || null;

  if (recordAlertOpened && alertId) {
    try {
      await recordAlertOpened(alertId, placeId);
    } catch {}
  }

  if (userId && (alertId || placeId)) {
    const payload = buildDecisionEventPayload(
      {
        place_id: placeId,
        name: parsed.place_name,
        best_item_name: parsed.best_item_name,
        display_rank_score_100: parsed.display_rank_score_100,
      },
      "recommendation_opened",
      { userId }
    );
    postMealDecisionEvent(payload);
  }

  return { parsed, alertId, placeId };
}

/**
 * Load local registration state from AsyncStorage.
 */
export async function loadPushRegistrationState() {
  try {
    const raw = await AsyncStorage.getItem(PUSH_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * Save local registration state.
 */
export async function savePushRegistrationState(state) {
  try {
    await AsyncStorage.setItem(PUSH_STORAGE_KEY, JSON.stringify(state));
  } catch {}
}
