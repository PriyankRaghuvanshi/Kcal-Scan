import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Image } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { spacing, radius, typography } from "../designTokens";
import { extractSwapSuggestions } from "../healthyNearbyUtils";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function pickPhotoUri(card) {
  const candidates = [
    card?.photo_url,
    card?.image_url,
    card?.hero_image_url,
    card?.top_menu_item?.photo_url,
  ];
  for (const c of candidates) {
    const s = String(c || "").trim();
    if (s) return s;
  }
  return "";
}

function hashPair(seed) {
  const s = String(seed || "meal");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  const pairs = [
    ["#22c55e", "#06b6d4"],
    ["#10b981", "#84cc16"],
    ["#3b82f6", "#06b6d4"],
    ["#16a34a", "#059669"],
  ];
  return pairs[h % pairs.length];
}

function MealTile({ card, onPress }) {
  const placeName = String(card?.place_name || card?.title || "Nearby meal suggestion").trim();
  const itemName = String(card?.best_item_name || card?.recommended_order || card?.best_order || "").trim();
  const subtitle = itemName || "Smart nearby meal pick";
  const score = Math.max(0, Math.min(100, Math.round(num(card?.display_rank_score_100) ?? num(card?.health_score_100) ?? 74)));
  const photoUri = pickPhotoUri(card);
  const [c0, c1] = hashPair(placeName + subtitle);
  const swapFirst = extractSwapSuggestions(card)[0] || "";

  return (
    <TouchableOpacity style={styles.tileWrap} onPress={onPress} activeOpacity={0.9}>
      <View style={styles.tileMedia}>
        {photoUri ? (
          <Image source={{ uri: photoUri }} resizeMode="cover" style={styles.tileImage} />
        ) : (
          <LinearGradient colors={[c0, c1]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.tilePlaceholder}>
            <Text style={styles.tileEmoji}>🍽</Text>
          </LinearGradient>
        )}
        <View style={styles.tileCheckBubble}>
          <Text style={styles.tileCheckText}>✓</Text>
        </View>
      </View>
      <View style={styles.tileBody}>
        <Text style={styles.tileTitle} numberOfLines={2}>
          {placeName}
        </Text>
        <Text style={styles.tileSubtitle} numberOfLines={2}>
          {subtitle}
        </Text>
        {swapFirst ? (
          <Text style={styles.tileSwapHint} numberOfLines={2}>
            Better swap: {swapFirst}
          </Text>
        ) : null}
        <View style={styles.tileMetaRow}>
          <View style={styles.tileAvatar} />
          <Text style={styles.tileMetaText} numberOfLines={1}>
            {`${score} score`}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );
}

export function HealthyNearbyDecisionShowcase({
  decision,
  onPrimaryPress,
  onCardPress,
}) {
  const cards = Array.isArray(decision?.cards) ? decision.cards.filter((x) => x && typeof x === "object") : [];
  const hero = cards[0] || null;
  const tileCards = cards.slice(0, 2);
  if (!hero || !tileCards.length) return null;

  const heroText = String(decision?.title || "What should I eat right now?").trim() || "What should I eat right now?";
  const heroSub = String(decision?.subtitle || "Decision mode turns your remaining macros into smart nearby meal picks.").trim();
  const heroSwapFirst = extractSwapSuggestions(hero)[0] || "";

  return (
    <View style={styles.root}>
      <Text style={styles.headerTitle} numberOfLines={2}>{heroText}</Text>
      {!!heroSub ? <Text style={styles.headerSub} numberOfLines={2}>{heroSub}</Text> : null}
      <View style={styles.headerAccent} />

      <LinearGradient colors={["#22c55e", "#34d399", "#0ea5e9"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.heroCard}>
        <View style={styles.heroTextWrap}>
          <Text style={styles.heroTitle}>AI coach</Text>
          <Text style={styles.heroSubtitle}>Recommendation</Text>
          <Text style={styles.heroBody} numberOfLines={2}>
            {String(hero?.why_this_works || "Meal picks tuned to your remaining calories and protein.")}
          </Text>
          {heroSwapFirst ? (
            <Text style={styles.heroSwapHint} numberOfLines={2}>
              Better swap: {heroSwapFirst}
            </Text>
          ) : null}
          <TouchableOpacity style={styles.heroCta} onPress={onPrimaryPress} activeOpacity={0.88}>
            <Text style={styles.heroCtaText}>CalorieClick. ›</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.heroPlateWrap}>
          <Text style={styles.heroPlate}>🍱</Text>
        </View>
      </LinearGradient>

      <View style={styles.tilesRow}>
        {tileCards.map((card, i) => (
          <MealTile key={`decision-tile-${i}`} card={card} onPress={() => onCardPress && onCardPress(card)} />
        ))}
      </View>

      <LinearGradient colors={["#18181b", "#0f172a"]} style={styles.brandBar}>
        <Text style={styles.brandText}>CalorieClick.ai</Text>
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    marginTop: spacing.md,
    backgroundColor: "#050b18",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: "rgba(59,130,246,0.25)",
    padding: spacing.md,
  },
  headerTitle: {
    color: "#f8fafc",
    fontSize: 36,
    lineHeight: 40,
    fontWeight: "900",
    letterSpacing: -0.7,
  },
  headerSub: {
    color: "#cbd5e1",
    fontSize: typography.base,
    marginTop: 8,
    lineHeight: 22,
  },
  headerAccent: {
    width: 92,
    height: 5,
    borderRadius: 3,
    backgroundColor: "#22c55e",
    marginTop: 10,
    marginBottom: 14,
  },
  heroCard: {
    borderRadius: radius.xl,
    padding: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    overflow: "hidden",
  },
  heroTextWrap: { flex: 1, paddingRight: 10 },
  heroTitle: {
    color: "#ecfdf5",
    fontSize: 42,
    lineHeight: 46,
    fontWeight: "900",
    letterSpacing: -0.7,
  },
  heroSubtitle: {
    color: "#ecfeff",
    fontSize: 34,
    lineHeight: 38,
    fontWeight: "800",
    marginTop: 2,
    letterSpacing: -0.4,
  },
  heroBody: {
    color: "#dcfce7",
    fontSize: typography.sm,
    marginTop: 6,
    lineHeight: 18,
  },
  heroSwapHint: {
    color: "#fef9c3",
    fontSize: typography.sm,
    fontWeight: "700",
    marginTop: 8,
    lineHeight: 18,
  },
  heroCta: {
    alignSelf: "flex-start",
    marginTop: 10,
    backgroundColor: "#0f172a",
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
  },
  heroCtaText: {
    color: "#f8fafc",
    fontSize: typography.sm,
    fontWeight: "700",
  },
  heroPlateWrap: {
    width: 118,
    height: 118,
    borderRadius: 59,
    backgroundColor: "rgba(255,255,255,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  heroPlate: {
    fontSize: 58,
  },
  tilesRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 12,
  },
  tileWrap: {
    flex: 1,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: "#f8fafc",
  },
  tileMedia: {
    height: 126,
    backgroundColor: "#dbeafe",
  },
  tileImage: { width: "100%", height: "100%" },
  tilePlaceholder: { flex: 1, alignItems: "center", justifyContent: "center" },
  tileEmoji: { fontSize: 38 },
  tileCheckBubble: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "#0f172a",
    alignItems: "center",
    justifyContent: "center",
  },
  tileCheckText: { color: "#fde047", fontWeight: "900" },
  tileBody: {
    paddingHorizontal: 10,
    paddingTop: 9,
    paddingBottom: 10,
    minHeight: 102,
  },
  tileTitle: {
    color: "#0f172a",
    fontSize: 32,
    lineHeight: 34,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
  tileSubtitle: {
    color: "#1f2937",
    fontSize: 18,
    lineHeight: 22,
    marginTop: 3,
    fontWeight: "600",
  },
  tileSwapHint: {
    color: "#a16207",
    fontSize: 13,
    fontWeight: "700",
    marginTop: 6,
    lineHeight: 17,
  },
  tileMetaRow: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  tileAvatar: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: "#cbd5e1",
  },
  tileMetaText: {
    color: "#6b7280",
    fontSize: typography.sm,
    fontWeight: "600",
  },
  brandBar: {
    marginTop: 10,
    borderRadius: radius.lg,
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
  },
  brandText: {
    color: "#f8fafc",
    fontSize: 34,
    lineHeight: 36,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
});
