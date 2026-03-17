import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { premium } from "../ui/premiumSystem";
import { spacing } from "../designTokens";

export function ScanConfirmationChips({
  title = "Confirm powder",
  powderTypes = [],
  scoopSizesG = [],
  selectedPowderType = "",
  selectedScoopG = null,
  onSelectPowderType,
  onSelectScoopG,
  disabled = false,
}) {
  const types = Array.isArray(powderTypes) ? powderTypes : [];
  const sizes = Array.isArray(scoopSizesG) ? scoopSizesG : [];
  return (
    <View style={[premium.cardInset, styles.wrap]}>
      <Text style={premium.kicker}>{title}</Text>
      <View style={styles.rowWrap}>
        {types.map((t) => {
          const key = String(t);
          const active = String(selectedPowderType) === key;
          return (
            <TouchableOpacity
              key={`powder-${key}`}
              style={[
                premium.chipBaseSm,
                premium.chipNeutral,
                styles.chip,
                active ? styles.chipActive : null,
              ]}
              onPress={() => onSelectPowderType && onSelectPowderType(key)}
              disabled={disabled}
            >
              <Text style={[premium.chipTextNeutral, active ? styles.chipTextActive : null]}>
                {key.replace(/_/g, " ")}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <View style={[styles.rowWrap, { marginTop: spacing.sm }]}>
        {sizes.map((g) => {
          const val = Number(g);
          const active = Number(selectedScoopG) === val;
          return (
            <TouchableOpacity
              key={`scoop-${val}`}
              style={[
                premium.chipBaseSm,
                premium.chipNeutral,
                styles.chip,
                active ? styles.chipActive : null,
              ]}
              onPress={() => onSelectScoopG && onSelectScoopG(val)}
              disabled={disabled}
            >
              <Text style={[premium.chipTextNeutral, active ? styles.chipTextActive : null]}>{val}g</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 10 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap" },
  chip: { marginRight: spacing.sm, marginBottom: spacing.sm },
  chipActive: { borderColor: "rgba(147, 197, 253, 0.50)", backgroundColor: "rgba(147, 197, 253, 0.10)" },
  chipTextActive: { color: "rgba(147, 197, 253, 1)" },
});

