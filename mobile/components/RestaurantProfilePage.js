import React, { useMemo } from "react";
import {
  Modal,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { PressableScale } from "./PressableScale";
import { MenuItemThumbnailPlaceholder } from "./MenuItemThumbnailPlaceholder";
import { colors, spacing, radius, typography, shadows } from "../designTokens";
import { premium } from "../ui/premiumSystem";
import { extractSwapSuggestions } from "../healthyNearbyUtils";
import { getAlertTrustLabel } from "../smartAlertTrustLabels";

function num(value) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMacro(value, suffix = "g") {
  const parsed = num(value);
  return parsed == null ? "--" : `${Math.round(parsed)}${suffix}`;
}

function scoreTone(score) {
  const rounded = Math.round(num(score) ?? 0);
  if (rounded >= 75) {
    return {
      bg: colors.success.bg,
      border: colors.success.border,
      text: colors.success.text,
    };
  }
  if (rounded >= 60) {
    return {
      bg: colors.amber.bg,
      border: colors.amber.border,
      text: colors.amber.text,
    };
  }
  return {
    bg: "rgba(127, 29, 29, 0.55)",
    border: colors.warning.primary,
    text: colors.warning.text,
  };
}

function proteinDensity(item) {
  const protein = num(
    item?.estimated_protein_g ??
      item?.protein_g ??
      item?.best_item_protein ??
      item?.protein
  );
  const calories = num(
    item?.estimated_calories ??
      item?.calories ??
      item?.best_item_calories
  );
  if (protein == null || protein <= 0) return 0;
  if (calories == null || calories <= 0) return protein;
  return protein / calories;
}

function normalizeMenuItem(item) {
  if (!item || typeof item !== "object") return null;
  const name = String(item.item_name ?? item.name ?? "").trim();
  if (!name) return null;

  const calories = num(item.estimated_calories ?? item.calories ?? item.best_item_calories);
  const protein = num(item.estimated_protein_g ?? item.protein_g ?? item.best_item_protein);
  const carbs = num(item.estimated_carbs_g ?? item.carbs_g ?? item.best_item_carbs);
  const fat = num(item.estimated_fat_g ?? item.fat_g ?? item.best_item_fat);

  return {
    ...item,
    item_name: name,
    estimated_calories: calories,
    estimated_protein_g: protein,
    estimated_carbs_g: carbs,
    estimated_fat_g: fat,
    proteinDensity: proteinDensity({
      estimated_calories: calories,
      estimated_protein_g: protein,
    }),
  };
}

function buildMenu(place) {
  const rawItems = []
    .concat(Array.isArray(place?.top_menu_items) ? place.top_menu_items : [])
    .concat(Array.isArray(place?.best_menu_items) ? place.best_menu_items : [])
    .concat(Array.isArray(place?.menu_items) ? place.menu_items : []);

  const fallbackName = String(place?.best_item_name ?? place?.best_order ?? "").trim();
  const fallbackItem =
    fallbackName
      ? {
          item_name: fallbackName,
          estimated_calories: num(place?.best_item_calories ?? place?.estimated_calories),
          estimated_protein_g: num(place?.best_item_protein ?? place?.estimated_protein_g),
          estimated_carbs_g: num(place?.best_item_carbs ?? place?.estimated_carbs_g),
          estimated_fat_g: num(place?.best_item_fat ?? place?.estimated_fat_g),
          image_url: place?.best_item_image_url || null,
          swap_suggestion: place?.swap_suggestion,
          better_swap: place?.better_swap,
          swap_suggestions: place?.swap_suggestions,
        }
      : null;

  if (fallbackItem) rawItems.push(fallbackItem);

  const deduped = [];
  const seen = new Set();

  rawItems.forEach((item) => {
    const normalized = normalizeMenuItem(item);
    if (!normalized) return;
    const key = normalized.item_name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    deduped.push(normalized);
  });

  return deduped.sort((a, b) => {
    const densityDelta = (b.proteinDensity || 0) - (a.proteinDensity || 0);
    if (Math.abs(densityDelta) > 0.0001) return densityDelta;

    const proteinDelta = (num(b.estimated_protein_g) ?? 0) - (num(a.estimated_protein_g) ?? 0);
    if (proteinDelta !== 0) return proteinDelta;

    const caloriesA = num(a.estimated_calories);
    const caloriesB = num(b.estimated_calories);
    if (caloriesA == null && caloriesB == null) return a.item_name.localeCompare(b.item_name);
    if (caloriesA == null) return 1;
    if (caloriesB == null) return -1;
    if (caloriesA !== caloriesB) return caloriesA - caloriesB;
    return a.item_name.localeCompare(b.item_name);
  });
}

function MacroPill({ label, value, accentStyle, textStyle }) {
  return (
    <View style={[styles.macroPill, accentStyle]}>
      <Text style={[styles.macroPillLabel, textStyle]}>{label}</Text>
      <Text style={[styles.macroPillValue, textStyle]}>{value}</Text>
    </View>
  );
}

export function RestaurantProfilePage({
  place,
  visible,
  onClose,
  onOpenInMaps,
  onImprove,
}) {
  const safePlace = place && typeof place === "object" ? place : null;
  const menuItems = useMemo(() => buildMenu(safePlace), [safePlace]);

  if (!visible || !safePlace) return null;

  const name = String(safePlace.place_name ?? safePlace.name ?? "").trim() || "Restaurant";
  const trustLabel = getAlertTrustLabel(safePlace);
  const score = num(safePlace.display_rank_score_100 ?? safePlace.health_score_100);
  const scoreColors = scoreTone(score);
  const featuredItem = menuItems[0] || null;
  const featuredSwap = extractSwapSuggestions(featuredItem, safePlace)[0] || "";
  const subtitleBits = [];

  const address = String(
    safePlace.vicinity ??
      safePlace.formatted_address ??
      safePlace.address ??
      ""
  ).trim();
  if (address) subtitleBits.push(address);
  if (safePlace.distance_meters != null) {
    const meters = num(safePlace.distance_meters);
    if (meters != null) {
      subtitleBits.push(meters >= 1000 ? `${(meters / 1000).toFixed(1)} km away` : `${Math.round(meters)} m away`);
    }
  }

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.page}>
          <View style={styles.topBar}>
            <PressableScale
              onPress={onClose}
              style={[premium.ctaGhost, premium.btnSm, styles.iconButton]}
            >
              <Text style={styles.iconButtonText}>Back</Text>
            </PressableScale>
            <View style={styles.topBarActions}>
              <PressableScale
                onPress={() => onImprove?.(safePlace)}
                style={[premium.ctaGhost, premium.btnSm, styles.actionButton]}
              >
                <Text style={styles.actionButtonText}>Improve</Text>
              </PressableScale>
              <PressableScale
                onPress={() => onOpenInMaps?.(safePlace)}
                style={[premium.ctaPrimary, premium.btnSm, styles.mapsButton]}
                haptic
              >
                <Text style={styles.mapsButtonText}>Open in Maps</Text>
              </PressableScale>
            </View>
          </View>

          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
          >
            <LinearGradient
              colors={["rgba(34,197,94,0.16)", "rgba(17,24,39,0.96)", "rgba(10,15,24,1)"]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.hero}
            >
              <View style={styles.heroHeader}>
                <View style={styles.heroTextWrap}>
                  <Text style={styles.placeName}>{name}</Text>
                  {subtitleBits.length ? (
                    <Text style={styles.placeSubtitle}>{subtitleBits.join(" · ")}</Text>
                  ) : null}
                  <View style={styles.trustChip}>
                    <Text style={styles.trustChipText}>{trustLabel}</Text>
                  </View>
                </View>
                {score != null ? (
                  <View
                    style={[
                      styles.scoreBadge,
                      {
                        backgroundColor: scoreColors.bg,
                        borderColor: scoreColors.border,
                      },
                    ]}
                  >
                    <Text style={[styles.scoreLabel, { color: scoreColors.text }]}>Health score</Text>
                    <Text style={[styles.scoreValue, { color: scoreColors.text }]}>
                      {Math.round(score)}
                    </Text>
                  </View>
                ) : null}
              </View>

              {featuredItem ? (
                <View style={styles.featuredCard}>
                  <View style={styles.featuredRow}>
                    <MenuItemThumbnailPlaceholder
                      item={featuredItem}
                      fallbackName={featuredItem.item_name}
                      style={styles.featuredThumb}
                      textStyle={styles.featuredThumbText}
                    />
                    <View style={styles.featuredContent}>
                      <View style={styles.bestPickBadge}>
                        <Text style={styles.bestPickBadgeText}>Best pick</Text>
                      </View>
                      <Text style={styles.featuredName}>{featuredItem.item_name}</Text>
                      <Text style={styles.featuredDensity}>
                        Protein density {(featuredItem.proteinDensity * 100).toFixed(1)}g per 100 kcal
                      </Text>
                    </View>
                  </View>
                  <View style={styles.featuredMacros}>
                    <MacroPill
                      label="Calories"
                      value={formatMacro(featuredItem.estimated_calories, " kcal")}
                      accentStyle={styles.featuredMacroNeutral}
                    />
                    <MacroPill
                      label="Protein"
                      value={formatMacro(featuredItem.estimated_protein_g)}
                      accentStyle={styles.featuredMacroStrong}
                      textStyle={styles.featuredMacroStrongText}
                    />
                    <MacroPill
                      label="Carbs"
                      value={formatMacro(featuredItem.estimated_carbs_g)}
                      accentStyle={styles.featuredMacroNeutral}
                    />
                    <MacroPill
                      label="Fat"
                      value={formatMacro(featuredItem.estimated_fat_g)}
                      accentStyle={styles.featuredMacroNeutral}
                    />
                  </View>
                  {featuredSwap ? (
                    <View style={styles.swapCallout}>
                      <Text style={styles.swapLabel}>Smart swap</Text>
                      <Text style={styles.swapText}>{featuredSwap}</Text>
                    </View>
                  ) : null}
                </View>
              ) : null}
            </LinearGradient>

            <View style={styles.sectionHeader}>
              <Text style={styles.sectionKicker}>Full menu</Text>
              <Text style={styles.sectionTitle}>
                {menuItems.length > 0
                  ? `${menuItems.length} item${menuItems.length === 1 ? "" : "s"} ranked by protein density`
                  : "Menu details unavailable"}
              </Text>
            </View>

            {menuItems.length > 0 ? (
              menuItems.map((item, index) => {
                const itemSwap = extractSwapSuggestions(item)[0] || "";
                const isBestPick = index === 0;

                return (
                  <View
                    key={`${item.item_name}-${index}`}
                    style={[styles.menuCard, isBestPick && styles.menuCardBest]}
                  >
                    <View style={styles.menuTopRow}>
                      <View style={styles.menuLeft}>
                        <MenuItemThumbnailPlaceholder
                          item={item}
                          fallbackName={item.item_name}
                          style={styles.menuThumb}
                          textStyle={styles.menuThumbText}
                        />
                        <View style={styles.menuTextWrap}>
                          <View style={styles.menuTitleRow}>
                            <Text style={styles.menuName}>{item.item_name}</Text>
                            {isBestPick ? (
                              <View style={styles.inlineBestBadge}>
                                <Text style={styles.inlineBestBadgeText}>Best pick</Text>
                              </View>
                            ) : null}
                          </View>
                          <Text style={styles.menuDensity}>
                            {(item.proteinDensity * 100).toFixed(1)}g protein / 100 kcal
                          </Text>
                        </View>
                      </View>
                      <View style={styles.rankBadge}>
                        <Text style={styles.rankText}>#{index + 1}</Text>
                      </View>
                    </View>

                    <View style={styles.macroGrid}>
                      <View style={styles.macroStat}>
                        <Text style={styles.macroLabel}>Calories</Text>
                        <Text style={styles.macroValue}>{formatMacro(item.estimated_calories, " kcal")}</Text>
                      </View>
                      <View style={styles.macroStat}>
                        <Text style={styles.macroLabel}>Protein</Text>
                        <Text style={styles.macroValueStrong}>{formatMacro(item.estimated_protein_g)}</Text>
                      </View>
                      <View style={styles.macroStat}>
                        <Text style={styles.macroLabel}>Carbs</Text>
                        <Text style={styles.macroValue}>{formatMacro(item.estimated_carbs_g)}</Text>
                      </View>
                      <View style={styles.macroStat}>
                        <Text style={styles.macroLabel}>Fat</Text>
                        <Text style={styles.macroValue}>{formatMacro(item.estimated_fat_g)}</Text>
                      </View>
                    </View>

                    {itemSwap ? (
                      <View style={styles.itemSwapRow}>
                        <Text style={styles.itemSwapLabel}>Smart swap</Text>
                        <Text style={styles.itemSwapText}>{itemSwap}</Text>
                      </View>
                    ) : null}
                  </View>
                );
              })
            ) : (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyTitle}>No menu items available yet</Text>
                <Text style={styles.emptyBody}>
                  Use Improve to report missing menu details for this restaurant.
                </Text>
              </View>
            )}
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

export default RestaurantProfilePage;

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#0a0f18",
  },
  page: {
    flex: 1,
    backgroundColor: "#0a0f18",
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.base,
    paddingBottom: spacing.md,
    gap: spacing.base,
  },
  topBarActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    flexShrink: 1,
  },
  iconButton: {
    minWidth: 72,
    backgroundColor: "rgba(17,24,39,0.92)",
    borderColor: "rgba(148,163,184,0.16)",
  },
  iconButtonText: {
    color: colors.text.primary,
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
  },
  actionButton: {
    backgroundColor: "rgba(17,24,39,0.92)",
    borderColor: "rgba(148,163,184,0.16)",
    paddingHorizontal: spacing.base,
  },
  actionButtonText: {
    color: colors.text.secondary,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  mapsButton: {
    paddingHorizontal: spacing.lg,
  },
  mapsButtonText: {
    color: colors.text.inverse,
    fontSize: typography.sm,
    fontWeight: typography.weight.bold,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: spacing.section * 2,
  },
  hero: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.base,
    paddingBottom: spacing.xl,
  },
  heroHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: spacing.base,
  },
  heroTextWrap: {
    flex: 1,
  },
  placeName: {
    color: colors.text.primary,
    fontSize: 31,
    lineHeight: 36,
    fontWeight: typography.weight.extrabold,
    letterSpacing: -0.6,
  },
  placeSubtitle: {
    marginTop: spacing.sm,
    color: colors.text.muted,
    fontSize: typography.md,
    lineHeight: 20,
  },
  trustChip: {
    alignSelf: "flex-start",
    marginTop: spacing.base,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: "rgba(17,24,39,0.94)",
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.18)",
  },
  trustChipText: {
    color: colors.text.secondary,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  scoreBadge: {
    minWidth: 110,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.base,
    borderRadius: radius.xl,
    borderWidth: 1,
    alignItems: "center",
    ...shadows.sm,
  },
  scoreLabel: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  scoreValue: {
    marginTop: spacing.xs,
    fontSize: 28,
    lineHeight: 32,
    fontWeight: typography.weight.extrabold,
  },
  featuredCard: {
    marginTop: spacing.xl,
    backgroundColor: "#111827",
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderColor: "rgba(34,197,94,0.24)",
    padding: spacing.lg,
    ...shadows.md,
  },
  featuredRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.base,
  },
  featuredThumb: {
    width: 72,
    height: 72,
    borderRadius: radius.lg,
  },
  featuredThumbText: {
    fontSize: 28,
  },
  featuredContent: {
    flex: 1,
    gap: spacing.xs,
  },
  bestPickBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.success.bg,
    borderWidth: 1,
    borderColor: colors.success.border,
  },
  bestPickBadgeText: {
    color: colors.success.text,
    fontSize: typography.xs,
    fontWeight: typography.weight.bold,
  },
  featuredName: {
    color: colors.text.primary,
    fontSize: typography.hero,
    lineHeight: 24,
    fontWeight: typography.weight.bold,
  },
  featuredDensity: {
    color: colors.accent.primary,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  featuredMacros: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  featuredMacroNeutral: {
    backgroundColor: "rgba(15,23,42,0.75)",
    borderColor: "rgba(148,163,184,0.16)",
  },
  featuredMacroStrong: {
    backgroundColor: colors.success.bg,
    borderColor: colors.success.border,
  },
  featuredMacroStrongText: {
    color: colors.success.text,
  },
  macroPill: {
    minWidth: 104,
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  macroPillLabel: {
    color: colors.text.muted,
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
  },
  macroPillValue: {
    marginTop: spacing.xs,
    color: colors.text.primary,
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
  },
  swapCallout: {
    marginTop: spacing.lg,
    padding: spacing.base,
    borderRadius: radius.lg,
    backgroundColor: "rgba(15,65,38,0.55)",
    borderWidth: 1,
    borderColor: "rgba(34,197,94,0.22)",
  },
  swapLabel: {
    color: colors.success.text,
    fontSize: typography.xs,
    fontWeight: typography.weight.bold,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  swapText: {
    marginTop: spacing.xs,
    color: colors.text.secondary,
    fontSize: typography.md,
    lineHeight: 20,
  },
  sectionHeader: {
    paddingHorizontal: spacing.lg,
    marginTop: spacing.section,
    marginBottom: spacing.base,
  },
  sectionKicker: {
    color: colors.slate.muted,
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.9,
  },
  sectionTitle: {
    marginTop: spacing.xs,
    color: colors.text.primary,
    fontSize: typography.xxl,
    lineHeight: 24,
    fontWeight: typography.weight.bold,
  },
  menuCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.base,
    backgroundColor: "#111827",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.12)",
    padding: spacing.lg,
  },
  menuCardBest: {
    borderColor: "rgba(34,197,94,0.30)",
    shadowColor: "#22c55e",
    shadowOpacity: 0.12,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    elevation: 4,
  },
  menuTopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.base,
  },
  menuLeft: {
    flexDirection: "row",
    gap: spacing.base,
    flex: 1,
  },
  menuThumb: {
    width: 52,
    height: 52,
    borderRadius: radius.md,
  },
  menuThumbText: {
    fontSize: 22,
  },
  menuTextWrap: {
    flex: 1,
  },
  menuTitleRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  menuName: {
    flexShrink: 1,
    color: colors.text.primary,
    fontSize: typography.lg,
    lineHeight: 22,
    fontWeight: typography.weight.bold,
  },
  inlineBestBadge: {
    marginTop: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.success.bg,
  },
  inlineBestBadgeText: {
    color: colors.success.text,
    fontSize: typography.xs,
    fontWeight: typography.weight.bold,
  },
  menuDensity: {
    marginTop: spacing.xs,
    color: colors.accent.primary,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  rankBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: "rgba(15,23,42,0.82)",
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.16)",
  },
  rankText: {
    color: colors.text.secondary,
    fontSize: typography.sm,
    fontWeight: typography.weight.bold,
  },
  macroGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  macroStat: {
    minWidth: 110,
    flexGrow: 1,
    backgroundColor: "rgba(15,23,42,0.72)",
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.12)",
  },
  macroLabel: {
    color: colors.text.muted,
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
  },
  macroValue: {
    marginTop: spacing.xs,
    color: colors.text.primary,
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
  },
  macroValueStrong: {
    marginTop: spacing.xs,
    color: colors.success.text,
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
  },
  itemSwapRow: {
    marginTop: spacing.base,
    paddingTop: spacing.base,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(148,163,184,0.16)",
  },
  itemSwapLabel: {
    color: colors.success.text,
    fontSize: typography.xs,
    fontWeight: typography.weight.bold,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  itemSwapText: {
    marginTop: spacing.xs,
    color: colors.text.secondary,
    fontSize: typography.sm,
    lineHeight: 18,
  },
  emptyCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.base,
    backgroundColor: "#111827",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.12)",
    padding: spacing.xl,
  },
  emptyTitle: {
    color: colors.text.primary,
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
  },
  emptyBody: {
    marginTop: spacing.sm,
    color: colors.text.muted,
    fontSize: typography.md,
    lineHeight: 20,
  },
});
