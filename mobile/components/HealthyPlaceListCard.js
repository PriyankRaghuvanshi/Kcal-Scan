/**
 * HealthyPlaceListCard – List item for Healthy Nearby list view.
 * Uses RecommendationCard with compact layout + Open in Maps CTA.
 * Includes staggered entrance animation for premium feel.
 */

import React, { useEffect, useRef } from "react";
import { Animated } from "react-native";
import { RecommendationCard } from "./RecommendationCard";
import { getRecommendationHeroLabel } from "../healthyNearbyUtils";

export function HealthyPlaceListCard({
  place,
  indexInSection,
  onOpenInMaps,
  onPress,
  onFeedbackImprove,
}) {
  if (!place || typeof place !== "object") return null;

  const rankPosition = indexInSection < 3 ? indexInSection + 1 : null;
  const heroLabel = rankPosition ? getRecommendationHeroLabel(place, rankPosition) : "";

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    const delay = Math.min(indexInSection * 80, 400);
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 350,
        delay,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 350,
        delay,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  return (
    <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>
      <RecommendationCard
        place={place}
        heroLabel={heroLabel}
        rankPosition={rankPosition}
        actions={{
          primaryLabel: "Open in Maps",
          onPrimary: () => onOpenInMaps && onOpenInMaps(place),
          secondaryLabel: onFeedbackImprove ? "Improve" : undefined,
          onSecondary: onFeedbackImprove ? () => onFeedbackImprove(place) : undefined,
          primaryIcon: "📍",
        }}
        dark
        compact
        onPress={onPress}
      />
    </Animated.View>
  );
}
