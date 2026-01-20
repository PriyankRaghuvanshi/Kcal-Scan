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
  const active = customerInfo?.entitlements?.active || {};
  for (const k of ENTITLEMENTS) {
    if (active[k]) return k;
  }
  return "free";
}

function formatPrice(pkg) {
  try {
    return pkg?.product?.priceString || "";
  } catch {
    return "";
  }
}

// UPDATED: force Elite/Advanced/Pro/Infinite labels (no "Monthly")
function pkgTitle(pkg) {
  const pid =
    (pkg?.product?.identifier ||
      pkg?.product?.productIdentifier ||
      pkg?.identifier ||
      "")
      .toLowerCase()
      .trim();

  // Prefer explicit identifiers first
  if (pid.includes("calorieclick_elite") || pid.includes("elite")) return "Elite";
  if (pid.includes("calorieclick_advanced") || pid.includes("advanced")) return "Advanced";
  if (pid.includes("calorieclick_pro") || pid.includes("pro")) return "Pro";
  if (pid.includes("calorieclick_infinite") || pid.includes("infinite")) return "Infinite";

  // Fallback to title
  const title = (pkg?.product?.title || "").toLowerCase();
  if (title.includes("elite")) return "Elite";
  if (title.includes("advanced")) return "Advanced";
  if (title.includes("pro")) return "Pro";
  if (title.includes("infinite")) return "Infinite";

  // LAST fallback: infer from price (works well for your fixed tiers)
  const priceStr = (pkg?.product?.priceString || "").replace(/[^\d.]/g, "");
  const p = Number(priceStr);
  if (p === 9.99) return "Elite";
  if (p === 19.99) return "Advanced";
  if (p === 39.99) return "Pro";
  if (p === 149.99) return "Infinite";

  return pkg?.product?.title || "Plan";
}

function planRankFromPkg(pkg) {
  const t = pkgTitle(pkg).toLowerCase();
  if (t === "elite") return 1;
  if (t === "advanced") return 2;
  if (t === "pro") return 3;
  if (t === "infinite") return 4;
  return 99;
}

function planSubtitleFromTitle(t) {
  const k = (t || "").toLowerCase();
  if (k === "elite") return "Starter plan • daily + monthly scans";
  if (k === "advanced") return "More daily limit • more monthly scans";
  if (k === "pro") return "Power plan • very high monthly scans";
  if (k === "infinite") return "Unlimited scans (fair use)";
  return "";
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

  const userId = session?.user?.id || null;

  // ===================== INIT =====================
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(HISTORY_KEY);
        const arr = raw ? JSON.parse(raw) : [];
        if (Array.isArray(arr)) setHistory(arr);
      } catch {}
    })();
  }, []);

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
      const json = await res.json();
      setUsage(json);
    } catch (e) {
      console.log("usage fetch error:", e?.message || e);
    }
  }

  // keep UI plan in sync with backend plan (fixes “plan didn’t change”)
  useEffect(() => {
    if (usage?.plan) setActivePlan(String(usage.plan).toLowerCase());
  }, [usage?.plan]);

  // pull usage on login + after purchase
  useEffect(() => {
    if (userId) fetchUsage();
  }, [userId]);

  // ===================== PLAN SYNC =====================
  async function syncPlanToBackend(entitlement) {
    if (!userId) return null;
    try {
      const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ entitlement }),
      });
      const json = await res.json();
      console.log("plan/sync:", json);

      // update UI plan from backend response immediately
      if (json?.plan) setActivePlan(String(json.plan).toLowerCase());

      await fetchUsage();
      return json?.plan || null;
    } catch (e) {
      console.log("plan/sync error:", e?.message || e);
      return null;
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

      // prefer backend plan if available, otherwise entitlement
      if (usage?.plan) setActivePlan(String(usage.plan).toLowerCase());
      else setActivePlan(getActiveEntitlement(info));
    } catch (e) {
      console.log("open paywall error:", e?.message || e);
    } finally {
      setRcLoading(false);
    }
  }

  async function buyPackage(pkg) {
    if (!pkg) return;
    setRcLoading(true);
    try {
      const { customerInfo } = await Purchases.purchasePackage(pkg);

      // refresh customer info (helps iOS propagate entitlements faster)
      const info2 = await Purchases.getCustomerInfo();
      setCustomerInfo(info2);

      // use the package label as the plan to sync (more reliable than “Monthly” titles)
      const planLabel = pkgTitle(pkg).toLowerCase();
      setActivePlan(planLabel);

      // 🔥 sync to backend
      await syncPlanToBackend(planLabel);

      Alert.alert("✅ Purchase successful", `Plan activated: ${planLabel}`);
      setPaywallOpen(false);
    } catch (e) {
      const msg = e?.message || String(e);
      if (msg.toLowerCase().includes("cancel")) return;
      Alert.alert("Purchase failed", msg);
    } finally {
      setRcLoading(false);
    }
  }

  async function restorePurchases() {
    setRcLoading(true);
    try {
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);

      // figure out restored plan from RevenueCat
      const restored = getActiveEntitlement(info);

      // IMPORTANT: avoid letting restore "refill scans" (spam)
      // We only sync to backend if backend plan differs (eg reinstall/new device).
      await fetchUsage();
      const backendPlan = String(usage?.plan || "free").toLowerCase();
      const restoredPlan = String(restored || "free").toLowerCase();

      if (backendPlan !== restoredPlan && restoredPlan !== "free") {
        await syncPlanToBackend(restoredPlan);
      }

      // keep UI plan correct
      if (usage?.plan) setActivePlan(String(usage.plan).toLowerCase());
      else setActivePlan(restoredPlan);

      Alert.alert("✅ Restored", `Active plan: ${restoredPlan}`);
      setPaywallOpen(false);
    } catch (e) {
      Alert.alert("Restore failed", e?.message || String(e));
    } finally {
      setRcLoading(false);
    }
  }

  // ===================== SUPABASE AUTH UI =====================
  async function signUp() {
    if (!supabase) return;
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("✅ Signup success", "Now login.");
    } catch (e) {
      Alert.alert("Signup failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function signIn() {
    if (!supabase) return;
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setSession(null);
    setUsage(null);
    setResult(null);
    setPhotoUri(null);
  }

  // ===================== CLEAR HELPERS =====================
  async function clearCurrent() {
    setResult(null);
    setPhotoUri(null);
  }

  async function clearHistoryAll() {
    try {
      setHistory([]);
      await AsyncStorage.removeItem(HISTORY_KEY);
      Alert.alert("✅ Cleared", "History cleared.");
    } catch (e) {
      Alert.alert("Clear failed", e?.message || String(e));
    }
  }

  // ===================== SCAN FUNCTIONS =====================
  async function takePhoto() {
    try {
      if (!cameraRef.current) return;
      setLoading(true);
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
      setPhotoUri(photo?.uri || null);
      setResult(null);
    } catch (e) {
      Alert.alert("Camera error", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function analyzePhoto() {
    if (!photoUri || !userId) return;
    setLoading(true);

    try {
      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "photo.jpg",
        type: "image/jpeg",
      });

      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: backendHeaders(userId), // DO NOT set content-type for multipart
        body: form,
      });

      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.detail ? JSON.stringify(json.detail) : JSON.stringify(json));
      }

      const normalized = normalizeAnalyzeResponse(json);
      setResult(normalized);

      const entry = {
        id: nowISO(),
        ts: nowISO(),
        mode: "photo",
        total_kcal: normalized.total_kcal,
        totals: normalized.totals,
        items: normalized.items,
      };

      const newHist = [entry, ...history].slice(0, MAX_HISTORY);
      setHistory(newHist);
      await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(newHist));

      await fetchUsage();
    } catch (e) {
      Alert.alert("Analyze failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function barcodeLookup(code) {
    if (!code || !userId) return;

    const now = Date.now();
    const last = lastBarcodeRef.current;
    if (last.code === code && now - last.t < BARCODE_COOLDOWN_MS) return;

    if (barcodeBusyRef.current) return;
    barcodeBusyRef.current = true;
    lastBarcodeRef.current = { code, t: now };

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(code)}`, {
        headers: backendHeaders(userId),
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.detail ? JSON.stringify(json.detail) : JSON.stringify(json));
      }

      const normalized = normalizeBarcodeResponse(json);
      setResult(normalized);

      const entry = {
        id: nowISO(),
        ts: nowISO(),
        mode: "barcode",
        barcode: normalized.barcode,
        total_kcal: normalized.total_kcal,
        totals: normalized.totals,
        items: normalized.items,
      };

      const newHist = [entry, ...history].slice(0, MAX_HISTORY);
      setHistory(newHist);
      await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(newHist));

      await fetchUsage();
    } catch (e) {
      Alert.alert("Barcode failed", e?.message || String(e));
    } finally {
      setLoading(false);
      barcodeBusyRef.current = false;
    }
  }

  // ===================== UI =====================
  if (authLoading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" />
        <Text style={{ marginTop: 10 }}>Loading…</Text>
      </SafeAreaView>
    );
  }

  if (!HAS_SUPABASE) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.h1}>Kcal Scan</Text>
        <Text style={styles.sub}>
          Supabase env missing. Please set EXPO_PUBLIC_SUPABASE_URL & EXPO_PUBLIC_SUPABASE_ANON_KEY.
        </Text>
      </SafeAreaView>
    );
  }

  // AUTH SCREEN
  if (!session?.user) {
    return (
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ flex: 1 }}
        >
          <View style={styles.card}>
            <Text style={styles.h1}>Kcal Scan</Text>
            <Text style={styles.sub}>Login or Signup</Text>

            <TextInput
              style={styles.input}
              placeholder="Email"
              autoCapitalize="none"
              value={email}
              onChangeText={setEmail}
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />

            <TouchableOpacity style={styles.btn} onPress={signIn}>
              <Text style={styles.btnText}>Login</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={signUp}>
              <Text style={styles.btnText}>Signup</Text>
            </TouchableOpacity>

            <Text style={styles.small}>
              Backend: {API_BASE} {"\n"}
              Status: {serverOk ? "✅ OK" : "❌ Down"}
            </Text>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // MAIN APP
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>Kcal Scan</Text>
          <Text style={styles.small}>
            Plan: <Text style={{ fontWeight: "800" }}>{activePlan}</Text>
            {"  •  "}
            Remaining:{" "}
            <Text style={{ fontWeight: "800" }}>
              {usage?.remaining_month ?? "-"}
            </Text>
          </Text>
        </View>

        <TouchableOpacity style={styles.smallBtn} onPress={openPaywall}>
          <Text style={styles.smallBtnText}>Upgrade</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.smallBtn, { marginLeft: 8 }]} onPress={signOut}>
          <Text style={styles.smallBtnText}>Logout</Text>
        </TouchableOpacity>
      </View>

      {/* MAIN SCROLL (fixes “can’t scroll to history”) */}
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingBottom: 26 }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Mode Switch */}
        <View style={styles.modeRow}>
          <TouchableOpacity
            style={[styles.modeBtn, mode === "photo" && styles.modeBtnActive]}
            onPress={() => setMode("photo")}
          >
            <Text style={[styles.modeText, mode === "photo" && styles.modeTextActive]}>
              Photo
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.modeBtn, mode === "barcode" && styles.modeBtnActive, { marginRight: 0 }]}
            onPress={() => setMode("barcode")}
          >
            <Text style={[styles.modeText, mode === "barcode" && styles.modeTextActive]}>
              Barcode
            </Text>
          </TouchableOpacity>
        </View>

        {/* Camera */}
        <View style={styles.cameraWrap}>
          {permission?.granted ? (
            <CameraView
              ref={cameraRef}
              style={styles.camera}
              facing="back"
              barcodeScannerSettings={
                mode === "barcode"
                  ? { barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"] }
                  : undefined
              }
              onBarcodeScanned={
                mode === "barcode"
                  ? (e) => barcodeLookup(e?.data)
                  : undefined
              }
            />
          ) : (
            <View style={styles.centerInline}>
              <Text style={{ color: "white" }}>Camera permission required</Text>
              <TouchableOpacity style={styles.btn} onPress={requestPermission}>
                <Text style={styles.btnText}>Grant permission</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Actions */}
        <View style={styles.actionsRow}>
          {mode === "photo" ? (
            <>
              <TouchableOpacity style={[styles.btnBig, styles.btnBigLeft]} onPress={takePhoto} disabled={loading}>
                <Text style={styles.btnText}>{loading ? "..." : "Take Photo"}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.btnBig, styles.btnBigRight, !photoUri && { opacity: 0.4 }]}
                onPress={analyzePhoto}
                disabled={!photoUri || loading}
              >
                <Text style={styles.btnText}>{loading ? "Analyzing…" : "Analyze"}</Text>
              </TouchableOpacity>
            </>
          ) : (
            <Text style={styles.sub}>Scan barcode inside camera</Text>
          )}
        </View>

        {/* Clear current */}
        {(photoUri || result) && (
          <View style={{ marginTop: 10 }}>
            <TouchableOpacity style={styles.btnSecondaryFull} onPress={clearCurrent}>
              <Text style={styles.btnText}>Clear (Next Scan)</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Photo Preview */}
        {!!photoUri && (
          <View style={styles.previewWrap}>
            <Image source={{ uri: photoUri }} style={styles.preview} />
          </View>
        )}

        {/* Result */}
        {result && (
          <View style={styles.resultCard}>
            <Text style={styles.h2}>
              Total: {round1(result.total_kcal)} kcal
            </Text>
            <Text style={styles.sub}>
              P {round1(result?.totals?.protein_g)}g  •  C {round1(result?.totals?.carbs_g)}g  •  F{" "}
              {round1(result?.totals?.fat_g)}g
            </Text>

            {/* NOTE: disable internal scrolling so the main ScrollView scrolls smoothly */}
            <FlatList
              data={result.items || []}
              keyExtractor={(_, idx) => String(idx)}
              scrollEnabled={false}
              renderItem={({ item }) => (
                <View style={styles.itemRow}>
                  <Text style={styles.itemName}>{item?.name}</Text>
                  <Text style={styles.itemKcal}>{round1(item?.kcal)} kcal</Text>
                </View>
              )}
            />
          </View>
        )}

        {/* History */}
        <View style={styles.historyWrap}>
          <View style={styles.historyHeaderRow}>
            <Text style={styles.h2}>History</Text>
            <TouchableOpacity style={styles.smallBtn} onPress={clearHistoryAll}>
              <Text style={styles.smallBtnText}>Clear History</Text>
            </TouchableOpacity>
          </View>

          <FlatList
            data={history}
            keyExtractor={(it) => it.id}
            scrollEnabled={false}
            renderItem={({ item }) => (
              <TouchableOpacity onPress={() => setSelected(item)}>
                <View style={styles.historyRow}>
                  <Text style={styles.historyText}>
                    {item.mode === "barcode" ? "📦" : "📷"} {round1(item.total_kcal)} kcal
                  </Text>
                  <Text style={styles.small}>{new Date(item.ts).toLocaleString()}</Text>
                </View>
              </TouchableOpacity>
            )}
          />
        </View>
      </ScrollView>

      {/* Paywall Modal */}
      <Modal visible={paywallOpen}i’m building a calorie scan app what’s better than market apps?请完成后告诉我 which is good
        animationType="slide"
        onRequestClose={() => setPaywallOpen(false)}
      >
        <SafeAreaView style={styles.modalWrap}>
          <View style={styles.modalHeader}>
            <Text style={styles.h1}>Upgrade</Text>
            <TouchableOpacity style={styles.smallBtn} onPress={() => setPaywallOpen(false)}>
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
          </View>

          {rcLoading && (
            <View style={styles.centerInline}>
              <ActivityIndicator size="large" />
              <Text style={{ marginTop: 10, color: "white" }}>Loading plans…</Text>
            </View>
          )}

          {!rcLoading && !offering && (
            <View style={styles.centerInline}>
              <Text style={styles.sub}>No offering found (RevenueCat)</Text>
              <Text style={styles.small}>Offering ID: {OFFERING_ID}</Text>
            </View>
          )}

          {!rcLoading && offering && (
            <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 18 }}>
              <Text style={styles.sub}>
                Current plan: <Text style={{ fontWeight: "900" }}>{activePlan}</Text>
              </Text>

              {((offering.availablePackages || []) || [])
                .slice()
                .sort((a, b) => planRankFromPkg(a) - planRankFromPkg(b))
                .map((pkg) => {
                  const title = pkgTitle(pkg);
                  return (
                    <TouchableOpacity
                      key={pkg.identifier}
                      style={styles.planCard}
                      onPress={() => buyPackage(pkg)}
                      disabled={rcLoading}
                    >
                      <Text style={styles.h2}>
                        {title} • {formatPrice(pkg)}
                      </Text>
                      <Text style={styles.small}>{planSubtitleFromTitle(title)}</Text>
                    </TouchableOpacity>
                  );
                })}

              <TouchableOpacity style={[styles.btn, { marginTop: 14 }]} onPress={restorePurchases}>
                <Text style={styles.btnText}>Restore Purchases</Text>
              </TouchableOpacity>

              <Text style={[styles.small, { marginTop: 12 }]}>
                Restore is for reinstall/new device. It should not refill scans.
              </Text>
            </ScrollView>
          )}
        </SafeAreaView>
      </Modal>

      {/* History detail modal */}
      <Modal visible={!!selected} transparent animationType="fade">
        <View style={styles.overlay}>
          <View style={styles.detailCard}>
            <Text style={styles.h2}>Scan Detail</Text>
            <Text style={styles.sub}>{round1(selected?.total_kcal)} kcal</Text>
            <Text style={styles.small}>{selected?.ts}</Text>

            <ScrollView style={{ maxHeight: 300, marginTop: 10 }}>
              {(selected?.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>{it?.name}</Text>
                  <Text style={styles.itemKcal}>{round1(it?.kcal)} kcal</Text>
                </View>
              ))}
            </ScrollView>

            <TouchableOpacity style={[styles.btn, { marginTop: 12 }]} onPress={() => setSelected(null)}>
              <Text style={styles.btnText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ===================== STYLES =====================
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  centerInline: { justifyContent: "center", alignItems: "center", padding: 18 },
  card: {
    marginTop: 80,
    backgroundColor: "#15151c",
    borderRadius: 18,
    padding: 18,
  },
  topBar: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  h1: { fontSize: 24, fontWeight: "900", color: "white" },
  h2: { fontSize: 18, fontWeight: "800", color: "white" },
  sub: { marginTop: 6, color: "#b8b8c7" },
  small: { marginTop: 12, color: "#8d8da3", fontSize: 12 },
  input: {
    marginTop: 12,
    backgroundColor: "#1c1c25",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "white",
  },
  btn: {
    marginTop: 12,
    backgroundColor: "#5b7cfa",
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: "center",
  },
  btnSecondary: { backgroundColor: "#303043" },
  btnText: { color: "white", fontWeight: "900" },
  smallBtn: {
    backgroundColor: "#1c1c25",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 12,
  },
  smallBtnText: { color: "white", fontWeight: "800" },

  modeRow: { flexDirection: "row", marginBottom: 10 },
  modeBtn: {
    flex: 1,
    backgroundColor: "#1c1c25",
    padding: 10,
    borderRadius: 14,
    alignItems: "center",
    marginRight: 8,
  },
  modeBtnActive: { backgroundColor: "#5b7cfa" },
  modeText: { color: "#b8b8c7", fontWeight: "900" },
  modeTextActive: { color: "white" },

  cameraWrap: { height: 280, borderRadius: 18, overflow: "hidden" },
  camera: { flex: 1 },

  actionsRow: { marginTop: 12, flexDirection: "row", gap: 12, alignItems: "center" },

  // bigger buttons for Take Photo / Analyze
  btnBig: {
    flex: 1,
    backgroundColor: "#5b7cfa",
    borderRadius: 16,
    paddingVertical: 16,
    alignItems: "center",
  },
  btnBigLeft: { marginRight: 6 },
  btnBigRight: { marginLeft: 6 },

  btnSecondaryFull: {
    backgroundColor: "#303043",
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: "center",
  },

  previewWrap: { marginTop: 10, alignItems: "center" },
  preview: { width: 180, height: 180, borderRadius: 18 },

  // remove flex:1 so it doesn't “trap” the screen above history
  resultCard: {
    marginTop: 12,
    backgroundColor: "#15151c",
    borderRadius: 18,
    padding: 14,
  },

  itemRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  itemName: { color: "white", fontWeight: "700", flex: 1, paddingRight: 10 },
  itemKcal: { color: "#b8b8c7", fontWeight: "800" },

  historyWrap: { marginTop: 12 },
  historyHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  historyRow: {
    backgroundColor: "#15151c",
    marginTop: 8,
    borderRadius: 14,
    padding: 12,
  },
  historyText: { color: "white", fontWeight: "800" },

  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.65)",
    justifyContent: "center",
    alignItems: "center",
    padding: 18,
  },
  detailCard: {
    width: "100%",
    backgroundColor: "#15151c",
    borderRadius: 18,
    padding: 16,
  },

  modalWrap: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },

  planCard: {
    backgroundColor: "#15151c",
    borderRadius: 18,
    padding: 16,
    marginTop: 12,
  },
});

