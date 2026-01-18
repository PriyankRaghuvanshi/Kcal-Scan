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
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";

// ===================== CONFIG =====================
const API_BASE = "https://kcal-scan-production.up.railway.app";

// Local storage keys
const HISTORY_KEY = "kcal_scan_history_v3";
const MAX_HISTORY = 30;

const PLAN_KEY = "kcal_scan_plan_v1";
const USAGE_KEY = "kcal_scan_usage_v1";

// Supabase (optional)
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;
// ==================================================

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
function todayKey() {
  // local date key
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
function monthKey() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${yyyy}-${mm}`;
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

  const totalsCandidate =
    json?.totals ?? json?.macros ?? json?.total_macros ?? null;
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
    total_kcal && total_kcal > 0
      ? total_kcal
      : items.reduce((s, it) => s + num(it.kcal), 0);

  return {
    ...json,
    total_kcal: computedKcal,
    totals: computedTotals,
    items,
  };
}

// -------------------- Plans --------------------
const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    monthlyLimit: 25,
    dailyLimit: null,
    note: "25 scans total (resets if you didn’t scan for 1 month).",
  },
  {
    id: "elite",
    name: "Elite",
    price: "$20/mo",
    monthlyLimit: 50,
    dailyLimit: 15,
  },
  {
    id: "advanced",
    name: "Advanced",
    price: "$40/mo",
    monthlyLimit: 100,
    dailyLimit: 20,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$100/mo",
    monthlyLimit: 1000,
    dailyLimit: 25,
  },
  {
    id: "infinite",
    name: "Infinite",
    price: "$1000/mo",
    monthlyLimit: 10000,
    dailyLimit: 30,
  },
];

function planById(id) {
  return PLANS.find((p) => p.id === id) || PLANS[0];
}

async function loadJSON(key, fallback) {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}
async function saveJSON(key, val) {
  await AsyncStorage.setItem(key, JSON.stringify(val));
}

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Auth UI (optional)
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Modes
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"

  // App state
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // Barcode
  const [barcodeText, setBarcodeText] = useState("");
  const [lastScanned, setLastScanned] = useState(""); // debounce

  // Plan + usage
  const [planId, setPlanId] = useState("free");
  const [usage, setUsage] = useState({
    // monthly / daily usage
    month: monthKey(),
    monthCount: 0,
    day: todayKey(),
    dayCount: 0,
    // free rule: reset if no scans for 1 month
    lastScanAt: null,
    freeTotalCount: 0,
  });

  const plan = useMemo(() => planById(planId), [planId]);

  // ---- init ----
  useEffect(() => {
    console.log("✅ LOADED NEW APP.JS", new Date().toISOString());
  }, []);

  useEffect(() => {
    (async () => {
      // plan + usage
      const savedPlan = await loadJSON(PLAN_KEY, { planId: "free" });
      setPlanId(savedPlan.planId || "free");

      const savedUsage = await loadJSON(USAGE_KEY, null);
      if (savedUsage) setUsage(savedUsage);

      // history
      const raw = await AsyncStorage.getItem(HISTORY_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setHistory(parsed);
      }

      // supabase session
      if (supabase) {
        const { data } = await supabase.auth.getSession();
        setSession(data.session ?? null);
        supabase.auth.onAuthStateChange((_event, newSession) => {
          setSession(newSession ?? null);
        });
      }
      setAuthLoading(false);
    })();
  }, []);

  useEffect(() => {
    checkServer();
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

  const saveHistory = async (items) => {
    await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(items));
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
          await AsyncStorage.removeItem(HISTORY_KEY);
        },
      },
    ]);
  };

  // ---- usage enforcement (local for now) ----
  const refreshUsageCounters = async () => {
    const u = { ...usage };

    // reset day/month counters if changed
    const d = todayKey();
    const m = monthKey();

    if (u.day !== d) {
      u.day = d;
      u.dayCount = 0;
    }
    if (u.month !== m) {
      u.month = m;
      u.monthCount = 0;
    }

    // free rule: if no scan in 1 month, reset free total
    if (planId === "free" && u.lastScanAt) {
      const last = new Date(u.lastScanAt).getTime();
      const diffDays = (Date.now() - last) / (1000 * 60 * 60 * 24);
      if (diffDays >= 30) {
        u.freeTotalCount = 0;
      }
    }

    setUsage(u);
    await saveJSON(USAGE_KEY, u);
  };

  const canConsumeScan = async () => {
    await refreshUsageCounters();

    const u = await loadJSON(USAGE_KEY, usage);
    const p = planById(planId);

    // free = total limit
    if (planId === "free") {
      if ((u.freeTotalCount || 0) >= p.monthlyLimit) {
        return { ok: false, reason: "Free limit reached (25 scans). Upgrade to continue." };
      }
      return { ok: true };
    }

    // paid: monthly + daily
    if (p.monthlyLimit != null && (u.monthCount || 0) >= p.monthlyLimit) {
      return { ok: false, reason: `Monthly limit reached (${p.monthlyLimit}).` };
    }
    if (p.dailyLimit != null && (u.dayCount || 0) >= p.dailyLimit) {
      return { ok: false, reason: `Daily limit reached (${p.dailyLimit}/day).` };
    }
    return { ok: true };
  };

  const consumeScan = async () => {
    const u = await loadJSON(USAGE_KEY, usage);
    const p = planById(planId);

    u.lastScanAt = nowISO();

    if (planId === "free") {
      u.freeTotalCount = (u.freeTotalCount || 0) + 1;
    } else {
      // ensure counters aligned
      const d = todayKey();
      const m = monthKey();
      if (u.day !== d) {
        u.day = d;
        u.dayCount = 0;
      }
      if (u.month !== m) {
        u.month = m;
        u.monthCount = 0;
      }
      u.dayCount = (u.dayCount || 0) + 1;
      u.monthCount = (u.monthCount || 0) + 1;
    }

    setUsage(u);
    await saveJSON(USAGE_KEY, u);

    // Also persist selected plan
    await saveJSON(PLAN_KEY, { planId });
    return { usage: u, plan: p };
  };

  // ---- camera actions ----
  const snapPhoto = async () => {
    if (!cameraRef.current) return;
    const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
    setPhotoUri(photo.uri);
    setResult(null);
    setSelected(null);
  };

  const analyze = async () => {
    const gate = await canConsumeScan();
    if (!gate.ok) {
      Alert.alert("Limit reached", gate.reason);
      return;
    }

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

      // count scan usage only on success
      await consumeScan();

      const enriched = { ...normalized, photoUri, source: "photo" };
      setResult(enriched);
      await addToHistory(enriched);
    } catch (err) {
      Alert.alert("API Error", err.message);
    } finally {
      setLoading(false);
    }
  };

  // ---- barcode actions ----
  const barcodeLookup = async (code) => {
    const gate = await canConsumeScan();
    if (!gate.ok) {
      Alert.alert("Limit reached", gate.reason);
      return;
    }

    const barcode = String(code || "").trim();
    if (!barcode) return;

    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(barcode)}`, {
        method: "GET",
      });

      const text = await res.text();
      if (!res.ok) {
        // handle not found nicely
        if (res.status === 404) {
          Alert.alert(
            "Not found",
            "This barcode was not found in our global database yet.\n\nTry another product or use Photo scan."
          );
          return;
        }
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const json = JSON.parse(text);

      // count scan usage only on success
      await consumeScan();

      // Convert barcode response -> same UI structure
      // Your backend returns per_100g; we show as 100g item
      const kcal = num(json?.per_100g?.kcal);
      const protein = num(json?.per_100g?.protein_g);
      const carbs = num(json?.per_100g?.carbs_g);
      const fat = num(json?.per_100g?.fat_g);

      const itemName = json?.name || "Barcode product";
      const brand = json?.brand ? ` (${json.brand})` : "";

      const scan = {
        source: "barcode",
        barcode,
        total_kcal: kcal,
        totals: { protein_g: protein, carbs_g: carbs, fat_g: fat },
        items: [
          {
            name: `${itemName}${brand}`,
            grams: 100,
            confidence: 1,
            kcal,
            macros: { protein_g: protein, carbs_g: carbs, fat_g: fat },
          },
        ],
      };

      setResult(scan);
      await addToHistory(scan);
    } catch (err) {
      Alert.alert("Barcode error", err.message);
    } finally {
      setLoading(false);
    }
  };

  const onBarcodeScanned = (event) => {
    // expo-camera barcode event shape varies
    const code = event?.data || event?.rawValue || "";
    if (!code) return;

    // debounce so it doesn't spam
    if (code === lastScanned) return;
    setLastScanned(code);

    // allow rescan after short time
    setTimeout(() => setLastScanned(""), 2000);

    barcodeLookup(code);
  };

  // ---- auth actions (optional) ----
  const signUp = async () => {
    if (!supabase) {
      Alert.alert("Supabase not configured", "Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }
    try {
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Check your email", "Confirm your email, then log in.");
    } catch (e) {
      Alert.alert("Sign up error", e.message);
    }
  };

  const signIn = async () => {
    if (!supabase) {
      Alert.alert("Supabase not configured", "Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY");
      return;
    }
    try {
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
    } catch (e) {
      Alert.alert("Sign out error", e.message);
    }
  };

  // ---- UI helpers ----
  const display = result || selected;

  const usageText = useMemo(() => {
    if (planId === "free") {
      return `Free usage: ${usage.freeTotalCount || 0}/${plan.monthlyLimit} total`;
    }
    const daily = plan.dailyLimit != null ? `${usage.dayCount || 0}/${plan.dailyLimit} today` : "—";
    const monthly = `${usage.monthCount || 0}/${plan.monthlyLimit} this month`;
    return `Usage: ${daily} • ${monthly}`;
  }, [planId, usage, plan]);

  const setPlan = async (id) => {
    setPlanId(id);
    await saveJSON(PLAN_KEY, { planId: id });
    Alert.alert("Plan selected", `${planById(id).name} (${planById(id).price})\n\n(For now this is UI-only; payments next.)`);
  };

  // ---- render ----
  if (authLoading) {
    return (
      <View style={[styles.center, { backgroundColor: "#000" }]}>
        <ActivityIndicator color="white" />
        <Text style={{ color: "white", marginTop: 10 }}>Loading…</Text>
      </View>
    );
  }

  // If you want to force auth, change to: if (HAS_SUPABASE && !session) show auth
  if (HAS_SUPABASE && !session) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: "#000" }}>
        <KeyboardAvoidingView
          style={{ flex: 1, padding: 18, justifyContent: "center" }}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <Text style={{ color: "white", fontSize: 26, fontWeight: "900" }}>Kcal Scan</Text>
          <Text style={{ color: "#aaa", marginTop: 6 }}>Login to sync across devices</Text>

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

          <Text style={{ color: "#777", marginTop: 12, fontSize: 12 }}>
            Supabase auth is optional. If you want no-login app, remove HAS_SUPABASE gating.
          </Text>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // Camera permissions
  if (!permission) return <View style={{ flex: 1, backgroundColor: "#000" }} />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={{ color: "white", marginBottom: 10 }}>Camera permission required</Text>
        <TouchableOpacity onPress={requestPermission} style={styles.btn}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={signOut} style={[styles.btn, { marginTop: 12 }]}>
          <Text style={styles.btnText}>Sign out</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <SafeAreaView style={{ backgroundColor: "#000" }}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Kcal Scan ✅ NEW UI</Text>
          <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Sign out</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* CAMERA */}
      <View style={styles.cameraWrap}>
        <CameraView
          style={styles.camera}
          ref={cameraRef}
          barcodeScannerSettings={{
            // common barcode types, camera decides what it supports
            barcodeTypes: [
              "ean13",
              "ean8",
              "upc_a",
              "upc_e",
              "code128",
              "code39",
              "qr",
              "pdf417",
              "datamatrix",
            ],
          }}
          onBarcodeScanned={mode === "barcode" ? onBarcodeScanned : undefined}
        />
      </View>

      {/* PANEL */}
      <View style={styles.panel}>
        <Text style={{ color: serverOk ? "#2ecc71" : "#ff5a5f" }}>
          Server {serverOk ? "OK ✅" : "DOWN ❌"} • {usageText}
        </Text>

        {/* MODE TOGGLE */}
        <View style={[styles.row, { marginTop: 10 }]}>
          <TouchableOpacity
            onPress={() => setMode("photo")}
            style={[styles.btn, mode === "photo" ? styles.primary : null]}
          >
            <Text style={styles.btnText}>📷 Photo</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setMode("barcode")}
            style={[styles.btn, mode === "barcode" ? styles.primary : null]}
          >
            <Text style={styles.btnText}>🏷️ Barcode</Text>
          </TouchableOpacity>
        </View>

        {/* PHOTO MODE */}
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
          </>
        ) : (
          <>
            {/* BARCODE MODE */}
            <View style={{ marginTop: 10, backgroundColor: "#141414", padding: 10, borderRadius: 12 }}>
              <Text style={{ color: "#ccc", fontWeight: "700" }}>Barcode Mode</Text>
              <Text style={{ color: "#888", marginTop: 4, fontSize: 12 }}>
                Point camera at barcode. It will auto-scan.
              </Text>

              <View style={[styles.row, { marginTop: 10 }]}>
                <TextInput
                  value={barcodeText}
                  onChangeText={setBarcodeText}
                  placeholder="Enter barcode manually (EAN/UPC)"
                  placeholderTextColor="#666"
                  style={[styles.input, { flex: 2 }]}
                  keyboardType="number-pad"
                />
                <TouchableOpacity
                  onPress={() => barcodeLookup(barcodeText)}
                  style={[styles.btn, styles.primary, { flex: 1 }]}
                  disabled={loading}
                >
                  <Text style={styles.btnText}>Lookup</Text>
                </TouchableOpacity>
              </View>
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
              {result ? "Latest Result" : "From History"}{" "}
              {display?.source === "barcode" ? "• Barcode" : ""}
            </Text>

            <Text style={styles.kcalText}>Total: {round1(display.total_kcal)} kcal</Text>

            <Text style={styles.macros}>
              Protein {round1(display?.totals?.protein_g)}g • Carbs {round1(display?.totals?.carbs_g)}g • Fat{" "}
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

        {/* PLAN SELECTOR (UI only for now) */}
        <View style={{ marginTop: 14 }}>
          <Text style={{ color: "white", fontSize: 16, fontWeight: "900" }}>Plan</Text>
          <Text style={{ color: "#888", marginTop: 4, fontSize: 12 }}>
            (Payments next) Select a plan to test limits locally.
          </Text>

          <ScrollView horizontal style={{ marginTop: 10 }} showsHorizontalScrollIndicator={false}>
            {PLANS.map((p) => {
              const active = p.id === planId;
              return (
                <TouchableOpacity
                  key={p.id}
                  onPress={() => setPlan(p.id)}
                  style={[
                    styles.planCard,
                    active ? { borderColor: "#007AFF" } : null,
                  ]}
                >
                  <Text style={{ color: "white", fontWeight: "900" }}>{p.name}</Text>
                  <Text style={{ color: "#ccc", marginTop: 2 }}>{p.price}</Text>
                  <Text style={{ color: "#888", marginTop: 6, fontSize: 12 }}>
                    {p.id === "free"
                      ? p.note
                      : `${p.monthlyLimit}/mo • ${p.dailyLimit}/day`}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

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
            <Text style={{ color: "#aaa", marginTop: 8 }}>No scans yet. Do a scan.</Text>
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
                    {item.source === "barcode" ? "• 🏷️" : ""}
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
    justifyContent: "center",
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
  },

  planCard: {
    width: 180,
    marginRight: 10,
    backgroundColor: "#141414",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "#222",
  },

  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
});

