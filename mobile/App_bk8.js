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
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";

// ===================== CONFIG =====================
const API_BASE = "https://kcal-scan-production.up.railway.app";

// AsyncStorage keys
const HISTORY_KEY = "kcal_scan_history_v1";
const MAX_HISTORY = 30;

// Supabase (from mobile/.env)
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// Plans (UI-only for now)
const PLANS = [
  { key: "free", name: "Free", price: "$0", monthly: 25, daily: 5, note: "Resets if no scans received after 1 month" },
  { key: "elite", name: "Elite", monthly: 50, daily: 15 },
  { key: "advanced", name: "Advanced", monthly: 100, daily: 20 },
  { key: "pro", name: "Pro", monthly: 1000, daily: 25 },
  { key: "infinite", name: "Infinite", monthly: 10000, daily: 30 },
];
// ==================================================

function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function nowISO() {
  return new Date().toISOString();
}
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}

// accept totals/macros from different key styles
function pickMacros(obj) {
  if (!obj) return { protein_g: 0, carbs_g: 0, fat_g: 0 };

  const protein =
    obj.protein_g ?? obj.protein ?? obj.p ?? obj.proteinG ?? obj.protein_gm ?? 0;
  const carbs =
    obj.carbs_g ?? obj.carbs ?? obj.c ?? obj.carbsG ?? obj.carbs_gm ?? 0;
  const fat = obj.fat_g ?? obj.fat ?? obj.f ?? obj.fatG ?? obj.fat_gm ?? 0;

  return {
    protein_g: num(protein),
    carbs_g: num(carbs),
    fat_g: num(fat),
  };
}

function normalizeAnalyzeResponse(json) {
  const total_kcal = num(json?.total_kcal ?? json?.totalKcal ?? 0);

  const totalsCandidate = json?.totals ?? json?.macros ?? json?.total_macros ?? null;
  const totals = pickMacros(totalsCandidate);

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

  let computedTotals = totals;
  if (
    computedTotals.protein_g === 0 &&
    computedTotals.carbs_g === 0 &&
    computedTotals.fat_g === 0 &&
    items.length > 0
  ) {
    computedTotals = items.reduce(
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

  return {
    ...json,
    total_kcal: computedKcal,
    totals: computedTotals,
    items,
  };
}

/* =========================================================
✅ 1) Add these helper functions (near normalizeAnalyzeResponse)
========================================================= */

// Convert /barcode/{code} response into scan-like shape for history UI.
// Backend returns: { barcode, name, brand, per_100g:{kcal,protein_g,carbs_g,fat_g}, source, cached }
function normalizeBarcodeResponseToScan(json) {
  const kcal100 = num(json?.per_100g?.kcal);
  const p100 = num(json?.per_100g?.protein_g);
  const c100 = num(json?.per_100g?.carbs_g);
  const f100 = num(json?.per_100g?.fat_g);

  const name = (json?.name || "Unknown product").trim();
  const brand = (json?.brand || "").trim();
  const displayName = brand ? `${name} • ${brand}` : name;

  return {
    source: "barcode",
    barcode: json?.barcode || null,
    total_kcal: round1(kcal100), // per 100g
    totals: { protein_g: round1(p100), carbs_g: round1(c100), fat_g: round1(f100) },
    items: [
      {
        name: displayName,
        grams: 100,
        confidence: 1,
        kcal: round1(kcal100),
        macros: { protein_g: round1(p100), carbs_g: round1(c100), fat_g: round1(f100) },
      },
    ],
    cached: !!json?.cached,
    source_db: json?.source || null,
  };
}

// Fetch JSON but preserve HTTP status for 404 handling
async function fetchJsonWithStatus(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  return { ok: res.ok, status: res.status, text, json };
}

/* ========================================================= */

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Auth UI (optional)
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(Boolean(HAS_SUPABASE));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Subscription UI (do NOT remove)
  const [selectedPlan, setSelectedPlan] = useState("free");

  // App state
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // UI mode
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"

  /* =========================================================
✅ 2) Add state for Manual Add (somewhere in your useState section)
========================================================= */
  const [manualOpen, setManualOpen] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState("");

  const [manualBarcode, setManualBarcode] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualBrand, setManualBrand] = useState("");
  const [manualKcal100, setManualKcal100] = useState("");
  const [manualP100, setManualP100] = useState("");
  const [manualC100, setManualC100] = useState("");
  const [manualF100, setManualF100] = useState("");

  // Barcode scan guard (prevents repeated triggers + “multiple clicks to go back” feeling)
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const lastScanRef = useRef({ code: null, ts: 0 });

  useEffect(() => {
    checkServer();
    loadHistory();
  }, []);

  // Supabase session init + listener (optional)
  useEffect(() => {
    if (!HAS_SUPABASE || !supabase) {
      setAuthLoading(false);
      return;
    }

    (async () => {
      const { data } = await supabase.auth.getSession();
      setSession(data.session ?? null);
      setAuthLoading(false);
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession ?? null);
    });

    return () => {
      sub?.subscription?.unsubscribe?.();
    };
  }, []);

  const checkServer = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const json = await res.json();
      setServerOk(json.status === "ok");
    } catch {
      setServerOk(false);
    }
  };

  const loadHistory = async () => {
    try {
      const raw = await AsyncStorage.getItem(HISTORY_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) setHistory(parsed);
    } catch (e) {
      console.log("loadHistory error:", e);
    }
  };

  const saveHistory = async (items) => {
    try {
      await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(items));
    } catch (e) {
      console.log("saveHistory error:", e);
    }
  };

  const addToHistory = async (scan) => {
    const entry = {
      id: `${Date.now()}`,
      createdAt: nowISO(),
      total_kcal: round1(scan?.total_kcal),
      totals: scan?.totals || { protein_g: 0, carbs_g: 0, fat_g: 0 },
      items: scan?.items || [],
      photoUri: scan?.photoUri || null,
      source: scan?.source || "photo",
      barcode: scan?.barcode || null,
    };

    const next = [entry, ...history].slice(0, MAX_HISTORY);
    setHistory(next);
    await saveHistory(next);
  };

  const deleteHistoryItem = async (id) => {
    const next = history.filter((h) => h.id !== id);
    setHistory(next);
    if (selected?.id === id) setSelected(null);
    await saveHistory(next);
  };

  const clearHistory = async () => {
    Alert.alert("Clear history?", "This will remove all saved scans.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Clear",
        style: "destructive",
        onPress: async () => {
          setHistory([]);
          setSelected(null);
          setResult(null);
          await AsyncStorage.removeItem(HISTORY_KEY);
        },
      },
    ]);
  };

  const snapPhoto = async () => {
    if (!cameraRef.current) return;
    const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
    setPhotoUri(photo.uri);
    setResult(null);
    setSelected(null);
  };

  const analyze = async () => {
    if (!photoUri) {
      Alert.alert("Take a photo first");
      return;
    }

    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "food.jpg",
        type: "image/jpeg",
      });

      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        body: form,
      });

      const text = await res.text();
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${text}`);

      const json = JSON.parse(text);
      const normalized = normalizeAnalyzeResponse(json);

      const enriched = { ...normalized, photoUri, source: "photo" };
      setResult(enriched);
      await addToHistory(enriched);
    } catch (err) {
      Alert.alert("API Error", err.message);
    } finally {
      setLoading(false);
    }
  };

  // ---------- AUTH ACTIONS ----------
  const signUp = async () => {
    try {
      if (!supabase) return;
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Check your email", "Confirm your email, then log in.");
    } catch (e) {
      Alert.alert("Sign up error", e.message);
    }
  };

  const signIn = async () => {
    try {
      if (!supabase) return;
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login error", e.message);
    }
  };

  const signOut = async () => {
    try {
      if (supabase) await supabase.auth.signOut();
      setSelected(null);
      setResult(null);
      setPhotoUri(null);
      setMode("photo");
    } catch (e) {
      Alert.alert("Sign out error", e.message);
    }
  };

  /* =========================================================
✅ 3) Add the barcode lookup function (THIS is the main fix)
- calls GET /barcode/{code}
- handles 404 nicely (open manual add modal)
- stores success in history like photo scan
========================================================= */
  const openManualForBarcode = (barcode) => {
    setManualError("");
    setManualBarcode(barcode);
    setManualName("");
    setManualBrand("");
    setManualKcal100("");
    setManualP100("");
    setManualC100("");
    setManualF100("");
    setManualOpen(true);
  };

  const closeManual = () => {
    setManualOpen(false);
    setManualError("");
  };

  const barcodeLookup = async (rawCode) => {
    const code = String(rawCode || "").replace(/\D/g, "");
    if (!code) return;

    // Prevent repeated callbacks flooding
    const now = Date.now();
    const last = lastScanRef.current;
    if (last.code === code && now - last.ts < 1500) return;
    lastScanRef.current = { code, ts: now };

    // Pause scanning while modal open
    if (manualOpen) return;

    if (barcodeBusy) return;
    setBarcodeBusy(true);

    try {
      const { ok, status, json, text } = await fetchJsonWithStatus(`${API_BASE}/barcode/${code}`);

      if (!ok) {
        if (status === 404) {
          // Not found => manual add path
          openManualForBarcode(code);
          return;
        }
        throw new Error(`Barcode lookup failed (HTTP ${status}): ${text}`);
      }

      // Normalize and store like photo scan
      const scan = normalizeBarcodeResponseToScan(json);
      setMode("barcode");
      setPhotoUri(null);
      setSelected(null);
      setResult(scan);
      await addToHistory(scan);
    } catch (e) {
      Alert.alert("Barcode Error", e.message);
    } finally {
      setBarcodeBusy(false);
    }
  };

  /* =========================================================
✅ 4) Manual add -> POST /barcode/manual then store to history
========================================================= */
  const submitManual = async () => {
    setManualError("");

    const payload = {
      barcode: manualBarcode,
      name: manualName.trim(),
      brand: manualBrand.trim() || null,
      kcal_per_100g: num(manualKcal100),
      protein_g_per_100g: num(manualP100),
      carbs_g_per_100g: num(manualC100),
      fat_g_per_100g: num(manualF100),
    };

    if (!payload.barcode) return setManualError("Missing barcode");
    if (!payload.name) return setManualError("Name is required");
    if (!payload.kcal_per_100g || payload.kcal_per_100g <= 0)
      return setManualError("kcal per 100g is required");

    setManualBusy(true);
    try {
      const { ok, status, json, text } = await fetchJsonWithStatus(`${API_BASE}/barcode/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!ok) throw new Error(`Manual add failed (HTTP ${status}): ${text}`);

      const scan = normalizeBarcodeResponseToScan(json);
      setManualOpen(false);
      setMode("barcode");
      setPhotoUri(null);
      setSelected(null);
      setResult(scan);
      await addToHistory(scan);
    } catch (e) {
      setManualError(e.message);
    } finally {
      setManualBusy(false);
    }
  };

  // ---------- RENDER ----------
  if (!permission) return <View style={{ flex: 1, backgroundColor: "#000" }} />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={{ color: "white", marginBottom: 10 }}>Camera permission required</Text>
        <TouchableOpacity onPress={requestPermission} style={styles.btn}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // Auth screen only if Supabase configured
  if (HAS_SUPABASE) {
    if (authLoading) {
      return (
        <View style={[styles.center, { backgroundColor: "#000" }]}>
          <ActivityIndicator color="white" />
          <Text style={{ color: "white", marginTop: 10 }}>Loading…</Text>
        </View>
      );
    }

    if (!session) {
      return (
        <SafeAreaView style={{ flex: 1, backgroundColor: "#000" }}>
          <KeyboardAvoidingView
            style={{ flex: 1, padding: 18, justifyContent: "center" }}
            behavior={Platform.OS === "ios" ? "padding" : undefined}
          >
            <Text style={{ color: "white", fontSize: 26, fontWeight: "900" }}>Kcal Scan</Text>
            <Text style={{ color: "#aaa", marginTop: 6 }}>
              Login to save scans across devices (optional)
            </Text>

            <View style={{ marginTop: 18 }}>
              <Text style={styles.label}>Email</Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                keyboardType="email-address"
                placeholder="you@email.com"
                placeholderTextColor="#666"
                style={styles.input}
              />

              <Text style={[styles.label, { marginTop: 12 }]}>Password</Text>
              <TextInput
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                placeholder="••••••••"
                placeholderTextColor="#666"
                style={styles.input}
              />
            </View>

            <View style={{ flexDirection: "row", gap: 10, marginTop: 16 }}>
              <TouchableOpacity style={[styles.btn, styles.primary]} onPress={signIn}>
                <Text style={styles.btnText}>Login</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.btn} onPress={signUp}>
                <Text style={styles.btnText}>Sign up</Text>
              </TouchableOpacity>
            </View>
          </KeyboardAvoidingView>
        </SafeAreaView>
      );
    }
  }

  // IMPORTANT: show latest result first
  const display = result || selected;

  const planObj = PLANS.find((p) => p.key === selectedPlan) || PLANS[0];

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <SafeAreaView style={{ backgroundColor: "#000" }}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Kcal Scan</Text>

          <View style={{ flexDirection: "row", gap: 8 }}>
            <TouchableOpacity
              onPress={() => {
                setMode("photo");
                setManualOpen(false);
              }}
              style={[styles.smallBtn, mode === "photo" ? styles.smallBtnActive : null]}
            >
              <Text style={styles.smallBtnText}>Photo</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => {
                setMode("barcode");
                setPhotoUri(null);
                setSelected(null);
                setResult(null);
              }}
              style={[styles.smallBtn, mode === "barcode" ? styles.smallBtnActive : null]}
            >
              <Text style={styles.smallBtnText}>Barcode</Text>
            </TouchableOpacity>

            {HAS_SUPABASE ? (
              <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
                <Text style={styles.smallBtnText}>Sign out</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        </View>
      </SafeAreaView>

      {/* CAMERA */}
      <View style={styles.cameraWrap}>
        <CameraView
          style={styles.camera}
          ref={cameraRef}
          /* =========================================================
             ✅ 5) Hook it into Camera barcode scanning
             ========================================================= */
          onBarcodeScanned={
            mode === "barcode" && !manualOpen ? (e) => barcodeLookup(e?.data) : undefined
          }
          barcodeScannerSettings={{
            barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"],
          }}
        />
      </View>

      {/* PANEL */}
      <View style={styles.panel}>
        <Text style={{ color: serverOk ? "#2ecc71" : "#ff5a5f" }}>
          Server {serverOk ? "OK ✅" : "DOWN ❌"}
        </Text>

        {/* ===================== SUBSCRIPTION UI (KEEP THIS) ===================== */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Subscription plan (UI for now)</Text>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }}>
            {PLANS.map((p) => (
              <TouchableOpacity
                key={p.key}
                onPress={() => setSelectedPlan(p.key)}
                style={[styles.planPill, selectedPlan === p.key ? styles.planPillActive : null]}
              >
                <Text style={{ color: "white", fontWeight: "900" }}>
                  {p.name} {p.price}
                </Text>
                <Text style={{ color: "#cfcfcf", fontSize: 11, marginTop: 2 }}>
                  {p.daily}/day • {p.monthly}/mo
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={{ color: "#aaa", marginTop: 10, fontSize: 12 }}>
            Current:{" "}
            <Text style={{ color: "white", fontWeight: "900" }}>
              {planObj.name} ({planObj.price})
            </Text>
            {planObj.note ? ` • ${planObj.note}` : ""}
          </Text>
        </View>
        {/* ==================================================================== */}

        {/* PHOTO MODE CONTROLS */}
        {mode === "photo" ? (
          <>
            {photoUri ? <Image source={{ uri: photoUri }} style={styles.preview} /> : null}

            <View style={styles.row}>
              <TouchableOpacity onPress={snapPhoto} style={styles.btn} disabled={loading}>
                <Text style={styles.btnText}>📸 Snap</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={analyze}
                style={[styles.btn, styles.primary]}
                disabled={loading}
              >
                <Text style={styles.btnText}>{loading ? "Analyzing..." : "⚡ Snap & Analyze"}</Text>
              </TouchableOpacity>
            </View>

            {loading ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator color="white" />
                <Text style={{ color: "white", marginLeft: 10 }}>Estimating with AI + USDA…</Text>
              </View>
            ) : null}
          </>
        ) : (
          /* BARCODE MODE INFO */
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Barcode mode</Text>
            <Text style={{ color: "#ccc", marginTop: 6 }}>
              Point camera at a barcode. If it’s not found, you can add it once (per 100g).
            </Text>

            {barcodeBusy ? (
              <View style={[styles.loadingRow, { marginTop: 10 }]}>
                <ActivityIndicator color="white" />
                <Text style={{ color: "white", marginLeft: 10 }}>Looking up…</Text>
              </View>
            ) : null}
          </View>
        )}

        {/* =========================================================
            ✅ 6) Minimal Manual Add UI (quick modal-style block)
            ========================================================= */}
        {manualOpen ? (
          <View style={styles.modal}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={styles.modalTitle}>Add product (per 100g)</Text>
              <TouchableOpacity onPress={closeManual} style={styles.smallBtn}>
                <Text style={styles.smallBtnText}>Close</Text>
              </TouchableOpacity>
            </View>

            <Text style={styles.label}>Barcode</Text>
            <TextInput value={manualBarcode} editable={false} style={styles.input} />

            <Text style={styles.label}>Name *</Text>
            <TextInput value={manualName} onChangeText={setManualName} style={styles.input} />

            <Text style={styles.label}>Brand (optional)</Text>
            <TextInput value={manualBrand} onChangeText={setManualBrand} style={styles.input} />

            <Text style={styles.label}>kcal / 100g *</Text>
            <TextInput
              value={manualKcal100}
              onChangeText={setManualKcal100}
              keyboardType="numeric"
              style={styles.input}
            />

            <View style={{ flexDirection: "row", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Protein / 100g</Text>
                <TextInput
                  value={manualP100}
                  onChangeText={setManualP100}
                  keyboardType="numeric"
                  style={styles.input}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Carbs / 100g</Text>
                <TextInput
                  value={manualC100}
                  onChangeText={setManualC100}
                  keyboardType="numeric"
                  style={styles.input}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Fat / 100g</Text>
                <TextInput
                  value={manualF100}
                  onChangeText={setManualF100}
                  keyboardType="numeric"
                  style={styles.input}
                />
              </View>
            </View>

            {manualError ? (
              <Text style={{ color: "#ff6b6b", marginTop: 10, fontWeight: "800" }}>
                {manualError}
              </Text>
            ) : null}

            <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
              <TouchableOpacity
                onPress={submitManual}
                style={[styles.btn, styles.primary]}
                disabled={manualBusy}
              >
                <Text style={styles.btnText}>{manualBusy ? "Saving..." : "Save"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        {/* RESULT + MACROS */}
        {display ? (
          <View style={styles.resultBox}>
            <Text style={styles.resultTitle}>
              {result ? "Latest Result" : "From History"}{" "}
              {display?.source ? `• ${display.source}` : ""}
            </Text>

            <Text style={styles.kcalText}>Total: {round1(display.total_kcal)} kcal</Text>

            <Text style={styles.macros}>
              Protein {round1(display?.totals?.protein_g)}g • Carbs{" "}
              {round1(display?.totals?.carbs_g)}g • Fat{" "}
              {round1(display?.totals?.fat_g)}g
            </Text>

            {display?.barcode ? (
              <Text style={{ color: "#9aa", marginTop: 6, fontSize: 12 }}>
                Barcode: {display.barcode}
              </Text>
            ) : null}

            <ScrollView style={{ maxHeight: 140, marginTop: 10 }}>
              {(display.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>
                    {it.name} ({round1(it.grams)}g)
                  </Text>
                  <Text style={styles.itemMeta}>
                    {round1(it.kcal)} kcal • P {round1(it?.macros?.protein_g)}g • C{" "}
                    {round1(it?.macros?.carbs_g)}g • F {round1(it?.macros?.fat_g)}g{" "}
                    {typeof it.confidence === "number" ? `• conf ${round1(it.confidence)}` : ""}
                  </Text>
                </View>
              ))}
            </ScrollView>
          </View>
        ) : null}

        {/* HISTORY HEADER */}
        <View style={[styles.row, { marginTop: 14, alignItems: "center" }]}>
          <Text style={styles.historyTitle}>History</Text>
          <TouchableOpacity onPress={clearHistory} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Clear</Text>
          </TouchableOpacity>
        </View>

        {/* HISTORY LIST */}
        <FlatList
          data={history}
          keyExtractor={(item) => item.id}
          style={{ maxHeight: 220, marginTop: 8 }}
          ListEmptyComponent={
            <Text style={{ color: "#aaa", marginTop: 8 }}>
              No scans yet. Do a Snap & Analyze or scan a barcode.
            </Text>
          }
          renderItem={({ item }) => {
            const dt = new Date(item.createdAt);
            const label = `${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}`;

            return (
              <TouchableOpacity
                onPress={() => {
                  setSelected(item);
                  setResult(null);
                }}
                style={[
                  styles.historyRow,
                  selected?.id === item.id ? styles.historyRowActive : null,
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyMain}>
                    {round1(item.total_kcal)} kcal{" "}
                    {item?.source ? (
                      <Text style={{ color: "#7aa", fontSize: 12 }}>• {item.source}</Text>
                    ) : null}
                  </Text>

                  <Text style={styles.historySub}>
                    P {round1(item?.totals?.protein_g)}g • C{" "}
                    {round1(item?.totals?.carbs_g)}g • F{" "}
                    {round1(item?.totals?.fat_g)}g
                  </Text>

                  {item?.barcode ? (
                    <Text style={styles.historySub2}>Barcode: {item.barcode}</Text>
                  ) : null}

                  <Text style={styles.historySub2}>{label}</Text>
                </View>

                <TouchableOpacity
                  onPress={() => deleteHistoryItem(item.id)}
                  style={styles.deleteBtn}
                >
                  <Text style={{ color: "white", fontWeight: "700" }}>Del</Text>
                </TouchableOpacity>
              </TouchableOpacity>
            );
          }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },

  header: {
    paddingHorizontal: 14,
    paddingTop: 8,
    paddingBottom: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#000",
  },
  headerTitle: { color: "white", fontSize: 18, fontWeight: "900" },

  cameraWrap: { flex: 1 },
  camera: { flex: 1 },

  panel: { padding: 14, backgroundColor: "#0f0f0f" },

  preview: { height: 140, borderRadius: 12, marginTop: 10, marginBottom: 10 },

  row: { flexDirection: "row", gap: 10, marginTop: 10 },
  btn: {
    flex: 1,
    backgroundColor: "#2a2a2a",
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: "center",
  },
  primary: { backgroundColor: "#007AFF" },
  btnText: { color: "white", fontSize: 15, fontWeight: "700" },

  smallBtn: {
    backgroundColor: "#2a2a2a",
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 10,
  },
  smallBtnActive: { backgroundColor: "#007AFF" },
  smallBtnText: { color: "white", fontWeight: "700" },

  loadingRow: { flexDirection: "row", alignItems: "center", marginTop: 10 },

  card: {
    marginTop: 12,
    backgroundColor: "#161616",
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#222",
  },
  cardTitle: { color: "white", fontWeight: "900", fontSize: 14 },

  planPill: {
    backgroundColor: "#2a2a2a",
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 14,
    marginRight: 10,
    minWidth: 140,
  },
  planPillActive: { backgroundColor: "#007AFF" },

  resultBox: {
    marginTop: 14,
    backgroundColor: "#161616",
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#222",
  },
  resultTitle: { color: "#aaa", fontWeight: "700", marginBottom: 4 },
  kcalText: { color: "white", fontSize: 20, fontWeight: "900" },
  macros: { color: "#ccc", marginTop: 6 },

  itemRow: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#222" },
  itemName: { color: "white", fontWeight: "800" },
  itemMeta: { color: "#bdbdbd", marginTop: 2, fontSize: 12 },

  historyTitle: { color: "white", fontSize: 16, fontWeight: "800", flex: 1 },
  historyRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#141414",
    borderRadius: 12,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#1f1f1f",
  },
  historyRowActive: { borderColor: "#007AFF" },
  historyMain: { color: "white", fontWeight: "900", fontSize: 16 },
  historySub: { color: "#cfcfcf", marginTop: 2, fontSize: 12 },
  historySub2: { color: "#888", marginTop: 2, fontSize: 11 },

  deleteBtn: {
    backgroundColor: "#ff3b30",
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginLeft: 10,
  },

  label: { color: "#aaa", marginBottom: 6, marginTop: 10, fontWeight: "700" },
  input: {
    backgroundColor: "#121212",
    borderWidth: 1,
    borderColor: "#222",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: "white",
  },

  // ✅ modal-style manual add block (minimal)
  modal: {
    marginTop: 12,
    backgroundColor: "#141414",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "#222",
  },
  modalTitle: { color: "white", fontWeight: "900", fontSize: 16 },

  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
});

