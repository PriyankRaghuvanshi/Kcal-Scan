/**
 * PlaceDetailSheet — Premium bottom sheet for restaurant detail.
 * Slides up on tap, swipe-down to dismiss. Zero external dependencies.
 */
import React, { useRef } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  ScrollView,
  Image,
  PanResponder,
  Dimensions,
  Platform,
  StyleSheet,
} from "react-native";
import { BlurView } from "expo-blur";
import { colors, spacing, radius, typography } from "../designTokens";
import { ScoreBadge } from "./ScoreBadge";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { PressableScale } from "./PressableScale";
import { MenuItemThumbnailPlaceholder } from "./MenuItemThumbnailPlaceholder";

const { height: SCREEN_H } = Dimensions.get("window");
const SHEET_H = SCREEN_H * 0.72;

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function MacroBar({ protein, carbs, fat }) {
  const total = (protein || 0) + (carbs || 0) + (fat || 0);
  if (!total) return null;
  const pPct = ((protein || 0) / total) * 100;
  const cPct = ((carbs || 0) / total) * 100;
  const fPct = ((fat || 0) / total) * 100;
  return (
    <View style={s.macroBarWrap}>
      <View style={s.macroBarTrack}>
        {pPct > 0 && <View style={[s.macroSeg, { flex: pPct, backgroundColor: "#22c55e" }]} />}
        {cPct > 0 && <View style={[s.macroSeg, { flex: cPct, backgroundColor: "#f59e0b" }]} />}
        {fPct > 0 && <View style={[s.macroSeg, { flex: fPct, backgroundColor: "#93c5fd" }]} />}
      </View>
      <View style={s.macroLegend}>
        <Text style={[s.macroLegendDot, { color: "#22c55e" }]}>● </Text>
        <Text style={s.macroLegendText}>Protein {Math.round(protein || 0)}g</Text>
        <Text style={[s.macroLegendDot, { color: "#f59e0b" }]}>  ● </Text>
        <Text style={s.macroLegendText}>Carbs {Math.round(carbs || 0)}g</Text>
        <Text style={[s.macroLegendDot, { color: "#93c5fd" }]}>  ● </Text>
        <Text style={s.macroLegendText}>Fat {Math.round(fat || 0)}g</Text>
      </View>
    </View>
  );
}

export function PlaceDetailSheet({ visible, place, onClose, onOpenInMaps }) {
  const panRef = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, g) => g.dy > 8 && Math.abs(g.dy) > Math.abs(g.dx),
      onPanResponderRelease: (_, g) => {
        if (g.dy > 80) onClose?.();
      },
    })
  ).current;

  if (!visible || !place) return null;

  const name = String(place.place_name ?? place.name ?? "").trim() || "Restaurant";
  const score = num(place.display_rank_score_100) ?? num(place.health_score_100);
  const bestItem = String(place.best_item_name ?? place.best_order ?? "").trim();
  const calories = num(place.best_item_calories ?? place.estimated_calories);
  const protein = num(place.best_item_protein ?? place.estimated_protein_g);
  const carbs = num(place.best_item_carbs ?? place.estimated_carbs_g);
  const fat = num(place.best_item_fat ?? place.estimated_fat_g);
  const reason = String(place.rank_reason_short ?? place.why_this_ranked_here ?? "").trim();
  // Null contract: no real menu evidence backs the macros.
  const isNutritionUnknown =
    place.nutrition_status === "unknown" || place.nutrition_evidence_backed === false;

  const topItem = place.top_menu_item && typeof place.top_menu_item === "object" ? place.top_menu_item : null;
  const imageRaw = String((topItem && topItem.image_url) || place.best_item_image_url || "").trim();
  const image = imageRaw.startsWith("https://") ? imageRaw : null;
  const bestImageItem = topItem || {
    item_name: bestItem,
    estimated_protein_g: protein,
    estimated_carbs_g: carbs,
    negative_flags: place.negative_flags,
  };

  const gv = place.goal_variants;
  const variants = [];
  if (gv) {
    for (const [label, key] of [["High protein", "high_protein"], ["Lowest cal", "lowest_calorie"], ["Fat-loss", "fat_loss"]]) {
      const v = gv[key];
      if (v && v.item_name) {
        variants.push({ label, name: v.item_name, kcal: num(v.estimated_calories), protein: num(v.estimated_protein_g) });
      }
    }
  }

  const usual = place.usual_meal;
  const usualName = usual && String(usual.item_name || "").trim();

  // Full menu items (all chain items, not just best pick)
  const allMenuItems = (
    place.top_menu_items || place.best_menu_items || []
  ).filter(it => it && typeof it === "object" && it.item_name);
  // Add macro fit pct to each
  const remainingPro = num(place.remaining_protein_g);
  const remainingCal = num(place.remaining_calories);
  const menuWithFit = allMenuItems.map(it => {
    const pro = num(it.estimated_protein_g);
    const cal = num(it.estimated_calories);
    return {
      ...it,
      protein_fill_pct: remainingPro > 0 && pro > 0 ? Math.min(100, Math.round((pro / remainingPro) * 100)) : null,
      calorie_use_pct: remainingCal > 0 && cal > 0 ? Math.min(100, Math.round((cal / remainingCal) * 100)) : null,
    };
  }).sort((a, b) => (b.protein_fill_pct || 0) - (a.protein_fill_pct || 0));

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View style={s.overlay}>
        {Platform.OS === "ios" ? (
          <BlurView intensity={40} tint="dark" style={StyleSheet.absoluteFill}>
            <TouchableOpacity style={s.backdrop} activeOpacity={1} onPress={onClose} />
          </BlurView>
        ) : (
          <TouchableOpacity style={s.backdrop} activeOpacity={1} onPress={onClose} />
        )}
        <View style={s.sheet} {...panRef.panHandlers}>
          <View style={s.handleRow}>
            <View style={s.handle} />
          </View>
          <ScrollView style={s.scroll} showsVerticalScrollIndicator={false} bounces>
            {/* Header */}
            <View style={s.header}>
              <View style={{ flex: 1 }}>
                <Text style={s.placeName} numberOfLines={2}>{name}</Text>
                <ConfidenceBadge place={place} />
              </View>
              {Number.isFinite(score) && <ScoreBadge score={score} isTop={score >= 80} size="md" />}
            </View>

            {/* Best Pick */}
            <View style={s.section}>
              <Text style={s.kicker}>BEST PICK FOR YOU</Text>
              <View style={s.bestRow}>
                {image ? (
                  <Image source={{ uri: image }} style={s.bestImage} resizeMode="cover" />
                ) : (
                  <MenuItemThumbnailPlaceholder
                    item={bestImageItem}
                    fallbackName={bestItem || name}
                    style={s.bestImage}
                    textStyle={s.bestImageLetter}
                  />
                )}
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={s.bestName} numberOfLines={2}>
                    {isNutritionUnknown ? "Menu not verified — tap to scan" : (bestItem || "Menu item")}
                  </Text>
                  {!isNutritionUnknown && (calories != null || protein != null) ? (
                    <View style={s.macroChips}>
                      {calories != null && (
                        <View style={s.chip}><Text style={s.chipText}>🔥 {Math.round(calories)} kcal</Text></View>
                      )}
                      {protein != null && (
                        <View style={s.chip}><Text style={s.chipText}>💪 {Math.round(protein)}g protein</Text></View>
                      )}
                    </View>
                  ) : null}
                  {!isNutritionUnknown && num(place.protein_fill_pct) != null ? (
                    <View style={s.fitBadge}>
                      <Text style={s.fitBadgeText}>
                        Fills {place.protein_fill_pct}% of your protein gap
                      </Text>
                    </View>
                  ) : null}
                </View>
              </View>
              {reason ? <Text style={s.reason} numberOfLines={2}>{reason}</Text> : null}
            </View>

            {/* Macro Breakdown */}
            <MacroBar protein={protein} carbs={carbs} fat={fat} />

            {/* Goal Variants */}
            {variants.length > 0 && (
              <View style={s.section}>
                <Text style={s.kicker}>ALTERNATIVES BY GOAL</Text>
                {variants.map((v, i) => (
                  <View key={i} style={s.variantRow}>
                    <View style={s.variantLabel}><Text style={s.variantLabelText}>{v.label}</Text></View>
                    <Text style={s.variantName} numberOfLines={1}>{v.name}</Text>
                    <Text style={s.variantMacro}>
                      {v.kcal != null ? `${Math.round(v.kcal)}kcal` : ""}
                      {v.protein != null ? ` · ${Math.round(v.protein)}g p` : ""}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            {/* Your Usual — with smart comparison */}
            {usualName ? (
              <View style={s.usualCard}>
                <Text style={s.usualHeader}>YOUR HISTORY AT THIS PLACE</Text>
                <View style={s.usualRow}>
                  <Text style={s.usualLabel}>👤 Last order:</Text>
                  <Text style={s.usualName} numberOfLines={1}>{usualName}</Text>
                </View>
                {num(usual?.estimated_calories) != null && (
                  <Text style={s.usualMacro}>
                    {Math.round(usual.estimated_calories)} kcal · {Math.round(usual?.estimated_protein_g || 0)}g protein
                  </Text>
                )}
                {bestItem && usualName.toLowerCase() !== bestItem.toLowerCase() && (
                  <View style={s.usualSwapHint}>
                    <Text style={s.usualSwapText}>
                      💡 Today try "{bestItem}" instead — better fit for your remaining macros
                    </Text>
                  </View>
                )}
              </View>
            ) : null}

            {/* Full Menu — all items ranked by macro fit */}
            {menuWithFit.length > 1 && (
              <View style={s.section}>
                <Text style={s.kicker}>FULL MENU — RANKED FOR YOU</Text>
                {menuWithFit.slice(0, 12).map((it, i) => (
                  <View key={`mi-${i}`} style={s.menuItemRow}>
                    <View style={s.menuItemRank}>
                      <Text style={s.menuItemRankText}>{i + 1}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.menuItemName} numberOfLines={1}>
                        {it.item_name}
                      </Text>
                      <View style={{ flexDirection: "row", gap: 8 }}>
                        {num(it.estimated_calories) != null && (
                          <Text style={s.menuItemMacro}>{Math.round(it.estimated_calories)} kcal</Text>
                        )}
                        {num(it.estimated_protein_g) != null && (
                          <Text style={s.menuItemMacro}>{Math.round(it.estimated_protein_g)}g P</Text>
                        )}
                      </View>
                    </View>
                    {it.protein_fill_pct != null && (
                      <View style={[s.fitPill, it.protein_fill_pct >= 50 && s.fitPillStrong]}>
                        <Text style={[s.fitPillText, it.protein_fill_pct >= 50 && s.fitPillTextStrong]}>
                          {it.protein_fill_pct}%
                        </Text>
                      </View>
                    )}
                  </View>
                ))}
              </View>
            )}

            {/* CTA */}
            <PressableScale
              style={s.cta}
              onPress={() => { onOpenInMaps?.(place); onClose?.(); }}
              haptic
            >
              <Text style={s.ctaText}>📍 Open in Maps</Text>
            </PressableScale>

            <View style={{ height: 40 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(0,0,0,0.55)" },
  sheet: {
    height: SHEET_H,
    backgroundColor: "#0f1624",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    overflow: "hidden",
  },
  handleRow: { alignItems: "center", paddingTop: 10, paddingBottom: 6 },
  handle: { width: 40, height: 5, borderRadius: 3, backgroundColor: "#334155" },
  scroll: { flex: 1, paddingHorizontal: 20 },

  header: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginTop: 16, marginBottom: 20, gap: 12 },
  placeName: { fontSize: 22, fontWeight: "800", color: "#f8fafc", lineHeight: 28, marginBottom: 6 },

  section: { marginBottom: 20 },
  kicker: { fontSize: 11, fontWeight: "700", color: "#64748b", letterSpacing: 1.2, marginBottom: 10 },

  bestRow: { flexDirection: "row", gap: 14, alignItems: "center" },
  bestImage: { width: 72, height: 72, borderRadius: 14 },
  bestImageLetter: { fontSize: 28 },
  bestName: { fontSize: 17, fontWeight: "700", color: "#f8fafc", lineHeight: 22 },
  macroChips: { flexDirection: "row", gap: 8, flexWrap: "wrap", marginTop: 2 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: "#1e293b" },
  chipText: { fontSize: 12, fontWeight: "600", color: "#e2e8f0" },
  reason: { fontSize: 13, color: "#94a3b8", marginTop: 8, lineHeight: 18 },
  fitBadge: {
    marginTop: 8,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: "rgba(34, 197, 94, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(34, 197, 94, 0.25)",
    alignSelf: "flex-start",
  },
  fitBadgeText: {
    fontSize: 12,
    fontWeight: "700",
    color: "#4ade80",
    fontFamily: "Inter_700Bold",
  },

  macroBarWrap: { marginBottom: 20 },
  macroBarTrack: { flexDirection: "row", height: 8, borderRadius: 4, overflow: "hidden", backgroundColor: "#1e293b" },
  macroSeg: { height: 8 },
  macroLegend: { flexDirection: "row", alignItems: "center", marginTop: 6 },
  macroLegendDot: { fontSize: 10, fontWeight: "800" },
  macroLegendText: { fontSize: 11, color: "#94a3b8", fontWeight: "500" },

  variantRow: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  variantLabel: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: "#1e3a5f" },
  variantLabelText: { fontSize: 11, fontWeight: "700", color: "#93c5fd" },
  variantName: { flex: 1, fontSize: 13, color: "#f8fafc", fontWeight: "500" },
  variantMacro: { fontSize: 12, color: "#94a3b8", fontWeight: "500" },

  usualCard: {
    backgroundColor: "#0a1018",
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: "rgba(167, 139, 250, 0.2)",
    marginBottom: 20,
    gap: 6,
  },
  usualHeader: { fontSize: 10, fontWeight: "700", color: "#7c3aed", letterSpacing: 1, fontFamily: "Inter_700Bold" },
  usualRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  usualLabel: { fontSize: 13, color: "#a78bfa", fontWeight: "600" },
  usualName: { fontSize: 13, color: "#f8fafc", fontWeight: "500", flex: 1 },
  usualMacro: { fontSize: 12, color: "#94a3b8" },
  usualSwapHint: {
    marginTop: 4,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "rgba(34, 197, 94, 0.08)",
  },
  usualSwapText: { fontSize: 12, color: "#4ade80", lineHeight: 16 },

  menuItemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(148, 163, 184, 0.12)",
  },
  menuItemRank: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(148, 163, 184, 0.12)",
    alignItems: "center",
    justifyContent: "center",
  },
  menuItemRankText: { fontSize: 11, fontWeight: "700", color: "#94a3b8" },
  menuItemName: { fontSize: 14, fontWeight: "600", color: "#f8fafc", marginBottom: 2 },
  menuItemMacro: { fontSize: 12, color: "#94a3b8", fontWeight: "500" },
  fitPill: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    backgroundColor: "rgba(148, 163, 184, 0.12)",
  },
  fitPillStrong: {
    backgroundColor: "rgba(34, 197, 94, 0.15)",
  },
  fitPillText: { fontSize: 12, fontWeight: "700", color: "#94a3b8" },
  fitPillTextStrong: { color: "#4ade80" },

  cta: { backgroundColor: "#22c55e", paddingVertical: 16, borderRadius: 14, alignItems: "center" },
  ctaText: { fontSize: 16, fontWeight: "700", color: "#052e16" },
});
