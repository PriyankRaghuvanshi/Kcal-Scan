// mobile/App.js
import React, { useEffect, useMemo, useState } from "react";
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

import * as ImagePicker from "expo-image-picker";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";
import Purchases from "react-native-purchases";

// ===================== CONFIG =====================
const API_BASE =
  (process.env.EXPO_PUBLIC_API_BASE || "").trim() ||
  "https://kcal-scan-production.up.railway.app";

const HISTORY_KEY = "kcal_scan_history_v4";
const MAX_HISTORY = 50;

// Supabase
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY || "";
const HAS_SUPABASE = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
const supabase = HAS_SUPABASE ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

// RevenueCat (from env)
const RC_IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY || "";
const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "";
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";
const ENTITLEMENTS = (process.env.EXPO_PUBLIC_RC_ENTITLEMENTS || "elite,advanced,pro,infinite")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

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
  return {
    protein_g: num(obj.protein_g ?? obj.protein ?? 0),
    carbs_g: num(obj.carbs_g ?? obj.carbs ?? 0),
    fat_g: num(obj.fat_g ?? obj.fat ?? 0),
  };
}
function normalizeAnalyzeResponse(json) {
  const rawItems = Array.isArray(json?.items) ? json.items : [];
  const items = rawItems.map((it) => ({
    name: it?.name ?? "item",
    grams: num(it?.grams ?? 0),
    kcal: num(it?.kcal ?? 0),
    confidence: typeof it?.confidence === "number" ? it.confidence : undefined,
    macros: pickMacros(it?.macros ?? {}),
  }));

  let totals = pickMacros(json?.totals ?? {});
  if (totals.protein_g === 0 && totals.carbs_g === 0 && totals.fat_g === 0 && items.length) {
    totals = items.reduce(
      (acc, it) => ({
        protein_g: acc.protein_g + num(it?.macros?.protein_g),
        carbs_g: acc.carbs_g + num(it?.macros?.carbs_g),
        fat_g: acc.fat_g + num(it?.macros?.fat_g),
      }),
      { protein_g: 0, carbs_g: 0, fat_g: 0 }
    );
  }

  const total_kcal =
    num(json?.total_kcal) > 0 ? num(json.total_kcal) : items.reduce((s, it) => s + num(it.kcal), 0);

  return { ...json, total_kcal, totals, items };
}
function normalizeBarcodeResponse(json) {
  const per = json?.per_100g || {};
  const name = json?.name || "Unknown product";
  const brand = json?.brand || null;

  return {
    source: "barcode",
    barcode: json?.barcode,
    total_kcal: num(per.kcal),
    totals: {
      protein_g: num(per.protein_g),
      carbs_g: num(per.carbs_g),
      fat_g: num(per.fat_g),
    },
    items: [
      {
        name: brand ? `${name} (${brand})` : name,
        grams: 100,
        kcal: num(per.kcal),
        confidence: 1,
        macros: {
          protein_g: num(per.protein_g),
          carbs_g: num(per.carbs_g),
          fat_g: num(per.fat_g),
        },
      },
    ],
  };
}
function getActiveEntitlement(customerInfo) {
  const active = customerInfo?.entitlements?.active || {};
  for (const k of ENTITLEMENTS) if (active[k]) return k;
  return "free";
}

// ===================== APP =====================
export default function App() {
  // Auth
  const [authLoading, setAuthLoading] = useState(true);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [serverOk, setServerOk] = useState(false);
  const [loading, setLoading] = useState(false);

  const [photoUri, setPhotoUri] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);

  // Barcode manual
  const [barcodeText, setBarcodeText] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [manualBarcode, setManualBarcode] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualBrand, setManualBrand] = useState("");
  const [manualKcal, setManualKcal] = useState("");
  const [manualP, setManualP] = useState("");
  const [manualC, setManualC] = useState("");
  const [manualF, setManualF] = useState("");

  // RevenueCat
  const [rcReady, setRcReady] = useState(false);
  const [offering, setOffering] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [plan, setPlan] = useState("free");

  // Usage
  const [usage, setUsage] = useState(null);

  const userId = session?.user?.id || null;
  const display = result || selected;

  // -------------------- HISTORY --------------------
  const loadHistory = async () => {
    try {
      const raw = await AsyncStorage.getItem(HISTORY_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) setHistory(parsed);
    } catch {}
  };

  const saveHistory = async (items) => {
    try {
      await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(items));
    } catch {}
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

  // -------------------- SERVER HEALTH --------------------
  const checkServer = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const json = await res.json();
      setServerOk(json?.status === "ok");
    } catch {
      setServerOk(false);
    }
  };

  // -------------------- AUTH --------------------
  useEffect(() => {
    if (!HAS_SUPABASE) {
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

    return () => sub?.subscription?.unsubscribe?.();
  }, []);

  const signUp = async () => {
    try {
      if (!supabase) throw new Error("Supabase not configured.");
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Check your email", "Confirm your email, then log in.");
    } catch (e) {
      Alert.alert("Sign up error", e.message);
    }
  };

  const signIn = async () => {
    try {
      if (!supabase) throw new Error("Supabase not configured.");
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
      setOffering(null);
      setRcReady(false);
      setUsage(null);
      setPlan("free");
      setCustomerInfo(null);
    } catch (e) {
      Alert.alert("Sign out error", e.message);
    }
  };

  // -------------------- USAGE (BACKEND) --------------------
  const fetchUsage = async () => {
    if (!userId) return;
    try {
      const res = await fetch(`${API_BASE}/usage`, { headers: backendHeaders(userId) });
      const json = await res.json();
      if (!res.ok) return;
      setUsage(json);
    } catch {}
  };

  const syncPlanToBackend = async (entitlement) => {
    if (!userId) return;
    try {
      await fetch(`${API_BASE}/plan/sync`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ entitlement }),
      });
      await fetchUsage();
    } catch {}
  };

  // -------------------- REVENUECAT --------------------
  const loadOfferings = async () => {
    const offers = await Purchases.getOfferings();
    const main = offers?.all?.[OFFERING_ID] || offers?.current || null;
    setOffering(main);
    setRcReady(Boolean(main));
    return main;
  };

  useEffect(() => {
    (async () => {
      try {
        setRcReady(false);
        setOffering(null);
        setCustomerInfo(null);
        setPlan("free");

        if (!userId) return;

        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
        if (!apiKey) {
          await fetchUsage();
          return;
        }

        Purchases.setDebugLogsEnabled(true);
        await Purchases.configure({ apiKey, appUserID: userId });

        const info = await Purchases.getCustomerInfo();
        setCustomerInfo(info);

        const active = getActiveEntitlement(info);
        setPlan(active);
        await syncPlanToBackend(active);

        await loadOfferings();
        await fetchUsage();
      } catch (e) {
        await fetchUsage();
      }
    })();
  }, [userId]);

  const buy = async (packageId) => {
    try {
      if (!rcReady || !offering) throw new Error("Offerings not loaded. Tap Refresh.");
      const pkg =
        (offering.availablePackages || []).find((p) => p.identifier === packageId) || null;
      if (!pkg) throw new Error(`Package not found: ${packageId}`);

      setLoading(true);
      const { customerInfo: info } = await Purchases.purchasePackage(pkg);
      setCustomerInfo(info);

      const active = getActiveEntitlement(info);
      setPlan(active);
      await syncPlanToBackend(active);

      Alert.alert("Subscribed", `Plan: ${active}`);
    } catch (e) {
      const msg = String(e?.message || e);
      if (msg.toLowerCase().includes("cancel")) return;
      Alert.alert("Purchase failed", msg);
    } finally {
      setLoading(false);
    }
  };

  const restore = async () => {
    try {
      setLoading(true);
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);

      const active = getActiveEntitlement(info);
      setPlan(active);
      await syncPlanToBackend(active);

      Alert.alert("Restored", `Plan: ${active}`);
    } catch (e) {
      Alert.alert("Restore failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  const refreshOfferings = async () => {
    try {
      setLoading(true);
      const main = await loadOfferings();
      Alert.alert(main ? "Offerings loaded ✅" : "No offerings yet", main ? "You can purchase now." : "Check RC setup.");
    } catch (e) {
      Alert.alert("Refresh failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  // -------------------- INIT --------------------
  useEffect(() => {
    checkServer();
    loadHistory();
  }, []);

  useEffect(() => {
    if (userId) fetchUsage();
  }, [userId]);

  // -------------------- PHOTO PICK / CAMERA --------------------
  const ensureCameraPermission = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission required", "Camera permission is required to take a photo.");
      return false;
    }
    return true;
  };

  const takePhoto = async () => {
    const ok = await ensureCameraPermission();
    if (!ok) return;

    const res = await ImagePicker.launchCameraAsync({
      quality: 0.7,
      allowsEditing: false,
    });

    if (res.canceled) return;
    const uri = res.assets?.[0]?.uri;
    if (!uri) return;

    setPhotoUri(uri);
    setResult(null);
    setSelected(null);
  };

  const doAnalyze = async () => {
    if (!photoUri) return Alert.alert("Take a photo first");
    if (!userId) return Alert.alert("Login required", "Please login to use scans (plan limits).");

    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const form = new FormData();
      form.append("file", { uri: photoUri, name: "food.jpg", type: "image/jpeg" });

      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: backendHeaders(userId),
        body: form,
      });

      const text = await res.text();
      let json;
      try {
        json = JSON.parse(text);
      } catch {
        throw new Error(text || `HTTP ${res.status}`);
      }

      if (!res.ok) {
        if (res.status === 402) {
          Alert.alert("Limit reached", "No scans left for your plan.");
          await fetchUsage();
          return;
        }
        throw new Error(json?.detail?.error || json?.detail || text);
      }

      const normalized = normalizeAnalyzeResponse(json);
      const enriched = { ...normalized, photoUri, source: "photo" };

      setResult(enriched);
      await addToHistory(enriched);
      await fetchUsage();
    } catch (e) {
      Alert.alert("Analyze failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  // -------------------- BARCODE (MANUAL INPUT) --------------------
  const barcodeLookup = async () => {
    const clean = String(barcodeText || "").replace(/[^\d]/g, "");
    if (!clean) return Alert.alert("Enter barcode", "Please type a numeric barcode.");
    if (!userId) return Alert.alert("Login required", "Please login to use barcode scans.");

    setLoading(true);
    setResult(null);
    setSelected(null);

    try {
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(clean)}`, {
        headers: backendHeaders(userId),
      });

      const text = await res.text();
      let json = null;
      try {
        json = JSON.parse(text);
      } catch {
        json = { raw: text };
      }

      if (!res.ok) {
        if (res.status === 402) {
          Alert.alert("Limit reached", "No scans left for your plan.");
          await fetchUsage();
          return;
        }
        if (res.status === 404) {
          // open manual add modal
          setManualBarcode(clean);
          setManualName("");
          setManualBrand("");
          setManualKcal("");
          setManualP("");
          setManualC("");
          setManualF("");
          setManualOpen(true);
          return;
        }
        throw new Error(json?.detail?.error || json?.detail || text || "Barcode lookup failed");
      }

      const normalized = normalizeBarcodeResponse(json);
      const enriched = { ...normalized, source: "barcode", barcode: clean };

      setResult(enriched);
      await addToHistory(enriched);
      await fetchUsage();
    } catch (e) {
      Alert.alert("Barcode lookup failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  const submitManualAdd = async () => {
    if (!userId) return;

    const payload = {
      barcode: manualBarcode,
      name: manualName,
      brand: manualBrand || null,
      kcal_per_100g: Number(manualKcal),
      protein_g_per_100g: Number(manualP || 0),
      carbs_g_per_100g: Number(manualC || 0),
      fat_g_per_100g: Number(manualF || 0),
    };

    if (!payload.barcode || !payload.name || !payload.kcal_per_100g || payload.kcal_per_100g <= 0) {
      Alert.alert("Missing fields", "Barcode, Name, and kcal/100g are required.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/barcode/manual`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });

      const text = await res.text();
      let json = null;
      try {
        json = JSON.parse(text);
      } catch {
        json = { raw: text };
      }

      if (!res.ok) {
        if (res.status === 402) {
          Alert.alert("Limit reached", "No scans left for your plan.");
          await fetchUsage();
          return;
        }
        throw new Error(json?.detail?.error || json?.detail || text || "Manual add failed");
      }

      const stored = {
        source: "barcode",
        barcode: payload.barcode,
        total_kcal: payload.kcal_per_100g,
        totals: {
          protein_g: payload.protein_g_per_100g,
          carbs_g: payload.carbs_g_per_100g,
          fat_g: payload.fat_g_per_100g,
        },
        items: [
          {
            name: payload.brand ? `${payload.name} (${payload.brand})` : payload.name,
            grams: 100,
            confidence: 1,
            kcal: payload.kcal_per_100g,
            macros: {
              protein_g: payload.protein_g_per_100g,
              carbs_g: payload.carbs_g_per_100g,
              fat_g: payload.fat_g_per_100g,
            },
          },
        ],
      };

      setResult(stored);
      await addToHistory(stored);

      setManualOpen(false);
      await fetchUsage();
      Alert.alert("Saved", "Added product and saved to history.");
    } catch (e) {
      Alert.alert("Manual add failed", e.message);
    } finally {
      setLoading(false);
    }
  };

  // ===================== RENDER =====================
  if (authLoading) {
    return (
      <View style={[styles.center, { backgroundColor: "#000" }]}>
        <ActivityIndicator color="white" />
        <Text style={{ color: "white", marginTop: 10 }}>Loading…</Text>
      </View>
    );
  }

  if (!HAS_SUPABASE) {
    return (
      <View style={[styles.center, { backgroundColor: "#000" }]}>
        <Text style={{ color: "white", fontSize: 18, fontWeight: "900" }}>Missing Supabase config</Text>
        <Text style={{ color: "#aaa", marginTop: 10, textAlign: "center" }}>
          Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY in mobile/.env and restart Expo.
        </Text>
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
          <Text style={{ color: "white", fontSize: 28, fontWeight: "900" }}>CalorieClick.ai</Text>
          <Text style={{ color: "#aaa", marginTop: 6 }}>Login to use scans + subscriptions</Text>

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

  const purchaseDisabled = loading || !rcReady || !offering;

  return (
    <View style={styles.container}>
      <SafeAreaView style={{ backgroundColor: "#000" }}>
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>CalorieClick.ai</Text>
            <Text style={styles.subHeader}>
              Plan: <Text style={{ fontWeight: "900" }}>{plan}</Text> {rcReady ? "✅" : "⚠️"}
            </Text>
          </View>

          <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Sign out</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* MAIN PANEL */}
      <View style={styles.panel}>
        <Text style={{ color: serverOk ? "#2ecc71" : "#ff5a5f" }}>
          Server {serverOk ? "OK ✅" : "DOWN ❌"}
        </Text>

        {usage ? (
          <Text style={{ color: "#cfcfcf", marginTop: 6 }}>
            Remaining today: {usage.remaining_day} • Remaining month: {usage.remaining_month}
          </Text>
        ) : (
          <Text style={{ color: "#777", marginTop: 6 }}>Fetching usage…</Text>
        )}

        {/* PHOTO */}
        <View style={[styles.box, { marginTop: 12 }]}>
          <Text style={styles.boxTitle}>📸 Photo Analyze</Text>

          {photoUri ? <Image source={{ uri: photoUri }} style={styles.preview} /> : null}

          <View style={styles.row}>
            <TouchableOpacity onPress={takePhoto} style={styles.btn} disabled={loading}>
              <Text style={styles.btnText}>Take Photo</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={doAnalyze} style={[styles.btn, styles.primary]} disabled={loading}>
              <Text style={styles.btnText}>{loading ? "Analyzing..." : "Analyze"}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* BARCODE (MANUAL) */}
        <View style={[styles.box, { marginTop: 12 }]}>
          <Text style={styles.boxTitle}>🏷️ Barcode Lookup (Manual)</Text>

          <TextInput
            value={barcodeText}
            onChangeText={setBarcodeText}
            placeholder="Enter barcode (numbers only)"
            placeholderTextColor="#666"
            keyboardType="numeric"
            style={styles.input}
          />

          <View style={styles.row}>
            <TouchableOpacity onPress={barcodeLookup} style={[styles.btn, styles.primary]} disabled={loading}>
              <Text style={styles.btnText}>{loading ? "Looking..." : "Lookup"}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setBarcodeText("")} style={styles.btn} disabled={loading}>
              <Text style={styles.btnText}>Clear</Text>
            </TouchableOpacity>
          </View>

          <Text style={{ color: "#777", marginTop: 6, fontSize: 12 }}>
            If not found, you can add nutrition per 100g.
          </Text>
        </View>

        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color="white" />
            <Text style={{ color: "white", marginLeft: 10 }}>Working…</Text>
          </View>
        ) : null}

        {/* RESULT */}
        {display ? (
          <View style={styles.resultBox}>
            <Text style={styles.resultTitle}>
              {result ? "Latest Result" : "From History"} • {display.source || "photo"}
              {display.barcode ? ` • ${display.barcode}` : ""}
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
                    {round1(it.kcal)} kcal • P {round1(it?.macros?.protein_g)}g • C {round1(it?.macros?.carbs_g)}g • F{" "}
                    {round1(it?.macros?.fat_g)}g{" "}
                    {typeof it.confidence === "number" ? `• conf ${round1(it.confidence)}` : ""}
                  </Text>
                </View>
              ))}
            </ScrollView>
          </View>
        ) : null}

        {/* SUBSCRIPTIONS */}
        <View style={[styles.row, { marginTop: 14, alignItems: "center" }]}>
          <Text style={styles.historyTitle}>Upgrade</Text>

          <TouchableOpacity onPress={refreshOfferings} style={styles.smallBtn} disabled={loading}>
            <Text style={styles.smallBtnText}>Refresh</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={restore} style={styles.smallBtn} disabled={loading}>
            <Text style={styles.smallBtnText}>Restore</Text>
          </TouchableOpacity>
        </View>

        <Text style={{ color: "#888", marginTop: 6 }}>
          RevenueCat Offering: <Text style={{ fontWeight: "900" }}>{OFFERING_ID}</Text>
        </Text>

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={() => buy("elite")} disabled={purchaseDisabled}>
            <Text style={styles.btnText}>Elite</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => buy("advanced")} disabled={purchaseDisabled}>
            <Text style={styles.btnText}>Advanced</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={() => buy("pro")} disabled={purchaseDisabled}>
            <Text style={styles.btnText}>Pro</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => buy("infinite")} disabled={purchaseDisabled}>
            <Text style={styles.btnText}>Infinite</Text>
          </TouchableOpacity>
        </View>

        {!rcReady ? (
          <Text style={{ color: "#ffcc00", marginTop: 8, fontSize: 12 }}>
            ⚠️ Offerings not loaded yet. Tap Refresh.
          </Text>
        ) : (
          <Text style={{ color: "#777", marginTop: 8, fontSize: 12 }}>
            ✅ Auto-renews monthly • Cancel anytime
          </Text>
        )}

        {/* HISTORY */}
        <View style={[styles.row, { marginTop: 16, alignItems: "center" }]}>
          <Text style={styles.historyTitle}>History</Text>
          <TouchableOpacity onPress={clearHistory} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Clear</Text>
          </TouchableOpacity>
        </View>

        <FlatList
          data={history}
          keyExtractor={(item) => item.id}
          style={{ maxHeight: 260, marginTop: 8 }}
          ListEmptyComponent={<Text style={{ color: "#aaa", marginTop: 8 }}>No scans yet.</Text>}
          renderItem={({ item }) => {
            const dtt = new Date(item.createdAt);
            const label = `${dtt.toLocaleDateString()} ${dtt.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}`;

            return (
              <TouchableOpacity
                onPress={() => {
                  setSelected(item);
                  setResult(null);
                }}
                style={[styles.historyRow, selected?.id === item.id ? styles.historyRowActive : null]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyMain}>
                    {round1(item.total_kcal)} kcal{item.source ? ` • ${item.source}` : ""}{item.barcode ? ` • ${item.barcode}` : ""}
                  </Text>
                  <Text style={styles.historySub}>
                    P {round1(item?.totals?.protein_g)}g • C {round1(item?.totals?.carbs_g)}g • F {round1(item?.totals?.fat_g)}g
                  </Text>
                  <Text style={styles.historySub2}>{label}</Text>
                </View>

                <TouchableOpacity onPress={() => deleteHistoryItem(item.id)} style={styles.deleteBtn}>
                  <Text style={{ color: "white", fontWeight: "700" }}>Del</Text>
                </TouchableOpacity>
              </TouchableOpacity>
            );
          }}
        />
      </View>

      {/* MANUAL ADD MODAL */}
      <Modal visible={manualOpen} transparent animationType="fade">
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Barcode not found</Text>
            <Text style={styles.modalSub}>
              Add nutrition per 100g for: <Text style={{ fontWeight: "900" }}>{manualBarcode}</Text>
            </Text>

            <TextInput
              value={manualName}
              onChangeText={setManualName}
              placeholder="Product name (required)"
              placeholderTextColor="#777"
              style={styles.modalInput}
            />
            <TextInput
              value={manualBrand}
              onChangeText={setManualBrand}
              placeholder="Brand (optional)"
              placeholderTextColor="#777"
              style={styles.modalInput}
            />

            <View style={{ flexDirection: "row", gap: 8 }}>
              <TextInput
                value={manualKcal}
                onChangeText={setManualKcal}
                placeholder="kcal/100g *"
                placeholderTextColor="#777"
                keyboardType="numeric"
                style={[styles.modalInput, { flex: 1 }]}
              />
              <TextInput
                value={manualP}
                onChangeText={setManualP}
                placeholder="P g"
                placeholderTextColor="#777"
                keyboardType="numeric"
                style={[styles.modalInput, { flex: 1 }]}
              />
            </View>

            <View style={{ flexDirection: "row", gap: 8 }}>
              <TextInput
                value={manualC}
                onChangeText={setManualC}
                placeholder="C g"
                placeholderTextColor="#777"
                keyboardType="numeric"
                style={[styles.modalInput, { flex: 1 }]}
              />
              <TextInput
                value={manualF}
                onChangeText={setManualF}
                placeholder="F g"
                placeholderTextColor="#777"
                keyboardType="numeric"
                style={[styles.modalInput, { flex: 1 }]}
              />
            </View>

            <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
              <TouchableOpacity style={styles.btn} onPress={() => setManualOpen(false)} disabled={loading}>
                <Text style={styles.btnText}>Close</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.btn, styles.primary]} onPress={submitManualAdd} disabled={loading}>
                <Text style={styles.btnText}>{loading ? "Saving..." : "Save"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ===================== STYLES =====================
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
  subHeader: { color: "#aaa", marginTop: 2, fontSize: 12 },

  panel: { flex: 1, padding: 14, backgroundColor: "#0f0f0f" },

  box: {
    backgroundColor: "#141414",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1f1f1f",
    padding: 12,
  },
  boxTitle: { color: "white", fontWeight: "900", marginBottom: 10 },

  preview: { height: 180, borderRadius: 12, marginTop: 10, marginBottom: 10 },

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
    marginLeft: 8,
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
  historyMain: { color: "white", fontWeight: "900", fontSize: 14 },
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
    marginTop: 8,
  },

  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },

  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "center",
    padding: 18,
  },
  modalCard: {
    backgroundColor: "#121212",
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: "#222",
  },
  modalTitle: { color: "white", fontSize: 18, fontWeight: "900" },
  modalSub: { color: "#aaa", marginTop: 6, marginBottom: 10 },
  modalInput: {
    backgroundColor: "#0b0b0b",
    borderWidth: 1,
    borderColor: "#222",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "white",
    marginTop: 8,
  },
});

