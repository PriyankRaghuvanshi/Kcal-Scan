// mobile/App.js
import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, TouchableOpacity, Alert, ActivityIndicator, StyleSheet } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";

import { supabase, HAS_SUPABASE } from "./src/lib/supabase";
import {
  configurePurchases,
  getMainOffering,
  getCustomerInfo,
  purchasePackage,
  restorePurchases,
  getActiveEntitlement,
  ENTITLEMENTS,
} from "./src/lib/revenuecat";
import { consumeScan, upsertEntitlement } from "./src/lib/scans";

const API_BASE = "https://kcal-scan-production.up.railway.app";

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();

  // auth
  const [session, setSession] = useState(null);
  const userId = session?.user?.id || null;

  // RevenueCat
  const [rcReady, setRcReady] = useState(false);
  const [offering, setOffering] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [plan, setPlan] = useState("free");

  // usage (returned by consume_scan)
  const [usage, setUsage] = useState(null);

  // loading
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!HAS_SUPABASE) {
      Alert.alert("Missing Supabase", "Set EXPO_PUBLIC_SUPABASE_URL and ANON key in mobile/.env");
      return;
    }

    // Session init
    (async () => {
      const { data } = await supabase.auth.getSession();
      setSession(data.session ?? null);
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession ?? null);
    });

    return () => sub?.subscription?.unsubscribe?.();
  }, []);

  // Configure RevenueCat once we have userId
  useEffect(() => {
    if (!userId) return;

    (async () => {
      try {
        await configurePurchases(userId);
        const main = await getMainOffering();
        setOffering(main);

        const info = await getCustomerInfo();
        setCustomerInfo(info);

        const active = getActiveEntitlement(info);
        setPlan(active);

        // store entitlement in Supabase (used by scan-limit RPC)
        await upsertEntitlement({ userId, entitlement: active });
        setRcReady(true);
      } catch (e) {
        console.log("RevenueCat init error:", e);
        Alert.alert(
          "Subscriptions not ready",
          "RevenueCat needs a Development Build (not Expo Go). If you are in Expo Go, purchases won’t work."
        );
      }
    })();
  }, [userId]);

  async function refreshCustomer() {
    const info = await getCustomerInfo();
    setCustomerInfo(info);
    const active = getActiveEntitlement(info);
    setPlan(active);
    await upsertEntitlement({ userId, entitlement: active });
  }

  async function buy(planId) {
    if (!offering) return Alert.alert("Offerings not loaded yet");

    try {
      setLoading(true);

      // Find a package matching your planId.
      // RevenueCat packages are usually monthly/yearly types.
      // We’ll match by product identifier or package identifier containing the planId.
      const pkg =
        offering.availablePackages.find((p) =>
          (p.identifier || "").toLowerCase().includes(planId)
        ) ||
        offering.availablePackages.find((p) =>
          (p.product?.identifier || "").toLowerCase().includes(planId)
        );

      if (!pkg) {
        throw new Error(`Package not found for "${planId}". Check RevenueCat package IDs.`);
      }

      const info = await purchasePackage(pkg);
      setCustomerInfo(info);

      const active = getActiveEntitlement(info);
      setPlan(active);
      await upsertEntitlement({ userId, entitlement: active });

      Alert.alert("Success", `Subscribed: ${active}`);
    } catch (e) {
      Alert.alert("Purchase failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  async function doAnalyze() {
    if (!userId) return Alert.alert("Login required");

    try {
      setLoading(true);

      // 1) enforce scan limit in Supabase first
      const gate = await consumeScan({ userId, source: "photo" });
      setUsage(gate);

      if (!gate?.allowed) {
        Alert.alert(
          "Limit reached",
          `Plan: ${gate.plan}\nReason: ${gate.reason}\nRemaining today: ${gate.remaining_day}\nRemaining month: ${gate.remaining_month}`
        );
        return;
      }

      // 2) call your backend (placeholder example)
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error("Backend not reachable");
      Alert.alert("OK", "Scan allowed + backend reachable ✅");
    } catch (e) {
      Alert.alert("Error", e.message);
    } finally {
      setLoading(false);
    }
  }

  async function doRestore() {
    try {
      setLoading(true);
      const info = await restorePurchases();
      setCustomerInfo(info);
      const active = getActiveEntitlement(info);
      setPlan(active);
      await upsertEntitlement({ userId, entitlement: active });
      Alert.alert("Restored", `Plan: ${active}`);
    } catch (e) {
      Alert.alert("Restore failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  // Permissions
  // Permissions
  if (!permission) {
  return (
    <View style={[styles.center, { backgroundColor: "#0B0B0F" }]}>
      <Text style={{ color: "#fff", fontSize: 16 }}>Loading permissions…</Text>
    </View>
   );
 }

  if (!permission.granted) {
  return (
    <View style={[styles.center, { backgroundColor: "#0B0B0F", padding: 24 }]}>
      <Text style={{ color: "#fff", marginBottom: 12, fontSize: 16, fontWeight: "700" }}>
        Camera permission required
      </Text>
      <Text style={{ color: "#B8B8B8", marginBottom: 18, textAlign: "center" }}>
        We need camera access to scan meals and estimate calories.
      </Text>

      <TouchableOpacity onPress={requestPermission} style={[styles.btn, styles.primary]}>
        <Text style={styles.btnText}>Grant Permission</Text>
      </TouchableOpacity>
    </View>
   );
 }


  return (
    <View style={styles.container}>
      <View style={styles.cameraWrap}>
        <CameraView style={styles.camera} ref={cameraRef} />
      </View>

      <View style={styles.panel}>
        <Text style={styles.title}>CalorieClick.ai</Text>

        <Text style={{ color: "white", marginBottom: 6 }}>
          Plan: <Text style={{ fontWeight: "900" }}>{plan}</Text>
          {"  "}
          {rcReady ? "✅" : "⚠️"}
        </Text>

        {usage ? (
          <Text style={{ color: "#ccc", marginBottom: 10 }}>
            Remaining today: {usage.remaining_day} • Remaining month: {usage.remaining_month}
          </Text>
        ) : null}

        <TouchableOpacity style={[styles.btn, styles.primary]} onPress={doAnalyze} disabled={loading}>
          <Text style={styles.btnText}>{loading ? "Working..." : "Snap & Analyze (enforced)"}</Text>
        </TouchableOpacity>

        <View style={{ height: 10 }} />

        <Text style={{ color: "#aaa", marginBottom: 8 }}>Upgrade</Text>

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={() => buy("elite")} disabled={loading}>
            <Text style={styles.btnText}>Elite</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => buy("advanced")} disabled={loading}>
            <Text style={styles.btnText}>Advanced</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={() => buy("pro")} disabled={loading}>
            <Text style={styles.btnText}>Pro</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btn} onPress={() => buy("infinite")} disabled={loading}>
            <Text style={styles.btnText}>Infinite</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 10 }} />

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={doRestore} disabled={loading}>
            <Text style={styles.btnText}>Restore</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.btn}
            onPress={async () => {
              await refreshCustomer();
              Alert.alert("Refreshed", `Plan: ${plan}`);
            }}
            disabled={loading}
          >
            <Text style={styles.btnText}>Refresh</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  cameraWrap: { flex: 1 },
  camera: { flex: 1 },
  panel: { padding: 14, backgroundColor: "#0f0f0f" },
  title: { color: "white", fontSize: 20, fontWeight: "900", marginBottom: 10 },
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
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
});

