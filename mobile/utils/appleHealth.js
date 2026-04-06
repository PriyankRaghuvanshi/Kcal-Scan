/**
 * Apple Health (HealthKit) integration for iOS.
 * Writes food/nutrition from meal scans and weight from Let's Go journey to iPhone Health.
 * Reads a compact daily wellness summary for coach context.
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
const APPLE_HEALTH_ENABLED = false;

let AppleHealthKit = null;
let healthKitReady = false;

try {
  if (isIOS) {
    const healthModule = require("react-native-health");
    AppleHealthKit = healthModule?.default || healthModule || null;
  }
} catch (_) {
  // Module not installed or not linked
}

function healthPermissions() {
  return AppleHealthKit?.Constants?.Permissions || null;
}

function healthUnits() {
  return AppleHealthKit?.Constants?.Units || null;
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function getPermissions() {
  if (!AppleHealthKit) return null;
  const perms = healthPermissions();
  if (!perms || typeof perms !== "object") return null;
  const read = [
    perms.Steps,
    perms.SleepAnalysis,
    perms.DietaryWater,
  ].filter(Boolean);
  const write = [
    perms.EnergyConsumed,
    perms.Protein,
    perms.Carbohydrates,
    perms.FatTotal,
    perms.Fiber,
    perms.Weight,
  ].filter(Boolean);
  if (!read.length && !write.length) return null;
  return {
    permissions: {
      read,
      write,
    },
  };
}

function startOfDayIso(dateLike) {
  const d = dateLike ? new Date(dateLike) : new Date();
  if (!Number.isFinite(d.getTime())) return new Date().toISOString();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function endOfDayIso(dateLike) {
  const d = dateLike ? new Date(dateLike) : new Date();
  if (!Number.isFinite(d.getTime())) return new Date().toISOString();
  d.setHours(23, 59, 59, 999);
  return d.toISOString();
}

function callHealthMethod(methodName, options = {}) {
  return new Promise((resolve) => {
    if (!AppleHealthKit || typeof AppleHealthKit?.[methodName] !== "function") {
      resolve(null);
      return;
    }
    try {
      AppleHealthKit[methodName](options, (err, results) => {
        if (err) {
          resolve(null);
          return;
        }
        resolve(results ?? null);
      });
    } catch (_) {
      resolve(null);
    }
  });
}

function sumNumericValues(rows) {
  return (Array.isArray(rows) ? rows : []).reduce((acc, row) => {
    const value = num(row?.value ?? row?.quantity);
    return acc + (value != null ? value : 0);
  }, 0);
}

function sleepHoursFromSamples(rows) {
  const allowed = new Set(["ASLEEP", "CORE", "DEEP", "REM", "ASLEEP_CORE", "ASLEEP_DEEP", "ASLEEP_REM"]);
  return (Array.isArray(rows) ? rows : []).reduce((acc, row) => {
    const value = String(row?.value || "").trim().toUpperCase();
    if (value && !allowed.has(value)) return acc;
    const start = new Date(row?.startDate || "");
    const end = new Date(row?.endDate || "");
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) return acc;
    return acc + ((end.getTime() - start.getTime()) / 3600000);
  }, 0);
}

/**
 * Initialize HealthKit and request read + write permissions.
 * @param {function(err?: string)} callback - Called when init completes; err if user denied or unavailable.
 */
export function initAppleHealth(callback) {
  if (!APPLE_HEALTH_ENABLED || !isIOS || !AppleHealthKit || typeof AppleHealthKit?.initHealthKit !== "function") {
    if (callback) callback(null);
    return;
  }
  if (healthKitReady) {
    if (callback) callback(null);
    return;
  }
  try {
    const perms = getPermissions();
    if (!perms) {
      if (callback) callback(null);
      return;
    }
    AppleHealthKit.initHealthKit(perms, (err) => {
      if (!err) healthKitReady = true;
      if (callback) callback(err || null);
    });
  } catch (err) {
    if (callback) callback(err || null);
  }
}

export async function getDailyHealthContext(dateIso) {
  if (!APPLE_HEALTH_ENABLED || !isIOS || !AppleHealthKit) return null;

  const anchorDate = dateIso ? new Date(dateIso) : new Date();
  if (!Number.isFinite(anchorDate.getTime())) return null;

  const stepsRows = await callHealthMethod("getDailyStepCountSamples", {
    startDate: startOfDayIso(anchorDate),
    endDate: endOfDayIso(anchorDate),
  });
  const sleepRows = await callHealthMethod("getSleepSamples", {
    startDate: startOfDayIso(new Date(anchorDate.getTime() - 24 * 3600000)),
    endDate: endOfDayIso(anchorDate),
    limit: 24,
    ascending: false,
  });
  const waterResult = await callHealthMethod("getWater", {
    date: anchorDate.toISOString(),
    includeManuallyAdded: true,
  });

  const stepsCount = Math.round(sumNumericValues(stepsRows));
  const sleepHours = Number(sleepHoursFromSamples(sleepRows).toFixed(1));
  const waterLiters = Number((sumNumericValues(Array.isArray(waterResult) ? waterResult : [waterResult]) / 1000).toFixed(2));

  return {
    source: "apple_health",
    date: anchorDate.toISOString().slice(0, 10),
    steps_count: stepsCount > 0 ? stepsCount : null,
    sleep_hours: sleepHours > 0 ? sleepHours : null,
    hydration_l: waterLiters > 0 ? waterLiters : null,
    poor_sleep_flag: sleepHours > 0 ? sleepHours < 6.5 : false,
    low_hydration_flag: waterLiters > 0 ? waterLiters < 1.8 : false,
    low_steps_flag: stepsCount > 0 ? stepsCount < 4500 : false,
  };
}

/**
 * Write one meal's nutrition to Apple Health.
 * @param {object} opts - { dateIso, energyKcal, proteinG, carbsG, fatG, fiberG?, foodName? }
 */
export function writeNutritionToHealth(opts, callback) {
  if (!APPLE_HEALTH_ENABLED || !isIOS || !AppleHealthKit || typeof AppleHealthKit?.saveFood !== "function") {
    if (callback) callback(null);
    return;
  }
  try {
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
  } catch (err) {
    if (callback) callback(err || null);
  }
}

/**
 * Write weight to Apple Health (e.g. from Let's Go journey).
 * @param {object} opts - { dateIso?, valueKg }
 */
export function writeWeightToHealth(opts, callback) {
  if (!APPLE_HEALTH_ENABLED || !isIOS || !AppleHealthKit || typeof AppleHealthKit?.saveWeight !== "function") {
    if (callback) callback(null);
    return;
  }
  try {
    const valueKg = num(opts?.valueKg);
    if (valueKg == null || valueKg <= 0) {
      if (callback) callback(new Error("Invalid weight"));
      return;
    }
    const units = healthUnits();
    const unit = units?.gram || "gram";
    const startDate = opts?.dateIso ? new Date(opts.dateIso) : new Date();
    const options = {
      value: valueKg * 1000,
      unit,
      startDate: startDate.toISOString(),
    };
    AppleHealthKit.saveWeight(options, (err) => {
      if (callback) callback(err || null);
    });
  } catch (err) {
    if (callback) callback(err || null);
  }
}

/** True if HealthKit is available (iOS and module loaded). */
export function isAppleHealthAvailable() {
  return APPLE_HEALTH_ENABLED && isIOS && !!AppleHealthKit;
}
