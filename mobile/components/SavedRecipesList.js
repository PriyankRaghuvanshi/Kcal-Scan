/**
 * Lists recipes the user saved from post-scan suggestions (server-backed).
 */

import React, { useCallback, useEffect, useState } from "react";
import { View, Text, TouchableOpacity, Image, ActivityIndicator, ScrollView, StyleSheet, RefreshControl } from "react-native";
import { premium } from "../ui/premiumSystem";
import { colors, radius, spacing } from "../designTokens";
import { fetchSavedRecipes, postRecipeFeedback } from "../utils/recipeSuggestionsApi";

function pickUrl(row) {
  const u = String(row?.source_url || "").trim();
  if (u) return u;
  const title = String(row?.title || "").trim();
  if (!title) return "";
  return `https://www.google.com/search?q=${encodeURIComponent(`${title} recipe`)}`;
}

export function SavedRecipesList({
  userId,
  aiConsentGiven,
  onOpenUrl,
  onBack,
  onUpgradePress,
  planAtLeastPro,
}) {
  const [busy, setBusy] = useState(true);
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!userId || !aiConsentGiven) {
      setItems([]);
      setBusy(false);
      return;
    }
    setErr("");
    setBusy(true);
    try {
      const data = await fetchSavedRecipes(userId);
      setItems(Array.isArray(data?.recipes) ? data.recipes : []);
    } catch (e) {
      setErr("Could not load saved recipes.");
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, [userId, aiConsentGiven]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!userId) {
    return (
      <View style={styles.empty}>
        <Text style={styles.muted}>Sign in to see saved recipes.</Text>
      </View>
    );
  }

  if (!aiConsentGiven) {
    return (
      <View style={[premium.cardBase, premium.cardBaseV2, styles.card]}>
        <Text style={premium.title}>AI processing</Text>
        <Text style={premium.muted}>Turn on AI consent in settings to sync saved recipes.</Text>
        {typeof onBack === "function" ? (
          <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 12 }]} onPress={onBack}>
            <Text style={premium.ctaSecondaryText}>Back</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.scroll}
      refreshControl={
        <RefreshControl
          refreshing={busy && items.length > 0}
          onRefresh={() => void load()}
          tintColor="#93c5fd"
        />
      }
    >
      {!planAtLeastPro ? (
        <View style={[premium.cardBase, { marginBottom: 12, padding: 12 }]}>
          <Text style={premium.muted}>
            Free plan: limited recipe suggestion runs per day. Pro gets unlimited variety ideas after each scan.
          </Text>
          {typeof onUpgradePress === "function" ? (
            <TouchableOpacity style={[premium.ctaSecondary, { marginTop: 10 }]} onPress={() => onUpgradePress(null)}>
              <Text style={premium.ctaSecondaryText}>See plans</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      {err ? <Text style={styles.warn}>{err}</Text> : null}

      {busy && items.length === 0 ? (
        <ActivityIndicator color="#93c5fd" style={{ marginTop: 24 }} />
      ) : null}

      {!busy && items.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.muted}>No saved recipes yet. Save one from the cards after you scan a meal.</Text>
        </View>
      ) : null}

      {items.map((row) => {
        const key = String(row?.recipe_key || "");
        const title = String(row?.title || "Recipe").trim();
        const img = String(row?.image_url || "").trim();
        const kcal = row?.est_kcal_per_serving;
        const p = row?.est_protein_g_per_serving;
        const url = pickUrl(row);

        return (
          <View key={key || title} style={[premium.cardBase, premium.cardBaseV2, styles.row]}>
            {img ? <Image source={{ uri: img }} style={styles.thumb} /> : <View style={styles.thumbPh} />}
            <Text style={styles.rowTitle} numberOfLines={2}>
              {title}
            </Text>
            {kcal != null || p != null ? (
              <Text style={styles.meta}>
                {kcal != null ? `~${Math.round(kcal)} kcal` : ""}
                {kcal != null && p != null ? " · " : ""}
                {p != null ? `~${p}g protein` : ""}
              </Text>
            ) : null}
            <View style={styles.rowActions}>
              {url ? (
                <TouchableOpacity
                  style={premium.ctaSecondary}
                  onPress={() => {
                    if (typeof onOpenUrl === "function") onOpenUrl(url);
                  }}
                >
                  <Text style={premium.ctaSecondaryText}>Open</Text>
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity
                style={premium.ctaGhost}
                onPress={() => {
                  postRecipeFeedback({
                    userId,
                    recipeKey: key,
                    action: "unsave",
                  });
                  setItems((prev) => prev.filter((x) => String(x?.recipe_key) !== key));
                }}
              >
                <Text style={premium.ctaGhostText}>Remove</Text>
              </TouchableOpacity>
            </View>
          </View>
        );
      })}
      <View style={{ height: spacing.xxl }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 0 },
  card: { padding: 14, marginBottom: 12 },
  empty: { paddingVertical: 20, paddingHorizontal: 8 },
  muted: { color: colors.text?.muted || "#94a3b8", fontSize: 14, lineHeight: 20 },
  warn: { color: "#fca5a5", marginBottom: 8 },
  row: { padding: 12, marginBottom: 12 },
  thumb: { width: "100%", height: 120, borderRadius: radius.md, marginBottom: 8, backgroundColor: colors.surface?.elevated || "#1e293b" },
  thumbPh: { width: "100%", height: 72, borderRadius: radius.md, marginBottom: 8, backgroundColor: colors.surface?.elevated || "#1e293b" },
  rowTitle: { fontSize: 16, fontWeight: "700", color: colors.text?.primary || "#f8fafc" },
  meta: { marginTop: 4, fontSize: 12, color: colors.text?.muted || "#94a3b8" },
  rowActions: { flexDirection: "row", flexWrap: "wrap", marginTop: 10 },
});
