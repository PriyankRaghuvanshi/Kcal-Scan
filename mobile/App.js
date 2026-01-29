import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  ActivityIndicator,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Platform,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Purchases from "react-native-purchases";
import { createClient } from "@supabase/supabase-js";

// ===================== ENV =====================
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
const API_BASE = process.env.EXPO_PUBLIC_API_BASE;
const RC_IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY;
const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY;
const RC_OFFERING = process.env.EXPO_PUBLIC_RC_OFFERING || "main";

const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
const PLAN_RANK = { free: 0, elite: 1, advanced: 2, pro: 3, infinite: 4 };

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ===================== HELPERS =====================
function planAtLeast(current, required) {
  const c = PLAN_RANK[String(current || "free").toLowerCase()] ?? 0;
  const r = PLAN_RANK[String(required || "free").toLowerCase()] ?? 0;
  return c >= r;
}

function pickBestActiveEntitlement(customerInfo) {
  const active = customerInfo?.entitlements?.active || {};
  let best = "free";
  let bestRank = 0;
  for (const k of Object.keys(active)) {
    const key = String(k || "").toLowerCase();
    const rank = PLAN_RANK[key];
    if (rank !== undefined && rank > bestRank) {
      best = key;
      bestRank = rank;
    }
  }
  return best;
}

async function safeJson(res) {
  const txt = await res.text();
  try {
    return JSON.parse(txt);
  } catch {
    return { _raw: txt };
  }
}

function backendHeaders(userId, extra = {}) {
  return {
    Accept: "application/json",
    ...(userId ? { "X-User-Id": userId } : {}),
    ...extra,
  };
}

// ===================== UI COMPONENTS =====================
function Btn({ title, onPress, kind = "primary", disabled = false }) {
  return (
    <TouchableOpacity
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.btn,
        kind === "secondary" && styles.btnSecondary,
        disabled && { opacity: 0.55 },
      ]}
    >
      <Text style={styles.btnText}>{title}</Text>
    </TouchableOpacity>
  );
}

function Pill({ text, tone = "neutral" }) {
  return (
    <View
      style={[
        styles.pill,
        tone === "good" && styles.pillGood,
        tone === "warn" && styles.pillWarn,
      ]}
    >
      <Text style={styles.pillText}>{text}</Text>
    </View>
  );
}

// ===================== APP =====================
export default function App() {
  const [session, setSession] = useState(null);
  const userId = session?.user?.id || null;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [usage, setUsage] = useState(null);
  const [activePlan, setActivePlan] = useState("free");

  const [loading, setLoading] = useState(false);
  const [planMsg, setPlanMsg] = useState("");

  const [barcode, setBarcode] = useState("");
  const [result, setResult] = useState(null);

  const [history, setHistory] = useState([]);

  const historyKey = useMemo(
    () => (userId ? `kcal_history_${userId}` : "kcal_history_anon"),
    [userId]
  );

  // ---------- Supabase session ----------
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data?.session || null));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // ---------- RevenueCat init ----------
  useEffect(() => {
    (async () => {
      try {
        const apiKey = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
        if (!apiKey) return;
        await Purchases.configure({ apiKey });
      } catch (e) {
        console.log("Purchases configure failed:", e?.message || e);
      }
    })();
  }, []);

  // ---------- Usage ----------
  async function fetchUsage(uid = userId) {
    if (!uid) return null;
    try {
      const res = await fetch(`${API_BASE}/usage?user_id=${encodeURIComponent(uid)}`, {
        headers: backendHeaders(uid),
      });
      const json = await safeJson(res);
      if (!res.ok) throw new Error(json?.detail || json?._raw || "usage failed");
      setUsage(json);
      if (json?.plan) setActivePlan(String(json.plan).toLowerCase());
      return json;
    } catch (e) {
      console.log("usage fetch error:", e?.message || e);
      return null;
    }
  }

  useEffect(() => {
    if (userId) fetchUsage(userId);
  }, [userId]);

  // ---------- History ----------
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(historyKey);
        const list = raw ? JSON.parse(raw) : [];
        setHistory(Array.isArray(list) ? list : []);
      } catch {
        setHistory([]);
      }
    })();
  }, [historyKey]);

  async function saveHistory(next) {
    setHistory(next);
    try {
      await AsyncStorage.setItem(historyKey, JSON.stringify(next));
    } catch {}
  }

  // ---------- Plan sync ----------
  async function syncPlanToBackend(entitlement, mode) {
    if (!userId) return null;
    try {
      const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: backendHeaders(userId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ entitlement, mode: mode || "restore" }),
      });
      const json = await safeJson(res);
      if (!res.ok) throw new Error(json?.detail || json?._raw || "plan sync failed");
      return json;
    } catch (e) {
      console.log("plan sync error:", e?.message || e);
      return null;
    }
  }

  async function restorePurchases() {
    try {
      setLoading(true);
      setPlanMsg("Restoring purchases...");
      const info = await Purchases.restorePurchases();
      const best = pickBestActiveEntitlement(info);
      await syncPlanToBackend(best, "restore"); // restore should NOT refill scans
      await fetchUsage();
      setPlanMsg(best === "free" ? "No active subscription found." : `Restored: ${best.toUpperCase()}`);
    } catch (e) {
      setPlanMsg("");
      Alert.alert("Restore failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function purchasePlan(targetPlan) {
    try {
      setLoading(true);
      setPlanMsg(`Purchasing ${String(targetPlan).toUpperCase()}...`);

      const offerings = await Purchases.getOfferings();
      const offering = offerings?.all?.[RC_OFFERING] || offerings?.current;
      if (!offering) throw new Error("No RevenueCat offering found.");

      // find package whose identifier includes the plan name
      const pkg =
        (offering.availablePackages || []).find((p) =>
          String(p?.identifier || "").toLowerCase().includes(String(targetPlan).toLowerCase())
        ) || null;

      if (!pkg) throw new Error(`No package found for plan: ${targetPlan}`);

      const { customerInfo } = await Purchases.purchasePackage(pkg);
      const best = pickBestActiveEntitlement(customerInfo);

      // IMPORTANT: only sync the plan that RevenueCat says is ACTIVE NOW.
      // For downgrades iOS may keep the higher plan until next billing cycle.
      const mode = "purchase"; // purchase can refill to plan limits (server side)
      await syncPlanToBackend(best, mode);
      await fetchUsage();

      if (best !== String(targetPlan).toLowerCase()) {
        setPlanMsg(`Plan active now: ${best.toUpperCase()} (change to ${String(targetPlan).toUpperCase()} may apply next cycle)`);
      } else {
        setPlanMsg(`Plan updated: ${best.toUpperCase()}`);
      }
    } catch (e) {
      setPlanMsg("");
      Alert.alert("Purchase failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // ---------- Auth ----------
  async function signIn() {
    try {
      setLoading(true);
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) throw error;
      setSession(data.session);
    } catch (e) {
      Alert.alert("Login failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function signUp() {
    try {
      setLoading(true);
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
      });
      if (error) throw error;
      setSession(data.session);
      Alert.alert("Account created", "You can now log in.");
    } catch (e) {
      Alert.alert("Sign up failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    setSession(null);
    setUsage(null);
    setActivePlan("free");
    setResult(null);
    setPlanMsg("");
  }

  // ---------- Analyze ----------
  async function pickAndAnalyze() {
    try {
      if (!userId) return;

      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert("Permission needed", "Please allow photo library access.");
        return;
      }

      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.9,
      });

      if (picked.canceled) return;

      const asset = picked.assets?.[0];
      if (!asset?.uri) return;

      setLoading(true);
      setResult(null);

      const form = new FormData();
      form.append("file", {
        uri: asset.uri,
        name: "photo.jpg",
        type: "image/jpeg",
      });

      const res = await fetch(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: backendHeaders(userId),
        body: form,
      });

      const json = await safeJson(res);

      if (!res.ok) {
        const msg = json?.detail?.error || json?.detail || json?._raw || "Analyze failed";
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }

      setResult(json);

      // History item (isolated per userId by key)
      const item = {
        ts: new Date().toISOString(),
        source: "photo",
        total_kcal: json?.total_kcal,
        totals: json?.totals,
        items: json?.items,
        coaching: json?.coaching,
      };
      await saveHistory([item, ...history].slice(0, 30));

      // refresh usage counters
      await fetchUsage();
    } catch (e) {
      Alert.alert("Analyze error", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // ---------- Barcode lookup (manual input) ----------
  async function lookupBarcode() {
    try {
      if (!userId) return;
      const code = String(barcode || "").trim();
      if (!code) return;

      setLoading(true);
      setResult(null);

      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(code)}?user_id=${encodeURIComponent(userId)}`, {
        headers: backendHeaders(userId),
      });

      const json = await safeJson(res);

      if (!res.ok) {
        // If backend sends upgrade_required detail
        const d = json?.detail;
        if (d?.error === "upgrade_required") {
          setResult({ locked: { feature: d.feature, required_plan: d.required_plan }, usage: json?.usage || null });
          throw new Error(`Upgrade required: ${String(d.required_plan).toUpperCase()} for ${d.feature}`);
        }
        throw new Error(json?.detail?.error || json?.detail || json?._raw || "Barcode lookup failed");
      }

      setResult(json);

      const item = {
        ts: new Date().toISOString(),
        source: "barcode",
        barcode: json?.barcode,
        name: json?.name,
        per_100g: json?.per_100g,
      };
      await saveHistory([item, ...history].slice(0, 30));
      await fetchUsage();
    } catch (e) {
      Alert.alert("Barcode", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // ---------- Screens ----------
  if (!session) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.card}>
          <Text style={styles.h1}>CalorieClick.ai</Text>
          <Text style={styles.sub}>Login to start scanning.</Text>

          <TextInput
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="Email"
            placeholderTextColor="#7c7c93"
            style={styles.input}
          />
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Password"
            placeholderTextColor="#7c7c93"
            secureTextEntry
            style={styles.input}
          />

          <Btn title={loading ? "..." : "Login"} onPress={signIn} disabled={loading} />
          <Btn title={loading ? "..." : "Create account"} kind="secondary" onPress={signUp} disabled={loading} />

          <Text style={styles.small}>
            Tip: use a simple test password (min 6 chars). Supabase will create the user id automatically.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  const plan = String(activePlan || usage?.plan || "free").toLowerCase();
  const canBarcode = planAtLeast(plan, "elite");
  const canCoaching = planAtLeast(plan, "pro");

  const coaching = result?.coaching || null;
  const locked = result?.locked || null;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>

        <View style={styles.topBar}>
          <Text style={styles.h1}>CalorieClick.ai</Text>
          <TouchableOpacity onPress={signOut} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Logout</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.h2}>Your Plan</Text>
          <View style={styles.rowWrap}>
            <Pill text={`Plan: ${String(plan).toUpperCase()}`} tone="good" />
            <Pill text={`Daily: ${usage?.remaining_day ?? "-"}`} />
            <Pill text={`Monthly: ${usage?.remaining_month ?? "-"}`} />
          </View>

          <View style={styles.rowWrap}>
            {PLAN_ORDER.filter(p => p !== "free").map((p) => (
              <TouchableOpacity
                key={p}
                style={[styles.planBtn, plan === p && styles.planBtnActive]}
                onPress={() => purchasePlan(p)}
                disabled={loading}
              >
                <Text style={styles.planBtnText}>{p.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.rowWrap}>
            <Btn title={loading ? "..." : "Restore Purchases"} kind="secondary" onPress={restorePurchases} disabled={loading} />
            <Btn title="Refresh Usage" kind="secondary" onPress={() => fetchUsage()} disabled={loading} />
          </View>

          {planMsg ? <Text style={styles.small}>{planMsg}</Text> : null}
        </View>

        <View style={styles.section}>
          <Text style={styles.h2}>Scan a Meal (photo)</Text>
          <Btn title={loading ? "Analyzing..." : "Pick Photo & Analyze"} onPress={pickAndAnalyze} disabled={loading} />
        </View>

        <View style={styles.section}>
          <Text style={styles.h2}>Barcode (Elite+)</Text>
          {!canBarcode ? (
            <Text style={styles.lockedText}>🔒 Barcode scanning is unlocked on Elite / Advanced / Pro / Infinite.</Text>
          ) : null}

          <View style={styles.row}>
            <TextInput
              value={barcode}
              onChangeText={setBarcode}
              placeholder="Enter barcode number"
              placeholderTextColor="#7c7c93"
              style={[styles.input, { flex: 1, marginTop: 0 }]}
            />
            <TouchableOpacity
              style={[styles.smallBtn, { marginLeft: 10 }]}
              onPress={lookupBarcode}
              disabled={loading || !canBarcode}
            >
              <Text style={styles.smallBtnText}>Lookup</Text>
            </TouchableOpacity>
          </View>
        </View>

        {loading ? (
          <View style={styles.centerInline}>
            <ActivityIndicator />
            <Text style={styles.small}>Working...</Text>
          </View>
        ) : null}

        {result ? (
          <View style={styles.section}>
            <Text style={styles.h2}>Result</Text>

            {/* --- Photo result --- */}
            {result?.source === "photo" ? (
              <>
                <Text style={styles.sub}>Total: {result?.total_kcal ?? "-"} kcal</Text>
                <Text style={styles.sub}>
                  Macros: P {result?.totals?.protein_g ?? "-"}g • C {result?.totals?.carbs_g ?? "-"}g • F{" "}
                  {result?.totals?.fat_g ?? "-"}g
                </Text>

                <View style={{ marginTop: 12 }}>
                  {(result?.items || []).map((it, idx) => (
                    <View key={`${it?.name}-${idx}`} style={styles.itemRow}>
                      <Text style={styles.itemName}>{it?.name}</Text>
                      <Text style={styles.itemMeta}>
                        {it?.grams}g • {it?.kcal} kcal • P {it?.macros?.protein_g}g / C {it?.macros?.carbs_g}g / F{" "}
                        {it?.macros?.fat_g}g
                      </Text>
                    </View>
                  ))}
                </View>

                {/* --- Coaching (Pro/Infinite only) --- */}
                {!coaching ? (
                  <View style={styles.lockedBox}>
                    <Text style={styles.lockedTitle}>🔒 Unlock Pro for Coaching Insights</Text>
                    <Text style={styles.lockedText}>
                      Pro + Infinite includes: Satiety, Protein BV, Leucine/MPS, Glycemic Load, Ultra‑Processed score.
                    </Text>
                  </View>
                ) : (
                  <View style={styles.coachBox}>
                    <Text style={styles.h2}>Coaching Insights (Pro+)</Text>

                    <Text style={styles.sub}>
                      Satiety Score (how filling): {round1(coaching?.satiety_score)}/100{" "}
                      <Text style={styles.dim}>({coaching?.layman_terms?.satiety || "how full you’ll feel"})</Text>
                    </Text>

                    <Text style={styles.sub}>
                      Protein BV (how much you use): {round1(coaching?.protein_bv_score)}/100{" "}
                      <Text style={styles.dim}>({coaching?.layman_terms?.protein_bv || "protein quality"})</Text>
                    </Text>

                    <Text style={styles.sub}>
                      Leucine estimate: {round1(coaching?.leucine_estimate_g)}g{" "}
                      <Text style={styles.dim}>({coaching?.layman_terms?.leucine || "muscle-building trigger"})</Text>
                    </Text>

                    <Text style={styles.sub}>
                      MPS Threshold: {round1(coaching?.mps_threshold_g)}g •{" "}
                      {coaching?.mps_triggered ? "✅ MPS triggered" : "❌ Not yet"}
                    </Text>

                    {coaching?.glycemic_load ? (
                      <Text style={styles.sub}>
                        Glycemic load: {round1(coaching?.glycemic_load?.gl)} ({coaching?.glycemic_load?.level}){" "}
                        <Text style={styles.dim}>({coaching?.layman_terms?.glycemic_load || "blood sugar spike risk"})</Text>
                      </Text>
                    ) : null}

                    {coaching?.ultra_processed_score !== undefined ? (
                      <Text style={styles.sub}>
                        Ultra‑processed score: {round1(coaching?.ultra_processed_score)}/10{" "}
                        <Text style={styles.dim}>({coaching?.layman_terms?.ultra_processed || "how processed it is"})</Text>
                      </Text>
                    ) : null}

                    {(coaching?.messages || []).length ? (
                      <View style={{ marginTop: 10 }}>
                        {(coaching.messages || []).map((m, i) => (
                          <Text key={`m-${i}`} style={styles.msgLine}>
                            • {m}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                  </View>
                )}
              </>
            ) : null}

            {/* --- Barcode result --- */}
            {result?.source === "barcode" ? (
              <>
                <Text style={styles.sub}>
                  {result?.name} {result?.brand ? `(${result.brand})` : ""}
                </Text>
                <Text style={styles.sub}>
                  Per 100g: {result?.per_100g?.kcal} kcal • P {result?.per_100g?.protein_g}g • C{" "}
                  {result?.per_100g?.carbs_g}g • F {result?.per_100g?.fat_g}g
                </Text>
              </>
            ) : null}

            {/* Locked from backend */}
            {locked ? (
              <View style={styles.lockedBox}>
                <Text style={styles.lockedTitle}>🔒 Locked feature: {locked.feature}</Text>
                <Text style={styles.lockedText}>Required plan: {String(locked.required_plan).toUpperCase()}</Text>
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={styles.section}>
          <Text style={styles.h2}>History</Text>
          <Text style={styles.small}>History is saved per user.</Text>

          {history.length === 0 ? (
            <Text style={styles.sub}>No scans yet.</Text>
          ) : (
            history.map((h, idx) => (
              <View key={`${h?.ts}-${idx}`} style={styles.historyRow}>
                <Text style={styles.historyTitle}>
                  {h?.source === "barcode" ? `Barcode: ${h?.name || h?.barcode}` : `Meal: ${h?.total_kcal || "-"} kcal`}
                </Text>
                <Text style={styles.small}>{new Date(h.ts).toLocaleString()}</Text>
              </View>
            ))
          )}

          <Btn
            title="Clear history"
            kind="secondary"
            onPress={() => saveHistory([])}
            disabled={loading}
          />
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

function round1(x) {
  const n = Number(x);
  if (Number.isFinite(n)) return Math.round(n * 10) / 10;
  return "-";
}

// ===================== STYLES =====================
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b0b0f", padding: 14 },
  centerInline: { justifyContent: "center", alignItems: "center", padding: 18 },

  card: { marginTop: 60, backgroundColor: "#15151c", borderRadius: 18, padding: 18 },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 },
  section: { marginTop: 18, backgroundColor: "#15151c", borderRadius: 18, padding: 16 },

  h1: { fontSize: 24, fontWeight: "900", color: "white" },
  h2: { fontSize: 18, fontWeight: "800", color: "white" },
  sub: { marginTop: 6, color: "#c7c7d8" },
  small: { marginTop: 8, color: "#9a9ab1", fontSize: 12 },
  dim: { color: "#9a9ab1", fontSize: 12 },

  input: {
    marginTop: 12,
    backgroundColor: "#1c1c25",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "white",
  },

  btn: { marginTop: 12, backgroundColor: "#5b7cfa", borderRadius: 14, paddingVertical: 12, alignItems: "center" },
  btnSecondary: { backgroundColor: "#303043" },
  btnText: { color: "white", fontWeight: "900" },

  smallBtn: { backgroundColor: "#1c1c25", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  smallBtnText: { color: "white", fontWeight: "800" },

  row: { flexDirection: "row", alignItems: "center", marginTop: 12 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", marginTop: 10, gap: 8 },

  planBtn: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: "#1c1c25",
    borderRadius: 12,
  },
  planBtnActive: { backgroundColor: "#2f4bdc" },
  planBtnText: { color: "white", fontWeight: "900" },

  pill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: "#1c1c25" },
  pillGood: { backgroundColor: "#1f4f2a" },
  pillWarn: { backgroundColor: "#5a3a1b" },
  pillText: { color: "white", fontWeight: "800", fontSize: 12 },

  itemRow: { marginTop: 10, padding: 10, borderRadius: 14, backgroundColor: "#1c1c25" },
  itemName: { color: "white", fontWeight: "900" },
  itemMeta: { color: "#c7c7d8", marginTop: 4 },

  lockedBox: { marginTop: 14, padding: 12, borderRadius: 14, backgroundColor: "#1c1c25" },
  lockedTitle: { color: "white", fontWeight: "900" },
  lockedText: { color: "#c7c7d8", marginTop: 6 },

  coachBox: { marginTop: 14, padding: 12, borderRadius: 14, backgroundColor: "#11111a", borderWidth: 1, borderColor: "#2a2a3a" },
  msgLine: { color: "#c7c7d8", marginTop: 6 },

  historyRow: { marginTop: 10, padding: 10, borderRadius: 14, backgroundColor: "#1c1c25" },
  historyTitle: { color: "white", fontWeight: "900" },
});
