// mobile/App.js
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
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";

// ===================== CONFIG =====================
const API_BASE = "https://kcal-scan-production.up.railway.app";
const HISTORY_KEY = "kcal_scan_history_v2";
const MAX_HISTORY = 50;

// Supabase (from mobile/.env)
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error(
    "Missing Supabase env vars. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY in mobile/.env then restart Expo."
  );
}

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ===================== PLANS =====================
// Your requested plans
const PLANS = {
  free: { name: "Free", price: 0, monthLimit: 25, dayLimit: 9999 },
  elite: { name: "Elite", price: 20, monthLimit: 50, dayLimit: 15 },
  advanced: { name: "Advanced", price: 40, monthLimit: 100, dayLimit: 20 },
  pro: { name: "Pro", price: 100, monthLimit: 1000, dayLimit: 25 },
  infinite: { name: "Infinite", price: 1000, monthLimit: 10000, dayLimit: 30 },
};

// “Free reset if no scans in 1 month”
const FREE_INACTIVITY_RESET_DAYS = 30;

// ===================== helpers =====================
function round1(x) {
  const n = Number(x);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}
function num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}
function nowISO() {
  return new Date().toISOString();
}
function dayKey(d = new Date()) {
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}
function monthKey(d = new Date()) {
  return d.toISOString().slice(0, 7); // YYYY-MM
}

// Normalize backend analyze response
function normalizeAnalyzeResponse(json) {
  const total_kcal = num(json?.total_kcal ?? 0);
  const totals = json?.totals || { protein_g: 0, carbs_g: 0, fat_g: 0 };
  const items = Array.isArray(json?.items) ? json.items : [];
  return { total_kcal, totals, items };
}

// Normalize barcode response
function normalizeBarcodeResponse(json) {
  // backend returns { source:"barcode", barcode, name, brand, per_100g:{...} }
  const per = json?.per_100g || {};
  return {
    source: "barcode",
    barcode: json?.barcode,
    name: json?.name,
    brand: json?.brand,
    total_kcal: num(per?.kcal ?? 0),
    totals: {
      protein_g: num(per?.protein_g ?? 0),
      carbs_g: num(per?.carbs_g ?? 0),
      fat_g: num(per?.fat_g ?? 0),
    },
    items: [
      {
        name: json?.name || "Product",
        grams: 100,
        confidence: 1,
        kcal: num(per?.kcal ?? 0),
        macros: {
          protein_g: num(per?.protein_g ?? 0),
          carbs_g: num(per?.carbs_g ?? 0),
          fat_g: num(per?.fat_g ?? 0),
        },
      },
    ],
  };
}

// ===================== Supabase usage gating (soft) =====================
//
// Tables expected:
//
// profiles:
//   id uuid PK references auth.users
//   plan text default 'free'
//
// usage_counters:
//   id uuid PK references auth.users
//   month_key text
//   month_scans int
//   day_key text
//   day_scans int
//   lifetime_scans int
//   last_scan_at timestamptz
//
async function ensureProfile(userId) {
  // upsert profile row (plan defaults to free)
  await supabase.from("profiles").upsert({ id: userId }, { onConflict: "id" });
}

async function getProfile(userId) {
  const { data, error } = await supabase
    .from("profiles")
    .select("id,plan")
    .eq("id", userId)
    .maybeSingle();

  if (error) throw error;
  return data || { id: userId, plan: "free" };
}

async function getUsage(userId) {
  const { data, error } = await supabase
    .from("usage_counters")
    .select("id,month_key,month_scans,day_key,day_scans,lifetime_scans,last_scan_at")
    .eq("id", userId)
    .maybeSingle();

  if (error) throw error;
  return data;
}

async function upsertUsage(row) {
  const { data, error } = await supabase
    .from("usage_counters")
    .upsert(row, { onConflict: "id" })
    .select()
    .single();

  if (error) throw error;
  return data;
}

function daysSince(iso) {
  if (!iso) return 9999;
  const ms = Date.now() - new Date(iso).getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
}

async function canScanAndConsume(userId, planCode) {
  const plan = PLANS[planCode] || PLANS.free;

  const today = dayKey();
  const thisMonth = monthKey();

  let usage = await getUsage(userId);

  // create if missing
  if (!usage) {
    usage = await upsertUsage({
      id: userId,
      month_key: thisMonth,
      month_scans: 0,
      day_key: today,
      day_scans: 0,
      lifetime_scans: 0,
      last_scan_at: null,
    });
  }

  // Reset month/day keys if changed
  let month_scans = usage.month_key === thisMonth ? num(usage.month_scans) : 0;
  let day_scans = usage.day_key === today ? num(usage.day_scans) : 0;
  let lifetime_scans = num(usage.lifetime_scans);

  // Free inactivity reset
  if (planCode === "free") {
    const inactiveDays = daysSince(usage.last_scan_at);
    if (inactiveDays >= FREE_INACTIVITY_RESET_DAYS) {
      lifetime_scans = 0;
    }
  }

  // Check limits
  if (day_scans >= plan.dayLimit) {
    return { ok: false, reason: `Daily limit reached (${plan.dayLimit}/day)` };
  }

  // For free: lifetime cap acts like "monthLimit" but lifetime
  if (planCode === "free") {
    if (lifetime_scans >= plan.monthLimit) {
      return { ok: false, reason: `Free limit reached (${plan.monthLimit} total)` };
    }
  } else {
    if (month_scans >= plan.monthLimit) {
      return { ok: false, reason: `Monthly limit reached (${plan.monthLimit}/month)` };
    }
  }

  // Consume 1 scan
  const newUsage = await upsertUsage({
    id: userId,
    month_key: thisMonth,
    month_scans: planCode === "free" ? month_scans : month_scans + 1,
    day_key: today,
    day_scans: day_scans + 1,
    lifetime_scans: lifetime_scans + 1,
    last_scan_at: nowISO(),
  });

  return { ok: true, usage: newUsage };
}

// ==================================================

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Auth
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // Barcode scanning throttle
  const [lastBarcode, setLastBarcode] = useState(null);
  const [barcodeBusy, setBarcodeBusy] = useState(false);

  // Subscription
  const [profile, setProfile] = useState({ plan: "free" });
  const plan = PLANS[profile.plan] || PLANS.free;

  // Manual add modal
  const [manualOpen, setManualOpen] = useState(false);
  const [manualBarcode, setManualBarcode] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualBrand, setManualBrand] = useState("");
  const [manualKcal, setManualKcal] = useState("");
  const [manualP, setManualP] = useState("");
  const [manualC, setManualC] = useState("");
  const [manualF, setManualF] = useState("");

  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getSession();
      setSession(data.session ?? null);
      setAuthLoading(false);
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession ?? null);
    });

    return () => sub?.subscription?.unsubscribe?.();
  }, []);

  useEffect(() => {
    checkServer();
    loadHistory();
  }, []);

  useEffect(() => {
    // load profile on login
    (async () => {
      if (!session?.user?.id) return;
      try {
        await ensureProfile(session.user.id);
        const p = await getProfile(session.user.id);
        setProfile(p);
      } catch (e) {
        console.log("profile load error:", e);
      }
    })();
  }, [session?.user?.id]);

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
      mode: scan.mode || "photo",
      barcode: scan.barcode || null,
      total_kcal: round1(scan?.total_kcal),
      totals: scan?.totals || { protein_g: 0, carbs_g: 0, fat_g: 0 },
      items: scan?.items || [],
      photoUri: scan?.photoUri || null,
    };
    const next = [entry, ...history].slice(0, MAX_HISTORY);
    setHistory(next);
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
          setPhotoUri(null);
          await AsyncStorage.removeItem(HISTORY_KEY);
        },
      },
    ]);
  };

  const deleteHistoryItem = async (id) => {
    const next = history.filter((h) => h.id !== id);
    setHistory(next);
    if (selected?.id === id) setSelected(null);
    await saveHistory(next);
  };

  // ---------- AUTH ----------
  const signUp = async () => {
    try {
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Check your email", "Confirm your email, then log in.");
    } catch (e) {
      Alert.alert("Sign up error", e.message);
    }
  };

  const signIn = async () => {
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login error", e.message);
    }
  };

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
      setSelected(null);
      setResult(null);
      setPhotoUri(null);
      setProfile({ plan: "free" });
    } catch (e) {
      Alert.alert("Sign out error", e.message);
    }
  };

  // ---------- PHOTO ----------
  const snapPhoto = async () => {
    if (!cameraRef.current) return;
    const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
    setPhotoUri(photo.uri);
    setResult(null);
    setSelected(null);
  };

  const analyzePhoto = async () => {
    if (!photoUri) {
      Alert.alert("Take a photo first");
      return;
    }
    if (!session?.user?.id) {
      Alert.alert("Login required");
      return;
    }

    // plan gating
    const gate = await canScanAndConsume(session.user.id, profile.plan);
    if (!gate.ok) {
      Alert.alert("Limit reached", gate.reason);
      return;
    }

    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const form = new FormData();
      form.append("file", { uri: photoUri, name: "food.jpg", type: "image/jpeg" });

      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        body: form,
      });

      const text = await res.text();
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${text}`);

      const json = JSON.parse(text);
      const normalized = normalizeAnalyzeResponse(json);

      const enriched = { ...normalized, photoUri, mode: "photo" };
      setResult(enriched);
      await addToHistory(enriched);
    } catch (err) {
      Alert.alert("API Error", err.message);
    } finally {
      setLoading(false);
    }
  };

  // ---------- BARCODE ----------
  const onBarcodeScanned = async ({ data }) => {
    if (!data || barcodeBusy) return;

    const digits = String(data).replace(/\D/g, "");
    if (!digits || digits.length < 8) return;

    // throttle repeated scans
    if (digits === lastBarcode) return;
    setLastBarcode(digits);

    await lookupBarcode(digits);
  };

  const lookupBarcode = async (code) => {
    if (!session?.user?.id) {
      Alert.alert("Login required");
      return;
    }

    // plan gating
    const gate = await canScanAndConsume(session.user.id, profile.plan);
    if (!gate.ok) {
      Alert.alert("Limit reached", gate.reason);
      return;
    }

    setBarcodeBusy(true);
    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const res = await fetch(`${API_BASE}/barcode/${code}`);
      const text = await res.text();

      if (res.status === 404) {
        // show manual add modal
        setManualBarcode(code);
        setManualName("");
        setManualBrand("");
        setManualKcal("");
        setManualP("");
        setManualC("");
        setManualF("");
        setManualOpen(true);
        return;
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}: ${text}`);
      const json = JSON.parse(text);
      const normalized = normalizeBarcodeResponse(json);

      const enriched = { ...normalized, mode: "barcode", barcode: code };
      setResult(enriched);
      await addToHistory(enriched);
    } catch (e) {
      Alert.alert("Barcode error", e.message);
    } finally {
      setLoading(false);
      setBarcodeBusy(false);
    }
  };

  const saveManualProduct = async () => {
    const payload = {
      barcode: manualBarcode,
      name: manualName.trim(),
      brand: manualBrand.trim() || null,
      kcal_per_100g: Number(manualKcal),
      protein_g_per_100g: Number(manualP || 0),
      carbs_g_per_100g: Number(manualC || 0),
      fat_g_per_100g: Number(manualF || 0),
    };

    if (!payload.name) {
      Alert.alert("Missing", "Name is required");
      return;
    }
    if (!Number.isFinite(payload.kcal_per_100g) || payload.kcal_per_100g <= 0) {
      Alert.alert("Invalid", "kcal per 100g must be > 0");
      return;
    }

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/barcode/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const text = await res.text();
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${text}`);

      const json = JSON.parse(text);

      // convert to barcode response format for display
      const normalized = normalizeBarcodeResponse({
        barcode: json.barcode,
        name: json.name,
        brand: json.brand,
        per_100g: {
          kcal: json?.per_100g?.kcal,
          protein_g: json?.per_100g?.protein_g,
          carbs_g: json?.per_100g?.carbs_g,
          fat_g: json?.per_100g?.fat_g,
        },
      });

      const enriched = { ...normalized, mode: "barcode", barcode: manualBarcode };
      setResult(enriched);
      await addToHistory(enriched);

      setManualOpen(false);
      Alert.alert("Saved ✅", "Product saved to your database");
    } catch (e) {
      Alert.alert("Save failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  // ---------- PLAN UI (for now: manual switch for testing) ----------
  const setPlanForTesting = async (planCode) => {
    if (!session?.user?.id) return;
    try {
      const { error } = await supabase.from("profiles").upsert(
        { id: session.user.id, plan: planCode },
        { onConflict: "id" }
      );
      if (error) throw error;
      setProfile({ plan: planCode });
      Alert.alert("Plan updated", `Now on ${PLANS[planCode].name}`);
    } catch (e) {
      Alert.alert("Plan update failed", e.message);
    }
  };

  // ---------- RENDER ----------
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
          <Text style={{ color: "white", fontSize: 26, fontWeight: "900" }}>
            Kcal Scan
          </Text>
          <Text style={{ color: "#aaa", marginTop: 6 }}>
            Login to save scans + subscriptions
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

  if (!permission) return <View style={{ flex: 1, backgroundColor: "#000" }} />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={{ color: "white", marginBottom: 10 }}>
          Camera permission required
        </Text>
        <TouchableOpacity onPress={requestPermission} style={styles.btn}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={signOut} style={[styles.btn, { marginTop: 12 }]}>
          <Text style={styles.btnText}>Sign out</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const display = result || selected;

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <SafeAreaView style={{ backgroundColor: "#000" }}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Kcal Scan</Text>

          <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
            <Text style={{ color: "#aaa", fontSize: 12 }}>
              Plan: {plan.name}
            </Text>
            <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
              <Text style={styles.smallBtnText}>Sign out</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Mode toggle */}
        <View style={styles.modeRow}>
          <TouchableOpacity
            onPress={() => setMode("photo")}
            style={[styles.modeBtn, mode === "photo" && styles.modeBtnActive]}
          >
            <Text style={styles.modeBtnText}>📷 Photo</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => setMode("barcode")}
            style={[styles.modeBtn, mode === "barcode" && styles.modeBtnActive]}
          >
            <Text style={styles.modeBtnText}>🏷️ Barcode</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* CAMERA */}
      <View style={styles.cameraWrap}>
        <CameraView
          style={styles.camera}
          ref={cameraRef}
          // barcode scanning only in barcode mode
          onBarcodeScanned={mode === "barcode" ? onBarcodeScanned : undefined}
          barcodeScannerSettings={{
            barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"],
          }}
        />
      </View>

      {/* PANEL */}
      <View style={styles.panel}>
        <Text style={{ color: serverOk ? "#2ecc71" : "#ff5a5f" }}>
          Server {serverOk ? "OK ✅" : "DOWN ❌"}
        </Text>

        {/* Plan test controls (temporary) */}
        <ScrollView horizontal style={{ marginTop: 10 }} showsHorizontalScrollIndicator={false}>
          {Object.keys(PLANS).map((k) => (
            <TouchableOpacity
              key={k}
              onPress={() => setPlanForTesting(k)}
              style={[
                styles.planPill,
                profile.plan === k ? styles.planPillActive : null,
              ]}
            >
              <Text style={styles.planPillText}>
                {PLANS[k].name} ${PLANS[k].price}/mo
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {mode === "photo" ? (
          <>
            {photoUri ? <Image source={{ uri: photoUri }} style={styles.preview} /> : null}

            <View style={styles.row}>
              <TouchableOpacity onPress={snapPhoto} style={styles.btn} disabled={loading}>
                <Text style={styles.btnText}>📸 Snap</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={analyzePhoto}
                style={[styles.btn, styles.primary]}
                disabled={loading}
              >
                <Text style={styles.btnText}>
                  {loading ? "Analyzing..." : "⚡ Snap & Analyze"}
                </Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Text style={{ color: "#ccc", marginTop: 10 }}>
              Point camera at a barcode (EAN/UPC). It will auto-scan.
            </Text>
            <View style={styles.row}>
              <TouchableOpacity
                onPress={() => {
                  setLastBarcode(null);
                  Alert.alert("Ready", "Scan another barcode");
                }}
                style={styles.btn}
                disabled={loading}
              >
                <Text style={styles.btnText}>Reset</Text>
              </TouchableOpacity>
            </View>
          </>
        )}

        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color="white" />
            <Text style={{ color: "white", marginLeft: 10 }}>
              {mode === "barcode" ? "Looking up barcode…" : "Estimating with AI + USDA…"}
            </Text>
          </View>
        ) : null}

        {/* RESULT */}
        {display ? (
          <View style={styles.resultBox}>
            <Text style={styles.resultTitle}>
              {result ? "Latest Result" : "From History"}
            </Text>

            <Text style={styles.kcalText}>
              Total: {round1(display.total_kcal)} kcal
              {display?.mode === "barcode" ? " (per 100g)" : ""}
            </Text>

            <Text style={styles.macros}>
              Protein {round1(display?.totals?.protein_g)}g • Carbs{" "}
              {round1(display?.totals?.carbs_g)}g • Fat{" "}
              {round1(display?.totals?.fat_g)}g
            </Text>

            <ScrollView style={{ maxHeight: 140, marginTop: 10 }}>
              {(display.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>
                    {it.name} ({round1(it.grams)}g)
                  </Text>
                  <Text style={styles.itemMeta}>
                    {round1(it.kcal)} kcal • P {round1(it?.macros?.protein_g)}g • C{" "}
                    {round1(it?.macros?.carbs_g)}g • F {round1(it?.macros?.fat_g)}g
                  </Text>
                </View>
              ))}
            </ScrollView>
          </View>
        ) : null}

        {/* HISTORY */}
        <View style={[styles.row, { marginTop: 14, alignItems: "center" }]}>
          <Text style={styles.historyTitle}>History</Text>
          <TouchableOpacity onPress={clearHistory} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Clear</Text>
          </TouchableOpacity>
        </View>

        <FlatList
          data={history}
          keyExtractor={(item) => item.id}
          style={{ maxHeight: 220, marginTop: 8 }}
          ListEmptyComponent={
            <Text style={{ color: "#aaa", marginTop: 8 }}>
              No scans yet.
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
                    {round1(item.total_kcal)} kcal {item.mode === "barcode" ? "(per 100g)" : ""}
                  </Text>
                  <Text style={styles.historySub}>
                    P {round1(item?.totals?.protein_g)}g • C{" "}
                    {round1(item?.totals?.carbs_g)}g • F{" "}
                    {round1(item?.totals?.fat_g)}g
                  </Text>
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

      {/* Manual add modal */}
      <Modal visible={manualOpen} transparent animationType="slide">
        <View style={styles.modalBg}>
          <View style={styles.modalCard}>
            <Text style={{ color: "white", fontSize: 18, fontWeight: "900" }}>
              Barcode not found
            </Text>
            <Text style={{ color: "#aaa", marginTop: 6 }}>
              Add nutrition per 100g and save it (so next scan works).
            </Text>

            <Text style={styles.modalLabel}>Barcode</Text>
            <Text style={{ color: "white" }}>{manualBarcode}</Text>

            <Text style={styles.modalLabel}>Name *</Text>
            <TextInput
              value={manualName}
              onChangeText={setManualName}
              placeholder="Product name"
              placeholderTextColor="#666"
              style={styles.input}
            />

            <Text style={styles.modalLabel}>Brand</Text>
            <TextInput
              value={manualBrand}
              onChangeText={setManualBrand}
              placeholder="Optional"
              placeholderTextColor="#666"
              style={styles.input}
            />

            <Text style={styles.modalLabel}>kcal per 100g *</Text>
            <TextInput
              value={manualKcal}
              onChangeText={setManualKcal}
              placeholder="e.g. 250"
              keyboardType="numeric"
              placeholderTextColor="#666"
              style={styles.input}
            />

            <View style={{ flexDirection: "row", gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalLabel}>Protein (g)</Text>
                <TextInput
                  value={manualP}
                  onChangeText={setManualP}
                  keyboardType="numeric"
                  placeholderTextColor="#666"
                  placeholder="0"
                  style={styles.input}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalLabel}>Carbs (g)</Text>
                <TextInput
                  value={manualC}
                  onChangeText={setManualC}
                  keyboardType="numeric"
                  placeholderTextColor="#666"
                  placeholder="0"
                  style={styles.input}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalLabel}>Fat (g)</Text>
                <TextInput
                  value={manualF}
                  onChangeText={setManualF}
                  keyboardType="numeric"
                  placeholderTextColor="#666"
                  placeholder="0"
                  style={styles.input}
                />
              </View>
            </View>

            <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
              <TouchableOpacity
                style={[styles.btn, { flex: 1 }]}
                onPress={() => setManualOpen(false)}
                disabled={loading}
              >
                <Text style={styles.btnText}>Cancel</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.btn, styles.primary, { flex: 1 }]}
                onPress={saveManualProduct}
                disabled={loading}
              >
                <Text style={styles.btnText}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ===================== styles =====================
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

  modeRow: {
    flexDirection: "row",
    gap: 10,
    paddingHorizontal: 14,
    paddingBottom: 10,
  },
  modeBtn: {
    flex: 1,
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#222",
  },
  modeBtnActive: {
    borderColor: "#007AFF",
  },
  modeBtnText: { color: "white", fontWeight: "800" },

  cameraWrap: { flex: 1 },
  camera: { flex: 1 },

  panel: { padding: 14, backgroundColor: "#0f0f0f" },

  preview: { height: 140, borderRadius: 12, marginTop: 10, marginBottom: 10 },

  row: { flexDirection: "row", gap: 10, marginTop: 10 },
  btn: {
    backgroundColor: "#2a2a2a",
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: "center",
    flex: 1,
  },
  primary: { backgroundColor: "#007AFF" },
  btnText: { color: "white", fontSize: 15, fontWeight: "700" },

  smallBtn: {
    backgroundColor: "#2a2a2a",
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 10,
  },
  smallBtnText: { color: "white", fontWeight: "700" },

  loadingRow: { flexDirection: "row", alignItems: "center", marginTop: 10 },

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

  label: { color: "#aaa", marginBottom: 6, marginTop: 2, fontWeight: "700" },
  input: {
    backgroundColor: "#121212",
    borderWidth: 1,
    borderColor: "#222",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: "white",
    marginTop: 6,
  },

  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },

  planPill: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: "#1a1a1a",
    borderWidth: 1,
    borderColor: "#222",
    marginRight: 8,
  },
  planPillActive: { borderColor: "#007AFF" },
  planPillText: { color: "white", fontWeight: "700", fontSize: 12 },

  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "center",
    padding: 16,
  },
  modalCard: {
    backgroundColor: "#111",
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: "#222",
  },
  modalLabel: { color: "#aaa", marginTop: 10, fontWeight: "700" },
});

