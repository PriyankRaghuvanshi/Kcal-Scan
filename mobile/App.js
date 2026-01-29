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

const HISTORY_KEY_BASE = "kcal_scan_history_v3";
const historyKeyForUser = (uid) => `${HISTORY_KEY_BASE}_${uid || "guest"}`;
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
// FIX: Priority order (High to Low) so getActiveEntitlement picks the best one.
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "infinite,pro,advanced,elite")
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

function normalizeAnalyzeResponse(json) {
  // Pass through without much change, mostly ensures numbers
  const total_kcal = num(json?.total_kcal ?? 0);
  const totals = json?.totals || { protein_g: 0, carbs_g: 0, fat_g: 0 };
  const items = (json?.items || []).map(it => ({
     ...it,
     kcal: num(it.kcal),
     grams: num(it.grams)
  }));
  
  return { ...json, total_kcal, totals, items };
}

function normalizeBarcodeResponse(json) {
  const per = json?.per_100g || {};
  const item = {
    name: json?.name || "Unknown",
    grams: 100,
    kcal: num(per.kcal),
    macros: { protein_g: num(per.protein_g), carbs_g: num(per.carbs_g), fat_g: num(per.fat_g) }
  };
  return {
    source: "barcode",
    barcode: json?.barcode,
    total_kcal: num(per.kcal),
    totals: item.macros,
    items: [item],
    usage: json?.usage
  };
}

function getActiveEntitlement(customerInfo) {
  const active = customerInfo?.entitlements?.active || {};
  // Checks in order of definition (Infinite -> Pro -> Advanced -> Elite)
  for (const k of ENTITLEMENTS) {
    if (active[k]) return k;
  }
  return "free";
}

function pkgTitle(pkg) {
  const id = (pkg?.identifier || pkg?.product?.identifier || "").toLowerCase();
  if (id.includes("infinite")) return "INFINITE";
  if (id.includes("pro")) return "PRO";
  if (id.includes("advanced")) return "ADVANCED";
  if (id.includes("elite")) return "ELITE";
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

function isProPlus(plan) {
  const p = (plan || "free").toLowerCase();
  return p === "pro" || p === "infinite";
}

function isElitePlus(plan) {
    const p = (plan || "free").toLowerCase();
    return p !== "free";
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
        const raw = await AsyncStorage.getItem(historyKeyForUser(userId));
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
    return () => { listener?.subscription?.unsubscribe?.(); };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        setServerOk(res.ok);
      } catch { setServerOk(false); }
    })();
  }, []);

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
      } catch (e) {
        console.log("RC init error:", e);
      }
    })();
  }, [userId]);

  // ===================== BACKEND USAGE =====================
  async function fetchUsage() {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/usage`, { headers: backendHeaders(userId) });
      const json = await res.json();
      if(res.ok) setUsage(json);
    } catch {}
  }
  useEffect(() => { if (userId) fetchUsage(); }, [userId]);

  // ===================== PLAN SYNC =====================
  async function syncPlanToBackend(entitlement) {
    if (!userId) return;
    try {
      await fetch(`${API_BASE}/plan/sync`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ entitlement }),
      });
      await fetchUsage();
    } catch {}
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
      setActivePlan(getActiveEntitlement(info));
    } catch (e) { console.log(e); } finally { setRcLoading(false); }
  }

  async function buyPackage(pkg) {
    if (!pkg) return;
    setRcLoading(true);
    try {
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      const plan = getActiveEntitlement(customerInfo);
      setActivePlan(plan);
      await syncPlanToBackend(plan);
      Alert.alert("Success", `Plan activated: ${plan}`);
      setPaywallOpen(false);
    } catch (e) {
      if(!e.message.includes("cancel")) Alert.alert("Error", e.message);
    } finally { setRcLoading(false); }
  }

  async function restorePurchases() {
    setRcLoading(true);
    try {
      const info = await Purchases.restorePurchases();
      const plan = getActiveEntitlement(info);
      setActivePlan(plan);
      await syncPlanToBackend(plan);
      Alert.alert("Restored", `Active plan: ${plan}`);
      setPaywallOpen(false);
    } catch (e) { Alert.alert("Error", e.message); } finally { setRcLoading(false); }
  }

  // ===================== SCAN FUNCTIONS =====================
  async function analyzePhoto() {
    if (!photoUri || !userId) return;
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", { uri: photoUri, name: "photo.jpg", type: "image/jpeg" });

      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: backendHeaders(userId),
        body: form,
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail || "Analyze failed");

      const normalized = normalizeAnalyzeResponse(json);
      setResult(normalized);
      if(normalized.usage) setUsage(normalized.usage);

      const entry = {
        id: nowISO(), ts: nowISO(), mode: "photo",
        total_kcal: normalized.total_kcal, totals: normalized.totals, items: normalized.items
      };
      const newHist = [entry, ...history].slice(0, MAX_HISTORY);
      setHistory(newHist);
      await AsyncStorage.setItem(historyKeyForUser(userId), JSON.stringify(newHist));

    } catch (e) { Alert.alert("Error", e.message); } finally { setLoading(false); }
  }

  async function barcodeLookup(code) {
    if (!code || !userId) return;
    if (!isElitePlus(activePlan)) {
      Alert.alert("Elite Required", "Barcode scanning requires Elite plan or higher.");
      return;
    }
    const now = Date.now();
    if (lastBarcodeRef.current.code === code && now - lastBarcodeRef.current.t < BARCODE_COOLDOWN_MS) return;
    if (barcodeBusyRef.current) return;
    barcodeBusyRef.current = true;
    lastBarcodeRef.current = { code, t: now };

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(code)}`, {
        headers: backendHeaders(userId),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail || "Barcode failed");

      const normalized = normalizeBarcodeResponse(json);
      setResult(normalized);
      if(normalized.usage) setUsage(normalized.usage);

      const entry = {
        id: nowISO(), ts: nowISO(), mode: "barcode",
        total_kcal: normalized.total_kcal, totals: normalized.totals, items: normalized.items
      };
      setHistory([entry, ...history].slice(0, MAX_HISTORY));
      await AsyncStorage.setItem(historyKeyForUser(userId), JSON.stringify(history));

    } catch (e) { Alert.alert("Error", e.message); } finally { setLoading(false); barcodeBusyRef.current = false; }
  }

  // ===================== UI RENDER =====================
  if (!session?.user) {
    // Basic Auth Screen
    return (
       <SafeAreaView style={styles.container}>
         <View style={styles.card}>
           <Text style={styles.h1}>CalorieClick.ai</Text>
           <TextInput style={styles.input} placeholder="Email" value={email} onChangeText={setEmail} autoCapitalize="none"/>
           <TextInput style={styles.input} placeholder="Password" value={password} onChangeText={setPassword} secureTextEntry/>
           <TouchableOpacity style={styles.btn} onPress={async () => {
             setAuthLoading(true);
             const { error } = await supabase.auth.signInWithPassword({ email, password });
             setAuthLoading(false);
             if(error) Alert.alert("Login Error", error.message);
           }}><Text style={styles.btnText}>Login</Text></TouchableOpacity>
           
           <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={async () => {
             setAuthLoading(true);
             const { error } = await supabase.auth.signUp({ email, password });
             setAuthLoading(false);
             if(error) Alert.alert("Signup Error", error.message);
             else Alert.alert("Success", "Check email!");
           }}><Text style={styles.btnText}>Signup</Text></TouchableOpacity>
         </View>
       </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.topBar}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>CalorieClick</Text>
          <Text style={styles.small}>Plan: {activePlan.toUpperCase()} • Scans: {usage?.remaining_month ?? "-"}</Text>
        </View>
        <TouchableOpacity style={styles.smallBtn} onPress={openPaywall}><Text style={styles.smallBtnText}>Upgrade</Text></TouchableOpacity>
        <TouchableOpacity style={[styles.smallBtn, { marginLeft: 8 }]} onPress={() => supabase.auth.signOut()}><Text style={styles.smallBtnText}>Logout</Text></TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Mode Switch */}
        <View style={styles.modeRow}>
          <TouchableOpacity style={[styles.modeBtn, mode==="photo"&&styles.modeBtnActive]} onPress={()=>setMode("photo")}>
             <Text style={mode==="photo"?styles.modeTextActive:styles.modeText}>Photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.modeBtn, mode==="barcode"&&styles.modeBtnActive]} onPress={()=>setMode("barcode")}>
             <Text style={mode==="barcode"?styles.modeTextActive:styles.modeText}>Barcode</Text>
          </TouchableOpacity>
        </View>

        {/* Camera */}
        <View style={styles.cameraWrap}>
           {permission?.granted ? (
             <CameraView 
                ref={cameraRef} 
                style={styles.camera} 
                facing="back"
                barcodeScannerSettings={ mode==="barcode" ? { barcodeTypes: ["ean13", "upc_a"] } : undefined }
                onBarcodeScanned={ mode==="barcode" ? (e)=>barcodeLookup(e.data) : undefined }
             />
           ) : <Text style={{color:"white", padding:20}}>No Camera Permission</Text>}
        </View>

        {/* Actions */}
        <View style={styles.actionsRow}>
           {mode === "photo" && (
             <>
              <TouchableOpacity style={styles.btnBig} onPress={async () => {
                if(cameraRef.current) {
                   const p = await cameraRef.current.takePictureAsync({quality:0.5});
                   setPhotoUri(p.uri);
                }
              }}><Text style={styles.btnText}>Capture</Text></TouchableOpacity>
              
              <TouchableOpacity style={[styles.btnBig, !photoUri && { opacity: 0.5 }]} disabled={!photoUri} onPress={analyzePhoto}>
                 <Text style={styles.btnText}>{loading ? "Analyzing..." : "Analyze"}</Text>
              </TouchableOpacity>
             </>
           )}
           {mode === "barcode" && <Text style={styles.sub}>Scan a barcode to lookup.</Text>}
        </View>

        {/* Result Area */}
        {result && (
          <View style={styles.resultCard}>
            <Text style={styles.h2}>{round1(result.total_kcal)} kcal</Text>
            <Text style={styles.sub}>P: {round1(result.totals.protein_g)}g • C: {round1(result.totals.carbs_g)}g • F: {round1(result.totals.fat_g)}g</Text>
            {result.items.map((it, i) => (
               <Text key={i} style={styles.small}>{it.name} ({round1(it.kcal)} kcal)</Text>
            ))}

            {/* COACHING UI */}
            {isProPlus((usage?.plan || activePlan)) && result?.coaching && (() => {
               // Bar helper function
               const bar = (val, max = 100) => {
                 const pct = Math.max(0, Math.min(1, val / max));
                 return (
                   <View style={styles.barWrap}>
                     <View style={[styles.barFill, { width: `${pct * 100}%` }]} />
                   </View>
                 );
               };

               const sat = num(result.coaching.satiety_score);
               const bv = num(result.coaching.protein_bv);
               
               return (
                  <View style={styles.coachingCard}>
                     <Text style={styles.h2}>Coach Insights</Text>
                     
                     <Text style={styles.sub}>Satiety Score (how filling): {round1(sat)}/100</Text>
                     {bar(sat, 100)}

                     <Text style={styles.sub}>Protein Bioavailability: {round1(bv)}/100</Text>
                     {bar(bv, 100)}

                     <Text style={styles.sub}>Leucine: {result.coaching.leucine_g}g {result.coaching.mps_triggered ? "✅" : "⚠️"}</Text>
                     
                     {result.coaching.glycemic_load && <Text style={styles.sub}>Glycemic Load: {result.coaching.glycemic_load}</Text>}
                     {result.coaching.nova_label && <Text style={styles.sub}>Processing: {result.coaching.nova_label}</Text>}
                  </View>
               );
            })()}
            
            {result.locked && (
              <View style={styles.lockedCard}>
                <Text style={styles.lockedTitle}>🔓 Unlock Pro Insights</Text>
                <Text style={styles.lockedBody}>Upgrade to see Satiety, Bioavailability, Glycemic Load, and more.</Text>
              </View>
            )}
          </View>
        )}
      </ScrollView>

      {/* PAYWALL MODAL */}
      <Modal visible={paywallOpen} animationType="slide">
         <SafeAreaView style={styles.modalWrap}>
           <View style={styles.modalHeader}>
             <Text style={styles.h1}>Upgrade Plan</Text>
             <TouchableOpacity onPress={()=>setPaywallOpen(false)}><Text style={styles.smallBtnText}>Close</Text></TouchableOpacity>
           </View>
           {rcLoading ? <ActivityIndicator size="large"/> : (
             <ScrollView>
               {offering?.availablePackages?.sort((a,b)=>planRankFromPkg(b)-planRankFromPkg(a)).map(pkg => (
                  <TouchableOpacity key={pkg.identifier} style={styles.planCard} onPress={()=>buyPackage(pkg)}>
                     <Text style={styles.h2}>{pkgTitle(pkg)}</Text>
                     <Text style={styles.sub}>{pkg.product.priceString}</Text>
                     <Text style={styles.small}>{pkg.product.description}</Text>
                  </TouchableOpacity>
               ))}
               <TouchableOpacity style={[styles.btn, {marginTop:20}]} onPress={restorePurchases}>
                 <Text style={styles.btnText}>Restore Purchases</Text>
               </TouchableOpacity>
               <Text style={[styles.small, {textAlign:"center", marginTop:10}]}>
                 Downgrades apply at next billing cycle.
               </Text>
             </ScrollView>
           )}
         </SafeAreaView>
      </Modal>

    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  card: { backgroundColor: "#15151c", borderRadius: 18, padding: 18, marginTop: 80 },
  topBar: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  h1: { fontSize: 24, fontWeight: "900", color: "white" },
  h2: { fontSize: 18, fontWeight: "800", color: "white" },
  sub: { marginTop: 6, color: "#b8b8c7" },
  small: { marginTop: 4, color: "#8d8da3", fontSize: 12 },
  input: { marginTop: 12, backgroundColor: "#1c1c25", borderRadius: 14, padding: 12, color: "white" },
  btn: { marginTop: 12, backgroundColor: "#5b7cfa", borderRadius: 14, padding: 12, alignItems: "center" },
  btnBig: { flex: 1, backgroundColor: "#5b7cfa", borderRadius: 16, padding: 14, alignItems: "center" },
  btnSecondary: { backgroundColor: "#303043" },
  btnText: { color: "white", fontWeight: "900" },
  smallBtn: { backgroundColor: "#1c1c25", padding: 10, borderRadius: 12 },
  smallBtnText: { color: "white", fontWeight: "800" },
  modeRow: { flexDirection: "row", marginBottom: 10 },
  modeBtn: { flex: 1, backgroundColor: "#1c1c25", padding: 10, borderRadius: 14, alignItems: "center", marginRight: 8 },
  modeBtnActive: { backgroundColor: "#5b7cfa" },
  modeText: { color: "#b8b8c7", fontWeight: "900" },
  modeTextActive: { color: "white" },
  cameraWrap: { height: 280, borderRadius: 18, overflow: "hidden", backgroundColor:"#000" },
  camera: { flex: 1 },
  actionsRow: { marginTop: 12, flexDirection: "row", gap: 12, alignItems: "center" },
  resultCard: { marginTop: 12, backgroundColor: "#15151c", borderRadius: 18, padding: 14 },
  coachingCard: { marginTop: 12, backgroundColor: "#1f1f29", borderRadius: 12, padding: 12 },
  barWrap: { height: 8, backgroundColor: "#333", borderRadius: 4, marginTop: 4, marginBottom: 8, overflow: "hidden" },
  barFill: { height: "100%", backgroundColor: "#5b7cfa" },
  lockedCard: { marginTop: 12, padding: 12, borderWidth: 1, borderColor: "#333", borderRadius: 12 },
  lockedTitle: { color: "#ffcf5a", fontWeight: "bold" },
  lockedBody: { color: "#888", fontSize: 12 },
  modalWrap: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 20 },
  planCard: { backgroundColor: "#15151c", borderRadius: 18, padding: 16, marginTop: 12 },
});
