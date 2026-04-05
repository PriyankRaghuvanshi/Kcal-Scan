/**
 * Grid tile — colourful marketing-style browse (gradients, badges).
 */

import React, { useMemo } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Image, Platform } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { spacing, radius } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function hashHue(name) {
  let h = 0;
  const s = String(name || "x");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h >>> 0;
}

// Vibrant food-photo–like gradients (top → bottom), close to promo hero imagery.
const GRADIENT_PAIRS = [
  ["#f97316", "#fb7185"], // orange → rose
  ["#eab308", "#f43f5e"], // amber → pink
  ["#22d3ee", "#6366f1"], // cyan → indigo
  ["#34d399", "#0d9488"], // emerald → teal
  ["#a78bfa", "#ec4899"], // violet → fuchsia
  ["#fdba74", "#ef4444"], // peach → red
  ["#4ade80", "#16a34a"], // lime → green
  ["#38bdf8", "#7c3aed"], // sky → purple
];

const COMPACT_ANDROID = Platform.OS === "android";

export function HealthyNearbyGridTile({ place, index, onPress, formatDistance, selected, getStableId }) {
  const name = String(place?.place_name ?? place?.name ?? "Restaurant").trim() || "Restaurant";
  const subtitle = String(place?.best_item_name ?? place?.best_order ?? place?.primary_type ?? "")
    .trim()
    .replace(/_/g, " ")
    .slice(0, 44);
  const score = num(place?.display_rank_score_100) ?? num(place?.health_score_100);
  const kcal = num(place?.best_item_calories) ?? num(place?.estimated_calories);
  const protein = num(place?.best_item_protein) ?? num(place?.estimated_protein_g);
  const photoUri = String(place?.photo_url || place?.image_url || "").trim();

  const pairIdx = useMemo(() => hashHue(name) % GRADIENT_PAIRS.length, [name]);
  const [c0, c1] = GRADIENT_PAIRS[pairIdx];

  const footerParts = [];
  if (kcal != null) footerParts.push(`${Math.round(kcal)} kcal`);
  if (protein != null) footerParts.push(`${Math.round(protein)}g protein`);
  if (formatDistance && place?.distance_meters != null) {
    const d = formatDistance(place.distance_meters);
    if (d) footerParts.push(d);
  }
  const footer = footerParts.length ? footerParts.join(" · ") : "Tap for details";

  const sid = getStableId ? getStableId(place, index) : "";
  const isSel = Boolean(selected && sid && String(selected) === String(sid));

  return (
    <TouchableOpacity
      style={[styles.wrap, isSel && styles.wrapSelected]}
      onPress={() => onPress && onPress(place, index)}
      activeOpacity={0.88}
    >
      <View style={styles.imageShell}>
        {photoUri ? (
          <Image source={{ uri: photoUri }} style={styles.image} resizeMode="cover" />
        ) : (
          <LinearGradient
            colors={[c0, c1]}
            start={{ x: 0.1, y: 0 }}
            end={{ x: 0.9, y: 1 }}
            style={styles.placeholder}
          >
            <View style={styles.placeholderShine} pointerEvents="none" />
            <Text style={styles.placeholderEmoji}>🍽</Text>
          </LinearGradient>
        )}
        {score != null ? (
          <LinearGradient
            colors={["#4ade80", "#22c55e"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.scoreBubble}
          >
            <Text style={styles.scoreText}>{Math.round(score)}</Text>
          </LinearGradient>
        ) : null}
        <LinearGradient
          colors={["rgba(255,255,255,0.95)", "#fde68a"]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.forkBubble}
        >
          <Text style={styles.forkText}>🍴</Text>
        </LinearGradient>
      </View>
      <LinearGradient
        colors={["#141824", "#0f1219"]}
        style={styles.textBlock}
      >
        <View style={styles.textAccentLine} />
        <Text style={styles.title} numberOfLines={1}>
          {name}
        </Text>
        <Text style={styles.subtitle} numberOfLines={2}>
          {subtitle || "Healthy pick nearby"}
        </Text>
        <Text style={styles.footer} numberOfLines={1}>
          {footer}
        </Text>
      </LinearGradient>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    marginHorizontal: COMPACT_ANDROID ? 4 : 5,
    marginBottom: COMPACT_ANDROID ? spacing.sm + 2 : spacing.md + 2,
    minWidth: 0,
    borderRadius: radius.xl,
    ...Platform.select({
      ios: {
        shadowColor: "#7c3aed",
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.22,
        shadowRadius: 12,
      },
      android: { elevation: 10 },
    }),
  },
  wrapSelected: {
    borderRadius: radius.xl,
    borderWidth: 2,
    borderColor: "#fbbf24",
  },
  imageShell: {
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    overflow: "hidden",
    height: COMPACT_ANDROID ? 112 : 128,
    backgroundColor: "#1e1b4b",
  },
  image: {
    width: "100%",
    height: "100%",
  },
  placeholder: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  placeholderShine: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(255,255,255,0.18)",
    transform: [{ translateX: -40 }, { rotate: "18deg" }, { scale: 1.4 }],
  },
  placeholderEmoji: {
    fontSize: COMPACT_ANDROID ? 34 : 42,
    textShadowColor: "rgba(0,0,0,0.35)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 6,
  },
  scoreBubble: {
    position: "absolute",
    top: 10,
    left: 10,
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.98)",
    ...Platform.select({
      ios: {
        shadowColor: "#22c55e",
        shadowOffset: { width: 0, height: 3 },
        shadowOpacity: 0.7,
        shadowRadius: 5,
      },
      android: { elevation: 6 },
    }),
  },
  scoreText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "900",
  },
  forkBubble: {
    position: "absolute",
    top: 10,
    right: 10,
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.85)",
  },
  forkText: {
    fontSize: 16,
  },
  textBlock: {
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    borderWidth: 1,
    borderTopWidth: 0,
    borderColor: "rgba(124,58,237,0.45)",
    paddingHorizontal: COMPACT_ANDROID ? spacing.sm : spacing.sm + 2,
    paddingTop: COMPACT_ANDROID ? spacing.sm : spacing.sm + 4,
    paddingBottom: COMPACT_ANDROID ? spacing.xs + 2 : spacing.sm + 2,
    minHeight: COMPACT_ANDROID ? 72 : 82,
    overflow: "hidden",
  },
  textAccentLine: {
    position: "absolute",
    top: 0,
    left: 12,
    right: 12,
    height: 3,
    borderRadius: 2,
    backgroundColor: "#a855f7",
    opacity: 0.9,
  },
  title: {
    color: "#fafafa",
    fontSize: COMPACT_ANDROID ? 14 : 16,
    fontWeight: "800",
    letterSpacing: -0.2,
  },
  subtitle: {
    color: "#c4b5fd",
    fontSize: COMPACT_ANDROID ? 12 : 13,
    marginTop: COMPACT_ANDROID ? 3 : 4,
    lineHeight: COMPACT_ANDROID ? 16 : 18,
    fontWeight: "500",
  },
  footer: {
    color: "#86efac",
    fontSize: COMPACT_ANDROID ? 11 : 12,
    marginTop: COMPACT_ANDROID ? 6 : 8,
    fontWeight: "700",
  },
});
