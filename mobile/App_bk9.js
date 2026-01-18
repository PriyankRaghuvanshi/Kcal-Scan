import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  ActivityIndicator,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";

import { supabase } from "./src/lib/supabase";
import {
  configurePurchases,
  fetchMainOffering,
  getActiveEntitlement,
  purchasePackage,
  restorePurchases,
} from "./src/lib/purchases";

/**
 * ENV required (Expo):
 * EXPO_PUBLIC_SUPABASE_URL
 * EXPO_PUBLIC_SUPABASE_ANON_KEY
 * EXPO_PUBLIC_REVENUECAT_IOS_API_KEY
 * EXPO_PUBLIC_ANALYZE_URL            (optional for now)
 * EXPO_PUBLIC_BARCODE_LOOKUP_URL     (optional for now)
 *
 * NOTE: For iOS RevenueCat to actually load products in dev,
 * you must use StoreKit Configuration OR a sandbox tester + approved IAP setup.
 */

export default function App() {
  // ---------- Auth ----------
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("review@calorieclick.ai");
  const [password, setPassword] = useState("CalorieClick@123");
  const [authLoading, setAuthLoading] = useState(false);

  // ---------- RevenueCat ----------
  const [rcReady, setRcReady] = useState(false);
  const [offering, setOffering] = useState(null);
  const [plan, setPlan] = useState("free");
  const [loading, setLoading] = useState(false);

  // ---------- Usage (from Supabase) ----------
  const [usage, setUsage] = useState(null); // { remaining_day, remaining_month }

  // ---------- Camera / Barcode ----------
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [mode, setMode] = useState("camera"); // "camera" | "barcode"
  const [scanned, setScanned] = useState(false);

  const userId = session?.user?.id || null;

  // -----------------------
  // Auth bootstrap
  // -----------------------
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, sess) => {
      setSession(sess);
    });
    return () => sub?.subscription?.unsubscribe?.();
  }, []);

  async function doLogin() {
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login failed", e.message);
    } finally {
      setAuthLoading(false);
    }
  }

  async function doSignup() {
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Account created", "Now log in with the same details.");
    } catch (e) {
      Alert.alert("Signup failed", e.message);
    } finally {
      setAuthLoading(false);
    }
  }

  async function doLogout() {
    await supabase.auth.signOut();
    setPlan("free");
    setUsage(null);
  }

  // -----------------------
  // RevenueCat init (after login)
  // -----------------------
  useEffect(() => {
    if (!userId) return;

    (async () => {
      try {
        setRcReady(false);
        const apiKey = process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY;
        await configurePurchases(apiKey, userId);

        // Load offerings (main)
        const main = await fetchMainOffering();
        setOffering(main);

        // Customer info -> active plan
        const info = await (await import("react-native-purchases")).default.getCustomerInfo();
        const active = getActiveEntitlement(info);
        setPlan(active);

        setRcReady(true);
      } catch (e) {
        console.log("[RevenueCat] init error:", e);
        setRcReady(false);
        // Don’t block the app; just show upgrade not available
      }
    })();
  }, [userId]);

  // -----------------------
  // Usage load (from Supabase)
  // -----------------------
  useEffect(() => {
    if (!userId) return;
    refreshUsage().catch(() => {});
  }, [userId, plan]);

  async function refreshUsage() {
    if (!userId) return;
    const { data, error } = await supabase.rpc("get_usage", { p_user_id: userId });
    if (error) {
      console.log("get_usage error", error);
      return;
    }
    setUsage(data);
  }

  // -----------------------
  // Purchase flow
  // -----------------------
  const packagesByEntitlement = useMemo(() => {
    // We map package identifier -> entitlement key
    // In RevenueCat dashboard you set entitlement per product.
    // Here we find the package whose product identifier matches.
    const map = {};
    const pkgs = offering?.availablePackages || [];
    for (const p of pkgs) {
      // Try best-effort mapping by identifier/title
      const id = (p.identifier || "").toLowerCase();
      if (id.includes("elite")) map.elite = p;
      if (id.includes("advanced")) map.advanced = p;
      if (id.includes("pro")) map.pro = p;
      if (id.includes("infinite")) map.infinite = p;
    }
    return map;
  }, [offering]);

  async function buy(entitlementKey) {
    try {
      if (!userId) return Alert.alert("Login required", "Please login first.");
      if (!rcReady || !offering) return Alert.alert("Offerings not loaded yet", "RevenueCat not ready.");
      const pkg = packagesByEntitlement[entitlementKey];
      if (!pkg) {
        return Alert.alert(
          "Package not found",
          `Couldn't find a package for "${entitlementKey}" in offering "main". Check RevenueCat package identifiers.`
        );
      }

      setLoading(true);
      const info = await purchasePackage(pkg);
      const active = getActiveEntitlement(info);
      setPlan(active);

      // Sync plan to Supabase (optional but useful)
      await supabase.rpc("upsert_plan", { p_user_id: userId, p_plan: active });

      await refreshUsage();
      Alert.alert("Subscribed ✅", `Plan: ${active}`);
    } catch (e) {
      Alert.alert("Purchase failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  async function doRestore() {
    try {
      setLoading(true);
      const info = await restorePurchases();
      const active = getActiveEntitlement(info);
      setPlan(active);

      await supabase.rpc("upsert_plan", { p_user_id: userId, p_plan: active });
      await refreshUsage();

      Alert.alert("Restored ✅", `Plan: ${active}`);
    } catch (e) {
      Alert.alert("Restore failed", e.message);
    } finally {
      setLoading(false);
    }
  }

  // -----------------------
  // Enforced consume
  // -----------------------
  async function consume(kind, payload) {
    // kind = "photo" | "barcode"
    if (!userId) {
      Alert.alert("Login required");
      return { ok: false };
    }

    const { data, error } = await supabase.rpc("consume_scan", {
      p_user_id: userId,
      p_kind: kind,
    });

    if (error) {
      Alert.alert("Limit check failed", error.message);
      return { ok: false };
    }

    // data returns { allowed, remaining_day, remaining_month, reason }
    setUsage({ remaining_day: data.remaining_day, remaining_month: data.remaining_month });

    if (!data.allowed) {
      Alert.alert("Limit reached", data.reason || "No scans remaining. Upgrade to continue.");
      return { ok: false };
    }

    return { ok: true };
  }

  async function doAnalyze() {
    try {
      setLoading(true);
      const gate = await consume("photo");
      if (!gate.ok) return;

      // If you have analyze URL ready, call it here.
      const ANALYZE_URL = process.env.EXPO_PUBLIC_ANALYZE_URL;
      if (!ANALYZE_URL) {
        Alert.alert("Captured ✅", "Photo captured. Add EXPO_PUBLIC_ANALYZE_URL to run analysis.");
        return;
      }

      // Minimal stub: you can implement your capture->upload->analyze pipeline later
      Alert.alert("TODO", "Hook camera capture + upload -> analyze API.");
    } finally {
      setLoading(false);
    }
  }

  async function doBarcodeLookup(barcode) {
    try {
      setLoading(true);
      const gate = await consume("barcode");
      if (!gate.ok) return;

      const LOOKUP = process.env.EXPO_PUBLIC_BARCODE_LOOKUP_URL;
      if (!LOOKUP) {
        Alert.alert("Barcode scanned ✅", `${barcode}\nAdd EXPO_PUBLIC_BARCODE_LOOKUP_URL to lookup nutrition.`);
        return;
      }

      // Example request:
      // const res = await fetch(`${LOOKUP}?code=${encodeURIComponent(barcode)}`);
      // const json = await res.json();
      // Alert.alert("Result", JSON.stringify(json, null, 2));

      Alert.alert("TODO", "Implement lookup API call + UI display.");
    } finally {
      setLoading(false);
    }
  }

  // -----------------------
  // Camera permissions UI (fixes your black screen)
  // -----------------------
  if (!permission) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: "#0b0b0f" }]}>
        <Text style={{ color: "#fff" }}>Loading permissions…</Text>
      </SafeAreaView>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: "#0b0b0f" }]}>
        <Text style={{ color: "#fff", fontSize: 16, fontWeight: "700", marginBottom: 10 }}>
          Camera permission required
        </Text>
        <Text style={{ color: "#aaa", marginBottom: 16, textAlign: "center", paddingHorizontal: 24 }}>
          We need camera access to scan meals and barcodes.
        </Text>
        <TouchableOpacity onPress={requestPermission} style={[styles.btn, styles.primary]}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  // -----------------------
  // If not logged in -> Login Screen
  // -----------------------
  if (!session) {
    return (
      <SafeAreaView style={styles.authWrap}>
        <Text style={styles.authTitle}>CalorieClick.ai</Text>
        <Text style={styles.authSub}>Login to continue</Text>

        <TextInput
          placeholder="Email"
          placeholderTextColor="#777"
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
        />
        <TextInput
          placeholder="Password"
          placeholderTextColor="#777"
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />

        <TouchableOpacity onPress={doLogin} style={[styles.btn, styles.primary]} disabled={authLoading}>
          {authLoading ? <ActivityIndicator /> : <Text style={styles.btnText}>Login</Text>}
        </TouchableOpacity>

        <View style={{ height: 12 }} />

        <TouchableOpacity onPress={doSignup} style={[styles.btn, styles.secondary]} disabled={authLoading}>
          <Text style={styles.btnText}>Create account</Text>
        </TouchableOpacity>

        <Text style={styles.reviewHint}>
          Use your review login in App Store Connect:{"\n"}review@calorieclick.ai / CalorieClick@123
        </Text>
      </SafeAreaView>
    );
  }

  // -----------------------
  // Main App UI
  // -----------------------
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.cameraWrap}>
        <CameraView
          style={styles.camera}
          ref={cameraRef}
          // barcode scanning only when in barcode mode
          onBarcodeScanned={
            mode === "barcode" && !scanned
              ? ({ data, type }) => {
                  setScanned(true);
                  doBarcodeLookup(data);
                  // reset after a moment so user can scan again
                  setTimeout(() => setScanned(false), 1500);
                }
              : undefined
          }
          barcodeScannerSettings={{
            barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "code39", "qr"],
          }}
        />
      </View>

      <View style={styles.panel}>
        <View style={styles.headerRow}>
          <Text style={styles.title}>CalorieClick.ai</Text>
          <TouchableOpacity onPress={doLogout} style={styles.logoutBtn}>
            <Text style={{ color: "#ddd", fontWeight: "700" }}>Logout</Text>
          </TouchableOpacity>
        </View>

        <Text style={{ color: "white", marginBottom: 6 }}>
          Plan: <Text style={{ fontWeight: "900" }}>{plan}</Text> {"  "}
          {rcReady ? "✅" : "⚠️"}
        </Text>

        {usage ? (
          <Text style={{ color: "#ccc", marginBottom: 10 }}>
            Remaining today: {usage.remaining_day} • Remaining month: {usage.remaining_month}
          </Text>
        ) : (
          <Text style={{ color: "#777", marginBottom: 10 }}>Loading limits…</Text>
        )}

        {/* Primary actions */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.primary, { flex: 1 }]}
            onPress={() => {
              setMode("camera");
              doAnalyze();
            }}
            disabled={loading}
          >
            <Text style={styles.btnText}>{loading ? "Working…" : "Snap & Analyze"}</Text>
          </TouchableOpacity>

          <View style={{ width: 10 }} />

          <TouchableOpacity
            style={[styles.btn, styles.secondary, { flex: 1 }]}
            onPress={() => setMode((m) => (m === "barcode" ? "camera" : "barcode"))}
            disabled={loading}
          >
            <Text style={styles.btnText}>{mode === "barcode" ? "Barcode (ON)" : "Barcode"}</Text>
          </TouchableOpacity>
        </View>

        <Text style={{ color: "#888", marginTop: 10 }}>
          Mode: <Text style={{ color: "#fff", fontWeight: "800" }}>{mode === "barcode" ? "Barcode" : "Camera"}</Text>
        </Text>

        <View style={{ height: 14 }} />

        {/* Upgrade */}
        <Text style={{ color: "#aaa", marginBottom: 8 }}>Upgrade</Text>

        <View style={styles.row}>
          <TouchableOpacity style={styles.planBtn} onPress={() => buy("elite")} disabled={loading}>
            <Text style={styles.planText}>Elite</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.planBtn} onPress={() => buy("advanced")} disabled={loading}>
            <Text style={styles.planText}>Advanced</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.row}>
          <TouchableOpacity style={styles.planBtn} onPress={() => buy("pro")} disabled={loading}>
            <Text style={styles.planText}>Pro</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.planBtn} onPress={() => buy("infinite")} disabled={loading}>
            <Text style={styles.planText}>Infinite</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.row}>
          <TouchableOpacity style={styles.planBtn} onPress={doRestore} disabled={loading}>
            <Text style={styles.planText}>Restore</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.planBtn} onPress={refreshUsage} disabled={loading}>
            <Text style={styles.planText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        {/* Trust line */}
        <Text style={styles.trustLine}>✅ Auto-renews monthly • Cancel anytime</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },

  cameraWrap: { flex: 1 },
  camera: { flex: 1 },

  panel: {
    padding: 16,
    backgroundColor: "rgba(0,0,0,0.85)",
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
  },

  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: "white", fontSize: 24, fontWeight: "900" },
  logoutBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.12)",
    borderRadius: 10,
  },

  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 10 },

  btn: {
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  primary: { backgroundColor: "#1e6fff" },
  secondary: { backgroundColor: "rgba(255,255,255,0.12)" },
  btnText: { color: "white", fontWeight: "900" },

  planBtn: {
    flex: 1,
    marginHorizontal: 4,
    paddingVertical: 14,
    borderRadius: 14,
    backgroundColor: "rgba(255,255,255,0.10)",
    alignItems: "center",
  },
  planText: { color: "#eee", fontWeight: "900" },

  trustLine: { color: "#aaa", marginTop: 14, textAlign: "center", fontSize: 12 },

  // Auth screen
  authWrap: { flex: 1, backgroundColor: "#000", padding: 18, justifyContent: "center" },
  authTitle: { color: "white", fontSize: 30, fontWeight: "900", textAlign: "center" },
  authSub: { color: "#aaa", textAlign: "center", marginBottom: 18 },
  input: {
    backgroundColor: "rgba(255,255,255,0.08)",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 14,
    color: "white",
    marginBottom: 12,
  },
  reviewHint: { color: "#666", textAlign: "center", marginTop: 18, fontSize: 12, lineHeight: 18 },
});

