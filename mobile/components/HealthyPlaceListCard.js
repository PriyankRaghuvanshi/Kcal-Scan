/**
 * HealthyPlaceListCard – List item for Healthy Nearby list view.
 * Uses RecommendationCard with compact layout + Open in Maps CTA.
 */

import React from "react";
import { RecommendationCard } from "./RecommendationCard";
import { getRecommendationHeroLabel } from "../healthyNearbyUtils";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function HealthyPlaceListCard({
  place,
  indexInSection,
  onOpenInMaps,
  onPress,
}) {
  if (!place || typeof place !== "object") return null;

  const rankPosition = indexInSection < 3 ? indexInSection + 1 : null;
  const heroLabel = rankPosition ? getRecommendationHeroLabel(place, rankPosition) : "";

  return (
    <RecommendationCard
      place={place}
      heroLabel={heroLabel}
      rankPosition={rankPosition}
      actions={{
        primaryLabel: "Open in Maps",
        onPrimary: () => onOpenInMaps && onOpenInMaps(place),
        primaryIcon: "📍",
      }}
      dark
      compact
      onPress={onPress}
    />
  );
}
