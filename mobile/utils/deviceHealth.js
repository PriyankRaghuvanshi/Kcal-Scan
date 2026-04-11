/**
 * Unified health sync — runs only on the relevant platform:
 * - iPhone: Apple Health (HealthKit) via appleHealth.js
 * - Android: Health Connect (Google Fit and other apps read/write here) via androidHealthConnect.js
 *
 * Each platform is independent; the same App.js hooks call into the correct stack per OS.
 */

import { Platform } from "react-native";
import {
  initAppleHealth,
  getDailyHealthContext as getAppleDailyHealthContext,
  writeNutritionToHealth as writeAppleNutrition,
  writeWeightToHealth as writeAppleWeight,
  isAppleHealthAvailable,
} from "./appleHealth";
import {
  initAndroidHealthConnect,
  getDailyHealthConnectContext,
  writeNutritionToHealthConnect,
  writeWeightToHealthConnect,
  isAndroidHealthConnectAvailable,
} from "./androidHealthConnect";

export function isDeviceHealthAvailable() {
  if (Platform.OS === "ios") return isAppleHealthAvailable();
  if (Platform.OS === "android") return isAndroidHealthConnectAvailable();
  return false;
}

export function initDeviceHealth(callback) {
  if (Platform.OS === "ios") {
    initAppleHealth(callback);
    return;
  }
  if (Platform.OS === "android") {
    initAndroidHealthConnect(callback);
    return;
  }
  if (callback) callback(null);
}

export async function getDailyHealthContext(dateIso) {
  if (Platform.OS === "ios" && isAppleHealthAvailable()) {
    return getAppleDailyHealthContext(dateIso);
  }
  if (Platform.OS === "android" && isAndroidHealthConnectAvailable()) {
    return getDailyHealthConnectContext(dateIso);
  }
  return null;
}

export function writeNutritionToDeviceHealth(opts, callback) {
  if (Platform.OS === "ios" && isAppleHealthAvailable()) {
    writeAppleNutrition(opts, callback);
    return;
  }
  if (Platform.OS === "android" && isAndroidHealthConnectAvailable()) {
    writeNutritionToHealthConnect(opts, callback);
    return;
  }
  if (callback) callback(null);
}

export function writeWeightToDeviceHealth(opts, callback) {
  if (Platform.OS === "ios" && isAppleHealthAvailable()) {
    writeAppleWeight(opts, callback);
    return;
  }
  if (Platform.OS === "android" && isAndroidHealthConnectAvailable()) {
    writeWeightToHealthConnect(opts, callback);
    return;
  }
  if (callback) callback(null);
}
