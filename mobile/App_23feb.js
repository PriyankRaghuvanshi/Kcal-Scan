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
} from "react-native";

import { CameraView, useCameraPermissions } from "expo-camera";
import * as FileSystem from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

// OAuth helpers (Google)
import * as AuthSession from "expo-auth-session";


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
const OAUTH_REDIRECT_TO = process.env.EXPO_PUBLIC_OAUTH_REDIRECT_TO || "";

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
  const out = {
    goal_type: ["fat_loss", "recomposition", "lean_gain"].includes(goalType) ? goalType : DEFAULT_COACH_PROFILE.goal_type,
    diet_style: ["veg", "non-veg", "vegan"].includes(dietStyle) ? dietStyle : DEFAULT_COACH_PROFILE.diet_style,
    training_days_per_week: Math.max(0, Math.min(7, Math.round(num(src.training_days_per_week ?? DEFAULT_COACH_PROFILE.training_days_per_week)))),
    training_time: ["morning", "afternoon", "evening", "night", "variable"].includes(trainingTime)
      ? trainingTime
      : DEFAULT_COACH_PROFILE.training_time,
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
  const redirectUri = AuthSession.makeRedirectUri({ scheme: "calorieclickai", path: "auth-callback" });
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

  // ===== History (isolated by user id) =====
  const [history, setHistory] = useState([]);
  const [coachDaily, setCoachDaily] = useState(null);
  const [coachBusy, setCoachBusy] = useState(false);
  const [coachErr, setCoachErr] = useState("");
  const [coachProfile, setCoachProfile] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileDraft, setCoachProfileDraft] = useState(DEFAULT_COACH_PROFILE);
  const [coachProfileReady, setCoachProfileReady] = useState(false);
  const [coachProfileModal, setCoachProfileModal] = useState(false);
  const coachReqRef = useRef(false);

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
    setCoachErr("");
    setCoachProfile(DEFAULT_COACH_PROFILE);
    setCoachProfileDraft(DEFAULT_COACH_PROFILE);
    setCoachProfileReady(false);
    setCoachProfileModal(false);
    setBarcodeManual("");
    setBarcodeOpen(false);
    setCamOpen(false);
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
  }, [userId]);

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

  async function pushHistory(entry) {
    try {
      const key = historyKey(userId);
      const raw = await AsyncStorage.getItem(key);
      const existing = raw ? JSON.parse(raw) : [];
      const arr = Array.isArray(existing) ? existing : [];
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
      },
    };
  }

  async function ensureDailyCoach(force = false) {
    const uid = userId || session?.user?.id;
    if (!uid || !coachProfileReady) return;

    const payload = buildDailyCoachPayload();
    if (!payload || num(payload?.consumed?.kcal) <= 0) {
      const dayKey = localDayISO();
      try {
        const raw = await AsyncStorage.getItem(dailyCoachKey(uid, dayKey));
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedResp = parsed?.response || parsed;
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(cachedResp);
            setCoachErr("");
            return;
          }
        }
      } catch {}
      setCoachDaily(null);
      setCoachErr("");
      return;
    }
    const day = payload.date || localDayISO();
    const cacheKey = dailyCoachKey(uid, day);
    const payloadHash = hashString(JSON.stringify(payload));

    if (!force) {
      try {
        const raw = await AsyncStorage.getItem(cacheKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedResp = parsed?.response || parsed;
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(cachedResp);
            setCoachErr("");
            return;
          }
        }
      } catch {}
    }

    if (coachReqRef.current) return;
    coachReqRef.current = true;
    setCoachBusy(true);
    if (force) setCoachErr("");
    try {
      const url = withTimezoneQuery(`${API_BASE}/coach/daily?user_id=${encodeURIComponent(uid)}`);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await safeJson(res);
      const cleaned = {
        date: String(data?.date || day),
        fat_loss_score: Math.round(num(data?.fat_loss_score)),
        diagnosis: Array.isArray(data?.diagnosis) ? data.diagnosis : [],
        tomorrow_focus: Array.isArray(data?.tomorrow_focus) ? data.tomorrow_focus : [],
        actions: Array.isArray(data?.actions) ? data.actions.slice(0, 3) : [],
        risk_alerts: Array.isArray(data?.risk_alerts) ? data.risk_alerts : [],
        disclaimer: String(data?.disclaimer || "Informational only."),
      };
      setCoachDaily(cleaned);
      setCoachErr("");
      await AsyncStorage.setItem(cacheKey, JSON.stringify({ payloadHash, ts: nowISO(), response: cleaned }));
    } catch (e) {
      setCoachErr(String(e).slice(0, 200));
      try {
        const raw = await AsyncStorage.getItem(cacheKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          const cachedResp = parsed?.response || parsed;
          if (cachedResp && typeof cachedResp === "object") {
            setCoachDaily(cachedResp);
          }
        }
      } catch {}
    } finally {
      coachReqRef.current = false;
      setCoachBusy(false);
    }
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
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (!userId || !coachProfileReady) return;
    ensureDailyCoach(false);
  }, [userId, coachProfileReady, goals, dailySummary, history, coachProfile]);

  async function applyCoachProfile() {
    const uid = userId || session?.user?.id;
    const normalized = normalizeCoachProfile(coachProfileDraft);
    await saveCoachProfile(uid, normalized);
    setCoachProfileModal(false);
    await ensureDailyCoach(true);
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
    setCoachErr("");
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
  }

  // ===== NEW: Google OAuth =====
  async function signInWithGoogle() {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase env", "Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }

    setAuthBusy(true);
    try {
      if (typeof supabase?.auth?.signInWithOAuth !== "function") {
        throw new Error("Google OAuth is unavailable in this app build.");
      }
      if (typeof WebBrowser.openAuthSessionAsync !== "function") {
        throw new Error("Auth browser helper is unavailable.");
      }

      const redirectTo = OAUTH_REDIRECT_TO?.trim() || redirectUri;
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: "google",
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
      const codeParam = extractQueryParam(callbackUrl, "code");
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

      throw new Error("Google callback did not include a valid auth session.");
    } catch (e) {
      console.log("Google login error:", e);
      Alert.alert("Google login failed", String(e?.message || e));
    } finally {
      setAuthBusy(false);
    }
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
      const normalized = {
        ...data,
        micros: normalizeMicros(data?.micros || data?.totals?.micros),
      };
      setResult(normalized);
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

      await pushHistory({
        ts: nowISO(),
        kind: "photo",
        photo_uri: photoUri,
        total_kcal: data?.total_kcal,
        totals: data?.totals,
        micros: data?.micros || data?.totals?.micros,
        items: data?.items,
        coaching: data?.coaching || null,
        locked: data?.locked || null,
      });
    } catch (e) {
      Alert.alert("Analyze failed", String(e).slice(0, 220));
    } finally {
      setBusy(false);
    }
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
          <View style={styles.topRow}>
            <Text style={styles.cardTitle}>Fat Loss Intelligence</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <TouchableOpacity
                style={styles.smallBtn}
                onPress={() => {
                  setCoachProfileDraft(coachProfile || DEFAULT_COACH_PROFILE);
                  setCoachProfileModal(true);
                }}
              >
                <Text style={styles.smallBtnText}>Profile</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.smallBtn} onPress={() => ensureDailyCoach(true)} disabled={coachBusy}>
                <Text style={styles.smallBtnText}>{coachBusy ? "…" : "Refresh"}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <Text style={styles.tiny}>
            {coachProfile?.goal_type || "fat_loss"} • {coachProfile?.diet_style || "non-veg"} •{" "}
            {Math.round(num(coachProfile?.training_days_per_week))} training day(s)/week • {coachProfile?.training_time || "evening"}
          </Text>

          {coachErr ? <Text style={[styles.tiny, { color: "#ffb4b4", marginTop: 8 }]}>{coachErr}</Text> : null}

          {coachBusy && !coachDaily ? (
            <View style={{ marginTop: 10 }}>
              <ActivityIndicator />
            </View>
          ) : coachDaily ? (
            <View style={{ marginTop: 10 }}>
              <Text style={styles.big}>Score: {Math.round(num(coachDaily?.fat_loss_score))}/100</Text>

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
                    <View key={`risk-${i}`} style={styles.riskRow}>
                      <Text style={styles.riskType}>
                        {String(ra?.type || "risk")} ({String(ra?.level || "medium")})
                      </Text>
                      <Text style={styles.tiny}>{String(ra?.reason || "")}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {(coachDaily?.actions || []).length ? (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.cardTitle}>Actions</Text>
                  {(coachDaily.actions || []).slice(0, 3).map((a, i) => (
                    <View key={`action-${i}`} style={styles.actionBox}>
                      <Text style={styles.itemName}>{String(a?.title || "Action")}</Text>
                      <Text style={styles.tiny}>{String(a?.why || "")}</Text>
                      <Text style={styles.p}>{String(a?.how || "")}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              <Text style={[styles.tiny, { marginTop: 8 }]}>{String(coachDaily?.disclaimer || "Informational only.")}</Text>
            </View>
          ) : (
            <Text style={[styles.tiny, { marginTop: 10 }]}>
              Analyze at least one meal today to generate daily intelligence.
            </Text>
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
            <TouchableOpacity style={styles.primaryBtn} onPress={analyzePhoto} disabled={busy || !photoUri}>
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
