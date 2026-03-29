import { LayoutAnimation, Platform, UIManager } from "react-native";

// Enable LayoutAnimation on Android (no-op on iOS).
try {
  if (Platform.OS === "android" && UIManager?.setLayoutAnimationEnabledExperimental) {
    UIManager.setLayoutAnimationEnabledExperimental(true);
  }
} catch (_) {}

// Optional Expo haptics (safe no-op when not installed).
let _Haptics = null;
try {
  // eslint-disable-next-line global-require
  _Haptics = require("expo-haptics");
} catch (_) {
  _Haptics = null;
}

const _lastFireByKey = new Map();

function _shouldFire(key, cooldownMs) {
  if (!key) return true;
  const now = Date.now();
  const last = _lastFireByKey.get(key) || 0;
  if (now - last < cooldownMs) return false;
  _lastFireByKey.set(key, now);
  return true;
}

export function layoutEaseInOut() {
  try {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
  } catch (_) {}
}

export async function hapticSuccess({ key = "", cooldownMs = 2500 } = {}) {
  try {
    if (!_Haptics?.notificationAsync) return;
    if (!_shouldFire(key, cooldownMs)) return;
    await _Haptics.notificationAsync(_Haptics.NotificationFeedbackType.Success);
  } catch (_) {}
}

export async function hapticLight({ key = "", cooldownMs = 800 } = {}) {
  try {
    if (!_Haptics?.impactAsync) return;
    if (!_shouldFire(key, cooldownMs)) return;
    await _Haptics.impactAsync(_Haptics.ImpactFeedbackStyle.Light);
  } catch (_) {}
}

/** Short “tick” — good as a listen start/stop cue when a tone asset isn’t bundled. */
export async function hapticSelection({ key = "", cooldownMs = 400 } = {}) {
  try {
    if (!_Haptics?.selectionAsync) return;
    if (!_shouldFire(key, cooldownMs)) return;
    await _Haptics.selectionAsync();
  } catch (_) {}
}

