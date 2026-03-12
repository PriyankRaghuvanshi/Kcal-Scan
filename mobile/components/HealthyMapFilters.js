/**
 * Filter chips for Healthy Nearby map.
 */

import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

const CHIPS = [
  { key: "all", label: "All" },
  { key: "high_protein", label: "High Protein" },
  { key: "under_600", label: "Under 600 kcal" },
  { key: "fits_today", label: "Fits Today" },
  { key: "cut_friendly", label: "Cut Friendly" },
  { key: "best_right_now", label: "Best Right Now" },
];

export function HealthyMapFilters({ activeKey, onSelect, style }) {
  return (
    <View style={[styles.row, style]}>
      {CHIPS.map((chip) => {
        const active = activeKey === chip.key;
        return (
          <TouchableOpacity
            key={chip.key}
            style={[styles.chip, active && styles.chipActive]}
            onPress={() => onSelect(chip.key)}
            activeOpacity={0.7}
          >
            <Text style={[styles.chipText, active && styles.chipTextActive]}>{chip.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    paddingHorizontal: 4,
  },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 20,
    backgroundColor: "#0c1a2e",
    borderWidth: 1,
    borderColor: "#274869",
  },
  chipActive: {
    backgroundColor: "#1e3a5f",
    borderColor: "#3b82f6",
  },
  chipText: {
    color: "#94b8d9",
    fontSize: 13,
    fontWeight: "600",
  },
  chipTextActive: {
    color: "#93c5fd",
  },
});
