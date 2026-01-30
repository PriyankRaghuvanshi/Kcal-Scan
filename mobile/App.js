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
import AsyncStorage from "@react-native-async-storage/async-storage";

/**
 * CalorieClick.ai — TestFlight-ready single-file app.
 * - Uses real camera (not photo library) for meal scanning
 * - Uses camera barcode scanning + manual barcode input
 * - No expo-file-system, no expo-image-manipulator (avoids build errors)
 * - Coaching insights locked to Pro+ based on backend plan
 * - History isolated per user (stored under key history_<userId>)
 * - Login uses Email+Password fields and derives a deterministic userId (no Supabase Auth required)
 */

const API_BASE = "https://kcal-scan-production.up.railway.app";
const MPS_THRESHOLD_G = 2.5;

// -------------------- small helpers --------------------
function round1(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 10) / 10;
}

function clamp01(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function planRank(plan) {
  const p = String(plan || "free").toLowerCase();
  const order = ["free", "elite", "advanced", "pro", "infinite"];
  const idx = order.indexOf(p);
  return idx === -1 ? 0 : idx;
}

// Simple deterministic "UUID-like" ID from a string (not cryptographic).
// This is purely to isolate per-user usage/history without a full auth system.
function hashToUuid(input) {
  const str = String(input || "");
  let h1 = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h1 ^= str.charCodeAt(i);
    h1 = (h1 * 0x01000193) >>> 0;
  }
  const hex = (n, len) => n.toString(16).padStart(len, "0");
  const a = hex(h1, 8);
  const b = hex((h1 ^ 0xabcdef01) >>> 0, 4);
  const c = hex((h1 ^ 0x12345678) >>> 0, 4);
  const d = hex((h1 ^ 0x0fedcba9) >>> 0, 4);
  const e = hex((h1 ^ 0x9e3779b9) >>> 0, 8) + hex((h1 ^ 0x7f4a7c15) >>> 0, 4);
  return `${a}-${b}-${c}-${d}-${e}`;
}

async function safeJson(res) {
  const text = await res.text();
  try {
    return { ok: true, json: JSON.parse(text) };
  } catch (e) {
    return { ok: false, text };
  }
}

// -------------------- UI primitives --------------------
function Pill({ label, value }) {
  return (
    <View style={styles.pill}>
      <Text style={styles.pillLabel}>{label}</Text>
      <Text style={styles.pillValue}>{value}</Text>
    </View>
  );
}

function PrimaryButton({ title, onPress, disabled }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={!!disabled}
      style={[styles.btn, disabled ? styles.btnDisabled : null]}
      activeOpacity={0.85}
    >
      <Text style={styles.btnText}>{title}</Text>
    </TouchableOpacity>
  );
}

function GhostButton({ title, onPress }) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.btnGhost} activeOpacity={0.85}>
      <Text style={styles.btnGhostText}>{title}</Text>
    </TouchableOpacity>
  );
}

function Bar({ value, max }) {
  const pct = clamp01((Number(value) || 0) / (Number(max) || 1));
  return (
    <View style={styles.barBg}>
      <View style={[styles.barFill, { width: `${pct * 100}%` }]} />
    </View>
  );
}

// -------------------- Camera modal --------------------
function CameraModal({ visible, onClose, onCaptured }) {
  const camRef = useRef(null);
  const [perm, requestPerm] = useCameraPermissions();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (visible && !perm?.granted) requestPerm();
  }, [visible, perm, requestPerm]);

  const canUse = !!perm?.granted;

  const take = async () => {
    try {
      if (!camRef.current) return;
      setBusy(true);
      const photo = await camRef.current.takePictureAsync({ quality: 0.75, skipProcessing: true });
      if (photo?.uri) onCaptured(photo.uri);
      onClose();
    } catch (e) {
      Alert.alert("Camera", String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.camWrap}>
        <View style={styles.camTopRow}>
          <GhostButton title="Close" onPress={onClose} />
          <Text style={styles.camTitle}>Take a photo</Text>
          <View style={{ width: 90 }} />
        </View>

        {!canUse ? (
          <View style={styles.centerPad}>
            <Text style={styles.muted}>Camera permission is required.</Text>
            <PrimaryButton title="Allow camera" onPress={requestPerm} />
          </View>
        ) : (
          <View style={styles.camBody}>
            <CameraView ref={camRef} style={styles.camPreview} facing="back" />
            <View style={styles.captureRow}>
              <TouchableOpacity
                onPress={take}
                disabled={busy}
                style={[styles.captureBtn, busy ? styles.btnDisabled : null]}
              >
                {busy ? <ActivityIndicator /> : <Text style={styles.captureText}>Capture</Text>}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}

// -------------------- Barcode modal --------------------
function BarcodeModal({ visible, onClose, onDetected }) {
  const [perm, requestPerm] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);

  useEffect(() => {
    if (visible) {
      setScanned(false);
      if (!perm?.granted) requestPerm();
    }
  }, [visible, perm, requestPerm]);

  const canUse = !!perm?.granted;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={styles.camWrap}>
        <View style={styles.camTopRow}>
          <GhostButton title="Close" onPress={onClose} />
          <Text style={styles.camTitle}>Scan barcode</Text>
          <View style={{ width: 90 }} />
        </View>

        {!canUse ? (
          <View style={styles.centerPad}>
            <Text style={styles.muted}>Camera permission is required.</Text>
            <PrimaryButton title="Allow camera" onPress={requestPerm} />
          </View>
        ) : (
          <View style={styles.camBody}>
            <CameraView
              style={styles.camPreview}
              facing="back"
              onBarcodeScanned={(e) => {
                if (scanned) return;
                setScanned(true);
                const code = String(e?.data || "").trim();
                if (code) onDetected(code);
                onClose();
              }}
            />
            <View style={styles.scanHintBox}>
              <Text style={styles.scanHintText}>Align the barcode inside the frame</Text>
            </View>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}

// -------------------- Main app --------------------
function AppInner() {
  // session
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [userId, setUserId] = useState(null);
  const [loggingIn, setLoggingIn] = useState(false);

  // usage
  const [plan, setPlan] = useState("free");
  const [remainingDay, setRemainingDay] = useState(0);
  const [remainingMonth, setRemainingMonth] = useState(0);

  // scan state
  const [photoUri, setPhotoUri] = useState(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState(null);

  // barcode state
  const [barcodeOpen, setBarcodeOpen] = useState(false);
  const [barcodeManual, setBarcodeManual] = useState("");
  const [barcodeResult, setBarcodeResult] = useState(null);
  const [barcodeBusy, setBarcodeBusy] = useState(false);

  // coaching
  const [coaching, setCoaching] = useState(null);
  const [locked, setLocked] = useState(null);

  // history
  const [history, setHistory] = useState([]);

  const coachingUnlocked = useMemo(() => planRank(plan) >= planRank("pro"), [plan]);

  // ---------- init ----------
  useEffect(() => {
    (async () => {
      const storedUserId = await AsyncStorage.getItem("cc_user_id");
      const storedEmail = await AsyncStorage.getItem("cc_email");
      if (storedEmail) setEmail(storedEmail);
      if (storedUserId) setUserId(storedUserId);
    })();
  }, []);

  // load usage/history when user changes
  useEffect(() => {
    if (!userId) return;
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const historyKey = useMemo(() => (userId ? `cc_history_${userId}` : null), [userId]);

  async function loadHistory() {
    if (!historyKey) return;
    const raw = await AsyncStorage.getItem(historyKey);
    if (!raw) {
      setHistory([]);
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      setHistory(Array.isArray(parsed) ? parsed : []);
    } catch {
      setHistory([]);
    }
  }

  async function saveHistory(next) {
    if (!historyKey) return;
    setHistory(next);
    await AsyncStorage.setItem(historyKey, JSON.stringify(next));
  }

  async function fetchUsage() {
    if (!userId) return;
    const res = await fetch(`${API_BASE}/usage?user_id=${encodeURIComponent(userId)}`);
    const parsed = await safeJson(res);
    if (!parsed.ok) throw new Error(`Usage not JSON: ${String(parsed.text).slice(0, 160)}`);
    const u = parsed.json;
    setPlan(String(u?.plan || "free").toLowerCase());
    setRemainingDay(Number(u?.remaining_day ?? 0));
    setRemainingMonth(Number(u?.remaining_month ?? 0));
  }

  async function refreshAll() {
    try {
      await fetchUsage();
      await loadHistory();
    } catch (e) {
      Alert.alert("Refresh failed", String(e?.message || e));
    }
  }

  function resetScreenForNextScan() {
    setPhotoUri(null);
    setResult(null);
    setCoaching(null);
    setLocked(null);
    setBarcodeResult(null);
    setBarcodeManual("");
  }

  // ---------- login/logout ----------
  async function login() {
    try {
      setLoggingIn(true);
      const em = String(email || "").trim().toLowerCase();
      const pw = String(password || "");
      if (!em || !pw) {
        Alert.alert("Login", "Enter email and password.");
        return;
      }
      const uid = hashToUuid(`${em}|${pw}`);
      await AsyncStorage.setItem("cc_user_id", uid);
      await AsyncStorage.setItem("cc_email", em);
      setUserId(uid);
      // isolate state immediately
      resetScreenForNextScan();
      setHistory([]);
    } finally {
      setLoggingIn(false);
    }
  }

  async function logout() {
    await AsyncStorage.removeItem("cc_user_id");
    await AsyncStorage.removeItem("cc_email");
    setUserId(null);
    setPassword("");
    setPlan("free");
    setRemainingDay(0);
    setRemainingMonth(0);
    resetScreenForNextScan();
    setHistory([]);
  }

  // ---------- plan sync (RevenueCat hook) ----------
  // Your existing UI likely calls this after purchase/restore.
  // IMPORTANT: mode must be 'purchase' on new purchase, and 'restore' on restore.
  async function planSync(entitlement, mode) {
    if (!userId) return;
    const res = await fetch(`${API_BASE}/plan/sync?user_id=${encodeURIComponent(userId)}` , {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entitlement, mode }),
    });
    const parsed = await safeJson(res);
    if (!parsed.ok) throw new Error(`Plan sync not JSON: ${String(parsed.text).slice(0, 160)}`);
    await fetchUsage();
  }

  // ---------- analyze ----------
  async function analyze() {
    if (!userId) {
      Alert.alert("Login required", "Please login first.");
      return;
    }
    if (!photoUri) {
      Alert.alert("No photo", "Tap Open Camera and capture a meal photo.");
      return;
    }

    setAnalyzing(true);
    try {
      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "meal.jpg",
        type: "image/jpeg",
      });

      const res = await fetch(`${API_BASE}/analyze?user_id=${encodeURIComponent(userId)}`, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: form,
      });

      const parsed = await safeJson(res);
      if (!parsed.ok) {
        throw new Error(`Server returned non-JSON. First bytes: ${String(parsed.text).slice(0, 160)}`);
      }
      const data = parsed.json;

      if (!res.ok) {
        const msg = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
        throw new Error(msg);
      }

      setResult(data);
      setCoaching(data?.coaching || null);
      setLocked(data?.locked || null);

      // usage refresh
      const u = data?.usage;
      if (u) {
        setPlan(String(u?.plan || "free").toLowerCase());
        setRemainingDay(Number(u?.remaining_day ?? remainingDay));
        setRemainingMonth(Number(u?.remaining_month ?? remainingMonth));
      } else {
        await fetchUsage();
      }

      // store history entry
      const entry = {
        ts: new Date().toISOString(),
        photoUri,
        total_kcal: data?.total_kcal ?? null,
        totals: data?.totals ?? null,
        items: data?.items ?? [],
        coaching: data?.coaching ?? null,
      };
      const next = [entry, ...(history || [])].slice(0, 50);
      await saveHistory(next);
    } catch (e) {
      Alert.alert("Analyze failed", String(e?.message || e));
    } finally {
      setAnalyzing(false);
    }
  }

  // ---------- barcode ----------
  async function barcodeLookup(code) {
    if (!userId) {
      Alert.alert("Login required", "Please login first.");
      return;
    }
    const digits = String(code || "").replace(/\D/g, "");
    if (!digits) {
      Alert.alert("Barcode", "Invalid barcode.");
      return;
    }

    setBarcodeBusy(true);
    try {
      const res = await fetch(`${API_BASE}/barcode/${digits}?user_id=${encodeURIComponent(userId)}`);
      const parsed = await safeJson(res);
      if (!parsed.ok) throw new Error(`Barcode not JSON: ${String(parsed.text).slice(0, 160)}`);
      const data = parsed.json;

      if (!res.ok) {
        const msg = data?.detail ? JSON.stringify(data.detail) : JSON.stringify(data);
        throw new Error(msg);
      }

      setBarcodeResult(data);

      // usage refresh
      const u = data?.usage;
      if (u) {
        setPlan(String(u?.plan || "free").toLowerCase());
        setRemainingDay(Number(u?.remaining_day ?? remainingDay));
        setRemainingMonth(Number(u?.remaining_month ?? remainingMonth));
      } else {
        await fetchUsage();
      }
    } catch (e) {
      Alert.alert("Barcode failed", String(e?.message || e));
    } finally {
      setBarcodeBusy(false);
    }
  }

  // ---------- render ----------
  if (!userId) {
    return (
      <SafeAreaView style={styles.root}>
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <View style={styles.loginWrap}>
            <Text style={styles.title}>CalorieClick.ai</Text>
            <Text style={styles.muted}>Login to sync scans + history per user.</Text>

            <Text style={styles.label}>Email</Text>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor="#6e6e6e"
              autoCapitalize="none"
              keyboardType="email-address"
              style={styles.input}
            />

            <Text style={styles.label}>Password</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="password"
              placeholderTextColor="#6e6e6e"
              secureTextEntry
              style={styles.input}
            />

            <PrimaryButton title={loggingIn ? "Signing in..." : "Login"} onPress={login} disabled={loggingIn} />

            <Text style={[styles.muted, { marginTop: 12 }]}>Note: this is a lightweight TestFlight login (no Apple ID / Supabase auth yet).</Text>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  const totalKcal = result?.total_kcal;
  const totals = result?.totals || {};

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerRow}>
          <Text style={styles.title}>CalorieClick.ai</Text>
          <View style={styles.headerButtons}>
            <GhostButton
              title="Refresh"
              onPress={async () => {
                resetScreenForNextScan();
                await refreshAll();
              }}
            />
            <GhostButton title="Logout" onPress={logout} />
          </View>
        </View>

        <View style={styles.pillsRow}>
          <Pill label="Plan" value={plan} />
          <Pill label="Day" value={String(remainingDay)} />
          <Pill label="Month" value={String(remainingMonth)} />
        </View>

        {/* Meal scan */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Meal scan</Text>

          {photoUri ? (
            <Image source={{ uri: photoUri }} style={styles.photo} />
          ) : (
            <View style={styles.photoEmpty}>
              <Text style={styles.muted}>No photo yet. Tap Open Camera.</Text>
            </View>
          )}

          <View style={styles.row}>
            <PrimaryButton title="Open Camera" onPress={() => setCameraOpen(true)} />
            <PrimaryButton title={analyzing ? "Analyzing..." : "Analyze"} onPress={analyze} disabled={analyzing} />
          </View>

          {result ? (
            <View style={{ marginTop: 12 }}>
              <Text style={styles.h2}>Total: {round1(totalKcal)} kcal</Text>
              <Text style={styles.muted2}>
                Protein {round1(totals?.protein_g)}g · Carbs {round1(totals?.carbs_g)}g · Fat {round1(totals?.fat_g)}g
              </Text>

              <Text style={[styles.h3, { marginTop: 12 }]}>Items</Text>
              {(result?.items || []).map((it, idx) => (
                <View key={`${it?.name || "item"}-${idx}`} style={styles.itemRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemName}>{String(it?.name || "").toLowerCase()}</Text>
                    <Text style={styles.muted2}>{round1(it?.grams)}g</Text>
                  </View>
                  <Text style={styles.itemKcal}>{round1(it?.kcal)} kcal</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        {/* Coaching */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Coaching insights</Text>

          {!coachingUnlocked ? (
            <View style={styles.lockedBox}>
              <Text style={styles.lockedTitle}>Locked 🔒</Text>
              <Text style={styles.lockedText}>
                Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.
              </Text>
              <Text style={styles.muted2}>Upgrade to Pro or Infinite to unlock.</Text>
            </View>
          ) : coaching ? (
            <View>
              <Text style={styles.sub}>Satiety Score: {round1(coaching?.satiety_score)}/100</Text>
              <Bar value={coaching?.satiety_score} max={100} />

              <Text style={styles.sub}>Protein Bioavailability (BV): {round1(coaching?.protein_bv_score)}/100</Text>
              <Bar value={coaching?.protein_bv_score} max={100} />

              <Text style={styles.sub}>
                Leucine Estimate: {round1(coaching?.leucine_estimate_g)}g {coaching?.mps_triggered ? "✅" : ""}
              </Text>
              <Text style={styles.muted2}>Threshold: {round1(coaching?.mps_threshold_g || MPS_THRESHOLD_G)}g · {coaching?.mps_triggered ? "Triggered" : "Not triggered"}</Text>

              <View style={{ marginTop: 10 }}>
                <Text style={styles.sub}>Glycemic Load: {round1(coaching?.glycemic_load?.gl)} ({String(coaching?.glycemic_load?.level || "").replaceAll("_", " ")})</Text>
                <Text style={styles.sub}>Ultra-Processed Score: {round1(coaching?.ultra_processed_score)}/10</Text>
              </View>

              {(coaching?.messages || []).length ? (
                <View style={{ marginTop: 10 }}>
                  {(coaching.messages || []).map((m, i) => (
                    <Text key={`m-${i}`} style={styles.bullet}>• {m}</Text>
                  ))}
                </View>
              ) : null}
            </View>
          ) : (
            <Text style={styles.muted}>Run an analysis to see coaching insights.</Text>
          )}

          {/* If backend says locked (e.g., it sent locked: coaching), show hint */}
          {locked?.feature === "coaching" ? (
            <Text style={[styles.muted2, { marginTop: 8 }]}>Backend: coaching locked, required plan = {locked?.required_plan}</Text>
          ) : null}
        </View>

        {/* Barcode */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Barcode</Text>
          <Text style={styles.muted2}>Elite+ can scan barcodes to fetch macros (OpenFoodFacts).</Text>

          {planRank(plan) < planRank("elite") ? (
            <View style={[styles.lockedBox, { marginTop: 10 }]}>
              <Text style={styles.lockedTitle}>Locked 🔒</Text>
              <Text style={styles.lockedText}>Barcode scanning requires Elite or higher.</Text>
            </View>
          ) : (
            <>
              <PrimaryButton title={barcodeBusy ? "Working..." : "Scan barcode"} onPress={() => setBarcodeOpen(true)} disabled={barcodeBusy} />

              <View style={styles.manualRow}>
                <TextInput
                  value={barcodeManual}
                  onChangeText={setBarcodeManual}
                  placeholder="Enter barcode manually"
                  placeholderTextColor="#6e6e6e"
                  style={[styles.input, { flex: 1, marginBottom: 0 }]}
                  keyboardType="number-pad"
                />
                <TouchableOpacity
                  onPress={() => barcodeLookup(barcodeManual)}
                  style={styles.manualBtn}
                  disabled={barcodeBusy}
                >
                  <Text style={styles.manualBtnText}>Lookup</Text>
                </TouchableOpacity>
              </View>

              {barcodeResult ? (
                <View style={{ marginTop: 12 }}>
                  <Text style={styles.h3}>{barcodeResult?.name || "Product"}</Text>
                  {barcodeResult?.brand ? <Text style={styles.muted2}>{barcodeResult.brand}</Text> : null}
                  <Text style={styles.muted2}>Per 100g:</Text>
                  <Text style={styles.muted2}>
                    {round1(barcodeResult?.per_100g?.kcal)} kcal · P {round1(barcodeResult?.per_100g?.protein_g)}g · C {round1(barcodeResult?.per_100g?.carbs_g)}g · F 
{round1(barcodeResult?.per_100g?.fat_g)}g
                  </Text>
                </View>
              ) : null}
            </>
          )}
        </View>

        {/* Upgrade (TestFlight simulation buttons) */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Upgrade</Text>
          <Text style={styles.muted2}>TestFlight: simulate purchase/restore syncing with backend.</Text>

          <View style={styles.rowWrap}>
            {[
              { p: "elite", price: "ELITE" },
              { p: "advanced", price: "ADVANCED" },
              { p: "pro", price: "PRO" },
              { p: "infinite", price: "INFINITE" },
            ].map((x) => (
              <TouchableOpacity
                key={x.p}
                style={styles.upBtn}
                onPress={async () => {
                  try {
                    // Simulate a PURCHASE (should refill limits). Use mode='restore' only for restore button.
                    await planSync(x.p, "purchase");
                    Alert.alert("Plan updated", `Plan is now ${x.p}`);
                  } catch (e) {
                    Alert.alert("Upgrade failed", String(e?.message || e));
                  }
                }}
              >
                <Text style={styles.upBtnText}>{x.price}</Text>
              </TouchableOpacity>
            ))}

            <TouchableOpacity
              style={[styles.upBtn, styles.restoreBtn]}
              onPress={async () => {
                try {
                  // NOTE: in real app, use RevenueCat restore to get entitlement, then call planSync(entitlement,'restore')
                  await planSync(plan, "restore");
                  Alert.alert("Restore", "Restore synced to backend (no scan refill). ");
                } catch (e) {
                  Alert.alert("Restore failed", String(e?.message || e));
                }
              }}
            >
              <Text style={styles.upBtnText}>Restore</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* History */}
        <View style={styles.card}>
          <View style={styles.historyHeader}>
            <Text style={styles.cardTitle}>History (this user only)</Text>
            <TouchableOpacity
              style={styles.clearHistoryBtn}
              onPress={async () => {
                await saveHistory([]);
              }}
            >
              <Text style={styles.clearHistoryText}>Clear</Text>
            </TouchableOpacity>
          </View>

          {history?.length ? (
            history.map((h, idx) => (
              <View key={`h-${idx}`} style={styles.histRow}>
                <Image source={{ uri: h.photoUri }} style={styles.histThumb} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemName}>{round1(h.total_kcal)} kcal</Text>
                  <Text style={styles.muted2}>{new Date(h.ts).toLocaleString()}</Text>
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.muted}>No history yet.</Text>
          )}
        </View>

        <View style={{ height: 20 }} />
      </ScrollView>

      <CameraModal
        visible={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCaptured={(uri) => {
          // when changing user, old photo should not persist
          setPhotoUri(uri);
          setResult(null);
          setCoaching(null);
          setLocked(null);
        }}
      />

      <BarcodeModal
        visible={barcodeOpen}
        onClose={() => setBarcodeOpen(false)}
        onDetected={(code) => barcodeLookup(code)}
      />
    </SafeAreaView>
  );
}

// -------------------- styles --------------------
const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#000" },
  container: { padding: 16, paddingBottom: 40 },

  title: { color: "#fff", fontSize: 32, fontWeight: "900" },
  muted: { color: "#9aa0a6", marginTop: 8 },
  muted2: { color: "#9aa0a6", marginTop: 4 },

  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButtons: { flexDirection: "row", gap: 10 },

  pillsRow: { flexDirection: "row", gap: 10, marginTop: 12, marginBottom: 12, flexWrap: "wrap" },
  pill: {
    backgroundColor: "#121212",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#1f1f1f",
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
  },
  pillLabel: { color: "#7b7b7b", fontSize: 12, fontWeight: "700" },
  pillValue: { color: "#fff", fontSize: 12, fontWeight: "900" },

  card: {
    backgroundColor: "#0b0b0b",
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: "#161616",
    marginTop: 12,
  },
  cardTitle: { color: "#fff", fontSize: 18, fontWeight: "900" },

  row: { flexDirection: "row", gap: 10, marginTop: 10 },
  rowWrap: { flexDirection: "row", gap: 10, marginTop: 10, flexWrap: "wrap" },

  btn: {
    backgroundColor: "#2f6bff",
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flex: 1,
    alignItems: "center",
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: "#fff", fontWeight: "900" },

  btnGhost: {
    backgroundColor: "#121212",
    borderWidth: 1,
    borderColor: "#1f1f1f",
    borderRadius: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  btnGhostText: { color: "#fff", fontWeight: "800" },

  photo: { width: "100%", height: 220, borderRadius: 14, marginTop: 10 },
  photoEmpty: {
    height: 220,
    borderRadius: 14,
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#1f1f1f",
    alignItems: "center",
    justifyContent: "center",
  },

  h2: { color: "#fff", fontSize: 22, fontWeight: "900" },
  h3: { color: "#fff", fontSize: 16, fontWeight: "900" },

  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#151515",
  },
  itemName: { color: "#fff", fontWeight: "800", fontSize: 14 },
  itemKcal: { color: "#fff", fontWeight: "900" },

  lockedBox: {
    marginTop: 10,
    backgroundColor: "#101010",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "#1f1f1f",
  },
  lockedTitle: { color: "#fff", fontWeight: "900", marginBottom: 4 },
  lockedText: { color: "#c8c8c8" },

  sub: { color: "#fff", marginTop: 10, fontWeight: "800" },
  barBg: { height: 10, borderRadius: 999, backgroundColor: "#151515", marginTop: 6, overflow: "hidden" },
  barFill: { height: 10, borderRadius: 999, backgroundColor: "#2f6bff" },

  bullet: { color: "#d7d7d7", marginTop: 6 },

  manualRow: { flexDirection: "row", gap: 10, marginTop: 10, alignItems: "center" },
  manualBtn: {
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: "#2a2a2a",
  },
  manualBtnText: { color: "#fff", fontWeight: "900" },

  upBtn: {
    backgroundColor: "#121212",
    borderWidth: 1,
    borderColor: "#1f1f1f",
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  upBtnText: { color: "#fff", fontWeight: "900" },
  restoreBtn: { borderColor: "#2f6bff" },

  historyHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  clearHistoryBtn: {
    backgroundColor: "#121212",
    borderWidth: 1,
    borderColor: "#1f1f1f",
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  clearHistoryText: { color: "#fff", fontWeight: "900" },
  histRow: { flexDirection: "row", gap: 12, alignItems: "center", marginTop: 12 },
  histThumb: { width: 54, height: 54, borderRadius: 10, backgroundColor: "#111" },

  input: {
    backgroundColor: "#0e0e0e",
    borderWidth: 1,
    borderColor: "#1f1f1f",
    borderRadius: 12,
    padding: 12,
    color: "#fff",
    marginBottom: 12,
  },
  label: { color: "#c8c8c8", fontWeight: "800", marginTop: 12, marginBottom: 6 },

  loginWrap: { padding: 16, flex: 1, justifyContent: "center" },

  // camera/barcode modal
  camWrap: { flex: 1, backgroundColor: "#000" },
  camTopRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 12, paddingTop: 6 },
  camTitle: { color: "#fff", fontWeight: "900", fontSize: 16 },
  camBody: { flex: 1 },
  camPreview: { flex: 1 },
  centerPad: { flex: 1, justifyContent: "center", alignItems: "center", padding: 16, gap: 12 },
  captureRow: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 18,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  captureBtn: {
    width: "100%",
    backgroundColor: "#2f6bff",
    borderRadius: 16,
    paddingVertical: 14,
    alignItems: "center",
  },
  captureText: { color: "#fff", fontWeight: "900", fontSize: 16 },
  scanHintBox: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 18,
    backgroundColor: "rgba(0,0,0,0.55)",
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  scanHintText: { color: "#fff", fontWeight: "800", textAlign: "center" },
});

// -------------------- CRASH GUARD (avoid white screen) --------------------
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }
  componentDidCatch(error, info) {
    console.log("[ErrorBoundary]", error);
    this.setState({ error, info });
  }
  render() {
    if (this.state.error) {
      const msg = String(this.state.error?.message || this.state.error || "Unknown error");
      return (
        <SafeAreaView style={{ flex: 1, backgroundColor: "#000" }}>
          <View style={{ flex: 1, padding: 18, justifyContent: "center" }}>
            <Text style={{ color: "#fff", fontSize: 22, fontWeight: "900", marginBottom: 8 }}>
              App crashed
            </Text>
            <Text style={{ color: "#ddd", marginBottom: 12 }}>
              {msg}
            </Text>
            <Text style={{ color: "#888", marginBottom: 18 }}>
              If this is a TestFlight white screen, this message helps us pinpoint the exact cause.
            </Text>
            <Pressable
              onPress={() => this.setState({ error: null, info: null })}
              style={{ backgroundColor: "#2b6cff", paddingVertical: 12, borderRadius: 14, alignItems: "center" }}
            >
              <Text style={{ color: "#fff", fontWeight: "900" }}>Try again</Text>
            </Pressable>
          </View>
        </SafeAreaView>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}
