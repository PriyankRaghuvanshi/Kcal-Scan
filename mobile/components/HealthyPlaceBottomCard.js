/**
 * Selected place bottom card for Healthy Nearby map.
 * Uses unified RecommendationCard with premium design tokens.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { RecommendationCard } from "./RecommendationCard";
import { getRecommendationHeroLabel } from "../healthyNearbyUtils";
import { openDirections } from "../externalMaps";
import { radius } from "../designTokens";

export function HealthyPlaceBottomCard({
  place,
  rankPosition,
  heroLabelOverride,
  onDirections,
  onScanMenu,
  onFeedbackYes,
  onFeedbackImprove,
  style,
}) {
  if (!place || typeof place !== "object") return null;

  const handleDirections = () => {
    if (onDirections) {
      onDirections(place);
    } else {
      openDirections(place);
    }
  };

  const heroLabel = heroLabelOverride != null && heroLabelOverride !== ""
    ? heroLabelOverride
    : getRecommendationHeroLabel(place, rankPosition);

  return (
    <View style={[styles.wrapper, style]}>
      <RecommendationCard
        place={place}
        heroLabel={heroLabel}
        rankPosition={rankPosition}
        actions={{
          primaryLabel: "Directions",
          onPrimary: handleDirections,
          secondaryLabel: onScanMenu ? "Scan Menu" : undefined,
          onSecondary: onScanMenu ? () => onScanMenu(place) : undefined,
          primaryIcon: "📍",
        }}
        dark
        style={styles.card}
      />
      <View style={styles.feedbackRow}>
        <Text style={styles.feedbackLabel}>Was this helpful?</Text>
        <View style={styles.feedbackButtons}>
          <TouchableOpacity
            style={styles.feedbackBtn}
            onPress={() => onFeedbackYes && onFeedbackYes(place)}
            activeOpacity={0.8}
          >
            <Text style={styles.feedbackText}>Yes</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.feedbackBtn}
            onPress={() => onFeedbackImprove && onFeedbackImprove(place)}
            activeOpacity={0.8}
          >
            <Text style={styles.feedbackText}>Improve</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    padding: 0,
  },
  card: {
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderBottomLeftRadius: 0,
    borderBottomRightRadius: 0,
  },
  feedbackRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  feedbackLabel: {
    color: "#cfd7e3",
    fontSize: 12,
  },
  feedbackButtons: {
    flexDirection: "row",
    gap: 8,
  },
  feedbackBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#2f3b4f",
  },
  feedbackText: {
    color: "#cfd7e3",
    fontSize: 12,
  },
});
