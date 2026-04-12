/**
 * Android Health Connect — sync with the Google Fit ecosystem (and other apps).
 * - Writes: nutrition from scans, weight from journey (already in Google Fit when user allows).
 * - Reads: steps, sleep, hydration, resting HR, HRV (RMSSD), active calories, distance, floors
 *   for Goal Coach via health_context (same path as iOS Apple Health; Android-only fields added here).
 *
 * Requires Health Connect on device (Play app on API ≤33; system on 14+).
 * Play Console: Health Connect declaration required for production.
 */

import { Platform } from "react-native";

const ANDROID_HC_ENABLED = true;

let HC = null;
try {
  if (Platform.OS === "android") {
    HC = require("react-native-health-connect");
  }
} catch (_) {
  HC = null;
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function isAndroidHealthConnectAvailable() {
  return ANDROID_HC_ENABLED && Platform.OS === "android" && !!HC;
}

let hcInitialized = false;

async function ensureClientInitialized() {
  if (!isAndroidHealthConnectAvailable()) return false;
  try {
    const status = await HC.getSdkStatus();
    const readyCode = HC?.SdkAvailabilityStatus?.SDK_AVAILABLE ?? 3;
    if (status !== readyCode) return false;
    return await HC.initialize();
  } catch {
    return false;
  }
}

/**
 * Initialize SDK and request permissions (reads for coach + writes for meals/weight).
 */
export function initAndroidHealthConnect(callback) {
  if (!isAndroidHealthConnectAvailable()) {
    if (callback) callback(null);
    return;
  }
  if (hcInitialized) {
    if (callback) callback(null);
    return;
  }
  (async () => {
    try {
      const ok = await ensureClientInitialized();
      if (!ok) {
        if (callback) callback(new Error("Health Connect unavailable"));
        return;
      }
      await HC.requestPermission([
        { accessType: "read", recordType: "Steps" },
        { accessType: "read", recordType: "SleepSession" },
        { accessType: "read", recordType: "Hydration" },
        { accessType: "read", recordType: "RestingHeartRate" },
        { accessType: "read", recordType: "HeartRate" },
        { accessType: "read", recordType: "HeartRateVariabilityRmssd" },
        { accessType: "read", recordType: "ActiveCaloriesBurned" },
        { accessType: "read", recordType: "Distance" },
        { accessType: "read", recordType: "FloorsClimbed" },
        { accessType: "write", recordType: "Nutrition" },
        { accessType: "write", recordType: "Weight" },
      ]);
      hcInitialized = true;
      if (callback) callback(null);
    } catch (e) {
      if (callback) callback(e || null);
    }
  })();
}

function startEndOfDayUtc(dateIso) {
  const d = dateIso ? new Date(dateIso) : new Date();
  if (!Number.isFinite(d.getTime())) {
    const n = new Date();
    n.setUTCHours(0, 0, 0, 0);
    const end = new Date(n);
    end.setUTCHours(23, 59, 59, 999);
    return { start: n.toISOString(), end: end.toISOString() };
  }
  const local = new Date(d);
  local.setHours(0, 0, 0, 0);
  const end = new Date(local);
  end.setHours(23, 59, 59, 999);
  return { start: local.toISOString(), end: end.toISOString() };
}

function avgPositive(values) {
  const xs = (Array.isArray(values) ? values : []).filter((x) => num(x) != null && num(x) > 0).map(num);
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

/**
 * Daily wellness + activity summary for Goal Coach (Health Connect / Google Fit sources).
 */
export async function getDailyHealthConnectContext(dateIso) {
  if (!isAndroidHealthConnectAvailable()) return null;
  try {
    const ready = await ensureClientInitialized();
    if (!ready) return null;
    const { start, end } = startEndOfDayUtc(dateIso);
    const range = { operator: "between", startTime: start, endTime: end };

    let stepsCount = 0;
    let sleepHours = 0;
    let waterLiters = 0;
    let restingHrAvg = null;
    let heartRateAvg = null;
    let hrvRmssdMsAvg = null;
    let activeEnergyKcal = null;
    let distanceKm = null;
    let floorsClimbed = null;

    try {
      const stepsAgg = await HC.aggregateRecord({ recordType: "Steps", timeRangeFilter: range });
      stepsCount = Math.round(num(stepsAgg?.COUNT_TOTAL) || 0);
    } catch (_) {}

    try {
      const sleepAgg = await HC.aggregateRecord({ recordType: "SleepSession", timeRangeFilter: range });
      const sec = num(sleepAgg?.SLEEP_DURATION_TOTAL) || 0;
      sleepHours = Number((sec / 3600).toFixed(1));
    } catch (_) {}

    try {
      const hydAgg = await HC.aggregateRecord({ recordType: "Hydration", timeRangeFilter: range });
      waterLiters = Number((num(hydAgg?.VOLUME_TOTAL?.inLiters) || 0).toFixed(2));
    } catch (_) {}

    try {
      const rhr = await HC.aggregateRecord({ recordType: "RestingHeartRate", timeRangeFilter: range });
      const bpm = num(rhr?.BPM_AVG);
      restingHrAvg = bpm != null && bpm > 0 ? Math.round(bpm) : null;
    } catch (_) {}

    try {
      const hr = await HC.aggregateRecord({ recordType: "HeartRate", timeRangeFilter: range });
      const bpm = num(hr?.BPM_AVG);
      heartRateAvg = bpm != null && bpm > 0 ? Math.round(bpm) : null;
    } catch (_) {}

    try {
      const hrvRes = await HC.readRecords("HeartRateVariabilityRmssd", { timeRangeFilter: range });
      const rows = Array.isArray(hrvRes?.records) ? hrvRes.records : [];
      const msVals = rows.map((r) => r?.heartRateVariabilityMillis).filter((x) => num(x) != null && num(x) > 0);
      const avg = avgPositive(msVals);
      hrvRmssdMsAvg = avg != null ? Math.round(avg) : null;
    } catch (_) {}

    try {
      const act = await HC.aggregateRecord({ recordType: "ActiveCaloriesBurned", timeRangeFilter: range });
      const kcal = num(act?.ACTIVE_CALORIES_TOTAL?.inKilocalories);
      activeEnergyKcal = kcal != null && kcal > 0 ? Number(kcal.toFixed(0)) : null;
    } catch (_) {}

    try {
      const dist = await HC.aggregateRecord({ recordType: "Distance", timeRangeFilter: range });
      const m = num(dist?.DISTANCE?.inMeters);
      distanceKm = m != null && m > 0 ? Number((m / 1000).toFixed(2)) : null;
    } catch (_) {}

    try {
      const fl = await HC.aggregateRecord({ recordType: "FloorsClimbed", timeRangeFilter: range });
      const f = num(fl?.FLOORS_CLIMBED_TOTAL);
      floorsClimbed = f != null && f > 0 ? Math.round(f) : null;
    } catch (_) {}

    const anchor = dateIso ? new Date(dateIso) : new Date();
    const dateStr = Number.isFinite(anchor.getTime())
      ? anchor.toISOString().slice(0, 10)
      : new Date().toISOString().slice(0, 10);

    return {
      source: "health_connect",
      date: dateStr,
      steps_count: stepsCount > 0 ? stepsCount : null,
      sleep_hours: sleepHours > 0 ? sleepHours : null,
      hydration_l: waterLiters > 0 ? waterLiters : null,
      resting_heart_rate_bpm: restingHrAvg,
      heart_rate_avg_bpm: heartRateAvg,
      hrv_rmssd_ms_avg: hrvRmssdMsAvg,
      active_energy_kcal: activeEnergyKcal,
      distance_walking_running_km: distanceKm,
      floors_climbed: floorsClimbed,
      poor_sleep_flag: sleepHours > 0 ? sleepHours < 6.5 : false,
      low_hydration_flag: waterLiters > 0 ? waterLiters < 1.8 : false,
      low_steps_flag: stepsCount > 0 ? stepsCount < 4500 : false,
      low_hrv_flag: hrvRmssdMsAvg != null ? hrvRmssdMsAvg < 30 : false,
      elevated_resting_hr_flag: restingHrAvg != null ? restingHrAvg >= 80 : false,
    };
  } catch {
    return null;
  }
}

/** Health Connect RecordingMethod.RECORDING_METHOD_MANUAL_ENTRY */
const RECORDING_MANUAL_ENTRY = 3;
/** Health Connect MealType.LUNCH */
const MEAL_TYPE_LUNCH = 2;

/**
 * Write meal nutrition to Health Connect (syncs to Google Fit when allowed).
 */
export function writeNutritionToHealthConnect(opts, callback) {
  if (!isAndroidHealthConnectAvailable()) {
    if (callback) callback(null);
    return;
  }
  (async () => {
    try {
      const ready = await ensureClientInitialized();
      if (!ready) {
        if (callback) callback(null);
        return;
      }
      const date = opts?.dateIso ? new Date(opts.dateIso) : new Date();
      const foodName =
        opts?.foodName && String(opts.foodName).trim() ? String(opts.foodName).trim().slice(0, 100) : "Meal";
      const energyKcal = num(opts?.energyKcal);
      const proteinG = num(opts?.proteinG);
      const carbsG = num(opts?.carbsG);
      const fatG = num(opts?.fatG);
      const fiberG = num(opts?.fiberG);

      if (energyKcal == null || energyKcal < 0) {
        if (callback) callback(null);
        return;
      }

      const startMs = date.getTime();
      const startTime = new Date(startMs).toISOString();
      const endTime = new Date(startMs + 60_000).toISOString();

      const record = {
        recordType: "Nutrition",
        startTime,
        endTime,
        mealType: MEAL_TYPE_LUNCH,
        name: foodName,
        energy: { unit: "kilocalories", value: energyKcal },
        metadata: { recordingMethod: RECORDING_MANUAL_ENTRY },
      };
      if (proteinG != null && proteinG >= 0) record.protein = { unit: "grams", value: proteinG };
      if (carbsG != null && carbsG >= 0) record.totalCarbohydrate = { unit: "grams", value: carbsG };
      if (fatG != null && fatG >= 0) record.totalFat = { unit: "grams", value: fatG };
      if (fiberG != null && fiberG >= 0) record.dietaryFiber = { unit: "grams", value: fiberG };

      await HC.insertRecords([record]);
      if (callback) callback(null);
    } catch (e) {
      if (callback) callback(e || null);
    }
  })();
}

/**
 * Write body weight (kg) to Health Connect.
 */
export function writeWeightToHealthConnect(opts, callback) {
  if (!isAndroidHealthConnectAvailable()) {
    if (callback) callback(null);
    return;
  }
  (async () => {
    try {
      const ready = await ensureClientInitialized();
      if (!ready) {
        if (callback) callback(null);
        return;
      }
      const valueKg = num(opts?.valueKg);
      if (valueKg == null || valueKg <= 0) {
        if (callback) callback(new Error("Invalid weight"));
        return;
      }
      const time = opts?.dateIso ? new Date(opts.dateIso).toISOString() : new Date().toISOString();
      await HC.insertRecords([
        {
          recordType: "Weight",
          time,
          weight: { unit: "kilograms", value: valueKg },
          metadata: { recordingMethod: RECORDING_MANUAL_ENTRY },
        },
      ]);
      if (callback) callback(null);
    } catch (e) {
      if (callback) callback(e || null);
    }
  })();
}
