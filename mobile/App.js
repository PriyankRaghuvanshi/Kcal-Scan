import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  Alert,
  ActivityIndicator,
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
import * as ImageManipulator from "expo-image-manipulator";
import AsyncStorage from "@react-native-async-storage/async-storage";

/**
 * CalorieClick.ai - TestFlight ready single-file App.js
 *
 * Fixes:
 * - nowISO reference error (replaced with nowISO() function)
 * - Refresh clears screen and pulls latest /usage
 * - History saves locally PER USER (isolated), and resets on logout/user switch
 * - Photo preview cleared when switching users (no bleed)
 * - Camera modal capture button clearly visible
 * - Barcode scanner via camera + manual entry
 * - Coaching insights render ONLY for Pro/Infinite (when backend returns `coaching`)
 */

const API_BASE = "https://kcal-scan-production.up.railway.app";

const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];
const planAtLeast = (plan, required) => {
  const p = (plan || "free").toLowerCase();
  const r = (required || "free").toLowerCase();
  return PLAN_ORDER.indexOf(p) >= PLAN_ORDER.indexOf(r);
};

const nowISO = () => new Date().toISOString();

const storageKeys = {
  userId: "ccai:user_id",
  history: (uid) => `ccai:history:${uid}`,
};

async function safeJson(res) {
  const txt = await res.text();
  try {
    return { ok: true, data: JSON.parse(txt) };
  } catch (e) {
    return { ok: false, raw: txt };
  }
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}
function round1(n) {
  if (n === null || n === undefined) return 0;
  return Math.round(Number(n) * 10) / 10;
}

export default function App() {
  // ---------- Auth / user ----------
  const [userId, setUserId] = useState("");
  const [userInput, setUserInput] = useState("");
  const [loadingUser, setLoadingUser] = useState(true);

  // ---------- Usage / plan ----------
  const [plan, setPlan] = useState("free");
  const [remainingDay, setRemainingDay] = useState(0);
  const [remainingMonth, setRemainingMonth] = useState(0);

  // ---------- Photo / analyze ----------
  const [photoUri, setPhotoUri] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);

  // ---------- Barcode ----------
  const [barcodeManual, setBarcodeManual] = useState("");
  const [barcodeResult, setBarcodeResult] = useState(null);
  const [barcodeLoading, setBarcodeLoading] = useState(false);

  // ---------- History ----------
  const [history, setHistory] = useState([]);

  // ---------- Camera modals ----------
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraMode, setCameraMode] = useState("photo"); // "photo" | "barcode"
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef(null);
  const [barcodeCooldown, setBarcodeCooldown] = useState(false);

  // ---------- Refresh ----------
  const [refreshing, setRefreshing] = useState(false);

  const coachingEnabled = useMemo(() => planAtLeast(plan, "pro"), [plan]);
  const barcodeEnabled = useMemo(() => planAtLeast(plan, "elite"), [plan]);

  // ---------- Init ----------
  useEffect(() => {
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(storageKeys.userId);
        if (saved) {
          setUserId(saved);
          setUserInput(saved);
        }
      } finally {
        setLoadingUser(false);
      }
    })();
  }, []);

  // Load user-specific state when user changes
  useEffect(() => {
    if (!userId) return;
    (async () => {
      await AsyncStorage.setItem(storageKeys.userId, userId);
      await loadUsage(userId);
      await loadHistory(userId);
      // Clear volatile UI state to avoid bleed between users
      clearForNextScan({ keepHistory: true }); // keep history; loaded per-user
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // ---------- API ----------
  async function loadUsage(uid = userId) {
    if (!uid) return;
    try {
      const res = await fetch(`${API_BASE}/usage?user_id=${encodeURIComponent(uid)}`);
      const sj = await safeJson(res);
      if (!sj.ok) throw new Error(`Bad JSON: ${String(sj.raw).slice(0, 120)}`);
      const u = sj.data;
      setPlan((u.plan || "free").toLowerCase());
      setRemainingDay(Number(u.remaining_day || 0));
      setRemainingMonth(Number(u.remaining_month || 0));
    } catch (e) {
      console.log("loadUsage error:", e?.message || e);
      Alert.alert("Usage error", String(e?.message || e));
    }
  }

  async function loadHistory(uid = userId) {
    try {
      const raw = await AsyncStorage.getItem(storageKeys.history(uid));
      const arr = raw ? JSON.parse(raw) : [];
      setHistory(Array.isArray(arr) ? arr : []);
    } catch {
      setHistory([]);
    }
  }

  async function saveHistory(uid = userId, items) {
    try {
      await AsyncStorage.setItem(storageKeys.history(uid), JSON.stringify(items || []));
    } catch (e) {
      console.log("saveHistory error:", e?.message || e);
    }
  }

  async function callPlanSync(entitlement, mode) {
    const uid = userId;
    if (!uid) return;
    try {
      const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(uid)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entitlement, mode }),
      });
      const sj = await safeJson(res);
      if (!sj.ok) throw new Error(`Bad JSON: ${String(sj.raw).slice(0, 120)}`);
      if (sj.data?.ok) {
        await loadUsage(uid);
      } else {
        throw new Error("plan/sync failed");
      }
    } catch (e) {
      Alert.alert("Plan sync failed", String(e?.message || e));
    }
  }

  // ---------- Actions ----------
  function clearForNextScan({ keepHistory = true } = {}) {
    setPhotoUri(null);
    setAnalysis(null);
    setBarcodeResult(null);
    setBarcodeManual("");
    setAnalyzing(false);
    setBarcodeLoading(false);
    if (!keepHistory) setHistory([]);
  }

  async function onRefresh() {
    setRefreshing(true);
    try {
      clearForNextScan({ keepHistory: true });
      await loadUsage();
      await loadHistory();
    } finally {
      setRefreshing(false);
    }
  }

  async function logout() {
    await AsyncStorage.removeItem(storageKeys.userId);
    setUserId("");
    setUserInput("");
    setPlan("free");
    setRemainingDay(0);
    setRemainingMonth(0);
    clearForNextScan({ keepHistory: false });
  }

  async function openCamera(mode) {
    setCameraMode(mode);
    if (!permission?.granted) {
      const req = await requestPermission();
      if (!req.granted) {
        Alert.alert("Camera permission required", "Please allow camera access in Settings.");
        return;
      }
    }
    setCameraOpen(true);
  }

  async function takePhoto() {
    try {
      if (!cameraRef.current) return;
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        base64: false,
        skipProcessing: true,
      });
      if (!photo?.uri) return;
      // Reduce size to avoid huge uploads (faster + fewer crashes)
      const manipulated = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1024 } }],
        { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG }
      );
      setPhotoUri(manipulated.uri);
      setCameraOpen(false);
    } catch (e) {
      Alert.alert("Camera", String(e?.message || e));
    }
  }

  async function analyzePhoto() {
    if (!userId) return Alert.alert("Login required", "Enter your user id first.");
    if (!photoUri) return Alert.alert("No photo", "Open camera and take a photo first.");
    setAnalyzing(true);
    try {
      const info = await FileSystem.getInfoAsync(photoUri);
      if (!info.exists) throw new Error("Photo not found");

      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: `meal_${Date.now()}.jpg`,
        type: "image/jpeg",
      });

      const res = await fetch(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: form,
      });

      const sj = await safeJson(res);
      if (!sj.ok) {
        throw new Error(`Server returned non-JSON: ${String(sj.raw).slice(0, 140)}`);
      }
      const data = sj.data;
      setAnalysis(data);

      // Update usage from response
      if (data?.usage) {
        setPlan((data.usage.plan || plan || "free").toLowerCase());
        setRemainingDay(Number(data.usage.remaining_day || remainingDay));
        setRemainingMonth(Number(data.usage.remaining_month || remainingMonth));
      } else {
        await loadUsage();
      }

      // Save history (per-user)
      const entry = {
        id: `${Date.now()}`,
        ts: nowISO(),
        type: "photo",
        photoUri,
        total_kcal: data?.total_kcal ?? null,
        totals: data?.totals ?? null,
      };
      const next = [entry, ...(history || [])].slice(0, 50);
      setHistory(next);
      await saveHistory(userId, next);
    } catch (e) {
      Alert.alert("Analyze failed", String(e?.message || e));
      await loadUsage(); // keep UI consistent
    } finally {
      setAnalyzing(false);
    }
  }

  async function lookupBarcode(code) {
    if (!userId) return Alert.alert("Login required", "Enter your user id first.");
    if (!barcodeEnabled) return Alert.alert("Upgrade required", "Barcode scanning is Elite+.");
    const bc = String(code || "").trim();
    if (!bc) return;

    setBarcodeLoading(true);
    try {
      const res = await fetch(`${API_BASE}/barcode/${encodeURIComponent(bc)}?user_id=${encodeURIComponent(userId)}`, {
        headers: { Accept: "application/json" },
      });
      const sj = await safeJson(res);
      if (!sj.ok) throw new Error(`Server returned non-JSON: ${String(sj.raw).slice(0, 140)}`);

      const data = sj.data;
      setBarcodeResult(data);

      if (data?.usage) {
        setPlan((data.usage.plan || plan || "free").toLowerCase());
        setRemainingDay(Number(data.usage.remaining_day || remainingDay));
        setRemainingMonth(Number(data.usage.remaining_month || remainingMonth));
      } else {
        await loadUsage();
      }

      // Save history entry
      const entry = {
        id: `${Date.now()}`,
        ts: nowISO(),
        type: "barcode",
        barcode: bc,
        name: data?.name || "",
        per_100g: data?.per_100g || null,
      };
      const next = [entry, ...(history || [])].slice(0, 50);
      setHistory(next);
      await saveHistory(userId, next);

      setBarcodeManual("");
    } catch (e) {
      Alert.alert("Barcode failed", String(e?.message || e));
      await loadUsage();
    } finally {
      setBarcodeLoading(false);
    }
  }

  function onBarcodeScanned({ data }) {
    if (barcodeCooldown) return;
    setBarcodeCooldown(true);
    setTimeout(() => setBarcodeCooldown(false), 1500);

    const code = String(data || "").trim();
    if (!code) return;
    setCameraOpen(false);
    lookupBarcode(code);
  }

  async function clearHistory() {
    const next = [];
    setHistory(next);
    await saveHistory(userId, next);
  }

  // ---------- UI bits ----------
  const PlanPill = ({ label, active }) => (
    <View style={[styles.pill, active ? styles.pillActive : styles.pillIdle]}>
      <Text style={[styles.pillText, active ? styles.pillTextActive : styles.pillTextIdle]}>{label}</Text>
    </View>
  );

  const ProgressBar = ({ value, max = 100, label, sublabel }) => {
    const pct = clamp((Number(value) || 0) / (Number(max) || 1), 0, 1);
    return (
      <View style={{ marginTop: 10 }}>
        <Text style={styles.sub}>{label} {round1(value)}/{max}</Text>
        {sublabel ? <Text style={styles.muted}>{sublabel}</Text> : null}
        <View style={styles.barBg}>
          <View style={[styles.barFill, { width: `${pct * 100}%` }]} />
        </View>
      </View>
    );
  };

  function renderCoachingCard() {
    const coaching = analysis?.coaching || null;
    const locked = analysis?.locked || null;

    // Correct behavior: only show values when backend provides coaching (Pro/Infinite).
    if (!coaching) {
      return (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Coaching insights</Text>
          <View style={styles.lockedBox}>
            <Text style={styles.lockedTitle}>Locked 🔒</Text>
            <Text style={styles.muted}>
              Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.
              {"\n"}Upgrade to Pro or Infinite to unlock these insights.
            </Text>
          </View>
          {locked ? (
            <Text style={[styles.muted, { marginTop: 8 }]}>
              Required plan: {locked.required_plan || "pro"}
            </Text>
          ) : null}
        </View>
      );
    }

    const sat = coaching.satiety_score;
    const bv = coaching.protein_bv_score;
    const leu = coaching.leucine_estimate_g;
    const trig = coaching.mps_triggered;
    const thr = coaching.mps_threshold_g;
    const gl = coaching.glycemic_load?.gl;
    const glLevel = coaching.glycemic_load?.level;
    const up = coaching.ultra_processed_score;
    const lay = coaching.layman_terms || {};
    const msgs = coaching.messages || [];

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Coaching insights</Text>

        <ProgressBar
          value={sat}
          max={100}
          label="Satiety Score (how filling)"
          sublabel={lay.satiety}
        />
        <ProgressBar
          value={bv}
          max={100}
          label="Protein Bioavailability (BV)"
          sublabel={lay.protein_bv}
        />

        <View style={{ marginTop: 12 }}>
          <Text style={styles.sub}>Leucine Estimate: {round1(leu)}g {trig ? "✅" : "⚠️"}</Text>
          <Text style={styles.muted}>Threshold: {round1(thr)}g • {trig ? "Triggered" : "Not triggered"}</Text>
          {lay.leucine ? <Text style={[styles.muted, { marginTop: 4 }]}>{lay.leucine}</Text> : null}
        </View>

        <View style={{ marginTop: 12 }}>
          <Text style={styles.sub}>Glycemic Load: {round1(gl)} ({glLevel || "-"})</Text>
          {lay.glycemic_load ? <Text style={styles.muted}>{lay.glycemic_load}</Text> : null}
          <View style={styles.barBg}>
            <View style={[styles.barFill, { width: `${clamp((Number(gl) || 0) / 120, 0, 1) * 100}%` }]} />
          </View>
        </View>

        <View style={{ marginTop: 12 }}>
          <Text style={styles.sub}>Ultra-Processed Score: {round1(up)}/10</Text>
          {lay.ultra_processed ? <Text style={styles.muted}>{lay.ultra_processed}</Text> : null}
          <View style={styles.barBg}>
            <View style={[styles.barFill, { width: `${clamp((Number(up) || 0) / 10, 0, 1) * 100}%` }]} />
          </View>
        </View>

        {msgs?.length ? (
          <View style={{ marginTop: 12 }}>
            {msgs.slice(0, 6).map((m, idx) => (
              <Text key={idx} style={styles.bullet}>• {m}</Text>
            ))}
          </View>
        ) : null}
      </View>
    );
  }

  function renderBarcodeCard() {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Barcode</Text>
        <Text style={styles.muted}>Elite+ can scan barcodes to fetch macros (OpenFoodFacts).</Text>

        <TouchableOpacity
          style={[styles.primaryBtn, !barcodeEnabled && styles.btnDisabled]}
          onPress={() => openCamera("barcode")}
          disabled={!barcodeEnabled}
        >
          <Text style={styles.primaryBtnText}>Scan barcode</Text>
        </TouchableOpacity>

        <View style={styles.manualRow}>
          <TextInput
            value={barcodeManual}
            onChangeText={setBarcodeManual}
            placeholder="Enter barcode manually"
            placeholderTextColor="#666"
            style={styles.input}
            keyboardType="number-pad"
          />
          <TouchableOpacity
            style={[styles.secondaryBtn, (!barcodeEnabled || barcodeLoading) && styles.btnDisabled]}
            onPress={() => lookupBarcode(barcodeManual)}
            disabled={!barcodeEnabled || barcodeLoading}
          >
            {barcodeLoading ? <ActivityIndicator /> : <Text style={styles.secondaryBtnText}>Lookup</Text>}
          </TouchableOpacity>
        </View>

        {barcodeResult ? (
          <View style={{ marginTop: 12 }}>
            <Text style={styles.sub}>{barcodeResult.name || "Product"}</Text>
            {barcodeResult.brand ? <Text style={styles.muted}>{barcodeResult.brand}</Text> : null}
            <Text style={styles.muted}>Per 100g:</Text>
            <Text style={styles.muted}>
              {round1(barcodeResult.per_100g?.kcal)} kcal •
              P {round1(barcodeResult.per_100g?.protein_g)}g •
              C {round1(barcodeResult.per_100g?.carbs_g)}g •
              F {round1(barcodeResult.per_100g?.fat_g)}g
            </Text>
          </View>
        ) : null}
      </View>
    );
  }

  function renderHistory() {
    return (
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.cardTitle}>History (this user only)</Text>
          <TouchableOpacity style={styles.smallBtn} onPress={clearHistory}>
            <Text style={styles.smallBtnText}>Clear</Text>
          </TouchableOpacity>
        </View>

        {history?.length ? (
          history.map((h) => (
            <View key={h.id} style={styles.histRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.histTitle}>
                  {h.type === "photo" ? "📷" : "🏷️"}{" "}
                  {h.type === "photo" ? `${round1(h.total_kcal)} kcal` : (h.name || h.barcode)}
                </Text>
                <Text style={styles.muted}>{new Date(h.ts).toLocaleString()}</Text>
              </View>
              {h.type === "photo" && h.photoUri ? (
                <Image source={{ uri: h.photoUri }} style={styles.histThumb} />
              ) : null}
            </View>
          ))
        ) : (
          <Text style={styles.muted}>No history yet.</Text>
        )}
      </View>
    );
  }

  // ---------- Render ----------
  if (loadingUser) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <ActivityIndicator />
          <Text style={styles.muted}>Loading…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!userId) {
    return (
      <SafeAreaView style={styles.safe}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ flex: 1 }}
        >
          <View style={styles.header}>
            <Text style={styles.title}>CalorieClick.ai</Text>
            <Text style={styles.muted}>Enter your Supabase user_id (UUID) to continue.</Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Login</Text>
            <TextInput
              value={userInput}
              onChangeText={setUserInput}
              placeholder="user_id (UUID)"
              placeholderTextColor="#666"
              style={styles.inputFull}
              autoCapitalize="none"
            />
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={() => {
                const v = (userInput || "").trim();
                if (!v) return;
                setUserId(v);
              }}
            >
              <Text style={styles.primaryBtnText}>Continue</Text>
            </TouchableOpacity>
          </View>

          <View style={{ padding: 16 }}>
            <Text style={styles.muted}>
              Tip: You can copy the user_id from your Supabase auth user record. In TestFlight you’ll eventually replace this with real auth.
            </Text>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.title}>CalorieClick.ai</Text>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <PlanPill label={`Plan: ${plan}`} active />
              <PlanPill label={`Day: ${remainingDay}`} />
              <PlanPill label={`Month: ${remainingMonth}`} />
            </View>
          </View>

          <View style={{ gap: 8 }}>
            <TouchableOpacity style={styles.smallBtn} onPress={onRefresh} disabled={refreshing}>
              <Text style={styles.smallBtnText}>{refreshing ? "Refreshing…" : "Refresh"}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.smallBtn} onPress={logout}>
              <Text style={styles.smallBtnText}>Logout</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Photo */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Meal scan</Text>

          {photoUri ? (
            <Image source={{ uri: photoUri }} style={styles.preview} />
          ) : (
            <View style={[styles.preview, styles.previewEmpty]}>
              <Text style={styles.muted}>No photo yet</Text>
            </View>
          )}

          <View style={styles.row}>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => openCamera("photo")}>
              <Text style={styles.primaryBtnText}>Open Camera</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.primaryBtn, (!photoUri || analyzing) && styles.btnDisabled]}
              onPress={analyzePhoto}
              disabled={!photoUri || analyzing}
            >
              {analyzing ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Analyze</Text>}
            </TouchableOpacity>

            <TouchableOpacity style={styles.secondaryBtn} onPress={() => clearForNextScan({ keepHistory: true })}>
              <Text style={styles.secondaryBtnText}>Clear</Text>
            </TouchableOpacity>
          </View>

          {analysis ? (
            <View style={{ marginTop: 12 }}>
              <Text style={styles.big}>Total: {round1(analysis.total_kcal)} kcal</Text>
              <Text style={styles.muted}>
                Protein {round1(analysis.totals?.protein_g)}g • Carbs {round1(analysis.totals?.carbs_g)}g • Fat{" "}
                {round1(analysis.totals?.fat_g)}g
              </Text>

              <Text style={[styles.sub, { marginTop: 10 }]}>Items</Text>
              {(analysis.items || []).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.itemName}>{it.name}</Text>
                  <Text style={styles.itemMeta}>
                    {round1(it.grams)}g • {round1(it.kcal)} kcal
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        {/* Coaching */}
        {renderCoachingCard()}

        {/* Barcode */}
        {renderBarcodeCard()}

        {/* Upgrade / Restore (TestFlight / dev controls) */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Upgrade</Text>
          <Text style={styles.muted}>
            TestFlight/dev: use these buttons to simulate purchases (calls backend /plan/sync).
          </Text>

          <View style={styles.rowWrap}>
            {["elite", "advanced", "pro", "infinite"].map((p) => (
              <TouchableOpacity
                key={p}
                style={[styles.planBtn, plan === p && styles.planBtnActive]}
                onPress={() => callPlanSync(p, "purchase")}
              >
                <Text style={styles.planBtnText}>{p.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity style={styles.secondaryBtn} onPress={() => callPlanSync(plan, "restore")}>
            <Text style={styles.secondaryBtnText}>Restore Purchases</Text>
          </TouchableOpacity>

          <Text style={[styles.muted, { marginTop: 8 }]}>
            Restore updates plan without refilling scan counters.
          </Text>
        </View>

        {/* History */}
        {renderHistory()}
      </ScrollView>

      {/* Camera Modal */}
      <Modal visible={cameraOpen} animationType="slide" onRequestClose={() => setCameraOpen(false)}>
        <SafeAreaView style={styles.modalSafe}>
          <View style={styles.modalTop}>
            <TouchableOpacity style={styles.smallBtn} onPress={() => setCameraOpen(false)}>
              <Text style={styles.smallBtnText}>Close</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>
              {cameraMode === "photo" ? "Take a photo" : "Scan barcode"}
            </Text>
            <View style={{ width: 70 }} />
          </View>

          <CameraView
            ref={cameraRef}
            style={styles.camera}
            facing="back"
            barcodeScannerSettings={
              cameraMode === "barcode"
                ? { barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"] }
                : undefined
            }
            onBarcodeScanned={cameraMode === "barcode" ? onBarcodeScanned : undefined}
          />

          <View style={styles.modalBottom}>
            {cameraMode === "photo" ? (
              <TouchableOpacity style={styles.captureBtn} onPress={takePhoto}>
                <Text style={styles.captureText}>Capture</Text>
              </TouchableOpacity>
            ) : (
              <Text style={styles.mutedCenter}>
                Point camera at barcode. It will scan automatically.
              </Text>
            )}
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#000" },
  header: { padding: 16 },
  title: { color: "#fff", fontSize: 28, fontWeight: "900" },
  big: { color: "#fff", fontSize: 20, fontWeight: "800" },
  sub: { color: "#fff", fontSize: 14, fontWeight: "800" },
  muted: { color: "#9aa0a6", marginTop: 4, lineHeight: 18 },
  mutedCenter: { color: "#9aa0a6", textAlign: "center" },

  center: { flex: 1, alignItems: "center", justifyContent: "center" },

  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12 },
  row: { flexDirection: "row", gap: 10, marginTop: 12, flexWrap: "wrap" },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 12 },

  card: {
    backgroundColor: "#0e0e10",
    borderRadius: 18,
    padding: 14,
    marginTop: 14,
    borderWidth: 1,
    borderColor: "#1b1b1f",
  },
  cardTitle: { color: "#fff", fontSize: 16, fontWeight: "900" },

  pill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  pillIdle: { borderColor: "#2a2a2f", backgroundColor: "#121216" },
  pillActive: { borderColor: "#2a6df5", backgroundColor: "#0b1b3d" },
  pillText: { fontSize: 12, fontWeight: "800" },
  pillTextIdle: { color: "#9aa0a6" },
  pillTextActive: { color: "#dbe6ff" },

  preview: { width: "100%", height: 220, borderRadius: 16, marginTop: 12, backgroundColor: "#111" },
  previewEmpty: { alignItems: "center", justifyContent: "center" },

  primaryBtn: {
    backgroundColor: "#2a6df5",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 14,
    minWidth: 120,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryBtnText: { color: "#fff", fontWeight: "900" },

  secondaryBtn: {
    backgroundColor: "#151515",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 14,
    minWidth: 110,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#222",
  },
  secondaryBtnText: { color: "#fff", fontWeight: "800" },

  btnDisabled: { opacity: 0.45 },

  smallBtn: {
    backgroundColor: "#151515",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#222",
    alignSelf: "flex-end",
  },
  smallBtnText: { color: "#fff", fontWeight: "800" },

  itemRow: { marginTop: 10, borderTopWidth: 1, borderTopColor: "#1b1b1f", paddingTop: 10 },
  itemName: { color: "#fff", fontWeight: "800" },
  itemMeta: { color: "#9aa0a6", marginTop: 2 },

  barBg: { height: 10, backgroundColor: "#141414", borderRadius: 999, marginTop: 8, overflow: "hidden", borderWidth: 1, borderColor: "#232323" },
  barFill: { height: 10, backgroundColor: "#2a6df5", borderRadius: 999 },

  lockedBox: { marginTop: 12, padding: 12, borderRadius: 14, backgroundColor: "#121216", borderWidth: 1, borderColor: "#222" },
  lockedTitle: { color: "#fff", fontWeight: "900" },

  bullet: { color: "#dbe6ff", marginTop: 6, lineHeight: 20 },

  manualRow: { marginTop: 10, flexDirection: "row", gap: 10, alignItems: "center" },
  input: {
    flex: 1,
    backgroundColor: "#0a0a0a",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: "#fff",
    borderWidth: 1,
    borderColor: "#222",
  },
  inputFull: {
    width: "100%",
    backgroundColor: "#0a0a0a",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 14,
    color: "#fff",
    borderWidth: 1,
    borderColor: "#222",
    marginTop: 10,
  },

  planBtn: {
    backgroundColor: "#151515",
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#222",
  },
  planBtnActive: { borderColor: "#2a6df5" },
  planBtnText: { color: "#fff", fontWeight: "900" },

  histRow: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: "#1b1b1f", flexDirection: "row", gap: 12, alignItems: "center" },
  histThumb: { width: 56, height: 56, borderRadius: 12, backgroundColor: "#111" },
  histTitle: { color: "#fff", fontWeight: "900" },

  modalSafe: { flex: 1, backgroundColor: "#000" },
  modalTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12 },
  modalTitle: { color: "#fff", fontWeight: "900", fontSize: 16 },
  camera: { flex: 1 },
  modalBottom: { padding: 12, backgroundColor: "#000", paddingBottom: 24 },
  captureBtn: {
    backgroundColor: "#2a6df5",
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  captureText: { color: "#fff", fontWeight: "900", fontSize: 16 },
};
