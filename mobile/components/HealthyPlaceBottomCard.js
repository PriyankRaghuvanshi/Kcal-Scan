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
import { premium } from "../ui/premiumSystem";

export function HealthyPlaceBottomCard({
  place,
  rankPosition,
  heroLabelOverride,
  onDirections,
  onScanMenu,
  onFeedbackYes,
  onFeedbackImprove,
  style,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
}) {
  if (!place || typeof place !== "object") return null;
  const isScreenshot = Boolean(screenshotMode);

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
        screenshotMode={isScreenshot}
        actions={{
          primaryLabel: "Directions",
          onPrimary: handleDirections,
          secondaryLabel: !isScreenshot && onScanMenu ? "Scan Menu" : undefined,
          onSecondary: !isScreenshot && onScanMenu ? () => onScanMenu(place) : undefined,
          primaryIcon: "📍",
        }}
        dark
        style={styles.card}
      />
      {!isScreenshot ? (
        <View style={styles.feedbackRow}>
          <Text style={premium.muted}>Was this helpful?</Text>
          <View style={styles.feedbackButtons}>
            <TouchableOpacity
              style={premium.ctaGhost}
              onPress={() => onFeedbackYes && onFeedbackYes(place)}
              activeOpacity={0.8}
            >
              <Text style={premium.ctaGhostText}>Yes</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[premium.ctaGhost, { marginLeft: 8 }]}
              onPress={() => onFeedbackImprove && onFeedbackImprove(place)}
              activeOpacity={0.8}
            >
              <Text style={premium.ctaGhostText}>Improve</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}
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
  },
});
