/**
 * EmptyState — Premium illustrated empty states.
 * Shows when no data is available (no places, no meals, no coach data).
 * Uses emoji illustrations + message + optional CTA.
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { PressableScale } from "./PressableScale";

const PRESETS = {
  no_places: {
    icon: "🗺️",
    title: "No restaurants found nearby",
    message: "Try expanding your search radius or moving to a different area",
  },
  no_meals: {
    icon: "🍽️",
    title: "No meals logged today",
    message: "Scan or type your first meal to start tracking",
  },
  no_coach: {
    icon: "🎯",
    title: "Coach is warming up",
    message: "Log a few meals and your personalized insights will appear here",
  },
  no_history: {
    icon: "📊",
    title: "No history yet",
    message: "Your meal history will build up over time",
  },
  loading_error: {
    icon: "⚡",
    title: "Something went wrong",
    message: "Pull down to refresh and try again",
  },
  location_needed: {
    icon: "📍",
    title: "Location access needed",
    message: "Enable location to find healthy restaurants near you",
  },
};

export function EmptyState({
  preset,
  icon,
  title,
  message,
  ctaLabel,
  onCta,
}) {
  const p = PRESETS[preset] || {};
  const displayIcon = icon || p.icon || "💡";
  const displayTitle = title || p.title || "Nothing here yet";
  const displayMessage = message || p.message || "";

  return (
    <View style={s.container}>
      <Text style={s.icon}>{displayIcon}</Text>
      <Text style={s.title}>{displayTitle}</Text>
      {displayMessage ? <Text style={s.message}>{displayMessage}</Text> : null}
      {ctaLabel && onCta ? (
        <PressableScale style={s.cta} onPress={onCta} haptic>
          <Text style={s.ctaText}>{ctaLabel}</Text>
        </PressableScale>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 48,
    paddingHorizontal: 32,
    gap: 10,
  },
  icon: {
    fontSize: 48,
    marginBottom: 8,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: "#f8fafc",
    textAlign: "center",
    fontFamily: "Inter_700Bold",
  },
  message: {
    fontSize: 14,
    color: "#94a3b8",
    textAlign: "center",
    lineHeight: 20,
    fontFamily: "Inter_400Regular",
    maxWidth: 280,
  },
  cta: {
    marginTop: 12,
    backgroundColor: "#22c55e",
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 12,
  },
  ctaText: {
    fontSize: 14,
    fontWeight: "700",
    color: "#052e16",
    fontFamily: "Inter_700Bold",
  },
});
