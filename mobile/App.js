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

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const HISTORY_KEY = "kcal_scan_history_v3";
const historyKey = (uid) => `${HISTORY_KEY}:${uid}`;
const MAX_HISTORY = 50;

const RC_IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY || "";
const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "";
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((x) => x.trim())
  .filter(Boolean);

// barcode scan cooldown (avoid duplicate reads)
const BARCODE_COOLDOWN_MS = 1400;

// ===================== HELPERS =====================
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function planAtLeast(current, required) {
  const c = (current || "free").toLowerCase();
  const r = (required || "free").toLowerCase();
  return PLAN_ORDER.indexOf(c) >= PLAN_ORDER.indexOf(r);
}
function pickHighestEntitlement(active) {
  // active: array of entitlement ids/names
  const normalized = (active || []).map((x) => String(x || "").toLowerCase());
  // ensure only known entitlements
  const valid = normalized.filter((x) => PLAN_ORDER.includes(x));
  if (!valid.length) return null;
  // pick highest
  valid.sort((a, b) => PLAN_ORDER.indexOf(a) - PLAN_ORDER.indexOf(b));
  return valid[valid.length - 1];
}
async function safeJson(res) {
  const t = await res.text();
  try {
    return JSON.parse(t);
  } catch (e) {
    // This is the common "Unexpected token" in app when backend returns HTML/text.
    throw new Error(t?.slice(0, 220) || "Non-JSON response");
  }
}
async function apiGetUsage(userId) {
  const res = await fetch(`${API_BASE}/usage?user_id=${encodeURIComponent(userId)}`, {
    headers: { accept: "application/json" },
  });
  return await safeJson(res);
}
async function apiPlanSync(userId, entitlement, mode) {
  const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", accept: "application/json" },
    body: JSON.stringify({ entitlement, mode }),
  });
  return await safeJson(res);
}

function nowISO() {
  try {
    return new Date().toISOString();
  } catch {
    // fallback for very old JS engines
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
          <Text style={styles.meterValue}>{round1(value)}/{max}</Text>
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
  const [authEmail, setAuthEmail] = useState("");
  const [authPass, setAuthPass] = useState("");
  const [authBusy, setAuthBusy] = useState(false);

  // ===== Plan / Usage =====
  const [userId, setUserId] = useState(null);
  const [usage, setUsage] = useState(null);
  const plan = (usage?.plan || "free").toLowerCase();

  // ===== Photo Scan =====
  const [photoUri, setPhotoUri] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  // ===== History (isolated by user id) =====
  const [history, setHistory] = useState([]);

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

  // ===================== INIT =====================
  useEffect(() => {
    (async () => {
      if (!HAS_SUPABASE) return;
      const { data } = await supabase.auth.getSession();
      setSession(data?.session || null);
      supabase.auth.onAuthStateChange((_event, sess) => setSession(sess || null));
    })();
  }, []);

  useEffect(() => {
    // derive userId from session
    const uid = session?.user?.id || null;
    setUserId(uid);
  }, [session]);

  useEffect(() => {
    if (!userId) return;
    refreshUsage();
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

        // initial load
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

  async function syncPlanToBackend(mode) {
    if (!userId) return;
    const highest = pickHighestEntitlement(activeEntitlements);
    // If nothing active, keep free.
    const ent = highest || "free";

    try {
      await apiPlanSync(userId, ent, mode); // backend prevents restore from refilling scans
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
    // Buy a package that matches entitlement (best effort).
    try {
      if (!offerings?.current) {
        Alert.alert("Not ready", "Offerings not loaded yet.");
        return;
      }
      setRcBusy(true);

      // Find a package whose identifier contains the entitlement name.
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

      // IMPORTANT: send purchase mode so backend may reset counters (new period)
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
  }

  // ===================== CAMERA (PHOTO) =====================
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
  async function analyzePhoto() {
    if (!userId) return;
    if (!photoUri) {
      Alert.alert("No photo", "Take a photo first.");
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

      const res = await fetch(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: {
          accept: "application/json",
        },
        body: form,
      });

      const data = await safeJson(res);
      setResult(data);
      await refreshUsage();

      await pushHistory({
        ts: nowISO(),
        kind: "photo",
        total_kcal: data?.total_kcal,
        totals: data?.totals,
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
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`, {
        headers: { accept: "application/json" },
      });
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
        <KeyboardAvoidingView
          style={styles.safe}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <View style={styles.container}>
            <Text style={styles.h1}>CalorieClick.ai</Text>
            <Text style={styles.p}>Log in to scan meals and track your history.</Text>

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

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>

        <View style={styles.topRow}>
          <View>
            <Text style={styles.h1}>CalorieClick.ai</Text>
            <Text style={styles.p}>Plan: <Text style={styles.plan}>{plan}</Text></Text>
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
          <Text style={styles.tiny}>
            Restore does NOT refill scans (only syncs your plan).
          </Text>
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
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={clearCurrentScan}
              disabled={!photoUri && !result}
            >
              <Text style={styles.btnText}>Clear current scan</Text>
            </TouchableOpacity>
          </View>

          {result ? (
            <View style={{ marginTop: 14 }}>
              <Text style={styles.big}>Total: {round1(result.total_kcal)} kcal</Text>
              <Text style={styles.p}>
                Protein {round1(result?.totals?.protein_g)}g • Carbs {round1(result?.totals?.carbs_g)}g • Fat {round1(result?.totals?.fat_g)}g
              </Text>

              <Text style={[styles.cardTitle, { marginTop: 12 }]}>Items</Text>
              {(result.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>{it.name}</Text>
                  <Text style={styles.itemMeta}>{round1(it.grams)}g • {round1(it.kcal)} kcal</Text>
                </View>
              ))}

              <Text style={[styles.cardTitle, { marginTop: 14 }]}>Coaching insights</Text>

              {!canCoaching ? (
                <View style={styles.lockedBox}>
                  <Text style={styles.lockedTitle}>Locked 🔒</Text>
                  <Text style={styles.p}>Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.</Text>
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
                      MPS trigger: {round1(coaching.mps_threshold_g)}g • {coaching.mps_triggered ? "✅ Triggered" : "❌ Not yet"}
                    </Text>
                  </View>

                  <View style={styles.meter}>
                    <View style={styles.meterTop}>
                      <Text style={styles.meterLabel}>Glycemic load</Text>
                      <Text style={styles.meterValue}>{round1(coaching?.glycemic_load?.gl)} ({coaching?.glycemic_load?.level || "-"})</Text>
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
                        <Text key={i} style={styles.p}>• {m}</Text>
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
                    {item.kind === "barcode" ? `Barcode: ${item.name || item.barcode}` : `Meal: ${round1(item.total_kcal)} kcal`}
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
            <TouchableOpacity style={[styles.primaryBtn, styles.captureBtn]} onPress={takePhoto}>
              <Text style={styles.btnText}>Capture</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </Modal>

      {/* BARCODE MODAL (expo-camera barcode scanning, no expo-barcode-scanner dependency) */}
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
            barcodeScannerSettings={{ barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"] }}
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
  btnText: { color: "#fff", fontWeight: "800" },

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

  meter: { marginTop: 10, backgroundColor: "#0f0f0f", padding: 12, borderRadius: 14, borderWidth: 1, borderColor: "#1c1c1c" },
  meterTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  meterLabel: { color: "#fff", fontWeight: "900" },
  meterValue: { color: "#fff", fontWeight: "800" },
  meterHelp: { color: "#9c9c9c", marginTop: 6, fontSize: 12, lineHeight: 18 },
  barOuter: { height: 10, backgroundColor: "#1a1a1a", borderRadius: 999, marginTop: 10, overflow: "hidden" },
  barFill: { height: 10, backgroundColor: "#22c55e", borderRadius: 999 },

  lockedTag: { color: "#fff", fontWeight: "800", backgroundColor: "#2a2a2a", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },

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

  modalSafe: { flex: 1, backgroundColor: "#000" },
  modalTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12 },
  modalTitle: { color: "#fff", fontWeight: "900", fontSize: 16 },
  camera: { flex: 1 },
  modalBottom: { padding: 12, paddingBottom: 48, backgroundColor: "#000" },
});

