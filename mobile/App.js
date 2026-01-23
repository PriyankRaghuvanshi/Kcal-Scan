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
const ENTITLEMENTS = (
  process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite"
)
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

const BARCODE_COOLDOWN_MS = 1800;

const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
function planRank(plan) {
  const p = String(plan || "free").toLowerCase();
  const idx = PLAN_ORDER.indexOf(p);
  return idx >= 0 ? idx : 0;
}
function isElitePlus(plan) {
  return planRank(plan) >= planRank("elite");
}
function isProPlus(plan) {
  return planRank(plan) >= planRank("pro");
}

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
  const carbs = obj.carbs_g ?? obj.carbs ?? obj.c ?? obj.carbsG ?? obj.carbs_gm ?? 0;
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

function pkgTitle(pkg) {
  const id = String(pkg?.identifier || pkg?.product?.identifier || pkg?.product?.productIdentifier || "").toLowerCase();
  for (const ent of ENTITLEMENTS) {
    if (id.includes(ent.toLowerCase())) return ent;
  }
  if (id.includes("monthly")) return "Monthly";
  if (id.includes("year")) return "Yearly";
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

  const [authLoading, setAuthLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  const [mode, setMode] = useState("photo");
  const lastBarcodeRef = useRef({ code: null, t: 0 });
  const barcodeBusyRef = useRef(false);

  const [usage, setUsage] = useState(null);

  const [paywallOpen, setPaywallOpen] = useState(false);
  const [rcLoading, setRcLoading] = useState(false);
  const [offering, setOffering] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [activePlan, setActivePlan] = useState("free");

  const userId = session?.user?.id || null;

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

  useEffect(() => {
    if (!permission?.granted) requestPermission();
  }, [permission]);

  useEffect(() => {
    if (!userId) return;
    (async () => {
      try {
        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
        Purchases.setLogLevel(Purchases.LOG_LEVEL.INFO);
        await Purchases.configure({ apiKey, appUserID: userId });
        if (Purchases.invalidateCustomerInfoCache) { await Purchases.invalidateCustomerInfoCache(); }
        const info = await Purchases.getCustomerInfo();
        setCustomerInfo(info);
        setActivePlan(getActiveEntitlement(info));
        const offerings = await Purchases.getOfferings();
        const off = offerings?.current || offerings?.all?.[OFFERING_ID];
        setOffering(off || null);
      } catch (e) {
        console.log("RevenueCat init error:", e?.message || e);
      }
    })();
  }, [userId]);

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

  useEffect(() => {
    if (usage?.plan) setActivePlan(String(usage.plan).toLowerCase());
  }, [usage?.plan]);

  useEffect(() => {
    if (userId) fetchUsage();
  }, [userId]);

  async function syncPlanToBackend(entitlement) {
    if (!userId) return null;
    try {
      const res = await fetch(
        `${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`,
        {
          method: "POST",
          headers: backendHeaders(userId, { "Content-Type": "application/json" }),
          body: JSON.stringify({ entitlement }),
        }
      );
      const json = await res.json();
      if (json?.plan) setActivePlan(String(json.plan).toLowerCase());
      await fetchUsage();
      return json?.plan || null;
    } catch (e) {
      console.log("plan/sync error:", e?.message || e);
      return null;
    }
  }

  async function buyPackage(pkg) {
    if (!pkg) return;
    setRcLoading(true);
    try {
      await Purchases.purchasePackage(pkg);
      const info2 = await Purchases.getCustomerInfo();
      setCustomerInfo(info2);
      const planLabel = pkgTitle(pkg).toLowerCase();
      setActivePlan(planLabel);
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
      if (Purchases.invalidateCustomerInfoCache) { await Purchases.invalidateCustomerInfoCache(); }
      const restored = getActiveEntitlement(info);
      await fetchUsage();
      const backendPlan = String(usage?.plan || "free").toLowerCase();
      const restoredPlan = String(restored || "free").toLowerCase();
      if (backendPlan !== restoredPlan && restoredPlan !== "free") {
        await syncPlanToBackend(restoredPlan);
      }
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

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setSession(null);
    setUsage(null);
    setResult(null);
    setPhotoUri(null);
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
        headers: backendHeaders(userId),
        body: form,
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json?.detail ? JSON.stringify(json.detail) : JSON.stringify(json));
      }
      const normalized = normalizeAnalyzeResponse(json);
      setResult(normalized);
      const entry = { id: nowISO(), ts: nowISO(), mode: "photo", total_kcal: normalized.total_kcal, totals: normalized.totals, items: normalized.items };
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
    if (lastBarcodeRef.current.code === code && now - lastBarcodeRef.current.t < BARCODE_COOLDOWN_MS) return;
    if (barcodeBusyRef.current) return;
    barcodeBusyRef.current = true;
    lastBarcodeRef.current = { code, t: now };
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(code)}`, { headers: backendHeaders(userId) });
      const json = await res.json();
      if (!res.ok) {
        if (res.status === 403 && json?.detail?.code === "upgrade_required") {
          Alert.alert("Upgrade required", json.detail.message);
          setPaywallOpen(true);
          return;
        }
        throw new Error(JSON.stringify(json || {}));
      }
      const normalized = normalizeBarcodeResponse(json);
      setResult(normalized);
      const entry = { id: nowISO(), ts: nowISO(), mode: "barcode", barcode: normalized.barcode, total_kcal: normalized.total_kcal, totals: normalized.totals, items: normalized.items };
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

  if (authLoading) return <SafeAreaView style={styles.center}><ActivityIndicator size="large" /></SafeAreaView>;

  if (!session?.user) {
    return (
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <View style={styles.card}>
            <Text style={styles.h1}>CalorieClick.ai</Text>
            <Text style={styles.sub}>Login or Signup</Text>
            <TextInput style={styles.input} placeholder="Email" autoCapitalize="none" value={email} onChangeText={setEmail} />
            <TextInput style={styles.input} placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
            <TouchableOpacity style={styles.btn} onPress={signIn}><Text style={styles.btnText}>Login</Text></TouchableOpacity>
            <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={signUp}><Text style={styles.btnText}>Signup</Text></TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>CalorieClick.ai</Text>
          <Text style={styles.small}>Plan: <Text style={{ fontWeight: "800" }}>{activePlan}</Text> • Remaining: <Text style={{ fontWeight: "800" }}>{usage?.remaining_month ?? "-"}</Text></Text>
        </View>
        <TouchableOpacity style={styles.smallBtn} onPress={() => setPaywallOpen(true)}><Text style={styles.smallBtnText}>Upgrade</Text></TouchableOpacity>
        <TouchableOpacity style={[styles.smallBtn, { marginLeft: 8 }]} onPress={signOut}><Text style={styles.smallBtnText}>Logout</Text></TouchableOpacity>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 26 }}>
        <View style={styles.modeRow}>
          <TouchableOpacity style={[styles.modeBtn, mode === "photo" && styles.modeBtnActive]} onPress={() => setMode("photo")}><Text style={[styles.modeText, mode === "photo" && 
styles.modeTextActive]}>Photo</Text></TouchableOpacity>
          <TouchableOpacity style={[styles.modeBtn, mode === "barcode" && styles.modeBtnActive]} onPress={() => { if (!isElitePlus(activePlan)) { Alert.alert("Upgrade required", "Barcode scanning 
requires Elite+."); return; } setMode("barcode"); }}><Text style={[styles.modeText, mode === "barcode" && styles.modeTextActive]}>Barcode</Text></TouchableOpacity>
        </View>

        <View style={styles.cameraWrap}>
          {permission?.granted ? (
            <CameraView ref={cameraRef} style={styles.camera} facing="back" barcodeScannerSettings={mode === "barcode" ? { barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"] } : undefined} 
onBarcodeScanned={mode === "barcode" ? (e) => barcodeLookup(e?.data) : undefined} />
          ) : (
            <View style={styles.centerInline}><TouchableOpacity style={styles.btn} onPress={requestPermission}><Text style={styles.btnText}>Grant permission</Text></TouchableOpacity></View>
          )}
        </View>

        <View style={styles.actionsRow}>
          <TouchableOpacity style={styles.btnBig} onPress={() => { if (mode === "photo") cameraRef.current.takePictureAsync({ quality: 0.7 }).then(p => setPhotoUri(p.uri)); }}><Text 
style={styles.btnText}>Take Photo</Text></TouchableOpacity>
          <TouchableOpacity style={[styles.btnBig, !photoUri && { opacity: 0.4 }]} onPress={analyzePhoto} disabled={!photoUri}><Text style={styles.btnText}>Analyze</Text></TouchableOpacity>
        </View>

        {!!photoUri && <View style={styles.previewWrap}><Image source={{ uri: photoUri }} style={styles.preview} /></View>}

        {result && (
          <View style={styles.resultCard}>
            <Text style={styles.h2}>Total: {round1(result.total_kcal)} kcal</Text>
            <Text style={styles.sub}>P {round1(result?.totals?.protein_g)}g • C {round1(result?.totals?.carbs_g)}g • F {round1(result?.totals?.fat_g)}g</Text>

            {result?.coaching && (() => {
              const coaching = result.coaching;
              const satScore = num(coaching.satiety_score);
              const bv = num(coaching.protein_bv);
              const leucine = num(coaching.leucine_est_g);
              const mpsOk = Boolean(coaching.mps_triggered); // FIX: Removed duplicate assignment
              return (
                <View style={{ marginTop: 12 }}>
                  <View style={styles.metricRow}><Text style={styles.metricLabel}>Satiety Index</Text><Text style={styles.metricValue}>{Math.round(satScore)}/100</Text></View>
                  <View style={styles.barTrack}><View style={[styles.barFill, { width: `${satScore}%` }]} /></View>
                  <View style={[styles.metricRow, { marginTop: 10 }]}><Text style={styles.metricLabel}>Protein Bioavailability</Text><Text 
style={styles.metricValue}>{Math.round(bv)}/100</Text></View>
                  <View style={styles.barTrack}><View style={[styles.barFill, { width: `${bv}%` }]} /></View>
                  <View style={[styles.metricRow, { marginTop: 10 }]}><Text style={styles.metricLabel}>MPS (Leucine)</Text><Text style={styles.metricValue}>{leucine.toFixed(2)}g {mpsOk ? "✅" : 
"❌"}</Text></View>
                </View>
              );
            })()}

            <FlatList data={result.items} keyExtractor={(_, idx) => String(idx)} scrollEnabled={false} renderItem={({ item }) => (
              <View style={styles.itemRow}><Text style={styles.itemName}>{item.name}</Text><Text style={styles.itemKcal}>{round1(item.kcal)} kcal</Text></View>
            )} />
          </View>
        )}
      </ScrollView>

      <Modal visible={paywallOpen} animationType="slide">
        <SafeAreaView style={styles.modalWrap}>
          <View style={styles.modalHeader}><Text style={styles.h1}>Upgrade</Text><TouchableOpacity onPress={() => setPaywallOpen(false)}><Text 
style={styles.btnText}>Close</Text></TouchableOpacity></View>
          <ScrollView>
            {offering?.availablePackages.map(pkg => (
              <TouchableOpacity key={pkg.identifier} style={styles.planCard} onPress={() => buyPackage(pkg)}>
                <Text style={styles.h2}>{pkgTitle(pkg)} • {formatPrice(pkg)}</Text>
                <Text style={styles.small}>{planSubtitleFromTitle(pkgTitle(pkg))}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity style={styles.btn} onPress={restorePurchases}><Text style={styles.btnText}>Restore Purchases</Text></TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  card: { marginTop: 80, backgroundColor: "#15151c", borderRadius: 18, padding: 18 },
  topBar: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  h1: { fontSize: 24, fontWeight: "900", color: "white" },
  h2: { fontSize: 18, fontWeight: "800", color: "white" },
  sub: { marginTop: 6, color: "#b8b8c7" },
  small: { marginTop: 12, color: "#8d8da3", fontSize: 12 },
  input: { marginTop: 12, backgroundColor: "#1c1c25", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 10, color: "white" },
  btn: { marginTop: 12, backgroundColor: "#5b7cfa", borderRadius: 14, paddingVertical: 12, alignItems: "center" },
  btnSecondary: { backgroundColor: "#303043" },
  btnText: { color: "white", fontWeight: "900" },
  smallBtn: { backgroundColor: "#1c1c25", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  smallBtnText: { color: "white", fontWeight: "800" },
  modeRow: { flexDirection: "row", marginBottom: 10 },
  modeBtn: { flex: 1, backgroundColor: "#1c1c25", padding: 10, borderRadius: 14, alignItems: "center", marginRight: 8 },
  modeBtnActive: { backgroundColor: "#5b7cfa" },
  modeText: { color: "#b8b8c7", fontWeight: "900" },
  modeTextActive: { color: "white" },
  cameraWrap: { height: 280, borderRadius: 18, overflow: "hidden" },
  camera: { flex: 1 },
  actionsRow: { marginTop: 12, flexDirection: "row", gap: 12 },
  btnBig: { flex: 1, backgroundColor: "#5b7cfa", borderRadius: 16, paddingVertical: 16, alignItems: "center" },
  previewWrap: { marginTop: 10, alignItems: "center" },
  preview: { width: 180, height: 180, borderRadius: 18 },
  resultCard: { marginTop: 12, backgroundColor: "#15151c", borderRadius: 18, padding: 14 },
  metricRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  metricLabel: { color: "white", fontWeight: "800" },
  metricValue: { color: "#b8b8c7", fontWeight: "900" },
  barTrack: { marginTop: 8, height: 10, borderRadius: 10, backgroundColor: "#1c1c25", overflow: "hidden" },
  barFill: { height: 10, borderRadius: 10, backgroundColor: "#5b7cfa" },
  itemRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  itemName: { color: "white", fontWeight: "700", flex: 1, paddingRight: 10 },
  itemKcal: { color: "#b8b8c7", fontWeight: "800" },
  modalWrap: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planCard: { backgroundColor: "#15151c", borderRadius: 18, padding: 16, marginTop: 12 }
});
