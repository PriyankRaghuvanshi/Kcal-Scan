// App.js — CalorieClick.ai (Pro Coaching gated)
// Free: calories/macros only
// Elite/Advanced: barcode + more scans (NO coaching)
// Pro/Infinite: coaching (Satiety, BV, MPS Leucine)

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ActivityIndicator,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import Constants from "expo-constants";

const BACKEND =
  Constants.expoConfig?.extra?.BACKEND_URL ||
  "https://kcal-scan-production.up.railway.app";

const PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"];

function planAtLeast(current, required) {
  const c = (current || "free").toLowerCase();
  const r = (required || "free").toLowerCase();
  return PLAN_ORDER.indexOf(c) >= PLAN_ORDER.indexOf(r);
}

function clamp01(x) {
  return Math.max(0, Math.min(1, x));
}

export default function App() {
  const [userId, setUserId] = useState("");
  const [plan, setPlan] = useState("free");
  const [remaining, setRemaining] = useState(null);

  const [busy, setBusy] = useState(false);

  const [photoUri, setPhotoUri] = useState(null);
  const [result, setResult] = useState(null);

  const [history, setHistory] = useState([]);

  // -------- usage fetch
  async function refreshUsage(uid) {
    if (!uid) return;
    try {
      const r = await fetch(`${BACKEND}/usage?user_id=${uid}`);
      const j = await r.json();
      setPlan((j.plan || "free").toLowerCase());
      setRemaining(j.remaining_month ?? j.remaining_day ?? null);
    } catch (e) {
      console.log("usage error", e);
    }
  }

  // -------- init placeholder
  useEffect(() => {
    // Set your UUID here or from login screen
    const demo = "f2c9517b-48e1-41c1-ad3f-c6fbcf89053b";
    setUserId(demo);
    refreshUsage(demo);
  }, []);

  const canShowCoaching = useMemo(() => planAtLeast(plan, "pro"), [plan]);

  // -------- pick/take photo
  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Camera permission required");
      return;
    }
    const img = await ImagePicker.launchCameraAsync({
      quality: 0.8,
      allowsEditing: false,
    });
    if (!img.canceled) {
      setPhotoUri(img.assets[0].uri);
      setResult(null);
    }
  }

  async function pickPhoto() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Gallery permission required");
      return;
    }
    const img = await ImagePicker.launchImageLibraryAsync({
      quality: 0.8,
      allowsEditing: false,
    });
    if (!img.canceled) {
      setPhotoUri(img.assets[0].uri);
      setResult(null);
    }
  }

  // -------- clear for next scan
  function clearNext() {
    setPhotoUri(null);
    setResult(null);
  }

  // -------- clear history
  function clearHistory() {
    setHistory([]);
  }

  // -------- analyze
  async function analyze() {
    if (!photoUri) {
      Alert.alert("Take a photo first");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", {
        uri: photoUri,
        name: "photo.jpg",
        type: "image/jpeg",
      });

      const r = await fetch(`${BACKEND}/analyze?user_id=${userId}`, {
        method: "POST",
        body: form,
      });

      const j = await r.json();

      // sync usage after scan
      refreshUsage(userId);

      // handle paywall/limit
      if (!r.ok) {
        Alert.alert("Analyze failed", j?.detail?.error || j?.detail || "Error");
        return;
      }

      setResult(j);

      // push history
      setHistory((prev) => [
        {
          id: Date.now(),
          kcal: j.total_kcal,
          ts: new Date().toLocaleString(),
        },
        ...prev,
      ]);
    } catch (e) {
      console.log(e);
      Alert.alert("Analyze failed", String(e));
    } finally {
      setBusy(false);
    }
  }

  // -------- UI helpers
  const totalLine = result?.total_kcal
    ? `Total: ${result.total_kcal} kcal`
    : null;

  const totals = result?.totals || {};
  const P = totals.protein_g ?? 0;
  const C = totals.carbs_g ?? 0;
  const F = totals.fat_g ?? 0;

  const satiety = result?.coaching?.satiety_score; // 0..100
  const bv = result?.coaching?.protein_bv_score; // 0..100
  const bioProtein = result?.coaching?.bioavailable_protein_g;
  const leucine = result?.coaching?.leucine_g;
  const leucineOk = result?.coaching?.mps_triggered;

  // Backend sets this for non-pro:
  const lockedCoaching =
    result?.locked?.feature === "coaching" && !canShowCoaching;

  return (
    <View style={styles.container}>
      <Text style={styles.header}>CalorieClick.ai</Text>

      <View style={styles.topBar}>
        <Text style={styles.planText}>
          Plan: {plan} • Remaining: {remaining ?? "-"}
        </Text>
      </View>

      {!!photoUri && (
        <View style={styles.imageWrap}>
          <Image source={{ uri: photoUri }} style={styles.preview} />
        </View>
      )}

      <View style={styles.btnRow}>
        <TouchableOpacity style={styles.btn} onPress={takePhoto}>
          <Text style={styles.btnText}>Take Photo</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.btn} onPress={analyze}>
          <Text style={styles.btnText}>Analyze</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity style={styles.clearBtn} onPress={clearNext}>
        <Text style={styles.clearText}>Clear (Next Scan)</Text>
      </TouchableOpacity>

      {busy && (
        <View style={{ marginTop: 20 }}>
          <ActivityIndicator />
        </View>
      )}

      {/* RESULT */}
      {!!result && (
        <View style={styles.card}>
          <Text style={styles.totalText}>{totalLine}</Text>
          <Text style={styles.macrosText}>
            P {P}g • C {C}g • F {F}g
          </Text>

          {/* COACHING — ONLY PRO+ */}
          {canShowCoaching && (
            <>
              {/* Satiety */}
              <Text style={styles.sectionTitle}>
                Satiety Index{" "}
                <Text style={styles.scoreRight}>
                  {Math.round(satiety ?? 0)}/100
                </Text>
              </Text>
              <View style={styles.barBg}>
                <View
                  style={[
                    styles.barFill,
                    { width: `${clamp01((satiety ?? 0) / 100) * 100}%` },
                  ]}
                />
              </View>

              {/* Protein BV */}
              <Text style={styles.sectionTitle}>
                Protein Bioavailability{" "}
                <Text style={styles.scoreRight}>
                  {Math.round(bv ?? 0)}/100
                </Text>
              </Text>
              <View style={styles.barBg}>
                <View
                  style={[
                    styles.barFill,
                    { width: `${clamp01((bv ?? 0) / 100) * 100}%` },
                  ]}
                />
              </View>

              {/* MPS (Leucine) */}
              <View style={styles.mpsRow}>
                <Text style={styles.sectionTitle}>MPS (Leucine)</Text>
                <Text style={styles.mpsRight}>
                  {(leucine ?? 0).toFixed(2)}g {leucineOk ? "✅" : "❌"}
                </Text>
              </View>
              <Text style={styles.subText}>
                Threshold: 2.5g • {leucineOk ? "Triggered" : "Not yet"}
              </Text>

              <Text style={styles.subText}>
                Est. bioavailable protein:{" "}
                {bioProtein ? `${bioProtein.toFixed(1)}g` : "-"} (BV ~
                {Math.round(bv ?? 0)})
              </Text>
            </>
          )}

          {/* LOCKED MESSAGE — for Free/Elite/Advanced */}
          {lockedCoaching && (
            <View style={styles.lockedBox}>
              <Text style={styles.lockedTitle}>
                🔓 Unlock Satiety + Protein BV + MPS
              </Text>
              <Text style={styles.lockedSub}>
                Upgrade to <Text style={{ fontWeight: "700" }}>Pro</Text> or{" "}
                <Text style={{ fontWeight: "700" }}>Infinite</Text> to see
                coaching insights.
              </Text>
            </View>
          )}

          {/* ITEMS */}
          {(result.items || []).map((it, idx) => (
            <View key={idx} style={styles.itemRow}>
              <Text style={styles.itemName}>{it.name}</Text>
              <Text style={styles.itemKcal}>{it.kcal} kcal</Text>
            </View>
          ))}
        </View>
      )}

      {/* HISTORY */}
      <View style={styles.historyHeader}>
        <Text style={styles.historyTitle}>History</Text>
        <TouchableOpacity style={styles.clearHistoryBtn} onPress={clearHistory}>
          <Text style={styles.clearHistoryText}>Clear History</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={{ flex: 1 }}>
        {history.map((h) => (
          <View key={h.id} style={styles.historyRow}>
            <Text style={styles.historyKcal}>📷 {h.kcal} kcal</Text>
            <Text style={styles.historyTs}>{h.ts}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

// ---------------- Styles ----------------
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b0c10", paddingTop: 50 },
  header: {
    color: "white",
    fontSize: 34,
    fontWeight: "800",
    paddingHorizontal: 18,
    marginBottom: 10,
  },
  topBar: {
    paddingHorizontal: 18,
    marginBottom: 10,
  },
  planText: { color: "#a6a6a6", fontSize: 15 },

  imageWrap: {
    marginHorizontal: 18,
    borderRadius: 18,
    overflow: "hidden",
    backgroundColor: "#111",
  },
  preview: { width: "100%", height: 260 },

  btnRow: {
    flexDirection: "row",
    gap: 14,
    paddingHorizontal: 18,
    marginTop: 14,
  },
  btn: {
    flex: 1,
    backgroundColor: "#3a6df0",
    paddingVertical: 16,
    borderRadius: 16,
    alignItems: "center",
  },
  btnText: { color: "white", fontWeight: "800", fontSize: 16 },

  clearBtn: {
    marginHorizontal: 18,
    marginTop: 12,
    backgroundColor: "#1f212b",
    borderRadius: 16,
    paddingVertical: 14,
    alignItems: "center",
  },
  clearText: { color: "#d3d3d3", fontWeight: "700" },

  card: {
    marginHorizontal: 18,
    marginTop: 18,
    backgroundColor: "#12131a",
    borderRadius: 18,
    padding: 16,
  },

  totalText: { color: "white", fontSize: 26, fontWeight: "800" },
  macrosText: { color: "#c7c7c7", marginTop: 6, marginBottom: 10 },

  sectionTitle: { color: "white", fontWeight: "800", marginTop: 14 },
  scoreRight: { color: "#a6a6a6", fontWeight: "800" },

  barBg: {
    height: 10,
    backgroundColor: "#262833",
    borderRadius: 99,
    marginTop: 8,
    overflow: "hidden",
  },
  barFill: { height: "100%", backgroundColor: "#3a6df0" },

  subText: { color: "#8f8f8f", marginTop: 8 },

  mpsRow: { flexDirection: "row", justifyContent: "space-between" },
  mpsRight: { color: "white", fontWeight: "900" },

  lockedBox: {
    marginTop: 14,
    padding: 14,
    borderRadius: 14,
    backgroundColor: "#1a1c25",
    borderWidth: 1,
    borderColor: "#2a2e3a",
  },
  lockedTitle: {
    color: "white",
    fontWeight: "900",
    fontSize: 16,
    marginBottom: 6,
  },
  lockedSub: { color: "#bdbdbd" },

  itemRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 12,
  },
  itemName: { color: "white", fontWeight: "800" },
  itemKcal: { color: "#bdbdbd", fontWeight: "700" },

  historyHeader: {
    marginTop: 18,
    paddingHorizontal: 18,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  historyTitle: { color: "white", fontSize: 22, fontWeight: "900" },
  clearHistoryBtn: {
    backgroundColor: "#1f212b",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 14,
  },
  clearHistoryText: { color: "#d3d3d3", fontWeight: "700" },

  historyRow: {
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: "#151720",
  },
  historyKcal: { color: "white", fontWeight: "800", fontSize: 18 },
  historyTs: { color: "#8f8f8f", marginTop: 6 },
});

