// App.js
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  ActivityIndicator,
  Image,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

import AsyncStorage from "@react-native-async-storage/async-storage";
import * as ImagePicker from "expo-image-picker";

import { createClient } from "@supabase/supabase-js";

// -------------------- CONFIG --------------------
const API_BASE = "https://kcal-scan-production.up.railway.app";

// ✅ Put your Supabase project values here (same as before)
const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY";

// Plans order must match backend
const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];

// Feature gates
const isPlanAtLeast = (current, required) => {
  const c = (current || "free").toLowerCase();
  const r = (required || "free").toLowerCase();
  return PLAN_ORDER.indexOf(c) >= PLAN_ORDER.indexOf(r);
};

const FEATURES = {
  barcode: "elite", // elite+
  coaching: "pro",  // pro+ (satiety + protein BV + MPS)
};

// -------------------- UI HELPERS --------------------
function Pill({ children }) {
  return (
    <View style={styles.pill}>
      <Text style={styles.pillText}>{children}</Text>
    </View>
  );
}

function PrimaryButton({ title, onPress, disabled }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      style={[styles.primaryBtn, disabled && { opacity: 0.5 }]}
    >
      <Text style={styles.primaryBtnText}>{title}</Text>
    </TouchableOpacity>
  );
}

function SecondaryButton({ title, onPress, disabled }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled}
      style={[styles.secondaryBtn, disabled && { opacity: 0.5 }]}
    >
      <Text style={styles.secondaryBtnText}>{title}</Text>
    </TouchableOpacity>
  );
}

function ProgressBar({ label, value, max = 100, rightText }) {
  const pct = Math.max(0, Math.min(1, (value || 0) / max));
  return (
    <View style={{ marginTop: 12 }}>
      <View style={styles.rowBetween}>
        <Text style={styles.sectionTitle}>{label}</Text>
        <Text style={styles.muted}>{rightText ?? `${Math.round(value || 0)}/${max}`}</Text>
      </View>
      <View style={styles.barTrack}>
        <View style={[styles.barFill, { width: `${pct * 100}%` }]} />
      </View>
    </View>
  );
}

// -------------------- LOGIN SCREEN --------------------
function LoginScreen({
  email,
  setEmail,
  password,
  setPassword,
  onLogin,
  onSignup,
  loading,
}) {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.loginWrap}>
        <Text style={styles.brandTitle}>CalorieClick.ai</Text>
        <Text style={styles.muted}>Login to sync plan + usage</Text>

        <View style={{ height: 18 }} />

        <Text style={styles.inputLabel}>Email</Text>
        <TextInput
          value={email}
          onChangeText={setEmail}
          placeholder="you@email.com"
          placeholderTextColor="#666"
          autoCapitalize="none"
          keyboardType="email-address"
          style={styles.input}
        />

        <Text style={styles.inputLabel}>Password</Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          placeholder="••••••••"
          placeholderTextColor="#666"
          secureTextEntry
          style={styles.input}
        />

        <View style={{ height: 14 }} />

        <PrimaryButton title={loading ? "Logging in..." : "Login"} onPress={onLogin} disabled={loading} />
        <View style={{ height: 10 }} />
        <SecondaryButton title={loading ? "Creating..." : "Create account"} onPress={onSignup} disabled={loading} />

        <View style={{ height: 22 }} />
        <Text style={styles.mutedSmall}>
          Tip: if you were logged in earlier, tap <Text style={{ color: "#9bbcff" }}>Logout</Text> or{" "}
          <Text style={{ color: "#9bbcff" }}>Switch account</Text> to see this screen again.
        </Text>
      </View>
    </SafeAreaView>
  );
}

// -------------------- APP --------------------
export default function App() {
  const supabase = useMemo(() => {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY || SUPABASE_URL.includes("YOUR_")) return null;

    // Persist auth in AsyncStorage (required on Expo)
    return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        storage: AsyncStorage,
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    });
  }, []);

  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  // Force-show login screen even if session exists (Switch account)
  const [forceLogin, setForceLogin] = useState(false);

  // Auth form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // App state
  const [usage, setUsage] = useState(null);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [mode, setMode] = useState("photo"); // "photo" | "barcode"
  const [photoUri, setPhotoUri] = useState(null);
  const [barcode, setBarcode] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  // history
  const [history, setHistory] = useState([]);

  const userId = session?.user?.id || null;
  const plan = (usage?.plan || "free").toLowerCase();

  const canBarcode = isPlanAtLeast(plan, FEATURES.barcode);
  const canCoaching = isPlanAtLeast(plan, FEATURES.coaching);

  // -------------------- AUTH INIT --------------------
  useEffect(() => {
    let sub;
    async function init() {
      try {
        if (!supabase) {
          setAuthLoading(false);
          return;
        }
        const { data } = await supabase.auth.getSession();
        setSession(data?.session || null);

        sub = supabase.auth.onAuthStateChange((_event, sess) => {
          setSession(sess);
        }).data.subscription;
      } catch (e) {
        setSession(null);
      } finally {
        setAuthLoading(false);
      }
    }
    init();

    return () => {
      if (sub) sub.unsubscribe();
    };
  }, [supabase]);

  // -------------------- USAGE --------------------
  async function fetchUsage() {
    if (!userId) return;
    try {
      setLoadingUsage(true);
      const r = await fetch(`${API_BASE}/usage?user_id=${encodeURIComponent(userId)}`, {
        method: "GET",
        headers: { accept: "application/json" },
      });
      const data = await r.json();
      setUsage(data);
    } catch (e) {
      console.log("usage err", e);
    } finally {
      setLoadingUsage(false);
    }
  }

  useEffect(() => {
    if (userId) fetchUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // -------------------- AUTH ACTIONS --------------------
  async function signIn() {
    if (!supabase) {
      Alert.alert("Missing Supabase config", "Please set SUPABASE_URL and SUPABASE_ANON_KEY in App.js");
      return;
    }
    if (!email || !password) return Alert.alert("Missing", "Enter email and password");
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      setForceLogin(false);
    } catch (e) {
      Alert.alert("Login failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function signUp() {
    if (!supabase) {
      Alert.alert("Missing Supabase config", "Please set SUPABASE_URL and SUPABASE_ANON_KEY in App.js");
      return;
    }
    if (!email || !password) return Alert.alert("Missing", "Enter email and password");
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Account created", "Now login (or check email if confirmations enabled).");
    } catch (e) {
      Alert.alert("Signup failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function signOut() {
    try {
      if (supabase) await supabase.auth.signOut();
    } catch {}
    setSession(null);
    setUsage(null);
    setResult(null);
    setPhotoUri(null);
    setBarcode("");
    setForceLogin(true); // show login after logout
  }

  // -------------------- IMAGE PICK / CAMERA --------------------
  async function ensureMediaPerm() {
    if (Platform.OS === "web") return true;
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") {
      Alert.alert("Permission needed", "Camera permission is required.");
      return false;
    }
    return true;
  }

  async function takePhoto() {
    const ok = await ensureMediaPerm();
    if (!ok) return;

    const res = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
    });

    if (!res.canceled && res.assets?.[0]?.uri) {
      setPhotoUri(res.assets[0].uri);
      setResult(null);
    }
  }

  async function pickImage() {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
    });
    if (!res.canceled && res.assets?.[0]?.uri) {
      setPhotoUri(res.assets[0].uri);
      setResult(null);
    }
  }

  function clearCurrent() {
    setResult(null);
    setPhotoUri(null);
    setBarcode("");
  }

  function clearHistory() {
    setHistory([]);
  }

  // -------------------- API CALLS --------------------
  async function analyzePhoto() {
    if (!photoUri) return Alert.alert("Missing photo", "Take or pick a photo first.");

    try {
      setBusy(true);

      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "photo.jpg",
        type: "image/jpeg",
      });

      const r = await fetch(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: { accept: "application/json" },
        body: form,
      });

      const data = await r.json();

      // API might return locked payload (for coaching)
      setResult(data);
      if (data?.usage) setUsage((u) => ({ ...(u || {}), ...data.usage }));

      setHistory((h) => [
        { ts: Date.now(), total_kcal: data?.total_kcal, plan: data?.usage?.plan },
        ...h,
      ]);
    } catch (e) {
      Alert.alert("Analyze failed", e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function lookupBarcode() {
    if (!barcode?.trim()) return Alert.alert("Missing barcode", "Enter a barcode first.");

    if (!canBarcode) {
      Alert.alert("Upgrade required", "Barcode scanning requires Elite or higher.");
      return;
    }

    try {
      setBusy(true);
      const r = await fetch(`${API_BASE}/barcode/${encodeURIComponent(barcode.trim())}?user_id=${encodeURIComponent(userId)}`, {
        method: "GET",
        headers: { accept: "application/json" },
      });
      const data = await r.json();
      setResult(data);
      if (data?.usage) setUsage((u) => ({ ...(u || {}), ...data.usage }));
      setHistory((h) => [{ ts: Date.now(), total_kcal: null, plan: data?.usage?.plan, barcode: barcode.trim() }, ...h]);
    } catch (e) {
      Alert.alert("Barcode failed", e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  // -------------------- DERIVED: coaching metrics --------------------
  function computeCoachingFromResult(res) {
    // Backend sends these (when pro+) as:
    // res.coaching = { satiety_score, protein_bv_score, bioavailable_protein_g, bv, leucine_g, leucine_threshold_g, mps_hit, glycemic_risk, nova_score }
    const c = res?.coaching || null;
    if (!c) return null;
    return c;
  }

  const coaching = computeCoachingFromResult(result);

  // -------------------- RENDER CHOICE: LOGIN vs APP --------------------
  if (authLoading) {
    return (
      <SafeAreaView style={styles.safeCenter}>
        <ActivityIndicator />
        <Text style={styles.muted}>(loading)</Text>
      </SafeAreaView>
    );
  }

  // No supabase configured -> show a warning but still allow app (optional).
  if (!supabase) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loginWrap}>
          <Text style={styles.brandTitle}>CalorieClick.ai</Text>
          <Text style={styles.muted}>
            Supabase login is not configured in this App.js. Add SUPABASE_URL and SUPABASE_ANON_KEY.
          </Text>
          <View style={{ height: 12 }} />
          <Text style={styles.mutedSmall}>
            After that, you’ll get the login screen + proper user_id syncing to backend usage.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!session || forceLogin) {
    return (
      <LoginScreen
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        onLogin={signIn}
        onSignup={signUp}
        loading={authLoading}
      />
    );
  }

  // -------------------- MAIN APP UI --------------------
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        {/* Header */}
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.brandTitle}>CalorieClick.ai</Text>
            <Text style={styles.muted}>
              Plan: <Text style={styles.bold}>{plan}</Text> · Remaining:{" "}
              <Text style={styles.bold}>
                {usage?.remaining_month ?? "—"}
              </Text>
            </Text>
          </View>

          <View style={{ flexDirection: "row", gap: 10 }}>
            <TouchableOpacity style={styles.headerBtn} onPress={() => Alert.alert("Upgrade", "Hook this to RevenueCat paywall")}>
              <Text style={styles.headerBtnText}>Upgrade</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.headerBtn} onPress={signOut}>
              <Text style={styles.headerBtnText}>Logout</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.headerBtnAlt} onPress={() => setForceLogin(true)}>
              <Text style={styles.headerBtnText}>Switch</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Mode Tabs */}
        <View style={styles.tabs}>
          <TouchableOpacity
            style={[styles.tab, mode === "photo" && styles.tabActive]}
            onPress={() => {
              setMode("photo");
              setResult(null);
            }}
          >
            <Text style={[styles.tabText, mode === "photo" && styles.tabTextActive]}>Photo</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.tab, mode === "barcode" && styles.tabActive]}
            onPress={() => {
              setMode("barcode");
              setResult(null);
            }}
          >
            <Text style={[styles.tabText, mode === "barcode" && styles.tabTextActive]}>Barcode</Text>
          </TouchableOpacity>
        </View>

        {/* Controls */}
        {mode === "photo" ? (
          <View style={styles.actionsRow}>
            <PrimaryButton title="Take Photo" onPress={takePhoto} disabled={busy} />
            <PrimaryButton title="Analyze" onPress={analyzePhoto} disabled={busy || !photoUri} />
          </View>
        ) : (
          <View style={styles.barcodeRow}>
            <TextInput
              value={barcode}
              onChangeText={setBarcode}
              placeholder="Enter barcode"
              placeholderTextColor="#666"
              style={styles.input}
            />
            <PrimaryButton title={canBarcode ? "Lookup" : "Elite+"} onPress={lookupBarcode} disabled={busy || !canBarcode} />
          </View>
        )}

        <TouchableOpacity style={styles.clearBtn} onPress={clearCurrent}>
          <Text style={styles.clearBtnText}>Clear (Next Scan)</Text>
        </TouchableOpacity>

        {/* Preview image */}
        {!!photoUri && (
          <View style={styles.previewWrap}>
            <Image source={{ uri: photoUri }} style={styles.previewImg} />
          </View>
        )}

        {/* Usage row */}
        <View style={styles.usageRow}>
          <Pill>{loadingUsage ? "Loading usage..." : `Day: ${usage?.remaining_day ?? "—"} | Month: ${usage?.remaining_month ?? "—"}`}</Pill>
          <TouchableOpacity onPress={fetchUsage} style={styles.refreshBtn}>
            <Text style={styles.refreshText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        {/* RESULT CARD */}
        {result && (
          <View style={styles.card}>
            {/* PHOTO RESULT */}
            {result.source === "photo" && (
              <>
                <Text style={styles.totalKcal}>Total: {result.total_kcal} kcal</Text>
                <Text style={styles.muted}>
                  P {result?.totals?.protein_g}g · C {result?.totals?.carbs_g}g · F {result?.totals?.fat_g}g
                </Text>

                {/* ✅ Coaching unlocked (pro+) */}
                {canCoaching && coaching && (
                  <>
                    <ProgressBar label="Satiety Index" value={coaching.satiety_score} max={100} />
                    <ProgressBar label="Protein Bioavailability" value={coaching.protein_bv_score} max={100} />
                    <View style={{ marginTop: 12 }}>
                      <View style={styles.rowBetween}>
                        <Text style={styles.sectionTitle}>MPS (Leucine)</Text>
                        <Text style={styles.muted}>
                          {Number(coaching.leucine_g || 0).toFixed(2)}g{" "}
                          {coaching.mps_hit ? "✅" : "❌"}
                        </Text>
                      </View>
                      <Text style={styles.mutedSmall}>
                        Threshold: {Number(coaching.leucine_threshold_g || 2.5).toFixed(1)}g ·{" "}
                        {coaching.mps_hit ? "Hit ✅" : "Not yet"}
                      </Text>
                    </View>

                    {!!coaching.bioavailable_protein_g && (
                      <Text style={styles.mutedSmall}>
                        Est. bioavailable protein: {Number(coaching.bioavailable_protein_g).toFixed(1)}g (BV ~{Math.round(coaching.bv || 0)})
                      </Text>
                    )}

                    {/* Optional fields */}
                    {(coaching.glycemic_risk || coaching.nova_score) && (
                      <View style={{ marginTop: 10 }}>
                        {!!coaching.glycemic_risk && (
                          <Text style={styles.mutedSmall}>Glycemic risk: {String(coaching.glycemic_risk)}</Text>
                        )}
                        {!!coaching.nova_score && (
                          <Text style={styles.mutedSmall}>Ultra-processed score (NOVA): {String(coaching.nova_score)}</Text>
                        )}
                      </View>
                    )}
                  </>
                )}

                {/* 🔒 Locked message for free/elite/advanced */}
                {!canCoaching && (
                  <View style={styles.lockedCard}>
                    <Text style={styles.lockedTitle}>🔓 Unlock Satiety + Protein BV + MPS</Text>
                    <Text style={styles.lockedSub}>Upgrade to Pro (or Infinite) to see coaching insights.</Text>
                  </View>
                )}

                <View style={{ marginTop: 10 }}>
                  {(result.items || []).map((it, idx) => (
                    <View key={`${it.name}-${idx}`} style={styles.itemRow}>
                      <Text style={styles.itemName}>{it.name}</Text>
                      <Text style={styles.itemKcal}>{it.kcal} kcal</Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            {/* BARCODE RESULT */}
            {result.source === "barcode" && (
              <>
                <View style={styles.rowBetween}>
                  <Text style={styles.totalKcal}>{result.name}</Text>
                  <Text style={styles.muted}>{result.barcode}</Text>
                </View>
                <Text style={styles.muted}>{result.brand || ""}</Text>

                <View style={{ marginTop: 10 }}>
                  <Text style={styles.muted}>Per 100g</Text>
                  <Text style={styles.muted}>
                    {result?.per_100g?.kcal} kcal · P {result?.per_100g?.protein_g}g · C {result?.per_100g?.carbs_g}g · F {result?.per_100g?.fat_g}g
                  </Text>
                </View>
              </>
            )}

            {/* Locked response from API */}
            {result.locked && (
              <View style={[styles.lockedCard, { marginTop: 12 }]}>
                <Text style={styles.lockedTitle}>
                  🔒 Locked: {result.locked.feature}
                </Text>
                <Text style={styles.lockedSub}>
                  Required plan: {result.locked.required_plan}
                </Text>
              </View>
            )}
          </View>
        )}

        {/* History */}
        <View style={styles.historyHeader}>
          <Text style={styles.hTitle}>History</Text>
          <TouchableOpacity style={styles.headerBtn} onPress={clearHistory}>
            <Text style={styles.headerBtnText}>Clear History</Text>
          </TouchableOpacity>
        </View>

        {history.map((h, idx) => (
          <View key={`${h.ts}-${idx}`} style={styles.historyRow}>
            <Text style={styles.hRowText}>
              {h.total_kcal ? `${h.total_kcal} kcal` : `barcode: ${h.barcode || "-"}`}
            </Text>
            <Text style={styles.mutedSmall}>{new Date(h.ts).toLocaleString()}</Text>
          </View>
        ))}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// -------------------- STYLES --------------------
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0b0c10" },
  safeCenter: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#0b0c10" },

  container: { padding: 16, paddingBottom: 40 },

  brandTitle: { color: "white", fontSize: 28, fontWeight: "800" },
  bold: { fontWeight: "800", color: "white" },
  muted: { color: "#a5a6aa", marginTop: 4 },
  mutedSmall: { color: "#8d8f95", marginTop: 6, fontSize: 12 },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  headerBtn: {
    backgroundColor: "#1d1f27",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 14,
  },
  headerBtnAlt: {
    backgroundColor: "#14151a",
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#242633",
  },
  headerBtnText: { color: "white", fontWeight: "700" },

  tabs: {
    flexDirection: "row",
    marginTop: 14,
    backgroundColor: "#14151a",
    borderRadius: 18,
    padding: 6,
    gap: 6,
  },
  tab: { flex: 1, paddingVertical: 12, borderRadius: 14, alignItems: "center" },
  tabActive: { backgroundColor: "#2a4cff" },
  tabText: { color: "#a5a6aa", fontWeight: "700" },
  tabTextActive: { color: "white" },

  actionsRow: { flexDirection: "row", gap: 12, marginTop: 12 },
  barcodeRow: { flexDirection: "row", gap: 12, marginTop: 12, alignItems: "center" },

  primaryBtn: {
    flex: 1,
    backgroundColor: "#2a4cff",
    paddingVertical: 16,
    borderRadius: 18,
    alignItems: "center",
  },
  primaryBtnText: { color: "white", fontWeight: "800", fontSize: 16 },

  secondaryBtn: {
    backgroundColor: "#14151a",
    paddingVertical: 14,
    borderRadius: 18,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#242633",
  },
  secondaryBtnText: { color: "white", fontWeight: "800" },

  clearBtn: {
    marginTop: 12,
    backgroundColor: "#1d1f27",
    paddingVertical: 14,
    borderRadius: 18,
    alignItems: "center",
  },
  clearBtnText: { color: "#d0d2d7", fontWeight: "700" },

  previewWrap: {
    marginTop: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  previewImg: { width: 220, height: 220, borderRadius: 22 },

  usageRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 12 },
  pill: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#14151a",
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#242633",
  },
  pillText: { color: "#cfd2da", fontWeight: "700" },
  refreshBtn: { paddingHorizontal: 10, paddingVertical: 6 },
  refreshText: { color: "#9bbcff", fontWeight: "700" },

  card: {
    marginTop: 14,
    backgroundColor: "#12131a",
    borderRadius: 22,
    padding: 16,
    borderWidth: 1,
    borderColor: "#242633",
  },
  totalKcal: { color: "white", fontSize: 22, fontWeight: "900" },

  sectionTitle: { color: "white", fontWeight: "800" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },

  barTrack: {
    marginTop: 8,
    height: 12,
    borderRadius: 999,
    backgroundColor: "#1f2230",
    overflow: "hidden",
  },
  barFill: {
    height: 12,
    borderRadius: 999,
    backgroundColor: "#2a4cff",
  },

  itemRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 8 },
  itemName: { color: "white", fontWeight: "700" },
  itemKcal: { color: "#a5a6aa", fontWeight: "700" },

  lockedCard: {
    marginTop: 14,
    backgroundColor: "#0f1015",
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: "#2b2f40",
  },
  lockedTitle: { color: "white", fontWeight: "900" },
  lockedSub: { color: "#a5a6aa", marginTop: 6, fontSize: 12 },

  historyHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 16 },
  hTitle: { color: "white", fontSize: 18, fontWeight: "900" },
  historyRow: {
    marginTop: 10,
    backgroundColor: "#12131a",
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: "#242633",
  },
  hRowText: { color: "white", fontWeight: "800" },

  inputLabel: { color: "#cfd2da", fontWeight: "700", marginTop: 8 },
  input: {
    flex: 1,
    marginTop: 6,
    backgroundColor: "#0f1015",
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "white",
    borderWidth: 1,
    borderColor: "#242633",
  },

  loginWrap: { padding: 18, marginTop: 24 },
});

