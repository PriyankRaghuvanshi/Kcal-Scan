/**
 * Selected place bottom card for Healthy Nearby map.
 * Uses unified RecommendationCard with premium design tokens.
 */

import React from "react";
import { View, StyleSheet } from "react-native";
import { RecommendationCard } from "./RecommendationCard";
import { getRecommendationHeroLabel } from "../healthyNearbyUtils";
import { openDirections } from "../externalMaps";
import { radius } from "../designTokens";

export function HealthyPlaceBottomCard({
  place,
  rankPosition,
  onDirections,
  onScanMenu,
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

  const heroLabel = getRecommendationHeroLabel(place, rankPosition);

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
});
