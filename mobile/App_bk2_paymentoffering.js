// App.js (Expo / React Native)
// Features included:
// ✅ Supabase email/password login screen
// ✅ RevenueCat: configure Purchases, fetch "main" offering, purchase packages, restore
// ✅ Reads active entitlement (elite / advanced / pro / infinite) and updates UI
// ✅ Camera permission + Snap & Analyze button (photo capture stub)
// ✅ Barcode scan mode + Barcode button (scans EAN/UPC/QR etc) (lookup stub)
//
// IMPORTANT: You MUST fill in these constants:
// - SUPABASE_URL
// - SUPABASE_ANON_KEY
// - REVENUECAT_IOS_PUBLIC_API_KEY  (RevenueCat Project -> API keys -> Public SDK key (iOS))
//
// INSTALL (if missing):
//   npx expo install expo-camera
//   npm i react-native-purchases
//   npm i @supabase/supabase-js
//
// NOTES:
// - "Analyze" and "Barcode lookup" are stubs: replace ANALYZE_URL / BARCODE_LOOKUP_URL with your backend/edge-function URL.
// - RevenueCat purchases on device require StoreKit sandbox setup for testing (Apple sandbox tester account).

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import Purchases from "react-native-purchases";
import { createClient } from "@supabase/supabase-js";

/** =========================
 *  CONFIG — FILL THESE IN
 *  ========================= */
const SUPABASE_URL = "https://mgrwrthvhjpmbrvmvkeo.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncndydGh2aGpwbWJydm12a2VvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwOTcyNzEsImV4cCI6MjA4MzY3MzI3MX0.Zvzgq3zZv00_3flUniLIk2ZLckylO-SphsKFwZbkTPA";
const REVENUECAT_IOS_PUBLIC_API_KEY = "appl_SoteCFCeVzvTTQWIpwbClzFnBdq"; // e.g. "appl_XXXX..."

const OFFERING_ID = "main"; // you said your offering identifier is "main"
const ENTITLEMENTS = ["elite", "advanced", "pro", "infinite"];

// Optional backend endpoints (replace with your API / Edge Functions)
const ANALYZE_URL = ""; // e.g. "https://YOUR_DOMAIN/api/analyze"
const BARCODE_LOOKUP_URL = ""; // e.g. "https://YOUR_DOMAIN/api/barcode"

/** Create Supabase client */
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

/** Utility: find active entitlement */
function getActiveEntitlement(customerInfo) {
  try {
    const active = customerInfo?.entitlements?.active || {};
    const activeKeys = Object.keys(active);
    // if multiple, pick the "highest" in your preference order:
    for (const k of ["infinite", "pro", "advanced", "elite"]) {
      if (activeKeys.includes(k)) return k;
    }
    return "free";
  } catch {
    return "free";
  }
}

/** Utility: get package from offering by entitlement identifier */
function findPackageByEntitlement(offerings, entitlementId) {
  const off = offerings?.all?.[OFFERING_ID] || offerings?.current;
  if (!off) return null;

  // RevenueCat "Package" identifier is not necessarily same as entitlement.
  // Common setup: product identifiers match plan ids, and packages are mapped accordingly.
  // We'll try multiple strategies:
  const pkgs = off.availablePackages || [];

  // 1) Match by package.identifier (often: "$rc_monthly", etc - may not match)
  let pkg =
    pkgs.find((p) => (p.identifier || "").toLowerCase() === entitlementId.toLowerCase()) || null;

  // 2) Match by product identifier (you showed product IDs like: "advanced", "pro", "infinite", "calorieclick_elite")
  if (!pkg) {
    pkg =
      pkgs.find((p) => (p.product?.identifier || "").toLowerCase() === entitlementId.toLowerCase()) ||
      null;
  }

  // 3) Special-case: elite product id is "calorieclick_elite"
  if (!pkg && entitlementId === "elite") {
    pkg =
      pkgs.find((p) => (p.product?.identifier || "").toLowerCase() === "calorieclick_elite") ||
      null;
  }

  return pkg;
}

export default function App() {
  /** =========================
   *  AUTH STATE (Supabase)
   *  ========================= */
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  // Login form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  /** =========================
   *  REVENUECAT STATE
   *  ========================= */
  const [rcReady, setRcReady] = useState(false);
  const [offerings, setOfferings] = useState(null);
  const [customerInfo, setCustomerInfo] = useState(null);
  const [plan, setPlan] = useState("free");
  const [loading, setLoading] = useState(false);

  /** =========================
   *  CAMERA / UI STATE
   *  ========================= */
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [mode, setMode] = useState("camera"); // "camera" | "barcode"
  const [scanned, setScanned] = useState(false);

  /** =========================
   *  USER ID
   *  ========================= */
  const userId = useMemo(() => session?.user?.id || null, [session]);

  /** =========================
   *  INIT: Supabase session
   *  ========================= */
  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!mounted) return;
        setSession(data.session || null);
      } finally {
        if (mounted) setAuthLoading(false);
      }
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    return () => {
      mounted = false;
      sub?.subscription?.unsubscribe?.();
    };
  }, []);

  /** =========================
   *  INIT: RevenueCat (when logged in)
   *  ========================= */
  useEffect(() => {
    if (!userId) return;

    let cancelled = false;

    (async () => {
      try {
        setRcReady(false);

        if (Platform.OS === "ios") {
          Purchases.configure({ apiKey: REVENUECAT_IOS_PUBLIC_API_KEY, appUserID: userId });
        } else {
          // Add Android key later if needed
          Purchases.configure({ apiKey: "YOUR_ANDROID_PUBLIC_SDK_KEY", appUserID: userId });
        }

        // Optional: listen for updates
        const remove = Purchases.addCustomerInfoUpdateListener((info) => {
          if (cancelled) return;
          setCustomerInfo(info);
          setPlan(getActiveEntitlement(info));
        });

        const info = await Purchases.getCustomerInfo();
        if (cancelled) return;
        setCustomerInfo(info);
        setPlan(getActiveEntitlement(info));

        const off = await Purchases.getOfferings();
        if (cancelled) return;

        setOfferings(off);

        // Make sure "main" exists
        const hasMain = !!off?.all?.[OFFERING_ID] || off?.current?.identifier === OFFERING_ID;
        if (!hasMain) {
          console.log("Offerings loaded but 'main' not found. Available:", Object.keys(off?.all || {}));
        }

        setRcReady(true);

        return () => remove?.remove?.();
      } catch (e) {
        console.log("RevenueCat init error:", e);
        Alert.alert("RevenueCat error", e?.message || String(e));
      } finally {
        if (!cancelled) setRcReady(true); // so UI doesn't stay blocked
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  /** =========================
   *  AUTH actions
   *  ========================= */
  async function doLogin() {
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (e) {
      Alert.alert("Login failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function doSignup() {
    try {
      setAuthLoading(true);
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      Alert.alert("Check email", "Confirm your email if required, then login.");
    } catch (e) {
      Alert.alert("Signup failed", e?.message || String(e));
    } finally {
      setAuthLoading(false);
    }
  }

  async function doLogout() {
    await supabase.auth.signOut();
    setOfferings(null);
    setCustomerInfo(null);
    setPlan("free");
    setRcReady(false);
  }

  /** =========================
   *  RevenueCat actions
   *  ========================= */
  async function refreshOfferings() {
    try {
      setLoading(true);
      const off = await Purchases.getOfferings();
      setOfferings(off);

      const info = await Purchases.getCustomerInfo();
      setCustomerInfo(info);
      setPlan(getActiveEntitlement(info));
    } catch (e) {
      Alert.alert("Refresh failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function restore() {
    try {
      setLoading(true);
      const info = await Purchases.restorePurchases();
      setCustomerInfo(info);
      const active = getActiveEntitlement(info);
      setPlan(active);
      Alert.alert("Restored", `Plan: ${active}`);
    } catch (e) {
      Alert.alert("Restore failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function buy(entitlementId) {
    if (!userId) {
      Alert.alert("Login required", "Please login before purchasing.");
      return;
    }
    if (!offerings) {
      Alert.alert("Offerings not loaded yet", "Tap Refresh and try again.");
      return;
    }

    const pkg = findPackageByEntitlement(offerings, entitlementId);

    if (!pkg) {
      Alert.alert(
        "Package not found",
        `Could not find package for "${entitlementId}".\nCheck that RevenueCat packages/products are mapped to this offering.`
      );
      return;
    }

    try {
      setLoading(true);
      const { customerInfo: info } = await Purchases.purchasePackage(pkg);
      setCustomerInfo(info);
      const active = getActiveEntitlement(info);
      setPlan(active);
      Alert.alert("Subscribed", `Active plan: ${active}`);
    } catch (e) {
      // User cancelled
      if (e?.userCancelled) return;
      Alert.alert("Purchase failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  /** =========================
   *  Camera actions
   *  ========================= */
  async function snapAndAnalyze() {
    if (!userId) {
      Alert.alert("Login required", "Please login first.");
      return;
    }
    if (!permission?.granted) {
      Alert.alert("Camera permission", "Please grant camera permission.");
      return;
    }
    try {
      setLoading(true);

      // Take photo
      const photo = await cameraRef.current?.takePictureAsync?.({
        quality: 0.7,
        base64: false,
        exif: false,
      });

      if (!photo?.uri) throw new Error("Failed to capture image.");

      // If you have a backend: upload photo + get nutrition result
      // Replace this stub with your actual upload/analyze call
      if (!ANALYZE_URL) {
        Alert.alert("Captured ✅", "Photo captured. Add ANALYZE_URL to run analysis.");
        return;
      }

      const form = new FormData();
      form.append("userId", userId);
      form.append("image", {
        uri: photo.uri,
        name: "meal.jpg",
        type: "image/jpeg",
      });

      const res = await fetch(ANALYZE_URL, { method: "POST", body: form });
      const json = await res.json();

      if (!res.ok) throw new Error(json?.error || "Analyze failed");
      Alert.alert("Result", JSON.stringify(json, null, 2));
    } catch (e) {
      Alert.alert("Analyze failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleBarcodeScanned({ data, type }) {
    if (scanned) return;
    setScanned(true);

    if (!userId) {
      Alert.alert("Login required", "Please login first.");
      return;
    }

    try {
      setLoading(true);

      if (!BARCODE_LOOKUP_URL) {
        Alert.alert("Barcode scanned ✅", `${data}\n(type: ${type})\nAdd BARCODE_LOOKUP_URL to lookup nutrition.`);
        return;
      }

      const res = await fetch(BARCODE_LOOKUP_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId, barcode: data, symbology: type }),
      });

      const json = await res.json();
      if (!res.ok) throw new Error(json?.error || "Barcode lookup failed");
      Alert.alert("Barcode result", JSON.stringify(json, null, 2));
    } catch (e) {
      Alert.alert("Barcode failed", e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  /** =========================
   *  RENDER: Auth loading
   *  ========================= */
  if (authLoading) {
    return (
      <SafeAreaView style={[styles.screen, styles.center]}>
        <ActivityIndicator />
        <Text style={{ marginTop: 10, color: "#ddd" }}>Loading...</Text>
      </SafeAreaView>
    );
  }

  /** =========================
   *  RENDER: Login screen
   *  ========================= */
  if (!session?.user) {
    return (
      <SafeAreaView style={[styles.screen, styles.center, { padding: 24 }]}>
        <Text style={styles.h1}>CalorieClick.ai</Text>
        <Text style={styles.sub}>Login to continue</Text>

        <TextInput
          style={styles.input}
          placeholder="Email"
          placeholderTextColor="#777"
          autoCapitalize="none"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />

        <TextInput
          style={styles.input}
          placeholder="Password"
          placeholderTextColor="#777"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
        />

        <TouchableOpacity style={[styles.btn, styles.primary]} onPress={doLogin}>
          <Text style={styles.btnText}>Login</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.btn]} onPress={doSignup}>
          <Text style={styles.btnText}>Create account</Text>
        </TouchableOpacity>

        <Text style={{ marginTop: 18, color: "#888", textAlign: "center" }}>
          Use your review login in App Store Connect:
          {"\n"}review@calorieclick.ai / CalorieClick@123
        </Text>
      </SafeAreaView>
    );
  }

  /** =========================
   *  RENDER: Permissions
   *  ========================= */
  if (!permission) {
    return (
      <SafeAreaView style={[styles.screen, styles.center]}>
        <Text style={{ color: "#fff" }}>Loading camera permissions...</Text>
      </SafeAreaView>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={[styles.screen, styles.center, { padding: 24 }]}>
        <Text style={styles.h1}>Camera permission required</Text>
        <Text style={styles.sub}>We need camera access to scan meals and barcodes.</Text>
        <TouchableOpacity onPress={requestPermission} style={[styles.btn, styles.primary]}>
          <Text style={styles.btnText}>Grant Permission</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={doLogout} style={styles.btn}>
          <Text style={styles.btnText}>Logout</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  /** =========================
   *  RENDER: Main app
   *  ========================= */
  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.cameraWrap}>
        <CameraView
          ref={cameraRef}
          style={styles.camera}
          // barcode mode only:
          onBarcodeScanned={mode === "barcode" ? handleBarcodeScanned : undefined}
          barcodeScannerSettings={{
            barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e", "code128", "qr"],
          }}
        />
      </View>

      <View style={styles.panel}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.title}>CalorieClick.ai</Text>
            <Text style={styles.meta}>
              Plan: <Text style={{ fontWeight: "900" }}>{plan}</Text> {"  "}
              {rcReady ? "✅" : "⚠️"}
            </Text>
          </View>

          <TouchableOpacity onPress={doLogout} style={[styles.smallBtn]}>
            <Text style={styles.smallBtnText}>Logout</Text>
          </TouchableOpacity>
        </View>

        {/* Primary actions */}
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.btn, styles.primary, { flex: 1 }]}
            onPress={() => {
              setMode("camera");
              setScanned(false);
              snapAndAnalyze();
            }}
            disabled={loading}
          >
            <Text style={styles.btnText}>{loading ? "Working..." : "Snap & Analyze"}</Text>
          </TouchableOpacity>

          <View style={{ width: 10 }} />

          <TouchableOpacity
            style={[styles.btn, { flex: 1 }]}
            onPress={() => {
              setMode("barcode");
              setScanned(false);
              Alert.alert("Barcode mode", "Point camera at barcode.");
            }}
            disabled={loading}
          >
            <Text style={styles.btnText}>Barcode</Text>
          </TouchableOpacity>
        </View>

        {/* Mode helper */}
        <Text style={styles.helper}>
          Mode: <Text style={{ fontWeight: "800" }}>{mode === "barcode" ? "Barcode scan" : "Camera"}</Text>
          {mode === "barcode" ? " • Scan once, then tap 'Scan Again'." : ""}
        </Text>

        {mode === "barcode" && (
          <TouchableOpacity
            style={[styles.btn, { marginTop: 8 }]}
            onPress={() => setScanned(false)}
            disabled={loading}
          >
            <Text style={styles.btnText}>Scan Again</Text>
          </TouchableOpacity>
        )}

        {/* Paywall / upgrades */}
        <View style={{ height: 14 }} />
        <Text style={styles.section}>Upgrade</Text>

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

        <View style={styles.row}>
          <TouchableOpacity style={styles.btn} onPress={restore} disabled={loading}>
            <Text style={styles.btnText}>Restore</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.btn} onPress={refreshOfferings} disabled={loading}>
            <Text style={styles.btnText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.footerNote}>
          ✅ Auto-renews monthly • Cancel anytime{"\n"}
          Offerings: {offerings ? "loaded" : "not loaded"} • User: {userId?.slice(0, 8)}…
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#000" },
  center: { justifyContent: "center", alignItems: "center" },

  cameraWrap: { flex: 1 },
  camera: { flex: 1 },

  panel: {
    padding: 16,
    backgroundColor: "rgba(0,0,0,0.85)",
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.08)",
  },

  h1: { color: "#fff", fontSize: 26, fontWeight: "900", marginBottom: 6 },
  sub: { color: "#aaa", fontSize: 14, marginBottom: 16 },

  title: { color: "#fff", fontSize: 22, fontWeight: "900" },
  meta: { color: "#ddd", marginTop: 6 },

  section: { color: "#aaa", marginBottom: 8, fontSize: 13 },

  helper: { color: "#999", marginTop: 10, fontSize: 12 },

  row: { flexDirection: "row", gap: 10, marginTop: 10 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },

  btn: {
    backgroundColor: "#1c1c1c",
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  primary: { backgroundColor: "#2E7CF6" },
  btnText: { color: "#fff", fontWeight: "800" },

  smallBtn: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
    backgroundColor: "#1c1c1c",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
  },
  smallBtnText: { color: "#fff", fontWeight: "700" },

  input: {
    width: "100%",
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    padding: 12,
    borderRadius: 12,
    color: "#fff",
    marginBottom: 10,
  },

  footerNote: { color: "#777", fontSize: 11, marginTop: 12, textAlign: "center" },
});

