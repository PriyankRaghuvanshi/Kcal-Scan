/**
 * Push notification helpers: permission, Expo token, backend registration, listeners.
 * Uses expo-notifications. Safe failure, no blocking UI.
 */

import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import * as Device from "expo-device";
import { postMealDecisionEvent, buildDecisionEventPayload } from "./personalLearningApi";
import { safeGetSmartAlertPayload, safeObject, safeParseJson } from "./startupSafety";

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
    const tzOffsetMin = -new Date().getTimezoneOffset();
    const tz =
      (typeof Intl !== "undefined" &&
        Intl?.DateTimeFormat &&
        Intl.DateTimeFormat().resolvedOptions &&
        Intl.DateTimeFormat().resolvedOptions().timeZone) ||
      undefined;
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
        tz: tz || undefined,
        tz_offset_min: Number.isFinite(tzOffsetMin) ? tzOffsetMin : undefined,
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
  const src = safeGetSmartAlertPayload(data);
  if (!src.alert_id && !src.place_id && !src.alert_type && !src.place_name && !src.best_item_name) return {};
  const out = {
    alert_type: src.alert_type,
    place_id: src.place_id,
    place_name: src.place_name,
    best_item_name: src.best_item_name,
    deep_link: src.deep_link,
    alert_id: src.alert_id,
    display_rank_score_100: src.display_rank_score_100,
    context_mode: src.context_mode,
    route_target: src.route_target || "smart_alert_inbox",
    place_lat: src.place_lat,
    place_lng: src.place_lng,
  };
  if (src.confidence_label) out.confidence_label = src.confidence_label;
  if (src.recommendation_label) out.recommendation_label = src.recommendation_label;
  if (src.chosen_candidate_specificity_tier) out.chosen_candidate_specificity_tier = src.chosen_candidate_specificity_tier;
  if (src.menu_item_source) out.menu_item_source = src.menu_item_source;
  if (src.matched_local_profile === true) out.matched_local_profile = true;
  if (src.local_profile_source) out.local_profile_source = src.local_profile_source;
  if (src.used_venue_intelligence_cache === true) out.used_venue_intelligence_cache = true;
  if (src.best_item_is_generic_fallback === true) out.best_item_is_generic_fallback = true;
  return out;
}

/**
 * Handle notification tap/open. Updates local state and optionally posts backend event.
 * @param {object} response - Expo notification response
 * @param {{ userId?: string, recordAlertOpened?: (alertId, placeId) => Promise<void> }} opts
 */
export async function handleNotificationOpen(response, opts = {}) {
  if (!response?.notification?.request?.content) return;

  const content = safeObject(response.notification.request.content, {});
  const data = safeObject(content.data, {});
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
    try {
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
    } catch (e) {
      devLog("handleNotificationOpen postMealDecisionEvent error", String(e?.message || e));
    }
  }

  return { parsed, alertId, placeId };
}

/**
 * Load local registration state from AsyncStorage.
 */
export async function loadPushRegistrationState() {
  try {
    const raw = await AsyncStorage.getItem(PUSH_STORAGE_KEY);
    const parsed = safeParseJson(raw, {}, "push_registration_state");
    return safeObject(parsed, {});
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
