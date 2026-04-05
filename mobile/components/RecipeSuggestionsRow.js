/**
 * Post-scan recipe variety suggestions (server: Spoonacular or AI + saved prefs).
 */

import React from "react";
import { View, Text, TouchableOpacity, ScrollView, Image, ActivityIndicator, StyleSheet } from "react-native";
import { premium } from "../ui/premiumSystem";
import { colors, spacing, radius } from "../designTokens";

function pickRecipeUrl(rec) {
  const direct = String(rec?.source_url || "").trim();
  if (direct) return direct;
  const title = String(rec?.title || "").trim();
  if (!title) return "";
  return `https://www.google.com/search?q=${encodeURIComponent(`${title} recipe`)}`;
}

export function RecipeSuggestionsRow({ busy, payload, onOpenUrl, onFeedback, mealTag, onUpgradePress }) {
  const rateLimited = Boolean(payload?.rate_limited) || payload?.source === "rate_limited";
  if (rateLimited && !busy) {
    const msg = String(payload?.disclaimer || "").trim() || "Daily limit reached for free accounts.";
    return (
      <View style={styles.wrap}>
        <Text style={styles.title}>Variety ideas</Text>
        <Text style={styles.sub}>{msg}</Text>
        {typeof onUpgradePress === "function" ? (
          <TouchableOpacity
            style={[premium.ctaSecondary, { marginTop: 10, alignSelf: "flex-start" }]}
            onPress={() => onUpgradePress(null)}
            activeOpacity={0.85}
          >
            <Text style={premium.ctaSecondaryText}>Upgrade for unlimited</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    );
  }

  const recipes = Array.isArray(payload?.recipes) ? payload.recipes : [];
  const disclaimer = String(payload?.disclaimer || "").trim();
  const show = busy || recipes.length > 0;
  if (!show) return null;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Variety ideas</Text>
      <Text style={styles.sub}>
        Recipes matched to your scan (ingredients + cuisine), ranked for higher protein and sensible calories — saves tune future picks.
      </Text>
      {busy && recipes.length === 0 ? (
        <ActivityIndicator color={colors.accent?.primary || "#60a5fa"} style={{ marginTop: 10 }} />
      ) : null}
      {recipes.length > 0 ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.hScroll}
        >
          {recipes.map((rec, idx) => {
            const key = String(rec?.recipe_key || `rec-${idx}`);
            const title = String(rec?.title || "Recipe").trim();
            const kcal = rec?.est_kcal_per_serving;
            const p = rec?.est_protein_g_per_serving;
            const why = String(rec?.why_similar || "").trim();
            const idea = String(rec?.short_idea || "").trim();
            const src = String(rec?.source || "");
            const img = String(rec?.image_url || "").trim();
            const cuisine = (Array.isArray(rec?.cuisines) ? rec.cuisines[0] : "") || "";
            const url = pickRecipeUrl(rec);

            return (
              <View key={key} style={[premium.cardBase, premium.cardBaseV2, styles.card]}>
                {img ? <Image source={{ uri: img }} style={styles.thumb} /> : <View style={styles.thumbPlaceholder} />}
                <Text style={styles.cardTitle} numberOfLines={2}>
                  {title}
                </Text>
                {kcal != null || p != null ? (
                  <Text style={styles.meta}>
                    {kcal != null ? `~${Math.round(kcal)} kcal` : ""}
                    {kcal != null && p != null ? " · " : ""}
                    {p != null ? `~${p}g protein` : ""}
                    {src === "llm" ? " (est.)" : ""}
                  </Text>
                ) : src === "themealdb" ? (
                  <Text style={styles.meta}>Free catalog — open for ingredients & macros</Text>
                ) : null}
                {why ? (
                  <Text style={styles.why} numberOfLines={3}>
                    {why}
                  </Text>
                ) : null}
                {idea ? (
                  <Text style={styles.idea} numberOfLines={2}>
                    {idea}
                  </Text>
                ) : null}
                <View style={styles.actions}>
                  {url ? (
                    <TouchableOpacity
                      style={[premium.ctaSecondary, styles.actionBtn]}
                      onPress={() => {
                        if (typeof onOpenUrl === "function") onOpenUrl(url);
                        if (typeof onFeedback === "function") {
                          onFeedback({ recipeKey: key, action: "open", cuisine, mealTag, recipe: rec });
                        }
                      }}
                      activeOpacity={0.85}
                    >
                      <Text style={premium.ctaSecondaryText}>Open</Text>
                    </TouchableOpacity>
                  ) : null}
                  <TouchableOpacity
                    style={[premium.ctaGhost, styles.actionBtn]}
                    onPress={() => {
                      if (typeof onFeedback === "function") {
                        onFeedback({ recipeKey: key, action: "save", cuisine, mealTag, recipe: rec });
                      }
                    }}
                    activeOpacity={0.85}
                  >
                    <Text style={premium.ctaGhostText}>Save</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[premium.ctaGhost, styles.actionBtn]}
                    onPress={() => {
                      if (typeof onFeedback === "function") {
                        onFeedback({ recipeKey: key, action: "more_like", cuisine, mealTag, recipe: rec });
                      }
                    }}
                    activeOpacity={0.85}
                  >
                    <Text style={premium.ctaGhostText}>More like this</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.dismiss}
                    onPress={() => {
                      if (typeof onFeedback === "function") {
                        onFeedback({ recipeKey: key, action: "dismiss", cuisine, mealTag, recipe: rec });
                      }
                    }}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Text style={styles.dismissText}>✕</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </ScrollView>
      ) : null}
      {disclaimer ? <Text style={styles.disclaimer}>{disclaimer}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 14 },
  title: { fontSize: 16, fontWeight: "800", color: colors.text?.primary || "#f8fafc" },
  sub: {
    marginTop: 4,
    fontSize: 12,
    color: colors.text?.muted || "#94a3b8",
    lineHeight: 16,
  },
  hScroll: { paddingVertical: 10, paddingRight: spacing.md },
  card: {
    width: 260,
    marginRight: 12,
    padding: 12,
  },
  thumb: {
    width: "100%",
    height: 96,
    borderRadius: radius.md,
    marginBottom: 8,
    backgroundColor: colors.surface?.elevated || "#1e293b",
  },
  thumbPlaceholder: {
    width: "100%",
    height: 72,
    borderRadius: radius.md,
    marginBottom: 8,
    backgroundColor: colors.surface?.elevated || "#1e293b",
  },
  cardTitle: { fontSize: 14, fontWeight: "700", color: colors.text?.primary || "#f1f5f9" },
  meta: { marginTop: 4, fontSize: 12, color: colors.text?.muted || "#94a3b8" },
  why: { marginTop: 6, fontSize: 12, color: colors.text?.secondary || "#cbd5e1", lineHeight: 16 },
  idea: { marginTop: 4, fontSize: 11, color: colors.text?.muted || "#94a3b8", fontStyle: "italic" },
  actions: { marginTop: 10, flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
  actionBtn: { marginRight: 8, marginBottom: 4 },
  dismiss: { marginLeft: "auto", padding: 4 },
  dismissText: { color: colors.text?.muted || "#64748b", fontSize: 14 },
  disclaimer: { marginTop: 8, fontSize: 10, color: colors.text?.muted || "#64748b", lineHeight: 14 },
});
