// build: 2026-02-04
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  Alert,
  ActivityIndicator,
  FlatList,
  StyleSheet,
  ScrollView,
  TextInput,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Linking,
  Share,
} from "react-native";

import { CameraView, useCameraPermissions } from "expo-camera";
import * as FileSystem from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

// OAuth helpers (Google)
import * as AuthSession from "expo-auth-session";
import * as Notifications from "expo-notifications";


import * as WebBrowser from "expo-web-browser";
// RevenueCat
import Purchases from "react-native-purchases";


WebBrowser.maybeCompleteAuthSession();

// ===================== SUBSCRIPTION (App Review 3.1.2) =====================
const PRIVACY_URL = "https://sites.google.com/view/calorieclickai/privacy-policy";
const TERMS_URL = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/";

// Pricing note for App Review & international launch
const SUBSCRIPTION_PRICE_NOTE =
  "Prices are shown in the App Store and may vary by country or region.";


// Health / medical info disclaimer + citations (App Review 1.4.1)
const HEALTH_DISCLAIMER = `CalorieClick.ai provides general nutrition estimates and wellness insights for informational purposes only and is not medical advice. Consult a qualified health 
professional for personal medical guidance.`;

const HEALTH_SOURCES = [
  { title: "USDA FoodData Central (nutrition reference)", url: "https://fdc.nal.usda.gov/" },
  { title: "NIH MedlinePlus: Protein in diet", url: "https://medlineplus.gov/ency/article/002467.htm" },
  {
    title: "International Tables of Glycemic Index (concept reference)",
    url: "https://diabetesjournals.org/care/article/34/9/2281/28564/International-Tables-of-Glycemic-Index-and",
  },
  { title: "NOVA classification (ultra-processed foods concept)", url: "https://iris.paho.org/handle/10665.2/55887" },
  { title: "WHO: Healthy diet (general nutrition guidance)", url: "https://www.who.int/news-room/fact-sheets/detail/healthy-diet" },
];



// ===================== CONFIG =====================
const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const HISTORY_KEY = "kcal_scan_history_v3";
const historyKey = (uid) => `${HISTORY_KEY}:${uid}`;
const MAX_HISTORY = 50;
const GOALS_KEY = "kcal_user_goals_v1";
const goalsKey = (uid) => `${GOALS_KEY}:${uid}`;
const DAILY_COACH_KEY = "kcal_daily_coach_v1";
const dailyCoachKey = (uid, day) => `${DAILY_COACH_KEY}:${uid}:${day}`;
const COACH_PROFILE_KEY = "kcal_coach_profile_v1";
const coachProfileKey = (uid) => `${COACH_PROFILE_KEY}:${uid}`;
const COACH_VOICE_MEMORY_KEY = "kcal_coach_voice_memory_v1";
const coachVoiceMemoryKey = (uid, day) => `${COACH_VOICE_MEMORY_KEY}:${uid}:${day}`;
const UPGRADE_NUDGE_KEY = "kcal_upgrade_nudge_v1";
const upgradeNudgeKey = (uid) => `${UPGRADE_NUDGE_KEY}:${uid}`;
const COACH_FEEDBACK_QUEUE_KEY = "kcal_coach_feedback_queue_v1";
const coachFeedbackQueueKey = (uid) => `${COACH_FEEDBACK_QUEUE_KEY}:${uid}`;

const RC_IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY || "";
const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "";
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

// OPTIONAL: If you have a custom deep link redirect (recommended for Google OAuth),
// set EXPO_PUBLIC_OAUTH_REDIRECT_TO to your app scheme URL.
// Example: "calorieclickai://auth-callback"
const OAUTH_REDIRECT_TO = process.env.EXPO_PUBLIC_OAUTH_REDIRECT_TO?.trim() || "calorieclickai://auth-callback";

// barcode scan cooldown (avoid duplicate reads)
const BARCODE_COOLDOWN_MS = 1400;
const DEFAULT_GOALS = {
  kcal: 2000,
  protein_g: 150,
  carbs_g: 200,
  fat_g: 70,
  fiber_g: 30,
};
const DEFAULT_COACH_PROFILE = {
  goal_type: "fat_loss",
  diet_style: "non-veg",
  training_days_per_week: 3,
  training_time: "evening",
  tone_preference: "supportive",
};

// ===================== HELPERS =====================
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function getDeviceTimeZone() {
  try {
    const tz = Intl?.DateTimeFormat?.().resolvedOptions?.().timeZone;
    return typeof tz === "string" && tz.trim() ? tz.trim() : "";
  } catch {
    return "";
  }
}
function withTimezoneQuery(url) {
  const tz = getDeviceTimeZone();
  const tzOffsetMin = -new Date().getTimezoneOffset(); // local UTC offset; east is positive
  const extra = [];
  if (tz) extra.push(`tz=${encodeURIComponent(tz)}`);
  if (Number.isFinite(tzOffsetMin)) extra.push(`tz_offset_min=${encodeURIComponent(tzOffsetMin)}`);
  if (!extra.length) return url;
  return `${url}${url.includes("?") ? "&" : "?"}${extra.join("&")}`;
}
function localDayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function localDayFromISO(ts) {
  try {
    if (!ts) return "";
    const d = new Date(ts);
    if (!Number.isFinite(d.getTime())) return "";
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch {
    return "";
  }
}
function normalizeGoals(raw, fallback = DEFAULT_GOALS) {
  const src = raw || {};
  const fb = fallback || DEFAULT_GOALS;
  return {
    kcal: num(src.kcal ?? src.kcal_goal ?? fb.kcal),
    protein_g: num(src.protein_g ?? src.protein_goal_g ?? fb.protein_g),
    carbs_g: num(src.carbs_g ?? src.carbs_goal_g ?? fb.carbs_g),
    fat_g: num(src.fat_g ?? src.fat_goal_g ?? fb.fat_g),
    fiber_g: num(src.fiber_g ?? src.fiber_goal_g ?? fb.fiber_g),
  };
}
function normalizeCoachProfile(raw) {
  const src = raw || {};
  const goalType = String(src.goal_type || DEFAULT_COACH_PROFILE.goal_type).toLowerCase();
  const dietStyle = String(src.diet_style || DEFAULT_COACH_PROFILE.diet_style).toLowerCase();
  const trainingTime = String(src.training_time || DEFAULT_COACH_PROFILE.training_time).toLowerCase();
  const rawTone = String(src.tone_preference || DEFAULT_COACH_PROFILE.tone_preference).toLowerCase();
  const toneAlias = {
    firm: "strict",
    fun: "funny",
    indian: "indian_coach",
    neutral: "supportive",
  };
  const tonePreference = toneAlias[rawTone] || rawTone;
  const out = {
    goal_type: ["fat_loss", "recomposition", "lean_gain"].includes(goalType) ? goalType : DEFAULT_COACH_PROFILE.goal_type,
    diet_style: ["veg", "non-veg", "vegan"].includes(dietStyle) ? dietStyle : DEFAULT_COACH_PROFILE.diet_style,
    training_days_per_week: Math.max(0, Math.min(7, Math.round(num(src.training_days_per_week ?? DEFAULT_COACH_PROFILE.training_days_per_week)))),
    training_time: ["morning", "afternoon", "evening", "night", "variable"].includes(trainingTime)
      ? trainingTime
      : DEFAULT_COACH_PROFILE.training_time,
    tone_preference: ["supportive", "strict", "funny", "indian_coach"].includes(tonePreference)
      ? tonePreference
      : DEFAULT_COACH_PROFILE.tone_preference,
  };
  return out;
}
function regionFromLocale() {
  try {
    const locale =
      Intl?.DateTimeFormat?.().resolvedOptions?.().locale ||
      Intl?.NumberFormat?.().resolvedOptions?.().locale ||
      "";
    const m = String(locale).match(/-([A-Za-z]{2})$/);
    return m ? m[1].toUpperCase() : "US";
  } catch {
    return "US";
  }
}
function hashString(text) {
  const s = String(text || "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h += (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24);
  }
  return `h${(h >>> 0).toString(16)}`;
}
function avg(arr) {
  const list = Array.isArray(arr) ? arr.map((x) => num(x)).filter((x) => Number.isFinite(x)) : [];
  if (!list.length) return 0;
  return list.reduce((a, b) => a + b, 0) / list.length;
}
function clampPct(v) {
  return Math.max(0, Math.min(100, num(v)));
}
function scoreTone(score) {
  const s = Math.round(num(score));
  if (s >= 80) return { label: "Excellent", color: "#22c55e", bg: "#0f2617" };
  if (s >= 65) return { label: "Good", color: "#34d399", bg: "#10281f" };
  if (s >= 50) return { label: "Improving", color: "#f59e0b", bg: "#2d210b" };
  if (s >= 35) return { label: "Needs focus", color: "#fb923c", bg: "#2f1a0d" };
  return { label: "At risk", color: "#ef4444", bg: "#2b1212" };
}
function riskLevelTone(level) {
  const l = String(level || "").toLowerCase();
  if (l === "high") return { color: "#ef4444", bg: "#2c1111" };
  if (l === "medium") return { color: "#f59e0b", bg: "#2a210f" };
  return { color: "#22c55e", bg: "#11271a" };
}
function shortDayLabel(dayIso) {
  try {
    if (!dayIso) return "";
    const d = new Date(`${dayIso}T00:00:00`);
    if (!Number.isFinite(d.getTime())) return String(dayIso).slice(5);
    return d.toLocaleDateString(undefined, { weekday: "short" });
  } catch {
    return String(dayIso || "").slice(5);
  }
}
function buildCoachIndicators(payload) {
  const p = payload || {};
  const goals = p.goals || {};
  const consumed = p.consumed || {};
  const signals = p.signals || {};
  const timing = p.meal_timing || {};

  const proteinPct = goals.protein_g > 0 ? clampPct((num(consumed.protein_g) / num(goals.protein_g)) * 100) : 0;
  const fiberPct = goals.fiber_g > 0 ? clampPct((num(consumed.fiber_g) / num(goals.fiber_g)) * 100) : 0;
  const glHealth = clampPct(100 - (num(signals.avg_glycemic_load) * 2.2));
  const upfHealth = clampPct(100 - (num(signals.ultra_processed_avg) * 10));
  const lateHealth = clampPct(100 - num(timing.late_calories_pct));

  return [
    { key: "protein", label: "Protein target", value: proteinPct, subtitle: `${round1(consumed.protein_g)}g / ${round1(goals.protein_g)}g` },
    { key: "fiber", label: "Fiber target", value: fiberPct, subtitle: `${round1(consumed.fiber_g)}g / ${round1(goals.fiber_g)}g` },
    { key: "gl", label: "Glycemic control", value: glHealth, subtitle: `GL ${round1(signals.avg_glycemic_load)}` },
    { key: "upf", label: "Whole-food quality", value: upfHealth, subtitle: `UPF ${round1(signals.ultra_processed_avg)}/10` },
    { key: "late", label: "Timing balance", value: lateHealth, subtitle: `${round1(timing.late_calories_pct)}% late kcal` },
  ];
}
function buildCoachPreviewTiles(plan) {
  const p = String(plan || "free").toLowerCase();
  const unlock =
    p === "advanced"
      ? "Unlock with Pro (1 step away)"
      : p === "elite"
      ? "Unlock with Pro"
      : "Unlock path: Elite -> Advanced -> Pro";
  return [
    {
      key: "diag",
      title: "Diagnosis engine",
      subtitle: "See why fat-loss progress slowed today.",
      unlock,
    },
    {
      key: "risk",
      title: "Risk alerts",
      subtitle: "Early flags for evening hunger and sugar spikes.",
      unlock,
    },
    {
      key: "actions",
      title: "Tomorrow actions",
      subtitle: "Get 1-3 specific food and behavior swaps.",
      unlock,
    },
  ];
}
function coachUpgradeBody(plan) {
  const p = String(plan || "free").toLowerCase();
  if (p === "advanced") {
    return "You are one step away. Upgrade to Pro to unlock diagnosis, risk alerts, and action coaching.";
  }
  if (p === "elite") {
    return "Elite unlocked barcode scanning. Upgrade to Pro to unlock deeper daily coaching.";
  }
  return "Upgrade to Pro to unlock diagnosis, risk alerts, and personalized action coaching.";
}
function estimateLocalSatiety(kcal, protein_g, fat_g) {
  const total = Math.max(1, num(kcal));
  const p = Math.max(0, num(protein_g));
  const f = Math.max(0, num(fat_g));
  const pDensity = (p / total) * 1000;
  const fDensity = (f / total) * 1000;
  return round1(Math.max(0, Math.min(100, 50 + (pDensity * 0.55) - (fDensity * 0.25) - (total / 60))));
}
function estimateLocalGL(carbs_g) {
  return round1(Math.max(0, num(carbs_g)) * 0.72);
}
function estimateLocalUPF(kcal, carbs_g, fat_g) {
  const total = Math.max(1, num(kcal));
  const cFrac = (Math.max(0, num(carbs_g)) * 4) / total;
  const fFrac = (Math.max(0, num(fat_g)) * 9) / total;
  return round1(Math.max(0, Math.min(10, (cFrac * 6) + (fFrac * 6) + (total / 800) * 4)));
}
function bucketFromHour(hour) {
  const h = num(hour);
  if (h >= 5 && h < 11) return "breakfast";
  if (h >= 11 && h < 16) return "lunch";
  if (h >= 16 && h < 22) return "dinner";
  return "snack";
}

function extractQueryParam(url, key) {
  try {
    const qIndex = url.indexOf("?");
    if (qIndex === -1) return null;
    const query = url.slice(qIndex + 1);
    const parts = query.split("&");
    for (const part of parts) {
      const [k, v] = part.split("=");
      if (decodeURIComponent(k || "") === key) return decodeURIComponent(v || "");
    }
    return null;
  } catch {
    return null;
  }
}
function extractHashParam(url, key) {
  try {
    const hashIndex = url.indexOf("#");
    if (hashIndex === -1) return null;
    const hash = url.slice(hashIndex + 1);
    const parts = hash.split("&");
    for (const part of parts) {
      const [k, v] = part.split("=");
      if (decodeURIComponent(k || "") === key) return decodeURIComponent(v || "");
    }
    return null;
  } catch {
    return null;
  }
}
function normalizeMicros(raw) {
  if (!raw || typeof raw !== "object") return null;
  const hasAny =
    raw.fiber_g != null ||
    raw.fiber != null ||
    raw.vitamin_d_ug != null ||
    raw.vitamin_d_mcg != null ||
    raw.vitamin_b12_ug != null ||
    raw.vitamin_b12_mcg != null ||
    raw.iron_mg != null ||
    raw.magnesium_mg != null;
  if (!hasAny) return null;
  return {
    fiber_g: num(raw.fiber_g ?? raw.fiber),
    vitamin_d_ug: num(raw.vitamin_d_ug ?? raw.vitamin_d_mcg),
    vitamin_b12_ug: num(raw.vitamin_b12_ug ?? raw.vitamin_b12_mcg),
    iron_mg: num(raw.iron_mg),
    magnesium_mg: num(raw.magnesium_mg),
  };
}
function normalizeTopCandidates(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x) => x && typeof x === "object")
    .map((x, idx) => ({
      candidate_id: String(x.candidate_id || `c${idx + 1}`),
      label: String(x.label || "").trim(),
      confidence: Math.max(0, Math.min(1, num(x.confidence))),
      evidence: Array.isArray(x.evidence) ? x.evidence.map((s) => String(s || "").trim()).filter(Boolean) : [],
      assumptions: Array.isArray(x.assumptions) ? x.assumptions.map((s) => String(s || "").trim()).filter(Boolean) : [],
      portion_guess_g: num(x.portion_guess_g),
    }))
    .filter((x) => x.label);
}
function normalizeEditableItems(raw) {
  const src = Array.isArray(raw?.items) ? raw.items : Array.isArray(raw) ? raw : [];
  return src
    .filter((x) => x && typeof x === "object")
    .map((x, idx) => ({
      item_id: String(x.item_id || `i${idx + 1}`),
      name: String(x.name || "").trim(),
      grams: num(x.grams),
      cooking_method: String(x.cooking_method || "unknown").trim().toLowerCase(),
      oil_added_tsp: Math.max(0, num(x.oil_added_tsp)),
      confidence: Math.max(0, Math.min(1, num(x.confidence))),
      candidate_alternatives: Array.isArray(x.candidate_alternatives)
        ? x.candidate_alternatives.map((s) => String(s || "").trim()).filter(Boolean)
        : [],
    }))
    .filter((x) => x.name && x.grams > 0);
}
function normalizeMealQA(raw) {
  const src = raw && typeof raw === "object" ? raw : {};
  const issues = Array.isArray(src.issues) ? src.issues : [];
  const fixes = Array.isArray(src.one_tap_fixes) ? src.one_tap_fixes : [];
  return {
    qa_score: Math.max(0, Math.min(100, num(src.qa_score))),
    issues: issues
      .filter((x) => x && typeof x === "object")
      .map((x) => ({
        issue_type: String(x.issue_type || "quality_check").trim(),
        severity: String(x.severity || "medium").trim().toLowerCase(),
        message: String(x.message || "").trim(),
      }))
      .filter((x) => x.message),
    one_tap_fixes: fixes
      .filter((x) => x && typeof x === "object")
      .map((x) => ({
        label: String(x.label || "").trim(),
        patch: x.patch && typeof x.patch === "object" ? x.patch : {},
      }))
      .filter((x) => x.label),
    ask_to_confirm: String(src.ask_to_confirm || "").trim() || null,
  };
}
function normalizeRerunPatch(patch, editableItems = []) {
  const src = patch && typeof patch === "object" ? patch : {};
  const out = { ...src };
  const firstItemId = String(editableItems?.[0]?.item_id || "").trim();
  const methodRaw = src?.set_cooking_method;
  const methodFromObj =
    methodRaw && typeof methodRaw === "object"
      ? String(methodRaw?.method || "").trim().toLowerCase()
      : "";
  const methodFromString =
    typeof methodRaw === "string" ? String(methodRaw || "").trim().toLowerCase() : "";
  const methodValue = methodFromObj || methodFromString;
  const methodItemId =
    methodRaw && typeof methodRaw === "object" ? String(methodRaw?.item_id || "").trim() : "";
  const fallbackItemId = methodItemId || firstItemId;

  if (methodValue) {
    out.set_cooking_method = fallbackItemId
      ? { item_id: fallbackItemId, method: methodValue }
      : { method: methodValue };
  }

  const oilRaw = src?.set_oil_added_tsp;

  if (oilRaw != null) {
    if (typeof oilRaw === "number" || typeof oilRaw === "string") {
      const tsp = Math.max(0, num(oilRaw));
      out.set_oil_added_tsp = fallbackItemId ? { item_id: fallbackItemId, tsp } : { tsp };
    } else if (oilRaw && typeof oilRaw === "object") {
      const tsp = Math.max(0, num(oilRaw?.tsp));
      const itemId = String(oilRaw?.item_id || fallbackItemId || "").trim();
      out.set_oil_added_tsp = itemId ? { item_id: itemId, tsp } : { tsp };
    }
  }

  const swapRaw = src?.swap_item;
  if (swapRaw != null) {
    if (typeof swapRaw === "string") {
      const newName = String(swapRaw || "").trim();
      if (newName) {
        out.swap_item = fallbackItemId ? { item_id: fallbackItemId, new_name: newName } : { new_name: newName };
      }
    } else if (swapRaw && typeof swapRaw === "object") {
      const newName = String(swapRaw?.new_name || "").trim();
      if (newName) {
        const itemId = String(swapRaw?.item_id || fallbackItemId || "").trim();
        out.swap_item = itemId ? { item_id: itemId, new_name: newName } : { new_name: newName };
      }
    }
  }

  const portionRaw = src?.portion_multiplier;
  if (portionRaw != null) {
    if (typeof portionRaw === "number" || typeof portionRaw === "string") {
      const multiplier = Math.max(0.3, Math.min(3, num(portionRaw)));
      out.portion_multiplier = fallbackItemId
        ? { item_id: fallbackItemId, multiplier }
        : { multiplier };
    } else if (portionRaw && typeof portionRaw === "object") {
      const multiplier = Math.max(0.3, Math.min(3, num(portionRaw?.multiplier)));
      const itemId = String(portionRaw?.item_id || fallbackItemId || "").trim();
      out.portion_multiplier = itemId
        ? { item_id: itemId, multiplier }
        : { multiplier };
    }
  }
  return out;
}
function normalizeAnalyzeResult(data) {
  const src = data && typeof data === "object" ? data : {};
  return {
    ...src,
    analysis_id: String(src.analysis_id || "").trim() || null,
    vision_confidence: Math.max(0, Math.min(1, num(src.vision_confidence))),
    top_candidates: normalizeTopCandidates(src.top_candidates),
    clarifying_question:
      src.clarifying_question && typeof src.clarifying_question === "object"
        ? {
            ask: String(src.clarifying_question.ask || "").trim(),
            options: Array.isArray(src.clarifying_question.options)
              ? src.clarifying_question.options.map((x) => String(x || "").trim()).filter(Boolean)
              : [],
          }
        : null,
    editable_context: { items: normalizeEditableItems(src.editable_context) },
    meal_qa: normalizeMealQA(src.meal_qa),
    micros: normalizeMicros(src?.micros || src?.totals?.micros),
    learning_applied: Boolean(src?.learning_applied),
    personalization_used:
      src?.personalization_used && typeof src.personalization_used === "object"
        ? {
            portion_prior_used: Boolean(src.personalization_used?.portion_prior_used),
            oil_prior_used: Boolean(src.personalization_used?.oil_prior_used),
            asked_clarifying_question: Boolean(src.personalization_used?.asked_clarifying_question),
            asked_clarifying_question_reason: String(src.personalization_used?.asked_clarifying_question_reason || "").trim(),
          }
        : null,
  };
}
function normalizeCoachDaily(raw, dayFallback = localDayISO()) {
  const data = raw && typeof raw === "object" ? raw : {};
  const sourceRaw = String(data?.fli_source || data?.reasoning_source || "").trim().toLowerCase();
  const source =
    sourceRaw === "llm" || sourceRaw === "cached_llm" || sourceRaw === "rules"
      ? sourceRaw
      : sourceRaw === "heuristic" || sourceRaw === "fallback"
      ? "rules"
      : "rules";
  return {
    date: String(data?.date || dayFallback),
    fat_loss_score: Math.round(num(data?.fat_loss_score)),
    one_sentence_summary: String(data?.one_sentence_summary || ""),
    pattern_detected: String(data?.pattern_detected || ""),
    projection_explained: String(data?.projection_explained || ""),
    biggest_risk_lever:
      data?.biggest_risk_lever && typeof data.biggest_risk_lever === "object"
        ? {
            title: String(data.biggest_risk_lever?.title || ""),
            reason: String(data.biggest_risk_lever?.reason || ""),
          }
        : null,
    highest_roi_change:
      data?.highest_roi_change && typeof data.highest_roi_change === "object"
        ? {
            title: String(data.highest_roi_change?.title || ""),
            why: String(data.highest_roi_change?.why || ""),
            how: String(data.highest_roi_change?.how || ""),
          }
        : null,
    projection_7d:
      data?.projection_7d && typeof data.projection_7d === "object"
        ? {
            if_unchanged: String(data.projection_7d?.if_unchanged || ""),
            if_improved: String(data.projection_7d?.if_improved || ""),
          }
        : null,
    if_you_do_one_thing: String(data?.if_you_do_one_thing || ""),
    predictive_signals:
      data?.predictive_signals && typeof data.predictive_signals === "object"
        ? {
            days_with_data_7d: Math.max(0, Math.round(num(data.predictive_signals?.days_with_data_7d))),
            scans_7d: Math.max(0, Math.round(num(data.predictive_signals?.scans_7d))),
            projection_confidence_band: String(data.predictive_signals?.projection_confidence_band || ""),
            missing_data_reason: String(data.predictive_signals?.missing_data_reason || ""),
            fat_loss_probability_7d: Math.max(0, Math.min(1, num(data.predictive_signals?.fat_loss_probability_7d))),
            projection_7d_score: clampPct(num(data.predictive_signals?.projection_7d_score)),
          }
        : null,
    diagnosis: Array.isArray(data?.diagnosis) ? data.diagnosis : [],
    tomorrow_focus: Array.isArray(data?.tomorrow_focus) ? data.tomorrow_focus : [],
    actions: Array.isArray(data?.actions) ? data.actions.slice(0, 2) : [],
    risk_alerts: Array.isArray(data?.risk_alerts) ? data.risk_alerts : [],
    disclaimer: String(data?.disclaimer || "Informational only."),
    reasoning_source: String(data?.reasoning_source || source),
    fli_source: source,
    fli_status: String(data?.fli_status || "ready").toLowerCase(),
    fli_reason_code: String(data?.fli_reason_code || ""),
    fli_stale_seconds: Math.max(0, Math.round(num(data?.fli_stale_seconds))),
    source_display: String(data?.source_display || "Coach"),
    last_processed_scan_id: String(data?.last_processed_scan_id || data?.latest_scan_id || "").trim(),
    last_processed_scan_ts: String(data?.last_processed_scan_ts || data?.latest_scan_ts || "").trim(),
    updatedAt: String(data?.updatedAt || data?.updated_at || ""),
    coach_generated_ts: String(data?.coach_generated_ts || data?.updatedAt || data?.updated_at || ""),
    payload_hash_used: String(data?.payload_hash_used || ""),
    daily_totals_version: normalizeVersionToken(data?.daily_totals_version || data?.state_signature || ""),
    meals_count_today: Math.max(0, Math.round(num(data?.meals_count_today))),
    tone_requested: String(data?.tone_requested || "").trim().toLowerCase(),
    tone_used: String(data?.tone_used || "").trim().toLowerCase(),
    tone_tag: String(data?.tone_tag || "").trim().toLowerCase(),
    tone_rewrite_source: String(data?.tone_rewrite_source || "").trim().toLowerCase(),
    tone_rewrite_freshness: String(data?.tone_rewrite_freshness || "").trim().toLowerCase(),
    microcopy:
      data?.microcopy && typeof data.microcopy === "object"
        ? {
            updating_text: String(data.microcopy?.updating_text || "").trim(),
            updated_text: String(data.microcopy?.updated_text || "").trim(),
          }
        : null,
    copy_checks: data?.copy_checks && typeof data.copy_checks === "object" ? data.copy_checks : null,
  };
}
function normalizeCoachVoice(raw) {
  const data = raw && typeof raw === "object" ? raw : {};
  const action = data?.one_action && typeof data.one_action === "object" ? data.one_action : {};
  const steps = Array.isArray(action?.steps) ? action.steps.map((x) => String(x || "").trim()).filter(Boolean) : [];
  return {
    coach_generated_ts: String(data?.coach_generated_ts || ""),
    tone_tag: String(data?.tone_tag || "neutral").toLowerCase(),
    empathy_line: String(data?.empathy_line || "").trim(),
    insight_line: String(data?.insight_line || "").trim(),
    one_action: {
      title: String(action?.title || "").trim(),
      steps: steps.slice(0, 3),
    },
    why_this_action: String(data?.why_this_action || "").trim(),
    advice_key: String(data?.advice_key || "").trim(),
    safety_disclaimer: String(data?.safety_disclaimer || "Informational only.").trim(),
  };
}
function normalizeWeeklyReport(raw) {
  const data = raw && typeof raw === "object" ? raw : {};
  return {
    week_start: String(data?.week_start || ""),
    week_end: String(data?.week_end || ""),
    resilience_score: clampPct(num(data?.resilience_score)),
    risk_score: clampPct(num(data?.risk_score)),
    confidence_band: String(data?.confidence_band || "medium").toLowerCase(),
    top_risks: Array.isArray(data?.top_risks) ? data.top_risks : [],
    top_wins: Array.isArray(data?.top_wins) ? data.top_wins : [],
    next_week_plan: Array.isArray(data?.next_week_plan) ? data.next_week_plan : [],
    report_card_facts: data?.report_card_facts && typeof data.report_card_facts === "object" ? data.report_card_facts : {},
    data_quality: data?.data_quality && typeof data.data_quality === "object" ? data.data_quality : {},
    disclaimer: String(data?.disclaimer || "Informational only."),
  };
}
function isCoachStaleForScan(coachPayload, latestScanId) {
  const latest = String(latestScanId || "").trim();
  if (!latest) return false;
  const processed = String(coachPayload?.last_processed_scan_id || "").trim();
  if (!processed) return true;
  return processed !== latest;
}
function buildCoachStateSignature(payload) {
  const p = payload || {};
  const goals = p.goals || {};
  const consumed = p.consumed || {};
  const signals = p.signals || {};
  const timing = p.meal_timing || {};
  const profile = p.profile || {};
  const seed = {
    day: String(p.date || ""),
    goals: {
      kcal: round1(goals.kcal),
      protein_g: round1(goals.protein_g),
      carbs_g: round1(goals.carbs_g),
      fat_g: round1(goals.fat_g),
      fiber_g: round1(goals.fiber_g),
    },
    consumed: {
      kcal: round1(consumed.kcal),
      protein_g: round1(consumed.protein_g),
      carbs_g: round1(consumed.carbs_g),
      fat_g: round1(consumed.fat_g),
      fiber_g: round1(consumed.fiber_g),
    },
    signals: {
      avg_satiety: round1(signals.avg_satiety),
      avg_glycemic_load: round1(signals.avg_glycemic_load),
      ultra_processed_avg: round1(signals.ultra_processed_avg),
      leucine_hit: Math.round(num(signals?.leucine_triggers?.hit)),
      leucine_target: Math.round(num(signals?.leucine_triggers?.target)),
    },
    timing: {
      late_calories_pct: round1(timing.late_calories_pct),
      biggest_meal: String(timing.biggest_meal || ""),
    },
    profile: {
      goal_type: String(profile.goal_type || ""),
      training_days_per_week: Math.round(num(profile.training_days_per_week)),
      training_time: String(profile.training_time || ""),
      tone_preference: String(profile.tone_preference || p.tone_preference || ""),
    },
  };
  return hashString(JSON.stringify(seed));
}
function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Math.round(num(ms) || 0))));
}
function logFliEvent(name, payload) {
  try {
    console.log(`[fli] ${String(name || "event")}`, JSON.stringify(payload || {}));
  } catch {
    console.log(`[fli] ${String(name || "event")}`);
  }
}
function fliUpdatedLabel(coachPayload, pending = false) {
  const updatingText = String(coachPayload?.microcopy?.updating_text || "").trim() || "Updating insights…";
  const updatedText = String(coachPayload?.microcopy?.updated_text || "").trim() || "Updated just now";
  if (pending) return updatingText;
  const rawTs = String(coachPayload?.updatedAt || coachPayload?.coach_generated_ts || "").trim();
  if (!rawTs) return updatedText;
  const d = new Date(rawTs);
  if (!Number.isFinite(d.getTime())) return updatedText;
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 5) return updatedText;
  if (sec < 60) return `Updated ${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `Updated ${min}m ago`;
  const hr = Math.round(min / 60);
  return `Updated ${hr}h ago`;
}
function normalizeVersionToken(raw) {
  const s = String(raw ?? "").trim();
  if (!s) return "";
  const n = Number(s);
  if (Number.isFinite(n) && n >= 0) return String(Math.round(n));
  return s;
}
function coalesceVersionToken(a, b) {
  const aa = normalizeVersionToken(a);
  const bb = normalizeVersionToken(b);
  const na = Number(aa);
  const nb = Number(bb);
  const aNum = Number.isFinite(na) && na >= 0;
  const bNum = Number.isFinite(nb) && nb >= 0;
  if (aNum && bNum) return String(Math.max(Math.round(na), Math.round(nb)));
  if (bNum) return String(Math.round(nb));
  if (aNum) return String(Math.round(na));
  return bb || aa;
}
function errorToMessage(detail, fallbackStatus) {
  if (detail == null) return `HTTP ${fallbackStatus}`;
  if (typeof detail === "string") return detail;
  if (typeof detail === "number" || typeof detail === "boolean") return String(detail);
  if (typeof detail === "object") {
    if (detail?.error && detail?.raw) {
      const raw = String(detail.raw || "").slice(0, 220);
      return `${detail.error}: ${raw}`;
    }
    const nested =
      detail?.message ||
      detail?.error ||
      detail?.detail ||
      detail?.msg ||
      detail?.reason ||
      null;
    if (nested && nested !== detail) return errorToMessage(nested, fallbackStatus);
    try {
      return JSON.stringify(detail).slice(0, 280);
    } catch {
      return `HTTP ${fallbackStatus}`;
    }
  }
  return `HTTP ${fallbackStatus}`;
}

function planAtLeast(current, required) {
  const c = (current || "free").toLowerCase();
  const r = (required || "free").toLowerCase();
  return PLAN_ORDER.indexOf(c) >= PLAN_ORDER.indexOf(r);
}
function pickHighestEntitlement(active) {
  const normalized = (active || []).map((x) => String(x || "").toLowerCase());
  const valid = normalized.filter((x) => PLAN_ORDER.includes(x));
  if (!valid.length) return null;
  valid.sort((a, b) => PLAN_ORDER.indexOf(a) - PLAN_ORDER.indexOf(b));
  return valid[valid.length - 1];
}
async function safeJson(res) {
  const t = await res.text();
  if (!t) {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return {};
  }

  let parsed = null;
  try {
    parsed = JSON.parse(t);
  } catch {
    const fallback = t?.slice(0, 220) || "Non-JSON response";
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${fallback}`);
    throw new Error(fallback);
  }

  if (!res.ok) {
    const msg = errorToMessage(
      parsed?.error || parsed?.message || parsed?.detail || parsed?.msg || parsed,
      res.status
    );
    throw new Error(msg);
  }
  return parsed;
}
async function apiGetUsage(userId) {
  const url = withTimezoneQuery(`${API_BASE}/usage?user_id=${encodeURIComponent(userId)}`);
  const res = await fetch(url, {
    headers: { accept: "application/json" },
  });
  return await safeJson(res);
}
async function apiPlanSync(userId, entitlement, mode) {
  const url = withTimezoneQuery(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", accept: "application/json" },
    body: JSON.stringify({ entitlement, mode }),
  });
  return await safeJson(res);
}
async function apiPost(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", accept: "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return await safeJson(res);
}

function nowISO() {
  try {
    return new Date().toISOString();
  } catch {
    return String(Date.now());
  }
}

// ===================== UI HELPERS =====================
function Meter({ label, value, max = 100, help, locked, lockedText }) {
  const pct = Math.max(0, Math.min(1, num(value) / num(max)));
  return (
    <View style={styles.meter}>
      <View style={styles.meterTop}>
        <Text style={styles.meterLabel}>{label}</Text>
        {locked ? (
          <Text style={styles.lockedTag}>{lockedText || "Locked 🔒"}</Text>
        ) : (
          <Text style={styles.meterValue}>
            {round1(value)}/{max}
          </Text>
        )}
      </View>
      <Text style={styles.meterHelp}>{help}</Text>
      <View style={styles.barOuter}>
        <View style={[styles.barFill, { width: `${pct * 100}%` }]} />
      </View>
    </View>
  );
}

export default function App() {
  // ===== Auth (Supabase) =====
  const [session, setSession] = useState(null);
  const redirectUri =
    OAUTH_REDIRECT_TO ||
    AuthSession.makeRedirectUri({ scheme: "calorieclickai", path: "auth-callback" });
  const [authEmail, setAuthEmail] = useState("");
  const [authPass, setAuthPass] = useState("");
  const [authBusy, setAuthBusy] = useState(false);

  // ===== NEW: Google + Phone OTP login =====

  // ===== Plan / Usage =====
  const [userId, setUserId] = useState(null);
  const [usage, setUsage] = useState(null);
  const plan = (usage?.plan || "free").toLowerCase();

  // ===== Photo Scan =====
  const [photoUri, setPhotoUri] = useState(null);
  const [result, setResult] = useState(null);
  const [dailySummary, setDailySummary] = useState(null);
  const [goals, setGoals] = useState(null);
  const [goalsDraft, setGoalsDraft] = useState(DEFAULT_GOALS);
  const [goalsModal, setGoalsModal] = useState(false);
  const [goalsBusy, setGoalsBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rerunBusy, setRerunBusy] = useState(false);

  // ===== History (isolated by user id) =====
  const [history, setHistory] = useState([]);
  const [coachDaily, setCoachDaily] = useState(null);
  const [coachVoice, setCoachVoice] = useState(null);
  const [coachVoiceBusy, setCoachVoiceBusy] = useState(false);
  const [coachTrend, setCoachTrend] = useState([]);
  const [coachLastPayload, setCoachLastPayload] = useState(null);
  const [weeklyReport, setWeeklyReport] = useState(null);
  const [weeklyReportBusy, setWeeklyReportBusy] = useState(false);
  const [coachBusy, setCoachBusy] = useState(false);
  const [fliSyncing, setFliSyncing] = useState(false);
  const [fliPending, setFliPending] = useState(false);
  const [coachErr, setCoachErr] = useState("");
  const [showCoachDebug, setShowCoachDebug] = useState(false);
  const [confidenceCalibration, setConfidenceCalibration] = useState(null);
  const [confidenceCalibrationBusy, setConfidenceCalibrationBusy] = useState(false);
  const [latestScanMeta, setLatestScanMeta] = useState({ id: "", ts: "" });
  const [showCoachDetails, setShowCoachDetails] = useState(false);
  const [coachProfile, setCoachProfile] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileDraft, setCoachProfileDraft] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileReady, setCoachProfileReady] = useState(false);
  const [coachProfileModal, setCoachProfileModal] = useState(false);
  const coachReqRef = useRef(false);
  const coachRefreshTimerRef = useRef(null);
  const coachQueuedRefreshRef = useRef(null);
  const coachTitleTapRef = useRef({ count: 0, lastTs: 0 });
  const rerunReqSeqRef = useRef(0);

  // ===== Camera Modal =====
  const [camOpen, setCamOpen] = useState(false);
  const camRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // ===== Barcode Modal =====
  const [barcodeOpen, setBarcodeOpen] = useState(false);
  const [barcodeManual, setBarcodeManual] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const lastBarcodeAt = useRef(0);

  // ===== RevenueCat =====
  const [rcReady, setRcReady] = useState(false);
  const [offerings, setOfferings] = useState(null);
  const [rcCustomerInfo, setRcCustomerInfo] = useState(null);
  const [rcBusy, setRcBusy] = useState(false);

  // ===== Derived gating =====
  const canBarcode = planAtLeast(plan, "elite");
  const canCoaching = planAtLeast(plan, "pro");
  const coachPreviewTiles = useMemo(() => (canCoaching ? [] : buildCoachPreviewTiles(plan)), [canCoaching, plan]);
  const previewPhotoUri = useMemo(() => {
    if (photoUri) return photoUri;
    const latestPhoto = (history || []).find((h) => (h?.kind || "") === "photo" && h?.photo_uri);
    return latestPhoto?.photo_uri || null;
  }, [photoUri, history]);
  const remainingToday = useMemo(() => {
    const g = goals || DEFAULT_GOALS;
    const todayKey = localDayISO();
    const historyFiberToday = (history || []).reduce((acc, h) => {
      if ((h?.kind || "") !== "photo") return acc;
      if (localDayFromISO(h?.ts) !== todayKey) return acc;
      const hm = normalizeMicros(h?.micros || h?.totals?.micros);
      return acc + num(hm?.fiber_g);
    }, 0);

    const totals = dailySummary?.totals || {};
    const backendFiber = num(totals?.fiber_g ?? totals?.micros?.fiber_g ?? totals?.micros?.fiber);
    const consumed = {
      kcal: num(dailySummary?.total_kcal ?? totals?.kcal ?? totals?.total_kcal),
      protein_g: num(totals?.protein_g),
      carbs_g: num(totals?.carbs_g),
      fat_g: num(totals?.fat_g),
      fiber_g: Math.max(backendFiber, historyFiberToday),
    };
    const fallbackRemaining = {
      kcal: round1(Math.max(0, num(g.kcal) - consumed.kcal)),
      protein_g: round1(Math.max(0, num(g.protein_g) - consumed.protein_g)),
      carbs_g: round1(Math.max(0, num(g.carbs_g) - consumed.carbs_g)),
      fat_g: round1(Math.max(0, num(g.fat_g) - consumed.fat_g)),
      fiber_g: round1(Math.max(0, num(g.fiber_g) - consumed.fiber_g)),
    };

    const apiRemaining = dailySummary?.remaining;
    if (apiRemaining && typeof apiRemaining === "object") {
      return {
        kcal:
          apiRemaining.kcal != null || apiRemaining.kcal_left != null
            ? round1(Math.max(0, num(apiRemaining.kcal ?? apiRemaining.kcal_left)))
            : fallbackRemaining.kcal,
        protein_g:
          apiRemaining.protein_g != null || apiRemaining.protein_g_left != null
            ? round1(Math.max(0, num(apiRemaining.protein_g ?? apiRemaining.protein_g_left)))
            : fallbackRemaining.protein_g,
        carbs_g:
          apiRemaining.carbs_g != null || apiRemaining.carbs_g_left != null
            ? round1(Math.max(0, num(apiRemaining.carbs_g ?? apiRemaining.carbs_g_left)))
            : fallbackRemaining.carbs_g,
        fat_g:
          apiRemaining.fat_g != null || apiRemaining.fat_g_left != null
            ? round1(Math.max(0, num(apiRemaining.fat_g ?? apiRemaining.fat_g_left)))
            : fallbackRemaining.fat_g,
        // Fiber can be missing in older goal schemas; always compute from local goals + consumed totals.
        fiber_g: fallbackRemaining.fiber_g,
      };
    }

    return fallbackRemaining;
  }, [dailySummary, goals, history]);

  // ===================== INIT =====================
  useEffect(() => {
    try {
      Notifications.setNotificationHandler({
        handleNotification: async () => ({
          shouldShowAlert: true,
          shouldPlaySound: true,
          shouldSetBadge: false,
        }),
      });
    } catch {}
  }, []);

  useEffect(
    () => () => {
      if (coachRefreshTimerRef.current) {
        clearTimeout(coachRefreshTimerRef.current);
        coachRefreshTimerRef.current = null;
      }
    },
    []
  );

  useEffect(() => {
    let cancelled = false;
    let unsub = null;

    (async () => {
      if (!HAS_SUPABASE) return;
      try {
        const { data } = await supabase.auth.getSession();
        if (!cancelled) setSession(data?.session || null);
      } catch (e) {
        console.log("getSession failed", String(e));
      }

      const { data } = supabase.auth.onAuthStateChange((_event, sess) => {
        if (!cancelled) setSession(sess || null);
      });
      unsub = data?.subscription?.unsubscribe || null;
    })();

    return () => {
      cancelled = true;
      if (typeof unsub === "function") unsub();
    };
  }, []);

  useEffect(() => {
    const uid = session?.user?.id || null;
    setUserId(uid);
  }, [session]);

  // Reset user-scoped UI state immediately when account changes to avoid cross-account leakage on screen.
  useEffect(() => {
    setPhotoUri(null);
    setResult(null);
    setDailySummary(null);
    setHistory([]);
    setCoachDaily(null);
    setCoachVoice(null);
    setCoachTrend([]);
    setCoachLastPayload(null);
    setWeeklyReport(null);
    setFliSyncing(false);
    setFliPending(false);
    setCoachErr("");
    setShowCoachDebug(false);
    setConfidenceCalibration(null);
    setConfidenceCalibrationBusy(false);
    setLatestScanMeta({ id: "", ts: "" });
    setCoachProfile(DEFAULT_COACH_PROFILE);
    setCoachProfileDraft(DEFAULT_COACH_PROFILE);
    setCoachProfileReady(false);
    setCoachProfileModal(false);
    setBarcodeManual("");
    setBarcodeOpen(false);
    setCamOpen(false);
    setRerunBusy(false);
    if (coachRefreshTimerRef.current) {
      clearTimeout(coachRefreshTimerRef.current);
      coachRefreshTimerRef.current = null;
    }
    if (!userId) {
      setGoals(null);
      setGoalsDraft(DEFAULT_GOALS);
      setUsage(null);
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    refreshUsage();
    ensureGoals();
    fetchDailySummary();
    loadHistory();
    void flushCoachFeedbackQueue(userId);
  }, [userId]);

  useEffect(() => {
    if (!showCoachDebug) return;
    if (!userId) return;
    void fetchConfidenceCalibrationReport();
  }, [showCoachDebug, userId]);

  async function refreshUsage() {
    if (!userId) return;
    try {
      const u = await apiGetUsage(userId);
      setUsage(u);
    } catch (e) {
      console.log("usage error", String(e));
    }
  }

  async function loadHistory() {
    try {
      const raw = await AsyncStorage.getItem(historyKey(userId));
      const parsed = raw ? JSON.parse(raw) : [];
      setHistory(Array.isArray(parsed) ? parsed : []);
    } catch {
      setHistory([]);
    }
  }

  async function enqueueCoachFeedback(uid, body) {
    if (!uid || !body) return;
    const key = coachFeedbackQueueKey(uid);
    try {
      const raw = await AsyncStorage.getItem(key);
      const arr = raw ? JSON.parse(raw) : [];
      const queue = Array.isArray(arr) ? arr : [];
      queue.push({
        payload: body,
        attempts: 0,
        queued_at: nowISO(),
      });
      await AsyncStorage.setItem(key, JSON.stringify(queue.slice(-30)));
    } catch (e) {
      console.log("feedback queue write failed", String(e));
    }
  }

  async function flushCoachFeedbackQueue(uid) {
    if (!uid) return;
    const key = coachFeedbackQueueKey(uid);
    let queue = [];
    try {
      const raw = await AsyncStorage.getItem(key);
      queue = raw ? JSON.parse(raw) : [];
      queue = Array.isArray(queue) ? queue : [];
    } catch {
      queue = [];
    }
    if (!queue.length) return;

    const remaining = [];
    for (const row of queue) {
      const payload = row?.payload && typeof row.payload === "object" ? row.payload : null;
      if (!payload) continue;
      try {
        const res = await fetch(withTimezoneQuery(`${API_BASE}/coach/memory/feedback`), {
          method: "POST",
          headers: { "Content-Type": "application/json", accept: "application/json" },
          body: JSON.stringify(payload),
        });
        await safeJson(res);
      } catch (e) {
        const attempts = Math.max(0, Math.round(num(row?.attempts)));
        if (attempts < 1) {
          remaining.push({
            payload,
            attempts: attempts + 1,
            queued_at: row?.queued_at || nowISO(),
          });
        }
      }
    }
    try {
      if (remaining.length) {
        await AsyncStorage.setItem(key, JSON.stringify(remaining));
      } else {
        await AsyncStorage.removeItem(key);
      }
    } catch {}
  }

  async function pushHistory(entry) {
    try {
      const key = historyKey(userId);
      const raw = await AsyncStorage.getItem(key);
      const existing = raw ? JSON.parse(raw) : [];
      const arr = Array.isArray(existing) ? existing : [];
      const incomingAnalysisId = String(entry?.analysis_id || "").trim();
      if (incomingAnalysisId) {
        const idx = arr.findIndex((it) => String(it?.analysis_id || "").trim() === incomingAnalysisId);
        if (idx >= 0) {
          const merged = { ...(arr[idx] || {}), ...(entry || {}) };
          const next = [...arr];
          next[idx] = merged;
          setHistory(next);
          await AsyncStorage.setItem(key, JSON.stringify(next.slice(0, MAX_HISTORY)));
          return;
        }
      }
      const isDupPhoto =
        (entry?.kind || "") === "photo" &&
        Boolean(entry?.photo_uri) &&
        arr.some(
          (it) =>
            (it?.kind || "") === "photo" &&
            String(it?.photo_uri || "") === String(entry.photo_uri) &&
            localDayFromISO(it?.ts) === localDayFromISO(entry?.ts)
        );
      if (isDupPhoto) {
        setHistory(arr);
        return;
      }
      const next = [entry, ...arr].slice(0, MAX_HISTORY);
      setHistory(next);
      await AsyncStorage.setItem(key, JSON.stringify(next));
    } catch {}
  }

  async function clearHistory() {
    if (!userId) return;
    try {
      await AsyncStorage.removeItem(historyKey(userId));
    } catch {}
    setHistory([]);
  }

  async function loadLocalGoals(uid) {
    if (!uid) return null;
    try {
      const raw = await AsyncStorage.getItem(goalsKey(uid));
      if (!raw) return null;
      return normalizeGoals(JSON.parse(raw), DEFAULT_GOALS);
    } catch {
      return null;
    }
  }

  async function saveLocalGoals(uid, g) {
    if (!uid || !g) return;
    try {
      await AsyncStorage.setItem(goalsKey(uid), JSON.stringify(normalizeGoals(g, DEFAULT_GOALS)));
    } catch {}
  }

  async function loadCoachProfile(uid) {
    if (!uid) return DEFAULT_COACH_PROFILE;
    try {
      const raw = await AsyncStorage.getItem(coachProfileKey(uid));
      if (!raw) return DEFAULT_COACH_PROFILE;
      return normalizeCoachProfile(JSON.parse(raw));
    } catch {
      return DEFAULT_COACH_PROFILE;
    }
  }

  async function saveCoachProfile(uid, profile) {
    const normalized = normalizeCoachProfile(profile);
    if (!uid) {
      setCoachProfile(normalized);
      setCoachProfileDraft(normalized);
      return;
    }
    try {
      await AsyncStorage.setItem(coachProfileKey(uid), JSON.stringify(normalized));
    } catch {}
    setCoachProfile(normalized);
    setCoachProfileDraft(normalized);
  }

  async function loadCoachTrend(uid) {
    if (!uid) {
      setCoachTrend([]);
      return;
    }
    try {
      const prefix = `${DAILY_COACH_KEY}:${uid}:`;
      const keys = (await AsyncStorage.getAllKeys()) || [];
      const trendKeys = keys.filter((k) => String(k).startsWith(prefix));
      if (!trendKeys.length) {
        setCoachTrend([]);
        return;
      }
      const rows = await AsyncStorage.multiGet(trendKeys);
      const parsed = (rows || [])
        .map((row) => {
          const k = row?.[0];
          const v = row?.[1];
          if (!k || !v) return null;
          try {
            const obj = JSON.parse(v);
            const resp = obj?.response || obj;
            const score = Math.round(num(resp?.fat_loss_score));
            if (!Number.isFinite(score)) return null;
            const day = String(resp?.date || k.slice(prefix.length) || "");
            return { day: day.slice(0, 10), score: clampPct(score) };
          } catch {
            return null;
          }
        })
        .filter(Boolean)
        .sort((a, b) => String(a.day).localeCompare(String(b.day)))
        .slice(-7);
      setCoachTrend(parsed);
    } catch {
      setCoachTrend([]);
    }
  }

  function onCoachTitleTap() {
    const now = Date.now();
    const prev = coachTitleTapRef.current || { count: 0, lastTs: 0 };
    const nextCount = now - Number(prev.lastTs || 0) > 1700 ? 1 : Number(prev.count || 0) + 1;
    coachTitleTapRef.current = { count: nextCount, lastTs: now };
    if (nextCount >= 7) {
      coachTitleTapRef.current = { count: 0, lastTs: now };
      setShowCoachDebug((v) => !v);
    }
  }

  function getTodayPhotoMeals() {
    const today = localDayISO();
    return (history || [])
      .filter((h) => (h?.kind || "") === "photo" && localDayFromISO(h?.ts) === today)
      .map((h) => {
        const kcal = num(h?.total_kcal ?? h?.totals?.kcal ?? h?.totals?.total_kcal);
        const protein_g = num(h?.totals?.protein_g);
        const carbs_g = num(h?.totals?.carbs_g);
        const fat_g = num(h?.totals?.fat_g);
        const at = new Date(h?.ts || "");
        const hour = Number.isFinite(at.getTime()) ? at.getHours() : 12;
        const coachingObj = h?.coaching || null;
        const satiety = coachingObj?.satiety_score != null
          ? num(coachingObj.satiety_score)
          : estimateLocalSatiety(kcal, protein_g, fat_g);
        const gl = coachingObj?.glycemic_load?.gl != null
          ? num(coachingObj.glycemic_load.gl)
          : estimateLocalGL(carbs_g);
        const upf = coachingObj?.ultra_processed_score != null
          ? num(coachingObj.ultra_processed_score)
          : estimateLocalUPF(kcal, carbs_g, fat_g);
        return { kcal, protein_g, carbs_g, fat_g, hour, satiety, gl, upf };
      });
  }

  function buildDailyCoachPayload() {
    const g = normalizeGoals(goals || dailySummary?.goals || DEFAULT_GOALS, DEFAULT_GOALS);
    const totals = dailySummary?.totals || {};
    const meals = getTodayPhotoMeals();

    const mealSums = meals.reduce(
      (acc, m) => ({
        kcal: acc.kcal + num(m.kcal),
        protein_g: acc.protein_g + num(m.protein_g),
        carbs_g: acc.carbs_g + num(m.carbs_g),
        fat_g: acc.fat_g + num(m.fat_g),
      }),
      { kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 }
    );

    const consumedKcal = num(totals?.total_kcal ?? totals?.kcal) || mealSums.kcal;
    const consumedProtein = num(totals?.protein_g) || mealSums.protein_g;
    const consumedCarbs = num(totals?.carbs_g) || mealSums.carbs_g;
    const consumedFat = num(totals?.fat_g) || mealSums.fat_g;
    const backendFiber = num(totals?.fiber_g ?? totals?.micros?.fiber_g ?? totals?.micros?.fiber);
    const fiberFromRemaining = Math.max(0, num(g?.fiber_g) - num(remainingToday?.fiber_g));
    const consumedFiber = Math.max(backendFiber, fiberFromRemaining);

    const leucineTarget = coachProfile?.goal_type === "lean_gain" ? 4 : 3;
    const leucineHit = meals.filter((m) => num(m.protein_g) * 0.08 >= 2.5).length;

    const avgSatiety = meals.length
      ? avg(meals.map((m) => m.satiety))
      : estimateLocalSatiety(consumedKcal, consumedProtein, consumedFat);
    const avgGL = meals.length ? avg(meals.map((m) => m.gl)) : estimateLocalGL(consumedCarbs);
    const avgUPF = meals.length ? avg(meals.map((m) => m.upf)) : estimateLocalUPF(consumedKcal, consumedCarbs, consumedFat);

    const bucketTotals = { breakfast: 0, lunch: 0, dinner: 0, snack: 0 };
    let lateKcal = 0;
    meals.forEach((m) => {
      const b = bucketFromHour(m.hour);
      bucketTotals[b] += num(m.kcal);
      if (m.hour >= 19 || m.hour <= 1) lateKcal += num(m.kcal);
    });
    const biggestMeal = Object.entries(bucketTotals).sort((a, b) => num(b[1]) - num(a[1]))[0]?.[0] || "dinner";
    const lateCaloriesPct = consumedKcal > 0 ? round1((lateKcal / consumedKcal) * 100) : 0;

    return {
      date: localDayISO(),
      goals: {
        kcal: round1(g.kcal),
        protein_g: round1(g.protein_g),
        carbs_g: round1(g.carbs_g),
        fat_g: round1(g.fat_g),
        fiber_g: round1(g.fiber_g),
      },
      consumed: {
        kcal: round1(consumedKcal),
        protein_g: round1(consumedProtein),
        carbs_g: round1(consumedCarbs),
        fat_g: round1(consumedFat),
        fiber_g: round1(consumedFiber),
      },
      signals: {
        leucine_triggers: { target: leucineTarget, hit: Math.min(leucineTarget, leucineHit) },
        avg_satiety: round1(avgSatiety),
        avg_glycemic_load: round1(avgGL),
        ultra_processed_avg: round1(avgUPF),
      },
      meal_timing: {
        late_calories_pct: round1(lateCaloriesPct),
        biggest_meal: biggestMeal,
      },
      constraints: {
        diet: coachProfile?.diet_style || "non-veg",
        allergies: [],
        region: regionFromLocale(),
      },
      profile: {
        goal_type: coachProfile?.goal_type || "fat_loss",
        diet_style: coachProfile?.diet_style || "non-veg",
        training_days_per_week: num(coachProfile?.training_days_per_week),
        training_time: coachProfile?.training_time || "evening",
        tone_preference: coachProfile?.tone_preference || "supportive",
      },
      tone_preference: coachProfile?.tone_preference || "supportive",
    };
  }

  function localWeekStartISO(dayIso = localDayISO()) {
    try {
      const d = new Date(`${String(dayIso)}T00:00:00`);
      if (!Number.isFinite(d.getTime())) return String(dayIso);
      const wd = (d.getDay() + 6) % 7; // Monday=0
      d.setDate(d.getDate() - wd);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}-${m}-${day}`;
    } catch {
      return String(dayIso);
    }
  }

  async function loadRecentCoachVoiceMessages(uid, dayIso) {
    try {
      const raw = await AsyncStorage.getItem(coachVoiceMemoryKey(uid, dayIso));
      if (!raw) return [];
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];
      return arr
        .map((x) => ({
          advice_key: String(x?.advice_key || "").trim(),
          ts: String(x?.ts || "").trim(),
          summary: String(x?.summary || "").trim().slice(0, 180),
        }))
        .filter((x) => x.advice_key)
        .slice(0, 6);
    } catch {
      return [];
    }
  }

  async function rememberCoachVoiceMessage(uid, dayIso, voiceObj) {
    try {
      const cur = await loadRecentCoachVoiceMessages(uid, dayIso);
      const msg = {
        advice_key: String(voiceObj?.advice_key || "").trim(),
        ts: String(voiceObj?.coach_generated_ts || nowISO()),
        summary: `${String(voiceObj?.empathy_line || "")} ${String(voiceObj?.insight_line || "")}`.trim().slice(0, 180),
      };
      if (!msg.advice_key) return;
      const merged = [msg, ...cur.filter((x) => x.advice_key !== msg.advice_key)].slice(0, 6);
      await AsyncStorage.setItem(coachVoiceMemoryKey(uid, dayIso), JSON.stringify(merged));
    } catch {}
  }

  function getTodayVoiceMeals(latestResult = null) {
    const today = localDayISO();
    const rows = (history || [])
      .filter((h) => (h?.kind || "") === "photo" && localDayFromISO(h?.ts) === today)
      .map((h) => ({
        meal_id: String(h?.analysis_id || h?.ts || ""),
        ts: String(h?.ts || ""),
        label: String((h?.items?.[0]?.name || h?.items?.[0]?.item || "meal") || "meal"),
        kcal: round1(num(h?.totals?.kcal ?? h?.totals?.total_kcal ?? h?.total_kcal)),
        protein_g: round1(num(h?.totals?.protein_g)),
        carbs_g: round1(num(h?.totals?.carbs_g)),
        fat_g: round1(num(h?.totals?.fat_g)),
        confidence: Math.max(0, Math.min(1, num(h?.vision_confidence))),
        notes: String(h?.items?.map?.((x) => x?.name || x?.item || "").filter(Boolean).slice(0, 3).join(", ") || ""),
      }));

    const latest = latestResult && typeof latestResult === "object" ? latestResult : null;
    if (latest?.analysis_id) {
      const latestMeal = {
        meal_id: String(latest.analysis_id),
        ts: nowISO(),
        label: String((latest?.items?.[0]?.name || latest?.items?.[0]?.item || "meal") || "meal"),
        kcal: round1(num(latest?.totals?.kcal ?? latest?.totals?.total_kcal ?? latest?.total_kcal)),
        protein_g: round1(num(latest?.totals?.protein_g)),
        carbs_g: round1(num(latest?.totals?.carbs_g)),
        fat_g: round1(num(latest?.totals?.fat_g)),
        confidence: Math.max(0, Math.min(1, num(latest?.vision_confidence))),
        notes: String(latest?.items?.map?.((x) => x?.name || x?.item || "").filter(Boolean).slice(0, 3).join(", ") || ""),
      };
      const exists = rows.some((m) => String(m.meal_id) === String(latestMeal.meal_id));
      if (!exists) rows.push(latestMeal);
    }
    return rows.slice(-10);
  }

  async function fetchCoachVoice(latestResult = null, force = false) {
    const uid = userId || session?.user?.id;
    if (!uid || !canCoaching) return;
    const base = buildDailyCoachPayload();
    const day = String(base?.date || localDayISO());
    const payloadHash = hashString(
      JSON.stringify({
        goals: base?.goals || {},
        consumed: base?.consumed || {},
        meals: getTodayVoiceMeals(latestResult),
        tone: coachProfile?.tone_preference || "supportive",
      })
    );
    if (!force && coachVoice?.advice_key && String(coachVoice?.coach_generated_ts || "").startsWith(day)) {
      return;
    }
    const recentMessages = await loadRecentCoachVoiceMessages(uid, day);
    const requestBody = {
      user_id: uid,
      day,
      payload_hash: payloadHash,
      goals: base?.goals || {},
      consumed: base?.consumed || {},
      meals: getTodayVoiceMeals(latestResult),
      recent_messages: recentMessages,
      user_profile: {
        goal_type: coachProfile?.goal_type || "fat_loss",
        diet_style: coachProfile?.diet_style || "non-veg",
        training_days_per_week: Math.round(num(coachProfile?.training_days_per_week)),
        training_time: coachProfile?.training_time || "evening",
      },
      tone_preference: coachProfile?.tone_preference || "supportive",
    };
    setCoachVoiceBusy(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/coach/voice`);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(requestBody),
      });
      const data = await safeJson(res);
      const cleaned = normalizeCoachVoice(data);
      setCoachVoice(cleaned);
      await rememberCoachVoiceMessage(uid, day, cleaned);
    } catch (e) {
      console.log("coach voice fetch failed", String(e));
    } finally {
      setCoachVoiceBusy(false);
    }
  }

  async function sendCoachFeedback(feedbackType, corrections = {}) {
    const uid = userId || session?.user?.id;
    if (!uid || !result?.analysis_id) return;
    const items = Array.isArray(result?.items) ? result.items : [];
    const itemFromPatchId = String(corrections?.item_id || "").trim();
    const firstItem =
      items.find((it) => String(it?.item_id || "").trim() === itemFromPatchId) ||
      items.find((it) => String(it?.name || "").trim()) ||
      null;
    const itemName = String(corrections?.item_name || firstItem?.name || "").trim();
    const itemId = String(corrections?.item_id || firstItem?.item_id || "").trim();
    const foodKey = String(corrections?.food_key || itemName)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 64);
    const confirmedItems = items
      .map((it) => ({ name: String(it?.name || it?.item || "").trim(), grams: round1(num(it?.grams)) }))
      .filter((x) => x.name)
      .slice(0, 5);
    const body = {
      user_id: uid,
      analysis_id: String(result?.analysis_id || ""),
      meal_id: String(result?.analysis_id || ""),
      feedback_type: String(feedbackType || "overall"),
      rating: 4,
      free_text: "",
      corrections: {
        item_id: itemId,
        item_name: itemName,
        food_key: foodKey,
        cooking_method: String(corrections?.cooking_method || ""),
        oil_added_tsp:
          corrections?.oil_added_tsp == null || corrections?.oil_added_tsp === ""
            ? null
            : num(corrections?.oil_added_tsp),
        portion_multiplier:
          corrections?.portion_multiplier == null || corrections?.portion_multiplier === ""
            ? null
            : num(corrections?.portion_multiplier),
        confirmed_items: confirmedItems,
      },
    };
    try {
      const res = await fetch(withTimezoneQuery(`${API_BASE}/coach/memory/feedback`), {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(body),
      });
      await safeJson(res);
      void flushCoachFeedbackQueue(uid);
    } catch (e) {
      console.log("coach feedback failed", String(e));
      await enqueueCoachFeedback(uid, body);
    }
  }

  async function fetchWeeklyReport(force = false) {
    const uid = userId || session?.user?.id;
    if (!uid || !canCoaching) return;
    if (weeklyReport && !force) return;
    setWeeklyReportBusy(true);
    try {
      const body = {
        user_id: uid,
        week_start: localWeekStartISO(localDayISO()),
        tone_preference: coachProfile?.tone_preference || "supportive",
        training_days_per_week: Math.round(num(coachProfile?.training_days_per_week)),
      };
      const res = await fetch(withTimezoneQuery(`${API_BASE}/coach/weekly_report`), {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      setWeeklyReport(normalizeWeeklyReport(data));
    } catch (e) {
      console.log("weekly report fetch failed", String(e));
    } finally {
      setWeeklyReportBusy(false);
    }
  }

  async function fetchConfidenceCalibrationReport() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    setConfidenceCalibrationBusy(true);
    try {
      const types = ["portion", "oil", "vision"];
      const out = {};
      for (const t of types) {
        const url = withTimezoneQuery(
          `${API_BASE}/confidence/calibration/report?user_id=${encodeURIComponent(uid)}&prediction_type=${encodeURIComponent(t)}`
        );
        const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
        out[t] = await safeJson(res);
      }
      setConfidenceCalibration(out);
    } catch (e) {
      console.log("confidence calibration fetch failed", String(e));
      setConfidenceCalibration(null);
    } finally {
      setConfidenceCalibrationBusy(false);
    }
  }

  async function shareWeeklyReportCard() {
    if (!weeklyReport) return;
    const facts = weeklyReport?.report_card_facts || {};
    const msg = [
      `CalorieClick Weekly Report (${weeklyReport?.week_start} to ${weeklyReport?.week_end})`,
      `Resilience: ${Math.round(num(weeklyReport?.resilience_score))}/100`,
      `Risk: ${Math.round(num(weeklyReport?.risk_score))}/100`,
      `Confidence: ${String(weeklyReport?.confidence_band || "medium")}`,
      `Avg protein: ${round1(num(facts?.avg_protein_g))}g`,
      `Avg UPF: ${round1(num(facts?.avg_upf_score))}/10`,
      `Late calories: ${round1(num(facts?.late_calories_pct))}%`,
      `${String(weeklyReport?.disclaimer || "Informational only.")}`,
    ].join("\n");
    try {
      await Share.share({ message: msg });
    } catch (e) {
      console.log("share weekly report failed", String(e));
    }
  }

  async function ensureDailyCoach(force = false, opts = {}) {
    const uid = userId || session?.user?.id;
    if (!uid || !coachProfileReady) return;

    const payload = buildDailyCoachPayload();
    setCoachLastPayload(payload || null);
    const day = String(payload?.date || localDayISO());
    const requestedLatestScanId = String(opts?.latestScanId || latestScanMeta?.id || "").trim();
    const requestedLatestScanTs = String(opts?.latestScanTs || latestScanMeta?.ts || "").trim();
    const pollForLatest = Boolean(opts?.pollForLatest && requestedLatestScanId);
    const refreshServer = Boolean(opts?.refreshServer ?? force);
    const fastMode = opts?.fastMode !== false;
    const trigger = String(opts?.trigger || (force ? "manual" : "auto"));
    const requestedTone = String(coachProfile?.tone_preference || payload?.tone_preference || "supportive")
      .trim()
      .toLowerCase();
    const requestedDailyTotalsVersion = normalizeVersionToken(opts?.dailyTotalsVersion);

    if (!payload || num(payload?.consumed?.kcal) <= 0) {
      setFliSyncing(false);
      setFliPending(false);
      try {
        const raw = await AsyncStorage.getItem(dailyCoachKey(uid, day));
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(cachedResp);
            setCoachErr("");
            setFliPending(false);
            await loadCoachTrend(uid);
            return;
          }
        }
      } catch {}
      setCoachDaily(null);
      setCoachErr("");
      setFliPending(false);
      return;
    }

    const cacheKey = dailyCoachKey(uid, day);
    const localStateSignature = buildCoachStateSignature(payload);
    const stateSignature = requestedDailyTotalsVersion || localStateSignature;
    const payloadHash = hashString(`${JSON.stringify(payload)}|${stateSignature}`);

    if (!force) {
      try {
        const raw = await AsyncStorage.getItem(cacheKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedPayloadHash = String(parsed?.payloadHash || "");
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (
            cachedResp &&
            typeof cachedResp === "object" &&
            cachedPayloadHash === payloadHash &&
            !isCoachStaleForScan(cachedResp, requestedLatestScanId)
          ) {
            setCoachDaily(cachedResp);
            setCoachErr("");
            setFliPending(false);
            await loadCoachTrend(uid);
            return;
          }
          if (isCoachStaleForScan(cachedResp, requestedLatestScanId)) {
            logFliEvent("fli_stale_detected", {
              trigger: "cache",
              latest_scan_id: requestedLatestScanId,
              last_processed_scan_id: String(cachedResp?.last_processed_scan_id || ""),
            });
          }
        }
      } catch {}
    }

    if (coachReqRef.current) {
      if (force || pollForLatest) {
        const queuedNow = {
          latestScanId: requestedLatestScanId,
          latestScanTs: requestedLatestScanTs,
          dailyTotalsVersion: stateSignature,
          pollForLatest,
          refreshServer: true,
          fastMode,
          trigger: `${trigger}_queued`,
        };
        const prevQueued = coachQueuedRefreshRef.current && typeof coachQueuedRefreshRef.current === "object"
          ? coachQueuedRefreshRef.current
          : null;
        coachQueuedRefreshRef.current = {
          latestScanId: queuedNow.latestScanId || String(prevQueued?.latestScanId || "").trim(),
          latestScanTs: queuedNow.latestScanTs || String(prevQueued?.latestScanTs || "").trim(),
          dailyTotalsVersion: coalesceVersionToken(prevQueued?.dailyTotalsVersion, queuedNow.dailyTotalsVersion),
          pollForLatest: Boolean(queuedNow.pollForLatest || prevQueued?.pollForLatest),
          refreshServer: Boolean(queuedNow.refreshServer || prevQueued?.refreshServer),
          fastMode: Boolean((prevQueued?.fastMode !== false) && (queuedNow.fastMode !== false)),
          trigger: queuedNow.trigger,
        };
        setFliPending(true);
      }
      return;
    }
    coachReqRef.current = true;
    setCoachBusy(true);
    if (pollForLatest) setFliSyncing(true);
    if (force) setCoachErr("");

    const fetchCoachOnce = async (refreshFlag = false, pollAttempt = 0) => {
      const params = [`user_id=${encodeURIComponent(uid)}`];
      if (refreshFlag) params.push("refresh=1");
      if (fastMode) params.push("fast=1");
      if (requestedLatestScanId) params.push(`latest_scan_id=${encodeURIComponent(requestedLatestScanId)}`);
      if (requestedLatestScanTs) params.push(`latest_scan_ts=${encodeURIComponent(requestedLatestScanTs)}`);
      if (stateSignature) params.push(`state_signature=${encodeURIComponent(stateSignature)}`);
      if (requestedTone) params.push(`tone_id=${encodeURIComponent(requestedTone)}`);
      const url = withTimezoneQuery(`${API_BASE}/coach/daily?${params.join("&")}`);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await safeJson(res);
      const cleaned = normalizeCoachDaily(data, day);
      logFliEvent("fli_fetch", {
        trigger,
        poll_attempt: pollAttempt,
        updatedAt: cleaned?.updatedAt || "",
        coach_generated_ts: cleaned?.coach_generated_ts || "",
        payload_hash_used: cleaned?.payload_hash_used || "",
        meals_count_today: cleaned?.meals_count_today ?? null,
        last_processed_scan_id: cleaned?.last_processed_scan_id || "",
      });
      const toneUsed = String(cleaned?.tone_used || "").trim().toLowerCase();
      if (toneUsed && requestedTone && toneUsed !== requestedTone) {
        console.log(`[fli] tone_mismatch requested=${requestedTone} used=${toneUsed}`);
      }
      return cleaned;
    };

    const autoRefreshStarted = Date.now();
    let autoRefreshAttemptCount = 0;
    try {
      let cleaned = await fetchCoachOnce(refreshServer, 0);
      let stale = isCoachStaleForScan(cleaned, requestedLatestScanId);
      if (stale) {
        logFliEvent("fli_stale_detected", {
          trigger,
          latest_scan_id: requestedLatestScanId,
          last_processed_scan_id: String(cleaned?.last_processed_scan_id || ""),
        });
      }

      if (stale && pollForLatest) {
        const maxPollAttempts = 10;
        for (let attempt = 1; attempt <= maxPollAttempts; attempt += 1) {
          autoRefreshAttemptCount = attempt;
          await waitMs(1200);
          cleaned = await fetchCoachOnce(true, attempt);
          stale = isCoachStaleForScan(cleaned, requestedLatestScanId);
          if (!stale) break;
        }
        logFliEvent("fli_auto_refreshed", {
          trigger,
          success: !stale,
          duration_ms: Date.now() - autoRefreshStarted,
          attempts: autoRefreshAttemptCount,
        });
      }

      setCoachDaily(cleaned);
      setCoachErr("");
      setFliPending(false);
      await AsyncStorage.setItem(
        cacheKey,
        JSON.stringify({
          payloadHash,
          stateSignature,
          latestScanId: requestedLatestScanId,
          ts: nowISO(),
          payload,
          response: cleaned,
        })
      );
      await loadCoachTrend(uid);
    } catch (e) {
      const errMsg = String(e).slice(0, 200);
      setCoachErr(errMsg);
      setFliPending(false);
      if (pollForLatest) {
        logFliEvent("fli_auto_refreshed", {
          trigger,
          success: false,
          duration_ms: Date.now() - autoRefreshStarted,
          attempts: autoRefreshAttemptCount,
          error: errMsg,
        });
      }
      try {
        const raw = await AsyncStorage.getItem(cacheKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(cachedResp);
            await loadCoachTrend(uid);
          }
        }
      } catch {}
    } finally {
      coachReqRef.current = false;
      setCoachBusy(false);
      setFliSyncing(false);
      setFliPending(false);
      const queued = coachQueuedRefreshRef.current;
      if (queued) {
        coachQueuedRefreshRef.current = null;
        setTimeout(() => {
          void ensureDailyCoach(true, queued);
        }, 0);
      }
    }
  }

  function scheduleDailyCoachRefresh(opts = {}) {
    if (coachRefreshTimerRef.current) {
      clearTimeout(coachRefreshTimerRef.current);
      coachRefreshTimerRef.current = null;
    }
    const safeOpts = opts && typeof opts === "object" ? opts : {};
    setFliPending(true);
    coachRefreshTimerRef.current = setTimeout(() => {
      coachRefreshTimerRef.current = null;
      void ensureDailyCoach(true, safeOpts);
    }, 600);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!userId) return;
      const loaded = await loadCoachProfile(userId);
      if (cancelled) return;
      setCoachProfile(loaded);
      setCoachProfileDraft(loaded);
      setCoachProfileReady(true);
      await loadCoachTrend(userId);
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (!userId || !coachProfileReady) return;
    if (!canCoaching) {
      setCoachDaily(null);
      setCoachVoice(null);
      setWeeklyReport(null);
      setFliSyncing(false);
      setFliPending(false);
      setCoachErr("");
      return;
    }
    void ensureDailyCoach(false);
    void fetchCoachVoice(null, false);
    void fetchWeeklyReport(false);
  }, [userId, coachProfileReady, goals, dailySummary, history, coachProfile, canCoaching]);

  async function applyCoachProfile() {
    const uid = userId || session?.user?.id;
    const normalized = normalizeCoachProfile(coachProfileDraft);
    await saveCoachProfile(uid, normalized);
    setCoachProfileModal(false);
    await ensureDailyCoach(true, { refreshServer: true, fastMode: true, trigger: "profile_update" });
  }

  function clearCurrentScan() {
    setPhotoUri(null);
    setResult(null);
  }

  // ===================== RevenueCat =====================
  useEffect(() => {
    (async () => {
      try {
        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
        if (!apiKey) return;
        Purchases.configure({ apiKey });
        setRcReady(true);

        const info = await Purchases.getCustomerInfo();
        setRcCustomerInfo(info);

        const offs = await Purchases.getOfferings();
        setOfferings(offs);
      } catch (e) {
        console.log("RC init error", e);
      }
    })();
  }, []);

  const activeEntitlements = useMemo(() => {
    const active = rcCustomerInfo?.entitlements?.active || {};
    return Object.keys(active).map((k) => k.toLowerCase());
  }, [rcCustomerInfo]);

  const priceByEntitlement = useMemo(() => {
    const map = {};
    const pkgs = offerings?.current?.availablePackages || [];
    for (const p of pkgs) {
      const id = String(p?.identifier || "").toLowerCase();
      const prod = p?.product;
      const price =
        prod?.priceString ||
        prod?.localizedPriceString ||
        (prod?.currencyCode && prod?.price ? `${prod.price} ${prod.currencyCode}` : null);

      if (!price) continue;

      for (const ent of ["elite", "advanced", "pro", "infinite"]) {
        if (id.includes(ent) && !map[ent]) map[ent] = price;
      }
    }
    return map;
  }, [offerings]);


  async function syncPlanToBackend(mode) {
    if (!userId) return;
    const highest = pickHighestEntitlement(activeEntitlements);
    const ent = highest || "free";

    try {
      await apiPlanSync(userId, ent, mode);
      await refreshUsage();
    } catch (e) {
      Alert.alert("Plan sync failed", String(e).slice(0, 180));
    }
  }

  async function restorePurchases() {
    try {
      setRcBusy(true);
      const info = await Purchases.restorePurchases();
      setRcCustomerInfo(info);
      await syncPlanToBackend("restore");
      Alert.alert("Restored", "Purchases restored and plan synced.");
    } catch (e) {
      Alert.alert("Restore failed", String(e).slice(0, 180));
    } finally {
      setRcBusy(false);
    }
  }

  async function purchaseEntitlement(entitlement) {
    try {
      if (!offerings?.current) {
        Alert.alert("Not ready", "Offerings not loaded yet.");
        return;
      }
      setRcBusy(true);

      const packages = offerings.current.availablePackages || [];
      const target = packages.find((p) =>
        String(p?.identifier || "").toLowerCase().includes(entitlement.toLowerCase())
      );

      if (!target) {
        Alert.alert("Not available", `Purchase option for ${entitlement} isn't available right now.`);
        return;
      }

      const { customerInfo } = await Purchases.purchasePackage(target);
      setRcCustomerInfo(customerInfo);

      await apiPlanSync(userId, entitlement, "purchase");
      await refreshUsage();

      Alert.alert("Purchased", `Upgraded to ${entitlement}.`);
    } catch (e) {
      const msg = String(e?.message || e);
      if (msg.toLowerCase().includes("cancel")) return;
      Alert.alert("Purchase failed", msg.slice(0, 200));
    } finally {
      setRcBusy(false);
    }
  }

  // ===================== AUTH =====================
  async function signIn() {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }
    setAuthBusy(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: authEmail.trim(),
        password: authPass,
      });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login failed", String(e?.message || e));
    } finally {
      setAuthBusy(false);
    }
  }

  async function signUp() {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }
    setAuthBusy(true);
    try {
      const { error } = await supabase.auth.signUp({
        email: authEmail.trim(),
        password: authPass,
      });
      if (error) throw error;
      Alert.alert("Check email", "Confirm your email, then log in.");
    } catch (e) {
      Alert.alert("Signup failed", String(e?.message || e));
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    try {
      await supabase.auth.signOut();
    } catch {}
    setPhotoUri(null);
    setResult(null);
    setDailySummary(null);
    setHistory([]);
    setCoachDaily(null);
    setCoachVoice(null);
    setCoachTrend([]);
    setCoachLastPayload(null);
    setWeeklyReport(null);
    setFliSyncing(false);
    setFliPending(false);
    setCoachErr("");
    setShowCoachDebug(false);
    setCoachProfile(DEFAULT_COACH_PROFILE);
    setCoachProfileDraft(DEFAULT_COACH_PROFILE);
    setCoachProfileReady(false);
    setCoachProfileModal(false);
    setGoals(null);
    setGoalsDraft(DEFAULT_GOALS);
    setGoalsModal(false);
    setBarcodeManual("");
    setBarcodeOpen(false);
    setCamOpen(false);
    setRerunBusy(false);
    if (coachRefreshTimerRef.current) {
      clearTimeout(coachRefreshTimerRef.current);
      coachRefreshTimerRef.current = null;
    }
    coachQueuedRefreshRef.current = null;
  }

  async function signInWithOAuthProvider(provider, failTitle) {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }

    setAuthBusy(true);
    try {
      if (typeof supabase?.auth?.signInWithOAuth !== "function") {
        throw new Error("OAuth login is unavailable in this app build.");
      }
      if (typeof WebBrowser.openAuthSessionAsync !== "function") {
        throw new Error("Auth browser helper is unavailable.");
      }

      const redirectTo = OAUTH_REDIRECT_TO || redirectUri;
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo,
          skipBrowserRedirect: true,
        },
      });
      if (error) throw error;
      if (!data?.url) throw new Error("No OAuth URL returned");

      const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);
      if (result.type !== "success" || !result.url) return;

      const callbackUrl = result.url;
      const oauthError =
        extractQueryParam(callbackUrl, "error") ||
        extractHashParam(callbackUrl, "error") ||
        "";
      const oauthErrorDesc =
        extractQueryParam(callbackUrl, "error_description") ||
        extractHashParam(callbackUrl, "error_description") ||
        "";
      if (oauthError) {
        throw new Error(oauthErrorDesc || oauthError);
      }

      const codeParam = extractQueryParam(callbackUrl, "code") || extractHashParam(callbackUrl, "code");
      if (codeParam && typeof supabase.auth.exchangeCodeForSession === "function") {
        const { data: sessionData, error: exchErr } = await supabase.auth.exchangeCodeForSession(codeParam);
        if (exchErr) throw exchErr;
        if (!sessionData?.session) throw new Error("No session returned");
        return;
      }

      const accessToken =
        extractQueryParam(callbackUrl, "access_token") || extractHashParam(callbackUrl, "access_token");
      const refreshToken =
        extractQueryParam(callbackUrl, "refresh_token") || extractHashParam(callbackUrl, "refresh_token");
      if (accessToken && refreshToken && typeof supabase.auth.setSession === "function") {
        const { data: setData, error: setErr } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        if (setErr) throw setErr;
        if (!setData?.session) throw new Error("No session returned");
        return;
      }

      if (typeof supabase.auth.getSessionFromUrl === "function") {
        const { data: urlData, error: urlErr } = await supabase.auth.getSessionFromUrl({
          storeSession: true,
          url: callbackUrl,
        });
        if (urlErr) throw urlErr;
        if (urlData?.session) return;
      }

      if (typeof supabase.auth.getSession === "function") {
        for (let i = 0; i < 5; i += 1) {
          const { data: cur } = await supabase.auth.getSession();
          if (cur?.session) return;
          await waitMs(180);
        }
      }

      throw new Error("OAuth callback did not include a valid auth session.");
    } catch (e) {
      console.log(`${String(provider || "oauth")} login error:`, e);
      Alert.alert(failTitle, String(e?.message || e));
    } finally {
      setAuthBusy(false);
    }
  }

  async function signInWithGoogle() {
    await signInWithOAuthProvider("google", "Google login failed");
  }

  async function signInWithApple() {
    await signInWithOAuthProvider("apple", "Apple login failed");
  }


async function openCamera() {
    const { granted } = permission || {};
    if (!granted) {
      const r = await requestPermission();
      if (!r?.granted) {
        Alert.alert("Camera permission", "Please allow camera access.");
        return;
      }
    }
    setCamOpen(true);
  }

  async function takePhoto() {
    try {
      if (!camRef.current) return;
      const photo = await camRef.current.takePictureAsync({ quality: 0.85, skipProcessing: true });
      if (!photo?.uri) return;
      setPhotoUri(photo.uri);
      setCamOpen(false);
    } catch (e) {
      Alert.alert("Camera error", String(e).slice(0, 180));
    }
  }

  // ===================== ANALYZE =====================
  async function fetchDailySummary(forceUserId) {
    try {
      const uid = forceUserId || session?.user?.id;
      if (!uid) return;
      const url = withTimezoneQuery(`${API_BASE}/daily/summary?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
      const data = await safeJson(res);
      const micros = normalizeMicros(data?.micros || data?.totals?.micros);
      const mergedGoals = normalizeGoals(data?.goals, goals || DEFAULT_GOALS);
      setDailySummary({ ...data, goals: mergedGoals, micros });
    } catch (e) {
      setDailySummary(null);
    }
  }

  async function upsertGoals(nextGoals) {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    const source = normalizeGoals(nextGoals || DEFAULT_GOALS, goals || DEFAULT_GOALS);
    try {
      const payload = normalizeGoals(source, goals || DEFAULT_GOALS);
      const res = await apiPost(`/goals?user_id=${encodeURIComponent(uid)}`, payload);
      const g = normalizeGoals(res?.goals || payload, payload);
      setGoals(g);
      setGoalsDraft(g);
      await saveLocalGoals(uid, g);
      setGoalsModal(false);
      await fetchDailySummary(uid);
    } catch (e) {
      Alert.alert("Goals update failed", errorToMessage(e?.message || e, 0));
    }
  }



  async function fetchGoals() {
    if (!userId) return null;
    try {
      const res = await fetch(`${API_BASE}/goals?user_id=${encodeURIComponent(userId)}`);
      const j = await safeJson(res);
      return normalizeGoals(j?.goals, DEFAULT_GOALS);
    } catch (e) {
      console.log("fetchGoals failed", e);
      return null;
    }
  }

  async function upsertDefaultGoals() {
    if (!userId) return null;
    const defaults = normalizeGoals({
      user_id: userId,
      ...DEFAULT_GOALS,
    }, DEFAULT_GOALS);
    try {
      const res = await fetch(`${API_BASE}/goals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, ...defaults }),
      });
      const j = await safeJson(res);
      return normalizeGoals(j?.goals || defaults, defaults);
    } catch (e) {
      console.log("upsertDefaultGoals failed", e);
      return defaults;
    }
  }

  async function ensureGoals() {
    if (!userId) return;
    setGoalsBusy(true);
    try {
      const local = await loadLocalGoals(userId);
      let g = await fetchGoals();
      // If no goals exist, set sensible defaults so "Remaining today" works out of the box
      if (!g || !g.kcal || Number(g.kcal) <= 0) {
        g = await upsertDefaultGoals();
      }
      const merged = normalizeGoals(g, local || DEFAULT_GOALS);
      setGoals(merged);
      setGoalsDraft(merged);
      await saveLocalGoals(userId, merged);
    } finally {
      setGoalsBusy(false);
    }
  }

  async function maybeSendScanUpgradeNudge(photoScansAfterThisAnalyze) {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    if (!usage || !["free", "elite", "advanced"].includes(plan)) return;
    if (num(photoScansAfterThisAnalyze) !== 5) return;

    try {
      const alreadySent = await AsyncStorage.getItem(upgradeNudgeKey(uid));
      if (alreadySent === "1") return;
      await AsyncStorage.setItem(upgradeNudgeKey(uid), "1");
    } catch {}

    const title = "Ready to unlock deeper coaching?";
    const body = coachUpgradeBody(plan);
    let sentAsPush = false;

    try {
      let status = "undetermined";
      const p = await Notifications.getPermissionsAsync();
      status = p?.status || "undetermined";
      if (status !== "granted") {
        const asked = await Notifications.requestPermissionsAsync();
        status = asked?.status || status;
      }
      if (status === "granted") {
        await Notifications.scheduleNotificationAsync({
          content: { title, body, sound: true },
          trigger: null,
        });
        sentAsPush = true;
      }
    } catch (e) {
      console.log("nudge notification error", String(e));
    }

    if (!sentAsPush) {
      Alert.alert(title, body);
    }
  }


  async function analyzePhoto() {
    if (!userId) return;
    if (!photoUri) {
      Alert.alert("No photo", "Take a photo first.");
      return;
    }
    const dupToday = (history || []).some(
      (it) =>
        (it?.kind || "") === "photo" &&
        String(it?.photo_uri || "") === String(photoUri) &&
        localDayFromISO(it?.ts) === localDayISO()
    );
    if (dupToday) {
      Alert.alert("Already analyzed", "This photo was already analyzed today. Take a new photo or clear current scan.");
      return;
    }
    const photoScansAfterThisAnalyze =
      (history || []).filter((h) => (h?.kind || "") === "photo").length + 1;
    setBusy(true);
    setResult(null);

    try {
      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "meal.jpg",
        type: "image/jpeg",
      });

      const analyzeUrl = withTimezoneQuery(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`);
      const res = await fetch(analyzeUrl, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });

      const data = await safeJson(res);
      const normalized = normalizeAnalyzeResult(data);
      setResult(normalized);
      const latestScanId = String(data?.scan_id || data?.latest_scan_id || data?.analysis_id || normalized?.analysis_id || "").trim();
      const latestScanTs = String(data?.latest_scan_ts || nowISO()).trim();
      if (latestScanId) {
        setLatestScanMeta({ id: latestScanId, ts: latestScanTs });
      }
      if (data?.fat_loss_intelligence && typeof data.fat_loss_intelligence === "object") {
        const quickCoach = normalizeCoachDaily(data.fat_loss_intelligence, localDayISO());
        setCoachDaily(quickCoach);
        setCoachErr("");
      }
      const coachStatus = String(data?.fat_loss_intelligence_status || "").trim().toLowerCase();
      const coachPendingNow = coachStatus === "pending";
      setFliPending(coachPendingNow);
      if (coachPendingNow) setFliSyncing(true);
      if (data?.daily && typeof data.daily === "object") {
        const dailyGoals = normalizeGoals(data?.daily?.goals, goals || DEFAULT_GOALS);
        setDailySummary({ ...data.daily, goals: dailyGoals });
      } else {
        const analyzedMicros = normalizeMicros(data?.micros || data?.totals?.micros || data?.micronutrients);
        setDailySummary((prev) => {
          const prevTotals = prev?.totals || {};
          const prevTotalKcal = num(prevTotals.total_kcal ?? prevTotals.kcal);
          const analyzedKcal = num(data?.total_kcal ?? data?.totals?.kcal ?? data?.totals?.total_kcal);

          const nextTotals = {
            ...prevTotals,
            total_kcal: round1(prevTotalKcal + analyzedKcal),
            kcal: round1(prevTotalKcal + analyzedKcal),
            protein_g: round1(num(prevTotals.protein_g) + num(data?.totals?.protein_g)),
            carbs_g: round1(num(prevTotals.carbs_g) + num(data?.totals?.carbs_g)),
            fat_g: round1(num(prevTotals.fat_g) + num(data?.totals?.fat_g)),
            fiber_g: round1(num(prevTotals.fiber_g) + num(analyzedMicros?.fiber_g)),
          };

          const g = prev?.goals || goals || DEFAULT_GOALS;
          const remaining = {
            kcal: round1(Math.max(0, num(g.kcal) - num(nextTotals.total_kcal))),
            protein_g: round1(Math.max(0, num(g.protein_g) - num(nextTotals.protein_g))),
            carbs_g: round1(Math.max(0, num(g.carbs_g) - num(nextTotals.carbs_g))),
            fat_g: round1(Math.max(0, num(g.fat_g) - num(nextTotals.fat_g))),
            fiber_g: round1(Math.max(0, num(g.fiber_g) - num(nextTotals.fiber_g))),
          };

          return {
            ...(prev || {}),
            day: prev?.day || localDayISO(),
            totals: nextTotals,
            goals: g,
            remaining,
          };
        });
      }
      await fetchDailySummary(userId);
      await refreshUsage();
      const totalsHash = hashString(
        JSON.stringify({
          kcal: round1(num(normalized?.totals?.kcal ?? normalized?.totals?.total_kcal ?? normalized?.total_kcal)),
          protein_g: round1(num(normalized?.totals?.protein_g)),
          carbs_g: round1(num(normalized?.totals?.carbs_g)),
          fat_g: round1(num(normalized?.totals?.fat_g)),
          fiber_g: round1(num(normalized?.micros?.fiber_g)),
        })
      );
      logFliEvent("analyze_success", {
        scan_id: latestScanId || "",
        scanCount: Math.round(num(data?.daily_signals?.scan_count ?? data?.daily_signals?.meals_count)),
        totalsHash,
      });
      await pushHistory({
        ts: nowISO(),
        kind: "photo",
        photo_uri: photoUri,
        total_kcal: data?.total_kcal,
        analysis_id: data?.analysis_id || null,
        totals: data?.totals,
        micros: data?.micros || data?.totals?.micros,
        items: data?.items,
        vision_confidence: data?.vision_confidence ?? null,
        coaching: data?.coaching || null,
        locked: data?.locked || null,
      });
      const dailyTotalsVersion = normalizeVersionToken(data?.daily_totals_version || data?.state_signature || "");
      scheduleDailyCoachRefresh({
        latestScanId,
        latestScanTs,
        dailyTotalsVersion,
        pollForLatest: Boolean(latestScanId),
        refreshServer: true,
        fastMode: true,
        trigger: "analyze",
      });
      void fetchCoachVoice(normalized, true);
      void fetchWeeklyReport(true);
      await maybeSendScanUpgradeNudge(photoScansAfterThisAnalyze);
    } catch (e) {
      setFliPending(false);
      Alert.alert("Analyze failed", String(e).slice(0, 220));
    } finally {
      setBusy(false);
    }
  }

  async function rerunAnalyzeWithPatch(editPatch) {
    if (!userId) return;
    const analysisId = String(result?.analysis_id || "").trim();
    if (!analysisId) {
      Alert.alert("Rerun unavailable", "Analyze a meal first.");
      return;
    }

    const rerunSeq = Number(rerunReqSeqRef.current || 0) + 1;
    rerunReqSeqRef.current = rerunSeq;
    setRerunBusy(true);
    try {
      const rerunUrl = withTimezoneQuery(`${API_BASE}/analyze/rerun?user_id=${encodeURIComponent(userId)}`);
      const normalizedPatch = normalizeRerunPatch(editPatch, result?.editable_context?.items || []);
      const res = await fetch(rerunUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify({
          analysis_id: analysisId,
          edits: normalizedPatch,
        }),
      });
      const data = await safeJson(res);
      if (rerunSeq !== Number(rerunReqSeqRef.current || 0)) {
        return;
      }
      const normalized = normalizeAnalyzeResult(data);
      setResult(normalized);
      const latestScanId = String(data?.scan_id || data?.latest_scan_id || data?.analysis_id || analysisId || "").trim();
      const latestScanTs = String(data?.latest_scan_ts || nowISO()).trim();
      if (latestScanId) {
        setLatestScanMeta({ id: latestScanId, ts: latestScanTs });
      }
      if (data?.fat_loss_intelligence && typeof data.fat_loss_intelligence === "object") {
        const quickCoach = normalizeCoachDaily(data.fat_loss_intelligence, localDayISO());
        setCoachDaily(quickCoach);
        setCoachErr("");
      }
      const coachStatus = String(data?.fat_loss_intelligence_status || "").trim().toLowerCase();
      const coachPendingNow = coachStatus === "pending";
      setFliPending(coachPendingNow);
      if (coachPendingNow) setFliSyncing(true);

      if (data?.daily && typeof data.daily === "object") {
        const dailyGoals = normalizeGoals(data?.daily?.goals, goals || DEFAULT_GOALS);
        setDailySummary({ ...data.daily, goals: dailyGoals });
      } else {
        await fetchDailySummary(userId);
      }
      await refreshUsage();
      await pushHistory({
        ts: nowISO(),
        kind: "photo",
        photo_uri: photoUri,
        total_kcal: data?.total_kcal,
        analysis_id: analysisId,
        totals: data?.totals,
        micros: data?.micros || data?.totals?.micros,
        items: data?.items,
        vision_confidence: data?.vision_confidence ?? null,
        coaching: data?.coaching || null,
        locked: data?.locked || null,
      });
      const dailyTotalsVersion = normalizeVersionToken(data?.daily_totals_version || data?.state_signature || "");
      scheduleDailyCoachRefresh({
        latestScanId,
        latestScanTs,
        dailyTotalsVersion,
        pollForLatest: Boolean(latestScanId),
        refreshServer: true,
        fastMode: true,
        trigger: "rerun",
      });
      void fetchCoachVoice(normalized, true);
      void fetchWeeklyReport(true);
    } catch (e) {
      if (rerunSeq === Number(rerunReqSeqRef.current || 0)) {
        setFliPending(false);
        console.log("rerun failed", String(e));
        Alert.alert("Rerun failed", "Couldn't apply edit. Try again.");
      }
    } finally {
      if (rerunSeq === Number(rerunReqSeqRef.current || 0)) {
        setRerunBusy(false);
      }
    }
  }

  async function applyClarifyingAnswer(answer) {
    const a = String(answer || "").trim();
    if (!a) return;
    setFliPending(true);
    await rerunAnalyzeWithPatch({ clarifying_answer: a });
    const lowered = a.toLowerCase();
    let cookingMethod = "";
    if (lowered.includes("air")) cookingMethod = "air_fried";
    else if (lowered.includes("deep")) cookingMethod = "deep_fried";
    else if (lowered.includes("pan") || lowered.includes("shallow")) cookingMethod = "pan_fried";
    else if (lowered.includes("grill")) cookingMethod = "grilled";
    else if (lowered.includes("boil")) cookingMethod = "boiled";
    const oilGuess =
      lowered.includes("heavy") || lowered.includes("deep")
        ? 3
        : lowered.includes("normal") || lowered.includes("pan")
        ? 1.5
        : lowered.includes("light") || lowered.includes("air")
        ? 0.5
        : 0;
    void sendCoachFeedback("cooking", { cooking_method: cookingMethod, oil_added_tsp: oilGuess });
  }

  async function applyQaFix(fix) {
    const rawPatch = fix?.patch && typeof fix.patch === "object" ? fix.patch : null;
    const patch = rawPatch ? normalizeRerunPatch(rawPatch, result?.editable_context?.items || []) : null;
    if (!patch) return;
    setFliPending(true);
    await rerunAnalyzeWithPatch(patch);
    void sendCoachFeedback("overall", {
      item_id:
        patch?.set_cooking_method?.item_id ||
        patch?.set_oil_added_tsp?.item_id ||
        patch?.swap_item?.item_id ||
        (patch?.portion_multiplier && typeof patch.portion_multiplier === "object" ? patch?.portion_multiplier?.item_id : "") ||
        "",
      cooking_method: patch?.set_cooking_method?.method || "",
      oil_added_tsp: patch?.set_oil_added_tsp?.tsp,
      portion_multiplier:
        patch?.portion_multiplier && typeof patch.portion_multiplier === "object"
          ? patch?.portion_multiplier?.multiplier
          : patch?.portion_multiplier,
    });
  }

  // ===================== BARCODE =====================
  async function openBarcodeScanner() {
    if (!canBarcode) {
      Alert.alert("Locked 🔒", "Barcode scanning is Elite+.");
      return;
    }
    const { granted } = permission || {};
    if (!granted) {
      const r = await requestPermission();
      if (!r?.granted) {
        Alert.alert("Camera permission", "Please allow camera access.");
        return;
      }
    }
    setBarcodeManual("");
    setBarcodeOpen(true);
  }

  async function barcodeLookup(code) {
    if (!userId) return;
    if (!code) return;

    setBarcodeBusy(true);
    try {
      const barcodeUrl = withTimezoneQuery(
        `${API_BASE}/barcode/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`
      );
      const res = await fetch(barcodeUrl, { headers: { accept: "application/json" } });
      const data = await safeJson(res);

      Alert.alert("Barcode result", `${data?.name || "Product"}\n${round1(data?.per_100g?.kcal)} kcal / 100g`);
      await refreshUsage();
      await pushHistory({
        ts: nowISO(),
        kind: "barcode",
        barcode: data?.barcode,
        name: data?.name,
        brand: data?.brand,
        per_100g: data?.per_100g,
      });
    } catch (e) {
      Alert.alert("Barcode failed", String(e).slice(0, 220));
    } finally {
      setBarcodeBusy(false);
    }
  }

  async function onBarcodeScanned({ data }) {
    const now = Date.now();
    if (now - lastBarcodeAt.current < BARCODE_COOLDOWN_MS) return;
    lastBarcodeAt.current = now;

    const code = String(data || "").trim();
    if (!code) return;
    setBarcodeOpen(false);
    await barcodeLookup(code);
  }

  // ===================== RENDER: LOGIN =====================
  if (!session) {
    return (
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={styles.container}>
            <Text style={styles.h1}>CalorieClick.ai</Text>
            <Text style={styles.p}>Log in to scan meals and track your history.</Text>

            {Platform.OS === "ios" ? (
              <TouchableOpacity style={styles.appleBtn} onPress={signInWithApple} disabled={authBusy}>
                {authBusy ? <ActivityIndicator /> : <Text style={styles.btnText}>Continue with Apple</Text>}
              </TouchableOpacity>
            ) : null}

            {/* Google login */}
            <TouchableOpacity style={styles.googleBtn} onPress={signInWithGoogle} disabled={authBusy}>
              {authBusy ? <ActivityIndicator /> : <Text style={styles.btnText}>Continue with Google</Text>}
            </TouchableOpacity>

            {/* Divider */}
            <View style={styles.dividerRow}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or email</Text>
              <View style={styles.dividerLine} />
            </View>


            <TextInput
              style={styles.input}
              placeholder="Email"
              placeholderTextColor="#777"
              autoCapitalize="none"
              value={authEmail}
              onChangeText={setAuthEmail}
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor="#777"
              secureTextEntry
              value={authPass}
              onChangeText={setAuthPass}
            />

            <View style={{ flexDirection: "row", gap: 10 }}>
              <TouchableOpacity style={styles.primaryBtn} onPress={signIn} disabled={authBusy}>
                {authBusy ? <ActivityIndicator /> : <Text style={styles.btnText}>Login</Text>}
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={signUp} disabled={authBusy}>
                <Text style={styles.btnText}>Sign up</Text>
              </TouchableOpacity>
            </View>

            {!HAS_SUPABASE ? (
              <Text style={[styles.p, { marginTop: 14, color: "#ffbdbd" }]}>
                Missing Supabase env vars. Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY.
              </Text>
            ) : null}
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // ===================== RENDER: APP =====================
  const coaching = result?.coaching || null;
  const locked = result?.locked || null;
  const coachTone = scoreTone(coachDaily?.fat_loss_score);
  const coachIndicators = buildCoachIndicators(coachLastPayload || {});
  const latestScanIdForCoach = String(latestScanMeta?.id || "").trim();
  const coachStale = Boolean(canCoaching && latestScanIdForCoach && isCoachStaleForScan(coachDaily, latestScanIdForCoach));

  const subscriptionPriceText = (key) => priceByEntitlement?.[key] || (rcReady ? "Loading…" : "See App Store");

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.topRow}>
          <View>
            <Text style={styles.h1}>CalorieClick.ai</Text>
            <Text style={styles.p}>
              Plan: <Text style={styles.plan}>{plan}</Text>
            </Text>
          </View>
          <TouchableOpacity style={styles.smallBtn} onPress={signOut}>
            <Text style={styles.smallBtnText}>Logout</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Scans left</Text>
          <Text style={styles.big}>
            {usage ? `${usage.remaining_day} today • ${usage.remaining_month} this month` : "…"}
          </Text>
          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={refreshUsage}>
              <Text style={styles.btnText}>Refresh</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={restorePurchases} disabled={rcBusy || !rcReady}>
              <Text style={styles.btnText}>{rcBusy ? "…" : "Restore"}</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.tiny}>Restore does NOT refill scans (only syncs your plan).</Text>
          <View style={{ marginTop: 12, flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={styles.tiny}>
              Goals: {Math.round(goals?.kcal || 0)} kcal • P {round1(goals?.protein_g || 0)}g • C {round1(goals?.carbs_g || 0)}g • F {round1(goals?.fat_g || 0)}g
            </Text>
            <TouchableOpacity style={styles.smallBtn} onPress={() => { setGoalsDraft(goals || DEFAULT_GOALS); setGoalsModal(true); }}>
              <Text style={styles.smallBtnText}>Edit</Text>
            </TouchableOpacity>
          </View>
          <View style={{ marginTop: 8 }}>
            <Text style={styles.p}>Protein left today: {round1(remainingToday.protein_g)}g</Text>
            <Text style={styles.tiny}>
              Remaining: {round1(remainingToday.kcal)} kcal • C {round1(remainingToday.carbs_g)}g • F {round1(remainingToday.fat_g)}g • Fiber {round1(remainingToday.fiber_g)}g
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.intelHeader}>
            <TouchableOpacity onPress={onCoachTitleTap} activeOpacity={0.9}>
              <Text style={styles.cardTitle}>Fat Loss Intelligence</Text>
            </TouchableOpacity>
            {canCoaching ? (
              <View style={styles.intelHeaderActions}>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => {
                    setCoachProfileDraft(coachProfile || DEFAULT_COACH_PROFILE);
                    setCoachProfileModal(true);
                  }}
                >
                  <Text style={styles.smallBtnText}>Profile</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => ensureDailyCoach(true, { refreshServer: true, fastMode: true, trigger: "manual_refresh" })}
                  disabled={coachBusy}
                >
                  <Text style={styles.smallBtnText}>{coachBusy ? "…" : "Refresh"}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => fetchWeeklyReport(true)}
                  disabled={weeklyReportBusy}
                >
                  <Text style={styles.smallBtnText}>{weeklyReportBusy ? "…" : "Weekly"}</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <Text style={styles.lockedTag}>Pro feature</Text>
            )}
          </View>

          <Text style={styles.intelSubline}>
            {canCoaching
              ? `${coachProfile?.goal_type || "fat_loss"} • ${coachProfile?.diet_style || "non-veg"} • ${Math.round(
                  num(coachProfile?.training_days_per_week)
                )} training day(s)/week • ${coachProfile?.training_time || "evening"} • ${coachProfile?.tone_preference || "supportive"}`
              : `${String(plan || "free").toUpperCase()} plan preview • Pro unlocks diagnosis, risk alerts, and actions`}
          </Text>

          {!canCoaching ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.p}>{coachUpgradeBody(plan)}</Text>
              <View style={styles.lockedPreviewGrid}>
                {(coachPreviewTiles || []).map((tile) => (
                  <View key={tile.key} style={styles.lockedPreviewTile}>
                    {previewPhotoUri ? (
                      <Image source={{ uri: previewPhotoUri }} style={styles.lockedPreviewBg} blurRadius={18} />
                    ) : (
                      <View style={styles.lockedPreviewGhost}>
                        <View style={styles.lockedPreviewGhostLine} />
                        <View style={styles.lockedPreviewGhostLineWide} />
                        <View style={styles.lockedPreviewGhostLineShort} />
                      </View>
                    )}
                    <View style={styles.lockedPreviewShade} />
                    <View style={styles.lockedPreviewContent}>
                      <Text style={styles.lockedPreviewUnlock}>{String(tile.unlock || "")}</Text>
                      <Text style={styles.lockedPreviewTitle}>{String(tile.title || "")}</Text>
                      <Text style={styles.lockedPreviewSubtitle}>{String(tile.subtitle || "")}</Text>
                    </View>
                  </View>
                ))}
              </View>
              <Text style={[styles.tiny, { marginTop: 8 }]}>
                After your 5th scan, we send: "Ready to unlock deeper coaching?"
              </Text>
            </View>
          ) : (
            <>
              {coachErr ? <Text style={[styles.tiny, { color: "#ffb4b4", marginTop: 8 }]}>{coachErr}</Text> : null}
              {(fliSyncing || coachStale || fliPending) ? (
                <View style={styles.fliUpdateBanner}>
                  <Text style={styles.fliUpdateText}>
                    {fliPending ? "New scan saved. Refining insights…" : "New scan detected. Updating insights…"}
                  </Text>
                </View>
              ) : null}

              {coachVoice ? (
                <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#1f2e45", borderRadius: 12, backgroundColor: "#08101e" }}>
                  <Text style={[styles.tiny, { textTransform: "uppercase", letterSpacing: 0.4 }]}>
                    Coach voice • {String(coachVoice?.tone_tag || "neutral")}
                  </Text>
                  {!!String(coachVoice?.empathy_line || "").trim() && <Text style={styles.p}>{String(coachVoice?.empathy_line || "")}</Text>}
                  {!!String(coachVoice?.insight_line || "").trim() && <Text style={styles.p}>{String(coachVoice?.insight_line || "")}</Text>}
                  {coachVoice?.one_action?.title ? (
                    <View style={{ marginTop: 6 }}>
                      <Text style={styles.itemName}>{String(coachVoice?.one_action?.title || "")}</Text>
                      {(coachVoice?.one_action?.steps || []).map((s, i) => (
                        <Text key={`${s}-${i}`} style={styles.tiny}>• {String(s || "")}</Text>
                      ))}
                      {!!String(coachVoice?.why_this_action || "").trim() && (
                        <Text style={[styles.tiny, { marginTop: 4 }]}>{String(coachVoice?.why_this_action || "")}</Text>
                      )}
                    </View>
                  ) : null}
                  {!!String(coachVoice?.safety_disclaimer || "").trim() && (
                    <Text style={[styles.tiny, { marginTop: 6 }]}>{String(coachVoice?.safety_disclaimer || "")}</Text>
                  )}
                </View>
              ) : coachVoiceBusy ? (
                <View style={{ marginTop: 10 }}>
                  <ActivityIndicator />
                </View>
              ) : null}

              {weeklyReport ? (
                <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#1f2e45", borderRadius: 12 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Text style={styles.cardTitle}>Weekly report card</Text>
                    <TouchableOpacity style={styles.smallBtn} onPress={shareWeeklyReportCard}>
                      <Text style={styles.smallBtnText}>Share</Text>
                    </TouchableOpacity>
                  </View>
                  <Text style={styles.tiny}>
                    {String(weeklyReport?.week_start || "")} to {String(weeklyReport?.week_end || "")} • confidence {String(weeklyReport?.confidence_band || "medium")}
                  </Text>
                  <Text style={styles.p}>
                    Resilience {Math.round(num(weeklyReport?.resilience_score))}/100 • Risk {Math.round(num(weeklyReport?.risk_score))}/100
                  </Text>
                  {(weeklyReport?.top_risks || []).slice(0, 2).map((r, i) => (
                    <Text key={`wr-risk-${i}`} style={styles.tiny}>• Risk: {String(r?.title || "")}</Text>
                  ))}
                  {(weeklyReport?.top_wins || []).slice(0, 2).map((w, i) => (
                    <Text key={`wr-win-${i}`} style={styles.tiny}>• Win: {String(w?.title || "")}</Text>
                  ))}
                  {!!String(weeklyReport?.disclaimer || "").trim() && <Text style={[styles.tiny, { marginTop: 6 }]}>{String(weeklyReport?.disclaimer || "")}</Text>}
                </View>
              ) : weeklyReportBusy ? (
                <View style={{ marginTop: 10 }}>
                  <ActivityIndicator />
                </View>
              ) : null}

              {coachBusy && !coachDaily ? (
                <View style={{ marginTop: 10 }}>
                  <ActivityIndicator />
                </View>
              ) : coachDaily ? (
                <View style={{ marginTop: 10 }}>
                  <View style={styles.intelScoreRow}>
                    <View style={[styles.scoreOrb, { borderColor: coachTone.color, shadowColor: coachTone.color }]}>
                      <Text style={styles.scoreOrbValue}>{Math.round(num(coachDaily?.fat_loss_score))}</Text>
                      <Text style={styles.scoreOrbUnit}>/100</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.intelKicker}>Fat-loss readiness</Text>
                      <View style={[styles.intelBadge, { backgroundColor: coachTone.bg, borderColor: coachTone.color }]}>
                        <View style={[styles.intelBadgeDot, { backgroundColor: coachTone.color }]} />
                        <Text style={[styles.intelBadgeText, { color: coachTone.color }]}>{coachTone.label}</Text>
                      </View>
                      <View style={styles.intelProgressTrack}>
                        <View
                          style={[
                            styles.intelProgressFill,
                            { width: `${clampPct(coachDaily?.fat_loss_score)}%`, backgroundColor: coachTone.color },
                          ]}
                        />
                      </View>
                      <Text style={styles.tiny}>
                        {fliUpdatedLabel(coachDaily, fliPending || fliSyncing)}
                        {coachDaily?.fli_source === "cached_llm" ? " • Refining…" : ""}
                      </Text>
                      {showCoachDebug ? (
                        <View style={{ marginTop: 6, padding: 8, borderWidth: 1, borderColor: "#26364f", borderRadius: 8 }}>
                          <Text style={styles.tiny}>payload_hash_used: {String(coachDaily?.payload_hash_used || "-")}</Text>
                          <Text style={styles.tiny}>
                            confidence_band: {String(coachDaily?.predictive_signals?.projection_confidence_band || "-")}
                          </Text>
                          <Text style={styles.tiny}>coach_generated_ts: {String(coachDaily?.coach_generated_ts || "-")}</Text>
                          <Text style={styles.tiny}>meals_count_today: {String(coachDaily?.meals_count_today ?? "-")}</Text>
                          <Text style={styles.tiny}>learning_applied: {result?.learning_applied ? "true" : "false"}</Text>
                          <Text style={styles.tiny}>
                            personalization_used: p={result?.personalization_used?.portion_prior_used ? "1" : "0"} / o=
                            {result?.personalization_used?.oil_prior_used ? "1" : "0"} / q=
                            {result?.personalization_used?.asked_clarifying_question ? "1" : "0"}
                          </Text>
                          <Text style={styles.tiny}>
                            clarifying_reason: {String(result?.personalization_used?.asked_clarifying_question_reason || "-")}
                          </Text>
                          {confidenceCalibrationBusy ? (
                            <Text style={styles.tiny}>calibration: loading…</Text>
                          ) : (
                            <>
                              <Text style={styles.tiny}>
                                Confidence Calibration
                              </Text>
                              <Text style={styles.tiny}>
                                Portion NACR: {Math.round(num(confidenceCalibration?.portion?.last_7d?.pct_within_range) * 100)}% within range
                              </Text>
                              <Text style={styles.tiny}>
                                Oil NACR: {Math.round(num(confidenceCalibration?.oil?.last_7d?.pct_within_range) * 100)}% within range
                              </Text>
                              <Text style={styles.tiny}>
                                Vision NACR: {Math.round(num(confidenceCalibration?.vision?.last_7d?.pct_within_range) * 100)}% within range
                              </Text>
                              <Text style={styles.tiny}>
                                Portion threshold: {round1(num(confidenceCalibration?.portion?.calibrated_threshold))}
                              </Text>
                            </>
                          )}
                        </View>
                      ) : null}
                    </View>
                  </View>

                  {String(coachDaily?.one_sentence_summary || "").trim() ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>Coach summary</Text>
                      <Text style={styles.p}>{String(coachDaily?.one_sentence_summary || "")}</Text>
                    </View>
                  ) : null}

                  {coachDaily?.predictive_signals ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>7-day outlook</Text>
                      <Text style={styles.p}>
                        Projection score {Math.round(num(coachDaily?.predictive_signals?.projection_7d_score))}/100 • probability{" "}
                        {Math.round(num(coachDaily?.predictive_signals?.fat_loss_probability_7d) * 100)}% • confidence{" "}
                        {String(coachDaily?.predictive_signals?.projection_confidence_band || "medium")}
                      </Text>
                      {String(coachDaily?.projection_explained || "").trim() ? (
                        <Text style={styles.tiny}>{String(coachDaily?.projection_explained || "")}</Text>
                      ) : null}
                      {String(coachDaily?.predictive_signals?.projection_confidence_band || "").toLowerCase() === "low" ? (
                        <Text style={[styles.tiny, { color: "#ffb4b4" }]}>
                          Low confidence - scan 2 more days to improve accuracy.
                        </Text>
                      ) : null}
                      {String(coachDaily?.predictive_signals?.missing_data_reason || "").trim() ? (
                        <Text style={styles.tiny}>{String(coachDaily?.predictive_signals?.missing_data_reason || "")}</Text>
                      ) : null}
                    </View>
                  ) : null}

                  {String(coachDaily?.if_you_do_one_thing || "").trim() ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>If you do one thing</Text>
                      <Text style={styles.p}>{String(coachDaily?.if_you_do_one_thing || "")}</Text>
                    </View>
                  ) : null}

                  {coachTrend?.length ? (
                    <View style={{ marginTop: 12 }}>
                      <Text style={styles.cardTitle}>7-day trend</Text>
                      <View style={styles.intelTrendRow}>
                        {coachTrend.map((pt, i) => {
                          const v = clampPct(pt?.score);
                          const h = 10 + (v * 0.46);
                          const tone = scoreTone(v);
                          return (
                            <View key={`${pt?.day || i}-${i}`} style={styles.intelTrendCol}>
                              <View style={[styles.intelTrendBar, { height: h, backgroundColor: tone.color }]} />
                              <Text style={styles.intelTrendValue}>{Math.round(v)}</Text>
                              <Text style={styles.intelTrendLabel}>{shortDayLabel(pt?.day)}</Text>
                            </View>
                          );
                        })}
                      </View>
                    </View>
                  ) : null}

                  {coachIndicators?.length ? (
                    <View style={{ marginTop: 12 }}>
                      <Text style={styles.cardTitle}>Daily signals</Text>
                      <View style={styles.intelSignalGrid}>
                        {coachIndicators.slice(0, 5).map((s) => {
                          const v = clampPct(s?.value);
                          const c = v >= 75 ? "#22c55e" : v >= 50 ? "#f59e0b" : "#ef4444";
                          return (
                            <View key={s.key} style={styles.intelSignalCard}>
                              <View style={styles.intelSignalTop}>
                                <Text style={styles.intelSignalLabel}>{s.label}</Text>
                                <Text style={[styles.intelSignalPercent, { color: c }]}>{Math.round(v)}%</Text>
                              </View>
                              <View style={styles.intelSignalTrack}>
                                <View style={[styles.intelSignalFill, { width: `${v}%`, backgroundColor: c }]} />
                              </View>
                              <Text style={styles.tiny}>{String(s.subtitle || "")}</Text>
                            </View>
                          );
                        })}
                      </View>
                    </View>
                  ) : null}

                  {String(coachDaily?.pattern_detected || "").trim() ? (
                    <View style={{ marginTop: 8 }}>
                      <Text style={styles.cardTitle}>Pattern detected</Text>
                      <Text style={styles.p}>{String(coachDaily?.pattern_detected || "")}</Text>
                    </View>
                  ) : null}

                  {coachDaily?.biggest_risk_lever?.title ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>Biggest risk lever</Text>
                      <View style={styles.actionBox}>
                        <Text style={styles.itemName}>{String(coachDaily?.biggest_risk_lever?.title || "")}</Text>
                        <Text style={styles.p}>{String(coachDaily?.biggest_risk_lever?.reason || "")}</Text>
                      </View>
                    </View>
                  ) : null}

                  {coachDaily?.highest_roi_change?.title ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>Highest ROI change</Text>
                      <View style={styles.actionBox}>
                        <Text style={styles.itemName}>{String(coachDaily?.highest_roi_change?.title || "")}</Text>
                        <Text style={styles.tiny}>{String(coachDaily?.highest_roi_change?.why || "")}</Text>
                        <Text style={styles.p}>{String(coachDaily?.highest_roi_change?.how || "")}</Text>
                      </View>
                    </View>
                  ) : null}

                  {(coachDaily?.projection_7d?.if_unchanged || coachDaily?.projection_7d?.if_improved) ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={styles.cardTitle}>7-day projection</Text>
                      {coachDaily?.projection_7d?.if_unchanged ? (
                        <Text style={styles.p}>• If unchanged: {String(coachDaily?.projection_7d?.if_unchanged || "")}</Text>
                      ) : null}
                      {coachDaily?.projection_7d?.if_improved ? (
                        <Text style={styles.p}>• If improved: {String(coachDaily?.projection_7d?.if_improved || "")}</Text>
                      ) : null}
                    </View>
                  ) : null}

                  <TouchableOpacity style={styles.intelToggleBtn} onPress={() => setShowCoachDetails((v) => !v)}>
                    <Text style={styles.btnText}>{showCoachDetails ? "Hide details" : "Show details"}</Text>
                  </TouchableOpacity>

                  {showCoachDetails ? (
                    <>
                      {(coachDaily?.diagnosis || []).length ? (
                        <View style={{ marginTop: 8 }}>
                          <Text style={styles.cardTitle}>Diagnosis</Text>
                          {(coachDaily.diagnosis || []).map((line, i) => (
                            <Text key={`diag-${i}`} style={styles.p}>
                              • {String(line)}
                            </Text>
                          ))}
                        </View>
                      ) : null}

                      {(coachDaily?.tomorrow_focus || []).length ? (
                        <View style={{ marginTop: 10 }}>
                          <Text style={styles.cardTitle}>Tomorrow focus</Text>
                          {(coachDaily.tomorrow_focus || []).map((line, i) => (
                            <Text key={`focus-${i}`} style={styles.p}>
                              • {String(line)}
                            </Text>
                          ))}
                        </View>
                      ) : null}

                      {(coachDaily?.risk_alerts || []).length ? (
                        <View style={{ marginTop: 10 }}>
                          <Text style={styles.cardTitle}>Risk alerts</Text>
                          {(coachDaily.risk_alerts || []).map((ra, i) => (
                            <View
                              key={`risk-${i}`}
                              style={[
                                styles.riskRow,
                                { backgroundColor: riskLevelTone(ra?.level).bg, borderColor: riskLevelTone(ra?.level).color },
                              ]}
                            >
                              <Text style={[styles.riskType, { color: riskLevelTone(ra?.level).color }]}>
                                {String(ra?.type || "risk").replace(/_/g, " ")} ({String(ra?.level || "medium")})
                              </Text>
                              <Text style={styles.tiny}>{String(ra?.reason || "")}</Text>
                            </View>
                          ))}
                        </View>
                      ) : null}

                      {(coachDaily?.actions || []).length ? (
                        <View style={{ marginTop: 10 }}>
                          <Text style={styles.cardTitle}>Actions</Text>
                          {(coachDaily.actions || []).slice(0, 2).map((a, i) => (
                            <View key={`action-${i}`} style={styles.actionBox}>
                              <Text style={styles.itemName}>{String(a?.title || "Action")}</Text>
                              <Text style={styles.tiny}>{String(a?.why || "")}</Text>
                              <Text style={styles.p}>{String(a?.how || "")}</Text>
                            </View>
                          ))}
                        </View>
                      ) : null}
                    </>
                  ) : null}

                  <Text style={[styles.tiny, { marginTop: 8 }]}>{String(coachDaily?.disclaimer || "Informational only.")}</Text>
                </View>
              ) : (
                <Text style={[styles.tiny, { marginTop: 10 }]}>
                  Analyze at least one meal today to generate daily intelligence.
                </Text>
              )}
            </>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Scan a meal</Text>

          {photoUri ? (
            <Image source={{ uri: photoUri }} style={styles.preview} />
          ) : (
            <View style={styles.previewEmpty}>
              <Text style={styles.previewText}>No photo yet</Text>
            </View>
          )}

          <View style={styles.row}>
            <TouchableOpacity style={styles.primaryBtn} onPress={openCamera}>
              <Text style={styles.btnText}>Open Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.primaryBtn} onPress={analyzePhoto} disabled={busy || rerunBusy || !photoUri}>
              {busy ? <ActivityIndicator /> : <Text style={styles.btnText}>Analyze</Text>}
            </TouchableOpacity>
          </View>

          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={clearCurrentScan} disabled={!photoUri && !result}>
              <Text style={styles.btnText}>Clear current scan</Text>
            </TouchableOpacity>
          </View>

          {result ? (
            <View style={{ marginTop: 14 }}>
              <Text style={styles.big}>Total: {round1(result.total_kcal)} kcal</Text>
              <Text style={styles.p}>
                Protein {round1(result?.totals?.protein_g)}g • Carbs {round1(result?.totals?.carbs_g)}g • Fat{" "}
                {round1(result?.totals?.fat_g)}g
              </Text>
              {rerunBusy ? <Text style={[styles.tiny, { marginTop: 6 }]}>Applying edit and rerunning analysis…</Text> : null}

              {result?.vision_confidence != null ? (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.cardTitle}>Scan confidence</Text>
                  <Text style={styles.p}>
                    {Math.round(Math.max(0, Math.min(1, num(result?.vision_confidence))) * 100)}% •{" "}
                    {Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.82
                      ? "High"
                      : Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.72
                      ? "Medium"
                      : "Low"}
                  </Text>
                  <View style={styles.barOuter}>
                    <View
                      style={[
                        styles.barFill,
                        {
                          width: `${Math.round(Math.max(0, Math.min(1, num(result?.vision_confidence))) * 100)}%`,
                          backgroundColor:
                            Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.82
                              ? "#22c55e"
                              : Math.max(0, Math.min(1, num(result?.vision_confidence))) >= 0.72
                              ? "#f59e0b"
                              : "#ef4444",
                        },
                      ]}
                    />
                  </View>
                </View>
              ) : null}

              {(result?.top_candidates || []).length ? (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.cardTitle}>Top candidates</Text>
                  {(result.top_candidates || []).slice(0, 3).map((c, idx) => (
                    <View key={`${c?.candidate_id || idx}`} style={styles.itemRow}>
                      <Text style={styles.itemName}>{String(c?.label || "")}</Text>
                      <Text style={styles.itemMeta}>
                        {Math.round(Math.max(0, Math.min(1, num(c?.confidence))) * 100)}% confidence • portion{" "}
                        {round1(c?.portion_guess_g)}g
                      </Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {result?.clarifying_question?.ask ? (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.cardTitle}>Confirm for better accuracy</Text>
                  <Text style={styles.p}>{String(result?.clarifying_question?.ask || "")}</Text>
                  <View style={styles.rowWrap}>
                    {(result?.clarifying_question?.options || []).slice(0, 6).map((opt, idx) => (
                      <TouchableOpacity
                        key={`${String(opt)}-${idx}`}
                        style={styles.chip}
                        onPress={() => applyClarifyingAnswer(opt)}
                        disabled={rerunBusy}
                      >
                        <Text style={styles.chipText}>{String(opt)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ) : null}

              {result?.meal_qa ? (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.cardTitle}>Meal QA</Text>
                  <Text style={styles.p}>Quality score: {round1(result?.meal_qa?.qa_score)}/100</Text>
                  {(result?.meal_qa?.issues || []).slice(0, 3).map((iss, idx) => (
                    <Text key={`qa-issue-${idx}`} style={styles.tiny}>
                      • {String(iss?.message || "")}
                    </Text>
                  ))}
                  {(result?.meal_qa?.one_tap_fixes || []).length ? (
                    <View style={styles.rowWrap}>
                      {(result?.meal_qa?.one_tap_fixes || []).slice(0, 3).map((fix, idx) => (
                        <TouchableOpacity
                          key={`fix-${idx}`}
                          style={styles.chip}
                          onPress={() => applyQaFix(fix)}
                          disabled={rerunBusy}
                        >
                          <Text style={styles.chipText}>{String(fix?.label || "Apply fix")}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  ) : null}
                </View>
              ) : null}

              {/* Micronutrients (Free) */}
{result?.micros ? (
  <View style={{ marginTop: 10 }}>
    <Text style={styles.cardTitle}>Micronutrients</Text>
    <Text style={styles.p}>
      Fiber {round1(result.micros.fiber_g ?? result.micros.fiber)}g • Vit D {round1(result.micros.vitamin_d_ug ?? result.micros.vitamin_d_mcg)}µg • B12{" "}
      {round1(result.micros.vitamin_b12_ug ?? result.micros.vitamin_b12_mcg)}µg
    </Text>
    <Text style={styles.p}>
      Iron {round1(result.micros.iron_mg)}mg • Magnesium {round1(result.micros.magnesium_mg)}mg
    </Text>
  </View>
) : null}

              <Text style={[styles.cardTitle, { marginTop: 12 }]}>Items</Text>
              {(result.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>{it.name}</Text>
                  <Text style={styles.itemMeta}>
                    {round1(it.grams)}g • {round1(it.kcal)} kcal
                  </Text>
                </View>
              ))}

              <Text style={[styles.cardTitle, { marginTop: 14 }]}>Coaching insights</Text>

              {!canCoaching ? (
                <View style={styles.lockedBox}>
                  <Text style={styles.lockedTitle}>Locked 🔒</Text>
                  <Text style={styles.p}>
                    Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.
                  </Text>
                  <Text style={styles.tiny}>Upgrade to Pro or Infinite to unlock these insights.</Text>
                </View>
              ) : coaching ? (
                <View style={{ marginTop: 8 }}>
                  <Meter
                    label="Satiety Score"
                    value={coaching.satiety_score}
                    max={100}
                    help={coaching?.layman_terms?.satiety || "How filling this meal is."}
                  />
                  <Meter
                    label="Protein Bioavailability"
                    value={coaching.protein_bv_score}
                    max={100}
                    help={coaching?.layman_terms?.protein_bv || "How well your body can use the protein."}
                  />

                  <View style={styles.meter}>
                    <View style={styles.meterTop}>
                      <Text style={styles.meterLabel}>Leucine estimate</Text>
                      <Text style={styles.meterValue}>{round1(coaching.leucine_estimate_g)}g</Text>
                    </View>
                    <Text style={styles.meterHelp}>
                      {coaching?.layman_terms?.leucine || "Key amino acid that helps switch on muscle-building."}
                    </Text>
                    <Text style={styles.tiny}>
                      MPS trigger: {round1(coaching.mps_threshold_g)}g •{" "}
                      {coaching.mps_triggered ? "✅ Triggered" : "❌ Not yet"}
                    </Text>
                  </View>

                  <View style={styles.meter}>
                    <View style={styles.meterTop}>
                      <Text style={styles.meterLabel}>Glycemic load</Text>
                      <Text style={styles.meterValue}>
                        {round1(coaching?.glycemic_load?.gl)} ({coaching?.glycemic_load?.level || "-"})
                      </Text>
                    </View>
                    <Text style={styles.meterHelp}>
                      {coaching?.layman_terms?.glycemic_load || "Sugar-spike risk from carbs."}
                    </Text>
                  </View>

                  <View style={styles.meter}>
                    <View style={styles.meterTop}>
                      <Text style={styles.meterLabel}>Ultra-processed score</Text>
                      <Text style={styles.meterValue}>{round1(coaching.ultra_processed_score)}/10</Text>
                    </View>
                    <Text style={styles.meterHelp}>
                      {coaching?.layman_terms?.ultra_processed || "How processed the food is."}
                    </Text>
                  </View>

                  {(coaching.messages || []).length ? (
                    <View style={{ marginTop: 10 }}>
                      {(coaching.messages || []).map((m, i) => (
                        <Text key={i} style={styles.p}>
                          • {m}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                </View>
              ) : locked ? (
                <View style={styles.lockedBox}>
                  <Text style={styles.lockedTitle}>Locked 🔒</Text>
                  <Text style={styles.p}>Upgrade to Pro to unlock coaching insights.</Text>
                </View>
              ) : (
                <Text style={styles.tiny}>No coaching data returned.</Text>
              )}

              {/* Health disclaimer + sources (Guideline 1.4.1) */}
              <View style={{ marginTop: 14 }}>
                <Text style={styles.muted}>{HEALTH_DISCLAIMER}</Text>

                <Text style={[styles.muted, { marginTop: 10, fontWeight: "800" }]}>Sources</Text>

                <View style={{ marginTop: 6 }}>
                  {HEALTH_SOURCES.map((s) => (
                    <TouchableOpacity
                      key={s.url}
                      onPress={() => Linking.openURL(s.url)}
                      style={{ marginBottom: 8 }}
                    >
                      <Text style={styles.link}>• {s.title}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

            </View>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Barcode</Text>
          <Text style={styles.p}>Elite+ can scan barcodes to fetch macros (OpenFoodFacts).</Text>

          <View style={styles.row}>
            <TouchableOpacity style={styles.primaryBtn} onPress={openBarcodeScanner} disabled={!canBarcode}>
              <Text style={styles.btnText}>{canBarcode ? "Scan barcode" : "Locked 🔒"}</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.manualRow}>
            <TextInput
              value={barcodeManual}
              onChangeText={setBarcodeManual}
              style={styles.manualInput}
              placeholder="Enter barcode manually"
              placeholderTextColor="#777"
              keyboardType="number-pad"
            />
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={() => barcodeLookup(barcodeManual.trim())}
              disabled={!canBarcode || barcodeBusy || !barcodeManual.trim()}
            >
              <Text style={styles.btnText}>{barcodeBusy ? "…" : "Lookup"}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Upgrade</Text>
          <Text style={styles.p}>Upgrade to unlock more scans and features.</Text>

          <View style={styles.rowWrap}>
            {["elite", "advanced", "pro", "infinite"].map((p) => (
              <TouchableOpacity
                key={p}
                style={styles.secondaryBtn}
                onPress={() => purchaseEntitlement(p)}
                disabled={rcBusy || !rcReady}
              >
                <Text style={styles.btnText}>{p.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Required subscription info for App Review (Guideline 3.1.2) */}
          <View style={{ marginTop: 12 }}>
            <Text style={styles.muted}>Service: CalorieClick.ai – Food Scan</Text>
            <Text style={[styles.muted, { marginTop: 6 }]}>
              Length: Monthly (auto-renewing) subscription. Each subscription period provides access to the plan features
              for that month.
            </Text>
            <Text style={[styles.muted, { marginTop: 6 }]}>
              What you get: Elite unlocks barcode scanning; Advanced increases scan limits; Pro unlocks coaching insights;
              Infinite provides the highest limits and all features.
            </Text>

            <Text style={[styles.muted, { marginTop: 8 }]}>Prices (per month):</Text>
            <Text style={[styles.muted, { marginTop: 2 }]}>{SUBSCRIPTION_PRICE_NOTE}</Text>

            <View style={{ marginTop: 6 }}>
              <Text style={styles.muted}>• Elite — {subscriptionPriceText("elite")}</Text>
              <Text style={styles.muted}>• Advanced — {subscriptionPriceText("advanced")}</Text>
              <Text style={styles.muted}>• Pro — {subscriptionPriceText("pro")}</Text>
              <Text style={styles.muted}>• Infinite — {subscriptionPriceText("infinite")}</Text>
            </View>

            <Text style={[styles.muted, { marginTop: 8 }]}>
              Subscriptions are billed monthly and auto-renew unless cancelled at least 24 hours before the end of the
              current period. Payment will be charged to your Apple ID account at confirmation of purchase. You can
              manage or cancel your subscription in Apple ID Settings.
            </Text>

            <View style={{ marginTop: 10, flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
              <TouchableOpacity onPress={() => Linking.openURL(PRIVACY_URL)}>
                <Text style={styles.link}>Privacy Policy</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => Linking.openURL(TERMS_URL)}>
                <Text style={styles.link}>Terms of Use (EULA)</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Health notice</Text>
          <Text style={[styles.muted, { marginTop: 6 }]}>{HEALTH_DISCLAIMER}</Text>

          <Text style={[styles.muted, { marginTop: 10, fontWeight: "800" }]}>Sources</Text>
          <View style={{ marginTop: 6 }}>
            {HEALTH_SOURCES.map((s) => (
              <TouchableOpacity
                key={s.url}
                onPress={() => Linking.openURL(s.url)}
                style={{ marginBottom: 8 }}
              >
                <Text style={styles.link}>• {s.title}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>



        <View style={styles.card}>
          <Text style={styles.cardTitle}>History (this user only)</Text>
          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={clearHistory} disabled={!history?.length}>
              <Text style={styles.btnText}>Clear history</Text>
            </TouchableOpacity>
          </View>

          {history?.length ? (
            <FlatList
              scrollEnabled={false}
              data={history}
              keyExtractor={(it, idx) => String(it.ts || idx)}
              renderItem={({ item }) => (
                <View style={styles.histRow}>
                  <Text style={styles.histTitle}>
                    {item.kind === "barcode"
                      ? `Barcode: ${item.name || item.barcode}`
                      : `Meal: ${round1(item.total_kcal)} kcal`}
                  </Text>
                  <Text style={styles.tiny}>{item.ts}</Text>
                </View>
              )}
            />
          ) : (
            <Text style={styles.tiny}>No history yet.</Text>
          )}
        </View>

        <View style={{ height: 30 }} />
      
        <Modal visible={goalsModal} transparent animationType="fade" onRequestClose={() => setGoalsModal(false)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.cardTitle}>Daily goals</Text>
              <Text style={styles.tiny}>Set targets so “Remaining today” becomes meaningful.</Text>

              <View style={{ marginTop: 12 }}>
                <Text style={styles.label}>Calories (kcal)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(goalsDraft?.kcal ?? "")}
                  onChangeText={(v) => setGoalsDraft((g) => ({ ...g, kcal: v }))}
                  placeholder="e.g., 2200"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Protein (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(goalsDraft?.protein_g ?? "")}
                  onChangeText={(v) => setGoalsDraft((g) => ({ ...g, protein_g: v }))}
                  placeholder="e.g., 160"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Carbs (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(goalsDraft?.carbs_g ?? "")}
                  onChangeText={(v) => setGoalsDraft((g) => ({ ...g, carbs_g: v }))}
                  placeholder="e.g., 220"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Fat (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(goalsDraft?.fat_g ?? "")}
                  onChangeText={(v) => setGoalsDraft((g) => ({ ...g, fat_g: v }))}
                  placeholder="e.g., 70"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Fiber (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(goalsDraft?.fiber_g ?? "")}
                  onChangeText={(v) => setGoalsDraft((g) => ({ ...g, fiber_g: v }))}
                  placeholder="e.g., 30"
                  placeholderTextColor="#666"
                />
              </View>

              <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                <TouchableOpacity style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]} onPress={() => setGoalsModal(false)}>
                  <Text style={styles.btnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.btn, { flex: 1 }]} onPress={() => upsertGoals(goalsDraft)}>
                  <Text style={styles.btnText}>Save</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal
          visible={coachProfileModal}
          transparent
          animationType="fade"
          onRequestClose={() => setCoachProfileModal(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.cardTitle}>Coach profile</Text>
              <Text style={styles.tiny}>Used for daily personalization (stored locally on this device).</Text>

              <View style={{ marginTop: 12 }}>
                <Text style={styles.label}>Primary goal</Text>
                <View style={styles.rowWrap}>
                  {["fat_loss", "recomposition", "lean_gain"].map((gk) => (
                    <TouchableOpacity
                      key={gk}
                      style={[styles.chip, coachProfileDraft?.goal_type === gk && styles.chipActive]}
                      onPress={() => setCoachProfileDraft((p) => ({ ...p, goal_type: gk }))}
                    >
                      <Text style={styles.chipText}>{gk}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={styles.label}>Diet style</Text>
                <View style={styles.rowWrap}>
                  {["veg", "non-veg", "vegan"].map((d) => (
                    <TouchableOpacity
                      key={d}
                      style={[styles.chip, coachProfileDraft?.diet_style === d && styles.chipActive]}
                      onPress={() => setCoachProfileDraft((p) => ({ ...p, diet_style: d }))}
                    >
                      <Text style={styles.chipText}>{d}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={styles.label}>Training days/week</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(coachProfileDraft?.training_days_per_week ?? "")}
                  onChangeText={(v) => setCoachProfileDraft((p) => ({ ...p, training_days_per_week: v }))}
                  placeholder="e.g., 3"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Typical training time</Text>
                <View style={styles.rowWrap}>
                  {["morning", "afternoon", "evening", "night", "variable"].map((t) => (
                    <TouchableOpacity
                      key={t}
                      style={[styles.chip, coachProfileDraft?.training_time === t && styles.chipActive]}
                      onPress={() => setCoachProfileDraft((p) => ({ ...p, training_time: t }))}
                    >
                      <Text style={styles.chipText}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={styles.label}>Coach style</Text>
                <View style={styles.rowWrap}>
                  {["supportive", "strict", "funny", "indian_coach"].map((t) => (
                    <TouchableOpacity
                      key={t}
                      style={[styles.chip, coachProfileDraft?.tone_preference === t && styles.chipActive]}
                      onPress={() => setCoachProfileDraft((p) => ({ ...p, tone_preference: t }))}
                    >
                      <Text style={styles.chipText}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => setCoachProfileModal(false)}
                >
                  <Text style={styles.btnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.btn, { flex: 1 }]} onPress={applyCoachProfile}>
                  <Text style={styles.btnText}>Save</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

</ScrollView>

      {/* CAMERA MODAL */}
      <Modal visible={camOpen} animationType="slide">
        <SafeAreaView style={styles.modalSafe}>
          <View style={styles.modalTop}>
            <TouchableOpacity style={styles.smallBtn} onPress={() => setCamOpen(false)}>
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Take a photo</Text>
            <View style={{ width: 70 }} />
          </View>

          <CameraView ref={camRef} style={styles.camera} facing="back" />

          <View style={styles.modalBottom}>
            <TouchableOpacity style={styles.captureBtn} onPress={takePhoto}>
              <Text style={styles.captureBtnText}>SNAP</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </Modal>

      {/* BARCODE MODAL */}
      <Modal visible={barcodeOpen} animationType="slide">
        <SafeAreaView style={styles.modalSafe}>
          <View style={styles.modalTop}>
            <TouchableOpacity style={styles.smallBtn} onPress={() => setBarcodeOpen(false)}>
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Scan barcode</Text>
            <View style={{ width: 70 }} />
          </View>

          <CameraView
            style={styles.camera}
            facing="back"
            barcodeScannerSettings={{
              barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"],
            }}
            onBarcodeScanned={barcodeBusy ? undefined : onBarcodeScanned}
          />

          <View style={styles.modalBottom}>
            <Text style={styles.tiny}>Point camera at barcode. It will auto-detect.</Text>
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000" },
  container: { padding: 16, gap: 12 },
  h1: { fontSize: 24, fontWeight: "800", color: "#fff" },
  p: { fontSize: 14, color: "#cfcfcf", lineHeight: 20 },
  tiny: { fontSize: 12, color: "#8c8c8c", lineHeight: 18 },
  muted: { fontSize: 12, color: "#bdbdbd", lineHeight: 18 },
  plan: { color: "#fff", fontWeight: "700" },

  topRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  row: { flexDirection: "row", gap: 10, marginTop: 10 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 10 },

  card: {
    backgroundColor: "#0b0b0b",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#1c1c1c",
    padding: 14,
  },
  cardTitle: { color: "#fff", fontWeight: "800", fontSize: 16 },
  big: { color: "#fff", fontWeight: "800", fontSize: 18, marginTop: 6 },

  input: {
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#222",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "#fff",
    marginTop: 8,
  },

  primaryBtn: {
    backgroundColor: "#2563eb",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
    flex: 1,
  },
  secondaryBtn: {
    backgroundColor: "#151515",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
  },
  btn: {
    backgroundColor: "#2563eb",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  btnText: { color: "#fff", fontWeight: "800" },
  label: { color: "#d7d7d7", marginTop: 8, fontSize: 13, fontWeight: "700" },

  // NEW: Google button
  googleBtn: {
    backgroundColor: "#151515",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#2a2a2a",
  },
  appleBtn: {
    backgroundColor: "#151515",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#2a2a2a",
  },

  // NEW: divider
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 14,
    marginBottom: 4,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: "#1e1e1e" },
  dividerText: { color: "#8c8c8c", fontSize: 12, fontWeight: "700" },

  smallBtn: {
    backgroundColor: "#151515",
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 12,
    alignItems: "center",
    flexShrink: 1,
  },
  smallBtnText: { color: "#fff", fontWeight: "700" },

  preview: { width: "100%", height: 220, borderRadius: 16, marginTop: 10 },
  previewEmpty: {
    width: "100%",
    height: 220,
    borderRadius: 16,
    marginTop: 10,
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#222",
    justifyContent: "center",
    alignItems: "center",
  },
  previewText: { color: "#777" },

  itemRow: { marginTop: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: "#161616" },
  itemName: { color: "#fff", fontWeight: "800" },
  itemMeta: { color: "#9c9c9c", marginTop: 2, fontSize: 12 },

  lockedBox: {
    marginTop: 10,
    backgroundColor: "#101010",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#222",
    padding: 12,
  },
  lockedTitle: { color: "#fff", fontWeight: "900", marginBottom: 6 },

  meter: {
    marginTop: 10,
    backgroundColor: "#0f0f0f",
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1c1c1c",
  },
  meterTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  meterLabel: { color: "#fff", fontWeight: "900" },
  meterValue: { color: "#fff", fontWeight: "800" },
  meterHelp: { color: "#9c9c9c", marginTop: 6, fontSize: 12, lineHeight: 18 },
  barOuter: { height: 10, backgroundColor: "#1a1a1a", borderRadius: 999, marginTop: 10, overflow: "hidden" },
  barFill: { height: 10, backgroundColor: "#22c55e", borderRadius: 999 },

  lockedTag: {
    color: "#fff",
    fontWeight: "800",
    backgroundColor: "#2a2a2a",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
  },

  manualRow: { marginTop: 10, flexDirection: "row", gap: 10, alignItems: "center" },
  manualInput: {
    flex: 1,
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#222",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "#fff",
  },

  histRow: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#151515" },
  histTitle: { color: "#fff", fontWeight: "800" },
  intelHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    flexWrap: "wrap",
    rowGap: 8,
    columnGap: 8,
  },
  intelHeaderActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-end",
    columnGap: 8,
    rowGap: 8,
    maxWidth: "100%",
  },
  intelSubline: { fontSize: 12, color: "#8ea0bf", marginTop: 4, lineHeight: 17 },
  fliUpdateBanner: {
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#305390",
    backgroundColor: "#0f1f37",
  },
  fliUpdateText: { color: "#cfe0ff", fontSize: 12, fontWeight: "700" },
  intelScoreRow: { marginTop: 10, flexDirection: "row", gap: 12, alignItems: "center" },
  scoreOrb: {
    width: 92,
    height: 92,
    borderRadius: 999,
    borderWidth: 3,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0f1218",
    shadowOpacity: 0.2,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  scoreOrbValue: { color: "#fff", fontSize: 28, fontWeight: "900", lineHeight: 32 },
  scoreOrbUnit: { color: "#9fb0cf", fontSize: 11, fontWeight: "800" },
  intelKicker: { color: "#d7e2ff", fontSize: 13, fontWeight: "800", marginBottom: 6 },
  intelBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  intelBadgeDot: { width: 7, height: 7, borderRadius: 99 },
  intelBadgeText: { fontSize: 12, fontWeight: "800" },
  intelProgressTrack: {
    marginTop: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: "#151d2b",
    overflow: "hidden",
  },
  intelProgressFill: { height: 8, borderRadius: 999 },
  intelTrendRow: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: 8,
    paddingHorizontal: 2,
  },
  intelTrendCol: { width: 36, alignItems: "center" },
  intelTrendBar: { width: 14, borderRadius: 999, marginBottom: 4 },
  intelTrendValue: { color: "#dce6ff", fontSize: 11, fontWeight: "800" },
  intelTrendLabel: { color: "#7f8aa1", fontSize: 10, marginTop: 2 },
  intelSignalGrid: { marginTop: 8, gap: 8 },
  intelSignalCard: {
    padding: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#263045",
    backgroundColor: "#0e131d",
  },
  intelSignalTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  intelSignalLabel: { color: "#e5edff", fontSize: 12, fontWeight: "800" },
  intelSignalPercent: { fontSize: 12, fontWeight: "900" },
  intelSignalTrack: {
    height: 7,
    borderRadius: 999,
    backgroundColor: "#182235",
    overflow: "hidden",
    marginTop: 6,
    marginBottom: 6,
  },
  intelSignalFill: { height: 7, borderRadius: 999 },
  intelToggleBtn: {
    marginTop: 10,
    alignSelf: "flex-start",
    backgroundColor: "#151515",
    borderWidth: 1,
    borderColor: "#2d3b57",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  lockedPreviewGrid: { marginTop: 10, gap: 8 },
  lockedPreviewTile: {
    height: 114,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#273247",
    backgroundColor: "#111827",
    overflow: "hidden",
  },
  lockedPreviewBg: {
    ...StyleSheet.absoluteFillObject,
    width: "100%",
    height: "100%",
    opacity: 0.8,
  },
  lockedPreviewGhost: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: 12,
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#111827",
  },
  lockedPreviewGhostLine: { height: 8, width: "38%", borderRadius: 999, backgroundColor: "#273247" },
  lockedPreviewGhostLineWide: { height: 10, width: "78%", borderRadius: 999, backgroundColor: "#2e3a52" },
  lockedPreviewGhostLineShort: { height: 8, width: "56%", borderRadius: 999, backgroundColor: "#273247" },
  lockedPreviewShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(5,8,14,0.60)",
  },
  lockedPreviewContent: {
    position: "absolute",
    left: 10,
    right: 10,
    bottom: 10,
    gap: 4,
  },
  lockedPreviewUnlock: {
    alignSelf: "flex-start",
    color: "#a5d8ff",
    fontSize: 10,
    fontWeight: "900",
    backgroundColor: "rgba(23,33,54,0.86)",
    borderColor: "#365081",
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  lockedPreviewTitle: { color: "#f3f7ff", fontSize: 14, fontWeight: "900" },
  lockedPreviewSubtitle: { color: "#c7d3ea", fontSize: 12, lineHeight: 16 },
  riskRow: {
    marginTop: 8,
    padding: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#262626",
    backgroundColor: "#111",
  },
  riskType: { color: "#fff", fontWeight: "800", fontSize: 12, marginBottom: 4 },
  actionBox: {
    marginTop: 8,
    padding: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#262626",
    backgroundColor: "#101010",
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#2a2a2a",
    backgroundColor: "#121212",
  },
  chipActive: {
    borderColor: "#3b82f6",
    backgroundColor: "#1b2c4f",
  },
  chipText: { color: "#e9e9e9", fontSize: 12, fontWeight: "700" },

  modalSafe: { flex: 1, backgroundColor: "#000" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.62)",
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
  },
  modalCard: {
    width: "100%",
    maxWidth: 460,
    backgroundColor: "#0d0d0d",
    borderWidth: 1,
    borderColor: "#262626",
    borderRadius: 18,
    padding: 14,
  },
  modalTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12 },
  modalTitle: { color: "#fff", fontWeight: "900", fontSize: 16 },
  camera: { flex: 1 },
  modalBottom: { padding: 12, paddingBottom: 48, backgroundColor: "#000" },
  captureBtn: {
    minWidth: 180,
    alignSelf: "center",
    backgroundColor: "#1e6dff",
    borderWidth: 1,
    borderColor: "#5ca2ff",
    borderRadius: 999,
    paddingHorizontal: 36,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  captureBtnText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "900",
    letterSpacing: 0.8,
  },

  link: {
    color: "#4da3ff",
    textDecorationLine: "underline",
    fontSize: 12,
    fontWeight: "700",
  },
});
