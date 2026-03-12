/**
 * ConfidenceBadge – Maps backend confidence/specificity to clear UI labels.
 * Verified | Chain-backed | Local favorite | Estimated | Needs menu check
 * Uses smartAlertTrustLabels for consistent mapping across push, inbox, and cards.
 */

import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { spacing, radius, typography, badge } from "../designTokens";
import {
  getAlertTrustLabel,
  getTrustTierForBadge,
  TRUST_LABELS,
} from "../smartAlertTrustLabels";

const LABEL_MAP = {
  verified: TRUST_LABELS.verified,
  chain_backed: TRUST_LABELS.chain_backed,
  local_favorite: TRUST_LABELS.local_favorite,
  estimated: TRUST_LABELS.estimated,
  needs_menu_check: TRUST_LABELS.needs_menu_check,
};

function inferConfidenceTier(place) {
  return getTrustTierForBadge(place);
}

function getBadgeStyle(tier) {
  switch (tier) {
    case "verified":
      return badge.strong;
    case "chain_backed":
    case "local_favorite":
      return badge.strong;
    case "estimated":
      return badge.estimated;
    default:
      return badge.weak;
  }
}

export function ConfidenceBadge({ place, labelOverride, variant, tier: tierOverride, style }) {
  const tier = tierOverride || variant || (place ? getTrustTierForBadge(place) : "needs_menu_check");
  const label = labelOverride || (place ? getAlertTrustLabel(place) : LABEL_MAP[tier]) || LABEL_MAP.needs_menu_check;
  const badgeStyle = getBadgeStyle(tier);

  return (
    <View style={[styles.badge, badgeStyle, style]}>
      <Text style={[styles.text, { color: badgeStyle.color }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    alignSelf: "flex-start",
  },
  text: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
  },
});

export { inferConfidenceTier, LABEL_MAP, getBadgeStyle };
