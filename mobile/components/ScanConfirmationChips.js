import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

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
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <View style={styles.rowWrap}>
        {types.map((t) => {
          const key = String(t);
          const active = String(selectedPowderType) === key;
          return (
            <TouchableOpacity
              key={`powder-${key}`}
              style={[styles.chip, active ? styles.chipActive : null]}
              onPress={() => onSelectPowderType && onSelectPowderType(key)}
              disabled={disabled}
            >
              <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>{key.replace(/_/g, " ")}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <View style={[styles.rowWrap, { marginTop: 8 }]}>
        {sizes.map((g) => {
          const val = Number(g);
          const active = Number(selectedScoopG) === val;
          return (
            <TouchableOpacity
              key={`scoop-${val}`}
              style={[styles.chip, active ? styles.chipActive : null]}
              onPress={() => onSelectScoopG && onSelectScoopG(val)}
              disabled={disabled}
            >
              <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>{val}g</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#1f2e45", borderRadius: 12, backgroundColor: "#08101e" },
  title: { color: "#cfe3ff", fontSize: 12, fontWeight: "800", marginBottom: 8 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 999, borderWidth: 1, borderColor: "#2a3d5b", backgroundColor: "#132033" },
  chipActive: { borderColor: "#7bd3ff", backgroundColor: "#0e2436" },
  chipText: { color: "#cfe3ff", fontSize: 12, fontWeight: "700" },
  chipTextActive: { color: "#7bd3ff" },
});

