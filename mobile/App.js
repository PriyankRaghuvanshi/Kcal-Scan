// mobile/App.js
import React, { useEffect, useRef, useState } from "react";
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
} from "react-native";

import { CameraView, useCameraPermissions } from "expo-camera";
import * as FileSystem from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

// RevenueCat
import Purchases from "react-native-purchases";

// ===================== CONFIG =====================
const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

const HISTORY_KEY = "kcal_scan_history_v3";
const historyKey = (uid) => `${HISTORY_KEY}:${uid}`;
const MAX_HISTORY = 50;

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// RevenueCat keys (env preferred)
const RC_IOS_KEY =
  process.env.EXPO_PUBLIC_RC_IOS_KEY || "appl_SoteCFCeVzvTTQWIpwbClzFnBdq";
const RC_ANDROID_KEY =
  process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "goog_XXXXXXXXXXXXXXXX";

// Offering + entitlements
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const PLAN_ORDER = ["free","elite","advanced","pro","infinite"];

const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

const BARCODE_COOLDOWN_MS = 1800;

// ===================== HELPERS =====================
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function nowISO() {
  return new Date().toISOString();
}

function backendHeaders(userId, extra = {}) {
  if (!userId) return { ...extra };
  return {
    "X-User-Id": userId,
    "x-user-id": userId,
    ...extra,
  };
}

function pickMacros(obj) {
  if (!obj) return { protein_g: 0, carbs_g: 0, fat_g: 0 };
  const protein =
    obj.protein_g ?? obj.protein ?? obj.p ?? obj.proteinG ?? obj.protein_gm ?? 0;
  const carbs =
    obj.carbs_g ?? obj.carbs ?? obj.c ?? obj.carbsG ?? obj.carbs_gm ?? 0;
  const fat = obj.fat_g ?? obj.fat ?? obj.f ?? obj.fatG ?? obj.fat_gm ?? 0;
  return { protein_g: num(protein), carbs_g: num(carbs), fat_g: num(fat) };
}

function normalizeAnalyzeResponse(json) {
  const total_kcal = num(json?.total_kcal ?? json?.totalKcal ?? 0);

  const totalsCandidate = json?.totals ?? json?.macros ?? json?.total_macros ?? null;
  let totals = pickMacros(totalsCandidate);

  const rawItems = Array.isArray(json?.items)
    ? json.items
    : Array.isArray(json?.foods)
      ? json.foods
      : [];

  const items = rawItems.map((it) => {
    const kcal = num(it?.kcal ?? it?.calories ?? 0);
    const grams = num(it?.grams ?? it?.g ?? it?.weight_g ?? 0);
    const macros = pickMacros(it?.macros ?? it);
    return {
      ...it,
      name: it?.name ?? it?.label ?? it?.food ?? "item",
      kcal,
      grams,
      macros,
      confidence: it?.confidence ?? it?.conf ?? it?.score,
    };
  });

  if (
    totals.protein_g === 0 &&
    totals.carbs_g === 0 &&
    totals.fat_g === 0 &&
    items.length > 0
  ) {
    totals = items.reduce(
      (acc, it) => ({
        protein_g: acc.protein_g + num(it?.macros?.protein_g),
        carbs_g: acc.carbs_g + num(it?.macros?.carbs_g),
        fat_g: acc.fat_g + num(it?.macros?.fat_g),
      }),
      { protein_g: 0, carbs_g: 0, fat_g: 0 }
    );
  }

  const computedKcal =
    total_kcal && total_kcal > 0 ? total_kcal : items.reduce((s, it) => s + num(it.kcal), 0);

  return { ...json, total_kcal: computedKcal, totals, items };
}

function normalizeBarcodeResponse(json) {
  const per = json?.per_100g || {};
  const name = json?.name || "Unknown product";
  const brand = json?.brand || null;

  const item = {
    name: brand ? `${name} (${brand})` : name,
    grams: 100,
    confidence: 1,
    kcal: num(per.kcal),
    macros: {
      protein_g: num(per.protein_g),
      carbs_g: num(per.carbs_g),
      fat_g: num(per.fat_g),
    },
    barcode: json?.barcode,
    source_db: json?.source_db,
  };

  return {
    source: "barcode",
    barcode: json?.barcode,
    total_kcal: num(per.kcal),
    totals: {
      protein_g: num(per.protein_g),
      carbs_g: num(per.carbs_g),
      fat_g: num(per.fat_g),
    },
    items: [item],
  };
}

function getActiveEntitlement(customerInfo) {
  // returns the HIGHEST active entitlement by PLAN_ORDER
  const active = customerInfo?.entitlements?.active || {};
  const activeKeys = Object.keys(active || {}).map((k) => String(k).toLowerCase());
  let best = "free";
  for (const k of activeKeys) {
    const idx = PLAN_ORDER.indexOf(k);
    if (idx >= 0 && idx > PLAN_ORDER.indexOf(best)) best = k;
  }
  return best;
}

function formatPrice(pkg) {
  try {
    return pkg?.product?.priceString || "";
  } catch {
    return "";
  }
}

function pkgTitle(pkg) {
  const id = (pkg?.identifier || "").toLowerCase();
  // Prefer showing plan name (Elite/Advanced/Pro/Infinite) over billing period
  if (id.includes("infinite")) return "Infinite";
  if (id.includes("pro")) return "Pro";
  if (id.includes("advanced")) return "Advanced";
  if (id.includes("elite")) return "Elite";
  return pkg?.product?.title || "Plan";
}

function planRankFromPkg(pkg) {
  const t = pkgTitle(pkg).toLowerCase();
  if (t.includes("infinite")) return 4;
  if (t.includes("pro")) return 3;
  if (t.includes("advanced")) return 2;
  if (t.includes("elite")) return 1;
  return 0;
}

function isElitePlus(plan) {
  const p = (plan || "free").toLowerCase();
  return p === "elite" || p === "advanced" || p === "pro" || p === "infinite";
}

function isProPlus(plan) {
  const p = (plan || "free").toLowerCase();
  return p === "pro" || p === "infinite";
}

function planSubtitleFromTitle(title) {
  const t = (title || "").toLowerCase();
  if (t.includes("elite")) return "Barcode scans + more scans";
  if (t.includes("advanced")) return "More scans + barcode";
  if (t.includes("pro")) return "Coaching insights + Satiety/BV + Muscle score";
  if (t.includes("infinite")) return "Everything + massive scan limits";
  return "Upgrade to unlock features";
}

// ===================== APP =====================
export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Supabase Auth
  const [authLoading, setAuthLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // Mode
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"
  const lastBarcodeRef = useRef({ code: null, t: 0 });
  const barcodeBusyRef = useRef(false);

  // Usage
  const [usage, setUsage] = useState(null);

  // RevenueCat paywall
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [rcLoading, setRcLoading] = useState(false);
  const [offering, setOffering] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [activePlan, setActivePlan] = useState("free");
  const effectivePlan = (result?.usage?.plan || activePlan || "free").toLowerCase();

  const userId = session?.user?.id || null;

  // ===================== INIT =====================
  useEffect(() => {
    (async () => {
      try {
        if (!userId) {
          setHistory([]);
          return;
        }
        const raw = await AsyncStorage.getItem(historyKey(userId));
        const arr = raw ? JSON.parse(raw) : [];
        if (Array.isArray(arr)) setHistory(arr);
      } catch {}
    })();
  }, [userId]);

  useEffect(() => {
    if (!HAS_SUPABASE) {
      setAuthLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data?.session || null);
      setAuthLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setAuthLoading(false);
    });

    return () => {
      listener?.subscription?.unsubscribe?.();
    };
  }, []);

  // Health check
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        setServerOk(res.ok);
      } catch {
        setServerOk(false);
      }
    })();
  }, []);

  // Setup camera permission
  useEffect(() => {
    if (!permission?.granted) requestPermission();
  }, [permission]);

  // ===================== REVENUECAT SETUP =====================
  useEffect(() => {
    if (!userId) return;

    (async () => {
      try {
        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;

        Purchases.setLogLevel(Purchases.LOG_LEVEL.INFO);
        await Purchases.configure({ apiKey, appUserID: userId });

        const info = await Purchases.getCustomerInfo();
        setCustomerInfo(info);
        setActivePlan(getActiveEntitlement(info));

        // preload offerings
        const offerings = await Purchases.getOfferings();
        const off = offerings?.current || offerings?.all?.[OFFERING_ID];
        setOffering(off || null);
      } catch (e) {
        console.log("RevenueCat init error:", e?.message || e);
      }
    })();
  }, [userId]);

  // ===================== BACKEND USAGE =====================
  async function fetchUsage() {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/usage`, {
        headers: backendHeaders(userId),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t);
      }
      const rawText = await res.text();
      let json = null;
      try { json = JSON.parse(rawText); } catch (e) { json = null; }
      setUsage(json);
    } catch (e) {
      console.log("usage fetch error:", e?.message || e);
    }
  }

  // pull usage on login + after purchase
  useEffect(() => {
    if (userId) fetchUsage();
  }, [userId]);

  // ===================== PLAN SYNC =====================
  
function planRank(plan) {
  const order = ["free", "elite", "advanced", "pro", "infinite"];
  const p = String(plan || "free").toLowerCase();
  const i = order.indexOf(p);
  return i >= 0 ? i : 0;
}

function planFromPackage(pkg) {
  const candidates = [
    pkg?.identifier,
    pkg?.product?.identifier,
    pkg?.product?.title,
    pkg?.product?.description,
  ]
    .filter(Boolean)
    .map((s) => String(s).toLowerCase());

  const hay = candidates.join(" | ");
  if (hay.includes("infinite")) return "infinite";
  if (hay.includes("pro")) return "pro";
  if (hay.includes("advanced")) return "advanced";
  if (hay.includes("elite")) return "elite";
  return null;
}


async function syncPlanToBackend(entitlement, mode = "purchase") {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
      body: JSON.stringify({ entitlement, mode }),
      });
      const rawText = await res.text();
      let json = null;
      try { json = JSON.parse(rawText); } catch (e) { json = null; }
      console.log("plan/sync:", json);
      await fetchUsage();
    } catch (e) {
      console.log("plan/sync error:", e?.message || e);
    }
  }

  // ===================== PURCHASE / RESTORE =====================
  async function openPaywall() {
    setPaywallOpen(true);
    setRcLoading(true);
    try {
      const offerings = await Purchases.getOfferings();
      const off = offerings?.current || offerings?.all?.[OFFERING_ID];
      setOffering(off || null);

      const info = await Purchases.getCustomerInfo();
      setCustomerInfo(info);
      setActivePlan(getActiveEntitlement(info));
    } catch (e) {
      console.log("open paywall error:", e?.message || e);
    } finally {
      setRcLoading(false);
    }
  }

  async function buyPackage(pkg) {
  try {
    setPaywallBusy(true);

    // Determine the plan the user tapped (from package metadata)
    const target = planFromPackage(pkg);

    // Purchase
    await Purchases.purchasePackage(pkg);

    // Refresh RevenueCat state
    const info = await Purchases.getCustomerInfo();
    const activeEnt = getActiveEntitlement(info); // what Apple/RC says is currently active right now
    setActivePlan(activeEnt);

    // Decide what we should tell backend:
    // - If the purchase is an upgrade (target >= current), we expect activeEnt to become target (usually immediate)
    // - If the purchase is a downgrade (target < current), Apple keeps higher plan active until next billing cycle.
    //   In that case, we keep backend on activeEnt (so the user doesn't lose features early).
    const backendPlan = activeEnt;

    // Sync to backend as a PURCHASE (this refills counters only on real purchase)
    await syncPlanToBackend(backendPlan, "purchase");

    // Messaging
    if (target && planRank(target) < planRank(activeEnt)) {
      Alert.alert(
        "Downgrade scheduled",
        `Your Apple subscription is still ${activeEnt.toUpperCase()} until the next billing cycle. The downgrade to ${target.toUpperCase()} will apply later.`
      );
    } else if (target && planRank(target) > planRank(activeEnt)) {
      Alert.alert(
        "Purchase pending",
        `Apple hasn’t switched your plan yet. Current: ${activeEnt.toUpperCase()}. If it doesn’t update soon, use Restore Purchases.`
      );
    } else {
      Alert.alert("Plan updated", `You are now on ${activeEnt.toUpperCase()}.`);
    }

    await fetchUsage(); // refresh usage from backend after plan sync
  } catch (e) {
    console.log("buy error", e);
    Alert.alert("Purchase failed", String(e?.message || e));
  } finally {
    setPaywallBusy(false);
  }
}


async function restorePurchases() {
    setRcLoading(true);
    try {
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);

      const plan = getActiveEntitlement(info);
      setActivePlan(plan);

      // IMPORTANT: restore should NOT refill scan counters.
      await syncPlanToBackend(plan, "restore");
      await fetchUsage();

      Alert.alert(
        "Purchases restored",
        `Your Apple subscription is currently ${plan.toUpperCase()}.\n\nNote: Restore does not refill scan limits — it only syncs your plan.`
      );
    } catch (e) {
      console.log("restore error", e);
      Alert.alert("Restore failed", String(e?.message || e));
    } finally {
      setRcLoading(false);
    }
  }

async function barcodeLookupManual() {
  const code = String(barcodeManual || "").trim();
  if (!code) {
    Alert.alert("Enter barcode", "Type a barcode number first.");
    return;
  }
  await barcodeLookup(code);
}

  },
  manualRow: {
    marginTop: 10,
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
  },
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
  btn:App.js
import React, { useEffect, useRef, useState } from "react";
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
} from "react-native";

import { CameraView, useCameraPermissions } from "expo-camera";
import * as FileSystem from "expo-file-system";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import "react-native-url-polyfill/auto";

// RevenueCat
import Purchases from "react-native-purchases";

// ===================== CONFIG =====================
const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

const HISTORY_KEY = "kcal_scan_history_v3";
const historyKey = (uid) => `${HISTORY_KEY}:${uid}`;
const MAX_HISTORY = 50;

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// RevenueCat keys (env preferred)
const RC_IOS_KEY =
  process.env.EXPO_PUBLIC_RC_IOS_KEY || "appl_SoteCFCeVzvTTQWIpwbClzFnBdq";
const RC_ANDROID_KEY =
  process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "goog_XXXXXXXXXXXXXXXX";

// Offering + entitlements
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const PLAN_ORDER = ["free","elite","advanced","pro","infinite"];

const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

const BARCODE_COOLDOWN_MS = 1800;

// ===================== HELPERS =====================
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function nowISO() {
  return new Date().toISOString();
}

function backendHeaders(userId, extra = {}) {
  if (!userId) return { ...extra };
  return {
    "X-User-Id": userId,
    "x-user-id": userId,
    ...extra,
  };
}

function pickMacros(obj) {
  if (!obj) return { protein_g: 0, carbs_g: 0, fat_g: 0 };
  const protein =
    obj.protein_g ?? obj.protein ?? obj.p ?? obj.proteinG ?? obj.protein_gm ?? 0;
  const carbs =
    obj.carbs_g ?? obj.carbs ?? obj.c ?? obj.carbsG ?? obj.carbs_gm ?? 0;
  const fat = obj.fat_g ?? obj.fat ?? obj.f ?? obj.fatG ?? obj.fat_gm ?? 0;
  return { protein_g: num(protein), carbs_g: num(carbs), fat_g: num(fat) };
}

function normalizeAnalyzeResponse(json) {
  const total_kcal = num(json?.total_kcal ?? json?.totalKcal ?? 0);

  const totalsCandidate = json?.totals ?? json?.macros ?? json?.total_macros ?? null;
  let totals = pickMacros(totalsCandidate);

  const rawItems = Array.isArray(json?.items)
    ? json.items
    : Array.isArray(json?.foods)
      ? json.foods
      : [];

  const items = rawItems.map((it) => {
    const kcal = num(it?.kcal ?? it?.calories ?? 0);
    const grams = num(it?.grams ?? it?.g ?? it?.weight_g ?? 0);
    const macros = pickMacros(it?.macros ?? it);
    return {
      ...it,
      name: it?.name ?? it?.label ?? it?.food ?? "item",
      kcal,
      grams,
      macros,
      confidence: it?.confidence ?? it?.conf ?? it?.score,
    };
  });

  if (
    totals.protein_g === 0 &&
    totals.carbs_g === 0 &&
    totals.fat_g === 0 &&
    items.length > 0
  ) {
    totals = items.reduce(
      (acc, it) => ({
        protein_g: acc.protein_g + num(it?.macros?.protein_g),
        carbs_g: acc.carbs_g + num(it?.macros?.carbs_g),
        fat_g: acc.fat_g + num(it?.macros?.fat_g),
      }),
      { protein_g: 0, carbs_g: 0, fat_g: 0 }
    );
  }

  const computedKcal =
    total_kcal && total_kcal > 0 ? total_kcal : items.reduce((s, it) => s + num(it.kcal), 0);

  return { ...json, total_kcal: computedKcal, totals, items };
}

function normalizeBarcodeResponse(json) {
  const per = json?.per_100g || {};
  const name = json?.name || "Unknown product";
  const brand = json?.brand || null;

  const item = {
    name: brand ? `${name} (${brand})` : name,
    grams: 100,
    confidence: 1,
    kcal: num(per.kcal),
    macros: {
      protein_g: num(per.protein_g),
      carbs_g: num(per.carbs_g),
      fat_g: num(per.fat_g),
    },
    barcode: json?.barcode,
    source_db: json?.source_db,
  };

  return {
    source: "barcode",
    barcode: json?.barcode,
    total_kcal: num(per.kcal),
    totals: {
      protein_g: num(per.protein_g),
      carbs_g: num(per.carbs_g),
      fat_g: num(per.fat_g),
    },
    items: [item],
  };
}

function getActiveEntitlement(customerInfo) {
  // returns the HIGHEST active entitlement by PLAN_ORDER
  const active = customerInfo?.entitlements?.active || {};
  const activeKeys = Object.keys(active || {}).map((k) => String(k).toLowerCase());
  let best = "free";
  for (const k of activeKeys) {
    const idx = PLAN_ORDER.indexOf(k);
    if (idx >= 0 && idx > PLAN_ORDER.indexOf(best)) best = k;
  }
  return best;
}

function formatPrice(pkg) {
  try {
    return pkg?.product?.priceString || "";
  } catch {
    return "";
  }
}

function pkgTitle(pkg) {
  const id = (pkg?.identifier || "").toLowerCase();
  // Prefer showing plan name (Elite/Advanced/Pro/Infinite) over billing period
  if (id.includes("infinite")) return "Infinite";
  if (id.includes("pro")) return "Pro";
  if (id.includes("advanced")) return "Advanced";
  if (id.includes("elite")) return "Elite";
  return pkg?.product?.title || "Plan";
}

function planRankFromPkg(pkg) {
  const t = pkgTitle(pkg).toLowerCase();
  if (t.includes("infinite")) return 4;
  if (t.includes("pro")) return 3;
  if (t.includes("advanced")) return 2;
  if (t.includes("elite")) return 1;
  return 0;
}

function isElitePlus(plan) {
  const p = (plan || "free").toLowerCase();
  return p === "elite" || p === "advanced" || p === "pro" || p === "infinite";
}

function isProPlus(plan) {
  const p = (plan || "free").toLowerCase();
  return p === "pro" || p === "infinite";
}

function planSubtitleFromTitle(title) {
  const t = (title || "").toLowerCase();
  if (t.includes("elite")) return "Barcode scans + more scans";
  if (t.includes("advanced")) return "More scans + barcode";
  if (t.includes("pro")) return "Coaching insights + Satiety/BV + Muscle score";
  if (t.includes("infinite")) return "Everything + massive scan limits";
  return "Upgrade to unlock features";
}

// ===================== APP =====================
export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Supabase Auth
  const [authLoading, setAuthLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // Mode
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"
  const lastBarcodeRef = useRef({ code: null, t: 0 });
  const barcodeBusyRef = useRef(false);

  // Usage
  const [usage, setUsage] = useState(null);

  // RevenueCat paywall
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [rcLoading, setRcLoading] = useState(false);
  const [offering, setOffering] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [activePlan, setActivePlan] = useState("free");
  const effectivePlan = (result?.usage?.plan || activePlan || "free").toLowerCase();

  const userId = session?.user?.id || null;

  // ===================== INIT =====================
  useEffect(() => {
    (async () => {
      try {
        if (!userId) {
          setHistory([]);
          return;
        }
        const raw = await AsyncStorage.getItem(historyKey(userId));
        const arr = raw ? JSON.parse(raw) : [];
        if (Array.isArray(arr)) setHistory(arr);
      } catch {}
    })();
  }, [userId]);

  useEffect(() => {
    if (!HAS_SUPABASE) {
      setAuthLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data?.session || null);
      setAuthLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setAuthLoading(false);
    });

    return () => {
      listener?.subscription?.unsubscribe?.();
    };
  }, []);

  // Health check
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        setServerOk(res.ok);
      } catch {
        setServerOk(false);
      }
    })();
  }, []);

  // Setup camera permission
  useEffect(() => {
    if (!permission?.granted) requestPermission();
  }, [permission]);

  // ===================== REVENUECAT SETUP =====================
  useEffect(() => {
    if (!userId) return;

    (async () => {
      try {
        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;

        Purchases.setLogLevel(Purchases.LOG_LEVEL.INFO);
        await Purchases.configure({ apiKey, appUserID: userId });

        const info = await Purchases.getCustomerInfo();
        setCustomerInfo(info);
        setActivePlan(getActiveEntitlement(info));

        // preload offerings
        const offerings = await Purchases.getOfferings();
        const off = offerings?.current || offerings?.all?.[OFFERING_ID];
        setOffering(off || null);
      } catch (e) {
        console.log("RevenueCat init error:", e?.message || e);
      }
    })();
  }, [userId]);

  // ===================== BACKEND USAGE =====================
  async function fetchUsage() {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/usage`, {
        headers: backendHeaders(userId),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t);
      }
      const rawText = await res.text();
      let json = null;
      try { json = JSON.parse(rawText); } catch (e) { json = null; }
      setUsage(json);
    } catch (e) {
      console.log("usage fetch error:", e?.message || e);
    }
  }

  // pull usage on login + after purchase
  useEffect(() => {
    if (userId) fetchUsage();
  }, [userId]);

  // ===================== PLAN SYNC =====================
  
function planRank(plan) {
  const order = ["free", "elite", "advanced", "pro", "infinite"];
  const p = String(plan || "free").toLowerCase();
  const i = order.indexOf(p);
  return i >= 0 ? i : 0;
}

function planFromPackage(pkg) {
  const candidates = [
    pkg?.identifier,
    pkg?.product?.identifier,
    pkg?.product?.title,
    pkg?.product?.description,
  ]
    .filter(Boolean)
    .map((s) => String(s).toLowerCase());

  const hay = candidates.join(" | ");
  if (hay.includes("infinite")) return "infinite";
  if (hay.includes("pro")) return "pro";
  if (hay.includes("advanced")) return "advanced";
  if (hay.includes("elite")) return "elite";
  return null;
}


async function syncPlanToBackend(entitlement, mode = "purchase") {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
      body: JSON.stringify({ entitlement, mode }),
      });
      const rawText = await res.text();
      let json = null;
      try { json = JSON.parse(rawText); } catch (e) { json = null; }
      console.log("plan/sync:", json);
      await fetchUsage();
    } catch (e) {
      console.log("plan/sync error:", e?.message || e);
    }
  }

  // ===================== PURCHASE / RESTORE =====================
  async function openPaywall() {
    setPaywallOpen(true);
    setRcLoading(true);
    try {
      const offerings = await Purchases.getOfferings();
      const off = offerings?.current || offerings?.all?.[OFFERING_ID];
      setOffering(off || null);

      const info = await Purchases.getCustomerInfo();
      setCustomerInfo(info);
      setActivePlan(getActiveEntitlement(info));
    } catch (e) {
      console.log("open paywall error:", e?.message || e);
    } finally {
      setRcLoading(false);
    }
  }

  async function buyPackage(pkg) {
  try {
    setPaywallBusy(true);

    // Determine the plan the user tapped (from package metadata)
    const target = planFromPackage(pkg);

    // Purchase
    await Purchases.purchasePackage(pkg);

    // Refresh RevenueCat state
    const info = await Purchases.getCustomerInfo();
    const activeEnt = getActiveEntitlement(info); // what Apple/RC says is currently active right now
    setActivePlan(activeEnt);

    // Decide what we should tell backend:
    // - If the purchase is an upgrade (target >= current), we expect activeEnt to become target (usually immediate)
    // - If the purchase is a downgrade (target < current), Apple keeps higher plan active until next billing cycle.
    //   In that case, we keep backend on activeEnt (so the user doesn't lose features early).
    const backendPlan = activeEnt;

    // Sync to backend as a PURCHASE (this refills counters only on real purchase)
    await syncPlanToBackend(backendPlan, "purchase");

    // Messaging
    if (target && planRank(target) < planRank(activeEnt)) {
      Alert.alert(
        "Downgrade scheduled",
        `Your Apple subscription is still ${activeEnt.toUpperCase()} until the next billing cycle. The downgrade to ${target.toUpperCase()} will apply later.`
      );
    } else if (target && planRank(target) > planRank(activeEnt)) {
      Alert.alert(
        "Purchase pending",
        `Apple hasn’t switched your plan yet. Current: ${activeEnt.toUpperCase()}. If it doesn’t update soon, use Restore Purchases.`
      );
    } else {
      Alert.alert("Plan updated", `You are now on ${activeEnt.toUpperCase()}.`);
    }

    await fetchUsage(); // refresh usage from backend after plan sync
  } catch (e) {
    console.log("buy error", e);
    Alert.alert("Purchase failed", String(e?.message || e));
  } finally {
    setPaywallBusy(false);
  }
}


async function restorePurchases() {
    setRcLoading(true);
    try {
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);

      const plan = getActiveEntitlement(info);
      setActivePlan(plan);

      // IMPORTANT: restore should NOT refill scan counters.
      await syncPlanToBackend(plan, "restore");
      await fetchUsage();

      Alert.alert(
        "Purchases restored",
        `Your Apple subscription is currently ${plan.toUpperCase()}.\n\nNote: Restore does not refill scan limits — it only syncs your plan.`
      );
    } catch (e) {
      console.log("restore error", e);
      Alert.alert("Restore failed", String(e?.message || e));
    } finally {
      setRcLoading(false);
    }
  }

async function barcodeLookupManual() {
  const code = String(barcodeManual || "").trim();
  if (!code) {
    Alert.alert("Enter barcode", "Type a barcode number first.");
    return;
  }
  await barcodeLookup(code);
}


