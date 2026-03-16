/**
 * Apple Health (HealthKit) integration for iOS.
 * Writes food/nutrition from meal scans and weight from Let's Go journey to iPhone Health.
 *
 * Setup (iOS only):
 * 1. npm install react-native-health
 * 2. cd ios && pod install
 * 3. In Xcode: add HealthKit capability; add to Info.plist:
 *    NSHealthShareUsageDescription, NSHealthUpdateUsageDescription
 * 4. Rebuild the app (Expo Go does not support HealthKit; use dev client).
 *
 * If react-native-health is not installed, all functions no-op and the app runs as before.
 */

import { Platform } from "react-native";

const isIOS = Platform.OS === "ios";

let AppleHealthKit = null;
let healthKitReady = false;

try {
  if (isIOS) {
    AppleHealthKit = require("react-native-health").default;
  }
} catch (_) {
  // Module not installed or not linked
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function getWritePermissions() {
  if (!AppleHealthKit) return null;
  return {
    permissions: {
      write: [
        AppleHealthKit.Constants.Permissions.EnergyConsumed,
        AppleHealthKit.Constants.Permissions.Protein,
        AppleHealthKit.Constants.Permissions.Carbohydrates,
        AppleHealthKit.Constants.Permissions.FatTotal,
        AppleHealthKit.Constants.Permissions.Fiber,
        AppleHealthKit.Constants.Permissions.Weight,
      ],
    },
  };
}

/**
 * Initialize HealthKit and request write permissions. Call once (e.g. on app load or before first write).
 * @param {function(err?: string)} callback - Called when init completes; err if user denied or unavailable.
 */
export function initAppleHealth(callback) {
  if (!isIOS || !AppleHealthKit) {
    if (callback) callback(null);
    return;
  }
  if (healthKitReady) {
    if (callback) callback(null);
    return;
  }
  const perms = getWritePermissions();
  if (!perms) {
    if (callback) callback(null);
    return;
  }
  AppleHealthKit.initHealthKit(perms, (err) => {
    if (!err) healthKitReady = true;
    if (callback) callback(err || null);
  });
}

/**
 * Write one meal's nutrition to Apple Health.
 * @param {object} opts - { dateIso, energyKcal, proteinG, carbsG, fatG, fiberG?, foodName? }
 */
export function writeNutritionToHealth(opts, callback) {
  if (!isIOS || !AppleHealthKit) {
    if (callback) callback(null);
    return;
  }
  const date = opts?.dateIso ? new Date(opts.dateIso) : new Date();
  const foodName = opts?.foodName && String(opts.foodName).trim() ? String(opts.foodName).trim() : "Meal";
  const energy = num(opts?.energyKcal);
  const protein = num(opts?.proteinG);
  const carbs = num(opts?.carbsG);
  const fat = num(opts?.fatG);
  const fiber = num(opts?.fiberG);

  const options = {
    foodName: foodName.slice(0, 100),
    mealType: "Lunch",
    date: date.toISOString(),
  };
  if (energy != null && energy >= 0) options.energy = energy;
  if (protein != null && protein >= 0) options.protein = protein;
  if (carbs != null && carbs >= 0) options.carbohydrates = carbs;
  if (fat != null && fat >= 0) options.fatTotal = fat;
  if (fiber != null && fiber >= 0) options.fiber = fiber;

  AppleHealthKit.saveFood(options, (err) => {
    if (callback) callback(err || null);
  });
}

/**
 * Write weight to Apple Health (e.g. from Let's Go journey).
 * @param {object} opts - { dateIso?, valueKg }
 */
export function writeWeightToHealth(opts, callback) {
  if (!isIOS || !AppleHealthKit) {
    if (callback) callback(null);
    return;
  }
  const valueKg = num(opts?.valueKg);
  if (valueKg == null || valueKg <= 0) {
    if (callback) callback(new Error("Invalid weight"));
    return;
  }
  const startDate = opts?.dateIso ? new Date(opts.dateIso) : new Date();
  const options = {
    value: valueKg * 1000,
    unit: AppleHealthKit.Constants.Units.gram,
    startDate: startDate.toISOString(),
  };
  AppleHealthKit.saveWeight(options, (err) => {
    if (callback) callback(err || null);
  });
}

/** True if HealthKit is available (iOS and module loaded). */
export function isAppleHealthAvailable() {
  return isIOS && !!AppleHealthKit;
}
