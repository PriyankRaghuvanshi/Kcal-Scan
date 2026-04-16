// bundle-stamp: 2026-03-10 — bump when verifying App Store / EAS ships latest JS
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  Alert,
  ActivityIndicator,
  AppState,
  FlatList,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TextInput,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Linking,
  Share,
  ToastAndroid,
  Keyboard,
} from "react-native";

import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import * as FileSystem from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

// OAuth helpers (Google)
import * as AuthSession from "expo-auth-session";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { LinearGradient } from "expo-linear-gradient";
import * as AppleAuthentication from "expo-apple-authentication";

import {
  normalizeHealthyPlacesResponse,
} from "./healthyNearbyUtils";
import { buildRemainingLine, buildWeeklyCoachSummaryLine } from "./utils/lunchAndWeeklyCoachUtils";
import {
  postMealDecisionEvent,
  postMealFeedback,
  buildDecisionEventPayload,
  buildMealFeedbackPayload,
} from "./personalLearningApi";
import { fetchRecipeSuggestions, postRecipeFeedback } from "./utils/recipeSuggestionsApi";
import MealFeedbackPrompt from "./MealFeedbackPrompt";
import {
  fetchSmartFoodAlertCandidates,
  buildSmartAlertFetchParams,
  requestSmartAlertPush,
} from "./smartAlertsApi";
import {
  getSmartAlertState,
  updateSmartAlertSettings,
  filterCandidatesForDisplay,
  getAlertId,
  recordAlertOpened,
  recordAlertDismissed,
} from "./smartAlertState";
import { SmartAlertCard } from "./components/SmartAlertCard";
import { SmartAlertInbox } from "./components/SmartAlertInbox";
import { SmartAlertSettings } from "./components/SmartAlertSettings";
import { HealthyNearbyMapScreen } from "./components/HealthyNearbyMapScreen";
import { HealthyNearbyDiscoverLayout } from "./components/HealthyNearbyDiscoverLayout";
import { HealthyPlaceListCard } from "./components/HealthyPlaceListCard";
import { PlaceDetailSheet } from "./components/PlaceDetailSheet";
import { HealthyNearbyDecisionShowcase } from "./components/HealthyNearbyDecisionShowcase";
import { AdminOpsDashboard } from "./components/AdminOpsDashboard";
import { ScanConfirmationChips } from "./components/ScanConfirmationChips";
import { ScanResultScreen } from "./components/ScanResultScreen";
import { BestOrderEvidenceBlock } from "./components/BestOrderEvidence";
import { LetsGoSetupModal } from "./components/LetsGoSetupModal";
import { GoalPlanCard } from "./components/GoalPlanCard";
import { JourneyCard } from "./components/JourneyCard";
import { DailyCoachCard } from "./components/DailyCoachCard";
import { WeeklyPlanReviewCard } from "./components/WeeklyPlanReviewCard";
import { PlanPaywallCard } from "./components/PlanPaywallCard";
import { VenueContributionSheet } from "./components/VenueContributionSheet";
import { HomeTodayHero } from "./components/HomeTodayHero";
import { RecipeSuggestionsRow } from "./components/RecipeSuggestionsRow";
import { SavedRecipesList } from "./components/SavedRecipesList";
import { spacing as tSpacing, colors as dt, radius as dr, shadows as dsh } from "./designTokens";
import { premium } from "./ui/premiumSystem";
import { hapticLight, layoutEaseInOut } from "./ui/feedback";
import {
  createGoalPlan,
  getGoalPlan,
  submitGoalCoachCheckIn,
  submitWeightEntry,
  submitPhotoEntry,
  getJourney,
  getGoalCoachDaily,
  getGoalCoachWeekly,
  getDailyActions,
  getWeeklyNextStepAction,
  ACTION_OPEN_HEALTHY_NEARBY,
  ACTION_OPEN_SCAN_CAMERA,
  ACTION_OPEN_SUPPLEMENT_SCAN,
  ACTION_OPEN_DAILY_SUMMARY,
  ACTION_OPEN_GOAL_PLAN,
  derivePreferredModeFromContext,
  preferredModeToFilterKey,
  trackGoalCoachActionClicked,
  trackGoalCoachDestinationOpened,
  trackGoalCoachActionCompleted,
  trackGoalCoachActionShown,
} from "./utils/goalCoachUtils";
import {
  buildHealthyNearbyContextKey,
  hasMaterialLocationChange,
  shouldApplyHealthyNearbyResponse,
} from "./utils/healthyNearbyRequestState";
import {
  createLaunchTracer,
  installGlobalErrorHandler,
  safeArray,
  safeGetSmartAlertPayload,
  safeObject,
  safeParseJson,
} from "./startupSafety";
import {
  requestPushPermissionsIfNeeded,
  getExpoPushTokenSafe,
  registerPushTokenWithBackend,
  unregisterPushTokenWithBackend,
  setupNotificationListeners,
  cleanupNotificationListeners,
  handleNotificationOpen,
  getPushPermissionStatus,
  loadPushRegistrationState,
  savePushRegistrationState,
  parseSmartAlertNotificationData,
} from "./pushNotifications";
import { parseSmartAlertDeepLink, resolveSmartAlertNavigationTarget } from "./deepLinkRouter";
import {
  initDeviceHealth,
  getDailyHealthContext,
  writeNutritionToDeviceHealth,
  writeWeightToDeviceHealth,
  isDeviceHealthAvailable,
} from "./utils/deviceHealth";

import * as WebBrowser from "expo-web-browser";
// RevenueCat
import Purchases from "react-native-purchases";


WebBrowser.maybeCompleteAuthSession();

// ===================== SUBSCRIPTION (App Review 3.1.2) =====================
const PRIVACY_URL = "https://sites.google.com/view/calorieclickai/privacy-policy";
const TERMS_URL = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/";

// Pricing note for App Review & international launch
const SUBSCRIPTION_PRICE_NOTE =
  Platform.OS === "android"
    ? "Prices are shown in Google Play and may vary by country or region."
    : "Prices are shown in the App Store and may vary by country or region.";

// Safe link open (avoids crash if URL invalid or Linking fails)
async function openURLSafe(url, fallbackMessage = "Could not open link.") {
  const u = String(url || "").trim();
  if (!u || !u.startsWith("http")) return;
  try {
    const can = await Linking.canOpenURL(u);
    if (can) await Linking.openURL(u);
    else if (fallbackMessage) Alert.alert("", fallbackMessage);
  } catch (e) {
    if (fallbackMessage) Alert.alert("", fallbackMessage);
  }
}


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

/** Rotating tips while scans run (large non-repeating deck). */
function _buildScanLoadingFacts() {
  const lead = [
    "Protein-forward meals",
    "High-fiber choices",
    "Balanced plates",
    "Portion-aware picks",
    "Lower-UPF options",
    "Hydration habits",
    "Slow-carb swaps",
    "Sleep-friendly dinners",
    "Lunch prep habits",
    "Recovery meals",
  ];
  const action = [
    "can improve satiety",
    "often reduce afternoon crashes",
    "help steady blood sugar swings",
    "can lower late-night hunger",
    "usually improve consistency",
    "can make calorie targets easier",
    "help protect muscle during cuts",
    "often improve food quality scores",
    "can reduce impulse snacking",
    "help improve weekly outcomes",
  ];
  const suffix = [
    "over 2-4 weeks.",
    "when repeated most days.",
    "with realistic portions.",
    "without needing perfect eating.",
    "even with takeout meals.",
    "when paired with hydration.",
    "for most goal-focused plans.",
    "with simple repeatable routines.",
    "for many fat-loss workflows.",
    "when combined with protein timing.",
  ];
  const out = [];
  for (let i = 0; i < lead.length; i++) {
    for (let j = 0; j < action.length; j++) {
      out.push(`${lead[i]} ${action[j]} ${suffix[(i + j) % suffix.length]}`);
    }
  }
  return out;
}
const SCAN_LOADING_FACTS = _buildScanLoadingFacts();

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
const MEAL_MEMORY_KEY = "kcal_meal_memory_v1";
const mealMemoryKey = (uid) => `${MEAL_MEMORY_KEY}:${uid}`;
const GOALS_KEY = "kcal_user_goals_v1";
const goalsKey = (uid) => `${GOALS_KEY}:${uid}`;
const DAILY_COACH_KEY = "kcal_daily_coach_v1";
const dailyCoachKey = (uid, day) => `${DAILY_COACH_KEY}:${uid}:${day}`;
const COACH_PROFILE_KEY = "kcal_coach_profile_v1";
const coachProfileKey = (uid) => `${COACH_PROFILE_KEY}:${uid}`;
const COACH_CHAT_HISTORY_KEY = "kcal_coach_chat_history_v1";
const coachChatHistoryKey = (uid, day) => `${COACH_CHAT_HISTORY_KEY}:${uid}:${day}`;
const COACH_VOICE_MEMORY_KEY = "kcal_coach_voice_memory_v1";
const coachVoiceMemoryKey = (uid, day) => `${COACH_VOICE_MEMORY_KEY}:${uid}:${day}`;
const UPGRADE_NUDGE_KEY = "kcal_upgrade_nudge_v1";
const upgradeNudgeKey = (uid) => `${UPGRADE_NUDGE_KEY}:${uid}`;
const POST_SCAN_BANNER_KEY = "kcal_post_scan_upgrade_banner_dismissed_v1";
const postScanBannerKey = (uid) => `${POST_SCAN_BANNER_KEY}:${uid}`;
const COACH_FEEDBACK_QUEUE_KEY = "kcal_coach_feedback_queue_v1";
const coachFeedbackQueueKey = (uid) => `${COACH_FEEDBACK_QUEUE_KEY}:${uid}`;
const WEEKLY_COACH_CHOICES_KEY = "kcal_weekly_coach_choices_v1";
const weeklyCoachChoicesKey = (uid) => `${WEEKLY_COACH_CHOICES_KEY}:${uid}`;
const GOAL_PLAN_CACHE_KEY = "kcal_goal_plan_cache_v1";
const goalPlanCacheKey = (uid) => `${GOAL_PLAN_CACHE_KEY}:${uid}`;

const RC_IOS_KEY =
  process.env.EXPO_PUBLIC_RC_IOS_KEY ||
  Constants.expoConfig?.extra?.REVENUECAT_IOS_API_KEY ||
  "";
const RC_ANDROID_KEY =
  process.env.EXPO_PUBLIC_RC_ANDROID_KEY ||
  Constants.expoConfig?.extra?.REVENUECAT_ANDROID_API_KEY ||
  "goog_prIetTCSFiELCySmPqvheMMqbqi";
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";

function sanitizeHistoryEntries(rows) {
  return safeArray(rows)
    .filter((row) => row && typeof row === "object")
    .slice(0, MAX_HISTORY);
}

function resolvedOfferingId() {
  const fromExtra = Constants.expoConfig?.extra?.REVENUECAT_OFFERING;
  return String(fromExtra || OFFERING_ID || "main").trim() || "main";
}

/** RevenueCat can expose packages on `availablePackages` and/or duration slots (e.g. monthly). */
function packagesFromOffering(offering) {
  if (!offering || typeof offering !== "object") return [];
  const out = [];
  const seen = new Set();
  const push = (p) => {
    if (!p || typeof p !== "object") return;
    const id = String(p.identifier || p.product?.identifier || "").trim();
    const key = id || `__${seen.size}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(p);
  };
  if (Array.isArray(offering.availablePackages)) {
    offering.availablePackages.forEach(push);
  }
  for (const k of ["lifetime", "annual", "sixMonth", "threeMonth", "twoMonth", "monthly", "weekly"]) {
    push(offering[k]);
  }
  return out;
}
const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

function packageMatchesEntitlement(pkg, entitlement) {
  const key = String(entitlement || "").trim().toLowerCase();
  const identifiers = [
    pkg?.identifier,
    pkg?.product?.identifier,
    pkg?.product?.productIdentifier,
  ]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean);
  // Play product IDs use truncated names: advance_monthly, infinit_monthly.
  // Map app entitlements to all known product-id substrings.
  const aliases =
    key === "advanced"
      ? ["advanced", "advance"]
      : key === "infinite"
        ? ["infinite", "infinit"]
        : [key];
  return identifiers.some((identifier) => aliases.some((alias) => identifier.includes(alias)));
}

function getActiveOffering(offeringsObj) {
  if (!offeringsObj || typeof offeringsObj !== "object") return null;
  const oid = resolvedOfferingId();
  const allRaw = offeringsObj.all;
  const all = typeof allRaw === "object" && allRaw !== null ? allRaw : {};
  const candidates = [];
  if (offeringsObj.current) candidates.push(offeringsObj.current);
  if (all[oid]) candidates.push(all[oid]);
  for (const k of Object.keys(all)) {
    const o = all[k];
    if (o && !candidates.includes(o)) candidates.push(o);
  }
  for (const o of candidates) {
    if (o && packagesFromOffering(o).length > 0) return o;
  }
  return candidates[0] || null;
}

async function loadOfferingsWithRetry(maxAttempts = 6) {
  let last = await Purchases.getOfferings();
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const active = getActiveOffering(last);
    if (active && packagesFromOffering(active).length > 0) break;
    await new Promise((r) => setTimeout(r, 300 * (attempt + 1)));
    last = await Purchases.getOfferings();
  }
  return last;
}

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
  food_preferences: [],
  goal_reminders: [],
  // Extra dietary + allergen filters applied to restaurant item recommendations.
  //   dietary_restrictions: subset of ["halal", "gluten_free"] (vegetarian/vegan
  //     live in diet_style already — no need to duplicate here).
  //   allergen_exclude: subset of ["nuts","dairy","gluten","soy","shellfish","egg","sesame"].
  dietary_restrictions: [],
  allergen_exclude: [],
};
const DIETARY_RESTRICTION_OPTIONS = ["halal", "gluten_free"];
const ALLERGEN_EXCLUDE_OPTIONS = ["nuts", "dairy", "gluten", "soy", "shellfish", "egg", "sesame"];
const SUPPLEMENT_TOTAL_STEPS = 4;
const SUPPLEMENT_PROCESSING_CHECKS = [
  "Checking barcode registry",
  "Validating batch structure",
  "Analyzing nutrition panel consistency",
  "Comparing ingredient patterns",
];
const SUPPLEMENT_LEGAL_NOTE =
  "This authenticity confidence score is based on structural and pattern analysis. It is not a definitive determination of product genuineness. For confirmation, contact the manufacturer.";
const DEFAULT_HEALTHY_RADIUS_M = 2000;
const WIDER_SEARCH_RADIUS_M = 8000;
const SUPPLEMENT_REPORT_REASONS = [
  { key: "packaging_differs", label: "Packaging looks different" },
  { key: "taste_texture_unusual", label: "Taste/texture unusual" },
  { key: "batch_not_recognized", label: "Batch not recognized" },
  { key: "other", label: "Other" },
];

// ===================== HELPERS =====================
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function finiteNumOrNull(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
/** Device-local time-of-day greeting (never stale — always uses current clock). */
function localGreeting() {
  const h = new Date().getHours();
  if (h >= 5 && h <= 11) return "Good morning.";
  if (h >= 12 && h <= 16) return "Good afternoon.";
  if (h >= 17 && h <= 21) return "Good evening.";
  return "Good night.";
}
function getDeviceTimeZone() {
  try {
    const tz = Intl?.DateTimeFormat?.().resolvedOptions?.().timeZone;
    return typeof tz === "string" && tz.trim() ? tz.trim() : "";
  } catch {
    return "";
  }
}
// ===================== MEAL MEMORY =====================
function mealFingerprint(items) {
  if (!Array.isArray(items) || !items.length) return "";
  const names = items
    .map((it) => String(it?.name || it?.item || "").trim().toLowerCase())
    .filter(Boolean);
  if (!names.length) return "";
  return [...new Set(names)].sort().join("|");
}
function mealLabel(items) {
  if (!Array.isArray(items) || !items.length) return "meal";
  const names = items
    .map((it) => String(it?.name || it?.item || "").trim())
    .filter(Boolean)
    .slice(0, 4);
  if (!names.length) return "meal";
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
async function loadMealMemory(uid) {
  if (!uid) return {};
  try {
    const raw = await AsyncStorage.getItem(mealMemoryKey(uid));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}
async function recordMealToMemory(uid, items) {
  if (!uid) return;
  const fp = mealFingerprint(items);
  if (!fp) return;
  const mem = await loadMealMemory(uid);
  const existing = mem[fp] || { label: mealLabel(items), count: 0, lastTs: "" };
  existing.count = (existing.count || 0) + 1;
  existing.lastTs = new Date().toISOString();
  existing.label = mealLabel(items);
  mem[fp] = existing;
  const sorted = Object.entries(mem).sort((a, b) => b[1].count - a[1].count).slice(0, 30);
  try {
    await AsyncStorage.setItem(mealMemoryKey(uid), JSON.stringify(Object.fromEntries(sorted)));
  } catch {}
}
function findMealInMemory(mem, items) {
  if (!mem || typeof mem !== "object") return null;
  const fp = mealFingerprint(items);
  if (!fp) return null;
  const hit = mem[fp];
  if (hit && hit.count >= 1) return { label: hit.label, count: hit.count };
  return null;
}
function frequentMealSummaries(mem) {
  if (!mem || typeof mem !== "object") return [];
  return Object.entries(mem)
    .filter(([, v]) => v.count >= 2)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 10)
    .map(([fp, v]) => ({ fingerprint: fp, label: v.label, count: v.count }));
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
function localWeekStartISO() {
  const d = new Date();
  const dayOfWeek = d.getDay();
  const diff = d.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1);
  const monday = new Date(d);
  monday.setDate(diff);
  const y = monday.getFullYear();
  const m = String(monday.getMonth() + 1).padStart(2, "0");
  const day = String(monday.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
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
  const rawFoods = Array.isArray(src.food_preferences) ? src.food_preferences : [];
  const rawGoals = Array.isArray(src.goal_reminders) ? src.goal_reminders : [];
  const food_preferences = [];
  const seenF = new Set();
  for (const x of rawFoods) {
    const s = String(x || "").trim();
    if (!s || s.length > 80) continue;
    const k = s.toLowerCase();
    if (seenF.has(k)) continue;
    seenF.add(k);
    food_preferences.push(s);
    if (food_preferences.length >= 12) break;
  }
  const goal_reminders = [];
  const seenG = new Set();
  for (const x of rawGoals) {
    const s = String(x || "").trim();
    if (!s || s.length > 120) continue;
    const k = s.toLowerCase();
    if (seenG.has(k)) continue;
    seenG.add(k);
    goal_reminders.push(s);
    if (goal_reminders.length >= 8) break;
  }
  const rawRestrict = Array.isArray(src.dietary_restrictions) ? src.dietary_restrictions : [];
  const rawAllergens = Array.isArray(src.allergen_exclude) ? src.allergen_exclude : [];
  const dietary_restrictions = Array.from(
    new Set(rawRestrict.map((v) => String(v || "").trim().toLowerCase()).filter((v) => DIETARY_RESTRICTION_OPTIONS.includes(v)))
  );
  const allergen_exclude = Array.from(
    new Set(rawAllergens.map((v) => String(v || "").trim().toLowerCase()).filter((v) => ALLERGEN_EXCLUDE_OPTIONS.includes(v)))
  );
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
    food_preferences,
    goal_reminders,
    dietary_restrictions,
    allergen_exclude,
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
function dismissKeyboardSafe() {
  try {
    Keyboard.dismiss();
  } catch {}
}
function closeBooleanStateSafely(setter) {
  dismissKeyboardSafe();
  setTimeout(() => {
    try {
      setter(false);
    } catch {}
  }, 60);
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
function supplementScoreTone(score) {
  const s = Math.round(num(score));
  if (s >= 80) return { label: "High Confidence", color: "#22c55e", bg: "#0f2617" };
  if (s >= 60) return { label: "Moderate", color: "#f59e0b", bg: "#2d210b" };
  if (s >= 40) return { label: "Low Confidence", color: "#fb923c", bg: "#2f1a0d" };
  return { label: "High Risk", color: "#ef4444", bg: "#2b1212" };
}
function supplementRiskTone(level) {
  const tag = String(level || "").toLowerCase();
  if (tag === "ok") return { icon: "✔", color: "#22c55e" };
  if (tag === "warn") return { icon: "⚠", color: "#f59e0b" };
  return { icon: "✖", color: "#ef4444" };
}
function healthyPlaceTone(score) {
  const s = Math.max(1, Math.min(10, num(score)));
  if (s >= 8) return { color: "#22c55e", badge: "Excellent" };
  if (s >= 6.5) return { color: "#84cc16", badge: "Good" };
  if (s >= 5) return { color: "#f59e0b", badge: "Moderate" };
  return { color: "#ef4444", badge: "Lower" };
}
function normalizePlaceNameKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}
function healthyPlaceCoordinateKey(lat, lng) {
  const a = num(lat);
  const b = num(lng);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return "";
  return `${a.toFixed(4)},${b.toFixed(4)}`;
}
function healthyPlaceStableId(place, idx = 0) {
  const raw = String(place?.place_id || place?.id || "").trim();
  if (raw) return raw;
  const slug = String(place?.place_name || place?.name || "place")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const coord = healthyPlaceCoordinateKey(place?.lat, place?.lng)
    .replace(/,/g, "-")
    .replace(/\./g, "_");
  if (coord) return `${slug || "place"}-${coord}`;
  return `${slug || "place"}-${idx}`;
}
function findMatchingHealthyPlaceIndex(target, places) {
  const rows = Array.isArray(places) ? places.filter((x) => x && typeof x === "object") : [];
  if (!rows.length || !target || typeof target !== "object") return -1;

  const targetId = String(target?.place_id || target?.id || target?.tracking?.place_id || "").trim();
  if (targetId) {
    const byId = rows.findIndex((row) => String(row?.place_id || row?.id || "").trim() === targetId);
    if (byId >= 0) return byId;
  }

  const targetName = normalizePlaceNameKey(target?.place_name || target?.name);
  const targetLat = num(target?.place_lat ?? target?.lat);
  const targetLng = num(target?.place_lng ?? target?.lng);
  const targetCoordKey = healthyPlaceCoordinateKey(targetLat, targetLng);

  let bestIdx = -1;
  let bestScore = -1;

  rows.forEach((row, idx) => {
    let score = 0;
    const rowName = normalizePlaceNameKey(row?.place_name || row?.name);
    if (targetName && rowName) {
      if (targetName === rowName) score += 6;
      else if (targetName.includes(rowName) || rowName.includes(targetName)) score += 4;
    }

    const rowLat = num(row?.lat);
    const rowLng = num(row?.lng);
    const rowCoordKey = healthyPlaceCoordinateKey(rowLat, rowLng);
    if (targetCoordKey && rowCoordKey && targetCoordKey === rowCoordKey) {
      score += 7;
    } else {
      const km = haversineKm(targetLat, targetLng, rowLat, rowLng);
      if (Number.isFinite(km)) {
        const meters = km * 1000;
        if (meters <= 120) score += 6;
        else if (meters <= 260) score += 4;
        else if (meters <= 500) score += 2;
      }
    }

    if (score > bestScore) {
      bestScore = score;
      bestIdx = idx;
    }
  });

  return bestScore >= 4 ? bestIdx : -1;
}
function findMatchingLunchCard(place, cards) {
  const list = Array.isArray(cards) ? cards.filter((x) => x && typeof x === "object") : [];
  if (!place || typeof place !== "object" || !list.length) return null;
  const idx = findMatchingHealthyPlaceIndex(place, list);
  return idx >= 0 ? list[idx] : null;
}
function healthyPlaceScore100(place) {
  const display = num(place?.display_rank_score_100);
  if (Number.isFinite(display)) return display;
  const v = num(place?.health_score_100);
  if (Number.isFinite(v)) return v;
  const h = num(place?.health_score);
  return Number.isFinite(h) ? h * 10 : 0;
}

function healthyPlaceBand(place) {
  const explicit = String(place?.score_band || "").trim().toLowerCase();
  if (explicit === "high" || explicit === "medium" || explicit === "low") return explicit;
  const score100 = healthyPlaceScore100(place);
  if (score100 >= 80) return "high";
  if (score100 >= 60) return "medium";
  return "low";
}
function healthyMapPinTone(place) {
  const explicit = String(place?.map_pin_color || "").trim().toLowerCase();
  if (explicit === "green") return { color: "#22c55e", badge: "Best" };
  if (explicit === "yellow") return { color: "#f59e0b", badge: "Okay" };
  if (explicit === "red") return { color: "#ef4444", badge: "Hard" };

  const band = healthyPlaceBand(place);
  if (band === "high") return { color: "#22c55e", badge: "Best" };
  if (band === "medium") return { color: "#f59e0b", badge: "Okay" };
  return { color: "#ef4444", badge: "Hard" };
}
function healthyPlaceBadges(place) {
  const source = Array.isArray(place?.badges)
    ? place.badges
    : Array.isArray(place?.recommended_badges)
    ? place.recommended_badges
    : [];
  const out = source.map((x) => String(x || "").trim()).filter(Boolean);
  if (place?.fit_for_today === true && !out.includes("Fits Today's Macros")) out.unshift("Fits Today's Macros");
  if ((place?.cut_friendly || place?.fat_loss_friendly) && !out.includes("Cut Friendly")) out.push("Cut Friendly");
  return Array.from(new Set(out)).slice(0, 3);
}
function filterHealthyPlacesForMap(places, filterKey) {
  const rows = Array.isArray(places) ? places.filter((x) => x && typeof x === "object") : [];
  const key = String(filterKey || "all").trim().toLowerCase();
  if (key === "high_protein") return rows.filter((x) => num(x?.estimated_protein_g) >= 30);
  if (key === "under_600") return rows.filter((x) => num(x?.estimated_calories) > 0 && num(x?.estimated_calories) <= 600);
  if (key === "fits_today") return rows.filter((x) => x?.fit_for_today === true || String(x?.decision_today || "").toUpperCase() === "YES");
  if (key === "cut_friendly") return rows.filter((x) => Boolean(x?.cut_friendly || x?.fat_loss_friendly));
  if (key === "best_right_now") {
    const scored = rows.filter((x) => {
      const rank = num(x?.map_rank);
      const score100 = healthyPlaceScore100(x);
      return (Number.isFinite(rank) && rank <= 5) || score100 >= 60;
    });
    return scored.length ? scored : rows.slice(0, 5);
  }
  return rows;
}
function haversineKm(lat1, lng1, lat2, lng2) {
  const a1 = num(lat1);
  const o1 = num(lng1);
  const a2 = num(lat2);
  const o2 = num(lng2);
  if (!Number.isFinite(a1) || !Number.isFinite(o1) || !Number.isFinite(a2) || !Number.isFinite(o2)) return null;
  const r = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(a2 - a1);
  const dLng = toRad(o2 - o1);
  const s1 = Math.sin(dLat / 2) ** 2;
  const s2 = Math.cos(toRad(a1)) * Math.cos(toRad(a2)) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(s1 + s2), Math.sqrt(1 - (s1 + s2)));
  return r * c;
}
function buildHealthyMapPoints(places, center, width = 320, height = 210) {
  const cx = num(center?.lat);
  const cy = num(center?.lng);
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) return [];
  const list = Array.isArray(places) ? places.filter((p) => p && Number.isFinite(num(p?.lat)) && Number.isFinite(num(p?.lng))) : [];
  if (!list.length) return [];

  const centerLatRad = (cx * Math.PI) / 180;
  const vectors = list.map((place) => {
    const lat = num(place?.lat);
    const lng = num(place?.lng);
    const dy = (lat - cx) * 110540; // meters north/south
    const dx = (lng - cy) * 111320 * Math.cos(centerLatRad); // meters east/west
    return { place, dx, dy };
  });
  const maxX = Math.max(200, ...vectors.map((v) => Math.abs(v.dx)));
  const maxY = Math.max(200, ...vectors.map((v) => Math.abs(v.dy)));
  const pad = 16;
  const halfW = Math.max(100, width / 2);
  const halfH = Math.max(80, height / 2);
  const maxDrawX = Math.max(10, halfW - pad);
  const maxDrawY = Math.max(10, halfH - pad);

  return vectors.map((v, idx) => {
    const x = halfW + (v.dx / maxX) * maxDrawX;
    const y = halfH - (v.dy / maxY) * maxDrawY;
    return {
      key: healthyPlaceStableId(v.place, idx),
      x: Math.max(pad, Math.min(width - pad, x)),
      y: Math.max(pad, Math.min(height - pad, y)),
      place: v.place,
      distance_km: haversineKm(cx, cy, v.place?.lat, v.place?.lng),
    };
  });
}
function buildSupplementBreakdown(result) {
  const riskFlags = Array.isArray(result?.risk_flags)
    ? result.risk_flags.map((x) => String(x || "").trim().toLowerCase())
    : [];
  const flags = new Set(riskFlags);
  const hasBatch = Boolean(String(result?.batch_number || "").trim());
  const communityCount = Number(result?.scan_count ?? result?.community_scan_count);
  const communityKnown = Number.isFinite(communityCount);
  const communityMature = communityKnown && communityCount >= 8;

  return [
    flags.has("barcode_checksum_invalid") || flags.has("barcode_not_found_public_db") || flags.has("barcode_brand_mismatch")
      ? { key: "barcode", level: "bad", text: "Barcode checks failed against checksum/public registry signals." }
      : flags.has("barcode_missing") || flags.has("barcode_invalid_format")
      ? { key: "barcode", level: "warn", text: "Barcode is missing or not in a valid GTIN format." }
      : { key: "barcode", level: "ok", text: "Barcode structure passes checksum and registry plausibility checks." },
    flags.has("gs1_prefix_mismatch_region")
      ? { key: "gs1", level: "bad", text: "GS1 prefix plausibility check shows region mismatch." }
      : flags.has("gs1_prefix_unknown")
      ? { key: "gs1", level: "warn", text: "GS1 prefix plausibility check is inconclusive for this barcode." }
      : { key: "gs1", level: "ok", text: "GS1 prefix plausibility check passed." },
    flags.has("mfr_verified_company_mismatch")
      ? { key: "mfr_registry", level: "bad", text: "Manufacturer registry check: Mismatch." }
      : flags.has("mfr_verified_company_match")
      ? { key: "mfr_registry", level: "ok", text: "Manufacturer registry check: Match." }
      : flags.has("mfr_verification_not_found")
      ? { key: "mfr_registry", level: "warn", text: "Manufacturer registry check: No registry match found." }
      : { key: "mfr_registry", level: "warn", text: "Manufacturer registry check: Unavailable." },
    flags.has("batch_format_mismatch")
      ? { key: "batch", level: "bad", text: "Batch format differs from expected structure." }
      : hasBatch
      ? { key: "batch", level: "ok", text: "Batch format appears structurally valid." }
      : { key: "batch", level: "warn", text: "Batch code not provided; structural validation is limited." },
    flags.has("batch_pattern_unseen")
      ? { key: "batch_pattern", level: "warn", text: "Batch pattern not seen in prior brand scans." }
      : { key: "batch_pattern", level: "ok", text: "Batch pattern aligns with observed brand formats." },
    flags.has("packaging_phrase_missing")
      ? { key: "packaging", level: "warn", text: "Packaging phrase consistency check found missing expected markers." }
      : { key: "packaging", level: "ok", text: "Packaging phrase consistency check passed." },
    flags.has("batch_anomaly_macro_outlier") || flags.has("batch_anomaly_region_outlier") || flags.has("community_flagged_batch")
      ? { key: "community", level: "warn", text: "Batch community pattern check found an outlier signal in shared scan trends." }
      : communityMature
      ? { key: "community", level: "ok", text: "Batch community pattern check is stable for this region." }
      : { key: "community", level: "warn", text: "Batch community pattern check: Not enough community data yet." },
    flags.has("nutrition_kcal_mismatch") || flags.has("nutrition_protein_implausible")
      ? { key: "nutrition_math", level: "bad", text: "Nutrition math consistency check found a label inconsistency." }
      : flags.has("possible_protein_spiking")
      ? { key: "nutrition_math", level: "warn", text: "Nutrition math consistency check suggests manual review." }
      : { key: "nutrition_math", level: "ok", text: "Nutrition math consistency check passed." },
    flags.has("seal_missing")
      ? { key: "seal", level: "warn", text: "Seal verification proof mode is on but seal evidence is missing." }
      : { key: "seal", level: "ok", text: "Seal verification signal is available or not required." },
  ];
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
  const src = raw && typeof raw === "object" ? raw : {};
  return {
    fiber_g: num(src.fiber_g ?? src.fiber),
    sugar_g: num(src.sugar_g),
    sodium_mg: num(src.sodium_mg),
    vitamin_d_ug: num(src.vitamin_d_ug ?? src.vitamin_d_mcg),
    vitamin_b12_ug: num(src.vitamin_b12_ug ?? src.vitamin_b12_mcg),
    iron_mg: num(src.iron_mg),
    magnesium_mg: num(src.magnesium_mg),
    calcium_mg: num(src.calcium_mg),
    potassium_mg: num(src.potassium_mg),
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

function sleepMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Number(ms) || 0)));
}
function shuffleArray(list) {
  const arr = Array.isArray(list) ? [...list] : [];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const t = arr[i];
    arr[i] = arr[j];
    arr[j] = t;
  }
  return arr;
}
function normalizeRerunPatch(patch, editableItems = []) {
  const src = patch && typeof patch === "object" ? patch : {};
  const out = { ...src };
  const firstItemId = String(editableItems?.[0]?.item_id || "").trim();
  const findCandidateName = (itemId, candidateIndex) => {
    const idx = Number(candidateIndex);
    if (!Number.isFinite(idx) || idx < 0) return "";
    const targetId = String(itemId || "").trim();
    const item = (editableItems || []).find((x) => String(x?.item_id || "").trim() === targetId);
    if (!item || !Array.isArray(item?.candidate_alternatives)) return "";
    return String(item.candidate_alternatives[idx] || "").trim();
  };
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
    out.set_cooking_method = { item_id: fallbackItemId || "", method: methodValue };
  }

  const oilRaw = src?.set_oil_added_tsp;

  if (oilRaw != null) {
    if (typeof oilRaw === "number" || typeof oilRaw === "string") {
      const tsp = Math.max(0, num(oilRaw));
      out.set_oil_added_tsp = { item_id: fallbackItemId || "", tsp };
    } else if (oilRaw && typeof oilRaw === "object") {
      const tsp = Math.max(0, num(oilRaw?.tsp));
      const itemId = String(oilRaw?.item_id || fallbackItemId || "").trim();
      out.set_oil_added_tsp = { item_id: itemId || "", tsp };
    }
  }

  const swapRaw = src?.swap_item;
  if (swapRaw != null) {
    if (typeof swapRaw === "string") {
      const newName = String(swapRaw || "").trim();
      if (newName) {
        out.swap_item = { item_id: fallbackItemId || "", new_name: newName };
      }
    } else if (swapRaw && typeof swapRaw === "object") {
      const newName = String(swapRaw?.new_name || "").trim();
      if (newName) {
        const itemId = String(swapRaw?.item_id || fallbackItemId || "").trim();
        out.swap_item = { item_id: itemId || "", new_name: newName };
      }
    }
  }

  const swapCandidateRaw = src?.swap_candidate;
  if (swapCandidateRaw && typeof swapCandidateRaw === "object") {
    const itemId = String(swapCandidateRaw?.item_id || fallbackItemId || "").trim();
    const candidateNameDirect = String(
      swapCandidateRaw?.candidate_name || swapCandidateRaw?.new_name || swapCandidateRaw?.to_name || ""
    ).trim();
    const candidateNameResolved =
      candidateNameDirect || findCandidateName(itemId, swapCandidateRaw?.candidate_index);
    if (candidateNameResolved) {
      out.swap_item = { item_id: itemId || "", new_name: candidateNameResolved };
    } else {
      out.swap_candidate = {
        item_id: itemId || "",
        candidate_index: Number.isFinite(Number(swapCandidateRaw?.candidate_index))
          ? Number(swapCandidateRaw?.candidate_index)
          : 0,
      };
    }
  }

  const portionRaw = src?.portion_multiplier;
  if (portionRaw != null) {
    if (typeof portionRaw === "number" || typeof portionRaw === "string") {
      const multiplier = Math.max(0.3, Math.min(3, num(portionRaw)));
      out.portion_multiplier = { item_id: fallbackItemId || "", multiplier };
    } else if (portionRaw && typeof portionRaw === "object") {
      const multiplier = Math.max(0.3, Math.min(3, num(portionRaw?.multiplier)));
      const itemId = String(portionRaw?.item_id || fallbackItemId || "").trim();
      out.portion_multiplier = { item_id: itemId || "", multiplier };
    }
  }
  const gramsRaw = src?.set_item_grams;
  if (gramsRaw != null) {
    if (typeof gramsRaw === "number" || typeof gramsRaw === "string") {
      const grams = Math.max(0, num(gramsRaw));
      out.set_item_grams = { item_id: fallbackItemId || "", grams };
    } else if (gramsRaw && typeof gramsRaw === "object") {
      const grams = Math.max(0, num(gramsRaw?.grams));
      const itemId = String(gramsRaw?.item_id || fallbackItemId || "").trim();
      out.set_item_grams = { item_id: itemId || "", grams };
    }
  }
  if (Array.isArray(src?.clarifying_answers)) {
    out.clarifying_answers = src.clarifying_answers.map((a) => {
      if (!(typeof a === "object" && a && ("key" in a || "value" in a))) return null;
      const row = { key: String(a.key || "").trim(), value: String(a.value || "").trim() };
      const ic = String(a.ingredient_context || "").trim();
      if (ic) row.ingredient_context = ic;
      return row;
    }).filter(Boolean);
  }
  if (src?.macro_override && typeof src.macro_override === "object") {
    const protein_g = Math.max(0, num(src.macro_override?.protein_g));
    const carbs_g = Math.max(0, num(src.macro_override?.carbs_g));
    const fat_g = Math.max(0, num(src.macro_override?.fat_g));
    out.macro_override = { protein_g, carbs_g, fat_g };
  }
  return out;
}
function rerunPatchToActions(patch) {
  const src = patch && typeof patch === "object" ? patch : {};
  const actions = [];
  if (src?.set_oil_added_tsp && typeof src.set_oil_added_tsp === "object") {
    actions.push({
      type: "set_oil_added_tsp",
      item_id: String(src.set_oil_added_tsp?.item_id || "").trim(),
      tsp: num(src.set_oil_added_tsp?.tsp),
    });
  }
  if (src?.set_cooking_method && typeof src.set_cooking_method === "object") {
    actions.push({
      type: "set_cooking_method",
      item_id: String(src.set_cooking_method?.item_id || "").trim(),
      method: String(src.set_cooking_method?.method || "").trim().toLowerCase(),
    });
  }
  if (src?.swap_candidate && typeof src.swap_candidate === "object") {
    const itemId = String(src.swap_candidate?.item_id || "").trim();
    if (itemId) {
      const a = { type: "swap_candidate", item_id: itemId };
      if (src.swap_candidate?.candidate_index != null && Number.isFinite(Number(src.swap_candidate?.candidate_index))) {
        a.candidate_index = Number(src.swap_candidate?.candidate_index);
      }
      if (String(src.swap_candidate?.candidate_name || "").trim()) {
        a.candidate_name = String(src.swap_candidate?.candidate_name || "").trim();
      }
      actions.push(a);
    }
  }
  if (src?.swap_item && typeof src.swap_item === "object") {
    actions.push({
      type: "swap_item",
      item_id: String(src.swap_item?.item_id || "").trim(),
      new_name: String(src.swap_item?.new_name || "").trim(),
    });
  }
  if (src?.portion_multiplier && typeof src.portion_multiplier === "object") {
    actions.push({
      type: "set_portion_multiplier",
      item_id: String(src.portion_multiplier?.item_id || "").trim(),
      multiplier: num(src.portion_multiplier?.multiplier),
    });
  }
  if (String(src?.clarifying_answer || "").trim()) {
    actions.push({
      type: "clarifying_answer",
      value: String(src.clarifying_answer || "").trim(),
    });
  }
  if (src?.set_item_grams && typeof src.set_item_grams === "object") {
    actions.push({
      type: "set_item_grams",
      item_id: String(src.set_item_grams?.item_id || "").trim(),
      grams: num(src.set_item_grams?.grams),
    });
  }
  if (src?.macro_override && typeof src.macro_override === "object") {
    actions.push({
      type: "set_macro_override",
      item_id: String(src.macro_override?.item_id || "").trim(),
      protein_g: num(src.macro_override?.protein_g),
      carbs_g: num(src.macro_override?.carbs_g),
      fat_g: num(src.macro_override?.fat_g),
    });
  }
  if (Array.isArray(src?.clarifying_answers) && src.clarifying_answers.length) {
    actions.push({ type: "clarifying_answers", clarifying_answers: src.clarifying_answers });
  }
  return actions;
}
function normalizeAnalyzeResult(data) {
  const src = data && typeof data === "object" ? data : {};
  const rawKcal = num(src.total_kcal ?? src.totals?.kcal ?? src.totals?.total_kcal);
  const totalKcal = Number.isFinite(rawKcal) ? rawKcal : (src.total_kcal ?? src.totals?.kcal ?? src.totals?.total_kcal);
  const totals = src.totals && typeof src.totals === "object" ? { ...src.totals } : {};
  if (Number.isFinite(totalKcal)) {
    totals.kcal = totalKcal;
    totals.total_kcal = totalKcal;
  }
  return {
    ...src,
    total_kcal: totalKcal,
    totals,
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
    clarification_questions: Array.isArray(src.clarification_questions)
      ? src.clarification_questions.filter((q) => q && (q.key || q.label)).map((q) => {
          const row = {
            key: String(q.key || "").trim(),
            label: String(q.label || q.key || "").trim(),
            options: Array.isArray(q.options) ? q.options.map((o) => String(o || "").trim()).filter(Boolean) : [],
          };
          const ic = String(q.ingredient_context || "").trim();
          if (ic) row.ingredient_context = ic;
          return row;
        })
      : [],
    meal_components: Array.isArray(src.meal_components)
      ? src.meal_components.map((x) => String(x || "").trim()).filter(Boolean).slice(0, 12)
      : [],
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
    usual_meal_hint: (() => {
      const h = src?.usual_meal_hint;
      if (!h || typeof h !== "object") return null;
      const line = String(h.line || "").trim();
      if (!line) return null;
      return {
        label: String(h.label || "").trim(),
        line,
        matched_food_key: String(h.matched_food_key || "").trim() || undefined,
      };
    })(),
  };
}
function normalizeCoachDaily(raw, dayFallback = localDayISO()) {
  const data = raw && typeof raw === "object" ? raw : {};
  const sourceRaw = String(data?.source || data?.fli_source || data?.reasoning_source || "").trim().toLowerCase();
  const source =
    sourceRaw === "llm" || sourceRaw === "cache" || sourceRaw === "rules"
      ? sourceRaw
      : sourceRaw === "cached_llm"
      ? "cache"
      : sourceRaw === "heuristic" || sourceRaw === "fallback"
      ? "rules"
      : "rules";
  const fliSource =
    sourceRaw === "cached_llm" || source === "cache"
      ? "cached_llm"
      : sourceRaw === "llm"
      ? "llm"
      : sourceRaw === "rules" || sourceRaw === "heuristic" || sourceRaw === "fallback"
      ? "rules"
      : "rules";
  return {
    date: String(data?.date || dayFallback),
    fat_loss_score: Math.round(num(data?.fat_loss_score)),
    one_sentence_summary: String(data?.one_sentence_summary || data?.coach_summary || ""),
    coach_summary: String(data?.coach_summary || data?.one_sentence_summary || ""),
    why_it_matters: String(data?.why_it_matters || ""),
    one_action: String(data?.one_action || data?.if_you_do_one_thing || ""),
    variation_seed: String(data?.variation_seed || ""),
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
    reasoning_source: String(data?.reasoning_source || fliSource),
    fli_source: fliSource,
    source,
    fli_status: String(data?.fli_status || "ready").toLowerCase(),
    fli_reason_code: String(data?.fli_reason_code || ""),
    fli_stale_seconds: Math.max(0, Math.round(num(data?.fli_stale_seconds))),
    source_display: String(data?.source_display || "Coach"),
    llm_model_used: String(data?.llm_model_used || ""),
    llm_error_code: String(data?.llm_error_code || ""),
    llm_tried_models: Array.isArray(data?.llm_tried_models) ? data.llm_tried_models.map((x) => String(x || "")).filter(Boolean) : [],
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
    request_id: String(data?.request_id || "").trim(),
    input_scan_id: String(data?.input_scan_id || "").trim(),
    analysis_id: String(data?.analysis_id || "").trim(),
    meal_id: String(data?.meal_id || "").trim(),
    model_used: String(data?.model_used || data?.llm_model_used || "").trim(),
    error_code: String(data?.error_code || data?.llm_error_code || "").trim(),
    tried_models: Array.isArray(data?.tried_models)
      ? data.tried_models.map((x) => String(x || "").trim()).filter(Boolean)
      : Array.isArray(data?.llm_tried_models)
      ? data.llm_tried_models.map((x) => String(x || "").trim()).filter(Boolean)
      : [],
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

function normalizeDietStyle(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (["vegan"].includes(v)) return "vegan";
  if (["veg", "vegetarian"].includes(v)) return "veg";
  if (["eggitarian", "eggetarian", "egg_veg"].includes(v)) return "eggitarian";
  if (["pescatarian", "pesc"].includes(v)) return "pescatarian";
  return "non_veg";
}

/** For GET /places/healthy and related APIs (matches backend diet_filters.normalize_diet_preference). */
function dietPreferenceQueryFromCoachStyle(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (v === "vegan") return "vegan";
  if (v === "veg" || v === "vegetarian") return "vegetarian";
  return "";
}

function disallowedFoodTokensForDiet(dietStyle) {
  const d = normalizeDietStyle(dietStyle);
  if (d === "vegan") {
    return [
      "egg",
      "eggs",
      "chicken",
      "fish",
      "beef",
      "mutton",
      "pork",
      "paneer",
      "curd",
      "yogurt",
      "milk",
      "cheese",
      "whey",
    ];
  }
  if (d === "veg") {
    return ["egg", "eggs", "chicken", "fish", "beef", "mutton", "pork", "prawn", "shrimp", "tuna"];
  }
  if (d === "eggitarian") {
    return ["chicken", "fish", "beef", "mutton", "pork", "prawn", "shrimp", "tuna"];
  }
  if (d === "pescatarian") {
    return ["chicken", "beef", "mutton", "pork"];
  }
  return [];
}

function scrubDietDisallowedText(text, dietStyle) {
  const src = String(text || "");
  if (!src.trim()) return src;
  const blocked = disallowedFoodTokensForDiet(dietStyle);
  if (!blocked.length) return src;
  let out = src;
  for (const token of blocked) {
    const re = new RegExp(`\\b${token.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}\\b`, "gi");
    out = out.replace(re, "protein source");
  }
  out = out.replace(/\bprotein source\/protein source\b/gi, "protein source");
  out = out.replace(/\s{2,}/g, " ").trim();
  return out;
}

function sanitizeCoachPayloadForDiet(payload, dietStyle) {
  const src = payload && typeof payload === "object" ? payload : null;
  if (!src) return src;
  const out = { ...src };
  out.one_sentence_summary = scrubDietDisallowedText(out.one_sentence_summary, dietStyle);
  out.coach_summary = scrubDietDisallowedText(out.coach_summary, dietStyle);
  out.if_you_do_one_thing = scrubDietDisallowedText(out.if_you_do_one_thing, dietStyle);
  out.one_action = scrubDietDisallowedText(out.one_action, dietStyle);
  out.why_it_matters = scrubDietDisallowedText(out.why_it_matters, dietStyle);
  out.pattern_detected = scrubDietDisallowedText(out.pattern_detected, dietStyle);
  out.projection_explained = scrubDietDisallowedText(out.projection_explained, dietStyle);
  if (Array.isArray(out.diagnosis)) {
    out.diagnosis = out.diagnosis.map((x) => scrubDietDisallowedText(x, dietStyle));
  }
  if (Array.isArray(out.tomorrow_focus)) {
    out.tomorrow_focus = out.tomorrow_focus.map((x) => scrubDietDisallowedText(x, dietStyle));
  }
  if (Array.isArray(out.actions)) {
    out.actions = out.actions.map((a) => {
      const item = a && typeof a === "object" ? { ...a } : {};
      item.title = scrubDietDisallowedText(item.title, dietStyle);
      item.why = scrubDietDisallowedText(item.why, dietStyle);
      item.how = scrubDietDisallowedText(item.how, dietStyle);
      return item;
    });
  }
  if (out.biggest_risk_lever && typeof out.biggest_risk_lever === "object") {
    out.biggest_risk_lever = {
      ...out.biggest_risk_lever,
      title: scrubDietDisallowedText(out.biggest_risk_lever.title, dietStyle),
      reason: scrubDietDisallowedText(out.biggest_risk_lever.reason, dietStyle),
    };
  }
  if (out.highest_roi_change && typeof out.highest_roi_change === "object") {
    out.highest_roi_change = {
      ...out.highest_roi_change,
      title: scrubDietDisallowedText(out.highest_roi_change.title, dietStyle),
      why: scrubDietDisallowedText(out.highest_roi_change.why, dietStyle),
      how: scrubDietDisallowedText(out.highest_roi_change.how, dietStyle),
    };
  }
  return out;
}
function normalizeCoachVoice(raw) {
  const data = raw && typeof raw === "object" ? raw : {};
  const action = data?.one_action && typeof data.one_action === "object" ? data.one_action : {};
  const steps = Array.isArray(action?.steps) ? action.steps.map((x) => String(x || "").trim()).filter(Boolean) : [];
  const toneRequested = String(data?.tone_requested || data?.tone_id || "").trim().toLowerCase();
  const toneUsed = String(data?.tone_used || toneRequested || data?.tone_tag || "").trim().toLowerCase();
  const source = String(data?.source || "").trim().toLowerCase();
  const toneMode = String(
    data?.tone_mode || (source === "llm" || source === "cache" ? "llm" : "fallback")
  )
    .trim()
    .toLowerCase();
  return {
    coach_generated_ts: String(data?.coach_generated_ts || ""),
    tone_requested: toneRequested,
    tone_used: toneUsed,
    tone_id: toneRequested || toneUsed || "supportive",
    tone_mode: toneMode,
    tone_tag: String(data?.tone_tag || "neutral").toLowerCase(),
    source,
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
function sanitizeCoachVoiceForDiet(payload, dietStyle) {
  const src = payload && typeof payload === "object" ? payload : null;
  if (!src) return src;
  const out = { ...src };
  out.empathy_line = scrubDietDisallowedText(out.empathy_line, dietStyle);
  out.insight_line = scrubDietDisallowedText(out.insight_line, dietStyle);
  out.why_this_action = scrubDietDisallowedText(out.why_this_action, dietStyle);
  out.safety_disclaimer = scrubDietDisallowedText(out.safety_disclaimer, dietStyle);
  if (out.one_action && typeof out.one_action === "object") {
    out.one_action = {
      ...out.one_action,
      title: scrubDietDisallowedText(out.one_action.title, dietStyle),
      steps: Array.isArray(out.one_action.steps)
        ? out.one_action.steps.map((s) => scrubDietDisallowedText(s, dietStyle))
        : [],
    };
  }
  return out;
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
function normalizeWeeklyCoach(raw) {
  const root = raw && typeof raw === "object" ? raw : {};
  const coach = root?.weekly_coach && typeof root.weekly_coach === "object" ? root.weekly_coach : root;
  const weekSummary = coach?.week_summary && typeof coach.week_summary === "object" ? coach.week_summary : {};
  const insights = Array.isArray(coach?.habit_insights) ? coach.habit_insights : [];
  const bestChoices = Array.isArray(coach?.best_choices_this_week) ? coach.best_choices_this_week : [];
  const focus = coach?.next_week_focus && typeof coach.next_week_focus === "object" ? coach.next_week_focus : {};

  return {
    week_start: String(root?.week_start || "").trim(),
    headline: String(coach?.headline || "").trim(),
    supporting_text: String(coach?.supporting_text || "").trim(),
    week_summary: {
      days_on_track: Math.max(0, Math.round(num(weekSummary?.days_on_track))),
      days_over_target: Math.max(0, Math.round(num(weekSummary?.days_over_target))),
      days_under_protein: Math.max(0, Math.round(num(weekSummary?.days_under_protein))),
      days_tracked: Math.max(0, Math.round(num(weekSummary?.days_tracked))),
      average_daily_protein_g: round1(num(weekSummary?.average_daily_protein_g)),
      average_daily_calories: round1(num(weekSummary?.average_daily_calories)),
    },
    habit_insights: insights
      .map((row) => ({
        type: String(row?.type || "info").trim().toLowerCase(),
        title: String(row?.title || "").trim(),
        text: String(row?.text || "").trim(),
      }))
      .filter((row) => row.title || row.text)
      .slice(0, 3),
    best_choices_this_week: bestChoices
      .map((row) => ({
        place_name: String(row?.place_name || "").trim(),
        recommended_order: String(row?.recommended_order || "").trim(),
        why_it_helped: String(row?.why_it_helped || "").trim(),
      }))
      .filter((row) => row.place_name && row.recommended_order)
      .slice(0, 2),
    next_week_focus: {
      headline: String(focus?.headline || "").trim(),
      supporting_text: String(focus?.supporting_text || "").trim(),
    },
    coach_version: String(coach?.coach_version || "v1"),
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
  // ===== Phase 1: local caches (consent + nearby snapshot) =====
  const AI_CONSENT_CACHE_KEY = "ai_consent_v1";
  const NEARBY_SNAPSHOT_CACHE_VERSION = 1;
  const NEARBY_SNAPSHOT_TTL_MS = 15 * 60 * 1000; // 15 minutes
  const nearbySnapshotKey = (uid) => `nearby_snapshot_v1:${String(uid || "").trim()}`;

  // ===== Auth (Supabase) =====
  const [session, setSession] = useState(null);
  const redirectUri =
    OAUTH_REDIRECT_TO ||
    AuthSession.makeRedirectUri({ scheme: "calorieclickai", path: "auth-callback" });
  const [authEmail, setAuthEmail] = useState("");
  const [authPass, setAuthPass] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [aiConsentGiven, setAiConsentGiven] = useState(false);
  const [aiConsentLoading, setAiConsentLoading] = useState(false);
  const [aiConsentModalVisible, setAiConsentModalVisible] = useState(false);
  const [deleteAccountBusy, setDeleteAccountBusy] = useState(false);

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
  const [scanProgress, setScanProgress] = useState("");
  const [scanLoadingFactLine, setScanLoadingFactLine] = useState("");
  const [rerunBusy, setRerunBusy] = useState(false);
  const [clarificationSelections, setClarificationSelections] = useState({});
  const [recipeSuggestPayload, setRecipeSuggestPayload] = useState(null);
  const [recipeSuggestBusy, setRecipeSuggestBusy] = useState(false);
  const [recipeDismissedLocal, setRecipeDismissedLocal] = useState({});
  const [editMacrosModalVisible, setEditMacrosModalVisible] = useState(false);
  const [macroDraft, setMacroDraft] = useState({ protein_g: "", carbs_g: "", fat_g: "" });
  const [nearbyDecisionFeedback, setNearbyDecisionFeedback] = useState({});
  const [nearbyDecisionFeedbackOpen, setNearbyDecisionFeedbackOpen] = useState({});
  const [nearbyDecisionAssumptionPresets, setNearbyDecisionAssumptionPresets] = useState({});
  const [supplementFrontUri, setSupplementFrontUri] = useState(null);
  const [supplementBackUri, setSupplementBackUri] = useState(null);
  const [sealImage, setSealImage] = useState(null);
  const [supplementProofMode, setSupplementProofMode] = useState(false);
  const [supplementBarcode, setSupplementBarcode] = useState("");
  const [supplementBatchNumber, setSupplementBatchNumber] = useState("");
  const [supplementStep, setSupplementStep] = useState(1);
  const [supplementBusy, setSupplementBusy] = useState(false);
  const [supplementResult, setSupplementResult] = useState(null);
  const [supplementReportBusy, setSupplementReportBusy] = useState(false);
  const [supplementBreakdownOpen, setSupplementBreakdownOpen] = useState(false);
  const [supplementProcessingVisible, setSupplementProcessingVisible] = useState(false);
  const [supplementProcessingIndex, setSupplementProcessingIndex] = useState(0);
  const [supplementReportModal, setSupplementReportModal] = useState(false);
  const [supplementReportReason, setSupplementReportReason] = useState(SUPPLEMENT_REPORT_REASONS[0].key);
  const [supplementReportOther, setSupplementReportOther] = useState("");
  const [healthyPlacesBusy, setHealthyPlacesBusy] = useState(false);
  const [healthyPlacesError, setHealthyPlacesError] = useState("");
  const [healthyPlaces, setHealthyPlaces] = useState([]);
  // Shared nearby snapshot (cached-first). Keeps endpoints intact, unifies rendering inputs.
  const [nearbySnapshot, setNearbySnapshot] = useState(null);
  const [healthySortMode, setHealthySortMode] = useState("flat_score");
  const [healthySections, setHealthySections] = useState(null);
  const [healthyPlaceCoords, setHealthyPlaceCoords] = useState(null);
  const [healthyMapFocusCoords, setHealthyMapFocusCoords] = useState(null);
  const [healthyMapWidth, setHealthyMapWidth] = useState(320);
  const [healthyViewMode, setHealthyViewMode] = useState("map");
  const [healthyMapFilter, setHealthyMapFilter] = useState("all");
  const [selectedHealthyPlaceId, setSelectedHealthyPlaceId] = useState("");
  const [healthyNearbyRefreshing, setHealthyNearbyRefreshing] = useState(false);
  const [activeScreen, setActiveScreen] = useState("home");
  /** Home hub: split the main feed into focused surfaces (premium IA — avoid one endless scroll). */
  const [homeHubTab, setHomeHubTab] = useState("today");
  const [healthyNearbyTab, setHealthyNearbyTab] = useState("decision");
  const [placeDetailPlace, setPlaceDetailPlace] = useState(null);
  const [lunchDecisionBusy, setLunchDecisionBusy] = useState(false);
  const [lunchDecisionError, setLunchDecisionError] = useState("");
  const [lunchDecision, setLunchDecision] = useState(null);
  const [menuScanPhotoUri, setMenuScanPhotoUri] = useState(null);
  const [menuScanBusy, setMenuScanBusy] = useState(false);
  const [menuScanError, setMenuScanError] = useState("");
  const [menuScanResult, setMenuScanResult] = useState(null);
  const [menuScanInitialAssumptions, setMenuScanInitialAssumptions] = useState(null);
  const [upfScanBusy, setUpfScanBusy] = useState(false);
  const [upfScanResult, setUpfScanResult] = useState(null);
  const [upfScanError, setUpfScanError] = useState("");
  const upfLastUserRef = useRef(null);
  const [cameraMode, setCameraMode] = useState("meal");
  const [pendingMealFeedback, setPendingMealFeedback] = useState(null);
  const [showMealFeedbackPrompt, setShowMealFeedbackPrompt] = useState(false);
  const [contributionSheetVisible, setContributionSheetVisible] = useState(false);
  const [contributionPlace, setContributionPlace] = useState(null);

  // ===== History (isolated by user id) =====
  const [history, setHistory] = useState([]);
  const [mealMemory, setMealMemory] = useState({});
  const [coachDaily, setCoachDaily] = useState(null);
  const [coachVoice, setCoachVoice] = useState(null);
  const [coachVoiceBusy, setCoachVoiceBusy] = useState(false);
  const [coachTrend, setCoachTrend] = useState([]);
  const [coachLastPayload, setCoachLastPayload] = useState(null);
  const [weeklyReport, setWeeklyReport] = useState(null);
  const [weeklyReportBusy, setWeeklyReportBusy] = useState(false);
  const [weeklyCoach, setWeeklyCoach] = useState(null);
  const [weeklyCoachBusy, setWeeklyCoachBusy] = useState(false);
  const [weeklyCoachError, setWeeklyCoachError] = useState("");
  const [weeklyCoachExpanded, setWeeklyCoachExpanded] = useState(false);
  const [coachBusy, setCoachBusy] = useState(false);
  const [fliSyncing, setFliSyncing] = useState(false);
  const [fliPending, setFliPending] = useState(false);
  const [coachErr, setCoachErr] = useState("");
  const [showCoachDebug, setShowCoachDebug] = useState(false);
  const [confidenceCalibration, setConfidenceCalibration] = useState(null);
  const [confidenceCalibrationBusy, setConfidenceCalibrationBusy] = useState(false);
  const [latestScanMeta, setLatestScanMeta] = useState({ id: "", ts: "" });
  const [showCoachDetails, setShowCoachDetails] = useState(false);
  const [fliPreviewExpanded, setFliPreviewExpanded] = useState(false);
  const [scansModuleExpanded, setScansModuleExpanded] = useState(false);
  const [coachProfile, setCoachProfile] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileDraft, setCoachProfileDraft] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileReady, setCoachProfileReady] = useState(false);
  const [coachProfileModal, setCoachProfileModal] = useState(false);
  const [coachMemoryFoodInput, setCoachMemoryFoodInput] = useState("");
  const [coachMemoryGoalInput, setCoachMemoryGoalInput] = useState("");
  // AI Live Coach Chat — restored from build 1.0.13 (182)
  const [coachChatInput, setCoachChatInput] = useState("");
  const [coachChatBusy, setCoachChatBusy] = useState(false);
  const [coachChatMessages, setCoachChatMessages] = useState([]);
  const [coachRecoveryBadge, setCoachRecoveryBadge] = useState({ label: "Recovery mode: balanced", tone: "amber" });
  const [coachRecoveryExpanded, setCoachRecoveryExpanded] = useState(false);
  const coachChatScrollRef = useRef(null);
  const coachReqRef = useRef(false);
  const coachRefreshTimerRef = useRef(null);
  const coachQueuedRefreshRef = useRef(null);
  const coachTitleTapRef = useRef({ count: 0, lastTs: 0 });
  const healthyPlacesReqSeqRef = useRef(0);
  const lunchDecisionReqSeqRef = useRef(0);
  const lunchDecisionInFlightRef = useRef(false);
  const rerunReqSeqRef = useRef(0);
  const lastAnalysisIdRef = useRef("");
  const mainScrollRef = useRef(null);
  const analyzeCancelRef = useRef(false);
  const goalCoachPendingCompletionRef = useRef(null);
  const goalCoachAutoAnalyzeAfterPhotoRef = useRef(false);
  const healthyNearbyContextKeyRef = useRef("");
  const healthyNearbyStaleIgnoredCountRef = useRef(0);

  // Screenshot mode (presentation-only): keep false for normal usage.
  const screenshotMode = false;
  const fliPreviewExpandedEffective = screenshotMode ? false : fliPreviewExpanded;

  // ===== Camera Modal =====
  const [camOpen, setCamOpen] = useState(false);
  const camRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // ===== Barcode Modal =====
  const [barcodeOpen, setBarcodeOpen] = useState(false);
  const [barcodeMode, setBarcodeMode] = useState("lookup");
  const [barcodeManual, setBarcodeManual] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const lastBarcodeAt = useRef(0);

  // ===== Smart Food Alerts =====
  const [smartAlertCandidates, setSmartAlertCandidates] = useState([]);
  const [smartAlertsBusy, setSmartAlertsBusy] = useState(false);
  const [smartAlertState, setSmartAlertState] = useState(null);
  const [smartAlertInboxVisible, setSmartAlertInboxVisible] = useState(false);
  const [smartAlertSettingsVisible, setSmartAlertSettingsVisible] = useState(false);
  const [adminOpsVisible, setAdminOpsVisible] = useState(false);
  const smartAlertsLastFetchRef = useRef(0);
  const SMART_ALERTS_COOLDOWN_MS = 5 * 60 * 1000; // 5 min between fetches

  // ===== Goal Coach (Let's Go) =====
  const [goalPlan, setGoalPlan] = useState(null);
  const [goalPlanLoading, setGoalPlanLoading] = useState(false);
  const [goalCoachDaily, setGoalCoachDaily] = useState(null);
  const [goalCoachWeekly, setGoalCoachWeekly] = useState(null);
  const [goalCoachDailyLoading, setGoalCoachDailyLoading] = useState(false);
  const [goalCoachWeeklyLoading, setGoalCoachWeeklyLoading] = useState(false);
  const [letsGoModalVisible, setLetsGoModalVisible] = useState(false);
  const [paywallOpen, setPaywallOpen] = useState(false);
  /** "advanced" | "pro" | null — which plan to highlight in paywall modal (null = Advanced). */
  const [paywallPlanHint, setPaywallPlanHint] = useState(null);
  const [postScanUpgradeBannerVisible, setPostScanUpgradeBannerVisible] = useState(false);
  const openPaywall = (planHint) => {
    setPaywallPlanHint(planHint || "advanced");
    setPaywallOpen(true);
  };
  const [journeyWeightInput, setJourneyWeightInput] = useState("");
  const [journeyWeightBusy, setJourneyWeightBusy] = useState(false);
  const [journeyPhotoBusy, setJourneyPhotoBusy] = useState(false);
  const [journeyData, setJourneyData] = useState(null);
  const [goalCoachCreateBusy, setGoalCoachCreateBusy] = useState(false);
  const [goalCoachContext, setGoalCoachContext] = useState(null);
  const lastGoalPlanFetchUidRef = useRef("");

  // ===== Push Notifications =====
  const [pushPermissionStatus, setPushPermissionStatus] = useState(null);
  const [expoPushToken, setExpoPushToken] = useState(null);
  const [pushRegisteredUserId, setPushRegisteredUserId] = useState(null);
  const pushNotificationSubsRef = useRef(null);
  const pushPermissionPromptedThisSessionRef = useRef(false);
  const pushRegistrationRef = useRef({ userId: null, token: null });
  const launchTracerRef = useRef(createLaunchTracer("app_launch"));
  const launchPhaseRef = useRef("boot_start");
  const startupCompleteLoggedRef = useRef(false);

  // ===== RevenueCat =====
  const [rcReady, setRcReady] = useState(false);
  const [offerings, setOfferings] = useState(null);
  const [rcCustomerInfo, setRcCustomerInfo] = useState(null);
  const [rcBusy, setRcBusy] = useState(false);
  const [rcRefreshing, setRcRefreshing] = useState(false);
  // rcDebug removed — no longer needed in production

  // ===== Derived gating =====
  const canBarcode = planAtLeast(plan, "elite");
  const canCoaching = planAtLeast(plan, "pro");
  const activeDietStyle = normalizeDietStyle(
    coachProfile?.diet_style || coachProfileDraft?.diet_style || "non_veg"
  );
  const sanitizeCoachForDiet = (payload) => sanitizeCoachPayloadForDiet(payload, activeDietStyle);
  const sanitizeVoiceForDiet = (payload) => sanitizeCoachVoiceForDiet(payload, activeDietStyle);
  const recipeSuggestFiltered = useMemo(() => {
    if (!recipeSuggestPayload) return null;
    const list = (recipeSuggestPayload.recipes || []).filter(
      (r) => !recipeDismissedLocal[String(r?.recipe_key || "")]
    );
    return { ...recipeSuggestPayload, recipes: list };
  }, [recipeSuggestPayload, recipeDismissedLocal]);

  useEffect(() => {
    const scanLoading = busy || menuScanBusy || supplementBusy || upfScanBusy || barcodeBusy;
    if (!scanLoading) {
      setScanLoadingFactLine("");
      return;
    }
    const facts = SCAN_LOADING_FACTS;
    if (!facts.length) {
      setScanLoadingFactLine("Analyzing your meal...");
      return;
    }
    const idx = Math.floor(Math.random() * facts.length);
    setScanLoadingFactLine(facts[idx]);
  }, [busy, menuScanBusy, supplementBusy, upfScanBusy, barcodeBusy]);
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

  function markLaunchPhase(phase, detail = null) {
    launchPhaseRef.current = String(phase || "unknown");
    try {
      launchTracerRef.current?.mark?.(phase, detail);
    } catch {}
  }

  // ===================== INIT =====================
  useEffect(() => {
    markLaunchPhase("boot_start", { appVersion: Constants?.expoConfig?.version || "unknown" });
    const cleanup = installGlobalErrorHandler(() => ({
      phase: launchPhaseRef.current,
      activeScreen,
      userId: userId ? "present" : "none",
    }));
    return () => {
      try {
        cleanup?.();
      } catch {}
    };
  }, []);

  useEffect(() => {
    markLaunchPhase("notification_handler_init_start");
    try {
      Notifications.setNotificationHandler({
        handleNotification: async () => ({
          shouldShowBanner: true,
          shouldShowList: true,
          shouldShowAlert: true,
          shouldPlaySound: true,
          shouldSetBadge: false,
        }),
      });
      if (Platform.OS === "android") {
        Notifications.setNotificationChannelAsync("default", {
          name: "Smart Food Alerts",
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: "#2563eb",
        });
      }
    } catch {}
    markLaunchPhase("notification_handler_init_done");
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
    const analysisId = String(result?.analysis_id || "").trim();
    if (!analysisId) {
      setClarificationSelections({});
      return;
    }
    // Reset on new analysis only; for reruns, keep selections for still-visible keys.
    setClarificationSelections((prev) => {
      const prevObj = prev && typeof prev === "object" ? prev : {};
      const keys = new Set(
        Array.isArray(result?.clarification_questions)
          ? result.clarification_questions.map((q) => String(q?.key || "").trim()).filter(Boolean)
          : []
      );
      // If analysis changed, drop all.
      const lastId = String(lastAnalysisIdRef.current || "").trim();
      if (lastId && lastId !== analysisId) {
        return {};
      }
      // Otherwise, prune to keys that still exist.
      const next = {};
      for (const [k, v] of Object.entries(prevObj)) {
        if (keys.has(String(k))) next[k] = v;
      }
      return next;
    });
    lastAnalysisIdRef.current = analysisId;
  }, [result?.analysis_id, JSON.stringify((result?.clarification_questions || []).map((q) => q?.key || ""))]);

  useEffect(() => {
    setRecipeDismissedLocal({});
  }, [result?.analysis_id]);

  useEffect(() => {
    const aid = result?.analysis_id || result?.meal_id || result?.id;
    if (!aid || !userId || !aiConsentGiven) {
      setRecipeSuggestPayload(null);
      setRecipeSuggestBusy(false);
      return;
    }
    let cancelled = false;
    setRecipeSuggestBusy(true);
    setRecipeSuggestPayload(null);
    void (async () => {
      try {
        const data = await fetchRecipeSuggestions({
          userId,
          analysisId: String(aid),
          meal: result,
          dietStyle: coachProfile?.diet_style || "non_veg",
          goalType: coachProfile?.goal_type || "fat_loss",
          plan,
        });
        if (!cancelled) setRecipeSuggestPayload(data);
      } catch {
        if (!cancelled) setRecipeSuggestPayload(null);
      } finally {
        if (!cancelled) setRecipeSuggestBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    result?.analysis_id,
    result?.meal_id,
    result?.id,
    userId,
    aiConsentGiven,
    plan,
    coachProfile?.diet_style,
    coachProfile?.goal_type,
  ]);

  useEffect(() => {
    let cancelled = false;
    let unsub = null;
    markLaunchPhase("auth_hydration_start");

    (async () => {
      if (!HAS_SUPABASE) return;
      try {
        const { data } = await supabase.auth.getSession();
        if (!cancelled) setSession(data?.session || null);
        markLaunchPhase("auth_session_loaded");
      } catch (e) {
        console.log("getSession failed", String(e));
        markLaunchPhase("auth_session_failed", { message: String(e?.message || e) });
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

  useEffect(() => {
    const uid = userId || session?.user?.id || null;
    if (upfLastUserRef.current !== uid) {
      upfLastUserRef.current = uid;
      setUpfScanBusy(false);
      setUpfScanError("");
      setUpfScanResult(null);
    }
  }, [userId, session?.user?.id]);

  // Phase 1: fast local AI consent check (never block UI if already accepted).
  useEffect(() => {
    let mounted = true;
    const uid = userId || session?.user?.id;
    if (!uid) return undefined;
    (async () => {
      try {
        const local = await AsyncStorage.getItem(AI_CONSENT_CACHE_KEY);
        if (!mounted) return;
        if (local === "true") {
          setAiConsentGiven(true);
          setAiConsentModalVisible(false);
        }
      } catch (_) {}
    })();
    return () => {
      mounted = false;
    };
  }, [userId, session?.user?.id]);

  // Phase 1: load cached nearby snapshot on login (cached-first list/decision/map).
  useEffect(() => {
    let mounted = true;
    const uid = userId || session?.user?.id;
    if (!uid) return undefined;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(nearbySnapshotKey(uid));
        if (!mounted || !raw) return;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return;
        if (parsed.version !== NEARBY_SNAPSHOT_CACHE_VERSION) return;
        const ts = Number(parsed.generated_at_ms) || 0;
        if (!ts || Date.now() - ts > NEARBY_SNAPSHOT_TTL_MS) return;
        setNearbySnapshot({ ...parsed, source: "cache" });
      } catch (_) {}
    })();
    return () => {
      mounted = false;
    };
  }, [userId, session?.user?.id]);

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
    setWeeklyCoach(null);
    setWeeklyCoachBusy(false);
    setWeeklyCoachError("");
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
    setRecipeSuggestPayload(null);
    setRecipeSuggestBusy(false);
    setRecipeDismissedLocal({});
    setBarcodeManual("");
    setBarcodeOpen(false);
    setBarcodeMode("lookup");
    setCamOpen(false);
    setCameraMode("meal");
    setSupplementFrontUri(null);
    setSupplementBackUri(null);
    setSealImage(null);
    setSupplementProofMode(false);
    setSupplementBarcode("");
    setSupplementBatchNumber("");
    setSupplementStep(1);
    setSupplementResult(null);
    setSupplementBusy(false);
    setSupplementReportBusy(false);
    setSupplementBreakdownOpen(false);
    setSupplementProcessingVisible(false);
    setSupplementProcessingIndex(0);
    setSupplementReportModal(false);
    setSupplementReportReason(SUPPLEMENT_REPORT_REASONS[0].key);
    setSupplementReportOther("");
    setHealthyPlacesBusy(false);
    setHealthyPlacesError("");
    setHealthyPlaces([]);
    setNearbySnapshot(null);
    setHealthySections(null);
    setHealthyPlaceCoords(null);
    setHealthyMapFocusCoords(null);
    setHealthyViewMode("map");
    setHealthyMapFilter("all");
    setSelectedHealthyPlaceId("");
    setLunchDecisionBusy(false);
    setLunchDecisionError("");
    setLunchDecision(null);
    setMenuScanPhotoUri(null);
    setMenuScanBusy(false);
    setMenuScanError("");
    setMenuScanResult(null);
    setActiveScreen("home");
    setHealthyMapWidth(320);
    setRerunBusy(false);
    setAiConsentGiven(false);
    setAiConsentModalVisible(false);
    setAiConsentLoading(false);
    setDeleteAccountBusy(false);
    if (coachRefreshTimerRef.current) {
      clearTimeout(coachRefreshTimerRef.current);
      coachRefreshTimerRef.current = null;
    }
    if (!userId) {
      setGoals(null);
      setGoalsDraft(DEFAULT_GOALS);
      setGoalPlan(null);
      setGoalCoachDaily(null);
      setGoalCoachWeekly(null);
      setUsage(null);
      setSupplementFrontUri(null);
      setSupplementBackUri(null);
      setSealImage(null);
      setSupplementProofMode(false);
      setSupplementBarcode("");
      setSupplementBatchNumber("");
      setSupplementStep(1);
      setSupplementResult(null);
      setSupplementBusy(false);
      setSupplementReportBusy(false);
      setSupplementBreakdownOpen(false);
      setSupplementProcessingVisible(false);
      setSupplementProcessingIndex(0);
      setSupplementReportModal(false);
      setSupplementReportReason(SUPPLEMENT_REPORT_REASONS[0].key);
      setSupplementReportOther("");
      setHealthyPlacesBusy(false);
      setHealthyPlacesError("");
      setHealthyPlaces([]);
      setHealthySections(null);
      setHealthyPlaceCoords(null);
      setHealthyMapFocusCoords(null);
      setHealthyViewMode("map");
      setHealthyMapFilter("all");
      setSelectedHealthyPlaceId("");
      setLunchDecisionBusy(false);
      setLunchDecisionError("");
      setLunchDecision(null);
      setMenuScanPhotoUri(null);
      setMenuScanBusy(false);
      setMenuScanError("");
      setMenuScanResult(null);
      setActiveScreen("home");
      setHealthyMapWidth(320);
      setCameraMode("meal");
      setBarcodeMode("lookup");
      setAiConsentGiven(false);
      setAiConsentModalVisible(false);
      setAiConsentLoading(false);
      setDeleteAccountBusy(false);
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    refreshUsage();
    ensureGoals();
    fetchDailySummary();
    loadHistory();
    loadMealMemory(userId).then((m) => setMealMemory(m || {})).catch(() => {});
    void fetchAiConsent(userId);
    void flushCoachFeedbackQueue(userId);
    void fetchGoalPlan();
  }, [userId]);

  useEffect(() => {
    if (!userId || !goalPlan) return;
    void fetchGoalCoachDaily();
    void fetchGoalCoachWeekly();
    void fetchGoalCoachJourney();
  }, [userId, goalPlan?.plan_id]);

  useEffect(() => {
    if (!userId || !isDeviceHealthAvailable()) return;
    initDeviceHealth((err) => {
      if (err) console.log("Device health init:", err);
      else {
        // Coach often ran before Health Connect finished (Android) or HealthKit auth (iOS).
        void ensureDailyCoach(true, {
          refreshServer: true,
          fastMode: true,
          trigger: "device_health_ready",
        });
      }
    });
  }, [userId]);

  useEffect(() => {
    markLaunchPhase("smart_alert_state_hydration_start");
    (async () => {
      try {
        const state = await getSmartAlertState();
        setSmartAlertState(state);
        markLaunchPhase("smart_alert_state_hydration_done");
      } catch (e) {
        console.log("smart alert state hydration failed", String(e?.message || e));
        setSmartAlertState(null);
        markLaunchPhase("smart_alert_state_hydration_failed", { message: String(e?.message || e) });
      }
    })();
  }, []);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (next === "active") {
        if (healthyPlaceCoords && userId && smartAlertState?.enabled) {
          void fetchSmartAlerts({ coords: healthyPlaceCoords, force: false });
        }
        // Play Billing can come up late after resume; refresh offerings when app returns foreground.
        void refreshRevenueCatState("app_active");
        // Coach + FLI cards share in-memory state; without a resume-refresh the
        // greeting + daypart copy go stale after a phone-lock across day-parts
        // (user sees "Good afternoon" in FLI while Coach Summary shows "Good
        // morning"). Force a fresh /coach/daily so both cards re-read the same
        // tz-aware greeting from backend.
        if (userId) {
          void ensureDailyCoach(true, { trigger: "app_resume", refreshServer: true });
        }
      }
    });
    return () => sub?.remove?.();
  }, [healthyPlaceCoords?.lat, healthyPlaceCoords?.lng, userId, smartAlertState?.enabled]);

  // Push registration: when Smart Alerts enabled + userId, request permission, get token, register
  useEffect(() => {
    let cancelled = false;
    const uid = userId || session?.user?.id;
    const enabled = smartAlertState?.enabled;
    if (!uid || !enabled) return;

    (async () => {
      const status = await getPushPermissionStatus();
      if (!cancelled) setPushPermissionStatus(status);
      if (!status.granted) return;

      const token = await getExpoPushTokenSafe();
      if (cancelled) return;
      if (!token) return;

      setExpoPushToken(token);
      const result = await registerPushTokenWithBackend({
        userId: uid,
        expoPushToken: token,
        platform: Platform.OS,
        appVersion: Constants?.expoConfig?.version || "1.0",
      });
      if (!cancelled && result.ok) {
        setPushRegisteredUserId(uid);
        pushRegistrationRef.current = { userId: uid, token };
        await savePushRegistrationState({
          pushPermissionStatus: "granted",
          expoPushToken: token,
          pushRegisteredUserId: uid,
          lastPushRegistrationAt: Date.now(),
        });
      }
    })();
  }, [userId, session?.user?.id, smartAlertState?.enabled]);

  // Push unregister when Smart Alerts disabled
  useEffect(() => {
    const enabled = smartAlertState?.enabled;
    const uid = pushRegisteredUserId;
    const token = expoPushToken;
    if (enabled || !uid || !token) return;

    (async () => {
      await unregisterPushTokenWithBackend({ userId: uid, expoPushToken: token });
      setPushRegisteredUserId(null);
      setExpoPushToken(null);
      pushRegistrationRef.current = { userId: null, token: null };
      await savePushRegistrationState({});
    })();
  }, [smartAlertState?.enabled, pushRegisteredUserId, expoPushToken]);

  // Load push state on mount
  useEffect(() => {
    markLaunchPhase("push_state_hydration_start");
    (async () => {
      try {
        const state = safeObject(await loadPushRegistrationState(), {});
        if (state.expoPushToken) {
          setExpoPushToken(String(state.expoPushToken));
          if (state.pushRegisteredUserId) {
            setPushRegisteredUserId(String(state.pushRegisteredUserId));
            pushRegistrationRef.current = {
              userId: String(state.pushRegisteredUserId),
              token: String(state.expoPushToken),
            };
          }
        }
        const status = await getPushPermissionStatus();
        setPushPermissionStatus(status);
        markLaunchPhase("push_state_hydration_done", { permission: status?.status || "unknown" });
      } catch (e) {
        console.log("push state hydration error", String(e?.message || e));
        setPushPermissionStatus({ granted: false, status: "error" });
        markLaunchPhase("push_state_hydration_failed", { message: String(e?.message || e) });
      }
    })();
  }, []);

  useEffect(() => {
    if (startupCompleteLoggedRef.current) return;
    if (pushPermissionStatus == null || smartAlertState == null) return;
    startupCompleteLoggedRef.current = true;
    markLaunchPhase("startup_complete", {
      active_screen: activeScreen,
      push_permission: pushPermissionStatus?.status || "unknown",
      smart_alerts_enabled: smartAlertState?.enabled === true,
    });
  }, [pushPermissionStatus, smartAlertState, activeScreen]);

  // Notification listeners: received + response (tap)
  useEffect(() => {
    markLaunchPhase("notification_listeners_setup_start");
    const subs = setupNotificationListeners({
      onNotificationReceived: (notification) => {
        try {
          const rawData = safeObject(notification?.request?.content?.data, {});
          const data = safeGetSmartAlertPayload(rawData);
          if (data?.place_id && data?.alert_type) {
            const candidate = {
              place_id: data.place_id,
              place_name: data.place_name,
              best_item_name: data.best_item_name,
              alert_type: data.alert_type,
              title: notification?.request?.content?.title || "Smart alert",
              body: notification?.request?.content?.body || "",
              display_rank_score_100: data.display_rank_score_100,
              confidence_label: data.confidence_label,
              recommendation_label: data.recommendation_label,
              chosen_candidate_specificity_tier: data.chosen_candidate_specificity_tier,
              menu_item_source: data.menu_item_source,
              matched_local_profile: data.matched_local_profile,
              local_profile_source: data.local_profile_source,
              used_venue_intelligence_cache: data.used_venue_intelligence_cache,
              best_item_is_generic_fallback: data.best_item_is_generic_fallback,
            };
            setSmartAlertCandidates((prev) => {
              const key = (c) => (c.place_id || "") + (c.alert_type || "");
              if (prev.some((p) => key(p) === key(candidate))) return prev;
              return [candidate, ...prev].slice(0, 10);
            });
          }
        } catch (err) {
          console.log("notification receive handler error", String(err?.message || err));
        }
      },
      onNotificationResponse: (response) => {
        markLaunchPhase("notification_open_received");
        void handleNotificationOpen(response, {
          userId: userId || session?.user?.id,
          recordAlertOpened,
        })
          .then(({ parsed }) => {
            try {
              markLaunchPhase("notification_open_parsed", {
                place_id: String(parsed?.place_id || ""),
                route_target: String(parsed?.route_target || ""),
              });
              setSmartAlertState(null);
              void getSmartAlertState().then(setSmartAlertState).catch(() => {});
              const resolved = resolveSmartAlertNavigationTarget(
                parseSmartAlertDeepLink(parsed || safeObject(response?.notification?.request?.content?.data, {}) || {})
              );
              if (resolved.action === "open_place" && resolved.place_id) {
                setActiveScreen("healthy_nearby");
                setSmartAlertInboxVisible(false);
                setHealthyNearbyTab("decision");
                const coords = Number.isFinite(resolved.place_lat) && Number.isFinite(resolved.place_lng)
                  ? { lat: resolved.place_lat, lng: resolved.place_lng }
                  : healthyPlaceCoords;
                const preferredCard = {
                  place_id: resolved.place_id,
                  place_name: resolved.place_name,
                  place_lat: resolved.place_lat,
                  place_lng: resolved.place_lng,
                  best_item_name: resolved.best_item_name,
                };
                if (coords) {
                  void loadHealthyPlacesNearby({ coords, preferredCard });
                } else {
                  void loadHealthyPlacesNearby();
                }
              } else if (resolved.action === "open_inbox" || resolved.place_id) {
                setActiveScreen("healthy_nearby");
                setSmartAlertInboxVisible(true);
                void fetchSmartAlerts({ force: true });
              } else {
                setActiveScreen("healthy_nearby");
              }
            } catch (err) {
              console.log("notification response handler error", String(err?.message || err));
              setActiveScreen("healthy_nearby");
              setSmartAlertInboxVisible(true);
            }
          })
          .catch((err) => {
            console.log("handleNotificationOpen failed", String(err?.message || err));
            setActiveScreen("healthy_nearby");
            setSmartAlertInboxVisible(true);
          });
      },
    });
    markLaunchPhase("notification_listeners_setup_done");
    pushNotificationSubsRef.current = subs;
    return () => {
      cleanupNotificationListeners(subs);
      pushNotificationSubsRef.current = null;
    };
  }, [userId, session?.user?.id]);

  useEffect(() => {
    if (!supplementProcessingVisible) {
      setSupplementProcessingIndex(0);
      return;
    }
    let active = true;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (!active) return;
      setSupplementProcessingIndex((prev) =>
        Math.min(SUPPLEMENT_PROCESSING_CHECKS.length, Number(prev || 0) + 1)
      );
      if (Date.now() - startedAt > 1800) {
        clearInterval(timer);
      }
    }, 350);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [supplementProcessingVisible]);

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
      const parsed = safeParseJson(raw, [], "history");
      setHistory(sanitizeHistoryEntries(parsed));
    } catch {
      setHistory([]);
    }
  }

  async function enqueueCoachFeedback(uid, body) {
    if (!uid || !body) return;
    const key = coachFeedbackQueueKey(uid);
    try {
      const raw = await AsyncStorage.getItem(key);
      const arr = safeParseJson(raw, [], "coach_feedback_queue");
      const queue = safeArray(arr);
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
      queue = safeArray(safeParseJson(raw, [], "coach_feedback_flush"));
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
      const existing = safeParseJson(raw, [], "history_push");
      const arr = sanitizeHistoryEntries(existing);
      const incomingAnalysisId = String(entry?.analysis_id || "").trim();
      if (incomingAnalysisId) {
        const idx = arr.findIndex((it) => String(it?.analysis_id || "").trim() === incomingAnalysisId);
        if (idx >= 0) {
          const merged = { ...(arr[idx] || {}), ...(entry || {}) };
          const next = [...arr];
          next[idx] = merged;
          setHistory(next);
          await AsyncStorage.setItem(key, JSON.stringify(sanitizeHistoryEntries(next)));
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
      const next = sanitizeHistoryEntries([entry, ...arr]);
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

  function reopenHistoryEntry(entry) {
    if (!entry || typeof entry !== "object") return;
    if ((entry.kind || "") === "barcode") {
      const normalized = normalizeAnalyzeResult({
        analysis_id: entry.analysis_id,
        total_kcal: entry.total_kcal,
        totals: entry.totals,
        items: Array.isArray(entry.items) ? entry.items : [],
        vision_confidence: 1,
        barcode: entry.barcode,
        barcode_source: true,
      });
      setPhotoUri(null);
      setResult(normalized);
      setClarificationSelections({});
      return;
    }
    if ((entry.kind || "") !== "photo") return;
    const normalized = normalizeAnalyzeResult({
      analysis_id: entry.analysis_id,
      total_kcal: entry.total_kcal,
      totals: entry.totals,
      items: Array.isArray(entry.items) ? entry.items : [],
      micros: entry.micros,
      vision_confidence: entry.vision_confidence ?? null,
      coaching: entry.coaching ?? null,
      locked: entry.locked ?? null,
    });
    setPhotoUri(entry.photo_uri ? entry.photo_uri : null);
    setResult(normalized);
    setClarificationSelections({});
  }

  async function loadLocalGoals(uid) {
    if (!uid) return null;
    try {
      const raw = await AsyncStorage.getItem(goalsKey(uid));
      if (!raw) return null;
      return normalizeGoals(safeParseJson(raw, {}, "goals"), DEFAULT_GOALS);
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

  // Device-locale-based default tone for first-time users. Returns "indian_coach"
  // when the device timezone or locale suggests India; otherwise "supportive".
  // Only consulted when no coach profile has ever been saved — once the user
  // picks a tone from Settings and saves, AsyncStorage holds their choice and
  // this helper is never consulted again.
  function detectDefaultCoachTone() {
    try {
      const opts = Intl.DateTimeFormat().resolvedOptions();
      const tz = String(opts.timeZone || "");
      const locale = String(opts.locale || "");
      if (tz === "Asia/Kolkata" || tz === "Asia/Calcutta") return "indian_coach";
      if (/-IN\b/i.test(locale) || /^hi\b/i.test(locale)) return "indian_coach";
    } catch {}
    return "supportive";
  }

  async function loadCoachProfile(uid) {
    if (!uid) return DEFAULT_COACH_PROFILE;
    try {
      const raw = await AsyncStorage.getItem(coachProfileKey(uid));
      if (!raw) return { ...DEFAULT_COACH_PROFILE, tone_preference: detectDefaultCoachTone() };
      return normalizeCoachProfile(safeParseJson(raw, {}, "coach_profile"));
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
            const obj = safeParseJson(v, null, "coach_trend_row");
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

  function buildWeeklyCoachDailyRows() {
    const target = normalizeGoals(goals || dailySummary?.goals || DEFAULT_GOALS, DEFAULT_GOALS);
    const today = localDayISO();
    const weekStart = localWeekStartISO(today);
    const rowsByDay = {};

    function ensureRow(day) {
      const token = String(day || "").slice(0, 10);
      if (!token) return null;
      if (!rowsByDay[token]) {
        rowsByDay[token] = {
          date: token,
          consumed_calories: 0,
          target_calories: round1(target.kcal),
          consumed_protein_g: 0,
          target_protein_g: round1(target.protein_g),
          lunch_calories: 0,
          dinner_calories: 0,
          lunch_protein_g: 0,
          dinner_protein_g: 0,
        };
      }
      return rowsByDay[token];
    }

    (Array.isArray(history) ? history : []).forEach((entry) => {
      if (String(entry?.kind || "").trim().toLowerCase() !== "photo") return;
      const day = localDayFromISO(entry?.ts);
      if (!day || day < weekStart || day > today) return;

      const row = ensureRow(day);
      if (!row) return;

      const kcal = Math.max(0, num(entry?.total_kcal ?? entry?.totals?.kcal ?? entry?.totals?.total_kcal));
      const protein = Math.max(0, num(entry?.totals?.protein_g));
      row.consumed_calories = round1(num(row.consumed_calories) + kcal);
      row.consumed_protein_g = round1(num(row.consumed_protein_g) + protein);

      const at = new Date(entry?.ts || "");
      const hour = Number.isFinite(at.getTime()) ? at.getHours() : 12;
      if (hour >= 11 && hour <= 15) {
        row.lunch_calories = round1(num(row.lunch_calories) + kcal);
        row.lunch_protein_g = round1(num(row.lunch_protein_g) + protein);
      } else if (hour >= 18 || hour <= 2) {
        row.dinner_calories = round1(num(row.dinner_calories) + kcal);
        row.dinner_protein_g = round1(num(row.dinner_protein_g) + protein);
      }
    });

    const todayRow = ensureRow(today);
    if (todayRow) {
      const totals = dailySummary?.totals && typeof dailySummary.totals === "object" ? dailySummary.totals : {};
      const consumedKcal = Math.max(
        0,
        num(dailySummary?.total_kcal ?? totals?.kcal ?? totals?.total_kcal)
      );
      const consumedProtein = Math.max(0, num(totals?.protein_g));
      if (consumedKcal > 0) todayRow.consumed_calories = round1(Math.max(num(todayRow.consumed_calories), consumedKcal));
      if (consumedProtein > 0) {
        todayRow.consumed_protein_g = round1(Math.max(num(todayRow.consumed_protein_g), consumedProtein));
      }
    }

    return Object.values(rowsByDay)
      .filter((row) => row.date >= weekStart && row.date <= today)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .slice(-7);
  }

  async function loadWeeklyCoachChoiceRows(uid, weekStartIso) {
    if (!uid) return [];
    try {
      const raw = await AsyncStorage.getItem(weeklyCoachChoicesKey(uid));
      const arr = safeParseJson(raw, [], "weekly_coach_choices_load");
      const rows = safeArray(arr);
      const today = localDayISO();
      return rows
        .map((row) => {
          const ts = String(row?.ts || "").trim();
          const day = localDayFromISO(ts);
          if (!day || day < weekStartIso || day > today) return null;
          return {
            ts,
            place_name: String(row?.place_name || "").trim(),
            recommended_order: String(row?.recommended_order || "").trim(),
            fit_for_today:
              typeof row?.fit_for_today === "boolean" ? row.fit_for_today : null,
            health_score:
              (row?.health_score != null) ? round1(num(row?.health_score)) : null,
            why_it_helped: String(row?.why_it_helped || "").trim(),
          };
        })
        .filter((row) => row && row.place_name && row.recommended_order)
        .slice(-40);
    } catch {
      return [];
    }
  }

  async function rememberWeeklyCoachChoice(uid, eventName, card, metadata = {}) {
    const event = String(eventName || "").trim().toLowerCase();
    if (!uid || !event) return;
    if (!["recommendation_clicked", "place_selected", "recommendation_followed", "recommendation_selected"].includes(event)) return;

    const payload = card && typeof card === "object" ? card : {};
    const placeName = String(payload?.place_name || payload?.name || "").trim();
    const order = String(payload?.recommended_order || payload?.best_order || "").trim();
    if (!placeName || !order) return;

    const row = {
      ts: nowISO(),
      event,
      place_name: placeName,
      recommended_order: order,
      fit_for_today: typeof payload?.fit_for_today === "boolean" ? payload.fit_for_today : null,
      health_score: Number.isFinite(num(payload?.health_score_100))
        ? round1(num(payload.health_score_100))
        : Number.isFinite(num(payload?.health_score))
        ? round1(num(payload.health_score) * 10)
        : null,
      why_it_helped: String(
        payload?.why_this_works ||
          payload?.decision_reason ||
          metadata?.why_it_helped ||
          ""
      ).trim(),
    };

    try {
      const key = weeklyCoachChoicesKey(uid);
      const raw = await AsyncStorage.getItem(key);
      const arr = safeParseJson(raw, [], "weekly_coach_choices_save");
      const rows = safeArray(arr);
      rows.push(row);
      await AsyncStorage.setItem(key, JSON.stringify(rows.slice(-120)));
    } catch {}
  }

  async function fetchWeeklyCoachProgress(force = false) {
    const uid = userId || session?.user?.id;
    if (!uid || !canCoaching || !aiConsentGiven) return;
    const currentWeekStart = localWeekStartISO(localDayISO());
    if (weeklyCoach && !force && String(weeklyCoach?.week_start || "").trim() === currentWeekStart) return;

    setWeeklyCoachBusy(true);
    setWeeklyCoachError("");
    try {
      const weekStart = currentWeekStart;
      const goal = resolveLunchGoal();
      const cutMode = goal === "fat_loss";
      const dailyRows = buildWeeklyCoachDailyRows();
      const choices = await loadWeeklyCoachChoiceRows(uid, weekStart);

      const body = {
        user_id: uid,
        week_start: weekStart,
        goal,
        cut_mode: cutMode,
        daily_rows: dailyRows,
        choices,
      };

      const res = await fetch(withTimezoneQuery(`${API_BASE}/coach/weekly-progress`), {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      setWeeklyCoach(normalizeWeeklyCoach(data));
    } catch (e) {
      setWeeklyCoachError(
        (String((e && e.message) || e || "").trim() || "Could not load weekly coach right now.").slice(0, 200)
      );
    } finally {
      setWeeklyCoachBusy(false);
    }
  }

  async function loadRecentCoachVoiceMessages(uid, dayIso) {
    try {
      const raw = await AsyncStorage.getItem(coachVoiceMemoryKey(uid, dayIso));
      if (!raw) return [];
      const arr = safeArray(safeParseJson(raw, [], "coach_voice_memory"));
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

  // ===== AI Live Coach Chat (restored from 1.0.13 build 182) =====
  async function loadCoachChatHistory(uid, dayIso) {
    try {
      const raw = await AsyncStorage.getItem(coachChatHistoryKey(uid, dayIso));
      const arr = safeParseJson(raw, [], "coach_chat_history");
      return (Array.isArray(arr) ? arr : [])
        .map((m) => ({
          role: String(m?.role || "").trim().toLowerCase() === "coach" ? "coach" : "user",
          text: String(m?.text || "").trim(),
          ts: String(m?.ts || ""),
        }))
        .filter((m) => m.text)
        .slice(-14);
    } catch {
      return [];
    }
  }

  async function saveCoachChatHistory(uid, dayIso, messages) {
    try {
      const cleaned = (Array.isArray(messages) ? messages : [])
        .map((m) => ({
          role: String(m?.role || "").trim().toLowerCase() === "coach" ? "coach" : "user",
          text: String(m?.text || "").trim().slice(0, 500),
          ts: String(m?.ts || nowISO()),
        }))
        .filter((m) => m.text)
        .slice(-14);
      await AsyncStorage.setItem(coachChatHistoryKey(uid, dayIso), JSON.stringify(cleaned));
    } catch {}
  }

  async function sendCoachChatTurn() {
    const uid = userId || session?.user?.id;
    const text = String(coachChatInput || "").trim();
    if (!uid || !text || coachChatBusy) return;
    setCoachChatBusy(true);
    const day = localDayISO();
    const userMsg = { role: "user", text, ts: nowISO() };
    const nextMessages = [...coachChatMessages, userMsg].slice(-12);
    setCoachChatMessages(nextMessages);
    void saveCoachChatHistory(uid, day, nextMessages);
    setCoachChatInput("");
    const base = buildDailyCoachPayload();
    const tone = coachProfile?.tone_preference || "supportive";

    const _applyReply = (data) => {
      const replyParts = [
        String(data?.coach_reply || "").trim(),
        String(data?.next_question || "").trim(),
        String(data?.action_hint || "").trim(),
      ].filter(Boolean);
      const coachText = replyParts.join("\n\n").trim();
      if (!coachText) {
        throw new Error("Coach returned an empty reply. Please try again.");
      }
      setCoachChatMessages((prev) => {
        const merged = [...prev, { role: "coach", text: coachText, ts: nowISO() }].slice(-14);
        void saveCoachChatHistory(uid, day, merged);
        return merged;
      });
    };

    const history = nextMessages
      .map((m) => ({
        role: String(m?.role || "").trim().toLowerCase() === "coach" ? "coach" : "user",
        text: String(m?.text || "").trim(),
      }))
      .filter((m) => m.text)
      .slice(-10);

    try {
      let healthContext = {};
      try {
        healthContext = (await getDailyHealthContext(String(base?.date || localDayISO()))) || {};
      } catch (_) {}
      const fp = Array.isArray(coachProfile?.food_preferences) ? coachProfile.food_preferences.filter(Boolean) : [];
      const gr = Array.isArray(coachProfile?.goal_reminders) ? coachProfile.goal_reminders.filter(Boolean) : [];
      const body = {
        user_id: uid,
        day: String(base?.date || localDayISO()),
        user_text: text,
        goals: base?.goals || {},
        consumed: base?.consumed || {},
        health_context: healthContext,
        history,
        tone_preference: tone,
        tone_id: tone,
        profile: base?.profile || {},
        signals: base?.signals || {},
        meal_timing: base?.meal_timing || {},
        food_preferences: fp,
        goal_reminders: gr,
      };
      const res = await fetch(withTimezoneQuery(`${API_BASE}/coach/audio/turn`), {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      _applyReply(data);
    } catch (err) {
      const fallback = "Coach could not respond right now. Check your connection and try again.";
      const msg = String(err?.message || "").trim() || fallback;
      setCoachChatMessages((prev) => {
        const merged = [...prev, { role: "coach", text: msg, ts: nowISO(), coach_error: true }].slice(-14);
        void saveCoachChatHistory(uid, day, merged);
        return merged;
      });
    } finally {
      setCoachChatBusy(false);
    }
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
    if (!aiConsentGiven) return;
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
      tone_id: coachProfile?.tone_preference || "supportive",
    };
    // Coach voice is optional/background enrichment.
    // Never block UI on it; keep request short and abortable.
    setCoachVoiceBusy(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/coach/voice`);
      const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
      const timeoutMs = 2200;
      const t = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(requestBody),
        signal: ctrl ? ctrl.signal : undefined,
      });
      if (t) clearTimeout(t);
      const data = await safeJson(res);
      const cleaned = sanitizeVoiceForDiet(normalizeCoachVoice(data));
      setCoachVoice(cleaned);
      await rememberCoachVoiceMessage(uid, day, cleaned);
    } catch (e) {
      // Silent failure; optional layer only.
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
    if (!aiConsentGiven) return;
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
    if (!aiConsentGiven) {
      setCoachDaily(null);
      setCoachErr("AI processing consent required.");
      setFliPending(false);
      return;
    }

    const baseCoachPayload = buildDailyCoachPayload();
    let payload = baseCoachPayload;
    if (isDeviceHealthAvailable()) {
      try {
        const hc = await getDailyHealthContext(baseCoachPayload.date);
        if (hc && typeof hc === "object") {
          payload = { ...baseCoachPayload, health_context: hc };
        }
      } catch (_) {}
    }
    const fp = Array.isArray(coachProfile?.food_preferences) ? coachProfile.food_preferences : [];
    const gr = Array.isArray(coachProfile?.goal_reminders) ? coachProfile.goal_reminders : [];
    if (fp.length || gr.length) {
      payload = {
        ...payload,
        coach_client_memory: {
          food_preferences: fp.map((x) => String(x || "").trim()).filter(Boolean).slice(0, 12),
          goal_reminders: gr.map((x) => String(x || "").trim()).filter(Boolean).slice(0, 8),
        },
      };
    }
    setCoachLastPayload(payload || null);
    const day = String(payload?.date || localDayISO());
    const requestedLatestScanId = String(opts?.latestScanId || opts?.analysisId || opts?.mealId || latestScanMeta?.id || "").trim();
    const requestedLatestScanTs = String(opts?.latestScanTs || latestScanMeta?.ts || "").trim();
    const requestedMealId = String(opts?.mealId || opts?.analysisId || requestedLatestScanId || latestScanMeta?.id || "").trim();
    const requestedAnalysisId = String(opts?.analysisId || opts?.mealId || requestedLatestScanId || latestScanMeta?.id || "").trim();
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
          const parsed = safeParseJson(raw, null, "daily_coach_cache_empty");
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(sanitizeCoachForDiet(cachedResp));
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
          const parsed = safeParseJson(raw, null, "daily_coach_cache");
          const cachedPayloadHash = String(parsed?.payloadHash || "");
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (
            cachedResp &&
            typeof cachedResp === "object" &&
            cachedPayloadHash === payloadHash &&
            !isCoachStaleForScan(cachedResp, requestedLatestScanId)
          ) {
            setCoachDaily(sanitizeCoachForDiet(cachedResp));
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
          mealId: requestedMealId,
          analysisId: requestedAnalysisId,
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
          mealId: queuedNow.mealId || String(prevQueued?.mealId || "").trim(),
          analysisId: queuedNow.analysisId || String(prevQueued?.analysisId || "").trim(),
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
      if (requestedMealId) params.push(`meal_id=${encodeURIComponent(requestedMealId)}`);
      if (requestedAnalysisId) params.push(`analysis_id=${encodeURIComponent(requestedAnalysisId)}`);
      if (stateSignature) params.push(`state_signature=${encodeURIComponent(stateSignature)}`);
      if (requestedTone) params.push(`tone_id=${encodeURIComponent(requestedTone)}`);
      const url = withTimezoneQuery(`${API_BASE}/coach/daily?${params.join("&")}`);
      const coachBody = {
        ...(payload || {}),
        meal_id: requestedMealId || undefined,
        analysis_id: requestedAnalysisId || undefined,
        input_scan_id: requestedLatestScanId || requestedAnalysisId || requestedMealId || undefined,
      };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(coachBody),
      });
      const data = await safeJson(res);
      const cleaned = sanitizeCoachForDiet(normalizeCoachDaily(data, day));
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
          const parsed = safeParseJson(raw, null, "daily_coach_cache_error");
          const cachedResp = normalizeCoachDaily(parsed?.response || parsed, day);
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(sanitizeCoachForDiet(cachedResp));
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
      setWeeklyCoach(null);
      setWeeklyCoachError("");
      setFliSyncing(false);
      setFliPending(false);
      setCoachErr("");
      return;
    }
    if (!aiConsentGiven) {
      setCoachDaily(null);
      setCoachVoice(null);
      setWeeklyReport(null);
      setWeeklyCoach(null);
      setWeeklyCoachError("");
      setFliSyncing(false);
      setFliPending(false);
      setCoachErr("AI processing consent required.");
      return;
    }
    void ensureDailyCoach(false);
    void fetchCoachVoice(null, false);
    void fetchWeeklyReport(false);
    void fetchWeeklyCoachProgress(false);
  }, [userId, coachProfileReady, goals, dailySummary, history, coachProfile, canCoaching, aiConsentGiven]);

  async function applyCoachProfile() {
    const uid = userId || session?.user?.id;
    const normalized = normalizeCoachProfile(coachProfileDraft);
    await saveCoachProfile(uid, normalized);
    setCoachMemoryFoodInput("");
    setCoachMemoryGoalInput("");
    closeBooleanStateSafely(setCoachProfileModal);
    await ensureDailyCoach(true, { refreshServer: true, fastMode: true, trigger: "profile_update" });
  }

  function addCoachFoodPreference() {
    const t = String(coachMemoryFoodInput || "").trim().slice(0, 80);
    if (!t) return;
    setCoachProfileDraft((p) => {
      const cur = Array.isArray(p.food_preferences) ? [...p.food_preferences] : [];
      if (cur.some((x) => String(x).toLowerCase() === t.toLowerCase())) return p;
      if (cur.length >= 12) return p;
      return { ...p, food_preferences: [...cur, t] };
    });
    setCoachMemoryFoodInput("");
  }

  function addCoachGoalReminder() {
    const t = String(coachMemoryGoalInput || "").trim().slice(0, 120);
    if (!t) return;
    setCoachProfileDraft((p) => {
      const cur = Array.isArray(p.goal_reminders) ? [...p.goal_reminders] : [];
      if (cur.some((x) => String(x).toLowerCase() === t.toLowerCase())) return p;
      if (cur.length >= 8) return p;
      return { ...p, goal_reminders: [...cur, t] };
    });
    setCoachMemoryGoalInput("");
  }

  function removeCoachFoodPreference(idx) {
    setCoachProfileDraft((p) => ({
      ...p,
      food_preferences: (Array.isArray(p.food_preferences) ? p.food_preferences : []).filter((_, i) => i !== idx),
    }));
  }

  function removeCoachGoalReminder(idx) {
    setCoachProfileDraft((p) => ({
      ...p,
      goal_reminders: (Array.isArray(p.goal_reminders) ? p.goal_reminders : []).filter((_, i) => i !== idx),
    }));
  }

  function clearCoachMemoryLists() {
    setCoachProfileDraft((p) => ({ ...p, food_preferences: [], goal_reminders: [] }));
    setCoachMemoryFoodInput("");
    setCoachMemoryGoalInput("");
  }

  function clearCurrentScan() {
    setPhotoUri(null);
    setResult(null);
  }

  function clearSupplementScan() {
    setSupplementFrontUri(null);
    setSupplementBackUri(null);
    setSealImage(null);
    setSupplementProofMode(false);
    setSupplementBarcode("");
    setSupplementBatchNumber("");
    setSupplementStep(1);
    setSupplementResult(null);
    setSupplementBreakdownOpen(false);
    setSupplementReportModal(false);
    setSupplementReportReason(SUPPLEMENT_REPORT_REASONS[0].key);
    setSupplementReportOther("");
  }

  // ===================== RevenueCat =====================
  async function refreshRevenueCatState(reason = "manual") {
    const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
    if (!apiKey) return { info: null, offerings: null };
    setRcRefreshing(true);
    try {
      try { await Purchases.invalidateCustomerInfoCache(); } catch (_) {}
      const info = await Purchases.getCustomerInfo();
      const offs = await loadOfferingsWithRetry(10);
      setRcCustomerInfo(info);
      setOfferings(offs);
      const activeOffering = getActiveOffering(offs);
      const packageCount = activeOffering ? packagesFromOffering(activeOffering).length : 0;
      const pkgIds = packagesFromOffering(activeOffering).map(
        (p) => p?.product?.identifier || p?.identifier || "?"
      );
      return { info, offerings: offs };
    } catch (_) {
      return { info: null, offerings: null };
    } finally {
      setRcRefreshing(false);
    }
  }

  useEffect(() => {
    const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
    if (!apiKey) return;
    Purchases.configure({ apiKey });
    setRcReady(true);

    (async () => {
      try {
        await refreshRevenueCatState("init");
      } catch (_) {
        // RC init failed silently
      }
    })();
  }, []);

  useEffect(() => {
    const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
    if (!apiKey || !userId) return;
    let cancelled = false;
    (async () => {
      try {
        const { customerInfo } = await Purchases.logIn(String(userId));
        if (cancelled) return;
        setRcCustomerInfo(customerInfo);
        const { offerings: offs } = await refreshRevenueCatState("login");
        if (cancelled) return;
        setOfferings(offs);
      } catch (_) {
        // RC logIn / refresh failed silently
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const activeEntitlements = useMemo(() => {
    const active = rcCustomerInfo?.entitlements?.active || {};
    return Object.keys(active).map((k) => k.toLowerCase());
  }, [rcCustomerInfo]);

  const priceByEntitlement = useMemo(() => {
    const map = {};
    const activeOffering = getActiveOffering(offerings);
    const pkgs = packagesFromOffering(activeOffering);
    for (const p of pkgs) {
      const prod = p?.product;
      const price =
        prod?.priceString ||
        prod?.localizedPriceString ||
        (prod?.currencyCode && prod?.price ? `${prod.price} ${prod.currencyCode}` : null);

      if (!price) continue;

      for (const ent of ["elite", "advanced", "pro", "infinite"]) {
        if (packageMatchesEntitlement(p, ent) && !map[ent]) map[ent] = price;
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
      let activeOffering = getActiveOffering(offerings);
      let packages = packagesFromOffering(activeOffering);
      if (!activeOffering || !packages.length) {
        const refreshed = await refreshRevenueCatState("purchase_preflight");
        activeOffering = getActiveOffering(refreshed.offerings || offerings);
        packages = packagesFromOffering(activeOffering);
        if (!activeOffering || !packages.length) {
          Alert.alert(
            "Not ready",
            "Subscriptions are still loading from Google Play. Please open this app from the Play internal testing build/account, then retry in 30-60 seconds.",
          );
          return;
        }
      }
      setRcBusy(true);

      const target = packages.find((p) => packageMatchesEntitlement(p, entitlement));

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
    dismissKeyboardSafe();
    const { userId: regUid, token: regToken } = pushRegistrationRef.current || {};
    if (regUid && regToken) {
      unregisterPushTokenWithBackend({ userId: regUid, expoPushToken: regToken });
      pushRegistrationRef.current = { userId: null, token: null };
    }
    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch (_) {}
    }
    setPhotoUri(null);
    setResult(null);
    setDailySummary(null);
    setHistory([]);
    setCoachDaily(null);
    setCoachVoice(null);
    setCoachTrend([]);
    setCoachLastPayload(null);
    setWeeklyReport(null);
    setWeeklyCoach(null);
    setWeeklyCoachBusy(false);
    setWeeklyCoachError("");
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
    setLetsGoModalVisible(false);
    setBarcodeManual("");
    setBarcodeOpen(false);
    setBarcodeMode("lookup");
    setCamOpen(false);
    setCameraMode("meal");
    setSupplementFrontUri(null);
    setSupplementBackUri(null);
    setSupplementBarcode("");
    setSupplementBatchNumber("");
    setSupplementStep(1);
    setSupplementResult(null);
    setSupplementBusy(false);
    setSupplementReportBusy(false);
    setSupplementBreakdownOpen(false);
    setSupplementProcessingVisible(false);
    setSupplementProcessingIndex(0);
    setSupplementReportModal(false);
    setSupplementReportReason(SUPPLEMENT_REPORT_REASONS[0].key);
    setSupplementReportOther("");
    setHealthyPlacesBusy(false);
    setHealthyPlacesError("");
    setHealthyPlaces([]);
    setHealthySections(null);
    setHealthyPlaceCoords(null);
    setHealthyMapFocusCoords(null);
    setHealthyViewMode("map");
    setHealthyMapFilter("all");
    setSelectedHealthyPlaceId("");
    setLunchDecisionBusy(false);
    setLunchDecisionError("");
    setLunchDecision(null);
    setMenuScanPhotoUri(null);
    setMenuScanBusy(false);
    setMenuScanError("");
    setMenuScanResult(null);
    setUpfScanBusy(false);
    setUpfScanError("");
    setUpfScanResult(null);
    setRerunBusy(false);
    setPushRegisteredUserId(null);
    setExpoPushToken(null);
    setSmartAlertCandidates([]);
    if (coachRefreshTimerRef.current) {
      clearTimeout(coachRefreshTimerRef.current);
      coachRefreshTimerRef.current = null;
    }
    coachQueuedRefreshRef.current = null;
  }

  async function fetchAiConsent(forceUserId) {
    const uid = forceUserId || userId || session?.user?.id;
    if (!uid) return false;
    // Fast path: local cache says consent is granted → do not block UI.
    try {
      const local = await AsyncStorage.getItem(AI_CONSENT_CACHE_KEY);
      if (local === "true") {
        setAiConsentGiven(true);
        setAiConsentModalVisible(false);
        return true;
      }
    } catch (_) {}
    setAiConsentLoading(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/ai/consent?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
      const data = await safeJson(res);
      const consent = Boolean(data?.consent_given);
      setAiConsentGiven(consent);
      setAiConsentModalVisible(!consent);
      if (consent) AsyncStorage.setItem(AI_CONSENT_CACHE_KEY, "true").catch(() => {});
      return consent;
    } catch (e) {
      console.log("fetchAiConsent failed", String(e));
      setAiConsentGiven(false);
      setAiConsentModalVisible(true);
      return false;
    } finally {
      setAiConsentLoading(false);
    }
  }

  async function updateAiConsent(nextConsent) {
    const uid = userId || session?.user?.id;
    if (!uid) return false;
    // Optimistic enable: update UI immediately; persist locally; POST in background.
    if (Boolean(nextConsent)) {
      setAiConsentGiven(true);
      setAiConsentModalVisible(false);
      setAiConsentLoading(false);
      AsyncStorage.setItem(AI_CONSENT_CACHE_KEY, "true").catch(() => {});
      const url = withTimezoneQuery(`${API_BASE}/ai/consent?user_id=${encodeURIComponent(uid)}`);
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify({ user_id: uid, consent: true }),
      })
        .then(safeJson)
        .then((data) => {
          const consent = Boolean(data?.consent_given);
          if (!consent) {
            // Server refused consent update (rare). Reconcile conservatively.
            setAiConsentGiven(false);
            setAiConsentModalVisible(true);
            AsyncStorage.removeItem(AI_CONSENT_CACHE_KEY).catch(() => {});
          }
        })
        .catch(() => {});
      return true;
    }
    setAiConsentLoading(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/ai/consent?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify({ user_id: uid, consent: Boolean(nextConsent) }),
      });
      const data = await safeJson(res);
      const consent = Boolean(data?.consent_given);
      setAiConsentGiven(consent);
      setAiConsentModalVisible(!consent);
      if (!consent) {
        AsyncStorage.removeItem(AI_CONSENT_CACHE_KEY).catch(() => {});
        Alert.alert("AI processing disabled", "Scanning and AI coaching are now blocked until you enable consent.");
      }
      return consent;
    } catch (e) {
      Alert.alert("Consent update failed", String(e?.message || e || "").slice(0, 200));
      return aiConsentGiven;
    } finally {
      setAiConsentLoading(false);
    }
  }

  function ensureAiConsentOrAlert() {
    if (aiConsentGiven) return true;
    if (aiConsentLoading) {
      Alert.alert("AI consent", "Checking consent status. Please wait a moment.");
      return false;
    }
    setAiConsentModalVisible(true);
    Alert.alert("AI consent required", "Enable AI Processing in Privacy settings to analyze photos and generate coaching.");
    return false;
  }

  async function deleteAccountPermanently() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    setDeleteAccountBusy(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/account/delete?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, { method: "DELETE", headers: { accept: "application/json" } });
      await safeJson(res);
      await AsyncStorage.clear();
      await signOut();
      Alert.alert("Account deleted", "Your account and related data were permanently deleted.");
    } catch (e) {
      Alert.alert("Delete failed", String(e?.message || e || "").slice(0, 220));
    } finally {
      setDeleteAccountBusy(false);
    }
  }

  function confirmDeleteAccount() {
    if (deleteAccountBusy) return;
    Alert.alert(
      "Delete account permanently?",
      "This will permanently delete scan history, coach data, goals, AI consent, and your login. This action cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete Permanently",
          style: "destructive",
          onPress: () => {
            void deleteAccountPermanently();
          },
        },
      ]
    );
  }

  async function signInWithOAuthProvider(provider, failTitle) {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }
    if (String(provider || "").trim().toLowerCase() === "apple") {
      Alert.alert("Apple login", "Apple Sign-In uses native login only. Please use Continue with Apple.");
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
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }

    setAuthBusy(true);
    try {
      if (!AppleAuthentication || typeof AppleAuthentication.signInAsync !== "function") {
        throw new Error("Apple Sign-In is unavailable in this app build.");
      }

      if (typeof AppleAuthentication.isAvailableAsync === "function") {
        const available = await AppleAuthentication.isAvailableAsync();
        if (!available) {
          throw new Error("Apple Sign-In is unavailable on this device.");
        }
      }

      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });

      const identityToken = String(credential?.identityToken || "").trim();
      if (!identityToken) {
        throw new Error("No identity token returned");
      }

      if (typeof supabase?.auth?.signInWithIdToken !== "function") {
        throw new Error("Supabase Apple ID-token login is unavailable in this app build.");
      }

      const payload = { provider: "apple", token: identityToken };
      const nonce = String(credential?.nonce || "").trim();
      if (nonce) payload.nonce = nonce;

      const { data, error } = await supabase.auth.signInWithIdToken(payload);
      if (error) throw error;
      if (!data?.session) {
        throw new Error("No session returned");
      }
    } catch (e) {
      console.log("apple login error:", e);
      Alert.alert("Apple login failed", String(e?.message || e));
    } finally {
      setAuthBusy(false);
    }
  }


async function openCamera(mode = "meal") {
    if (!ensureAiConsentOrAlert()) return;
    const normalizedMode = String(mode || "meal").trim().toLowerCase();
    if (normalizedMode === "upf_scan") {
      const remDay = num(usage?.remaining_day);
      const remMonth = num(usage?.remaining_month);
      if (remDay === 0 && remMonth === 0) {
        Alert.alert(
          "Out of scans",
          "Upgrade for more scans to use UPF Scanner.",
          [{ text: "Not now", style: "cancel" }, { text: "Upgrade", onPress: () => openPaywall("advanced") }]
        );
        return;
      }
      if (remDay <= 2 || remMonth <= 5) {
        Alert.alert(
          "Uses 1 scan",
          `You have ${remDay} left today, ${remMonth} this month.`,
          [
            { text: "Upgrade", onPress: () => openPaywall("advanced") },
            { text: "Continue", onPress: () => { setCameraMode("upf_scan"); setCamOpen(true); } },
          ]
        );
        return;
      }
    }
    try {
      const { granted } = permission || {};
      if (!granted) {
        const r = await requestPermission();
        if (!r?.granted) {
          Alert.alert("Camera permission", "Please allow camera access.");
          return;
        }
      }
    } catch (e) {
      Alert.alert("Camera permission", String((e && e.message) || e || "Please allow camera access.").slice(0, 180));
      return;
    }
    setCameraMode(normalizedMode);
    setCamOpen(true);
  }

  async function takePhoto() {
    try {
      if (!camRef.current) return;
      const photo = await camRef.current.takePictureAsync({ quality: 0.85, skipProcessing: true });
      if (!photo?.uri) return;
      const mode = String(cameraMode || "meal").trim().toLowerCase();
      if (mode === "supp_front") {
        setSupplementFrontUri(photo.uri);
        setSupplementStep((s) => Math.max(2, Math.round(num(s))));
      } else if (mode === "supp_back") {
        setSupplementBackUri(photo.uri);
        setSupplementStep((s) => Math.max(3, Math.round(num(s))));
      } else if (mode === "supp_seal") {
        setSealImage(photo.uri);
      } else if (mode === "menu_scan") {
        setMenuScanPhotoUri(photo.uri);
        setMenuScanError("");
        setMenuScanResult(null);
        setCamOpen(false);
        setCameraMode("meal");
        void scanRestaurantMenu(photo.uri);
        return;
      } else if (mode === "upf_scan") {
        setUpfScanError("");
        setUpfScanResult(null);
        setCamOpen(false);
        setCameraMode("meal");
        void scanUPFProduct(photo.uri);
        return;
      } else {
        setPhotoUri(photo.uri);
        const pending = goalCoachPendingCompletionRef.current;
        if (pending?.action_type === ACTION_OPEN_SCAN_CAMERA) {
          goalCoachAutoAnalyzeAfterPhotoRef.current = true;
          setActiveScreen("home");
          try {
            if (mainScrollRef.current && typeof mainScrollRef.current.scrollTo === "function") {
              mainScrollRef.current.scrollTo({ y: 0, animated: false });
            }
          } catch {}
        }
      }
      setCamOpen(false);
      setCameraMode("meal");
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
      closeBooleanStateSafely(setGoalsModal);
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

  async function fetchGoalPlan() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    const prevFetchUid = lastGoalPlanFetchUidRef.current;
    lastGoalPlanFetchUidRef.current = uid;
    if (prevFetchUid && prevFetchUid !== uid) setGoalPlan(null);
    setGoalPlanLoading(true);
    let cachedPlan = null;
    try {
      const raw = await AsyncStorage.getItem(goalPlanCacheKey(uid));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && parsed.plan_id) {
          cachedPlan = parsed;
          setGoalPlan(parsed);
        }
      }
    } catch (_) {}
    try {
      const data = await getGoalPlan(API_BASE, uid);
      if (data?.has_plan && data?.plan) {
        setGoalPlan(data.plan);
        try {
          await AsyncStorage.setItem(goalPlanCacheKey(uid), JSON.stringify(data.plan));
        } catch (_) {}
      } else if (!data?.has_plan) {
        if (cachedPlan) setGoalPlan(cachedPlan);
        else setGoalPlan(null);
      }
    } catch (e) {
      console.log("fetchGoalPlan failed", e);
      if (cachedPlan) setGoalPlan(cachedPlan);
      else setGoalPlan(null);
    } finally {
      setGoalPlanLoading(false);
    }
  }

  async function fetchGoalCoachDaily() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    setGoalCoachDailyLoading(true);
    try {
      const day = localDayISO();
      const hour = new Date().getHours();
      const url = withTimezoneQuery(`${API_BASE}/goal-coach/daily?user_id=${encodeURIComponent(uid)}&day=${encodeURIComponent(day)}&current_hour=${hour}`);
      const res = await fetch(url, { method: "GET", headers: { Accept: "application/json", "X-User-Id": uid } });
      const data = res.ok ? await res.json().catch(() => ({})) : {};
      setGoalCoachDaily(data);
    } catch (e) {
      console.log("fetchGoalCoachDaily failed", e);
      setGoalCoachDaily(null);
    } finally {
      setGoalCoachDailyLoading(false);
    }
  }

  async function fetchGoalCoachWeekly() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    setGoalCoachWeeklyLoading(true);
    try {
      const url = withTimezoneQuery(`${API_BASE}/goal-coach/weekly?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, { method: "GET", headers: { Accept: "application/json", "X-User-Id": uid } });
      const data = res.ok ? await res.json().catch(() => ({})) : {};
      setGoalCoachWeekly(data);
    } catch (e) {
      console.log("fetchGoalCoachWeekly failed", e);
      setGoalCoachWeekly(null);
    } finally {
      setGoalCoachWeeklyLoading(false);
    }
  }

  async function fetchGoalCoachJourney() {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    try {
      const data = await getJourney(API_BASE, uid, { day: localDayISO() });
      setJourneyData(data?.ok ? data : null);
    } catch (e) {
      setJourneyData(null);
    }
  }

  async function handleLetsGoSubmit(body) {
    const uid = userId || session?.user?.id;
    if (!uid) return;
    setGoalCoachCreateBusy(true);
    try {
      const data = await createGoalPlan(API_BASE, uid, body);
      if (data?.ok && data?.plan) {
        setGoalPlan(data.plan);
        try {
          await AsyncStorage.setItem(goalPlanCacheKey(uid), JSON.stringify(data.plan));
        } catch (_) {}
        setLetsGoModalVisible(false);
        await fetchGoalCoachDaily();
        await fetchGoalCoachWeekly();
      } else {
        Alert.alert("Could not create plan", "Please try again.");
      }
    } catch (e) {
      Alert.alert("Error", String(e?.message || e).slice(0, 120));
    } finally {
      setGoalCoachCreateBusy(false);
    }
  }

  function handleGoalCoachAction(action) {
    if (!action || !action.action_type) return;
    const uid = (userId || session?.user?.id) ?? "";
    const ctx = action.context || {};
    const sourceSurface = action.source_surface || "daily_coach";
    const meta = {
      source_surface: sourceSurface,
      action_type: action.action_type,
      goal_type: ctx.goal,
      reason: action.reason || ctx.reason,
      remaining_protein_g: ctx.remaining_protein_g,
      remaining_calories: ctx.remaining_calories,
      kickoff_active: ctx.kickoff_active,
      subscription_required: ctx.subscription_required,
    };
    trackGoalCoachActionClicked(API_BASE, uid, meta);

    const preferredMode = derivePreferredModeFromContext(ctx, action.action_type);
    const extendedContext = {
      ...ctx,
      source_surface: sourceSurface,
      action_type: action.action_type,
      action_reason: action.reason,
      coach_focus: ctx.coach_focus,
      preferred_mode: preferredMode,
    };
    setGoalCoachContext(extendedContext);

    switch (action.action_type) {
      case ACTION_OPEN_HEALTHY_NEARBY:
        setHealthyMapFilter(preferredModeToFilterKey(preferredMode));
        setActiveScreen("healthy_nearby");
        void loadHealthyPlacesNearby({ preserveFilter: true });
        break;
      case ACTION_OPEN_SCAN_CAMERA:
        goalCoachPendingCompletionRef.current = { ...meta, action_type: ACTION_OPEN_SCAN_CAMERA };
        setCamOpen(true);
        break;
      case ACTION_OPEN_SUPPLEMENT_SCAN:
        goalCoachPendingCompletionRef.current = { ...meta, action_type: ACTION_OPEN_SUPPLEMENT_SCAN };
        setBarcodeMode("supplement");
        setBarcodeOpen(true);
        break;
      case ACTION_OPEN_DAILY_SUMMARY:
        setActiveScreen("home");
        if (mainScrollRef.current && typeof mainScrollRef.current.scrollTo === "function") {
          mainScrollRef.current.scrollTo({ y: 0, animated: true });
        }
        break;
      case ACTION_OPEN_GOAL_PLAN:
        setActiveScreen("home");
        break;
      default:
        break;
    }
    trackGoalCoachDestinationOpened(API_BASE, uid, meta);
  }

  function scrollToGoalProgressSection() {
    setActiveScreen("home");
    setHomeHubTab("coach");
    requestAnimationFrame(() => {
      setTimeout(() => {
        try {
          mainScrollRef.current?.scrollTo({ y: 520, animated: true });
        } catch (_) {}
      }, 220);
    });
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

  async function showPostScanBannerIfNeeded() {
    const uid = userId || session?.user?.id;
    if (!uid || planAtLeast(plan, "pro")) return;
    try {
      const dismissed = await AsyncStorage.getItem(postScanBannerKey(uid));
      if (dismissed === "1") return;
      setPostScanUpgradeBannerVisible(true);
    } catch {}
  }

  function dismissPostScanBanner() {
    setPostScanUpgradeBannerVisible(false);
    const uid = userId || session?.user?.id;
    if (uid) {
      AsyncStorage.setItem(postScanBannerKey(uid), "1").catch(() => {});
    }
  }

  async function analyzePhoto() {
    if (!userId) return;
    if (!ensureAiConsentOrAlert()) return;
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
    analyzeCancelRef.current = false;
    setBusy(true);
    setResult(null);
    setScanProgress("Preparing photo…");

    try {
      const { prepareImageForScan } = await import("./utils/imageCompress");
      const uriToUpload = await prepareImageForScan(photoUri);
      setScanProgress("Sending for analysis…");
      const form = new FormData();
      form.append("file", {
        uri: uriToUpload,
        name: "meal.jpg",
        type: "image/jpeg",
      });
      // Send frequent meal summaries so backend can personalise (usual_meal_hint)
      const freqMeals = frequentMealSummaries(mealMemory);
      if (freqMeals.length) {
        form.append("frequent_meals", JSON.stringify(freqMeals));
      }

      const analyzeUrl = withTimezoneQuery(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`);
      const res = await fetch(analyzeUrl, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });

      let data = await safeJson(res);
      const queuedStatus = String(data?.status || "").trim().toLowerCase();
      if (res.status === 202 || queuedStatus === "queued" || queuedStatus === "running") {
        const jobId = String(data?.job_id || "").trim();
        if (!jobId) {
          throw new Error("Analyze job was queued without a job_id.");
        }
        const startedAt = Date.now();
        let pollDelay = 450;
        let finalPayload = null;
        let partialPayload = null;
        const hardTimeoutMs = 60000;
        while (Date.now() - startedAt < hardTimeoutMs) {
          if (analyzeCancelRef.current) {
            throw new Error("Analyze cancelled.");
          }
          const jobUrl = withTimezoneQuery(
            `${API_BASE}/jobs/${encodeURIComponent(jobId)}?user_id=${encodeURIComponent(userId)}`
          );
          const pollRes = await fetch(jobUrl, { method: "GET", headers: { accept: "application/json" } });
          const pollData = await safeJson(pollRes);
          const status = String(pollData?.status || "").trim().toLowerCase();
          const progressStage = String(pollData?.progress_stage || "").trim();
          if (progressStage === "enriching") {
            setScanProgress("Almost done…");
          } else if (status === "running") {
            setScanProgress("Analyzing…");
          } else if (status === "queued") {
            setScanProgress("Starting…");
          }
          const resultObj = pollData?.result && typeof pollData.result === "object" ? pollData.result : null;
          if (resultObj && !finalPayload) {
            partialPayload = resultObj;
            setResult(normalizeAnalyzeResult(resultObj));
          }
          if (status === "done") {
            finalPayload = resultObj;
            if (!finalPayload) {
              throw new Error("Analyze job completed but no result payload was returned.");
            }
            break;
          }
          if (status === "failed") {
            const errMsg = errorToMessage(
              pollData?.error || pollData?.message || "Analyze failed while processing image.",
              0
            );
            throw new Error(errMsg || "Analyze failed while processing image.");
          }
          await sleepMs(pollDelay);
          pollDelay = Math.min(1800, Math.round(pollDelay * 1.18));
        }
        if (!finalPayload) {
          if (partialPayload) {
            data = partialPayload;
          } else {
            throw new Error("Analyze timed out. Please try again.");
          }
        } else {
          data = finalPayload;
        }
      }
      const normalized = normalizeAnalyzeResult(data);
      // Enrich with local meal memory if backend didn't return usual_meal_hint
      if (!normalized.usual_meal_hint && mealMemory) {
        const memHit = findMealInMemory(mealMemory, normalized.items);
        if (memHit && memHit.count >= 2) {
          normalized.usual_meal_hint = {
            label: "Frequent meal",
            line: `Is this your usual ${memHit.label}? Scanned ${memHit.count} time${memHit.count === 1 ? "" : "s"} before.`,
          };
        }
      }
      setResult(normalized);
      const latestScanId = String(data?.scan_id || data?.latest_scan_id || data?.analysis_id || normalized?.analysis_id || "").trim();
      const latestScanTs = String(data?.latest_scan_ts || nowISO()).trim();
      if (latestScanId) {
        setLatestScanMeta({ id: latestScanId, ts: latestScanTs });
      }
      if (data?.fat_loss_intelligence && typeof data.fat_loss_intelligence === "object") {
        const quickCoach = sanitizeCoachForDiet(normalizeCoachDaily(data.fat_loss_intelligence, localDayISO()));
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
      const pending = goalCoachPendingCompletionRef.current;
      if (pending?.action_type === ACTION_OPEN_SCAN_CAMERA && (userId || session?.user?.id)) {
        trackGoalCoachActionCompleted(API_BASE, userId || session?.user?.id, {
          ...pending,
          completion_type: "scan_result_returned",
        });
        goalCoachPendingCompletionRef.current = null;
      }
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
      // Record meal items into memory for future "your usual meal" recognition
      recordMealToMemory(userId, data?.items).catch(() => {});
      const dailyTotalsVersion = normalizeVersionToken(data?.daily_totals_version || data?.state_signature || "");
      scheduleDailyCoachRefresh({
        latestScanId,
        latestScanTs,
        mealId: latestScanId || String(normalized?.analysis_id || "").trim(),
        analysisId: String(normalized?.analysis_id || latestScanId || "").trim(),
        dailyTotalsVersion,
        pollForLatest: Boolean(latestScanId),
        refreshServer: true,
        fastMode: true,
        trigger: "analyze",
      });
      if (goalPlan) void fetchGoalCoachDaily();
      const uid = userId || session?.user?.id;
      if (uid && goalPlan && (latestScanId || normalized?.analysis_id)) {
        submitGoalCoachCheckIn(API_BASE, uid, {
          day: localDayISO(),
          analysis_id: latestScanId || String(normalized?.analysis_id || "").trim(),
        })
          .then(() => {
            void fetchGoalCoachJourney();
            void fetchGoalCoachDaily();
          })
          .catch((e) => {
            if (e?.status === 402) openPaywall("advanced");
          });
      }
      void fetchCoachVoice(normalized, true);
      void fetchWeeklyReport(true);
      void fetchWeeklyCoachProgress(true);
      await maybeSendScanUpgradeNudge(photoScansAfterThisAnalyze);
      if (photoScansAfterThisAnalyze === 1 && !planAtLeast(plan, "pro")) {
        void showPostScanBannerIfNeeded();
      }
      if (isDeviceHealthAvailable()) {
        const kcal = num(normalized?.totals?.kcal ?? normalized?.totals?.total_kcal ?? data?.total_kcal);
        const protein = num(normalized?.totals?.protein_g ?? data?.totals?.protein_g);
        const carbs = num(normalized?.totals?.carbs_g ?? data?.totals?.carbs_g);
        const fat = num(normalized?.totals?.fat_g ?? data?.totals?.fat_g);
        const fiber = num(normalized?.micros?.fiber_g ?? data?.totals?.micros?.fiber_g);
        if (Number.isFinite(kcal) && kcal >= 0) {
          writeNutritionToDeviceHealth(
            {
              dateIso: latestScanTs || nowISO(),
              energyKcal: kcal,
              proteinG: protein,
              carbsG: carbs,
              fatG: fat,
              fiberG: fiber,
              foodName: "CalorieClick meal",
            },
            () => {}
          );
        }
      }
    } catch (e) {
      setFliPending(false);
      const msg = String((e && e.message) || e || "").trim();
      if (!/analyze cancelled/i.test(msg)) {
        Alert.alert("Analyze failed", msg.slice(0, 220));
      }
    } finally {
      setBusy(false);
      setScanProgress("");
      analyzeCancelRef.current = false;
      goalCoachAutoAnalyzeAfterPhotoRef.current = false;
    }
  }

  useEffect(() => {
    if (!goalCoachAutoAnalyzeAfterPhotoRef.current) return;
    if (!photoUri) return;
    if (busy) return;
    // Best-effort auto-analyze to reduce Goal Coach scan completion friction.
    setTimeout(() => {
      if (goalCoachAutoAnalyzeAfterPhotoRef.current && !busy && photoUri) {
        void analyzePhoto();
      }
    }, 250);
  }, [photoUri, busy]);

  function cancelAnalyzeJob() {
    analyzeCancelRef.current = true;
    setBusy(false);
    setFliPending(false);
    setFliSyncing(false);
  }

  function nextSupplementStep() {
    if (supplementStep === 1 && !supplementFrontUri) {
      Alert.alert("Front label required", "Capture the front label to continue.");
      return;
    }
    setSupplementStep((s) => Math.min(SUPPLEMENT_TOTAL_STEPS, Math.round(num(s)) + 1));
  }

  function prevSupplementStep() {
    setSupplementStep((s) => Math.max(1, Math.round(num(s)) - 1));
  }

  function skipSupplementStep() {
    if (supplementStep <= 1) return;
    setSupplementStep((s) => Math.min(SUPPLEMENT_TOTAL_STEPS, Math.round(num(s)) + 1));
  }

  async function scanSupplement() {
    if (!userId) return;
    if (!ensureAiConsentOrAlert()) return;
    const barcodeText = String(supplementBarcode || "").trim();
    const batchText = String(supplementBatchNumber || "").trim();
    if (!supplementFrontUri || (!barcodeText && !batchText)) {
      Alert.alert(
        "Details required",
        "Capture the front label and provide either barcode or batch code before verification."
      );
      return;
    }
    const backUriToUse = supplementBackUri || supplementFrontUri;
    const sealUriToUse = sealImage || null;
    setSupplementBusy(true);
    setSupplementProcessingVisible(true);
    try {
      const form = new FormData();
      form.append("front_image", {
        uri: supplementFrontUri,
        name: "supp-front.jpg",
        type: "image/jpeg",
      });
      form.append("back_image", {
        uri: backUriToUse,
        name: "supp-back.jpg",
        type: "image/jpeg",
      });
      if (sealUriToUse) {
        form.append("seal_image", {
          uri: sealUriToUse,
          name: "supp-seal.jpg",
          type: "image/jpeg",
        });
      }
      form.append("product_type", "whey_protein");
      if (barcodeText) form.append("barcode", barcodeText);
      if (batchText) form.append("batch_number", batchText);
      form.append("region", regionFromLocale());
      form.append("proof_mode", supplementProofMode ? "1" : "0");

      const url = withTimezoneQuery(
        `${API_BASE}/supplement/scan?user_id=${encodeURIComponent(userId)}`
      );
      const res = await fetch(url, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });
      const data = await safeJson(res);
      setSupplementResult(data && typeof data === "object" ? data : null);
      setSupplementBreakdownOpen(false);
      setSupplementStep(SUPPLEMENT_TOTAL_STEPS);
      if (String(data?.barcode || "").trim()) setSupplementBarcode(String(data?.barcode || "").trim());
      if (String(data?.batch_number || "").trim()) setSupplementBatchNumber(String(data?.batch_number || "").trim());
      const pending = goalCoachPendingCompletionRef.current;
      if (data && pending?.action_type === ACTION_OPEN_SUPPLEMENT_SCAN && (userId || session?.user?.id)) {
        trackGoalCoachActionCompleted(API_BASE, userId || session?.user?.id, {
          ...pending,
          completion_type: "supplement_scan_completed",
        });
        goalCoachPendingCompletionRef.current = null;
      }
    } catch (e) {
      Alert.alert(
        "Verification unavailable",
        "We couldn’t complete structural verification right now. Please try again in a moment."
      );
    } finally {
      setSupplementBusy(false);
      setSupplementProcessingVisible(false);
    }
  }

  async function getCurrentCoords() {
    let priorError = null;
    try {
      const mod = await import("expo-location");
      if (mod && typeof mod.requestForegroundPermissionsAsync === "function") {
        const perm = await mod.requestForegroundPermissionsAsync();
        if (!perm?.granted) {
          throw new Error("Location permission denied");
        }
        const loc = await mod.getCurrentPositionAsync({
          accuracy: mod.Accuracy?.Balanced ?? undefined,
        });
        const lat = num(loc?.coords?.latitude);
        const lng = num(loc?.coords?.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
          throw new Error("Location unavailable");
        }
        return { lat, lng };
      }
    } catch (e) {
      priorError = e;
    }

    try {
      return await new Promise((resolve, reject) => {
        const geo = globalThis?.navigator?.geolocation;
        if (!geo || typeof geo.getCurrentPosition !== "function") {
          reject(new Error("Location service unavailable"));
          return;
        }
        geo.getCurrentPosition(
          (pos) => {
            const lat = num(pos?.coords?.latitude);
            const lng = num(pos?.coords?.longitude);
            if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
              reject(new Error("Location unavailable"));
              return;
            }
            resolve({ lat, lng });
          },
          (err) => {
            reject(new Error(String(err?.message || "Location fetch failed")));
          },
          { enableHighAccuracy: false, timeout: 10000, maximumAge: 120000 }
        );
      });
    } catch (fallbackErr) {
      const priorMsg = String((priorError && priorError.message) || "").trim();
      if (priorMsg) throw new Error(priorMsg);
      throw fallbackErr;
    }
  }

  async function loadHealthyPlacesNearby(options = {}) {
    const opts = options && typeof options === "object" ? options : {};
    try {
      const seedCoords = opts?.coords && typeof opts.coords === "object" ? opts.coords : null;
      const coords = seedCoords || healthyPlaceCoords || (await getCurrentCoords());
      const lat = num(coords?.lat);
      const lng = num(coords?.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        throw new Error("Could not read location.");
      }
      const radiusM = Number.isFinite(num(opts?.radius_m))
        ? Math.max(500, Math.min(50000, num(opts.radius_m)))
        : DEFAULT_HEALTHY_RADIUS_M;

      const goal = String(opts?.goal || resolveLunchGoal()).trim();
      const cutMode = typeof opts?.cut_mode === "boolean" ? opts.cut_mode : goal === "fat_loss";

      const dietQ = dietPreferenceQueryFromCoachStyle(coachProfile?.diet_style);
      const contextKey = buildHealthyNearbyContextKey({
        lat,
        lng,
        radiusM,
        goal,
        cutMode,
        filterKey: healthyMapFilter,
        dietPreference: dietQ || "omnivore",
      });

      const prevCoords = healthyPlaceCoords;
      const materialMove = hasMaterialLocationChange(prevCoords, { lat, lng }, 200);
      const keyChanged = contextKey && contextKey !== healthyNearbyContextKeyRef.current;

      if (materialMove || keyChanged || !healthyPlaces.length) {
        healthyNearbyContextKeyRef.current = contextKey;
        setHealthyPlaceCoords({ lat, lng });
        setHealthyPlacesBusy(true);
        setHealthyPlacesError("");
        setHealthyNearbyRefreshing(true);
        setSelectedHealthyPlaceId("");
      }

      const reqSeq = healthyPlacesReqSeqRef.current + 1;
      healthyPlacesReqSeqRef.current = reqSeq;

      const remainingCalories = Number.isFinite(num(opts?.remaining_calories))
        ? Math.max(0, num(opts?.remaining_calories))
        : Number.isFinite(num(remainingToday?.kcal))
        ? Math.max(0, num(remainingToday?.kcal))
        : null;
      const remainingProtein = Number.isFinite(num(opts?.remaining_protein_g))
        ? Math.max(0, num(opts?.remaining_protein_g))
        : Number.isFinite(num(remainingToday?.protein_g))
        ? Math.max(0, num(remainingToday?.protein_g))
        : null;
      const params = [
        "lat=" + encodeURIComponent(lat),
        "lng=" + encodeURIComponent(lng),
        "radius=" + encodeURIComponent(radiusM),
        "limit=" + encodeURIComponent(Math.max(8, Math.min(40, num(opts?.limit) || 12))),
      ];
      if (remainingCalories !== null) params.push("remaining_calories=" + encodeURIComponent(remainingCalories));
      if (remainingProtein !== null) params.push("remaining_protein_g=" + encodeURIComponent(remainingProtein));
      if (goal) params.push("goal=" + encodeURIComponent(goal));
      if (cutMode) params.push("cut_mode=true");
      const sortMode = String(opts?.sortMode || "flat_score").trim().toLowerCase();
      if (sortMode === "sectioned" || sortMode === "flat_score") {
        params.push("sort_mode=" + encodeURIComponent(sortMode));
      } else {
        params.push("sort_mode=" + encodeURIComponent("flat_score"));
      }
      const uid = userId || (session?.user?.id ?? null);
      if (uid) {
        params.push("user_id=" + encodeURIComponent(String(uid)));
      }
      if (dietQ) {
        params.push("diet_preference=" + encodeURIComponent(dietQ));
      }
      const drList = Array.isArray(coachProfile?.dietary_restrictions) ? coachProfile.dietary_restrictions : [];
      if (drList.length) {
        params.push("dietary_restrictions=" + encodeURIComponent(drList.join(",")));
      }
      const aeList = Array.isArray(coachProfile?.allergen_exclude) ? coachProfile.allergen_exclude : [];
      if (aeList.length) {
        params.push("allergen_exclude=" + encodeURIComponent(aeList.join(",")));
      }

      const url = withTimezoneQuery(`${API_BASE}/places/healthy?${params.join("&")}`);
      const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
      const data = await safeJson(res);
      if (!shouldApplyHealthyNearbyResponse(reqSeq, healthyPlacesReqSeqRef.current, contextKey, healthyNearbyContextKeyRef.current)) {
        healthyNearbyStaleIgnoredCountRef.current += 1;
        return;
      }
      const normalized = normalizeHealthyPlacesResponse(data);
      const list = normalized.items;
      setHealthySortMode(normalized.sortMode);
      setHealthySections(normalized.sections ?? null);

      if (typeof __DEV__ !== "undefined" && __DEV__ && data?._debug) {
        console.log("[Healthy Nearby] pipeline debug:", data._debug);
      }

      setHealthyPlaces(list);
      setHealthyViewMode("map");
      if (!opts?.preserveFilter) setHealthyMapFilter("all");

      // Phase 1: update shared nearby snapshot + persist for cached-first rendering.
      try {
        const uidSnap = userId || (session?.user?.id ?? null);
        if (uidSnap) {
          const nextSnap = {
            version: NEARBY_SNAPSHOT_CACHE_VERSION,
            generated_at_ms: Date.now(),
            coords: { lat, lng, accuracy_m: num(coords?.accuracy_m ?? coords?.accuracy) || undefined },
            ranked_places: list,
            lunch_decision: nearbySnapshot?.lunch_decision || null,
            selected_place_id: "",
            source: "fresh",
          };
          setNearbySnapshot(nextSnap);
          AsyncStorage.setItem(nearbySnapshotKey(uidSnap), JSON.stringify(nextSnap)).catch(() => {});
        }
      } catch (_) {}

      // Fire a lightweight decision event for this load (one per call, not per card).
      if (uid && list.length) {
        const payload = buildDecisionEventPayload(list[0], "recommendation_viewed", {
          userId: uid,
          goal,
          timeOfDay: "",
          tab: "healthy_nearby",
        });
        postMealDecisionEvent(payload);
      }

      const preferredIndex = findMatchingHealthyPlaceIndex(opts?.preferredCard, list);
      const selectedIndex = preferredIndex >= 0 ? preferredIndex : list.length ? 0 : -1;
      const selectedPlace = selectedIndex >= 0 ? list[selectedIndex] : null;

      setSelectedHealthyPlaceId(
        selectedPlace ? healthyPlaceStableId(selectedPlace, selectedIndex) : ""
      );

      if (selectedPlace && Number.isFinite(num(selectedPlace?.lat)) && Number.isFinite(num(selectedPlace?.lng))) {
        setHealthyMapFocusCoords({ lat: num(selectedPlace.lat), lng: num(selectedPlace.lng) });
      } else {
        setHealthyMapFocusCoords(null);
      }

      void fetchSmartAlerts({ coords: { lat, lng }, force: false });

      if (uid && smartAlertState?.enabled === true && Number.isFinite(lat) && Number.isFinite(lng)) {
        requestSmartAlertPush({
          userId: uid,
          lat,
          lng,
          tonePreference: coachProfile?.tone_preference || "supportive",
          goal: goal || "",
          dryRun: false,
        }).catch(() => {});
      }

      if (!list.length) {
        const noResultsReason = String(data?._no_results_reason || "").trim();
        if (noResultsReason === "places_api_key_not_configured") {
          setHealthyPlacesError("Places search is not configured on this server. Contact support.");
        } else if (noResultsReason === "api_error_403" || noResultsReason === "api_error_401") {
          setHealthyPlacesError("Google Places (New) is not enabled or the API key is invalid. Enable \"Places API (New)\" in Google Cloud and ensure the key has access.");
        } else if (noResultsReason.startsWith("api_error_")) {
          setHealthyPlacesError("Could not load places from Google (server error). Try again later or contact support.");
        } else if (noResultsReason === "api_request_failed") {
          setHealthyPlacesError("Network or server error while loading places. Check your connection and try again.");
        } else {
          setHealthyPlacesError("No food places found nearby. Try moving to a more central location.");
        }
      }
      return list;
    } catch (e) {
      if (!shouldApplyHealthyNearbyResponse(healthyPlacesReqSeqRef.current, healthyPlacesReqSeqRef.current, healthyNearbyContextKeyRef.current, healthyNearbyContextKeyRef.current)) {
        return [];
      }
      const msg = String((e && e.message) || e || "").trim() || "Could not load nearby places.";
      setHealthyPlacesError(msg.slice(0, 220));
      setHealthyPlaces([]);
      setHealthySections(null);
      setSelectedHealthyPlaceId("");
      setHealthyMapFocusCoords(null);
      return [];
    } finally {
      setHealthyPlacesBusy(false);
      setHealthyNearbyRefreshing(false);
    }
  }

  async function fetchSmartAlerts(opts = {}) {
    const now = Date.now();
    if (!opts.force && now - smartAlertsLastFetchRef.current < SMART_ALERTS_COOLDOWN_MS) return;
    const coords = opts.coords || healthyPlaceCoords;
    if (!coords || !Number.isFinite(num(coords?.lat)) || !Number.isFinite(num(coords?.lng))) return;

    const state = smartAlertState || (await getSmartAlertState());
    if (state && !state.enabled) return;

    setSmartAlertsBusy(true);
    smartAlertsLastFetchRef.current = now;
    try {
      const params = buildSmartAlertFetchParams({
        userId: userId || session?.user?.id,
        lat: num(coords.lat),
        lng: num(coords.lng),
        remainingCalories: (remainingToday?.kcal != null) ? num(remainingToday?.kcal) : null,
        remainingProteinG: (remainingToday?.protein_g != null) ? num(remainingToday?.protein_g) : null,
        goal: resolveLunchGoal(),
        ignoredStreak: state?.ignored_streak_local ?? 0,
        diet_preference: dietPreferenceQueryFromCoachStyle(coachProfile?.diet_style),
      });
      const { candidates } = await fetchSmartFoodAlertCandidates(params, false, withTimezoneQuery);
      const filtered = state ? filterCandidatesForDisplay(candidates, state) : candidates;
      setSmartAlertCandidates(filtered.slice(0, 10));
    } catch (e) {
      if (typeof __DEV__ !== "undefined" && __DEV__) console.log("[SmartAlerts] fetch failed", String(e));
      setSmartAlertCandidates([]);
    } finally {
      setSmartAlertsBusy(false);
    }
  }

  function resolveLunchGoal() {
    const goalType = String(coachProfile?.goal_type || "").trim().toLowerCase();
    if (goalType === "fat_loss") return "fat_loss";
    if (goalType === "lean_gain") return "muscle_gain";
    if (goalType === "recomposition") return "high_protein";
    return "";
  }

  function formatDistanceFromMeters(distanceMeters) {
    const meters = num(distanceMeters);
    if (!Number.isFinite(meters) || meters <= 0) return "";
    if (meters >= 1000) return round1(meters / 1000) + " km away";
    return Math.round(meters) + " m away";
  }

  function extractSwapSuggestions(...sources) {
    const out = [];
    const seen = new Set();

    function pushLine(raw) {
      const text = String(raw || "").trim().replace(/\s+/g, " ");
      if (!text) return;
      const key = text.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(text);
    }

    function asSkipLine(raw) {
      const text = String(raw || "").trim();
      if (!text) return "";
      return /^skip\s+/i.test(text) ? text : `Skip ${text}`;
    }

    function asAddLine(raw) {
      const text = String(raw || "").trim();
      if (!text) return "";
      return /^(add|choose|pick|go for)\s+/i.test(text) ? text : `Add ${text}`;
    }

    for (const src of sources) {
      if (!src || typeof src !== "object") continue;
      const swaps = Array.isArray(src?.swap_suggestions) ? src.swap_suggestions : [];
      swaps.forEach((row) => pushLine(row));

      if (Array.isArray(src?.skip_items)) {
        src.skip_items.forEach((row) => pushLine(asSkipLine(row)));
      }
      if (Array.isArray(src?.add_items)) {
        src.add_items.forEach((row) => pushLine(asAddLine(row)));
      }

      pushLine(src?.swap_suggestion);
      pushLine(src?.better_swap);
    }

    return out.slice(0, 3);
  }

  function normalizeFeedbackPlaceId(card) {
    const raw = String(card?.place_id || card?.tracking?.place_id || "").trim();
    if (raw) return raw;
    const fallback = String(card?.place_name || "unknown place")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return fallback ? "name:" + fallback : "name:unknown-place";
  }

  async function logRecommendationEvent(eventName, card, metadata = {}) {
    const event = String(eventName || "").trim().toLowerCase();
    if (!event) return;

    const payload = card && typeof card === "object" ? card : {};
    const placeId = normalizeFeedbackPlaceId(payload);
    const item = String(payload?.recommended_order || payload?.tracking?.item || "").trim();
    const uid = String(userId || "").trim();
    const safeMetadata = (metadata && typeof metadata === "object") ? metadata : {};

    void rememberWeeklyCoachChoice(uid, event, payload, safeMetadata);

    try {
      await apiPost("/places/recommendation-feedback", {
        event,
        place_id: placeId,
        item,
        user_id: uid,
        session_id: String(uid || "anon"),
        metadata: {
          source: "lunch_decision_screen",
          card_type: String(payload?.card_type || ""),
          ...safeMetadata,
        },
      });
    } catch {
      // Feedback logging is best-effort and must never block meal decisions.
    }
  }

  function buildLunchShareMessage(card) {
    const payload = card && typeof card === "object" ? card : {};
    const shareCard = payload?.share_card && typeof payload.share_card === "object" ? payload.share_card : {};
    const realityCheck = payload?.reality_check && typeof payload.reality_check === "object" ? payload.reality_check : {};
    const realityShare =
      realityCheck?.share_card && typeof realityCheck.share_card === "object" ? realityCheck.share_card : {};

    const activeCard = Object.keys(shareCard).length ? shareCard : realityShare;

    const title = String(activeCard?.title || "Smarter Order").trim();
    const place = String(
      activeCard?.restaurant_name || activeCard?.place_name || payload?.place_name || "Nearby pick"
    ).trim();
    const order = String(
      activeCard?.order_name ||
        activeCard?.best_order ||
        activeCard?.smarter_order ||
        payload?.recommended_order ||
        "Lighter menu option"
    ).trim();
    const activeCardCalories = finiteNumOrNull(activeCard?.estimated_calories);
    const smarterCalories = finiteNumOrNull(realityShare?.smarter_calories);
    const payloadCalories = finiteNumOrNull(payload?.estimated_calories);
    const calories = activeCardCalories !== null
      ? Math.round(activeCardCalories)
      : smarterCalories !== null
      ? Math.round(smarterCalories)
      : payloadCalories !== null
      ? Math.round(payloadCalories)
      : null;
    const activeCardProtein = finiteNumOrNull(activeCard?.estimated_protein_g);
    const payloadProtein = finiteNumOrNull(payload?.estimated_protein_g);
    const protein = activeCardProtein !== null
      ? Math.round(activeCardProtein)
      : payloadProtein !== null
      ? Math.round(payloadProtein)
      : null;
    const activeCardCaloriesSaved = finiteNumOrNull(activeCard?.calories_saved);
    const realityShareCaloriesSaved = finiteNumOrNull(realityShare?.calories_saved);
    const realityCheckCaloriesSaved = finiteNumOrNull(realityCheck?.calories_saved);
    const caloriesSaved = activeCardCaloriesSaved !== null
      ? Math.max(0, Math.round(activeCardCaloriesSaved))
      : realityShareCaloriesSaved !== null
      ? Math.max(0, Math.round(realityShareCaloriesSaved))
      : realityCheckCaloriesSaved !== null
      ? Math.max(0, Math.round(realityCheckCaloriesSaved))
      : null;
    const heroLine =
      String(activeCard?.hero_line || "").trim() ||
      (caloriesSaved !== null && caloriesSaved > 0 ? "You saved " + caloriesSaved + " calories" : "");
    const badge = String(
      activeCard?.badge ||
        (Array.isArray(activeCard?.badges) && activeCard.badges[0]) ||
        (Array.isArray(shareCard?.badges) && shareCard.badges[0]) ||
        ""
    ).trim();
    const subtitle = String(activeCard?.subtitle || payload?.why_this_works || "").trim();

    const lines = [title, "", "Restaurant: " + place, "Order: " + order];
    if (calories !== null) lines.push("Calories: " + calories + " kcal");
    if (protein !== null) lines.push("Protein: " + protein + "g");
    if (heroLine) lines.push("", heroLine);
    if (badge) lines.push("Badge: " + badge);
    if (subtitle) lines.push("", subtitle);
    lines.push("", "CalorieClick AI");
    return lines.join("\n");
  }

  async function shareLunchDecisionCard(card) {
    const payload = card && typeof card === "object" ? card : {};
    void logRecommendationEvent("share_card_opened", payload, { action: "open_share_sheet" });

    try {
      await Share.share({ message: buildLunchShareMessage(payload) });
      void logRecommendationEvent("share_action_triggered", payload, { action: "native_share" });
    } catch (e) {
      Alert.alert("Share unavailable", String((e && e.message) || e || "").slice(0, 180));
    }
  }

  async function loadLunchDecision() {
    if (lunchDecisionInFlightRef.current) return;
    const reqSeq = lunchDecisionReqSeqRef.current + 1;
    lunchDecisionReqSeqRef.current = reqSeq;
    lunchDecisionInFlightRef.current = true;
    setLunchDecisionBusy(true);
    setLunchDecisionError("");
    try {
      const coords = healthyPlaceCoords || (await getCurrentCoords());
      if (reqSeq !== lunchDecisionReqSeqRef.current) return;
      const lat = num(coords?.lat);
      const lng = num(coords?.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        throw new Error("Could not read location.");
      }

      setHealthyPlaceCoords({ lat, lng });

      const remainingCalories = Number.isFinite(num(remainingToday?.kcal)) ? Math.max(0, num(remainingToday?.kcal)) : null;
      const remainingProtein = Number.isFinite(num(remainingToday?.protein_g))
        ? Math.max(0, num(remainingToday?.protein_g))
        : null;
      const targetCalories = Number.isFinite(num(goals?.kcal)) ? Math.max(0, num(goals?.kcal)) : null;
      const targetProtein = Number.isFinite(num(goals?.protein_g)) ? Math.max(0, num(goals?.protein_g)) : null;
      const consumedCalories = Number.isFinite(
        num(dailySummary?.total_kcal ?? dailySummary?.totals?.kcal ?? dailySummary?.totals?.total_kcal)
      )
        ? Math.max(0, num(dailySummary?.total_kcal ?? dailySummary?.totals?.kcal ?? dailySummary?.totals?.total_kcal))
        : null;
      const consumedProtein = Number.isFinite(num(dailySummary?.totals?.protein_g))
        ? Math.max(0, num(dailySummary?.totals?.protein_g))
        : null;
      const currentHour = new Date().getHours();
      const goal = resolveLunchGoal();
      const cutMode = goal === "fat_loss";

      const params = [
        "lat=" + encodeURIComponent(lat),
        "lng=" + encodeURIComponent(lng),
        "radius=" + encodeURIComponent(DEFAULT_HEALTHY_RADIUS_M),
      ];
      if (remainingCalories !== null) params.push("remaining_calories=" + encodeURIComponent(remainingCalories));
      if (remainingProtein !== null) params.push("remaining_protein_g=" + encodeURIComponent(remainingProtein));
      if (targetCalories !== null) params.push("target_calories=" + encodeURIComponent(targetCalories));
      if (consumedCalories !== null) params.push("consumed_calories=" + encodeURIComponent(consumedCalories));
      if (targetProtein !== null) params.push("target_protein_g=" + encodeURIComponent(targetProtein));
      if (consumedProtein !== null) params.push("consumed_protein_g=" + encodeURIComponent(consumedProtein));
      if (Number.isFinite(currentHour)) params.push("current_hour=" + encodeURIComponent(Math.max(0, Math.min(23, currentHour))));
      if (goal) params.push("goal=" + encodeURIComponent(goal));
      if (cutMode) params.push("cut_mode=true");
      const lunchDietQ = dietPreferenceQueryFromCoachStyle(coachProfile?.diet_style);
      if (lunchDietQ) params.push("diet_preference=" + encodeURIComponent(lunchDietQ));

      const url = withTimezoneQuery(API_BASE + "/places/lunch-decision?" + params.join("&"));
      // Run decision API and map (healthy places) in parallel for faster perceived load.
      const decisionPromise = fetch(url, { method: "GET", headers: { accept: "application/json" } }).then(safeJson);
      const placesPromise = loadHealthyPlacesNearby({
        coords: { lat, lng },
        remaining_calories: remainingCalories,
        remaining_protein_g: remainingProtein,
        goal,
        cut_mode: cutMode,
      });
      const [data, placesList] = await Promise.all([decisionPromise, placesPromise]);
      if (reqSeq !== lunchDecisionReqSeqRef.current) return;
      const payload = data && typeof data === "object" ? data : {};
      let cards = Array.isArray(payload?.cards) ? payload.cards.filter((x) => x && typeof x === "object") : [];
      const list = Array.isArray(placesList) ? placesList : [];

      // Align "Best right now" with list/map: use list's #1 as the top decision card so they match.
      if (list.length > 0) {
        const listFirst = list[0];
        const matchIndex = findMatchingHealthyPlaceIndex(listFirst, cards);
        if (matchIndex >= 0) {
          const firstCard = { ...cards[matchIndex], card_type: "best_right_now" };
          const rest = cards.filter((_, i) => i !== matchIndex);
          cards = [firstCard, ...rest];
        } else {
          // List's #1 not in decision cards: prepend a card from the list so "Best right now" = list #1.
          const place = listFirst;
          const syntheticCard = {
            card_type: "best_right_now",
            label: "Best right now",
            place_id: place?.place_id || place?.id,
            place_name: place?.place_name ?? place?.name ?? "Nearby",
            place_lat: num(place?.lat),
            place_lng: num(place?.lng),
            lat: num(place?.lat),
            lng: num(place?.lng),
            distance_meters: place?.distance_meters ?? place?.distance,
            recommended_order: String(place?.best_item_name ?? place?.best_order ?? "").trim() || undefined,
            recommended_order_label: String(place?.best_item_name ?? place?.best_order ?? "").trim() || undefined,
            estimated_calories: num(place?.best_item_calories ?? place?.estimated_calories),
            estimated_protein_g: num(place?.best_item_protein ?? place?.estimated_protein_g),
            why_this_works: String(place?.rank_reason_short ?? place?.why_this_ranked_here ?? "Top pick nearby.").trim() || "Good fit for today.",
          };
          cards = [syntheticCard, ...cards];
        }
      }

      const bestCard =
        cards.find((card) => String(card?.card_type || "").trim().toLowerCase() === "best_right_now") ||
        cards[0] ||
        null;
      const selectedPlaceId = String(payload?.selected_place_id || bestCard?.place_id || "").trim();
      const selectedPlaceName = String(payload?.selected_place_name || bestCard?.place_name || "").trim();
      const selectedPlaceLat = num(payload?.selected_place_lat ?? bestCard?.place_lat ?? bestCard?.lat);
      const selectedPlaceLng = num(payload?.selected_place_lng ?? bestCard?.place_lng ?? bestCard?.lng);

      setLunchDecision({
        ...payload,
        cards,
        selected_place_id: selectedPlaceId,
        selected_place_name: selectedPlaceName,
        selected_place_lat: Number.isFinite(selectedPlaceLat) ? selectedPlaceLat : null,
        selected_place_lng: Number.isFinite(selectedPlaceLng) ? selectedPlaceLng : null,
      });
      void fetchWeeklyCoachProgress(false);

      // Phase 1: update shared nearby snapshot + persist (keeps endpoints intact).
      try {
        const uidSnap = userId || (session?.user?.id ?? null);
        if (uidSnap) {
          const nextSnap = {
            version: NEARBY_SNAPSHOT_CACHE_VERSION,
            generated_at_ms: Date.now(),
            coords: { lat, lng, accuracy_m: num(coords?.accuracy_m ?? coords?.accuracy) || undefined },
            ranked_places: Array.isArray(list) ? list : [],
            lunch_decision: { ...payload, cards },
            selected_place_id: "",
            source: "mixed",
          };
          setNearbySnapshot(nextSnap);
          AsyncStorage.setItem(nearbySnapshotKey(uidSnap), JSON.stringify(nextSnap)).catch(() => {});
        }
      } catch (_) {}

      // Sync map selection to decision's best card using the already-loaded places list.
      const preferredIndex = findMatchingHealthyPlaceIndex(bestCard, list);
      const selectedIndex = preferredIndex >= 0 ? preferredIndex : list.length ? 0 : -1;
      const selectedPlace = selectedIndex >= 0 ? list[selectedIndex] : null;
      if (selectedPlace) {
        setSelectedHealthyPlaceId(healthyPlaceStableId(selectedPlace, selectedIndex));
        if (Number.isFinite(num(selectedPlace?.lat)) && Number.isFinite(num(selectedPlace?.lng))) {
          setHealthyMapFocusCoords({ lat: num(selectedPlace.lat), lng: num(selectedPlace.lng) });
        } else {
          setHealthyMapFocusCoords(null);
        }
      }

      if (cards.length) {
        setHealthyViewMode("map");
        cards.slice(0, 3).forEach((card, idx) => {
          void logRecommendationEvent("recommendation_shown", card, {
            position: idx + 1,
            generated_at: String(payload?.generated_at || ""),
          });
        });
      } else {
        const noResultsReason = String(payload?._no_results_reason || "").trim();
        if (noResultsReason === "places_api_key_not_configured") {
          setLunchDecisionError("Places search is not configured on this server. Contact support.");
        } else if (noResultsReason === "no_places_returned_by_api" || noResultsReason === "api_request_failed") {
          setLunchDecisionError("No food places found nearby. Try moving to a more central location or check location permissions.");
        } else if (noResultsReason === "api_error_403" || noResultsReason === "api_error_401") {
          setLunchDecisionError("Google Places (New) is not enabled or the API key is invalid. Enable \"Places API (New)\" in Google Cloud.");
        } else if (noResultsReason.startsWith("api_error_")) {
          setLunchDecisionError("Could not load places from Google. Try again later or contact support.");
        } else {
          setLunchDecisionError("No strong macro-fit picks found. Check the Map tab for nearby options.");
        }
      }
    } catch (e) {
      if (reqSeq !== lunchDecisionReqSeqRef.current) return;
      const msg = String((e && e.message) || e || "").trim() || "Could not decide your meal right now.";
      setLunchDecisionError(msg.slice(0, 220));
      setLunchDecision(null);
    } finally {
      if (reqSeq === lunchDecisionReqSeqRef.current) {
        setLunchDecisionBusy(false);
        lunchDecisionInFlightRef.current = false;
      }
    }
  }

  async function scanRestaurantMenu(photoUriOverride = "") {
    if (!userId) return;
    if (!ensureAiConsentOrAlert()) return;
    if (menuScanBusy) return;

    const sourceUri = String(photoUriOverride || menuScanPhotoUri || "").trim();
    if (!sourceUri) {
      Alert.alert("No menu photo", "Take a menu photo first.");
      return;
    }

    setMenuScanBusy(true);
    setMenuScanError("");
    setMenuScanResult(null);
    try {
      // If the user enters Scan Menu from Home (or other entrypoints),
      // do not accidentally reuse Decision-card presets.
      if (activeScreen !== "healthy_nearby") {
        setMenuScanInitialAssumptions(null);
      }
      const selectedPlace =
        (healthyPlaces || []).find(
          (x, idx) => healthyPlaceStableId(x, idx) === String(selectedHealthyPlaceId || "").trim()
        ) ||
        (Array.isArray(healthyPlaces) && healthyPlaces.length ? healthyPlaces[0] : null);

      const goal = resolveLunchGoal();
      const cutMode = goal === "fat_loss";
      const remainingCalories = Number.isFinite(num(remainingToday?.kcal))
        ? Math.max(0, num(remainingToday?.kcal))
        : null;
      const remainingProtein = Number.isFinite(num(remainingToday?.protein_g))
        ? Math.max(0, num(remainingToday?.protein_g))
        : null;

      const form = new FormData();
      form.append("file", {
        uri: sourceUri,
        name: "menu.jpg",
        type: "image/jpeg",
      });
      if (selectedPlace?.place_id) form.append("place_id", String(selectedPlace.place_id));
      if (selectedPlace?.place_name || selectedPlace?.name) {
        form.append("restaurant_name", String(selectedPlace.place_name || selectedPlace.name || ""));
      }
      if (selectedPlace?.primary_type) {
        form.append("cuisine", String(selectedPlace.primary_type));
      } else if (Array.isArray(selectedPlace?.types) && selectedPlace.types.length) {
        form.append("cuisine", String(selectedPlace.types[0] || "").replace(/_/g, " "));
      }
      if (remainingCalories !== null) form.append("remaining_calories", String(remainingCalories));
      if (remainingProtein !== null) form.append("remaining_protein_g", String(remainingProtein));
      if (goal) form.append("goal", goal);
      if (cutMode) form.append("cut_mode", "true");
      // Optional local assumption presets (additive; backend may ignore if unsupported).
      if (menuScanInitialAssumptions && typeof menuScanInitialAssumptions === "object") {
        if (menuScanInitialAssumptions.assume_sauce_included) form.append("assume_sauce_included", "true");
        if (menuScanInitialAssumptions.use_standard_portion) form.append("use_standard_portion", "true");
      }

      const url = withTimezoneQuery(`${API_BASE}/menu/scan?user_id=${encodeURIComponent(userId)}`);
      const res = await fetch(url, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });
      const data = await safeJson(res);
      const payload = data?.menu_scan && typeof data.menu_scan === "object" ? data.menu_scan : null;
      if (!payload) {
        throw new Error("Menu scan returned no recommendation payload.");
      }
      setMenuScanResult(payload);
      setMenuScanPhotoUri(sourceUri);
      // Always show the scan result in Healthy Nearby Decision tab.
      // If called from Home, this takes the user straight there.
      // If already in Healthy Nearby, it ensures the Decision tab is active.
      setActiveScreen("healthy_nearby");
      setHealthyNearbyTab("decision");
      _scrollToTop();
    } catch (e) {
      const msg =
        String((e && e.message) || e || "").trim() || "Could not scan this menu right now.";
      setMenuScanError(msg.slice(0, 220));
      setMenuScanResult(null);
      // On error: if the user was on Home, take them to Healthy Nearby so
      // the error message is visible in context.
      if (activeScreen !== "healthy_nearby") {
        setActiveScreen("healthy_nearby");
        setHealthyNearbyTab("decision");
        _scrollToTop();
      }
    } finally {
      setMenuScanBusy(false);
    }
  }

  async function scanUPFProduct(photoUri) {
    const uid = userId || session?.user?.id;
    if (!uid) {
      setUpfScanError("Please sign in to scan.");
      return;
    }
    setUpfScanBusy(true);
    setUpfScanError("");
    setUpfScanResult(null);
    try {
      const { prepareImageForUPF } = await import("./utils/imageCompress");
      const uriToUpload = await prepareImageForUPF(photoUri);
      const form = new FormData();
      form.append("file", {
        uri: uriToUpload,
        name: "product.jpg",
        type: "image/jpeg",
      });
      const analyzeUrl = withTimezoneQuery(`${API_BASE}/analyze/upf?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(analyzeUrl, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });
      const data = await safeJson(res);
      if (!res.ok) {
        throw new Error(errorToMessage(data?.detail || data?.message || `HTTP ${res.status}`, 0) || "Scan failed.");
      }
      if (data?.usage && typeof data.usage === "object") {
        setUsage((prev) => ({ ...(prev && typeof prev === "object" ? prev : {}), ...data.usage }));
      }
      const score =
        (data?.coaching?.ultra_processed_score != null ? num(data.coaching.ultra_processed_score) : null) ??
        (data?.signals?.ultra_processed_avg != null ? num(data.signals.ultra_processed_avg) : null);
      if (score != null && Number.isFinite(score)) {
        const s = Math.max(0, Math.min(10, score));
        const label =
          s <= 2.5 ? "Not much processed" : s <= 6 ? "Processed" : "Ultra processed";
        const symbol = s <= 2.5 ? "😊" : s <= 6 ? "😐" : "😟";
        setUpfScanResult({ score: round1(s), label, symbol });
        setUpfScanError("");
      } else {
        setUpfScanResult(null);
        setUpfScanError("Couldn't assess — try a clearer photo of the product.");
      }
    } catch (e) {
      setUpfScanResult(null);
      setUpfScanError(errorToMessage(e?.message || e, 0) || "Scan failed. Try again.");
    } finally {
      setUpfScanBusy(false);
    }
  }

  async function handleLunchDecisionCTA(card) {
    const payload = card && typeof card === "object" ? card : {};
    const cta = String(payload?.cta_label || "").trim().toLowerCase();

    void logRecommendationEvent("recommendation_clicked", payload, { cta_label: cta });
    void logRecommendationEvent("place_selected", payload, { cta_label: cta });

    if (cta.includes("navigate")) {
      await openPlaceInMaps({
        name: payload?.place_name,
        lat: payload?.place_lat,
        lng: payload?.place_lng,
      });
      return;
    }

    if (cta.includes("scan") && cta.includes("menu")) {
      // Carry Decision-card local assumption presets into Menu Scan.
      try {
        const feedbackKey =
          String(payload?.place_id || payload?.place_name || "unknown").trim() +
          "::" +
          String(payload?.recommended_order || payload?.best_item_name || "").trim();
        const preset =
          nearbyDecisionAssumptionPresets &&
          typeof nearbyDecisionAssumptionPresets === "object" &&
          nearbyDecisionAssumptionPresets[feedbackKey] &&
          typeof nearbyDecisionAssumptionPresets[feedbackKey] === "object"
            ? nearbyDecisionAssumptionPresets[feedbackKey]
            : null;

        const assume_sauce_included = Boolean(preset?.assume_sauce_included);
        const use_standard_portion = Boolean(preset?.use_standard_portion);
        if (assume_sauce_included || use_standard_portion) {
          setMenuScanInitialAssumptions({
            assume_sauce_included,
            use_standard_portion,
            source_feedback_key: feedbackKey,
            source_place_id: String(payload?.place_id || "").trim(),
            source_item: String(payload?.recommended_order || payload?.best_item_name || "").trim(),
            saved_at_ms: Date.now(),
          });
        } else {
          setMenuScanInitialAssumptions(null);
        }

        // If the user tapped Scan Menu on a non-top card, sync selected place so menu scan context is correct.
        const list = Array.isArray(healthyPlaces) ? healthyPlaces.filter((x) => x && typeof x === "object") : [];
        const idx = findMatchingHealthyPlaceIndex(payload, list);
        if (idx >= 0) {
          setSelectedHealthyPlaceId(healthyPlaceStableId(list[idx], idx));
        }
      } catch {}

      setHealthyNearbyTab("decision");
      await openCamera("menu_scan");
      return;
    }

    if (cta.includes("alternative")) {
      await loadHealthyPlacesNearby({
        coords: healthyPlaceCoords,
        preferredCard: payload,
      });
    }
  }

  async function openPlaceInMaps(place) {
    const name = String(place?.name || place?.place_name || "Healthy place").trim();
    const address = String(place?.address || place?.formatted_address || "").trim();
    const queryText = [name, address].filter(Boolean).join(" ");
    const lat = num(place?.lat ?? place?.place_lat);
    const lng = num(place?.lng ?? place?.place_lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      const fallbackQuery = encodeURIComponent(queryText || name);
      const webByName = `https://www.google.com/maps/search/?api=1&query=${fallbackQuery}`;
      try {
        await Linking.openURL(webByName);
      } catch (e) {
        Alert.alert("Map unavailable", String((e && e.message) || e || "").slice(0, 180));
      }
      return;
    }
    const label = encodeURIComponent(name);
    const iosUrl = `http://maps.apple.com/?ll=${lat},${lng}&q=${label}`;
    const androidUrl = `geo:${lat},${lng}?q=${lat},${lng}(${label})`;
    const webUrl = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
    const target = Platform.OS === "ios" ? iosUrl : androidUrl;
    try {
      const supported = await Linking.canOpenURL(target);
      await Linking.openURL(supported ? target : webUrl);
    } catch {
      await Linking.openURL(webUrl);
    }
  }

  async function openHealthyAreaMap() {
    const lat = num(healthyPlaceCoords?.lat);
    const lng = num(healthyPlaceCoords?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      Alert.alert("Location needed", "Turn on location to open nearby places on map.");
      return;
    }
    const webUrl = `https://www.google.com/maps/search/healthy+food/@${lat},${lng},14z`;
    try {
      await Linking.openURL(webUrl);
    } catch (e) {
      Alert.alert("Map unavailable", String((e && e.message) || e || "").slice(0, 180));
    }
  }

  function _scrollToTop() {
    try { mainScrollRef.current?.scrollTo({ y: 0, animated: false }); } catch (_) {}
  }

  async function openPlaceFromSmartAlert(candidate) {
    if (!candidate || typeof candidate !== "object") return;
    setActiveScreen("healthy_nearby");
    setSmartAlertInboxVisible(false);
    setWeeklyCoachExpanded(false);
    setHealthyNearbyTab("decision");
    _scrollToTop();
    const lat = num(candidate.place_lat ?? candidate.lat ?? healthyPlaceCoords?.lat);
    const lng = num(candidate.place_lng ?? candidate.lng ?? healthyPlaceCoords?.lng);
    const coords = Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : healthyPlaceCoords;
    const preferredCard = {
      place_id: candidate.place_id,
      place_name: candidate.place_name || candidate.name,
      place_lat: lat,
      place_lng: lng,
      best_item_name: candidate.best_item_name,
    };
    await loadHealthyPlacesNearby(coords ? { coords, preferredCard } : {});
  }

  async function openHealthyNearbyScreen(target = "overview") {
    const mode = String(target || "overview").trim().toLowerCase();
    setActiveScreen("healthy_nearby");
    setWeeklyCoachExpanded(false);
    _scrollToTop();

    const hasCachedSnapshot =
      nearbySnapshot &&
      Array.isArray(nearbySnapshot?.ranked_places) &&
      nearbySnapshot.ranked_places.length > 0 &&
      Number(nearbySnapshot?.generated_at_ms) > 0 &&
      (Date.now() - Number(nearbySnapshot.generated_at_ms) < NEARBY_SNAPSHOT_TTL_MS);

    if (mode === "decide") {
      setHealthyNearbyTab("decision");
      // Cached-first: render instantly if cache exists, then refresh in background.
      if (hasCachedSnapshot) {
        void loadLunchDecision();
        return;
      }
      void loadLunchDecision();
      return;
    }
    if (mode === "weekly") {
      setHealthyNearbyTab("coach");
      await fetchWeeklyCoachProgress(true);
      return;
    }
    if (mode === "menu") {
      setHealthyNearbyTab("decision");
      await openCamera("menu_scan");
      return;
    }
    if (mode === "map") {
      setHealthyNearbyTab("map");
      if (hasCachedSnapshot) {
        void loadHealthyPlacesNearby();
        setHealthyViewMode("map");
        return;
      }
      void loadHealthyPlacesNearby();
      setHealthyViewMode("map");
      return;
    }
    setHealthyNearbyTab("decision");
    if (hasCachedSnapshot) {
      void loadHealthyPlacesNearby({ preserveFilter: true });
      return;
    }
    void loadHealthyPlacesNearby();
  }

  function renderWeeklyCoachBlock() {
    if (weeklyCoach) {
      const weekSummary =
        weeklyCoach?.week_summary && typeof weeklyCoach.week_summary === "object"
          ? weeklyCoach.week_summary
          : {};
      const insights = Array.isArray(weeklyCoach?.habit_insights)
        ? weeklyCoach.habit_insights.filter((x) => x && typeof x === "object").slice(0, 3)
        : [];
      const bestChoices =
        Array.isArray(weeklyCoach?.best_choices_this_week)
          ? weeklyCoach.best_choices_this_week.filter((x) => x && typeof x === "object").slice(0, 2)
          : [];
      const nextFocus =
        weeklyCoach?.next_week_focus && typeof weeklyCoach.next_week_focus === "object"
          ? weeklyCoach.next_week_focus
          : null;
      const primaryInsight = insights.length ? insights[0] : null;
      const remainingInsights = insights.length > 1 ? insights.slice(1, 3) : [];
      const hasExpandedContent = Boolean(remainingInsights.length || bestChoices.length || nextFocus);
      const onTrackDays = Math.max(0, Math.round(num(weekSummary?.days_on_track)));
      const trackedDays = Math.max(0, Math.round(num(weekSummary?.days_tracked)));
      const avgProtein = Math.max(0, Math.round(num(weekSummary?.average_daily_protein_g)));
      const currentWeekStart = localWeekStartISO(localDayISO());
      const isCurrentWeek = String(weeklyCoach?.week_start || "").trim() === currentWeekStart;
      const hasLoggedToday = (history || []).some(
        (h) => (h?.kind || "") === "photo" && localDayFromISO(h?.ts) === localDayISO()
      );
      const todayInProgress = Boolean(isCurrentWeek && hasLoggedToday);
      const summaryLine = buildWeeklyCoachSummaryLine({
        onTrackDays,
        trackedDays,
        avgProtein,
        todayInProgress,
      });

      return (
        <View style={[styles.weeklyCoachCard, styles.weeklyCoachCardCompact]}>
          {!!String(weeklyCoach?.week_start || "").trim() ? (
            <Text style={styles.weeklyCoachMeta}>Week of {String(weeklyCoach.week_start).trim()}</Text>
          ) : null}

          {!!String(weeklyCoach?.headline || "").trim() ? (
            <Text style={styles.weeklyCoachHeadline} numberOfLines={2}>
              {String(weeklyCoach.headline).trim()}
            </Text>
          ) : null}
          {!!String(weeklyCoach?.supporting_text || "").trim() ? (
            <Text style={styles.weeklyCoachSupport} numberOfLines={2}>
              {String(weeklyCoach.supporting_text).trim()}
            </Text>
          ) : null}

          <Text style={styles.weeklyCoachSummaryLine}>{summaryLine}</Text>

          {primaryInsight ? (
            <View style={styles.weeklyCoachPrimaryInsight}>
              {!!String(primaryInsight?.title || "").trim() ? (
                <Text style={styles.weeklyCoachInsightTitle} numberOfLines={1}>
                  {String(primaryInsight.title).trim()}
                </Text>
              ) : null}
              {!!String(primaryInsight?.text || "").trim() ? (
                <Text style={styles.tiny} numberOfLines={2}>
                  {String(primaryInsight.text).trim()}
                </Text>
              ) : null}
            </View>
          ) : null}

          {weeklyCoachExpanded && remainingInsights.length ? (
            <View style={styles.dayCoachSection}>
              <Text style={styles.dayCoachSectionTitle}>More Patterns</Text>
              {remainingInsights.map((insight, idx) => (
                <View key={`weekly-insight-extra-${idx}`} style={styles.weeklyCoachInsightRow}>
                  <Text style={styles.weeklyCoachInsightBullet}>•</Text>
                  <View style={{ flex: 1 }}>
                    {!!String(insight?.title || "").trim() ? (
                      <Text style={styles.weeklyCoachInsightTitle}>{String(insight.title).trim()}</Text>
                    ) : null}
                    {!!String(insight?.text || "").trim() ? (
                      <Text style={styles.tiny}>{String(insight.text).trim()}</Text>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          ) : null}

          {weeklyCoachExpanded && bestChoices.length ? (
            <View style={styles.dayCoachSection}>
              <Text style={styles.dayCoachSectionTitle}>Best Pick</Text>
              <Text style={styles.tiny}>
                {String(bestChoices[0]?.place_name || "Nearby pick")}
                {String(bestChoices[0]?.recommended_order || "").trim()
                  ? ` — ${String(bestChoices[0].recommended_order).trim()}`
                  : ""}
              </Text>
              {!!String(bestChoices[0]?.why_it_helped || "").trim() ? (
                <Text style={styles.tiny}>{String(bestChoices[0].why_it_helped).trim()}</Text>
              ) : null}
            </View>
          ) : null}

          {weeklyCoachExpanded && nextFocus ? (
            <View style={styles.dayCoachSection}>
              <Text style={styles.dayCoachSectionTitle}>Next Week</Text>
              {!!String(nextFocus?.headline || "").trim() ? (
                <Text style={styles.tiny}>{String(nextFocus.headline).trim()}</Text>
              ) : null}
              {!!String(nextFocus?.supporting_text || "").trim() ? (
                <Text style={styles.tiny}>{String(nextFocus.supporting_text).trim()}</Text>
              ) : null}
            </View>
          ) : null}

          {hasExpandedContent ? (
            <TouchableOpacity
              style={[styles.smallBtn, styles.weeklyCoachToggleBtn]}
              onPress={() => setWeeklyCoachExpanded((v) => !v)}
            >
              <Text style={styles.smallBtnText}>{weeklyCoachExpanded ? "Show less" : "See more"}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      );
    }

    if (weeklyCoachBusy) {
      return (
        <View style={{ marginTop: 10 }}>
          <ActivityIndicator />
        </View>
      );
    }

    return (
      <Text style={[styles.tiny, styles.nearbyLowPriorityHint]}>
        Weekly insights will appear after a few tracked days.
      </Text>
    );
  }

  function openContributionSheet(place, sourceSurface) {
    if (!place) return;
    setContributionPlace({ place, sourceSurface });
    setContributionSheetVisible(true);
  }

  async function reportSupplementIssue(reasonKey, notes) {
    if (!userId) return;
    const scanId = String(supplementResult?.scan_id || "").trim();
    if (!scanId) {
      Alert.alert("No scan result", "Scan a supplement first.");
      return;
    }
    const reason = String(reasonKey || SUPPLEMENT_REPORT_REASONS[0].key).trim();
    const freeText = String(notes || "").trim();
    setSupplementReportBusy(true);
    try {
      const payload = {
        user_id: userId,
        scan_id: scanId,
        issue_type: reason || "review_requested",
        description:
          freeText ||
          SUPPLEMENT_REPORT_REASONS.find((x) => x.key === reason)?.label ||
          "User requested additional verification review.",
      };
      const url = withTimezoneQuery(
        `${API_BASE}/supplement/report_issue?user_id=${encodeURIComponent(userId)}`
      );
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(payload),
      });
      await safeJson(res);
      closeBooleanStateSafely(setSupplementReportModal);
      setSupplementReportOther("");
      if (Platform.OS === "android") {
        ToastAndroid.show("Report submitted for review", ToastAndroid.SHORT);
      } else {
        Alert.alert("Reported", "Report submitted for review.");
      }
    } catch (e) {
      Alert.alert("Report failed", String((e && e.message) || e || "").slice(0, 220));
    } finally {
      setSupplementReportBusy(false);
    }
  }

  async function shareSupplementResult() {
    if (!supplementResult) return;
    const score = Math.max(0, Math.min(100, Math.round(num(supplementResult?.authenticity_score))));
    const level = String(supplementResult?.confidence_level || supplementScoreTone(score).label);
    const text = `🛡 ${score}% Authenticity Confidence\n${level}\nCalorieClick.ai Supplement Scanner`;
    try {
      await Share.share({ message: text });
    } catch (e) {
      Alert.alert("Share failed", String((e && e.message) || e || "").slice(0, 180));
    }
  }

  async function rerunAnalyzeWithPatch(editPatch) {
    if (!userId) return;
    const analysisId = String(result?.analysis_id || "").trim();
    if (!analysisId) {
      Alert.alert("Rerun unavailable", "Analyze a meal first.");
      return;
    }

    // Macro-only fast path: when the user just corrected kcal/protein/carbs/fat
    // on an existing scan, skip the full /analyze/rerun (which re-runs Gemini
    // vision) and call the lightweight /analyze/macro-update endpoint instead.
    // Much faster (~50ms vs ~10s), no vision tokens spent, no risk of the
    // LLM re-interpreting the image differently.
    const mo = editPatch && typeof editPatch === "object" ? editPatch.macro_override : null;
    const hasMacroFields =
      mo && typeof mo === "object" &&
      (mo.kcal != null || mo.protein_g != null || mo.carbs_g != null || mo.fat_g != null);
    const otherEditKeys = [
      "portion_multiplier","set_cooking_method","set_oil_added_tsp","swap_item",
      "swap_candidate","set_item_grams","clarifying_answer","clarifying_answers",
      "ingredient_edits",
    ];
    const hasOtherEdits = editPatch && typeof editPatch === "object" &&
      otherEditKeys.some((k) => editPatch[k] != null);
    const macroOnly = hasMacroFields && !hasOtherEdits;

    const rerunSeq = Number(rerunReqSeqRef.current || 0) + 1;
    rerunReqSeqRef.current = rerunSeq;
    setRerunBusy(true);
    try {
      if (macroOnly) {
        const macroUrl = withTimezoneQuery(`${API_BASE}/analyze/macro-update?user_id=${encodeURIComponent(userId)}`);
        const macroPayload = {
          analysis_id: analysisId,
          item_id: String(mo.item_id || "").trim() || undefined,
          kcal: mo.kcal != null ? Number(mo.kcal) : undefined,
          protein_g: mo.protein_g != null ? Number(mo.protein_g) : undefined,
          carbs_g: mo.carbs_g != null ? Number(mo.carbs_g) : undefined,
          fat_g: mo.fat_g != null ? Number(mo.fat_g) : undefined,
        };
        const mres = await fetch(macroUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", accept: "application/json" },
          body: JSON.stringify(macroPayload),
        });
        console.log("[macro-update] payload", JSON.stringify(macroPayload));
        const mdata = await safeJson(mres);
        console.log("[macro-update] response", mres?.status, JSON.stringify(mdata || {}));
        if (!mres?.ok) {
          const detail = mdata?.detail;
          const backendMsg = errorToMessage(
            mdata?.message || mdata?.error || mdata?.error_code ||
              detail?.message || detail?.error || detail ||
              `Macro update failed (${mres?.status || 400}).`,
            0
          );
          throw new Error(backendMsg || `Macro update failed (${mres?.status || 400}).`);
        }
        if (rerunSeq !== Number(rerunReqSeqRef.current || 0)) return;
        const normalized = normalizeAnalyzeResult(mdata);
        setResult(normalized);
        if (mdata?.fat_loss_intelligence && typeof mdata.fat_loss_intelligence === "object") {
          const quickCoach = sanitizeCoachForDiet(normalizeCoachDaily(mdata.fat_loss_intelligence, localDayISO()));
          setCoachDaily(quickCoach);
          setCoachErr("");
        }
        // Refresh the daily summary card (totals) so edited kcal/macros
        // propagate to the main dashboard without a manual pull-to-refresh.
        try { await fetchDailySummary(userId); } catch (_) {}
        try {
          scheduleDailyCoachRefresh({
            latestScanId: analysisId,
            latestScanTs: String(mdata?.latest_scan_ts || nowISO()),
            mealId: analysisId,
            analysisId: analysisId,
            dailyTotalsVersion: normalizeVersionToken(mdata?.daily_totals_version || mdata?.state_signature || ""),
            pollForLatest: false,
            refreshServer: true,
            fastMode: true,
            trigger: "macro_update",
          });
        } catch (_) {}
        return;
      }

      const rerunUrl = withTimezoneQuery(`${API_BASE}/analyze/rerun?user_id=${encodeURIComponent(userId)}`);
      const normalizedPatch = normalizeRerunPatch(editPatch, result?.editable_context?.items || []);
      const rerunActions = rerunPatchToActions(normalizedPatch);
      const rerunPayload = {
        user_id: userId,
        scan_id: analysisId,
        analysis_id: analysisId,
        edits: rerunActions,
        edit: normalizedPatch,
      };
      const res = await fetch(rerunUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(rerunPayload),
      });
      console.log("[rerun] payload", JSON.stringify(rerunPayload));
      const data = await safeJson(res);
      console.log("[rerun] response", res?.status, JSON.stringify(data || {}));
      if (!res?.ok) {
        const detail = data?.detail;
        const backendMsg = errorToMessage(
          data?.message ||
            data?.error ||
            data?.error_code ||
            detail?.message ||
            detail?.error ||
            detail ||
            `Rerun request failed (${res?.status || 400}).`,
          0
        );
        throw new Error(backendMsg || `Rerun request failed (${res?.status || 400}).`);
      }
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
        const quickCoach = sanitizeCoachForDiet(normalizeCoachDaily(data.fat_loss_intelligence, localDayISO()));
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
        mealId: String(analysisId || latestScanId || "").trim(),
        analysisId: String(analysisId || latestScanId || "").trim(),
        dailyTotalsVersion,
        pollForLatest: Boolean(latestScanId),
        refreshServer: true,
        fastMode: true,
        trigger: "rerun",
      });
      void fetchCoachVoice(normalized, true);
      void fetchWeeklyReport(true);
      void fetchWeeklyCoachProgress(true);
    } catch (e) {
      if (rerunSeq === Number(rerunReqSeqRef.current || 0)) {
        setFliPending(false);
        console.log("rerun failed", String(e));
        const msg = String((e && e.message) || e || "").replace(/^Error:\s*/i, "").trim();
        Alert.alert("Rerun failed", msg || "Couldn't apply edit. Try again.");
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

  async function applyClarificationAnswers() {
    const qs = result?.clarification_questions || [];
    if (!qs.length) return;
    const answers = Object.entries(clarificationSelections)
      .filter(([, v]) => v)
      .map(([key, value]) => {
        const q = qs.find((x) => String(x?.key || "") === key);
        const row = { key, value };
        const ic = String(q?.ingredient_context || "").trim();
        if (ic) row.ingredient_context = ic;
        return row;
      });
    if (!answers.length) return;
    setFliPending(true);
    await rerunAnalyzeWithPatch({ clarifying_answers: answers });
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

  function openEditMacrosModal() {
    const p = round1(result?.totals?.protein_g);
    const c = round1(result?.totals?.carbs_g);
    const f = round1(result?.totals?.fat_g);
    setMacroDraft({
      protein_g: p == null ? "" : String(p),
      carbs_g: c == null ? "" : String(c),
      fat_g: f == null ? "" : String(f),
    });
    setEditMacrosModalVisible(true);
  }

  async function applyMacroOverrideCorrection() {
    const p = Math.max(0, num(macroDraft?.protein_g));
    const c = Math.max(0, num(macroDraft?.carbs_g));
    const f = Math.max(0, num(macroDraft?.fat_g));
    if (!Number.isFinite(p) || !Number.isFinite(c) || !Number.isFinite(f)) {
      return;
    }
    setEditMacrosModalVisible(false);
    setFliPending(true);
    const macroItemId = String(
      result?.editable_context?.items?.[0]?.item_id || result?.items?.[0]?.item_id || ""
    ).trim();
    await rerunAnalyzeWithPatch({
      macro_override: {
        ...(macroItemId ? { item_id: macroItemId } : {}),
        protein_g: p,
        carbs_g: c,
        fat_g: f,
      },
    });
  }

  async function applyPowderConfirmation(itemId, powderType, scoopG) {
    const id = String(itemId || "").trim();
    const pt = String(powderType || "").trim();
    const g = Number(scoopG);
    if (!id || !pt || !Number.isFinite(g) || g <= 0) return;
    setFliPending(true);
    // Backend recognizes supplement_powder:<type> as deterministic nutrition source.
    await rerunAnalyzeWithPatch({
      swap_item: { item_id: id, new_name: `supplement_powder:${pt}` },
      set_item_grams: { item_id: id, grams: g },
    });
  }

  // ===================== BARCODE =====================
  async function openBarcodeScanner(mode = "lookup") {
    if (!ensureAiConsentOrAlert()) return;
    const scannerMode = String(mode || "lookup").trim().toLowerCase() === "supplement" ? "supplement" : "lookup";
    if (scannerMode === "lookup" && !canBarcode) {
      Alert.alert(
        "Barcode scanning is an Elite feature",
        "Upgrade to Elite to scan barcodes for instant macros.",
        [{ text: "Not now", style: "cancel" }, { text: "See plans", onPress: () => openPaywall("elite") }]
      );
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
    setBarcodeMode(scannerMode);
    setBarcodeOpen(true);
  }

  async function barcodeLookup(code) {
    if (!userId) return;
    if (!ensureAiConsentOrAlert()) return;
    if (!code) return;

    setBarcodeBusy(true);
    try {
      const barcodeUrl = withTimezoneQuery(
        `${API_BASE}/barcode/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`
      );
      const res = await fetch(barcodeUrl, { headers: { accept: "application/json" } });
      const data = await safeJson(res);

      const logged = data?.logged_totals && typeof data.logged_totals === "object" ? data.logged_totals : {};
      const lt = num(logged.kcal ?? logged.total_kcal);
      const rawBc = String(data?.barcode || code || "").replace(/\W/g, "");
      const analysisId = `barcode_${rawBc || "x"}_${Date.now()}`;
      const items = Array.isArray(data?.logged_items) ? data.logged_items : [];
      const normalized = normalizeAnalyzeResult({
        analysis_id: analysisId,
        total_kcal: Number.isFinite(lt) ? lt : null,
        totals: {
          kcal: Number.isFinite(lt) ? lt : null,
          total_kcal: Number.isFinite(lt) ? lt : null,
          protein_g: num(logged.protein_g),
          carbs_g: num(logged.carbs_g),
          fat_g: num(logged.fat_g),
        },
        items,
        barcode: data?.barcode,
        barcode_source: true,
        portion_grams: num(data?.portion_grams) ?? 100,
        per_100g: data?.per_100g,
        vision_confidence: 1,
      });
      setPhotoUri(null);
      setResult(normalized);
      await refreshUsage();
      if (data?.daily && typeof data.daily === "object") {
        const dailyGoals = normalizeGoals(data?.daily?.goals, goals || DEFAULT_GOALS);
        setDailySummary({
          ...data.daily,
          goals: dailyGoals,
          micros: normalizeMicros(data?.daily?.micros || data?.daily?.totals?.micros),
        });
      } else {
        await fetchDailySummary(userId);
      }
      await pushHistory({
        ts: nowISO(),
        kind: "barcode",
        barcode: data?.barcode,
        name: data?.name,
        brand: data?.brand,
        per_100g: data?.per_100g,
        total_kcal: normalized?.total_kcal,
        totals: normalized?.totals,
        items: normalized?.items,
        analysis_id: analysisId,
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
    if (barcodeMode === "supplement") {
      setSupplementBarcode(code);
      setSupplementStep((s) => Math.max(4, num(s)));
      setBarcodeMode("lookup");
      return;
    }
    setBarcodeMode("lookup");
    await barcodeLookup(code);
  }

  // Phase 1: derived shared inputs for Healthy Nearby surfaces.
  const effectivePlaces = useMemo(() => {
    const snapPlaces = nearbySnapshot && Array.isArray(nearbySnapshot?.ranked_places) ? nearbySnapshot.ranked_places : [];
    return snapPlaces.length ? snapPlaces : healthyPlaces;
  }, [nearbySnapshot?.generated_at_ms, healthyPlaces]);
  const effectiveLunchDecision = useMemo(() => {
    return (nearbySnapshot && nearbySnapshot?.lunch_decision) ? nearbySnapshot.lunch_decision : lunchDecision;
  }, [nearbySnapshot?.generated_at_ms, lunchDecision]);
  const hasFreshNearbySnapshot = useMemo(() => {
    if (!nearbySnapshot || typeof nearbySnapshot !== "object") return false;
    const ts = Number(nearbySnapshot?.generated_at_ms) || 0;
    if (!ts) return false;
    if (Date.now() - ts > NEARBY_SNAPSHOT_TTL_MS) return false;
    const hasPlaces = Array.isArray(nearbySnapshot?.ranked_places) && nearbySnapshot.ranked_places.length > 0;
    const hasDecisionCards = Array.isArray(nearbySnapshot?.lunch_decision?.cards) && nearbySnapshot.lunch_decision.cards.length > 0;
    return Boolean(hasPlaces || hasDecisionCards);
  }, [nearbySnapshot?.generated_at_ms]);
  const hasNearbyRenderableContent = Boolean(
    (effectivePlaces && effectivePlaces.length) ||
    (effectiveLunchDecision && Array.isArray(effectiveLunchDecision?.cards) && effectiveLunchDecision.cards.length)
  );

  // Keep hook order stable regardless of auth state.
  // This must stay before any early return branches.
  useEffect(() => {
    const visiblePlaces = (() => {
      const isBackendOrdered = healthySortMode === "flat_score" || healthySortMode === "sectioned";
      if (healthySortMode === "sectioned" && Array.isArray(healthySections) && healthySections.length > 0) {
        const filteredSections = healthySections
          .map((sec) => ({
            name: String(sec?.name || "").trim() || "Section",
            items: filterHealthyPlacesForMap(Array.isArray(sec?.items) ? sec.items : [], healthyMapFilter),
          }))
          .filter((sec) => sec.items.length > 0);
        return filteredSections.flatMap((sec) => sec.items);
      }
      const filtered = filterHealthyPlacesForMap(effectivePlaces, healthyMapFilter);
      if (isBackendOrdered) return filtered;
      const rows = [...filtered];
      rows.sort((a, b) => {
        const scoreA = healthyPlaceScore100(a);
        const scoreB = healthyPlaceScore100(b);
        if (scoreB !== scoreA) return scoreB - scoreA;
        const rankA = num(a?.map_rank);
        const rankB = num(b?.map_rank);
        if (Number.isFinite(rankA) && Number.isFinite(rankB) && rankA !== rankB) return rankA - rankB;
        return 0;
      });
      return rows;
    })();

    if (!visiblePlaces.length) return;
    const id = String(selectedHealthyPlaceId || "").trim();
    const found = visiblePlaces.some((x, idx) => healthyPlaceStableId(x, idx) === id);
    if (!found) {
      const top = visiblePlaces[0];
      setSelectedHealthyPlaceId(healthyPlaceStableId(top, 0));
      if (top && Number.isFinite(num(top?.lat)) && Number.isFinite(num(top?.lng))) {
        setHealthyMapFocusCoords({ lat: num(top.lat), lng: num(top.lng) });
      }
    }
  }, [healthyMapFilter, effectivePlaces, selectedHealthyPlaceId, healthySections, healthySortMode]);

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
            <Text
              style={{
                marginTop: 18,
                fontSize: 11,
                color: "#9ca3af",
                textAlign: "center",
              }}
              testID="app-build-fingerprint"
            >
              {`Build ${String(Constants.expoConfig?.version || "?")}${
                Constants.nativeBuildVersion ? ` · ${String(Constants.nativeBuildVersion)}` : ""
              }`}
            </Text>
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
  const coachSourceRaw = String(coachDaily?.source || coachDaily?.fli_source || "").trim().toLowerCase();
  const coachIsLive = coachSourceRaw === "llm" || coachSourceRaw === "cached_llm" || coachSourceRaw === "cache";
  const coachBadgeText = fliPending || fliSyncing ? "Coach: Updating" : coachIsLive ? "Coach: Live" : "Coach: Basic";
  const coachVoiceTonePrimary = String(
    coachVoice?.tone_used || coachVoice?.tone_requested || coachVoice?.tone_id || coachProfile?.tone_preference || "supportive"
  )
    .trim()
    .toLowerCase();
  const coachVoiceModeTag = String(
    coachVoice?.tone_mode ||
      ((String(coachVoice?.source || "").trim().toLowerCase() === "llm" ||
        String(coachVoice?.source || "").trim().toLowerCase() === "cache")
        ? "llm"
        : "fallback")
  )
    .trim()
    .toLowerCase();
  const supplementTone = supplementScoreTone(supplementResult?.authenticity_score);
  const supplementFlags = Array.isArray(supplementResult?.risk_flags) ? supplementResult.risk_flags : [];
  const supplementBreakdown = buildSupplementBreakdown(supplementResult);
  const supplementScore = Math.max(0, Math.min(100, Math.round(num(supplementResult?.authenticity_score))));
  const supplementRegulatory =
    supplementResult?.structured_data && typeof supplementResult.structured_data === "object"
      ? supplementResult.structured_data.regulatory || {}
      : {};
  const supplementFssaiNumber = String(supplementRegulatory?.fssai_license_number || "").trim();
  const supplementFssaiConfidence = Math.max(0, Math.min(1, num(supplementRegulatory?.fssai_confidence)));
  const supplementFssaiSource = String(supplementRegulatory?.fssai_source_image || "").trim();
  const supplementFssaiSnippet = String(supplementRegulatory?.fssai_raw_text_snippet || "").trim();
  const supplementFssaiConfidenceLabel =
    supplementFssaiConfidence >= 0.75 ? "High" : supplementFssaiConfidence >= 0.45 ? "Medium" : "Low";
  const supplementCanSubmit = Boolean(
    supplementFrontUri &&
      (String(supplementBarcode || "").trim() || String(supplementBatchNumber || "").trim())
  );
  const supplementCommunityScanCount = Number(supplementResult?.scan_count ?? supplementResult?.community_scan_count);
  const healthyMapFilterChips = [
    { key: "all", label: "All" },
    { key: "high_protein", label: "High Protein" },
    { key: "under_600", label: "Under 600 kcal" },
    { key: "fits_today", label: "Fits Today" },
    { key: "cut_friendly", label: "Cut Friendly" },
    { key: "best_right_now", label: "Best Right Now" },
  ];
  const { healthyVisiblePlaces, healthySectionsFiltered } = (() => {
    const isBackendOrdered = healthySortMode === "flat_score" || healthySortMode === "sectioned";
    if (healthySortMode === "sectioned" && Array.isArray(healthySections) && healthySections.length > 0) {
      const filteredSections = healthySections
        .map((sec) => ({
          name: String(sec?.name || "").trim() || "Section",
          items: filterHealthyPlacesForMap(Array.isArray(sec?.items) ? sec.items : [], healthyMapFilter),
        }))
        .filter((sec) => sec.items.length > 0);
      const flat = filteredSections.flatMap((sec) => sec.items);
      return { healthyVisiblePlaces: flat, healthySectionsFiltered: filteredSections };
    }
    const filtered = filterHealthyPlacesForMap(effectivePlaces, healthyMapFilter);
    if (isBackendOrdered) {
      return { healthyVisiblePlaces: filtered, healthySectionsFiltered: null };
    }
    const rows = [...filtered];
    rows.sort((a, b) => {
      const scoreA = healthyPlaceScore100(a);
      const scoreB = healthyPlaceScore100(b);
      if (scoreB !== scoreA) return scoreB - scoreA;
      const rankA = num(a?.map_rank);
      const rankB = num(b?.map_rank);
      if (Number.isFinite(rankA) && Number.isFinite(rankB) && rankA !== rankB) return rankA - rankB;
      return 0;
    });
    return { healthyVisiblePlaces: rows, healthySectionsFiltered: null };
  })();
  const healthySelectedPlace = (() => {
    if (!healthyVisiblePlaces.length) return null;
    const picked = healthyVisiblePlaces.find(
      (x, idx) => healthyPlaceStableId(x, idx) === String(selectedHealthyPlaceId || "").trim()
    );
    return picked || healthyVisiblePlaces[0];
  })();
  const healthySelectedPlaceStableId = healthySelectedPlace ? healthyPlaceStableId(healthySelectedPlace, 0) : "";

  const healthySelectedDecisionCard = findMatchingLunchCard(healthySelectedPlace, effectiveLunchDecision?.cards || []);
  const lunchDayCoach = effectiveLunchDecision?.day_coach && typeof effectiveLunchDecision.day_coach === "object"
    ? effectiveLunchDecision.day_coach
    : null;
  const dailyDecision = effectiveLunchDecision?.daily_decision && typeof effectiveLunchDecision.daily_decision === "object"
    ? effectiveLunchDecision.daily_decision
    : null;
  const healthyMapCenter = healthyMapFocusCoords || healthyPlaceCoords;
  const healthyMapPoints = buildHealthyMapPoints(
    healthyVisiblePlaces,
    healthyMapCenter,
    Math.max(240, num(healthyMapWidth)),
    210
  );
  const cameraTitle =
    cameraMode === "supp_front"
      ? "Capture front label"
      : cameraMode === "supp_back"
      ? "Capture nutrition panel"
      : cameraMode === "supp_seal"
      ? "Capture seal photo"
      : cameraMode === "menu_scan"
      ? "Capture menu photo"
      : cameraMode === "upf_scan"
      ? "Scan product"
      : "Take a photo";
  const barcodeModalTitle = barcodeMode === "supplement" ? "Scan supplement barcode" : "Scan barcode";

  const subscriptionPriceText = (key) => priceByEntitlement?.[key] || (rcReady ? "Loading…" : Platform.OS === "android" ? "See Google Play" : "See App Store");
  const homeCoachLine = (() => {
    const greet = localGreeting();
    const daySummaryHeadline = String(lunchDayCoach?.day_summary?.headline || "").trim();
    if (daySummaryHeadline) return `${greet} ${daySummaryHeadline}`;

    const bestCard = Array.isArray(effectiveLunchDecision?.cards) && effectiveLunchDecision.cards.length
      ? effectiveLunchDecision.cards.find((x) => String(x?.card_type || "").trim().toLowerCase() === "best_right_now") ||
        effectiveLunchDecision.cards[0]
      : null;
    const bestPlace = String(bestCard?.place_name || "").trim();
    if (bestPlace) return `${greet} Best next meal near you: ${bestPlace}`;

    const gcConn = goalPlan && String(goalCoachDaily?.coach_connection || "").trim();
    if (gcConn) return gcConn.length > 150 ? `${gcConn.slice(0, 147)}…` : gcConn;

    const remainingProtein = num(remainingToday?.protein_g);
    if (Number.isFinite(remainingProtein) && remainingProtein > 0) {
      return `${greet} You still need ${Math.round(Math.max(0, remainingProtein))}g protein today.`;
    }

    return `${greet} AI helps you eat smarter anywhere.`;
  })();
  const homeMainVisible = activeScreen !== "healthy_nearby" && activeScreen !== "saved_recipes";
  const coachTabShowBadge = Boolean(
    canCoaching &&
      (fliPending || fliSyncing || coachStale || coachBusy || (coachErr && String(coachErr).trim()))
  );
  const smartAlertUnreadApprox = smartAlertState?.enabled ? (smartAlertCandidates || []).length : 0;
  const coachTabShowDot = Boolean(coachTabShowBadge || smartAlertUnreadApprox > 0);
  const planTabShowBadge = Boolean(
    usage &&
      (num(usage?.remaining_day) <= 2 ||
        num(usage?.remaining_month) <= 5 ||
        num(usage?.remaining_day) === 0 ||
        num(usage?.remaining_month) === 0)
  );
  const todayStripLoggedKcal = (dailySummary?.total_kcal != null)
    ? round1(num(dailySummary?.total_kcal))
    : (goals?.kcal != null && remainingToday?.kcal != null)
    ? round1(Math.max(0, num(goals?.kcal || 0) - num(remainingToday?.kcal)))
    : null;
  const todayStripProteinLeft = (remainingToday?.protein_g != null)
    ? round1(num(remainingToday?.protein_g))
    : null;
  const todayStripGoalKcal = (goals?.kcal != null) ? Math.round(num(goals?.kcal)) : null;
  const todaySummaryStripLine = (() => {
    let line = "";
    if (todayStripLoggedKcal != null) {
      line = `Logged ${todayStripLoggedKcal} kcal`;
      if (todayStripGoalKcal != null) line += ` / ~${todayStripGoalKcal} kcal goal`;
    } else {
      line = "Log a meal to see today's total";
    }
    if (todayStripProteinLeft != null) line += ` · ${todayStripProteinLeft}g protein left`;
    return line;
  })();

  return (
    <SafeAreaView
      style={[
        styles.safe,
        styles.safeFlex,
        activeScreen === "healthy_nearby" || activeScreen === "saved_recipes" ? styles.nearbyScreenBg : null,
      ]}
    >
      <ScrollView
        ref={mainScrollRef}
        style={styles.mainScrollFlex}
        contentContainerStyle={[styles.container, homeMainVisible ? styles.containerAboveBottomTabs : null]}
        refreshControl={
          activeScreen === "healthy_nearby" ? (
            <RefreshControl
              refreshing={healthyPlacesBusy}
              onRefresh={() => void loadHealthyPlacesNearby({ preserveFilter: true })}
              tintColor="#93c5fd"
              colors={["#93c5fd"]}
            />
          ) : undefined
        }
      >
        {homeMainVisible ? (
        <View style={styles.topRow}>
          <View style={styles.topRowTitle}>
            <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
              CalorieClick.ai
            </Text>
            <Text style={styles.p} numberOfLines={1} ellipsizeMode="tail">
              Plan: <Text style={styles.plan}>{plan}</Text>
            </Text>
          </View>
          <View style={styles.topRowActions}>
            <Text style={styles.topRowHint}>Use the More tab for account & saved recipes</Text>
          </View>
        </View>
        ) : (
        <View style={styles.nearbyScreenHeader}>
          <TouchableOpacity
            style={styles.nearbyBackBtn}
            onPress={() => { setActiveScreen("home"); _scrollToTop(); }}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <Text style={styles.nearbyBackBtnText}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.nearbyScreenTitle}>{activeScreen === "saved_recipes" ? "Saved recipes" : "Healthy Nearby"}</Text>
          <View style={{ width: 60 }} />
        </View>
        )}

        {activeScreen === "healthy_nearby" ? (
          <View style={styles.healthyHero}>
            <Text style={styles.healthyHeroTitle}>Find the best meal near you.</Text>
            <Text style={styles.healthyHeroSubtitle}>
              Healthy Nearby helps you choose what fits your calories, protein, and goals.
            </Text>
            <Text style={styles.healthyHeroTagline}>CalorieClick.ai</Text>
          </View>
        ) : null}

        {activeScreen === "saved_recipes" ? (
          <SavedRecipesList
            userId={userId}
            aiConsentGiven={aiConsentGiven}
            onOpenUrl={(url) => void openURLSafe(url, "Could not open link.")}
            onBack={() => {
              setActiveScreen("home");
              _scrollToTop();
            }}
            onUpgradePress={openPaywall}
            planAtLeastPro={planAtLeast(plan, "pro")}
          />
        ) : null}

        {homeMainVisible && homeHubTab !== "more" ? (
        <View style={styles.homeSectionTight}>
          <HomeTodayHero
            plan={plan}
            goalPlan={goalPlan}
            goalCoachDaily={goalCoachDaily}
            remainingToday={remainingToday}
            screenshotMode={screenshotMode}
            primaryAction={getDailyActions(goalCoachDaily).primaryAction}
            onPrimaryActionPress={(a) => {
              if (a) handleGoalCoachAction({ ...a, source_surface: "home_today_hero" });
            }}
            onScanPress={() => openCamera("meal")}
            onLetsGoPress={() => setLetsGoModalVisible(true)}
          />
        </View>
        ) : null}

        {homeMainVisible && homeHubTab === "more" ? (
          <View style={[premium.cardBase, styles.homeMorePanel]}>
            <Text style={premium.title}>More</Text>
            <Text style={[premium.muted, { marginBottom: 6 }]}>Saved recipes, plans, and account</Text>
            {userId ? (
              <TouchableOpacity
                style={styles.homeMoreRow}
                onPress={() => {
                  setActiveScreen("saved_recipes");
                  _scrollToTop();
                }}
                activeOpacity={0.85}
              >
                <Text style={styles.homeMoreRowText}>Saved recipes</Text>
                <Text style={styles.homeMoreChevron}>›</Text>
              </TouchableOpacity>
            ) : null}
            {!planAtLeast(plan, "pro") ? (
              <TouchableOpacity style={styles.homeMoreRow} onPress={() => openPaywall(null)} activeOpacity={0.85}>
                <Text style={styles.homeMoreRowText}>Plans & upgrades</Text>
                <Text style={styles.homeMoreChevron}>›</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity style={styles.homeMoreRow} onPress={signOut} activeOpacity={0.85}>
              <Text style={[styles.homeMoreRowText, { color: "#fca5a5" }]}>Log out</Text>
              <Text style={[styles.homeMoreChevron, { color: "#fca5a5" }]}>›</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {homeMainVisible && homeHubTab === "today" ? (
        <>
        <View style={styles.todaySummaryStripWrap}>
          <LinearGradient
            colors={["rgba(147,197,253,0.45)", "rgba(34,197,94,0.35)", "rgba(34,197,94,0)"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.todaySummaryStripHairline}
            pointerEvents="none"
          />
          <View style={styles.todaySummaryStrip}>
            <Text style={styles.todaySummaryStripLabel}>Today at a glance</Text>
            <Text style={styles.todaySummaryStripMetrics}>{todaySummaryStripLine}</Text>
          </View>
        </View>
        <View style={styles.launcherCard}>
          <Text style={styles.launcherTitle}>CalorieClick AI</Text>
          <Text style={styles.launcherQuestion}>What should I eat right now?</Text>
          <Text style={styles.launcherSubline}>One tap to the best next move.</Text>

          <View style={styles.launcherActions}>
            {/* Primary hero action */}
            <TouchableOpacity
              style={styles.launcherPrimaryCard}
              activeOpacity={0.9}
              onPress={() => openCamera("meal")}
            >
              <View style={styles.launcherPrimaryIconWrap}>
                <Text style={styles.launcherPrimaryIcon}>📸</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.launcherActionTitle}>Scan Food</Text>
                <Text style={styles.launcherActionSubtitle}>Analyze your meal in seconds</Text>
              </View>
            </TouchableOpacity>

            {/* Row: Scan Menu + Best Nearby */}
            <View style={styles.launcherRow}>
              <TouchableOpacity
                style={styles.launcherSecondaryCard}
                activeOpacity={0.9}
                onPress={() => openCamera("menu_scan")}
              >
                <Text style={styles.launcherActionIcon}>🍽</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.launcherSecondaryTitle}>Scan Menu</Text>
                  <Text style={styles.launcherSecondarySubtitle} numberOfLines={1}>Best pick at any restaurant</Text>
                </View>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.launcherSecondaryCard}
                activeOpacity={0.9}
                onPress={() => { void openHealthyNearbyScreen("decide"); }}
                disabled={lunchDecisionBusy}
              >
                <Text style={styles.launcherActionIcon}>📍</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.launcherSecondaryTitle}>Best Nearby</Text>
                  <Text style={styles.launcherSecondarySubtitle} numberOfLines={1}>
                    {lunchDecisionBusy ? "Finding options…" : "What fits your macros nearby"}
                  </Text>
                </View>
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.launcherUtilityRow}>
            <TouchableOpacity
              style={premium.ctaGhost}
              activeOpacity={0.85}
              onPress={() => {
                if (smartAlertState?.enabled) setSmartAlertInboxVisible(true);
                else setSmartAlertSettingsVisible(true);
              }}
            >
              <Text style={premium.ctaGhostText}>Smart Alerts</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[premium.ctaGhost, styles.launcherUtilityBtnSpacer]}
              activeOpacity={0.85}
              onPress={() => openCamera("upf_scan")}
            >
              <Text style={premium.ctaGhostText}>UPF Scanner</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[premium.ctaGhost, styles.launcherUtilityBtnSpacer]}
              activeOpacity={0.85}
              onPress={() => {
                if (goalPlan) {
                  setHomeHubTab("coach");
                  try {
                    mainScrollRef.current?.scrollTo({ y: 0, animated: true });
                  } catch (_) {}
                } else {
                  setLetsGoModalVisible(true);
                }
              }}
              disabled={goalCoachCreateBusy}
            >
              <Text style={premium.ctaGhostText}>Goal Coach</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.launcherCoachLine} numberOfLines={3}>{homeCoachLine}</Text>
          {!planAtLeast(plan, "pro") ? (
            <View style={styles.launcherValueRow}>
              <Text style={styles.launcherValueText}>Track meals in seconds. Upgrade for more scans and a personal coach.</Text>
              <TouchableOpacity style={styles.launcherValueBtn} onPress={() => openPaywall(null)}>
                <Text style={styles.launcherValueBtnText}>See plans</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {(upfScanResult || upfScanError || upfScanBusy) ? (
            <View style={[premium.cardBase, { marginTop: 12 }]}>
              <Text style={premium.title}>Processed?</Text>
              {upfScanBusy ? (
                <Text style={premium.muted}>Assessing…</Text>
              ) : upfScanError ? (
                <>
                  <Text style={premium.muted}>{upfScanError}</Text>
                  <TouchableOpacity
                    style={[premium.ctaSecondary, { marginTop: 10 }]}
                    onPress={() => { setUpfScanError(""); openCamera("upf_scan"); }}
                  >
                    <Text style={premium.ctaSecondaryText}>Try again</Text>
                  </TouchableOpacity>
                </>
              ) : upfScanResult ? (
                <>
                  <View style={{ alignItems: "center", marginVertical: 8 }}>
                    <Text style={{ fontSize: 48, marginBottom: 4 }}>{upfScanResult.symbol}</Text>
                    <Text style={[premium.body, { fontWeight: "700", marginBottom: 2 }]}>{upfScanResult.label}</Text>
                    <Text style={premium.muted}>{upfScanResult.score}/10</Text>
                  </View>
                  <TouchableOpacity
                    style={[premium.ctaSecondary, { marginTop: 8 }]}
                    onPress={() => { setUpfScanResult(null); openCamera("upf_scan"); }}
                  >
                    <Text style={premium.ctaSecondaryText}>Scan another</Text>
                  </TouchableOpacity>
                </>
              ) : null}
            </View>
          ) : null}
        </View>
        </>
        ) : null}

        {homeMainVisible && homeHubTab === "coach" ? (
        <>
        {/* Daily progress (pulled up for above-the-fold momentum) */}
        {goalPlan ? (
          <View style={styles.homeSection}>
            <DailyCoachCard
              apiBase={API_BASE}
              userId={userId || session?.user?.id}
              daily={goalCoachDaily}
              subscriptionRequired={goalCoachDaily?.subscription_required ?? false}
              primaryAction={getDailyActions(goalCoachDaily).primaryAction}
              secondaryAction={getDailyActions(goalCoachDaily).secondaryAction}
              onPrimaryAction={(a) => handleGoalCoachAction({ ...a, source_surface: "daily_coach" })}
              onSecondaryAction={(a) => handleGoalCoachAction({ ...a, source_surface: "daily_coach" })}
              onProgressReminderPress={scrollToGoalProgressSection}
            />
          </View>
        ) : null}

        {(() => {
          const enabled = smartAlertState?.enabled;
          const count = (smartAlertCandidates || []).length;
          const preview = (smartAlertCandidates || []).slice(0, 3);
          if (!enabled) {
            return (
              <TouchableOpacity
                style={[premium.cardBase, { opacity: 0.9 }]}
                onPress={() => setSmartAlertSettingsVisible(true)}
                activeOpacity={0.85}
              >
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <View>
                    <Text style={premium.title}>Smart Food Alerts</Text>
                    <Text style={premium.muted}>Turn on to see nearby options that fit your goals</Text>
                  </View>
                  <View style={premium.iconBtn}>
                    <Text style={premium.iconBtnText}>⚙</Text>
                  </View>
                </View>
              </TouchableOpacity>
            );
          }
          return (
            <View style={[premium.cardBase, styles.homeSection]}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <TouchableOpacity
                  style={{ flex: 1 }}
                  onPress={() => setSmartAlertInboxVisible(true)}
                  activeOpacity={0.9}
                >
                  <Text style={premium.title}>Smart Food Alerts</Text>
                  <Text style={premium.muted}>
                    {count > 0
                      ? `${count} nearby option${count !== 1 ? "s" : ""} for your goals`
                      : smartAlertsBusy
                      ? "Checking…"
                      : "No alerts right now"}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[premium.iconBtn, { marginLeft: 8 }]}
                  onPress={() => setSmartAlertSettingsVisible(true)}
                >
                  <Text style={premium.iconBtnText}>⚙</Text>
                </TouchableOpacity>
              </View>
              {preview.length > 0 ? (
                <View style={{ marginTop: 10 }}>
                  {preview.map((c, i) => (
                    <SmartAlertCard
                      key={(c.place_id || "") + (c.alert_type || "") + i}
                      candidate={c}
                      compact
                      onOpen={async (cand) => {
                        const aid = getAlertId(cand);
                        await recordAlertOpened(aid, cand.place_id);
                        setSmartAlertState(await getSmartAlertState());
                        await openPlaceFromSmartAlert(cand);
                      }}
                      onDismiss={async (cand) => {
                        const aid = getAlertId(cand);
                        await recordAlertDismissed(aid, cand.place_id);
                        setSmartAlertState(await getSmartAlertState());
                        setSmartAlertCandidates((prev) => prev.filter((p) => getAlertId(p) !== aid));
                      }}
                    />
                  ))}
                  {count > 3 ? (
                    <TouchableOpacity
                      style={[premium.ctaGhost, { marginTop: 8, alignSelf: "flex-start" }]}
                      onPress={() => setSmartAlertInboxVisible(true)}
                    >
                      <Text style={premium.ctaGhostText}>View all ({count})</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
              ) : null}
            </View>
          );
        })()}
        {/* Goal Coach (split into separate premium cards; no outer wrapper) */}
        <View style={styles.homeSection}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={styles.cardTitle}>Goal Coach</Text>
            {!goalPlan ? (
              <TouchableOpacity
                style={[styles.smallBtn, { backgroundColor: "#22c55e20", borderColor: "#22c55e" }]}
                onPress={() => setLetsGoModalVisible(true)}
                disabled={goalPlanLoading}
              >
                <Text style={[styles.smallBtnText, { color: "#4ade80" }]}>{goalPlanLoading ? "…" : "Let's Go"}</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          {!goalPlan ? (
            <Text style={[styles.tiny, { marginTop: 6 }]}>
              Set a goal and get a starter plan plus daily check-ins. Start free for 3 weeks—then upgrade to Advanced to continue your journey.
            </Text>
          ) : null}
        </View>

        {goalPlan ? (
          <>
            <View style={styles.homeSection}>
              <GoalPlanCard
                plan={goalPlan}
                kickoffDay={goalCoachDaily?.kickoff_day ?? 0}
                kickoffDaysTotal={goalCoachDaily?.kickoff_days_total ?? 21}
                kickoffActive={goalCoachDaily?.kickoff_active ?? true}
                hasDailyAction={!!(getDailyActions(goalCoachDaily).primaryAction)}
                onViewToday={() => {
                  const { primaryAction } = getDailyActions(goalCoachDaily);
                  if (primaryAction) handleGoalCoachAction({ ...primaryAction, source_surface: "goal_plan" });
                }}
              />
            </View>

            {canCoaching ? (
              <View style={styles.homeSection}>
                <View style={[premium.cardBase, styles.coachChatCard]}>
                  <View style={styles.coachChatHeaderRow}>
                    <Text style={premium.title}>Live Coach Chat</Text>
                    <View style={styles.coachChatHeaderActions}>
                      <TouchableOpacity
                        style={[
                          styles.coachRecoveryBadge,
                          coachRecoveryBadge?.tone === "green"
                            ? styles.coachRecoveryBadgeGreen
                            : coachRecoveryBadge?.tone === "red"
                            ? styles.coachRecoveryBadgeRed
                            : styles.coachRecoveryBadgeAmber,
                        ]}
                        onPress={() => setCoachRecoveryExpanded((v) => !v)}
                        activeOpacity={0.85}
                      >
                        <Text style={styles.coachRecoveryBadgeText}>
                          {String(coachRecoveryBadge?.label || "Recovery mode: balanced")} {coachRecoveryExpanded ? "▲" : "▼"}
                        </Text>
                      </TouchableOpacity>
                      {coachChatMessages.length > 0 ? (
                        <TouchableOpacity
                          style={premium.ctaGhost}
                          onPress={() => {
                            setCoachChatMessages([]);
                            const uid = userId || session?.user?.id;
                            if (uid) void saveCoachChatHistory(uid, localDayISO(), []);
                          }}
                          disabled={coachChatBusy}
                          activeOpacity={0.85}
                        >
                          <Text style={premium.ctaGhostText}>Clear</Text>
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  </View>
                  {coachRecoveryExpanded ? (
                    <View style={styles.coachRecoveryPanel}>
                      {(Array.isArray(coachRecoveryBadge?.lines) ? coachRecoveryBadge.lines : []).map((line, idx) => (
                        <Text key={`rec-line-${idx}`} style={styles.coachRecoveryPanelText}>
                          {line}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                  <Text style={premium.muted}>Ask anything about your next meal, cravings, or plan for today.</Text>
                  <ScrollView
                    style={styles.coachChatFeed}
                    contentContainerStyle={styles.coachChatFeedContent}
                    showsVerticalScrollIndicator={false}
                    onContentSizeChange={() => { coachChatScrollRef.current?.scrollToEnd?.({ animated: true }); }}
                    ref={coachChatScrollRef}
                    keyboardShouldPersistTaps="handled"
                  >
                    {(coachChatMessages.length ? coachChatMessages : [{ role: "coach", text: "Hey! 👋 I'm your personal coach. Tell me what's on your mind — meals, cravings, how you're feeling... I'm here for it all 😊" }]).slice(-8).map((m, idx) => {
                      const isCoach = String(m?.role || "").toLowerCase() === "coach";
                      return (
                        <View key={`cc-${idx}`} style={[styles.coachChatBubble, isCoach ? styles.coachChatCoachBubble : styles.coachChatUserBubble]}>
                          <Text style={[styles.coachChatBubbleText, isCoach ? styles.coachChatCoachText : styles.coachChatUserText]}>
                            {String(m?.text || "")}
                          </Text>
                        </View>
                      );
                    })}
                  </ScrollView>
                  <View style={styles.coachQuickRow}>
                    {["What should I eat rn? 🍽️", "Having a craving 😩", "How's my day looking?", "Feeling low today"].map((q) => (
                      <TouchableOpacity
                        key={q}
                        style={styles.coachQuickChip}
                        onPress={() => setCoachChatInput(q)}
                        disabled={coachChatBusy}
                        activeOpacity={0.85}
                      >
                        <Text style={styles.coachQuickChipText}>{q}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <View style={styles.coachChatComposerRow}>
                    <TextInput
                      style={styles.coachChatInputField}
                      value={coachChatInput}
                      onChangeText={setCoachChatInput}
                      placeholder="Type your question..."
                      placeholderTextColor="#94a3b8"
                      editable={!coachChatBusy}
                      multiline
                    />
                    <TouchableOpacity
                      style={[premium.ctaPrimary, styles.coachChatSendBtn, (!coachChatInput.trim() || coachChatBusy) ? { opacity: 0.65 } : null]}
                      onPress={() => { void sendCoachChatTurn(); }}
                      disabled={!coachChatInput.trim() || coachChatBusy}
                      activeOpacity={0.9}
                    >
                      <Text style={premium.ctaPrimaryText}>{coachChatBusy ? "…" : "Send"}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ) : null}

            <View style={styles.homeSection}>
              <JourneyCard
                dayNumber={goalCoachDaily?.kickoff_day ?? 0}
                kickoffDaysTotal={goalCoachDaily?.kickoff_days_total ?? 21}
                summary={journeyData?.summary ?? null}
                photoEntries={journeyData?.photo_entries ?? []}
                weekStartISO={localWeekStartISO()}
              />
            </View>

            <View style={styles.homeSection}>
              <WeeklyPlanReviewCard
                apiBase={API_BASE}
                userId={userId || session?.user?.id}
                review={goalCoachWeekly?.review}
                weekStart={goalCoachWeekly?.week_start}
                weekEnd={goalCoachWeekly?.week_end}
                subscriptionRequired={goalCoachWeekly?.subscription_required ?? false}
                winSummary={goalCoachWeekly?.win_summary}
                proteinDaysThisWeek={goalCoachWeekly?.report_card_facts?.protein_days_this_week}
                nextStepAction={getWeeklyNextStepAction(goalCoachWeekly)}
                onNextStepAction={(a) => handleGoalCoachAction({ ...a, source_surface: "weekly_review" })}
              />
            </View>

            <View style={styles.homeSection}>
              <View style={styles.card}>
                <Text style={styles.label}>Progress</Text>
                <Text style={styles.tiny}>
                  Your coach uses weight + weekly photos to see the trend—not to judge a single day. Same spot and lighting helps.
                </Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 }}>
                  <TextInput
                    style={[styles.input, { flex: 1, minWidth: 80 }]}
                    value={journeyWeightInput}
                    onChangeText={setJourneyWeightInput}
                    keyboardType="decimal-pad"
                    placeholder="Weight (kg)"
                    placeholderTextColor="#666"
                  />
                  <TouchableOpacity
                    style={[styles.secondaryBtn, journeyWeightBusy && { opacity: 0.7 }]}
                    onPress={async () => {
                      const v = parseFloat(journeyWeightInput);
                      if (!Number.isFinite(v) || v <= 0) {
                        Alert.alert("Invalid weight", "Enter a valid weight in kg.");
                        return;
                      }
                      const uid = userId || session?.user?.id;
                      if (!uid) return;
                      setJourneyWeightBusy(true);
                      try {
                        await submitWeightEntry(API_BASE, uid, { value_kg: v, day: localDayISO() });
                        setJourneyWeightInput("");
                        void fetchGoalCoachJourney();
                        if (isDeviceHealthAvailable()) {
                          writeWeightToDeviceHealth({ dateIso: localDayISO(), valueKg: v }, () => {});
                        }
                      } catch (e) {
                        if (e?.status === 402) openPaywall("advanced");
                        else Alert.alert("Error", e?.message || "Could not log weight.");
                      } finally {
                        setJourneyWeightBusy(false);
                      }
                    }}
                    disabled={journeyWeightBusy}
                  >
                    <Text style={styles.btnText}>{journeyWeightBusy ? "…" : "Log weight"}</Text>
                  </TouchableOpacity>
                </View>
                <TouchableOpacity
                  style={[styles.secondaryBtn, { marginTop: 8 }, journeyPhotoBusy && { opacity: 0.7 }]}
                  onPress={async () => {
                    const uid = userId || session?.user?.id;
                    if (!uid) return;
                    try {
                      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
                      if (status !== "granted") {
                        Alert.alert("Permission needed", "Allow photo library access to add progress photos.");
                        return;
                      }
                      setJourneyPhotoBusy(true);
                      const result = await ImagePicker.launchImageLibraryAsync({
                        mediaTypes: ImagePicker.MediaTypeOptions.Images,
                        allowsEditing: true,
                        quality: 0.8,
                      });
                      if (result.canceled || !result.assets?.[0]?.uri) {
                        setJourneyPhotoBusy(false);
                        return;
                      }
                      const uri = result.assets[0].uri;
                      await submitPhotoEntry(API_BASE, uid, {
                        week_start: localWeekStartISO(),
                        uri_or_ref: uri,
                      });
                      void fetchGoalCoachJourney();
                      Alert.alert("Saved", "Progress photo logged for this week.");
                    } catch (e) {
                      if (e?.status === 402) openPaywall("advanced");
                      else Alert.alert("Error", e?.message || "Could not add photo.");
                    } finally {
                      setJourneyPhotoBusy(false);
                    }
                  }}
                  disabled={journeyPhotoBusy}
                >
                  <Text style={styles.btnText}>{journeyPhotoBusy ? "…" : "Add progress photo"}</Text>
                </TouchableOpacity>
              </View>
            </View>

            {goalPlan &&
              goalCoachDaily?.kickoff_active &&
              !(goalCoachDaily?.subscription_required || goalCoachWeekly?.subscription_required) &&
              (() => {
                const day = num(goalCoachDaily?.kickoff_day) ?? 0;
                const total = num(goalCoachDaily?.kickoff_days_total) ?? 21;
                const daysLeft = Math.max(0, total - day);
                return daysLeft >= 1 && daysLeft <= 4;
              })() ? (
              <View style={styles.homeSection}>
                <View style={styles.trialEndingBanner}>
                  <Text style={styles.trialEndingText}>
                    Your free trial ends in{" "}
                    {Math.max(1, (num(goalCoachDaily?.kickoff_days_total) ?? 21) - (num(goalCoachDaily?.kickoff_day) ?? 0))} day(s).
                    Upgrade to Advanced to keep your journey, check-ins, and progress.
                  </Text>
                  <TouchableOpacity style={styles.trialEndingBtn} onPress={() => openPaywall("advanced")}>
                    <Text style={styles.trialEndingBtnText}>Upgrade to Advanced</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}

            {(goalCoachDaily?.subscription_required || goalCoachWeekly?.subscription_required) ? (
              <View style={styles.homeSection}>
                <PlanPaywallCard
                  kickoffDay={goalCoachDaily?.kickoff_day ?? 0}
                  kickoffDaysTotal={goalCoachDaily?.kickoff_days_total ?? 21}
                  requiresAdvancedPlan={goalCoachDaily?.requires_advanced_plan ?? goalCoachWeekly?.requires_advanced_plan ?? false}
                  onUnlock={() => openPaywall("advanced")}
                />
              </View>
            ) : null}
          </>
        ) : null}
        </>
        ) : null}

        {homeMainVisible && homeHubTab === "plan" ? (
        <View style={[premium.cardBase, styles.compactStatusCard]}>
          <View style={styles.compactHeaderRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.compactTitle}>Scans left</Text>
              <Text style={styles.compactValue} numberOfLines={1}>
                {usage ? `${usage.remaining_day} today • ${usage.remaining_month} month` : "…"}
              </Text>
            </View>
            <View style={styles.compactHeaderActions}>
              <TouchableOpacity
                style={premium.ctaGhost}
                onPress={() => setScansModuleExpanded((v) => !v)}
                activeOpacity={0.85}
              >
                <Text style={premium.ctaGhostText}>{scansModuleExpanded ? "Less" : "Details"}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {(num(usage?.remaining_day) <= 2 || num(usage?.remaining_month) <= 5) && usage ? (
            <View style={[styles.scansLowBanner, { marginTop: 10 }]}>
              <Text style={styles.scansLowText} numberOfLines={2}>
                {num(usage.remaining_day) === 0 || num(usage.remaining_month) === 0
                  ? "You’ve used your scans for this period."
                  : "Running low on scans."}
              </Text>
              <TouchableOpacity style={styles.scansLowBtn} onPress={() => openPaywall("advanced")}>
                <Text style={styles.scansLowBtnText}>Upgrade</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          <View style={styles.compactActionsRow}>
            <TouchableOpacity style={premium.ctaGhost} onPress={refreshUsage} activeOpacity={0.9}>
              <Text style={premium.ctaGhostText}>Refresh</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[premium.ctaGhost, { marginLeft: 10 }]}
              onPress={restorePurchases}
              disabled={rcBusy || rcRefreshing || !rcReady}
              activeOpacity={0.9}
            >
              <Text style={premium.ctaGhostText}>{rcBusy ? "…" : "Restore"}</Text>
            </TouchableOpacity>
          </View>

          {scansModuleExpanded ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.tiny}>
                Restore does NOT refill scans (only syncs your plan). Already subscribed? Tap Restore to sync.
              </Text>
              <View style={styles.compactMetaRow}>
                <Text style={styles.tiny} numberOfLines={2}>
                  Goals: {Math.round(goals?.kcal || 0)} kcal • P {round1(goals?.protein_g || 0)}g • C {round1(goals?.carbs_g || 0)}g • F{" "}
                  {round1(goals?.fat_g || 0)}g
                </Text>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => {
                    setGoalsDraft(goals || DEFAULT_GOALS);
                    setGoalsModal(true);
                  }}
                >
                  <Text style={styles.smallBtnText}>Edit</Text>
                </TouchableOpacity>
              </View>
              <View style={{ marginTop: 8 }}>
                <Text style={styles.p}>Protein left today: {round1(remainingToday?.protein_g)}g</Text>
                <Text style={styles.tiny}>
                  Remaining: {round1(remainingToday?.kcal)} kcal • C {round1(remainingToday?.carbs_g)}g • F {round1(remainingToday?.fat_g)}g • Fiber{" "}
                  {round1(remainingToday?.fiber_g)}g
                </Text>
              </View>
            </View>
          ) : null}
        </View>
        ) : null}

        {homeMainVisible && homeHubTab === "coach" ? (
        <>
        <View style={styles.card}>
          <View style={styles.intelHeader}>
            <View style={styles.intelHeaderTop}>
              <TouchableOpacity onPress={onCoachTitleTap} activeOpacity={0.9}>
                <Text style={styles.cardTitle}>Fat Loss Intelligence</Text>
              </TouchableOpacity>
              {!canCoaching ? <Text style={styles.lockedTag}>Pro feature</Text> : null}
            </View>
            {canCoaching && !screenshotMode ? (
              <View style={styles.fliPreviewActionsRow}>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => ensureDailyCoach(true, { refreshServer: true, fastMode: true, trigger: "manual_refresh" })}
                  disabled={coachBusy}
                >
                  <Text style={styles.smallBtnText}>{coachBusy ? "…" : "Refresh"}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.smallBtn}
                  onPress={() => {
                    layoutEaseInOut();
                    void hapticLight({ key: "fli:details_toggle", cooldownMs: 700 });
                    setFliPreviewExpanded((v) => !v);
                  }}
                  activeOpacity={0.85}
                >
                  <Text style={styles.smallBtnText}>{fliPreviewExpandedEffective ? "Less" : "Details"}</Text>
                </TouchableOpacity>
              </View>
            ) : null}
          </View>

          {canCoaching && fliPreviewExpandedEffective && !screenshotMode ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.intelHeaderActionsScroll}
              contentContainerStyle={styles.intelHeaderActions}
            >
              <TouchableOpacity
                style={styles.smallBtn}
                onPress={() => {
                  setCoachProfileDraft(normalizeCoachProfile(coachProfile || DEFAULT_COACH_PROFILE));
                  setCoachMemoryFoodInput("");
                  setCoachMemoryGoalInput("");
                  setCoachProfileModal(true);
                }}
              >
                <Text style={styles.smallBtnText}>Profile</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.smallBtn}
                onPress={() => fetchWeeklyReport(true)}
                disabled={weeklyReportBusy}
              >
                <Text style={styles.smallBtnText}>{weeklyReportBusy ? "…" : "Weekly"}</Text>
              </TouchableOpacity>
            </ScrollView>
          ) : null}

          {fliPreviewExpandedEffective ? (
            <Text style={styles.intelSubline}>
              {canCoaching
                ? `${coachProfile?.goal_type || "fat_loss"} • ${coachProfile?.diet_style || "non-veg"} • ${Math.round(
                    num(coachProfile?.training_days_per_week)
                  )} training day(s)/week • ${coachProfile?.training_time || "evening"} • ${coachProfile?.tone_preference || "supportive"}`
                : `${String(plan || "free").toUpperCase()} plan preview • Pro unlocks diagnosis, risk alerts, and actions`}
            </Text>
          ) : null}

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
              <TouchableOpacity
                style={styles.unlockProBtn}
                onPress={() => openPaywall("pro")}
                activeOpacity={0.85}
              >
                <Text style={styles.unlockProBtnText}>Unlock with Pro</Text>
              </TouchableOpacity>
              <TouchableOpacity style={{ marginTop: 8 }} onPress={() => openPaywall(null)} activeOpacity={0.8}>
                <Text style={[styles.tiny, { color: "#60a5fa", textDecorationLine: "underline" }]}>See all plans</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              {coachErr && !screenshotMode ? <Text style={[styles.tiny, { color: "#ffb4b4", marginTop: 8 }]}>{coachErr}</Text> : null}
              {(fliSyncing || coachStale || fliPending) && !screenshotMode ? (
                <View style={styles.fliUpdateBanner}>
                  <Text style={styles.fliUpdateText}>
                    {fliPending ? "New scan saved. Refining insights…" : "New scan detected. Updating insights…"}
                  </Text>
                </View>
              ) : null}

              {/* Preview: show just the strongest 1–2 lines. Full blocks stay behind Details. */}
              {coachVoice && !fliPreviewExpandedEffective ? (
                <View style={[premium.cardInset, styles.fliPreviewBox]}>
                  <View style={styles.coachVoiceHeaderRow}>
                    <View style={[premium.aiOrb, { width: 30, height: 30 }]}>
                      <Text style={premium.aiOrbText}>AI</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={premium.kickerOnDarkInset}>Coach says</Text>
                      <Text style={premium.title} numberOfLines={1}>One takeaway</Text>
                    </View>
                  </View>
                  {!!String(coachVoice?.insight_line || "").trim() ? (
                    <Text style={premium.body}>{String(coachVoice?.insight_line || "")}</Text>
                  ) : String(coachVoice?.empathy_line || "").trim() ? (
                    <Text style={premium.body}>{String(coachVoice?.empathy_line || "")}</Text>
                  ) : null}
                  {String(coachDaily?.one_sentence_summary || "").trim() ? (
                    <Text style={[premium.mutedOnDarkInset, { marginTop: 8 }]} numberOfLines={2}>
                      {String(coachDaily?.one_sentence_summary || "")}
                    </Text>
                  ) : null}
                </View>
              ) : null}

              {coachVoice && fliPreviewExpandedEffective && !screenshotMode ? (
                <View style={[premium.cardInset, styles.coachVoiceExpandedBox]}>
                  <View style={styles.coachVoiceHeaderRow}>
                    <View style={[premium.aiOrb, { width: 30, height: 30 }]}>
                      <Text style={premium.aiOrbText}>AI</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={premium.kickerOnDarkInset}>
                        Coach voice • {coachVoiceTonePrimary.replace(/_/g, " ")}
                        {coachVoiceModeTag && coachVoiceModeTag !== coachVoiceTonePrimary ? ` • mode ${coachVoiceModeTag}` : ""}
                      </Text>
                      <Text style={premium.title} numberOfLines={1}>Guidance</Text>
                    </View>
                  </View>
                  {!!String(coachVoice?.empathy_line || "").trim() && <Text style={styles.p}>{String(coachVoice?.empathy_line || "")}</Text>}
                  {!!String(coachVoice?.insight_line || "").trim() && <Text style={[styles.p, { marginTop: 6 }]}>{String(coachVoice?.insight_line || "")}</Text>}
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
              ) : null}

              {fliPreviewExpandedEffective && weeklyReport && !screenshotMode ? (
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
              ) : fliPreviewExpandedEffective && weeklyReportBusy && !screenshotMode ? (
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
                      <View
                        style={[
                          styles.coachSourceBadge,
                          coachIsLive ? styles.coachSourceBadgeLive : styles.coachSourceBadgeBasic,
                        ]}
                      >
                        <Text style={styles.coachSourceBadgeText}>{coachBadgeText}</Text>
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
                        {(coachDaily?.fli_source === "cached_llm" || coachDaily?.source === "cache") ? " • Refining…" : ""}
                      </Text>
                      {fliPreviewExpandedEffective && showCoachDebug && !screenshotMode ? (
                        <View style={{ marginTop: 6, padding: 8, borderWidth: 1, borderColor: "#26364f", borderRadius: 8 }}>
                          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <Text style={[styles.tiny, { fontWeight: "700", color: "#cfe3ff" }]}>Internal</Text>
                            <TouchableOpacity style={styles.smallBtn} onPress={() => setAdminOpsVisible(true)}>
                              <Text style={styles.smallBtnText}>Ops Dashboard</Text>
                            </TouchableOpacity>
                          </View>
                          <Text style={styles.tiny}>payload_hash_used: {String(coachDaily?.payload_hash_used || "-")}</Text>
                          <Text style={styles.tiny}>request_id: {String(coachDaily?.request_id || "-")}</Text>
                          <Text style={styles.tiny}>source: {String(coachDaily?.source || "-")}</Text>
                          <Text style={styles.tiny}>fli_source: {String(coachDaily?.fli_source || "-")}</Text>
                          <Text style={styles.tiny}>llm_model_used: {String(coachDaily?.llm_model_used || "-")}</Text>
                          <Text style={styles.tiny}>llm_error_code: {String(coachDaily?.llm_error_code || "-")}</Text>
                          <Text style={styles.tiny}>
                            llm_tried_models: {(coachDaily?.llm_tried_models || []).join(", ") || "-"}
                          </Text>
                          <Text style={styles.tiny}>
                            confidence_band: {String(coachDaily?.predictive_signals?.projection_confidence_band || "-")}
                          </Text>
                          <Text style={styles.tiny}>coach_generated_ts: {String(coachDaily?.coach_generated_ts || "-")}</Text>
                          <Text style={styles.tiny}>meals_count_today: {String(coachDaily?.meals_count_today ?? "-")}</Text>
                          <Text style={styles.tiny}>input_scan_id: {String(coachDaily?.input_scan_id || "-")}</Text>
                          <Text style={styles.tiny}>analysis_id: {String(coachDaily?.analysis_id || "-")}</Text>
                          <Text style={styles.tiny}>meal_id: {String(coachDaily?.meal_id || "-")}</Text>
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
        </>
        ) : null}

        {homeMainVisible && homeHubTab === "today" ? (
        <>
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
            <TouchableOpacity style={styles.primaryBtn} onPress={() => openCamera("meal")}>
              <Text style={styles.btnText}>Open Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.primaryBtn} onPress={analyzePhoto} disabled={busy || rerunBusy || !photoUri}>
              {busy ? <ActivityIndicator /> : <Text style={styles.btnText}>Analyze</Text>}
            </TouchableOpacity>
          </View>

          {busy ? (
            <View style={{ marginTop: 6 }}>
              <View style={styles.row}>
                <TouchableOpacity style={styles.secondaryBtn} onPress={cancelAnalyzeJob}>
                  <Text style={styles.btnText}>Cancel analyze</Text>
                </TouchableOpacity>
                <Text style={[styles.tiny, { marginLeft: 10, alignSelf: "center", flex: 1 }]}>
                  {scanProgress || "Analyzing…"}
                </Text>
              </View>
              {!!scanLoadingFactLine ? (
                <Text
                  style={[styles.tiny, { marginTop: 10, color: "#94a3b8", fontStyle: "italic", lineHeight: 18 }]}
                >
                  {scanLoadingFactLine}
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={styles.row}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={clearCurrentScan} disabled={!photoUri && !result}>
              <Text style={styles.btnText}>Clear current scan</Text>
            </TouchableOpacity>
          </View>

          {result ? (
            <View style={{ marginTop: 14 }}>
              {postScanUpgradeBannerVisible ? (
                <View style={[styles.card, { marginBottom: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }]}>
                  <Text style={[styles.p, { flex: 1 }]}>Get more scans + daily coaching — Upgrade</Text>
                  <TouchableOpacity style={styles.smallBtn} onPress={() => { dismissPostScanBanner(); openPaywall(null); }}>
                    <Text style={styles.smallBtnText}>See plans</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[premium.iconBtn, { marginLeft: 8 }]}
                    onPress={dismissPostScanBanner}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    activeOpacity={0.85}
                  >
                    <Text style={premium.iconBtnText}>✕</Text>
                  </TouchableOpacity>
                </View>
              ) : null}
              <Text style={styles.big}>Total: {round1(result?.total_kcal)} kcal</Text>
              <Text style={styles.p}>
                Protein {round1(result?.totals?.protein_g)}g • Carbs {round1(result?.totals?.carbs_g)}g • Fat{" "}
                {round1(result?.totals?.fat_g)}g
              </Text>
              {goalPlan && String(goalCoachDaily?.meal_log_encouragement || "").trim() ? (
                <View
                  style={{
                    marginTop: 10,
                    padding: 12,
                    borderRadius: 10,
                    backgroundColor: "rgba(245, 158, 11, 0.12)",
                    borderWidth: 1,
                    borderColor: "rgba(245, 158, 11, 0.35)",
                  }}
                >
                  <Text style={[styles.tiny, { fontWeight: "700", color: "#92400e" }]}>Goal Coach</Text>
                  <Text style={[styles.p, { marginTop: 4, color: "#78350f" }]}>
                    {String(goalCoachDaily.meal_log_encouragement).trim()}
                  </Text>
                </View>
              ) : null}
              {result?.usual_meal_hint?.line ? (
                <View
                  style={{
                    marginTop: 10,
                    padding: 10,
                    borderRadius: 10,
                    backgroundColor: "#ecfdf5",
                    borderWidth: 1,
                    borderColor: "#6ee7b7",
                  }}
                >
                  <Text style={[styles.tiny, { color: "#065f46", fontWeight: "600" }]}>Your usual meal</Text>
                  <Text style={[styles.p, { marginTop: 4, color: "#064e3b" }]}>{String(result.usual_meal_hint.line)}</Text>
                </View>
              ) : null}
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

              {(result?.clarifying_question?.ask ||
                (result?.clarification_questions || []).length > 0 ||
                (result?.meal_qa?.one_tap_fixes || []).length > 0) ? (
                <View style={[styles.card, { marginTop: 12 }]}>
                  <Text style={styles.cardTitle}>Improve accuracy</Text>
                  <Text style={styles.tiny}>
                    Quick fixes + confirmations help tighten kcal/macros. You can do these in any order.
                  </Text>
                  {(result?.meal_components || []).length > 0 ? (
                    <View style={{ marginTop: 8 }}>
                      <Text style={[styles.tiny, { fontWeight: "600", marginBottom: 4 }]}>Parts we detected</Text>
                      <View style={styles.rowWrap}>
                        {(result.meal_components || []).map((part, pi) => (
                          <View key={`mc-${pi}-${part}`} style={[styles.chip, { opacity: 0.95 }]}>
                            <Text style={styles.chipText}>{part}</Text>
                          </View>
                        ))}
                      </View>
                      <Text style={[styles.tiny, { marginTop: 4, opacity: 0.85 }]}>
                        Confirm details below — we remember your answers for this meal and each part.
                      </Text>
                    </View>
                  ) : null}
                  <View style={{ marginTop: 10 }}>
                    <TouchableOpacity style={styles.secondaryBtn} onPress={openEditMacrosModal} disabled={rerunBusy}>
                      <Text style={styles.btnText}>Fix result / Edit macros</Text>
                    </TouchableOpacity>
                    <Text style={[styles.tiny, { marginTop: 6 }]}>
                      Edit protein/carbs/fat directly. kcal updates from macros after apply.
                    </Text>
                  </View>

                  {(result?.meal_qa?.one_tap_fixes || []).length ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={[styles.p, { fontWeight: "700" }]}>Quick fixes</Text>
                      <View style={styles.rowWrap}>
                        {(result?.meal_qa?.one_tap_fixes || []).slice(0, 4).map((fix, idx) => (
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
                    </View>
                  ) : null}

                  {result?.clarifying_question?.ask ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={[styles.p, { fontWeight: "700" }]}>Confirm for better accuracy</Text>
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

                  {(result?.clarification_questions || []).length > 0 ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={[styles.p, { fontWeight: "700" }]}>Confirm details (we learn and remember)</Text>
                      <Text style={styles.tiny}>Your answers improve future scans for this meal and ingredients.</Text>
                      {(result.clarification_questions || []).map((q, qIdx) => (
                        <View key={q.key || qIdx} style={{ marginTop: 8 }}>
                          {q.ingredient_context ? (
                            <Text style={[styles.tiny, { marginBottom: 4, color: "#b45309" }]}>
                              About: {q.ingredient_context}
                            </Text>
                          ) : null}
                          <Text style={styles.p}>{q.label}</Text>
                          <View style={styles.rowWrap}>
                            {(q.options || []).map((opt, idx) => (
                              <TouchableOpacity
                                key={`${q.key}-${idx}`}
                                style={[
                                  styles.chip,
                                  clarificationSelections[q.key] === opt ? { borderColor: "#22c55e", borderWidth: 2 } : null,
                                ]}
                                onPress={() => setClarificationSelections((prev) => ({ ...prev, [q.key]: opt }))}
                                disabled={rerunBusy}
                              >
                                <Text style={styles.chipText}>{String(opt)}</Text>
                              </TouchableOpacity>
                            ))}
                          </View>
                        </View>
                      ))}
                      <TouchableOpacity
                        style={[styles.primaryBtn, { marginTop: 10 }]}
                        onPress={() => applyClarificationAnswers()}
                        disabled={rerunBusy || !Object.keys(clarificationSelections).some((k) => clarificationSelections[k])}
                      >
                        <Text style={styles.btnText}>Apply and update kcal</Text>
                      </TouchableOpacity>
                    </View>
                  ) : null}

                  {result?.meal_qa ? (
                    <View style={{ marginTop: 10 }}>
                      <Text style={[styles.p, { fontWeight: "700" }]}>Quality checks</Text>
                      <Text style={styles.tiny}>Score {round1(result?.meal_qa?.qa_score)}/100</Text>
                      {(result?.meal_qa?.issues || []).slice(0, 3).map((iss, idx) => (
                        <Text key={`qa-issue-${idx}`} style={styles.tiny}>
                          • {String(iss?.message || "")}
                        </Text>
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

              {/* Powder confirmation (supplements) */}
              {(Array.isArray(result?.items) ? result.items : [])
                .filter((it) => it && typeof it === "object" && it?._powder_meta?.is_powder_like)
                .slice(0, 1)
                .map((it) => {
                  const meta = it._powder_meta || {};
                  const conf = meta.powder_confirmation || {};
                  const needs = Boolean(meta.needs_powder_confirmation);
                  const resolved = String(meta.powder_type_resolved || "").trim();
                  const itemId = String(it.item_id || "").trim();
                  const scoopG = Math.round(num(it.grams));
                  return (
                    <ScanConfirmationChips
                      key={`powder-confirm-${itemId}`}
                      title={needs ? "Confirm powder type + scoop" : "Powder detected (optional confirm)"}
                      powderTypes={conf.powder_types || ["whey", "whey_isolate", "plant_protein", "mass_gainer", "cocoa_powder", "other_powder"]}
                      scoopSizesG={conf.scoop_sizes_g || [25, 30, 40]}
                      selectedPowderType={resolved}
                      selectedScoopG={scoopG || 30}
                      disabled={rerunBusy}
                      onSelectPowderType={(pt) => applyPowderConfirmation(itemId, pt, scoopG || 30)}
                      onSelectScoopG={(g) => applyPowderConfirmation(itemId, resolved || "whey", g)}
                    />
                  );
                })}

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

              {aiConsentGiven ? (
                <RecipeSuggestionsRow
                  busy={recipeSuggestBusy}
                  payload={recipeSuggestFiltered}
                  mealTag={String(result?.items?.[0]?.name || result?.top_candidates?.[0]?.label || "").trim()}
                  onOpenUrl={(url) => void openURLSafe(url, "Could not open recipe link.")}
                  onUpgradePress={openPaywall}
                  onFeedback={({ recipeKey, action, cuisine, mealTag, recipe }) => {
                    const uid = userId || session?.user?.id;
                    if (!uid || !recipeKey) return;
                    const snap =
                      action === "save" && recipe && typeof recipe === "object"
                        ? {
                            title: recipe.title,
                            source_url: recipe.source_url,
                            image_url: recipe.image_url,
                            est_kcal_per_serving: recipe.est_kcal_per_serving,
                            est_protein_g_per_serving: recipe.est_protein_g_per_serving,
                            source: recipe.source,
                            cuisines: recipe.cuisines,
                            why_similar: recipe.why_similar,
                          }
                        : undefined;
                    postRecipeFeedback({
                      userId: uid,
                      recipeKey,
                      action,
                      cuisine,
                      mealTag,
                      recipeSnapshot: snap,
                    });
                    if (action === "dismiss") {
                      setRecipeDismissedLocal((prev) => ({ ...prev, [recipeKey]: true }));
                    }
                  }}
                />
              ) : null}

              {/* Health disclaimer + sources (Guideline 1.4.1) */}
              <View style={{ marginTop: 14 }}>
                <Text style={styles.muted}>{HEALTH_DISCLAIMER}</Text>

                <Text style={[styles.muted, { marginTop: 10, fontWeight: "800" }]}>Sources</Text>

                <View style={{ marginTop: 6 }}>
                  {HEALTH_SOURCES.map((s) => (
                    <TouchableOpacity
                      key={s.url}
                      onPress={() => openURLSafe(s?.url, "Could not open source link.")}
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

        <View style={[premium.cardBase, styles.suppAuthorityCard]}>
          <View style={styles.suppHeaderRow}>
            <Text style={premium.title}>Supplement Scanner</Text>
            <View style={styles.suppAuthorityBadge}>
              <Text style={styles.suppAuthorityBadgeText}>FREE</Text>
            </View>
          </View>
          <Text style={premium.muted}>Verify whey protein authenticity</Text>

          <View style={styles.progressContainer}>
            <View
              style={[
                styles.progressFill,
                { width: `${(Math.max(1, supplementStep) / SUPPLEMENT_TOTAL_STEPS) * 100}%` },
              ]}
            />
          </View>
          <Text style={premium.muted}>Step {supplementStep} of {SUPPLEMENT_TOTAL_STEPS}</Text>

          {supplementStep === 1 ? (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.label}>Step 1 • Front label</Text>
              <Text style={premium.muted}>Capture a clear front label image (brand + variant visible).</Text>
              {supplementFrontUri ? (
                <Image source={{ uri: supplementFrontUri }} style={styles.suppPreviewSingle} />
              ) : (
                <View style={styles.suppPreviewEmptySingle}>
                  <Text style={styles.previewText}>Front label not captured</Text>
                </View>
              )}
              <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 8 }]} onPress={() => openCamera("supp_front")}>
                <Text style={premium.ctaSecondaryText}>{supplementFrontUri ? "Retake front label" : "Capture front label"}</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {supplementStep === 2 ? (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.label}>Step 2 • Nutrition panel</Text>
              <Text style={premium.muted}>Capture the nutrition panel/back label for stronger structural checks.</Text>
              {supplementBackUri ? (
                <Image source={{ uri: supplementBackUri }} style={styles.suppPreviewSingle} />
              ) : (
                <View style={styles.suppPreviewEmptySingle}>
                  <Text style={styles.previewText}>Nutrition panel not captured</Text>
                </View>
              )}
              <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 8 }]} onPress={() => openCamera("supp_back")}>
                <Text style={premium.ctaSecondaryText}>{supplementBackUri ? "Retake nutrition panel" : "Capture nutrition panel"}</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {supplementStep === 3 ? (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.label}>Step 3 • Barcode</Text>
              <Text style={premium.muted}>Scan or enter barcode manually for registry matching.</Text>
              <TextInput
                value={supplementBarcode}
                onChangeText={setSupplementBarcode}
                style={styles.input}
                placeholder="Barcode"
                placeholderTextColor="#777"
                keyboardType="number-pad"
              />
              <TouchableOpacity style={premium.ctaSecondary} onPress={() => openBarcodeScanner("supplement")}>
                <Text style={premium.ctaSecondaryText}>Scan barcode</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {supplementStep === 4 ? (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.label}>Step 4 • Batch code</Text>
              <Text style={premium.muted}>Enter batch code from the container (optional but recommended).</Text>
              <TextInput
                value={supplementBatchNumber}
                onChangeText={setSupplementBatchNumber}
                style={styles.input}
                placeholder="Batch code"
                placeholderTextColor="#777"
                autoCapitalize="characters"
              />
              <TouchableOpacity
                style={[premium.ctaGhost, { marginTop: 8 }]}
                onPress={() => setSupplementProofMode((v) => !v)}
              >
                <Text style={premium.ctaGhostText}>
                  {supplementProofMode ? "High Confidence Mode: ON" : "Enable High Confidence Mode"}
                </Text>
              </TouchableOpacity>
              <Text style={premium.muted}>
                Optional: capture cap/seal photo for stronger verification in high confidence mode.
              </Text>
              {sealImage ? (
                <Image source={{ uri: sealImage }} style={styles.suppPreviewSingle} />
              ) : (
                <View style={styles.suppPreviewEmptySingle}>
                  <Text style={styles.previewText}>Seal photo not captured</Text>
                </View>
              )}
              <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 8 }]} onPress={() => openCamera("supp_seal")}>
                <Text style={premium.ctaSecondaryText}>{sealImage ? "Retake seal photo" : "Capture seal photo (optional)"}</Text>
              </TouchableOpacity>
              {supplementProofMode && !sealImage ? (
                <Text style={[styles.tiny, { marginTop: 8, color: "#f59e0b" }]}>
                  High confidence mode is enabled. Capture seal photo to avoid missing-seal penalty.
                </Text>
              ) : null}
              {!supplementCanSubmit ? (
                <Text style={[styles.tiny, { marginTop: 8, color: "#fca5a5" }]}>
                  Front label and either barcode or batch code are required to submit.
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={styles.suppNavRow}>
            {supplementStep > 1 ? (
              <TouchableOpacity style={premium.ctaSecondary} onPress={prevSupplementStep} disabled={supplementBusy}>
                <Text style={premium.ctaSecondaryText}>Back</Text>
              </TouchableOpacity>
            ) : null}

            {supplementStep < SUPPLEMENT_TOTAL_STEPS ? (
              <>
                {supplementStep > 1 ? (
                  <TouchableOpacity style={premium.ctaGhost} onPress={skipSupplementStep} disabled={supplementBusy}>
                    <Text style={premium.ctaGhostText}>Skip</Text>
                  </TouchableOpacity>
                ) : null}
                <TouchableOpacity style={premium.ctaPrimary} onPress={nextSupplementStep} disabled={supplementBusy}>
                  <Text style={premium.ctaPrimaryText}>Next</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <TouchableOpacity
                  style={premium.ctaPrimary}
                  onPress={scanSupplement}
                  disabled={supplementBusy || !supplementCanSubmit}
                >
                  {supplementBusy ? <ActivityIndicator /> : <Text style={premium.ctaPrimaryText}>Start verification</Text>}
                </TouchableOpacity>
                <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 10 }]} onPress={clearSupplementScan} disabled={supplementBusy}>
                  <Text style={premium.ctaSecondaryText}>Reset</Text>
                </TouchableOpacity>
              </>
            )}
          </View>

          {supplementResult ? (
            <View style={[premium.cardInset, styles.suppResultPanel]}>
              <View style={styles.suppGaugeWrap}>
                <View style={[styles.suppGaugeRing, { borderColor: supplementTone.color }]}>
                  <Text style={[styles.suppGaugeValue, { color: supplementTone.color }]}>{supplementScore}%</Text>
                  <Text style={styles.suppGaugeLabel}>Authenticity Confidence</Text>
                </View>
              </View>

              <Text style={[styles.suppHeadline, { color: supplementTone.color }]}>
                {String(supplementResult?.confidence_level || supplementTone.label)}
              </Text>

              {!!String(supplementResult?.explanation || "").trim() ? (
                <Text style={[premium.body, { marginTop: 6 }]}>{String(supplementResult?.explanation || "")}</Text>
              ) : null}

              {supplementFssaiNumber ? (
                <View style={[premium.cardInset, styles.suppRegulatoryCard]}>
                  <Text style={premium.title}>Regulatory</Text>
                  <Text style={premium.body}>FSSAI license (extracted): {supplementFssaiNumber}</Text>
                  <Text style={premium.muted}>
                    Extraction confidence: {supplementFssaiConfidenceLabel}
                    {supplementFssaiSource ? ` • source ${supplementFssaiSource}` : ""}
                  </Text>
                  {supplementFssaiSnippet ? (
                    <Text style={[premium.muted, { marginTop: 4 }]}>Snippet: {supplementFssaiSnippet}</Text>
                  ) : null}
                  <TouchableOpacity
                    style={[premium.ctaGhost, { marginTop: 8, alignSelf: "flex-start" }]}
                    onPress={() => {
                      const q = `https://www.google.com/search?q=${encodeURIComponent(
                        `FSSAI license ${supplementFssaiNumber}`
                      )}`;
                      void openURLSafe(q, "Could not open search.");
                    }}
                  >
                    <Text style={premium.ctaGhostText}>Verify on official portal</Text>
                  </TouchableOpacity>
                  <Text style={[premium.muted, { marginTop: 6 }]}>
                    Extracted from packaging text. Not an official verification.
                  </Text>
                </View>
              ) : null}

              {Number.isFinite(supplementCommunityScanCount) ? (
                <Text style={[styles.tiny, { marginTop: 6 }]}>
                  {supplementCommunityScanCount <= 1
                    ? "First scan recorded for this batch in your region."
                    : `Scanned ${Math.round(supplementCommunityScanCount)} times in your region.`}
                </Text>
              ) : null}

              <TouchableOpacity
                style={styles.suppBreakdownToggle}
                onPress={() => setSupplementBreakdownOpen((v) => !v)}
                activeOpacity={0.85}
              >
                <Text style={styles.itemName}>Verification Breakdown</Text>
                <Text style={styles.smallBtnText}>{supplementBreakdownOpen ? "Hide" : "Show"}</Text>
              </TouchableOpacity>

              {supplementBreakdownOpen ? (
                <View style={{ marginTop: 8 }}>
                  {!supplementFlags.length ? (
                    <Text style={[styles.tiny, { marginBottom: 8 }]}>No structural inconsistencies detected.</Text>
                  ) : null}
                  {supplementBreakdown.map((row) => {
                    const tone = supplementRiskTone(row.level);
                    return (
                      <View key={row.key} style={styles.suppBreakdownRow}>
                        <Text style={[styles.suppBreakdownIcon, { color: tone.color }]}>{tone.icon}</Text>
                        <Text style={styles.tiny}>{row.text}</Text>
                      </View>
                    );
                  })}
                </View>
              ) : null}

              <Text style={styles.suppLegalText}>
                {String(supplementResult?.legal_note || SUPPLEMENT_LEGAL_NOTE)}
              </Text>

              <View style={styles.rowWrap}>
                <TouchableOpacity
                  style={premium.ctaSecondary}
                  onPress={() => setSupplementReportModal(true)}
                  disabled={supplementReportBusy}
                >
                  <Text style={premium.ctaSecondaryText}>Report suspicious product</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[premium.ctaSecondary, { marginLeft: 10 }]} onPress={shareSupplementResult}>
                  <Text style={premium.ctaSecondaryText}>Share result</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : null}
        </View>
        </>
        ) : null}

        {activeScreen === "healthy_nearby" ? (
        <>
        <View style={[styles.card, styles.healthyNearbyHeroCard]}>
          <Text style={styles.nearbyScreenSubtitle}>Find the best meal near you right now.</Text>
          {(remainingToday?.kcal != null || remainingToday?.protein_g != null) ? (
            <View style={styles.remainingMacrosBar}>
              {remainingToday?.kcal != null ? (
                <View style={styles.remainingMacroPill}>
                  <Text style={styles.remainingMacroIcon}>🔥</Text>
                  <Text style={styles.remainingMacroValue}>{Math.max(0, Math.round(remainingToday.kcal))}</Text>
                  <Text style={styles.remainingMacroLabel}> kcal left</Text>
                </View>
              ) : null}
              {remainingToday?.protein_g != null ? (
                <View style={styles.remainingMacroPill}>
                  <Text style={styles.remainingMacroIcon}>💪</Text>
                  <Text style={styles.remainingMacroValue}>{Math.max(0, Math.round(remainingToday.protein_g))}</Text>
                  <Text style={styles.remainingMacroLabel}>g protein left</Text>
                </View>
              ) : null}
            </View>
          ) : null}
          <View style={styles.nearbyTabsRowTop}>
            <TouchableOpacity
              style={[styles.nearbyTabPill, healthyNearbyTab === "decision" ? styles.nearbyTabPillActive : null]}
              onPress={() => setHealthyNearbyTab("decision")}
            >
              <Text style={[styles.nearbyTabText, healthyNearbyTab === "decision" ? styles.nearbyTabTextActive : null]}>
                Decision
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.nearbyTabPill, healthyNearbyTab === "map" ? styles.nearbyTabPillActive : null]}
              onPress={() => {
                setHealthyNearbyTab("map");
                if (!(effectivePlaces || []).length && !healthyPlacesBusy) {
                  void loadHealthyPlacesNearby();
                }
              }}
            >
              <Text style={[styles.nearbyTabText, healthyNearbyTab === "map" ? styles.nearbyTabTextActive : null]}>
                Map
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.nearbyTabPill, healthyNearbyTab === "coach" ? styles.nearbyTabPillActive : null]}
              onPress={() => {
                setHealthyNearbyTab("coach");
                if (!weeklyCoach && !weeklyCoachBusy) {
                  void fetchWeeklyCoachProgress(true);
                }
              }}
            >
              <Text style={[styles.nearbyTabText, healthyNearbyTab === "coach" ? styles.nearbyTabTextActive : null]}>
                Coach
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.nearbyPrimaryActions}>
            <TouchableOpacity
              style={[styles.primaryBtn, styles.nearbyPrimaryCta]}
              onPress={() => {
                setHealthyNearbyTab("decision");
                void loadLunchDecision();
              }}
              disabled={lunchDecisionBusy}
            >
              <Text style={styles.btnText}>{lunchDecisionBusy ? "Deciding..." : "🎯 Decide My Next Meal"}</Text>
            </TouchableOpacity>
            <View style={styles.nearbySecondaryActionsRow}>
              <TouchableOpacity
                style={[styles.secondaryBtn, { flex: 1 }]}
                onPress={async () => {
                  setHealthyNearbyTab("map");
                  await loadHealthyPlacesNearby();
                  setHealthyViewMode("map");
                }}
                disabled={healthyPlacesBusy}
              >
                <Text style={styles.btnText}>{healthyPlacesBusy ? "Loading..." : "🗺 Food Map"}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.secondaryBtn, { flex: 1 }]}
                onPress={() => {
                  setHealthyNearbyTab("decision");
                  void openCamera("menu_scan");
                }}
                disabled={menuScanBusy}
              >
                <Text style={styles.btnText}>{menuScanBusy ? "Scanning..." : "📸 Scan Menu"}</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={styles.nearbyExtrasRow}>
            <TouchableOpacity
              style={styles.nearbyExtraBtn}
              onPress={() => {
                setHealthyNearbyTab("coach");
                setWeeklyCoachExpanded(false);
                void fetchWeeklyCoachProgress(true);
              }}
              disabled={weeklyCoachBusy}
            >
              <Text style={styles.nearbyExtraBtnText}>{weeklyCoachBusy ? "Loading..." : "📅 Weekly Coach"}</Text>
            </TouchableOpacity>
            {healthyPlaceCoords ? (
              <TouchableOpacity style={styles.nearbyExtraBtn} onPress={openHealthyAreaMap}>
                <Text style={styles.nearbyExtraBtnText}>📍 Area Map</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          {healthyPlaceCoords ? (
            <Text style={[styles.tiny, { marginTop: 8 }]}>
              Using your current location
            </Text>
          ) : null}
          {(healthyPlacesError || lunchDecisionError) ? (
            <View style={styles.nearbyErrorBlock}>
              <Text style={styles.nearbyErrorText}>
                {healthyPlacesError || lunchDecisionError}
              </Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8, justifyContent: "center" }}>
                <TouchableOpacity
                  style={styles.nearbyRetryBtn}
                  onPress={() => {
                    setHealthyNearbyTab("decision");
                    void loadLunchDecision();
                  }}
                  disabled={lunchDecisionBusy || healthyPlacesBusy}
                >
                  <Text style={styles.nearbyRetryBtnText}>
                    {lunchDecisionBusy || healthyPlacesBusy ? "Searching..." : "↺ Retry"}
                  </Text>
                </TouchableOpacity>
                {healthyPlaceCoords ? (
                  <TouchableOpacity
                    style={[styles.nearbyRetryBtn, { backgroundColor: "#1e3a2f", borderColor: "#22c55e" }]}
                    onPress={openHealthyAreaMap}
                  >
                    <Text style={styles.nearbyRetryBtnText}>📍 Open in Maps</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ) : null}
          {menuScanError ? (
            <Text style={[styles.tiny, { marginTop: 6, color: "#fca5a5" }]}>{menuScanError}</Text>
          ) : null}
          {weeklyCoachError ? (
            <Text style={[styles.tiny, { marginTop: 6, color: "#fca5a5" }]}>{weeklyCoachError}</Text>
          ) : null}
        </View>

        {healthyNearbyTab === "decision" ? (
        <View style={[styles.card, styles.healthyNearbySectionCard]}>
          <Text style={styles.nearbySectionHeader}>Decision</Text>
          <Text style={styles.nearbySectionSubtle}>Coach + next meal picks</Text>
          {((lunchDecisionBusy || healthyPlacesBusy) && !hasNearbyRenderableContent && !hasFreshNearbySnapshot) ? (
            <View style={{ marginTop: 10 }}>
              <ActivityIndicator />
              <Text style={[styles.tiny, { marginTop: 6, textAlign: "center", color: "#94a3b8" }]}>
                Finding best options nearby...
              </Text>
            </View>
          ) : null}
          {!effectiveLunchDecision && !lunchDecisionBusy && !lunchDecisionError ? (
            <View style={{ marginTop: 14, alignItems: "center" }}>
              <TouchableOpacity
                style={styles.primaryBtn}
                onPress={() => void loadLunchDecision()}
                disabled={lunchDecisionBusy}
              >
                <Text style={styles.btnText}>Find My Best Meal Now</Text>
              </TouchableOpacity>
            </View>
          ) : null}
          {!effectiveLunchDecision && !lunchDecisionBusy && lunchDecisionError ? (
            <View style={styles.nearbyErrorBlock}>
              <Text style={styles.nearbyErrorText}>{lunchDecisionError}</Text>
              <TouchableOpacity
                style={styles.nearbyRetryBtn}
                onPress={() => void loadLunchDecision()}
                disabled={lunchDecisionBusy}
              >
                <Text style={styles.nearbyRetryBtnText}>↺ Try again</Text>
              </TouchableOpacity>
            </View>
          ) : null}
          {menuScanBusy && !menuScanResult ? (
            <View style={{ marginTop: 10 }}>
              <ActivityIndicator />
              <Text style={[styles.tiny, { marginTop: 8 }]}>Reading menu and finding best picks…</Text>
              {!!scanLoadingFactLine ? (
                <Text
                  style={[styles.tiny, { marginTop: 6, color: "#94a3b8", fontStyle: "italic", lineHeight: 18 }]}
                >
                  {scanLoadingFactLine}
                </Text>
              ) : null}
            </View>
          ) : null}
          {menuScanResult ? (
            (() => {
              const bestChoice =
                menuScanResult?.best_choice_here && typeof menuScanResult.best_choice_here === "object"
                  ? menuScanResult.best_choice_here
                  : Array.isArray(menuScanResult?.top_recommendations) && menuScanResult.top_recommendations.length
                  ? menuScanResult.top_recommendations[0]
                  : null;
              const betterSwap =
                menuScanResult?.better_swap && typeof menuScanResult.better_swap === "object"
                  ? menuScanResult.better_swap
                  : null;
              const avoidCutting =
                menuScanResult?.avoid_if_cutting && typeof menuScanResult.avoid_if_cutting === "object"
                  ? menuScanResult.avoid_if_cutting
                  : null;
              const coachMsg =
                menuScanResult?.coach_message && typeof menuScanResult.coach_message === "object"
                  ? menuScanResult.coach_message
                  : null;
              const reality =
                menuScanResult?.reality_check && typeof menuScanResult.reality_check === "object"
                  ? menuScanResult.reality_check
                  : null;

              const assumptionUsage =
                Array.isArray(menuScanResult?.assumption_usage) ? menuScanResult.assumption_usage : [];
              const hasAssumptionsUsed = assumptionUsage.length > 0;
              const assumptionUsageLabels = assumptionUsage
                .map((k) => String(k || "").trim())
                .filter(Boolean)
                .map((k) => {
                  if (k === "sauce_included") return "Sauce included";
                  if (k === "standard_portion") return "Standard portion";
                  return k;
                });

              return (
                <View style={styles.menuScanCard}>
                  <Text style={styles.cardTitle}>{String(menuScanResult?.title || "Best Choice Here")}</Text>
                  <Text style={styles.p}>{String(menuScanResult?.subtitle || "AI analyzed this restaurant menu")}</Text>
                  {hasAssumptionsUsed ? (
                    <Text style={[styles.tiny, { marginTop: 6, color: "#94a3b8" }]} numberOfLines={1}>
                      {`Assumptions used: ${assumptionUsageLabels.join(", ")}`}
                    </Text>
                  ) : null}
                  {finiteNumOrNull(menuScanResult?.scan_confidence) !== null ? (
                    <Text style={styles.tiny}>Scan confidence {Math.round(finiteNumOrNull(menuScanResult?.scan_confidence) * 100)}%</Text>
                  ) : null}

                  {bestChoice ? (
                    <View style={styles.dayCoachSection}>
                      <Text style={styles.dayCoachSectionTitle}>Best Choice Here</Text>
                      <Text style={styles.healthyPanelItemName}>{String(bestChoice?.item_name || "Smart pick")}</Text>
                      <Text style={styles.tiny}>
                        {finiteNumOrNull(bestChoice?.estimated_calories) !== null
                          ? `${Math.round(finiteNumOrNull(bestChoice?.estimated_calories))} kcal`
                          : "Calories n/a"}
                        {finiteNumOrNull(bestChoice?.estimated_protein_g) !== null
                          ? ` • ${Math.round(finiteNumOrNull(bestChoice?.estimated_protein_g))}g protein`
                          : ""}
                      </Text>
                      {!!String(bestChoice?.short_reason || "").trim() ? (
                        <Text style={styles.tiny}>{String(bestChoice.short_reason).trim()}</Text>
                      ) : null}
                      {bestChoice?.fit_for_today === true ? (
                        <Text style={[styles.tiny, styles.lunchFitGood]}>✅ Fits today's macros</Text>
                      ) : null}
                      {bestChoice?.fit_for_today === false ? (
                        <Text style={[styles.tiny, styles.lunchFitCaution]}>⚠ Harder to fit today</Text>
                      ) : null}
                    </View>
                  ) : null}

                  {betterSwap ? (
                    <View style={styles.dayCoachSection}>
                      <Text style={styles.dayCoachSectionTitle}>Better Swap</Text>
                      <Text style={styles.tiny}>
                        {String(betterSwap?.item_name || "Lighter menu swap")}
                        {finiteNumOrNull(betterSwap?.estimated_calories) !== null
                          ? ` • ${Math.round(finiteNumOrNull(betterSwap?.estimated_calories))} kcal`
                          : ""}
                      </Text>
                      {!!String(betterSwap?.short_reason || "").trim() ? (
                        <Text style={styles.tiny}>{String(betterSwap.short_reason).trim()}</Text>
                      ) : null}
                    </View>
                  ) : null}

                  {avoidCutting ? (
                    <View style={styles.dayCoachSection}>
                      <Text style={styles.dayCoachSectionTitle}>Avoid if Cutting</Text>
                      <Text style={styles.tiny}>
                        {String(avoidCutting?.item_name || "Calorie-dense option")}
                        {finiteNumOrNull(avoidCutting?.estimated_calories) !== null
                          ? ` • ~${Math.round(finiteNumOrNull(avoidCutting?.estimated_calories))} kcal`
                          : ""}
                      </Text>
                      {!!String(avoidCutting?.short_reason || "").trim() ? (
                        <Text style={styles.tiny}>{String(avoidCutting.short_reason).trim()}</Text>
                      ) : null}
                    </View>
                  ) : null}

                  {coachMsg ? (
                    <View style={styles.dayCoachSection}>
                      <Text style={styles.dayCoachSectionTitle}>Coach Note</Text>
                      {!!String(coachMsg?.headline || "").trim() ? (
                        <Text style={styles.mapCoachHeadline}>{String(coachMsg.headline).trim()}</Text>
                      ) : null}
                      {!!String(coachMsg?.supporting_text || "").trim() ? (
                        <Text style={styles.tiny}>{String(coachMsg.supporting_text).trim()}</Text>
                      ) : null}
                    </View>
                  ) : null}

                  {reality ? (
                    <View style={styles.dayCoachSection}>
                      <Text style={styles.dayCoachSectionTitle}>Reality Check</Text>
                      {finiteNumOrNull(reality?.typical_order?.estimated_calories) !== null ? (
                        <Text style={styles.tiny}>Typical order: ~{Math.round(finiteNumOrNull(reality?.typical_order?.estimated_calories))} kcal</Text>
                      ) : null}
                      {finiteNumOrNull(reality?.smarter_order?.estimated_calories) !== null ? (
                        <Text style={styles.tiny}>Smarter order: ~{Math.round(finiteNumOrNull(reality?.smarter_order?.estimated_calories))} kcal</Text>
                      ) : null}
                      {finiteNumOrNull(reality?.calories_saved) !== null ? (
                        <Text style={[styles.tiny, styles.realitySavedText]}>You save ~{Math.max(0, Math.round(finiteNumOrNull(reality?.calories_saved)))} kcal</Text>
                      ) : null}
                    </View>
                  ) : null}

                  <View style={styles.lunchCardActionsRow}>
                    <TouchableOpacity
                      style={[styles.smallBtn, styles.menuScanBtn]}
                      onPress={() => {
                        void openCamera("menu_scan");
                      }}
                    >
                      <Text style={styles.smallBtnText}>Scan again</Text>
                    </TouchableOpacity>
                    {!!menuScanPhotoUri ? (
                      <TouchableOpacity
                        style={styles.smallBtn}
                        onPress={() => {
                          void scanRestaurantMenu();
                        }}
                        disabled={menuScanBusy}
                      >
                        <Text style={styles.smallBtnText}>{menuScanBusy ? "Scanning..." : "Re-run"}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              );
            })()
          ) : null}
          {effectiveLunchDecision && Array.isArray(effectiveLunchDecision.cards) && !effectiveLunchDecision.cards.length && !lunchDecisionBusy ? (
            <View style={{ marginTop: 14, paddingVertical: 12, paddingHorizontal: 4 }}>
              <Text style={[styles.p, { color: "#94a3b8", textAlign: "center" }]}>
                No exact macro-fit picks found nearby.
              </Text>
              <Text style={[styles.tiny, { color: "#64748b", textAlign: "center", marginTop: 4 }]}>
                Nearby places may still have good options — check the Map tab.
              </Text>
              <TouchableOpacity
                style={[styles.secondaryBtn, { marginTop: 10, alignSelf: "center" }]}
                onPress={() => {
                  setHealthyNearbyTab("map");
                  if (!(effectivePlaces || []).length && !healthyPlacesBusy) {
                    void loadHealthyPlacesNearby();
                  }
                }}
              >
                <Text style={styles.btnText}>See Nearby Options on Map</Text>
              </TouchableOpacity>
            </View>
          ) : null}
          {effectiveLunchDecision && Array.isArray(effectiveLunchDecision.cards) && effectiveLunchDecision.cards.length ? (
            <HealthyNearbyDecisionShowcase
              decision={effectiveLunchDecision}
              onPrimaryPress={() => void handleLunchDecisionCTA(effectiveLunchDecision.cards[0])}
              onCardPress={(card) => void handleLunchDecisionCTA(card)}
            />
          ) : null}
          {false && effectiveLunchDecision && Array.isArray(effectiveLunchDecision.cards) && effectiveLunchDecision.cards.length ? (
            <View style={styles.lunchDecisionWrap}>
              <Text style={styles.cardTitle}>{String(effectiveLunchDecision.title || "What should I eat right now?")}</Text>
              <Text style={styles.p}>{String(effectiveLunchDecision.subtitle || "Best next meal near you")}</Text>
              {!!String(effectiveLunchDecision?.summary_line || "").trim() && !screenshotMode ? (
                <Text style={styles.lunchSummaryLine}>{String(effectiveLunchDecision.summary_line).trim()}</Text>
              ) : null}
              {dailyDecision && !screenshotMode ? (
                (() => {
                  const primary =
                    dailyDecision?.primary_recommendation && typeof dailyDecision.primary_recommendation === "object"
                      ? dailyDecision.primary_recommendation
                      : null;
                  const secondary = Array.isArray(dailyDecision?.secondary_recommendations)
                    ? dailyDecision.secondary_recommendations.filter((x) => x && typeof x === "object").slice(0, 2)
                    : [];
                  const mealWindow = String(dailyDecision?.meal_window || "").trim();
                  const goalLabel = String(dailyDecision?.decision_context?.goal || "").trim();
                  const decisionRemainingCal = finiteNumOrNull(dailyDecision?.decision_context?.remaining_calories);
                  const remainingCal = decisionRemainingCal !== null
                    ? Math.round(decisionRemainingCal)
                    : null;
                  const decisionRemainingProtein = finiteNumOrNull(dailyDecision?.decision_context?.remaining_protein_g);
                  const remainingProtein = decisionRemainingProtein !== null
                    ? Math.round(decisionRemainingProtein)
                    : null;

                  return (
                    <View style={styles.dayCoachCard}>
                      <Text style={styles.healthyPanelSectionTitle}>What should I eat next?</Text>
                      <Text style={styles.mapCoachHeadline}>
                        {String(dailyDecision?.subtitle || "Best option for your day right now")}
                      </Text>
                      {!!mealWindow ? (
                        <Text style={styles.dayCoachProgressSubtle}>
                          Meal window: {mealWindow.charAt(0).toUpperCase() + mealWindow.slice(1)}
                          {!!goalLabel ? ` • Goal: ${goalLabel.replace(/_/g, " ")}` : ""}
                        </Text>
                      ) : null}
                      {(remainingCal !== null || remainingProtein !== null) ? (
                        <Text style={styles.dayCoachProgressSubtle}>
                          {remainingCal !== null ? `${remainingCal} kcal left` : ""}
                          {remainingCal !== null && remainingProtein !== null ? " • " : ""}
                          {remainingProtein !== null ? `${remainingProtein}g protein left` : ""}
                        </Text>
                      ) : null}

                      {primary ? (
                        <View style={styles.dayCoachSection}>
                          <Text style={styles.dayCoachSectionTitle}>
                            {String(primary?.headline || "Best next meal").trim()}
                          </Text>
                          <Text style={styles.tiny}>
                            {String(primary?.place_name || "Nearby option")}
                            {String(primary?.recommended_order || "").trim()
                              ? ` — ${String(primary.recommended_order).trim()}`
                              : ""}
                          </Text>
                          {(finiteNumOrNull(primary?.estimated_calories) !== null || finiteNumOrNull(primary?.estimated_protein_g) !== null) ? (
                            <Text style={styles.tiny}>
                              {finiteNumOrNull(primary?.estimated_calories) !== null ? `${Math.round(finiteNumOrNull(primary?.estimated_calories))} kcal` : ""}
                              {finiteNumOrNull(primary?.estimated_calories) !== null && finiteNumOrNull(primary?.estimated_protein_g) !== null ? " • " : ""}
                              {finiteNumOrNull(primary?.estimated_protein_g) !== null ? `${Math.round(finiteNumOrNull(primary?.estimated_protein_g))}g protein` : ""}
                            </Text>
                          ) : null}
                          {(() => {
                            const swaps = extractSwapSuggestions(primary);
                            return swaps.length ? (
                              <Text style={styles.swapHintText} numberOfLines={2}>
                                Better swap: {swaps[0]}
                              </Text>
                            ) : null;
                          })()}
                          {!!String(primary?.why_this_works || "").trim() ? (
                            <Text style={styles.tiny}>{String(primary.why_this_works).trim()}</Text>
                          ) : null}
                        </View>
                      ) : null}

                      {secondary.map((row, idx) => (
                        <View key={`daily-secondary-${idx}`} style={styles.dayCoachSection}>
                          <Text style={styles.dayCoachSectionTitle}>
                            {String(row?.headline || "Next option").trim()}
                          </Text>
                          <Text style={styles.tiny}>
                            {String(row?.place_name || "Nearby option")}
                            {String(row?.recommended_order || "").trim()
                              ? ` — ${String(row.recommended_order).trim()}`
                              : ""}
                          </Text>
                          {(finiteNumOrNull(row?.estimated_calories) !== null || finiteNumOrNull(row?.estimated_protein_g) !== null) ? (
                            <Text style={styles.tiny}>
                              {finiteNumOrNull(row?.estimated_calories) !== null ? `${Math.round(finiteNumOrNull(row?.estimated_calories))} kcal` : ""}
                              {finiteNumOrNull(row?.estimated_calories) !== null && finiteNumOrNull(row?.estimated_protein_g) !== null ? " • " : ""}
                              {finiteNumOrNull(row?.estimated_protein_g) !== null ? `${Math.round(finiteNumOrNull(row?.estimated_protein_g))}g protein` : ""}
                            </Text>
                          ) : null}
                          {(() => {
                            const swaps = extractSwapSuggestions(row);
                            return swaps.length ? (
                              <Text style={styles.swapHintText} numberOfLines={2}>
                                Better swap: {swaps[0]}
                              </Text>
                            ) : null;
                          })()}
                          {!!String(row?.why_this_works || "").trim() ? (
                            <Text style={styles.tiny}>{String(row.why_this_works).trim()}</Text>
                          ) : null}
                        </View>
                      ))}
                    </View>
                  );
                })()
              ) : null}
              {lunchDayCoach && !screenshotMode ? (
                (() => {
                  const daySummary = lunchDayCoach?.day_summary && typeof lunchDayCoach.day_summary === "object"
                    ? lunchDayCoach.day_summary
                    : null;
                  const nextMeal = lunchDayCoach?.next_meal_guidance && typeof lunchDayCoach.next_meal_guidance === "object"
                    ? lunchDayCoach.next_meal_guidance
                    : null;
                  const evening = lunchDayCoach?.evening_guidance && typeof lunchDayCoach.evening_guidance === "object"
                    ? lunchDayCoach.evening_guidance
                    : null;
                  const endOfDay = lunchDayCoach?.end_of_day_feedback && typeof lunchDayCoach.end_of_day_feedback === "object"
                    ? lunchDayCoach.end_of_day_feedback
                    : null;
                  const progress = daySummary?.progress && typeof daySummary.progress === "object"
                    ? daySummary.progress
                    : {};
                  const consumedCalRaw = finiteNumOrNull(progress?.consumed_calories);
                  const consumedCal = consumedCalRaw !== null
                    ? Math.round(consumedCalRaw)
                    : null;
                  const targetCalRaw = finiteNumOrNull(progress?.target_calories);
                  const targetCal = targetCalRaw !== null
                    ? Math.round(targetCalRaw)
                    : null;
                  const remainingCalRaw = finiteNumOrNull(progress?.remaining_calories);
                  const remainingCal = remainingCalRaw !== null
                    ? Math.round(remainingCalRaw)
                    : null;
                  const consumedProteinRaw = finiteNumOrNull(progress?.consumed_protein_g);
                  const consumedProtein = consumedProteinRaw !== null
                    ? Math.round(consumedProteinRaw)
                    : null;
                  const targetProteinRaw = finiteNumOrNull(progress?.target_protein_g);
                  const targetProtein = targetProteinRaw !== null
                    ? Math.round(targetProteinRaw)
                    : null;
                  const remainingProteinRaw = finiteNumOrNull(progress?.remaining_protein_g);
                  const remainingProtein = remainingProteinRaw !== null
                    ? Math.round(remainingProteinRaw)
                    : null;

                  return (
                    <View style={styles.dayCoachCard}>
                      <Text style={styles.healthyPanelSectionTitle}>AI Coach</Text>
                      {!!String(daySummary?.headline || "").trim() ? (
                        <Text style={styles.mapCoachHeadline}>{String(daySummary.headline).trim()}</Text>
                      ) : null}
                      {!!String(daySummary?.supporting_text || "").trim() ? (
                        <Text style={styles.mapCoachSupport}>{String(daySummary.supporting_text).trim()}</Text>
                      ) : null}

                      {(consumedCal !== null || targetCal !== null || consumedProtein !== null || targetProtein !== null) ? (
                        <Text style={styles.dayCoachProgressLine}>
                          {consumedCal !== null && targetCal !== null ? `Today: ${consumedCal}/${targetCal} kcal` : ""}
                          {consumedCal !== null && targetCal !== null && consumedProtein !== null && targetProtein !== null ? " • " : ""}
                          {consumedProtein !== null && targetProtein !== null ? `Protein: ${consumedProtein}/${targetProtein}g` : ""}
                        </Text>
                      ) : null}

                      {(remainingCal !== null || remainingProtein !== null) ? (
                        <Text style={styles.dayCoachProgressSubtle}>
                          {remainingCal !== null ? `${remainingCal} kcal left` : ""}
                          {remainingCal !== null && remainingProtein !== null ? " • " : ""}
                          {remainingProtein !== null ? `${remainingProtein}g protein left` : ""}
                        </Text>
                      ) : null}

                      {nextMeal ? (
                        <View style={styles.dayCoachSection}>
                          <Text style={styles.dayCoachSectionTitle}>{String(nextMeal?.headline || "Best next meal").trim()}</Text>
                          <Text style={styles.tiny}>
                            {String(nextMeal?.recommended_place_name || "Nearby pick")}
                            {String(nextMeal?.recommended_order || "").trim() ? ` — ${String(nextMeal.recommended_order).trim()}` : ""}
                          </Text>
                          {(finiteNumOrNull(nextMeal?.estimated_calories) !== null || finiteNumOrNull(nextMeal?.estimated_protein_g) !== null) ? (
                            <Text style={styles.tiny}>
                              {finiteNumOrNull(nextMeal?.estimated_calories) !== null ? `${Math.round(finiteNumOrNull(nextMeal?.estimated_calories))} kcal` : ""}
                              {finiteNumOrNull(nextMeal?.estimated_calories) !== null && finiteNumOrNull(nextMeal?.estimated_protein_g) !== null ? " • " : ""}
                              {finiteNumOrNull(nextMeal?.estimated_protein_g) !== null ? `${Math.round(finiteNumOrNull(nextMeal?.estimated_protein_g))}g protein` : ""}
                            </Text>
                          ) : null}
                          {!!String(nextMeal?.supporting_text || "").trim() ? (
                            <Text style={styles.tiny}>{String(nextMeal.supporting_text).trim()}</Text>
                          ) : null}
                        </View>
                      ) : null}

                      {evening ? (
                        <View style={styles.dayCoachSection}>
                          <Text style={styles.dayCoachSectionTitle}>{String(evening?.headline || "").trim()}</Text>
                          {!!String(evening?.supporting_text || "").trim() ? (
                            <Text style={styles.tiny}>{String(evening.supporting_text).trim()}</Text>
                          ) : null}
                        </View>
                      ) : null}

                      {endOfDay ? (
                        <View style={styles.dayCoachSection}>
                          <Text style={styles.dayCoachSectionTitle}>{String(endOfDay?.headline || "").trim()}</Text>
                          {!!String(endOfDay?.supporting_text || "").trim() ? (
                            <Text style={styles.tiny}>{String(endOfDay.supporting_text).trim()}</Text>
                          ) : null}
                          {!!String(endOfDay?.score_label || "").trim() ? (
                            <Text style={styles.dayCoachScoreLabel}>{String(endOfDay.score_label).trim()}</Text>
                          ) : null}
                        </View>
                      ) : null}
                    </View>
                  );
                })()
              ) : null}
              {(() => {
                const topCard = effectiveLunchDecision?.cards?.[0];
                const topDistM = num(topCard?.distance_meters);
                const topCardType = String(topCard?.card_type || "").trim().toLowerCase();
                const topCardIsHere =
                  topCardType === "best_right_now" &&
                  Number.isFinite(topDistM) &&
                  topDistM >= 0 &&
                  topDistM <= 100;

                return effectiveLunchDecision.cards.slice(0, screenshotMode ? 1 : 3).map((card, idx) => {
                const distanceLabel = formatDistanceFromMeters(card?.distance_meters);
                const distM = num(card?.distance_meters);
                const cardType = String(card?.card_type || "").trim().toLowerCase();
                const isHere = Number.isFinite(distM) && distM >= 0 && distM <= 100;
                const hasBetterNearby = effectiveLunchDecision?.cards?.some?.(
                  (c) => String(c?.card_type || "").trim().toLowerCase() === "better_alternative"
                );
                const labelText =
                  cardType === "best_right_now"
                    ? topCardIsHere && idx === 0 && isHere
                      ? "Best here right now"
                      : "Best nearby right now"
                    : cardType === "better_alternative"
                    ? topCardIsHere
                      ? "Better nearby"
                      : "Next best nearby"
                    : cardType === "hard_to_fit_today"
                    ? "Hard to fit today"
                    : String(card?.label || "").replace(/^[-–—\s]*|[\s]*$/g, "");
                const subLabel =
                  cardType === "best_right_now"
                    ? topCardIsHere && idx === 0 && isHere
                      ? "You’re here — best order at this venue."
                      : hasBetterNearby
                      ? "Top pick nearby — compare with a stronger alternative."
                      : "Top pick nearby right now."
                    : cardType === "better_alternative"
                    ? topCardIsHere
                      ? "Stronger option close by."
                      : "A strong alternative nearby."
                    : cardType === "hard_to_fit_today"
                    ? "If you must eat here, use the lightest swap."
                    : "";
                const badges = Array.isArray(card?.badges) ? card.badges.filter(Boolean).slice(0, 2) : [];
                const cardSwaps = extractSwapSuggestions(card);
                const cta = String(card?.cta_label || "").trim();
                const orderLabel = String(card?.recommended_order_label || "").trim();
                const fitForToday = card?.fit_for_today;
                const realityCheck = card?.reality_check && typeof card.reality_check === "object" ? card.reality_check : null;
                const caloriesSavedRaw = finiteNumOrNull(realityCheck?.calories_saved);
                const caloriesSaved = caloriesSavedRaw !== null
                  ? Math.max(0, Math.round(caloriesSavedRaw))
                  : null;
                const typicalOrderName = String(realityCheck?.typical_order?.name || "").trim();
                const orderCal = (card?.estimated_calories != null) ? num(card?.estimated_calories) : null;
                const orderProtein = (card?.estimated_protein_g != null) ? num(card?.estimated_protein_g) : null;
                const decisionCtx = effectiveLunchDecision?.decision_context;
                const dayProgress = effectiveLunchDecision?.day_coach?.day_summary?.progress;
                const pageRemainingCal =
                  (remainingToday?.kcal != null) ? num(remainingToday?.kcal) :
                  (decisionCtx?.remaining_calories != null) ? num(decisionCtx?.remaining_calories) :
                  (dayProgress?.remaining_calories != null) ? num(dayProgress?.remaining_calories) : null;
                const pageRemainingProtein =
                  (remainingToday?.protein_g != null) ? num(remainingToday?.protein_g) :
                  (decisionCtx?.remaining_protein_g != null) ? num(decisionCtx?.remaining_protein_g) :
                  (dayProgress?.remaining_protein_g != null) ? num(dayProgress?.remaining_protein_g) : null;
                const cardRemaining = (card?.remaining_calories != null) ? num(card?.remaining_calories) : null;
                const remainingLine = buildRemainingLine({
                  pageRemainingCal: pageRemainingCal,
                  pageRemainingProtein: pageRemainingProtein,
                  cardRemainingCal: cardRemaining,
                  cardRemainingProtein: num(card?.remaining_protein_g),
                  orderCal: orderCal,
                  orderProtein: orderProtein,
                });
                const feedbackKey =
                  String(card?.place_id || card?.place_name || "unknown").trim() +
                  "::" +
                  String(card?.recommended_order || card?.best_item_name || "").trim();
                const feedbackOpen = Boolean(nearbyDecisionFeedbackOpen?.[feedbackKey]);
                const feedback = (nearbyDecisionFeedback && typeof nearbyDecisionFeedback === "object")
                  ? (nearbyDecisionFeedback[feedbackKey] && typeof nearbyDecisionFeedback[feedbackKey] === "object"
                    ? nearbyDecisionFeedback[feedbackKey]
                    : {})
                  : {};
                const setFeedback = (patch) => {
                  if (!patch || typeof patch !== "object") return;
                  setNearbyDecisionFeedback((prev) => {
                    const base = prev && typeof prev === "object" ? prev : {};
                    const cur = base[feedbackKey] && typeof base[feedbackKey] === "object" ? base[feedbackKey] : {};
                    return { ...base, [feedbackKey]: { ...cur, ...patch, updated_at_ms: Date.now() } };
                  });
                  // Best-effort: backend can ignore until fully supported.
                  try {
                    void logRecommendationEvent("recommendation_feedback", card, {
                      feedback_key: feedbackKey,
                      ...patch,
                    });
                  } catch {}
                };

                const preset =
                  nearbyDecisionAssumptionPresets &&
                  typeof nearbyDecisionAssumptionPresets === "object" &&
                  nearbyDecisionAssumptionPresets[feedbackKey] &&
                  typeof nearbyDecisionAssumptionPresets[feedbackKey] === "object"
                    ? nearbyDecisionAssumptionPresets[feedbackKey]
                    : {};
                const setPreset = (patch) => {
                  if (!patch || typeof patch !== "object") return;
                  setNearbyDecisionAssumptionPresets((prev) => {
                    const base = prev && typeof prev === "object" ? prev : {};
                    const cur = base[feedbackKey] && typeof base[feedbackKey] === "object" ? base[feedbackKey] : {};
                    return { ...base, [feedbackKey]: { ...cur, ...patch, updated_at_ms: Date.now() } };
                  });
                };
                const cardForEvidence = {
                  ...(card && typeof card === "object" ? card : {}),
                  __assumptionPreset: preset,
                  __setAssumptionPreset: setPreset,
                };
                return (
                  <View
                    key={"lunch-card-" + idx}
                    style={[styles.lunchDecisionCard, idx === 0 ? styles.lunchDecisionCardTop : null]}
                  >
                    <Text style={styles.lunchDecisionLabel}>{labelText}</Text>
                    {!!subLabel && !screenshotMode ? (
                      <Text style={[styles.tiny, { marginTop: 2, color: "#94a3b8" }]} numberOfLines={2}>
                        {subLabel}
                      </Text>
                    ) : null}
                    <Text style={styles.itemName} numberOfLines={2}>
                      {String(card?.place_name || "Nearby option")}
                      {distanceLabel ? " (" + distanceLabel + ")" : ""}
                    </Text>
                    {!!orderLabel ? (
                      <Text style={[styles.tiny, { marginTop: 4 }]}>{orderLabel}</Text>
                    ) : null}
                    {!!String(card?.recommended_order || "").trim() ? (
                      <Text style={[styles.tiny, { marginTop: 4 }]}>Recommended: {String(card.recommended_order)}</Text>
                    ) : null}
                    <BestOrderEvidenceBlock
                      payload={cardForEvidence}
                      mode="card"
                      dark
                      compact
                      screenshotMode={screenshotMode}
                      style={{ marginTop: 6 }}
                    />
                    {Number.isFinite(num(card?.estimated_calories)) ? (
                      <Text style={styles.tiny}>Calories: ~{Math.round(num(card?.estimated_calories))}</Text>
                    ) : null}
                    {Number.isFinite(num(card?.estimated_protein_g)) ? (
                      <Text style={styles.tiny}>Protein: {Math.round(num(card?.estimated_protein_g))}g</Text>
                    ) : null}
                    {cardSwaps.length && !screenshotMode ? (
                      <Text style={styles.swapHintText} numberOfLines={2}>
                        Better swap: {cardSwaps[0]}
                      </Text>
                    ) : null}
                    {!!String(card?.typical_calorie_range || "").trim() ? (
                      <Text style={styles.tiny}>Typical meals: {String(card.typical_calorie_range)}</Text>
                    ) : null}
                    {remainingLine ? (
                      <Text style={styles.tiny}>{remainingLine}</Text>
                    ) : null}
                    {caloriesSaved !== null && caloriesSaved > 0 && !screenshotMode ? (
                      <Text style={[styles.tiny, styles.realitySavedText]}>✨ You saved {caloriesSaved} calories</Text>
                    ) : null}
                    {!!typicalOrderName ? (
                      <Text style={styles.tiny}>Typical order: {typicalOrderName}</Text>
                    ) : null}
                    {fitForToday === true ? (
                      <Text style={[styles.tiny, styles.lunchFitGood]}>✅ Fits today's macros</Text>
                    ) : null}
                    {fitForToday === false ? (
                      <Text style={[styles.tiny, styles.lunchFitCaution]}>⚠ Harder to fit today</Text>
                    ) : null}
                    {badges.length ? (
                      <View style={styles.lunchBadgeRow}>
                        {badges.map((badge, badgeIdx) => (
                          <View key={"lunch-badge-" + idx + "-" + badgeIdx} style={styles.lunchBadge}>
                            <Text style={styles.lunchBadgeText}>{String(badge)}</Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                    <Text style={[styles.tiny, { marginTop: 6 }]}>Why: {String(card?.why_this_works || "Good fit for today.")}</Text>
                    {!!String(card?.decision_reason || "").trim() ? (
                      <Text style={[styles.tiny, { marginTop: 4 }]}>Coach: {String(card.decision_reason).trim()}</Text>
                    ) : null}
                    <View style={styles.lunchCardActionsRow}>
                      {!!cta ? (
                        <TouchableOpacity
                          style={[styles.secondaryBtn, styles.lunchCardCtaBtn]}
                          onPress={() => {
                            void handleLunchDecisionCTA(card);
                          }}
                        >
                          <Text style={styles.btnText} numberOfLines={1}>
                            {cta}
                          </Text>
                        </TouchableOpacity>
                      ) : null}
                      <TouchableOpacity
                        style={[styles.smallBtn, styles.lunchShareBtn]}
                        onPress={() => {
                          void shareLunchDecisionCard(card);
                        }}
                      >
                        <Text style={styles.smallBtnText}>Share</Text>
                      </TouchableOpacity>
                    </View>

                    {!screenshotMode ? (
                      <View style={styles.nearbyFeedbackWrap}>
                        <TouchableOpacity
                          style={styles.nearbyFeedbackToggle}
                          onPress={() =>
                            setNearbyDecisionFeedbackOpen((prev) => ({
                              ...(prev && typeof prev === "object" ? prev : {}),
                              [feedbackKey]: !feedbackOpen,
                            }))
                          }
                          activeOpacity={0.85}
                        >
                          <Text style={styles.nearbyFeedbackToggleText}>
                            {feedbackOpen ? "Hide feedback" : "Quick feedback"}
                          </Text>
                        </TouchableOpacity>

                        {feedbackOpen ? (
                          <View style={styles.nearbyFeedbackBody}>
                            <Text style={styles.nearbyFeedbackQ}>Was this available?</Text>
                            <View style={styles.nearbyFeedbackRow}>
                              {["yes", "no", "not_sure"].map((v) => (
                                <TouchableOpacity
                                  key={"avail-" + v}
                                  style={[
                                    styles.nearbyFeedbackChip,
                                    feedback.available === v ? styles.nearbyFeedbackChipActive : null,
                                  ]}
                                  onPress={() => setFeedback({ available: v })}
                                  activeOpacity={0.85}
                                >
                                  <Text style={styles.nearbyFeedbackChipText}>
                                    {v === "yes" ? "Yes" : v === "no" ? "No" : "Not sure"}
                                  </Text>
                                </TouchableOpacity>
                              ))}
                            </View>

                            <Text style={styles.nearbyFeedbackQ}>Did you order this?</Text>
                            <View style={styles.nearbyFeedbackRow}>
                              {["yes", "no"].map((v) => (
                                <TouchableOpacity
                                  key={"ordered-" + v}
                                  style={[
                                    styles.nearbyFeedbackChip,
                                    feedback.ordered === v ? styles.nearbyFeedbackChipActive : null,
                                  ]}
                                  onPress={() => setFeedback({ ordered: v })}
                                  activeOpacity={0.85}
                                >
                                  <Text style={styles.nearbyFeedbackChipText}>{v === "yes" ? "Yes" : "No"}</Text>
                                </TouchableOpacity>
                              ))}
                            </View>

                            <Text style={styles.nearbyFeedbackQ}>Did it include sauce by default?</Text>
                            <View style={styles.nearbyFeedbackRow}>
                              {["yes", "no", "not_sure"].map((v) => (
                                <TouchableOpacity
                                  key={"sauce-" + v}
                                  style={[
                                    styles.nearbyFeedbackChip,
                                    feedback.sauce_default === v ? styles.nearbyFeedbackChipActive : null,
                                  ]}
                                  onPress={() => setFeedback({ sauce_default: v })}
                                  activeOpacity={0.85}
                                >
                                  <Text style={styles.nearbyFeedbackChipText}>
                                    {v === "yes" ? "Yes" : v === "no" ? "No" : "Not sure"}
                                  </Text>
                                </TouchableOpacity>
                              ))}
                            </View>

                            <Text style={styles.nearbyFeedbackQ}>Portion looked standard?</Text>
                            <View style={styles.nearbyFeedbackRow}>
                              {["yes", "no", "not_sure"].map((v) => (
                                <TouchableOpacity
                                  key={"portion-" + v}
                                  style={[
                                    styles.nearbyFeedbackChip,
                                    feedback.portion_standard === v ? styles.nearbyFeedbackChipActive : null,
                                  ]}
                                  onPress={() => setFeedback({ portion_standard: v })}
                                  activeOpacity={0.85}
                                >
                                  <Text style={styles.nearbyFeedbackChipText}>
                                    {v === "yes" ? "Yes" : v === "no" ? "No" : "Not sure"}
                                  </Text>
                                </TouchableOpacity>
                              ))}
                            </View>
                          </View>
                        ) : null}
                      </View>
                    ) : null}
                  </View>
                );
              });
              })()}
            </View>
          ) : null}
        </View>
        ) : null}

        {healthyNearbyTab === "map" ? (

        <View style={[styles.card, styles.healthyNearbySectionCard]}>
          <Text style={styles.nearbySectionHeader}>Map</Text>
          <Text style={styles.nearbySectionSubtle}>Tap a place to compare options.</Text>
          {(effectivePlaces || []).length ? (
            <View style={styles.healthyViewToggleRow}>
              <TouchableOpacity
                style={[styles.smallBtn, healthyViewMode === "map" ? styles.healthyViewToggleActive : null]}
                onPress={() => setHealthyViewMode("map")}
              >
                <Text style={styles.smallBtnText}>Map</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.smallBtn, healthyViewMode === "browse" ? styles.healthyViewToggleActive : null]}
                onPress={() => {
                  setHealthyViewMode("browse");
                  if (!(effectivePlaces || []).length && !healthyPlacesBusy) {
                    void loadHealthyPlacesNearby();
                  }
                }}
              >
                <Text style={styles.smallBtnText}>Browse</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.smallBtn, healthyViewMode === "list" ? styles.healthyViewToggleActive : null]}
                onPress={() => setHealthyViewMode("list")}
              >
                <Text style={styles.smallBtnText}>List</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {healthyViewMode === "map" ? (
            Platform.OS === "android" ? (
              <View>
                <Text style={[styles.nearbySectionSubtle, { marginBottom: 8 }]}>
                  Android uses a lighter map preview here for stability. Use List for the most reliable browsing.
                </Text>
                <HealthyNearbyDiscoverLayout
                  places={healthyVisiblePlaces}
                  filterKey={healthyMapFilter}
                  onFilterChange={setHealthyMapFilter}
                  selectedPlaceStableId={String(selectedHealthyPlaceId || "").trim()}
                  onSelectPlace={(place, idx) => {
                    setSelectedHealthyPlaceId(place ? healthyPlaceStableId(place, idx) : "");
                    if (place && Number.isFinite(num(place?.lat)) && Number.isFinite(num(place?.lng))) {
                      setHealthyMapFocusCoords({ lat: num(place.lat), lng: num(place.lng) });
                    }
                    const uid = userId || session?.user?.id;
                    if (uid && goalCoachContext?.action_type === ACTION_OPEN_HEALTHY_NEARBY) {
                      trackGoalCoachActionCompleted(API_BASE, uid, {
                        source_surface: goalCoachContext.source_surface,
                        action_type: ACTION_OPEN_HEALTHY_NEARBY,
                        completion_type: "place_selected",
                        place_id: place?.place_id,
                        place_name: place?.place_name || place?.name,
                        goal_type: goalCoachContext.goal,
                        remaining_protein_g: goalCoachContext.remaining_protein_g,
                        remaining_calories: goalCoachContext.remaining_calories,
                      });
                    }
                  }}
                  userCoords={healthyPlaceCoords}
                  focusCoords={healthyMapCenter}
                  onLoadPlaces={() => void loadHealthyPlacesNearby()}
                  onRefreshAroundMe={async () => {
                    try {
                      const fresh = await getCurrentCoords();
                      await loadHealthyPlacesNearby({ coords: fresh, preserveFilter: true });
                    } catch (e) {
                      Alert.alert("Location needed", errorToMessage(e?.message || e || "", 0));
                    }
                  }}
                  busy={healthyPlacesBusy && !hasFreshNearbySnapshot}
                  error={healthyPlacesError}
                  formatDistanceFromMeters={formatDistanceFromMeters}
                  getPlaceStableId={healthyPlaceStableId}
                />
              </View>
            ) : (
              <HealthyNearbyMapScreen
                places={healthyVisiblePlaces}
                filterKey={healthyMapFilter}
                onFilterChange={setHealthyMapFilter}
                selectedPlace={healthySelectedPlace}
                goalCoachContext={goalCoachContext}
                onSelectPlace={(place, idx) => {
                  setSelectedHealthyPlaceId(place ? healthyPlaceStableId(place, idx) : "");
                  if (place && Number.isFinite(num(place?.lat)) && Number.isFinite(num(place?.lng))) {
                    setHealthyMapFocusCoords({ lat: num(place.lat), lng: num(place.lng) });
                  }
                  const uid = userId || session?.user?.id;
                  if (uid && goalCoachContext?.action_type === ACTION_OPEN_HEALTHY_NEARBY) {
                    trackGoalCoachActionCompleted(API_BASE, uid, {
                      source_surface: goalCoachContext.source_surface,
                      action_type: ACTION_OPEN_HEALTHY_NEARBY,
                      completion_type: "place_selected",
                      place_id: place?.place_id,
                      place_name: place?.place_name || place?.name,
                      goal_type: goalCoachContext.goal,
                      remaining_protein_g: goalCoachContext.remaining_protein_g,
                      remaining_calories: goalCoachContext.remaining_calories,
                    });
                  }
                }}
                userCoords={healthyPlaceCoords}
                focusCoords={healthyMapCenter}
                onLoadPlaces={() => void loadHealthyPlacesNearby()}
                onRefreshAroundMe={async () => {
                  try {
                    const fresh = await getCurrentCoords();
                    await loadHealthyPlacesNearby({ coords: fresh, preserveFilter: true });
                  } catch (e) {
                    Alert.alert("Location needed", errorToMessage(e?.message || e || "", 0));
                  }
                }}
                onSearchWider={
                  healthyMapFilter === "all"
                    ? () => void loadHealthyPlacesNearby({ radius_m: WIDER_SEARCH_RADIUS_M })
                    : null
                }
                busy={healthyPlacesBusy && !hasFreshNearbySnapshot}
                error={healthyPlacesError}
                formatDistanceFromMeters={formatDistanceFromMeters}
                getPlaceStableId={healthyPlaceStableId}
                onScanMenu={(place) => {
                  void openCamera("menu_scan");
                }}
                onOpenDirections={(place) => {
                  openPlaceInMaps(place);
                  const uid = userId || session?.user?.id;
                  if (uid && goalCoachContext?.action_type === ACTION_OPEN_HEALTHY_NEARBY) {
                    trackGoalCoachActionCompleted(API_BASE, uid, {
                      source_surface: goalCoachContext.source_surface,
                      action_type: ACTION_OPEN_HEALTHY_NEARBY,
                      completion_type: "directions_opened",
                      place_id: place?.place_id,
                      place_name: place?.place_name || place?.name,
                      goal_type: goalCoachContext.goal,
                      remaining_protein_g: goalCoachContext.remaining_protein_g,
                      remaining_calories: goalCoachContext.remaining_calories,
                    });
                  }
                }}
              />
            )
          ) : null}

          {healthyViewMode === "browse" ? (
            <HealthyNearbyDiscoverLayout
              places={healthyVisiblePlaces}
              filterKey={healthyMapFilter}
              onFilterChange={setHealthyMapFilter}
              selectedPlaceStableId={String(selectedHealthyPlaceId || "").trim()}
              onSelectPlace={(place, idx) => {
                setSelectedHealthyPlaceId(place ? healthyPlaceStableId(place, idx) : "");
                if (place && Number.isFinite(num(place?.lat)) && Number.isFinite(num(place?.lng))) {
                  setHealthyMapFocusCoords({ lat: num(place.lat), lng: num(place.lng) });
                }
                const uid = userId || session?.user?.id;
                if (uid && goalCoachContext?.action_type === ACTION_OPEN_HEALTHY_NEARBY) {
                  trackGoalCoachActionCompleted(API_BASE, uid, {
                    source_surface: goalCoachContext.source_surface,
                    action_type: ACTION_OPEN_HEALTHY_NEARBY,
                    completion_type: "place_selected",
                    place_id: place?.place_id,
                    place_name: place?.place_name || place?.name,
                    goal_type: goalCoachContext.goal,
                    remaining_protein_g: goalCoachContext.remaining_protein_g,
                    remaining_calories: goalCoachContext.remaining_calories,
                  });
                }
              }}
              userCoords={healthyPlaceCoords}
              focusCoords={healthyMapCenter}
              onLoadPlaces={() => void loadHealthyPlacesNearby()}
              onRefreshAroundMe={async () => {
                try {
                  const fresh = await getCurrentCoords();
                  await loadHealthyPlacesNearby({ coords: fresh, preserveFilter: true });
                } catch (e) {
                  Alert.alert("Location needed", errorToMessage(e?.message || e || "", 0));
                }
              }}
              busy={healthyPlacesBusy && !hasFreshNearbySnapshot}
              error={healthyPlacesError}
              formatDistanceFromMeters={formatDistanceFromMeters}
              getPlaceStableId={healthyPlaceStableId}
            />
          ) : null}

          {healthyViewMode === "list"
            ? (() => {
                const renderPlaceCard = (place, idx) => {
                  const stableId = healthyPlaceStableId(place, idx);
                  const handleOpenInMaps = (p) => {
                    const uid = userId || (session?.user?.id ?? null);
                    if (uid && goalCoachContext?.action_type === ACTION_OPEN_HEALTHY_NEARBY) {
                      trackGoalCoachActionCompleted(API_BASE, uid, {
                        source_surface: goalCoachContext.source_surface,
                        action_type: ACTION_OPEN_HEALTHY_NEARBY,
                        completion_type: "directions_opened",
                        place_id: p?.place_id,
                        place_name: p?.place_name || p?.name,
                        goal_type: goalCoachContext.goal,
                        remaining_protein_g: goalCoachContext.remaining_protein_g,
                        remaining_calories: goalCoachContext.remaining_calories,
                      });
                    }
                    if (uid) {
                      const payload = buildDecisionEventPayload(p, "place_opened", {
                        userId: uid,
                        goal: resolveLunchGoal(),
                        timeOfDay: "",
                        tab: "healthy_nearby",
                      });
                      postMealDecisionEvent(payload);
                      setPendingMealFeedback({
                        place_id: String(p?.place_id || ""),
                        place_name: String(p?.place_name || p?.name || ""),
                        best_item_name: String(p?.best_item_name || p?.best_order || "").trim(),
                        selected_item_name: String(p?.best_item_name || p?.best_order || "").trim(),
                        selected_candidate_source: String(p?.menu_item_source || "").trim(),
                        accepted_swap_label: (extractSwapSuggestions(p)[0] || ""),
                        estimated_calories: p?.best_item_calories ?? p?.estimated_calories ?? null,
                        estimated_protein_g: p?.best_item_protein ?? p?.estimated_protein_g ?? null,
                        goal: resolveLunchGoal(),
                        time_of_day: "",
                        swap_accepted: false,
                      });
                    }
                    void openPlaceInMaps(p);
                  };
                  return (
                    <View key={stableId} style={{ marginBottom: 12 }}>
                      <HealthyPlaceListCard
                        place={place}
                        indexInSection={idx}
                        onOpenInMaps={handleOpenInMaps}
                        onPress={() => setPlaceDetailPlace(place)}
                        onFeedbackImprove={(p) => openContributionSheet(p, "healthy_nearby_list")}
                      />
                    </View>
                  );
                };
                if (healthySectionsFiltered?.length) {
                  return healthySectionsFiltered.map((sec, secIdx) => (
                    <View key={`section-${secIdx}-${String(sec.name).slice(0, 20)}`} style={{ marginBottom: 16 }}>
                      <Text style={[styles.healthyPanelSectionTitle, { marginBottom: 8 }]}>{sec.name}</Text>
                      {(sec.items || []).slice(0, 8).map((place, idx) => renderPlaceCard(place, idx))}
                    </View>
                  ));
                }
                return (healthyVisiblePlaces || []).slice(0, 8).map((place, idx) => renderPlaceCard(place, idx));
              })()
            : null}
        </View>
        ) : null}

        {healthyNearbyTab === "coach" ? (
        <View style={[styles.card, styles.weeklyCoachSectionCard]}>
          <View style={styles.weeklyCoachSectionTopRow}>
            <Text style={styles.nearbySectionHeader}>Weekly Coach</Text>
            <Text style={[styles.tiny, styles.nearbyLowPriorityHint]}>Weekly</Text>
          </View>
          <Text style={styles.nearbySectionSubtle}>Quick weekly summary.</Text>
          {renderWeeklyCoachBlock()}
        </View>
        ) : null}
        </>
        ) : null}

        {homeMainVisible ? (
        <>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Barcode</Text>
          <Text style={styles.p}>Elite+ can scan barcodes to fetch macros (OpenFoodFacts).</Text>

          <View style={styles.row}>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => openBarcodeScanner("lookup")} disabled={!canBarcode}>
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
          <Text style={styles.socialProofLine}>Join thousands staying on track with CalorieClick.</Text>

          <View style={styles.rowWrap}>
            {["elite", "advanced", "pro", "infinite"].map((p) => (
              <TouchableOpacity
                key={p}
                style={styles.secondaryBtn}
                onPress={() => purchaseEntitlement(p)}
                disabled={rcBusy || rcRefreshing || !rcReady}
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
            {rcRefreshing ? <Text style={[styles.muted, { marginTop: 6 }]}>Refreshing plans from store...</Text> : null}


            <Text style={[styles.muted, { marginTop: 8 }]}>
              Subscriptions are billed monthly and auto-renew unless cancelled at least 24 hours before the end of the
              current period. Payment will be charged to your Apple ID account at confirmation of purchase. You can
              manage or cancel your subscription in Apple ID Settings.
            </Text>

            <View style={{ marginTop: 10, flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
              <TouchableOpacity onPress={() => openURLSafe(PRIVACY_URL, "Could not open Privacy Policy.")}>
                <Text style={styles.link}>Privacy Policy</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => openURLSafe(TERMS_URL, "Could not open Terms of Use.")}>
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
                onPress={() => openURLSafe(s?.url, "Could not open source link.")}
                style={{ marginBottom: 8 }}
              >
                <Text style={styles.link}>• {s.title}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Privacy & Account</Text>
          <Text style={[styles.p, { marginTop: 6 }]}>
            AI processing consent controls whether meal images and coaching metadata are sent to trusted AI providers.
          </Text>

          <View style={{ marginTop: 10, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={styles.itemName}>Allow AI Processing</Text>
              <Text style={styles.tiny}>{aiConsentGiven ? "Enabled" : "Disabled"}</Text>
            </View>
            <TouchableOpacity
              style={[styles.smallBtn, aiConsentGiven ? styles.consentOnBtn : styles.consentOffBtn]}
              disabled={aiConsentLoading || !userId}
              onPress={() => {
                void updateAiConsent(!aiConsentGiven);
              }}
            >
              <Text style={styles.smallBtnText}>{aiConsentLoading ? "…" : aiConsentGiven ? "On" : "Off"}</Text>
            </TouchableOpacity>
          </View>

          <Text style={[styles.tiny, { marginTop: 8 }]}>
            If disabled, scan and AI coaching features are blocked until you re-enable consent.
          </Text>

          <View style={{ marginTop: 14 }}>
            <Text style={styles.itemName}>Delete Account</Text>
            <Text style={styles.tiny}>
              This permanently deletes scan history, coach data, goals, AI consent, and account login. This action cannot be undone.
            </Text>
            <TouchableOpacity
              style={[styles.secondaryBtn, styles.dangerBtn, { marginTop: 10 }]}
              onPress={confirmDeleteAccount}
              disabled={deleteAccountBusy || !userId}
            >
              <Text style={styles.btnText}>{deleteAccountBusy ? "Deleting…" : "Delete Permanently"}</Text>
            </TouchableOpacity>
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
              keyExtractor={(it, idx) => String(it?.ts || it?.analysis_id || idx)}
              renderItem={({ item }) => {
                const row = item && typeof item === "object" ? item : {};
                return (
                <TouchableOpacity
                  style={styles.histRow}
                  activeOpacity={0.75}
                  onPress={() => reopenHistoryEntry(row)}
                >
                  <Text style={styles.histTitle}>
                    {row.kind === "barcode"
                      ? `Barcode: ${row.name || row.barcode || "Unknown item"}`
                      : `Meal: ${round1(row?.total_kcal)} kcal`}
                  </Text>
                  <Text style={styles.tiny}>{row?.ts || "Saved scan"}</Text>
                  <Text style={[styles.tiny, { marginTop: 4, color: "#64748b" }]}>Tap to reopen</Text>
                </TouchableOpacity>
              )}}
            />
          ) : (
            <Text style={styles.tiny}>No history yet.</Text>
          )}
        </View>
        </>
        ) : null}

        <View style={{ height: 30 }} />
      
        <LetsGoSetupModal
          visible={letsGoModalVisible}
          onClose={() => setLetsGoModalVisible(false)}
          onSubmit={handleLetsGoSubmit}
          loading={goalCoachCreateBusy}
        />

        <Modal
          visible={paywallOpen}
          transparent
          animationType="fade"
          onRequestClose={() => { setPaywallOpen(false); setPaywallPlanHint(null); }}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              {(() => {
                const isPro = paywallPlanHint === "pro";
                const isElite = paywallPlanHint === "elite";
                const planKey = isPro ? "pro" : isElite ? "elite" : "advanced";
                const title = isPro ? "Upgrade to Pro" : isElite ? "Upgrade to Elite" : "Upgrade to Advanced";
                const benefits = isPro
                  ? [
                      "Daily diagnosis & risk alerts",
                      "Personalized action coaching (1–3 swaps)",
                      "Weekly report card & resilience score",
                    ]
                  : isElite
                  ? [
                      "Scan barcodes for instant macros",
                      "More daily and monthly scans",
                      "OpenFoodFacts nutrition data",
                    ]
                  : [
                      "Keep daily check-ins & journey",
                      "Log weight & progress photos",
                      "No limit on goal coaching",
                    ];
                const price = subscriptionPriceText(planKey);
                const planLabel = planKey.charAt(0).toUpperCase() + planKey.slice(1);
                return (
                  <>
                    <Text style={styles.cardTitle}>{title}</Text>
                    <View style={{ marginTop: 8 }}>
                      {benefits.map((b, i) => (
                        <Text key={i} style={[styles.tiny, { marginTop: i ? 4 : 0 }]}>
                          • {b}
                        </Text>
                      ))}
                    </View>
                    {price ? (
                      <Text style={[styles.p, { marginTop: 10, fontWeight: "700" }]}>{planLabel} — {price}/month</Text>
                    ) : null}
                    <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                      <TouchableOpacity
                        style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                        onPress={() => { setPaywallOpen(false); setPaywallPlanHint(null); }}
                      >
                        <Text style={styles.btnText}>Not now</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.btn, { flex: 1 }]}
                        onPress={async () => {
                          setPaywallOpen(false);
                          setPaywallPlanHint(null);
                          await purchaseEntitlement(planKey);
                        }}
                        disabled={rcBusy || rcRefreshing || !rcReady}
                      >
                        <Text style={styles.btnText}>{rcBusy ? "…" : "Upgrade"}</Text>
                      </TouchableOpacity>
                    </View>
                  </>
                );
              })()}
            </View>
          </View>
        </Modal>

        <Modal visible={editMacrosModalVisible} transparent animationType="fade" onRequestClose={() => setEditMacrosModalVisible(false)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.cardTitle}>Edit macros</Text>
              <Text style={styles.tiny}>Correct protein/carbs/fat for this scan. kcal updates from macros.</Text>

              <View style={{ marginTop: 12 }}>
                <Text style={styles.label}>Protein (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(macroDraft?.protein_g ?? "")}
                  onChangeText={(v) => setMacroDraft((d) => ({ ...d, protein_g: v }))}
                  placeholder="e.g., 30"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Carbs (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(macroDraft?.carbs_g ?? "")}
                  onChangeText={(v) => setMacroDraft((d) => ({ ...d, carbs_g: v }))}
                  placeholder="e.g., 45"
                  placeholderTextColor="#666"
                />

                <Text style={styles.label}>Fat (g)</Text>
                <TextInput
                  style={styles.input}
                  keyboardType="numeric"
                  value={String(macroDraft?.fat_g ?? "")}
                  onChangeText={(v) => setMacroDraft((d) => ({ ...d, fat_g: v }))}
                  placeholder="e.g., 18"
                  placeholderTextColor="#666"
                />

                <Text style={[styles.p, { marginTop: 10 }]}>
                  kcal preview:{" "}
                  {round1((4 * Math.max(0, num(macroDraft?.protein_g))) + (4 * Math.max(0, num(macroDraft?.carbs_g))) + (9 * Math.max(0, num(macroDraft?.fat_g))))}
                </Text>
              </View>

              <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => setEditMacrosModalVisible(false)}
                >
                  <Text style={styles.btnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.btn, { flex: 1 }]} onPress={() => void applyMacroOverrideCorrection()} disabled={rerunBusy}>
                  <Text style={styles.btnText}>Apply correction</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal visible={goalsModal} transparent animationType="fade" onRequestClose={() => closeBooleanStateSafely(setGoalsModal)}>
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
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => closeBooleanStateSafely(setGoalsModal)}
                >
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
          visible={smartAlertInboxVisible}
          transparent
          animationType="slide"
          onRequestClose={() => setSmartAlertInboxVisible(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalCard, { maxHeight: "80%" }]}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <Text style={styles.cardTitle}>Smart Food Alerts</Text>
                <TouchableOpacity style={styles.smallBtn} onPress={() => setSmartAlertInboxVisible(false)}>
                  <Text style={styles.smallBtnText}>Close</Text>
                </TouchableOpacity>
              </View>
              <SmartAlertInbox
                candidates={smartAlertCandidates}
                loading={smartAlertsBusy}
                onOpenPlace={async (cand) => {
                  const aid = getAlertId(cand);
                  await recordAlertOpened(aid, cand.place_id);
                  setSmartAlertState(await getSmartAlertState());
                  await openPlaceFromSmartAlert(cand);
                }}
                onDismiss={async (cand) => {
                  const aid = getAlertId(cand);
                  await recordAlertDismissed(aid, cand.place_id);
                  setSmartAlertState(await getSmartAlertState());
                  setSmartAlertCandidates((prev) => prev.filter((p) => getAlertId(p) !== aid));
                }}
                onRefresh={() => void fetchSmartAlerts({ force: true })}
              />
            </View>
          </View>
        </Modal>

        <Modal
          visible={smartAlertSettingsVisible}
          transparent
          animationType="fade"
          onRequestClose={() => setSmartAlertSettingsVisible(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <Text style={styles.cardTitle}>Smart Alert Settings</Text>
                <TouchableOpacity style={styles.smallBtn} onPress={() => setSmartAlertSettingsVisible(false)}>
                  <Text style={styles.smallBtnText}>Done</Text>
                </TouchableOpacity>
              </View>
              <ScrollView style={{ maxHeight: 400 }} showsVerticalScrollIndicator={false}>
                <SmartAlertSettings
                  enabled={smartAlertState?.enabled ?? false}
                  categories={smartAlertState?.categories ?? {}}
                  frequencyMode={smartAlertState?.frequency_mode ?? "smart_only"}
                  pushPermissionStatus={pushPermissionStatus}
                  onRequestPushPermission={async () => {
                    if (pushPermissionPromptedThisSessionRef.current) return;
                    pushPermissionPromptedThisSessionRef.current = true;
                    const result = await requestPushPermissionsIfNeeded();
                    setPushPermissionStatus(result);
                    if (result.granted) {
                      const token = await getExpoPushTokenSafe();
                      if (token) {
                        const uid = userId || session?.user?.id;
                        if (uid) {
                          const reg = await registerPushTokenWithBackend({
                            userId: uid,
                            expoPushToken: token,
                            platform: Platform.OS,
                          });
                          if (reg.ok) {
                            setExpoPushToken(token);
                            setPushRegisteredUserId(uid);
                            pushRegistrationRef.current = { userId: uid, token };
                          }
                        }
                      }
                    }
                  }}
                  onOpenSettings={() => Linking.openSettings()}
                  onEnabledChange={async (v) => {
                    const next = await updateSmartAlertSettings({ enabled: v });
                    setSmartAlertState(next);
                  }}
                  onCategoryChange={async (key, v) => {
                    const next = await updateSmartAlertSettings({
                      categories: { [key]: v },
                    });
                    setSmartAlertState(next);
                  }}
                  onFrequencyChange={async (mode) => {
                    const next = await updateSmartAlertSettings({ frequency_mode: mode });
                    setSmartAlertState(next);
                  }}
                />
              </ScrollView>
            </View>
          </View>
        </Modal>

        <Modal
          visible={adminOpsVisible}
          transparent
          animationType="fade"
          onRequestClose={() => setAdminOpsVisible(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalCard, { width: "96%", maxHeight: "90%", padding: 0 }]}>
              <AdminOpsDashboard onClose={() => setAdminOpsVisible(false)} />
            </View>
          </View>
        </Modal>

        <Modal
          visible={coachProfileModal}
          transparent
          animationType="fade"
          onRequestClose={() => closeBooleanStateSafely(setCoachProfileModal)}
        >
          <View style={styles.modalBackdrop}>
            <View style={[styles.modalCard, { maxHeight: "88%" }]}>
              <Text style={styles.cardTitle}>Coach profile</Text>
              <Text style={styles.tiny}>
                Goals and style stay on this device. Foods and reminders below are also sent to your coach on the server when you save or refresh daily
                coaching.
              </Text>

              <ScrollView
                style={{ marginTop: 10, maxHeight: 440 }}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
              >
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

                <Text style={styles.label}>Dietary restrictions (optional)</Text>
                <View style={styles.rowWrap}>
                  {DIETARY_RESTRICTION_OPTIONS.map((r) => {
                    const selected = (coachProfileDraft?.dietary_restrictions || []).includes(r);
                    return (
                      <TouchableOpacity
                        key={r}
                        style={[styles.chip, selected && styles.chipActive]}
                        onPress={() =>
                          setCoachProfileDraft((p) => {
                            const cur = Array.isArray(p?.dietary_restrictions) ? p.dietary_restrictions : [];
                            const next = selected ? cur.filter((x) => x !== r) : [...cur, r];
                            return { ...p, dietary_restrictions: next };
                          })
                        }
                      >
                        <Text style={styles.chipText}>{r.replace("_", " ")}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <Text style={styles.label}>Allergies / exclude (optional)</Text>
                <View style={styles.rowWrap}>
                  {ALLERGEN_EXCLUDE_OPTIONS.map((a) => {
                    const selected = (coachProfileDraft?.allergen_exclude || []).includes(a);
                    return (
                      <TouchableOpacity
                        key={a}
                        style={[styles.chip, selected && styles.chipActive]}
                        onPress={() =>
                          setCoachProfileDraft((p) => {
                            const cur = Array.isArray(p?.allergen_exclude) ? p.allergen_exclude : [];
                            const next = selected ? cur.filter((x) => x !== a) : [...cur, a];
                            return { ...p, allergen_exclude: next };
                          })
                        }
                      >
                        <Text style={styles.chipText}>{a}</Text>
                      </TouchableOpacity>
                    );
                  })}
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

                <Text style={[styles.label, { marginTop: 6 }]}>Coach memory</Text>
                <Text style={styles.tiny}>
                  Short notes your coach can reuse (favorite meals, dislikes, weekly focus). Up to 12 foods and 8 reminders; duplicates ignored.
                </Text>

                <Text style={[styles.label, { marginTop: 8 }]}>Foods you want remembered</Text>
                <View style={styles.rowWrap}>
                  {(coachProfileDraft?.food_preferences || []).map((item, idx) => (
                    <View
                      key={`food-${idx}-${String(item).slice(0, 24)}`}
                      style={[styles.chip, { flexDirection: "row", alignItems: "center", paddingRight: 6 }]}
                    >
                      <Text style={[styles.chipText, { maxWidth: 220 }]} numberOfLines={2}>
                        {item}
                      </Text>
                      <TouchableOpacity onPress={() => removeCoachFoodPreference(idx)} hitSlop={{ top: 10, bottom: 10, left: 8, right: 8 }}>
                        <Text style={{ color: "#94a3b8", fontSize: 16, fontWeight: "700" }}>×</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </View>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center", marginTop: 8 }}>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    value={coachMemoryFoodInput}
                    onChangeText={setCoachMemoryFoodInput}
                    placeholder="e.g., oatmeal most mornings"
                    placeholderTextColor="#666"
                    onSubmitEditing={addCoachFoodPreference}
                    returnKeyType="done"
                  />
                  <TouchableOpacity style={styles.smallBtn} onPress={addCoachFoodPreference}>
                    <Text style={styles.smallBtnText}>Add</Text>
                  </TouchableOpacity>
                </View>

                <Text style={[styles.label, { marginTop: 12 }]}>Goal-based reminders</Text>
                <View style={styles.rowWrap}>
                  {(coachProfileDraft?.goal_reminders || []).map((item, idx) => (
                    <View
                      key={`goal-${idx}-${String(item).slice(0, 24)}`}
                      style={[styles.chip, { flexDirection: "row", alignItems: "center", paddingRight: 6 }]}
                    >
                      <Text style={[styles.chipText, { maxWidth: 220 }]} numberOfLines={2}>
                        {item}
                      </Text>
                      <TouchableOpacity onPress={() => removeCoachGoalReminder(idx)} hitSlop={{ top: 10, bottom: 10, left: 8, right: 8 }}>
                        <Text style={{ color: "#94a3b8", fontSize: 16, fontWeight: "700" }}>×</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </View>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center", marginTop: 8, marginBottom: 6 }}>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    value={coachMemoryGoalInput}
                    onChangeText={setCoachMemoryGoalInput}
                    placeholder="e.g., prioritize sleep this week"
                    placeholderTextColor="#666"
                    onSubmitEditing={addCoachGoalReminder}
                    returnKeyType="done"
                  />
                  <TouchableOpacity style={styles.smallBtn} onPress={addCoachGoalReminder}>
                    <Text style={styles.smallBtnText}>Add</Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity style={[styles.smallBtn, { alignSelf: "flex-start", marginBottom: 4 }]} onPress={clearCoachMemoryLists}>
                  <Text style={styles.smallBtnText}>Clear memory lists</Text>
                </TouchableOpacity>
              </ScrollView>

              <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => closeBooleanStateSafely(setCoachProfileModal)}
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

        <Modal visible={aiConsentModalVisible && Boolean(session)} transparent animationType="fade">
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.cardTitle}>AI Processing Consent</Text>
              <Text style={[styles.p, { marginTop: 8 }]}>
                To analyze your food photos and generate nutrition insights, CalorieClick securely sends:
              </Text>
              <Text style={styles.tiny}>• Food images</Text>
              <Text style={styles.tiny}>• Nutrition metadata</Text>
              <Text style={styles.tiny}>• Your selected goals</Text>
              <Text style={styles.tiny}>• Coaching preferences</Text>
              <Text style={[styles.p, { marginTop: 8 }]}>
                to trusted AI providers (Google Gemini API or equivalent). No advertising identifiers are shared. No data is sold.
              </Text>
              <Text style={[styles.tiny, { marginTop: 6 }]}>
                AI providers are contractually required to provide equal or stronger data protection standards.
              </Text>

              <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => {
                    void updateAiConsent(false);
                  }}
                  disabled={aiConsentLoading}
                >
                  <Text style={styles.btnText}>{aiConsentLoading ? "…" : "Decline"}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1 }]}
                  onPress={() => {
                    void updateAiConsent(true);
                  }}
                  disabled={aiConsentLoading}
                >
                  <Text style={styles.btnText}>{aiConsentLoading ? "…" : "Accept"}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal visible={supplementProcessingVisible} transparent animationType="fade">
          <View style={styles.suppProcessingOverlay}>
            <View style={styles.suppProcessingCard}>
              <Text style={styles.suppProcessingTitle}>🛡 Verifying Product Authenticity...</Text>
              {SUPPLEMENT_PROCESSING_CHECKS.map((line, idx) => {
                const visible = supplementProcessingIndex > idx;
                return (
                  <Text
                    key={line}
                    style={[
                      styles.suppProcessingLine,
                      { opacity: visible ? 1 : 0.24 },
                    ]}
                  >
                    {visible ? "✔" : "•"} {line}
                  </Text>
                );
              })}
            </View>
          </View>
        </Modal>

        <Modal
          visible={supplementReportModal}
          transparent
          animationType="fade"
          onRequestClose={() => closeBooleanStateSafely(setSupplementReportModal)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.cardTitle}>Report Suspicious Product</Text>
              <Text style={styles.tiny}>Select the closest reason for additional verification review.</Text>

              <View style={{ marginTop: 10 }}>
                {SUPPLEMENT_REPORT_REASONS.map((reason) => (
                  <TouchableOpacity
                    key={reason.key}
                    style={[
                      styles.chip,
                      supplementReportReason === reason.key && styles.chipActive,
                      { marginBottom: 8, alignSelf: "flex-start" },
                    ]}
                    onPress={() => setSupplementReportReason(reason.key)}
                  >
                    <Text style={styles.chipText}>{reason.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {supplementReportReason === "other" ? (
                <TextInput
                  style={styles.input}
                  value={supplementReportOther}
                  onChangeText={setSupplementReportOther}
                  placeholder="Describe the issue"
                  placeholderTextColor="#777"
                  multiline
                />
              ) : null}

              <View style={{ flexDirection: "row", gap: 10, marginTop: 14 }}>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1, backgroundColor: "#2c2c2c" }]}
                  onPress={() => closeBooleanStateSafely(setSupplementReportModal)}
                  disabled={supplementReportBusy}
                >
                  <Text style={styles.btnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btn, { flex: 1 }]}
                  onPress={() => {
                    void reportSupplementIssue(supplementReportReason, supplementReportOther);
                  }}
                  disabled={supplementReportBusy}
                >
                  <Text style={styles.btnText}>{supplementReportBusy ? "…" : "Submit Report"}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

      </ScrollView>

      {homeMainVisible ? (
        <View style={styles.homeBottomTabBarOuter}>
          <LinearGradient
            colors={["rgba(147,197,253,0.5)", "rgba(34,197,94,0.45)", "rgba(34,197,94,0)"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.homeBottomTabBarHairline}
            pointerEvents="none"
          />
          <View style={styles.homeBottomTabBar} accessibilityRole="tablist">
            {[
              { key: "today", label: "Today", icon: "⌂" },
              { key: "coach", label: "Coach", icon: "◎", badge: coachTabShowDot },
              { key: "plan", label: "Plan", icon: "≡", badgeDot: planTabShowBadge },
              { key: "more", label: "More", icon: "···" },
            ].map((t) => (
              <TouchableOpacity
                key={t.key}
                style={[styles.homeBottomTabItem, homeHubTab === t.key ? styles.homeBottomTabItemActive : null]}
                onPress={() => {
                  setHomeHubTab(t.key);
                  try {
                    mainScrollRef.current?.scrollTo({ y: 0, animated: true });
                  } catch (_) {}
                }}
                accessibilityRole="tab"
                accessibilityLabel={t.label}
                accessibilityState={{ selected: homeHubTab === t.key }}
                activeOpacity={0.88}
              >
                <View style={styles.homeBottomTabIconWrap}>
                  <Text style={[styles.homeBottomTabIcon, homeHubTab === t.key ? styles.homeBottomTabIconActive : null]}>
                    {t.icon}
                  </Text>
                  {(t.badge || t.badgeDot) ? <View style={styles.homeBottomTabBadgeDot} /> : null}
                </View>
                <Text style={[styles.homeBottomTabLabel, homeHubTab === t.key ? styles.homeBottomTabLabelActive : null]}>
                  {t.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ) : null}

      <MealFeedbackPrompt
        visible={!!showMealFeedbackPrompt && !!pendingMealFeedback}
        pending={pendingMealFeedback}
        onSkip={() => {
          setShowMealFeedbackPrompt(false);
          setPendingMealFeedback(null);
        }}
        onSubmit={(answers) => {
          const uid = userId || (session?.user?.id ?? null);
          if (uid && pendingMealFeedback) {
            const payload = buildMealFeedbackPayload(pendingMealFeedback, answers, {
              userId: uid,
              goal: resolveLunchGoal(),
              timeOfDay: "",
            });
            postMealFeedback(payload);
          }
          setShowMealFeedbackPrompt(false);
          setPendingMealFeedback(null);
        }}
      />

      <PlaceDetailSheet
        visible={!!placeDetailPlace}
        place={placeDetailPlace}
        onClose={() => setPlaceDetailPlace(null)}
        onOpenInMaps={(p) => {
          void openPlaceInMaps(p);
        }}
      />

      <VenueContributionSheet
        visible={contributionSheetVisible}
        onClose={() => setContributionSheetVisible(false)}
        onSubmit={async ({ contributionType, suggestedItemText }) => {
          const uid = userId || (session?.user?.id ?? null);
          if (!uid || !contributionPlace?.place) return;
          await postVenueContribution({
            place: contributionPlace.place,
            userId: uid,
            contributionType,
            suggestedItemText,
            sourceSurface: contributionPlace.sourceSurface || "healthy_nearby_map",
            dietContext: { goal: resolveLunchGoal() },
          });
        }}
      />

      {/* CAMERA MODAL */}
      <Modal visible={camOpen} animationType="slide">
        <SafeAreaView style={styles.modalSafe}>
          <View style={styles.modalTop}>
            <TouchableOpacity style={styles.smallBtn} onPress={() => setCamOpen(false)}>
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>{cameraTitle}</Text>
            <View style={{ width: 70 }} />
          </View>
          {goalCoachPendingCompletionRef.current?.action_type === ACTION_OPEN_SCAN_CAMERA ? (
            <View style={{ paddingHorizontal: 14, paddingBottom: 8 }}>
              <Text style={styles.tiny}>
                Goal Coach: take a meal photo — we’ll analyze it automatically.
              </Text>
            </View>
          ) : null}

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
            <TouchableOpacity
              style={styles.smallBtn}
              onPress={() => {
                setBarcodeOpen(false);
                setBarcodeMode("lookup");
              }}
            >
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>{barcodeModalTitle}</Text>
            <View style={{ width: 70 }} />
          </View>

          <CameraView
            style={styles.camera}
            facing="back"
            barcodeScannerSettings={{
              barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"],
            }}
            onBarcodeScanned={barcodeMode === "lookup" && barcodeBusy ? undefined : onBarcodeScanned}
          />

          <View style={styles.modalBottom}>
            <Text style={styles.tiny}>
              {barcodeMode === "supplement"
                ? "Point camera at supplement barcode. Capture is automatic."
                : "Point camera at barcode. It will auto-detect."}
            </Text>
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000", paddingBottom: 24 },
  safeFlex: { flex: 1 },
  mainScrollFlex: { flex: 1 },
  nearbyScreenBg: { backgroundColor: "#03080f" },
  container: { padding: 18, gap: 14, paddingBottom: 36 },
  containerAboveBottomTabs: { paddingBottom: 100 },
  // Phase 1 home spacing (token-based): use wrapper views, avoid large refactors.
  homeSection: { marginTop: tSpacing.section },
  homeSectionTight: { marginTop: tSpacing.xl },
  homeHubSegmentWrap: { marginTop: 2 },
  homeHubSegmentRow: {
    flexDirection: "row",
    backgroundColor: "#070d16",
    borderRadius: 18,
    padding: 4,
    borderWidth: 1,
    borderColor: "#1a2535",
    gap: 4,
  },
  homeHubSegmentPill: {
    flex: 1,
    paddingVertical: 11,
    paddingHorizontal: 6,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  homeHubSegmentPillActive: {
    backgroundColor: "rgba(34, 197, 94, 0.14)",
    borderWidth: 1,
    borderColor: "rgba(34, 197, 94, 0.45)",
  },
  homeHubSegmentText: { fontSize: 13, fontWeight: "700", color: "#64748b", letterSpacing: 0.2 },
  homeHubSegmentTextActive: { color: "#ecfdf5" },
  homeHubSegmentHint: {
    marginTop: 8,
    fontSize: 12,
    color: "#64748b",
    lineHeight: 17,
    textAlign: "center",
    letterSpacing: 0.15,
  },
  topRowHint: {
    fontSize: 11,
    color: "#64748b",
    maxWidth: 200,
    textAlign: "right",
    lineHeight: 15,
  },
  todaySummaryStripWrap: {
    marginTop: 2,
    borderRadius: dr.xl,
    borderWidth: 1,
    borderColor: dt.surface.cardBorder,
    backgroundColor: dt.surface.elevated,
    overflow: "hidden",
    ...dsh.sm,
  },
  todaySummaryStripHairline: {
    height: 2,
    width: "100%",
    opacity: 0.95,
  },
  todaySummaryStrip: {
    backgroundColor: "transparent",
    borderRadius: 0,
    borderWidth: 0,
    paddingVertical: tSpacing.base,
    paddingHorizontal: tSpacing.lg,
    marginTop: 0,
  },
  todaySummaryStripLabel: {
    fontSize: 11,
    fontWeight: "800",
    color: dt.slate.primary,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  todaySummaryStripMetrics: {
    fontSize: 14,
    color: dt.text.secondary,
    lineHeight: 20,
    fontWeight: "600",
  },
  homeBottomTabBarOuter: {
    backgroundColor: dt.surface.elevated,
    borderTopWidth: 1,
    borderTopColor: "rgba(26, 38, 66, 0.9)",
  },
  homeBottomTabBarHairline: {
    height: 2,
    width: "100%",
    opacity: 0.95,
  },
  homeBottomTabBar: {
    flexDirection: "row",
    alignItems: "stretch",
    justifyContent: "space-between",
    backgroundColor: "transparent",
    paddingTop: tSpacing.sm,
    paddingBottom: Platform.OS === "ios" ? 22 : 10,
    paddingHorizontal: tSpacing.xs,
  },
  homeBottomTabItem: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: tSpacing.xs,
    borderRadius: dr.lg,
  },
  homeBottomTabItemActive: {
    backgroundColor: "rgba(34, 197, 94, 0.12)",
  },
  homeBottomTabIconWrap: {
    position: "relative",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 22,
  },
  homeBottomTabIcon: {
    fontSize: 17,
    color: dt.slate.primary,
    fontWeight: "800",
  },
  homeBottomTabIconActive: { color: dt.success.text },
  homeBottomTabBadgeDot: {
    position: "absolute",
    top: -1,
    right: -6,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#f59e0b",
    borderWidth: 1,
    borderColor: dt.surface.primary,
  },
  homeBottomTabLabel: {
    fontSize: 10,
    fontWeight: "700",
    color: dt.slate.primary,
    marginTop: 2,
    letterSpacing: 0.2,
  },
  homeBottomTabLabelActive: { color: dt.text.primary },
  homeMorePanel: { marginTop: tSpacing.section, padding: 16, gap: 0 },
  homeMoreRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(148, 163, 184, 0.15)",
  },
  homeMoreRowText: { fontSize: 16, color: "#e2e8f0", fontWeight: "600" },
  homeMoreChevron: { fontSize: 20, color: "#64748b", fontWeight: "300" },
  h1: { fontSize: 26, fontWeight: "900", color: "#fff", lineHeight: 31, letterSpacing: 0.2 },
  p: { fontSize: 14, color: "#cfd7e3", lineHeight: 21 },
  tiny: { fontSize: 12, color: "#92a0b3", lineHeight: 17 },
  muted: { fontSize: 12, color: "#aab4c4", lineHeight: 17 },
  plan: { color: "#fff", fontWeight: "800" },

  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    rowGap: 8,
    flexWrap: "wrap",
    width: "100%",
  },
  topRowTitle: {
    flexGrow: 1,
    flexShrink: 1,
    minWidth: 0,
    paddingRight: 4,
  },
  topRowActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: 8,
    alignSelf: "flex-end",
    maxWidth: "100%",
  },
  row: { flexDirection: "row", gap: 10, marginTop: 12 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 12 },

  card: {
    backgroundColor: "#0b0b0b",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#1f2430",
    padding: 16,
  },
  launcherCard: {
    backgroundColor: dt.surface.primary,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: dt.surface.cardBorder,
    padding: 20,
    gap: 14,
    ...dsh.md,
  },
  launcherTitle: {
    color: dt.accent.muted,
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  launcherQuestion: {
    color: "#fff",
    fontSize: 28,
    fontWeight: "900",
    lineHeight: 34,
    letterSpacing: 0.2,
  },
  launcherSubline: { color: dt.accent.muted, fontSize: 14, lineHeight: 20 },
  launcherActions: { gap: 12, marginTop: 14 },
  launcherPrimaryCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: dt.success.primary,
    backgroundColor: dt.surface.card,
    paddingVertical: 16,
    paddingHorizontal: 16,
    ...dsh.sm,
  },
  launcherPrimaryIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(34,197,94,0.18)",
  },
  launcherPrimaryIcon: { fontSize: 24 },
  launcherRow: {
    flexDirection: "row",
    gap: 10,
  },
  launcherSecondaryCard: {
    flex: 1,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    borderRadius: dr.xl,
    borderWidth: 1,
    borderColor: dt.surface.cardBorder,
    backgroundColor: dt.surface.elevated,
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginTop: 10,
    ...dsh.sm,
  },
  launcherActionIcon: { fontSize: 20, marginTop: 2 },
  launcherActionTitle: { color: "#fff", fontSize: 18, fontWeight: "800", lineHeight: 22 },
  launcherActionSubtitle: { color: "#aac0de", fontSize: 13, marginTop: 2, lineHeight: 18 },
  launcherSecondaryTitle: { color: "#e5e7eb", fontSize: 15, fontWeight: "700" },
  launcherSecondarySubtitle: { color: "#94a3b8", fontSize: 12, marginTop: 2, lineHeight: 16 },
  launcherCoachLine: { color: "#c6daf6", fontSize: 12, lineHeight: 18, marginTop: 3 },
  launcherUtilityRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    marginTop: 10,
  },
  launcherUtilityBtnSpacer: { marginLeft: 10 },
  // launcherUtilityBtn/Text migrated to premium.ctaGhost / premium.ctaGhostText
  launcherValueRow: { marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: "rgba(41, 98, 255, 0.25)" },
  launcherValueText: { color: "#94b8d9", fontSize: 13, lineHeight: 18 },
  launcherValueBtn: { marginTop: 8, alignSelf: "flex-start", paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: "rgba(34, 197, 94, 0.2)", borderWidth: 1, borderColor: "#22c55e" },
  launcherValueBtnText: { color: "#4ade80", fontSize: 13, fontWeight: "700" },
  socialProofLine: { fontSize: 12, color: "#86efac", fontStyle: "italic", marginTop: 4 },
  cardTitle: { color: "#fff", fontWeight: "800", fontSize: 18, lineHeight: 23, letterSpacing: 0.2 },
  big: { color: "#fff", fontWeight: "800", fontSize: 20, lineHeight: 25, marginTop: 7 },

  scansLowBanner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: "rgba(245, 158, 11, 0.12)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.35)",
  },
  scansLowText: { flex: 1, fontSize: 13, color: "#fcd34d", lineHeight: 18 },
  scansLowBtn: { paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: "#22c55e" },
  scansLowBtnText: { fontSize: 14, fontWeight: "700", color: "#fff" },

  // Phase 3: compact lower-home modules (status-strip feel)
  compactStatusCard: {
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderRadius: 18,
    backgroundColor: "rgba(11, 20, 36, 0.65)",
    borderColor: "rgba(31, 46, 69, 0.9)",
  },
  compactHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  compactHeaderActions: { marginLeft: 10, flexDirection: "row", alignItems: "center" },
  compactTitle: { color: "#e5e7eb", fontSize: 13, fontWeight: "800", letterSpacing: 0.2 },
  compactValue: { color: "#fff", fontSize: 18, fontWeight: "900", marginTop: 4 },
  // compactGhostBtn/Text migrated to premium.ctaGhost / premium.ctaGhostText
  compactActionsRow: { flexDirection: "row", alignItems: "center", marginTop: 10 },
  // compactPillBtn/Text migrated to premium.ctaGhost / premium.ctaGhostText
  compactMetaRow: { marginTop: 10, flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  fliPreviewActionsRow: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", marginTop: 8 },
  // migrated to premium.cardInset + local marginTop
  fliPreviewBox: { marginTop: 10 },
  coachVoiceHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 10,
  },
  // coachVoiceOrb/typography migrated to premium.aiOrb / premium.kicker/title/body/muted
  coachVoiceExpandedBox: { marginTop: 10 },

  trialEndingBanner: {
    marginTop: 12,
    padding: 14,
    backgroundColor: "rgba(34, 197, 94, 0.12)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(34, 197, 94, 0.35)",
  },
  trialEndingText: { fontSize: 13, color: "#86efac", lineHeight: 19 },
  trialEndingBtn: { marginTop: 10, paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10, backgroundColor: "#22c55e", alignItems: "center" },
  trialEndingBtnText: { fontSize: 14, fontWeight: "700", color: "#fff" },

  unlockProBtn: {
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: "#2563eb",
    borderWidth: 1,
    borderColor: "#3b82f6",
    alignItems: "center",
  },
  unlockProBtnText: { fontSize: 15, fontWeight: "700", color: "#fff" },

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
    borderWidth: 1,
    borderColor: "#3a7dff",
    paddingVertical: 13,
    paddingHorizontal: 16,
    borderRadius: 14,
    alignItems: "center",
    flex: 1,
  },
  mapCtaBtn: {
    marginTop: 12,
    minHeight: 52,
    paddingVertical: 14,
    justifyContent: "center",
    width: "100%",
    flex: 0,
    alignSelf: "stretch",
  },
  healthyHero: {
    paddingTop: 24,
    paddingBottom: 20,
    paddingHorizontal: 24,
    backgroundColor: "#faf7f2",
    borderRadius: 22,
    marginTop: 12,
    marginBottom: 12,
  },
  healthyHeroTitle: {
    fontSize: 24,
    fontWeight: "800",
    color: "#111827",
  },
  healthyHeroSubtitle: {
    marginTop: 6,
    fontSize: 14,
    lineHeight: 20,
    color: "#4b5563",
  },
  healthyHeroTagline: {
    marginTop: 10,
    fontSize: 13,
    fontWeight: "600",
    color: "#111827",
  },
  secondaryBtn: {
    backgroundColor: "#121721",
    borderWidth: 1,
    borderColor: "#2a3445",
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
  btnText: { color: "#fff", fontWeight: "800", fontSize: 14, letterSpacing: 0.2 },
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
    backgroundColor: "#121721",
    borderWidth: 1,
    borderColor: "#2a3445",
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 12,
    alignItems: "center",
    flexShrink: 1,
  },
  consentOnBtn: {
    backgroundColor: "#15432c",
    borderWidth: 1,
    borderColor: "#1f8f4d",
  },
  consentOffBtn: {
    backgroundColor: "#2a1a1a",
    borderWidth: 1,
    borderColor: "#7f1d1d",
  },
  dangerBtn: {
    backgroundColor: "#3a1010",
    borderWidth: 1,
    borderColor: "#8a1d1d",
  },
  smallBtnText: { color: "#fff", fontWeight: "700", fontSize: 12, lineHeight: 16 },

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
  suppAuthorityCard: {
    borderColor: "#1f2937",
    backgroundColor: "#0a0d12",
  },
  suppHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  suppAuthorityBadge: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#334155",
    backgroundColor: "#0f172a",
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  suppAuthorityBadgeText: {
    color: "#cbd5e1",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  progressContainer: {
    width: "100%",
    height: 8,
    borderRadius: 999,
    backgroundColor: "#17202f",
    overflow: "hidden",
    marginTop: 12,
    borderWidth: 1,
    borderColor: "#1f2937",
  },
  progressFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: "#22c55e",
  },
  suppPreviewSingle: { width: "100%", height: 170, borderRadius: 12, marginTop: 8 },
  suppPreviewEmptySingle: {
    width: "100%",
    height: 170,
    borderRadius: 12,
    marginTop: 8,
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#222",
    justifyContent: "center",
    alignItems: "center",
  },
  suppNavRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 12,
  },
  suppResultPanel: {
    marginTop: 10,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    backgroundColor: "#08101e",
  },
  suppGaugeWrap: {
    marginTop: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  suppGaugeRing: {
    width: 168,
    height: 168,
    borderRadius: 999,
    borderWidth: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0b1320",
  },
  suppGaugeValue: {
    fontSize: 34,
    fontWeight: "900",
  },
  suppGaugeLabel: {
    marginTop: 2,
    color: "#c8d5e6",
    fontSize: 12,
    fontWeight: "700",
  },
  suppHeadline: {
    marginTop: 10,
    fontSize: 22,
    fontWeight: "900",
    textAlign: "center",
  },
  suppRegulatoryCard: {
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#2c3b51",
    borderRadius: 12,
    backgroundColor: "#0b1624",
    padding: 10,
  },
  suppBreakdownToggle: {
    marginTop: 12,
    borderWidth: 1,
    borderColor: "#274468",
    borderRadius: 12,
    backgroundColor: "#0b1a2c",
    paddingHorizontal: 10,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  suppBreakdownRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    marginBottom: 6,
  },
  suppBreakdownIcon: {
    width: 18,
    fontWeight: "900",
    textAlign: "center",
  },
  suppLegalText: {
    marginTop: 12,
    color: "#8b98aa",
    fontSize: 11,
    lineHeight: 16,
  },
  lunchDecisionBtn: {
    borderWidth: 1,
    borderColor: "#1f8f4d",
    backgroundColor: "#0f2f1c",
  },
  weeklyCoachBtn: {
    borderWidth: 1,
    borderColor: "#3b82f6",
    backgroundColor: "#0d1f36",
  },
  menuScanBtn: {
    borderWidth: 1,
    borderColor: "#f59e0b",
    backgroundColor: "#3a2a0e",
  },
  // ── Healthy Nearby dedicated screen header ──────────────────────────────
  nearbyScreenHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 4,
    paddingVertical: 10,
    marginBottom: 2,
  },
  nearbyBackBtn: {
    paddingVertical: 7,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: "#0c182c",
    borderWidth: 1,
    borderColor: "#294268",
    minWidth: 64,
    alignItems: "center",
  },
  nearbyBackBtnText: {
    color: "#93c5fd",
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  nearbyScreenTitle: {
    color: "#ffffff",
    fontSize: 20,
    fontWeight: "900",
    letterSpacing: 0.1,
  },
  nearbyScreenSubtitle: {
    color: "#7b93b4",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "500",
  },
  // ── Hero card ────────────────────────────────────────────────────────────
  healthyNearbyHeroCard: {
    borderColor: "#1e3a5f",
    backgroundColor: "#060e1c",
    padding: 16,
    gap: 14,
  },
  remainingMacrosBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: "#0f1a2e",
    borderWidth: 1,
    borderColor: "#1e3a5f",
  },
  remainingMacroPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  remainingMacroIcon: {
    fontSize: 14,
  },
  remainingMacroValue: {
    fontSize: 16,
    fontWeight: "700",
    color: "#f8fafc",
  },
  remainingMacroLabel: {
    fontSize: 12,
    fontWeight: "500",
    color: "#94a3b8",
  },
  nearbyTabsRowTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  nearbyPrimaryActions: {
    gap: 10,
  },
  nearbySecondaryActionsRow: {
    flexDirection: "row",
    gap: 10,
  },
  nearbyPrimaryCta: {
    borderWidth: 1,
    borderColor: "#23a259",
    backgroundColor: "#0f4126",
  },
  nearbyExtrasRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    alignItems: "center",
  },
  nearbyExtraBtn: {
    paddingVertical: 5,
    paddingHorizontal: 11,
    borderRadius: 10,
    backgroundColor: "#0c1a2e",
    borderWidth: 1,
    borderColor: "#274869",
  },
  nearbyExtraBtnText: {
    color: "#94b8d9",
    fontSize: 12,
    fontWeight: "600",
  },
  // ── Empty state / error block ─────────────────────────────────────────────
  nearbyErrorBlock: {
    marginTop: 6,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: "#1a0a0a",
    borderWidth: 1,
    borderColor: "#5b2121",
    gap: 8,
    alignItems: "flex-start",
  },
  nearbyErrorText: {
    color: "#fca5a5",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "500",
  },
  nearbyRetryBtn: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 10,
    backgroundColor: "#2a0f0f",
    borderWidth: 1,
    borderColor: "#8b2020",
    alignSelf: "flex-start",
  },
  nearbyRetryBtnText: {
    color: "#fca5a5",
    fontSize: 13,
    fontWeight: "700",
  },
  nearbySecondaryActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 10,
  },
  nearbyTabsRow: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  nearbyTabPill: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#365174",
    backgroundColor: "#0c1a2e",
    paddingHorizontal: 13,
    paddingVertical: 7,
  },
  nearbyTabPillActive: {
    borderColor: "#25d16b",
    backgroundColor: "#0d2c1a",
  },
  nearbyTabText: {
    color: "#cbd5e1",
    fontSize: 13,
    fontWeight: "700",
  },
  nearbyTabTextActive: {
    color: "#dcfce7",
  },
  healthyNearbySectionCard: {
    padding: 14,
    gap: 8,
  },
  nearbySectionHeader: {
    color: "#f8fafc",
    fontSize: 18,
    fontWeight: "800",
    lineHeight: 22,
  },
  nearbySectionSubtle: {
    color: "#9badc5",
    fontSize: 13,
    lineHeight: 18,
  },
  nearbyLowPriorityHint: {
    color: "#78879d",
  },
  lunchDecisionWrap: {
    marginTop: 12,
    gap: 12,
  },
  lunchSummaryLine: {
    color: "#86efac",
    fontSize: 13,
    fontWeight: "700",
  },
  dayCoachCard: {
    marginTop: 8,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1f8f4d",
    backgroundColor: "#0a1a13",
    padding: 12,
    gap: 6,
  },
  dayCoachProgressLine: {
    color: "#dcfce7",
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  dayCoachProgressSubtle: {
    color: "#a8b3c2",
    fontSize: 11,
    lineHeight: 16,
  },
  dayCoachSection: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#1b2d24",
    gap: 4,
  },
  dayCoachSectionTitle: {
    color: "#bbf7d0",
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  dayCoachScoreLabel: {
    color: "#86efac",
    fontSize: 11,
    fontWeight: "800",
    marginTop: 2,
  },
  weeklyCoachCard: {
    marginTop: 10,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#2563eb",
    backgroundColor: "#0a1629",
    padding: 11,
    gap: 5,
  },
  weeklyCoachCardCompact: {
    marginTop: 8,
    borderColor: "#27364a",
    backgroundColor: "#090f1b",
    padding: 10,
  },
  weeklyCoachSectionCard: {
    borderColor: "#1b2738",
    backgroundColor: "#060b13",
    paddingTop: 14,
  },
  weeklyCoachSectionTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  weeklyCoachHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  weeklyCoachMeta: {
    color: "#7f98b8",
    fontSize: 10,
    fontWeight: "700",
  },
  weeklyCoachHeadline: {
    color: "#d4deed",
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
  },
  weeklyCoachSupport: {
    color: "#9aaec7",
    fontSize: 11,
    lineHeight: 16,
  },
  weeklyCoachSummaryLine: {
    color: "#b8cbe4",
    fontSize: 11,
    fontWeight: "700",
    marginTop: 2,
  },
  weeklyCoachPrimaryInsight: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: "#1f2e44",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 7,
    gap: 3,
  },
  weeklyCoachInsightsWrap: {
    marginTop: 6,
    gap: 6,
  },
  weeklyCoachInsightRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
  },
  weeklyCoachInsightBullet: {
    color: "#93c5fd",
    width: 14,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 16,
  },
  weeklyCoachInsightTitle: {
    color: "#e2e8f0",
    fontSize: 12,
    fontWeight: "700",
  },
  weeklyCoachToggleBtn: {
    alignSelf: "flex-start",
    marginTop: 6,
    borderWidth: 1,
    borderColor: "#2b3a52",
    backgroundColor: "#0f1522",
  },
  menuScanCard: {
    marginTop: 10,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#a16207",
    backgroundColor: "#22180a",
    padding: 12,
    gap: 5,
  },
  lunchDecisionCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#22543d",
    backgroundColor: "#081711",
    padding: 12,
  },
  lunchDecisionCardTop: {
    borderColor: "#34d399",
    backgroundColor: "#052617",
  },
  lunchDecisionLabel: {
    color: "#d1fae5",
    fontSize: 11,
    fontWeight: "800",
    marginBottom: 6,
    letterSpacing: 0.4,
  },
  lunchFitGood: {
    color: "#86efac",
    marginTop: 4,
    fontWeight: "700",
  },
  lunchFitCaution: {
    color: "#fca5a5",
    marginTop: 4,
    fontWeight: "700",
  },
  swapHintText: {
    color: "#bfdbfe",
    fontSize: 11,
    lineHeight: 16,
    marginTop: 4,
  },
  realitySavedText: {
    color: "#fde68a",
    marginTop: 5,
    fontWeight: "800",
    fontSize: 12,
  },
  lunchBadgeRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
    marginTop: 7,
    alignItems: "flex-start",
    maxWidth: "100%",
  },
  lunchBadge: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#1f8f4d",
    backgroundColor: "#0b2a19",
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  lunchBadgeText: {
    color: "#d1fae5",
    fontSize: 10,
    fontWeight: "700",
  },
  lunchCardCtaBtn: {
    alignSelf: "flex-start",
    flexShrink: 1,
    maxWidth: "100%",
  },
  lunchCardActionsRow: {
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 10,
    maxWidth: "100%",
  },
  lunchShareBtn: {
    borderWidth: 1,
    borderColor: "#1f8f4d",
    backgroundColor: "#0a2316",
  },
  nearbyFeedbackWrap: {
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#143023",
  },
  nearbyFeedbackToggle: {
    alignSelf: "flex-start",
    paddingVertical: 4,
    paddingHorizontal: 6,
  },
  nearbyFeedbackToggleText: {
    fontSize: 12,
    fontWeight: "700",
    color: "#93c5fd",
  },
  nearbyFeedbackBody: {
    marginTop: 8,
  },
  nearbyFeedbackQ: {
    fontSize: 12,
    color: "#cfd7e3",
    marginTop: 8,
    marginBottom: 6,
    fontWeight: "700",
  },
  nearbyFeedbackRow: {
    flexDirection: "row",
    flexWrap: "wrap",
  },
  nearbyFeedbackChip: {
    borderWidth: 1,
    borderColor: "#294268",
    backgroundColor: "#0c182c",
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    marginRight: 8,
    marginBottom: 8,
  },
  nearbyFeedbackChipActive: {
    borderColor: "#22c55e",
    backgroundColor: "#0d2c1a",
  },
  nearbyFeedbackChipText: {
    fontSize: 12,
    color: "#e5e7eb",
    fontWeight: "700",
  },
  healthyViewToggleRow: {
    marginTop: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 10,
  },
  healthyViewToggleActive: {
    borderColor: "#22c55e",
    backgroundColor: "#0d2c1a",
  },
  healthyFilterRow: {
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 9,
  },
  healthyFilterChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#334155",
    backgroundColor: "#0f172a",
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  healthyFilterChipActive: {
    borderColor: "#22c55e",
    backgroundColor: "#0d2c1a",
  },
  healthyFilterChipText: {
    color: "#dbeafe",
    fontSize: 11,
    fontWeight: "700",
  },
  placeCard: {
    marginTop: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1f2937",
    backgroundColor: "#0b1118",
    padding: 12,
  },
  placeHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 8,
    width: "100%",
    flexWrap: "nowrap",
  },
  placeNameText: {
    flex: 1,
    minWidth: 0,
    paddingRight: 8,
  },
  placeScore: {
    fontSize: 12,
    fontWeight: "800",
    flexShrink: 0,
    textAlign: "right",
    minWidth: 64,
    maxWidth: 110,
  },
  placeMapCard: {
    marginTop: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1f2937",
    backgroundColor: "#0b1118",
    padding: 12,
  },
  placeMapCanvas: {
    marginTop: 10,
    width: "100%",
    height: 210,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#334155",
    backgroundColor: "#07101a",
    position: "relative",
    overflow: "hidden",
  },
  placeMapCenter: {
    position: "absolute",
    left: "50%",
    top: "50%",
    width: 10,
    height: 10,
    marginLeft: -5,
    marginTop: -5,
    borderRadius: 999,
    backgroundColor: "#93c5fd",
    borderWidth: 1,
    borderColor: "#1e40af",
  },
  placeMapPin: {
    position: "absolute",
    width: 16,
    height: 16,
    borderRadius: 999,
    borderWidth: 2,
    backgroundColor: "#0b1118",
    alignItems: "center",
    justifyContent: "center",
  },
  placeMapPinSelected: {
    transform: [{ scale: 1.25 }],
    zIndex: 4,
    shadowColor: "#22c55e",
    shadowOpacity: 0.45,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 0 },
    elevation: 3,
  },
  placeMapPinCore: {
    width: 7,
    height: 7,
    borderRadius: 999,
  },
  healthySelectedCard: {
    marginTop: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#2a6448",
    backgroundColor: "#081a13",
    padding: 12,
  },
  healthyCoachSection: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#1b2d24",
    gap: 4,
  },
  healthyPanelSection: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#1b2d24",
    gap: 4,
  },
  healthyPanelSectionTitle: {
    color: "#b4e8c8",
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  healthyPanelItemName: {
    color: "#f8fafc",
    fontSize: 16,
    fontWeight: "800",
    lineHeight: 21,
  },
  mapCoachHeadline: {
    color: "#dcfce7",
    fontSize: 15,
    fontWeight: "800",
    lineHeight: 20,
  },
  mapCoachSupport: {
    color: "#cbd5e1",
    fontSize: 11,
    lineHeight: 16,
  },
  mapCoachSupportCompact: {
    color: "#b5c3d6",
    fontSize: 12,
    lineHeight: 17,
  },
  mapDecisionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 3,
    flexWrap: "wrap",
  },
  mapDecisionLabel: {
    flexShrink: 1,
    minWidth: 0,
  },
  mapDecisionBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
    fontSize: 10,
    fontWeight: "800",
    overflow: "hidden",
  },
  mapDecisionBadgeYes: {
    color: "#86efac",
    backgroundColor: "#0e3a21",
    borderWidth: 1,
    borderColor: "#1f8f4d",
  },
  mapDecisionBadgeMaybe: {
    color: "#fde68a",
    backgroundColor: "#3a300f",
    borderWidth: 1,
    borderColor: "#a16207",
  },
  mapDecisionBadgeNo: {
    color: "#fecaca",
    backgroundColor: "#3b1212",
    borderWidth: 1,
    borderColor: "#b91c1c",
  },
  mapCoachToneEncouraging: {
    color: "#86efac",
    backgroundColor: "#0f3a21",
    borderWidth: 1,
    borderColor: "#15803d",
  },
  mapCoachToneCaution: {
    color: "#fde68a",
    backgroundColor: "#3a300f",
    borderWidth: 1,
    borderColor: "#a16207",
  },
  mapCoachToneWarning: {
    color: "#fecaca",
    backgroundColor: "#3b1212",
    borderWidth: 1,
    borderColor: "#b91c1c",
  },
  suppProcessingOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.72)",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  suppProcessingCard: {
    width: "100%",
    borderRadius: 16,
    backgroundColor: "#0b1018",
    borderWidth: 1,
    borderColor: "#26364a",
    padding: 16,
  },
  suppProcessingTitle: {
    color: "#e2e8f0",
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 10,
  },
  suppProcessingLine: {
    color: "#cbd5e1",
    fontSize: 14,
    lineHeight: 22,
  },

  itemRow: { marginTop: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: "#161616" },
  itemName: { color: "#fff", fontWeight: "800", fontSize: 16, lineHeight: 21 },
  itemMeta: { color: "#9aa4b5", marginTop: 3, fontSize: 12, lineHeight: 17 },

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
    flexDirection: "column",
    rowGap: 8,
  },
  intelHeaderTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    columnGap: 8,
  },
  intelHeaderActionsScroll: {
    width: "100%",
  },
  intelHeaderActions: {
    flexDirection: "row",
    flexWrap: "nowrap",
    justifyContent: "flex-start",
    columnGap: 8,
    rowGap: 8,
    paddingRight: 4,
    paddingBottom: 2,
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
  coachSourceBadge: {
    alignSelf: "flex-start",
    marginTop: 8,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  coachSourceBadgeLive: {
    backgroundColor: "#0f2b1a",
    borderColor: "#1f8f4d",
  },
  coachSourceBadgeBasic: {
    backgroundColor: "#1d1f24",
    borderColor: "#3f4553",
  },
  coachSourceBadgeText: { color: "#dbe7ff", fontSize: 11, fontWeight: "800" },
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
  // ===== AI Live Coach Chat (restored from 1.0.13 build 182) =====
  coachChatCard: { padding: 14 },
  coachChatHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  coachChatHeaderActions: { flexDirection: "row", alignItems: "center", gap: 8 },
  coachRecoveryBadge: { borderRadius: 999, borderWidth: 1, paddingHorizontal: 9, paddingVertical: 5 },
  coachRecoveryBadgeGreen: { borderColor: "rgba(34,197,94,0.5)", backgroundColor: "rgba(34,197,94,0.14)" },
  coachRecoveryBadgeAmber: { borderColor: "rgba(245,158,11,0.5)", backgroundColor: "rgba(245,158,11,0.14)" },
  coachRecoveryBadgeRed: { borderColor: "rgba(239,68,68,0.55)", backgroundColor: "rgba(239,68,68,0.14)" },
  coachRecoveryBadgeText: { color: "#e2e8f0", fontSize: 11, fontWeight: "700" },
  coachRecoveryPanel: {
    marginTop: 8, marginBottom: 4, borderRadius: 10, borderWidth: 1,
    borderColor: "rgba(148,163,184,0.24)", backgroundColor: "rgba(2,6,23,0.35)",
    paddingVertical: 8, paddingHorizontal: 10,
  },
  coachRecoveryPanelText: { color: "#cbd5e1", fontSize: 12, lineHeight: 18 },
  coachChatFeed: {
    marginTop: 10, maxHeight: 300, borderWidth: 1,
    borderColor: "rgba(148, 163, 184, 0.22)", borderRadius: 12,
    backgroundColor: "rgba(2, 6, 23, 0.35)",
  },
  coachChatFeedContent: { padding: 10, flexGrow: 1, justifyContent: "flex-end" },
  coachChatBubble: { paddingVertical: 8, paddingHorizontal: 10, borderRadius: 10, marginBottom: 8 },
  coachChatCoachBubble: {
    alignSelf: "flex-start", backgroundColor: "rgba(147, 197, 253, 0.12)",
    borderWidth: 1, borderColor: "rgba(147, 197, 253, 0.30)",
  },
  coachChatUserBubble: {
    alignSelf: "flex-end", backgroundColor: "rgba(34, 197, 94, 0.14)",
    borderWidth: 1, borderColor: "rgba(34, 197, 94, 0.30)",
  },
  coachChatBubbleText: { fontSize: 13, lineHeight: 18, fontWeight: "500" },
  coachChatCoachText: { color: "#dbeafe" },
  coachChatUserText: { color: "#dcfce7" },
  coachQuickRow: { marginTop: 8, flexDirection: "row", flexWrap: "wrap", gap: 8 },
  coachQuickChip: {
    borderRadius: 999, borderWidth: 1, borderColor: "rgba(148, 163, 184, 0.30)",
    backgroundColor: "rgba(15, 23, 42, 0.45)", paddingHorizontal: 10, paddingVertical: 6,
  },
  coachQuickChipText: { color: "#cbd5e1", fontSize: 12, fontWeight: "600" },
  coachChatComposerRow: { marginTop: 10, flexDirection: "row", alignItems: "flex-end", gap: 8 },
  coachChatInputField: {
    flex: 1, minHeight: 42, maxHeight: 110, borderWidth: 1,
    borderColor: "rgba(148, 163, 184, 0.24)", borderRadius: 10,
    color: "#f8fafc", paddingHorizontal: 12, paddingVertical: 9,
    backgroundColor: "rgba(15, 23, 42, 0.55)",
  },
  coachChatSendBtn: { paddingHorizontal: 16, minHeight: 42 },
});
