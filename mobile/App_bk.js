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
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error(
    "Missing Supabase env vars. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY in mobile/.env then restart Expo."
  );
}

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
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
    total_kcal && total_kcal > 0 ? total_kcal : items.reduce((s, it) => s + num(it.kcal), 0);

  return {
    ...json,
    total_kcal: computedKcal,
    totals: computedTotals,
    items,
  };
}

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // Auth UI
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [photoUri, setPhotoUri] = useState(null);
  const [loading, setLoading] = useState(false);
  const [serverOk, setServerOk] = useState(false);

  const [result, setResult] = useState(null); // latest scan result
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null); // selected history item

  useEffect(() => {
    // Supabase session init + listener
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

  useEffect(() => {
    checkServer();
    loadHistory();
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

      const enriched = { ...normalized, photoUri };
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
    } catch (e) {
      Alert.alert("Sign out error", e.message);
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

  // Auth screen
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
            Login to save scans across devices
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

          <Text style={{ color: "#777", marginTop: 12, fontSize: 12 }}>
            Note: If email confirmation link opens localhost, we’ll fix Supabase redirect
            URLs next (it can still login on device).
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

  // IMPORTANT: show latest result first (prevents “stuck on cucumber”)
  const display = result || selected;

  return (
    <View style={styles.container}>
      {/* HEADER */}
      <SafeAreaView style={{ backgroundColor: "#000" }}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Kcal Scan</Text>
          <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Sign out</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* CAMERA */}
      <View style={styles.cameraWrap}>
        <CameraView style={styles.camera} ref={cameraRef} />
      </View>

      {/* PANEL */}
      <View style={styles.panel}>
        <Text style={{ color: serverOk ? "#2ecc71" : "#ff5a5f" }}>
          Server {serverOk ? "OK ✅" : "DOWN ❌"}
        </Text>

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
            <Text style={styles.btnText}>
              {loading ? "Analyzing..." : "⚡ Snap & Analyze"}
            </Text>
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color="white" />
            <Text style={{ color: "white", marginLeft: 10 }}>
              Estimating with AI + USDA…
            </Text>
          </View>
        ) : null}

        {/* RESULT + MACROS */}
        {display ? (
          <View style={styles.resultBox}>
            <Text style={styles.resultTitle}>
              {result ? "Latest Result" : "From History"}
            </Text>

            <Text style={styles.kcalText}>Total: {round1(display.total_kcal)} kcal</Text>

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
                    {round1(it?.macros?.carbs_g)}g • F {round1(it?.macros?.fat_g)}g{" "}
                    {typeof it.confidence === "number"
                      ? `• conf ${round1(it.confidence)}`
                      : ""}
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
              No scans yet. Do a Snap & Analyze.
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
                  setResult(null); // show history explicitly
                }}
                style={[
                  styles.historyRow,
                  selected?.id === item.id ? styles.historyRowActive : null,
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyMain}>{round1(item.total_kcal)} kcal</Text>
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

  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
});

