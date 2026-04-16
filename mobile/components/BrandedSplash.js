/**
 * BrandedSplash — Premium loading screen for cold starts.
 * Shows branded animation while fonts/auth load. Fades out when ready.
 */
import React, { useEffect, useRef } from "react";
import { View, Text, Animated, StyleSheet } from "react-native";

export function BrandedSplash({ visible, onFadeComplete }) {
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(0.9)).current;
  const pulseOpacity = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    // Logo entrance
    Animated.spring(scale, {
      toValue: 1,
      useNativeDriver: true,
      speed: 8,
      bounciness: 12,
    }).start();

    // Subtitle pulse
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseOpacity, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(pulseOpacity, { toValue: 0.4, duration: 800, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  useEffect(() => {
    if (!visible) {
      Animated.timing(opacity, {
        toValue: 0,
        duration: 400,
        useNativeDriver: true,
      }).start(() => onFadeComplete?.());
    }
  }, [visible]);

  return (
    <Animated.View style={[s.container, { opacity }]} pointerEvents={visible ? "auto" : "none"}>
      <Animated.View style={{ transform: [{ scale }] }}>
        <Text style={s.logo}>CalorieClick</Text>
        <Text style={s.logoAi}>.ai</Text>
      </Animated.View>
      <Animated.Text style={[s.tagline, { opacity: pulseOpacity }]}>
        Real menu data. Personalized to you.
      </Animated.Text>
    </Animated.View>
  );
}

const s = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#000000",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 999,
  },
  logo: {
    fontSize: 36,
    fontWeight: "900",
    color: "#f8fafc",
    fontFamily: "Inter_800ExtraBold",
    textAlign: "center",
  },
  logoAi: {
    fontSize: 36,
    fontWeight: "900",
    color: "#22c55e",
    fontFamily: "Inter_800ExtraBold",
    textAlign: "center",
    marginTop: -10,
  },
  tagline: {
    fontSize: 14,
    color: "#94a3b8",
    fontFamily: "Inter_400Regular",
    marginTop: 20,
    textAlign: "center",
  },
});
