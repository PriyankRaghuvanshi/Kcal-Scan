/**
 * SmartAlertCard - Single alert candidate card for inbox/preview.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

const ALERT_TYPE_LABELS = {
  protein_rescue: "Protein rescue",
  post_workout_recovery: "Post-workout recovery",
  late_night_damage_control: "Late-night option",
  worked_before_repeat: "Worked well before",
  habit_rescue: "Habit rescue",
};

function formatDistance(m) {
  if (m == null || !Number.isFinite(m)) return "";
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
  return `${Math.round(m)} m`;
}

export function SmartAlertCard({
  candidate,
  onOpen,
  onDismiss,
  compact = false,
}) {
  if (!candidate || typeof candidate !== "object") return null;

  const title = candidate.title || "Nearby option";
  const body = candidate.body || "";
  const placeName = candidate.place_name || "Nearby spot";
  const bestItem = candidate.best_item_name || "";
  const score = candidate.display_rank_score_100;
  const conf = candidate.confidence_label || "";
  const alertType = candidate.alert_type || "";
  const distanceM = candidate.distance_m;
  const protein = candidate.estimated_protein_g;
  const personalLabel = candidate.personal_memory_label || "";

  const typeLabel = ALERT_TYPE_LABELS[alertType] || alertType.replace(/_/g, " ");
  const whyLine = personalLabel
    ? personalLabel
    : protein != null
    ? `${typeLabel} • ${protein}g protein • ${formatDistance(distanceM) || "nearby"}`
    : `${typeLabel} • ${formatDistance(distanceM) || "nearby"}`;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.typeBadge}>{typeLabel}</Text>
        {score != null && <Text style={styles.score}>Score {score}</Text>}
      </View>
      <Text style={styles.title} numberOfLines={2}>
        {title}
      </Text>
      <Text style={styles.body} numberOfLines={2}>
        {body}
      </Text>
      {!compact && (
        <>
          {bestItem ? (
            <Text style={styles.meta} numberOfLines={1}>
              {placeName} — {bestItem}
            </Text>
          ) : (
            <Text style={styles.meta} numberOfLines={1}>
              {placeName}
            </Text>
          )}
          <Text style={styles.why}>{whyLine}</Text>
          {conf ? (
            <Text style={styles.conf}>Confidence: {conf}</Text>
          ) : null}
        </>
      )}
      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.primaryBtn}
          onPress={() => onOpen && onOpen(candidate)}
          activeOpacity={0.8}
        >
          <Text style={styles.primaryBtnText}>View nearby option</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.dismissBtn}
          onPress={() => onDismiss && onDismiss(candidate)}
          activeOpacity={0.8}
        >
          <Text style={styles.dismissBtnText}>Dismiss</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  typeBadge: {
    fontSize: 11,
    fontWeight: "600",
    color: "#555",
    textTransform: "uppercase",
  },
  score: {
    fontSize: 11,
    color: "#888",
  },
  title: {
    fontSize: 15,
    fontWeight: "600",
    color: "#222",
    marginBottom: 4,
  },
  body: {
    fontSize: 14,
    color: "#444",
    marginBottom: 6,
  },
  meta: {
    fontSize: 12,
    color: "#666",
    marginBottom: 2,
  },
  why: {
    fontSize: 11,
    color: "#888",
    marginBottom: 4,
  },
  conf: {
    fontSize: 10,
    color: "#999",
    marginBottom: 10,
  },
  actions: {
    flexDirection: "row",
    gap: 8,
    marginTop: 4,
  },
  primaryBtn: {
    flex: 1,
    backgroundColor: "#2563eb",
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  primaryBtnText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  dismissBtn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
    backgroundColor: "#f1f5f9",
    justifyContent: "center",
  },
  dismissBtnText: {
    color: "#64748b",
    fontSize: 13,
  },
});
