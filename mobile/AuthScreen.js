import React, { useState } from "react";
import { View, Text, TextInput, Pressable, Alert, StyleSheet } from "react-native";
import { supabase } from "./supabase";

export default function AuthScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const signUp = async () => {
    setLoading(true);
    const { error } = await supabase.auth.signUp({ email, password });
    setLoading(false);
    if (error) return Alert.alert("Sign up error", error.message);
    Alert.alert("Check your email", "Confirm your email to finish signup.");
  };

  const signIn = async () => {
    setLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    if (error) return Alert.alert("Login error", error.message);
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.h1}>Kcal Scan</Text>
      <Text style={styles.sub}>Login to save meal history</Text>

      <TextInput
        style={styles.input}
        placeholder="Email"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />

      <Pressable style={[styles.btn, styles.primary]} onPress={signIn} disabled={loading}>
        <Text style={styles.btnText}>{loading ? "..." : "Sign In"}</Text>
      </Pressable>

      <Pressable style={[styles.btn]} onPress={signUp} disabled={loading}>
        <Text style={styles.btnText}>Create Account</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#000", padding: 20, justifyContent: "center" },
  h1: { color: "white", fontSize: 32, fontWeight: "800", marginBottom: 6 },
  sub: { color: "#aaa", marginBottom: 20 },
  input: { backgroundColor: "#111", color: "white", padding: 14, borderRadius: 12, marginBottom: 12 },
  btn: { padding: 14, borderRadius: 12, backgroundColor: "#222", marginTop: 10, alignItems: "center" },
  primary: { backgroundColor: "#0A84FF" },
  btnText: { color: "white", fontWeight: "700" },
});

