/**
 * SmartAlertSettings - Master toggle, category toggles, frequency mode, push status.
 */

import React from "react";
import { View, Text, TouchableOpacity, Switch, StyleSheet } from "react-native";

const PUSH_STATUS_LABELS = {
  granted: "On",
  denied: "Permission denied",
  undetermined: "Not enabled",
  permanentlyDenied: "Permission denied",
};

const CATEGORY_LABELS = {
  protein_rescue: "Protein rescue alerts",
  post_workout_recovery: "Post-workout alerts",
  late_night_damage_control: "Late-night alerts",
  worked_before_repeat: "Worked-before alerts",
  habit_rescue: "Habit rescue alerts",
};

const FREQUENCY_LABELS = {
  smart_only: "Smart only (recommended)",
  normal: "Normal",
  low: "Low",
};

export function SmartAlertSettings({
  enabled,
  categories = {},
  frequencyMode = "smart_only",
  onEnabledChange,
  onCategoryChange,
  onFrequencyChange,
  pushPermissionStatus,
  onRequestPushPermission,
  onOpenSettings,
}) {
  const cats = { ...categories };
  const pushGranted = pushPermissionStatus?.granted;
  const pushCanAsk = pushPermissionStatus?.status !== "denied" && pushPermissionStatus?.status !== "permanentlyDenied";

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <Text style={styles.label}>Smart Food Alerts</Text>
        <Switch
          value={enabled}
          onValueChange={onEnabledChange}
          trackColor={{ false: "#cbd5e1", true: "#93c5fd" }}
          thumbColor={enabled ? "#2563eb" : "#f8fafc"}
        />
      </View>
      <Text style={styles.hint}>
        Only high-value alerts when you need them: protein rescue, post-workout, late-night, worked-before.
      </Text>

      {enabled && (
        <>
          <View style={[styles.row, { marginTop: 12 }]}>
            <Text style={styles.optionLabel}>
              Push notifications: {pushGranted ? "On" : PUSH_STATUS_LABELS[pushPermissionStatus?.status] || "Off"}
            </Text>
            {pushCanAsk && !pushGranted ? (
              <TouchableOpacity
                style={styles.smallBtn}
                onPress={onRequestPushPermission}
              >
                <Text style={styles.smallBtnText}>Enable</Text>
              </TouchableOpacity>
            ) : !pushCanAsk && !pushGranted ? (
              <TouchableOpacity
                style={styles.smallBtn}
                onPress={onOpenSettings}
              >
                <Text style={styles.smallBtnText}>Open settings</Text>
              </TouchableOpacity>
            ) : null}
          </View>

          <Text style={styles.sectionTitle}>Alert categories</Text>
          {Object.keys(CATEGORY_LABELS).map((key) => (
            <View key={key} style={styles.row}>
              <Text style={styles.optionLabel}>{CATEGORY_LABELS[key]}</Text>
              <Switch
                value={cats[key] !== false}
                onValueChange={(v) => onCategoryChange && onCategoryChange(key, v)}
                trackColor={{ false: "#cbd5e1", true: "#93c5fd" }}
                thumbColor={cats[key] !== false ? "#2563eb" : "#f8fafc"}
              />
            </View>
          ))}

          <Text style={styles.sectionTitle}>Frequency</Text>
          {["smart_only", "normal", "low"].map((mode) => (
            <TouchableOpacity
              key={mode}
              style={[styles.freqOption, frequencyMode === mode && styles.freqOptionActive]}
              onPress={() => onFrequencyChange && onFrequencyChange(mode)}
            >
              <Text style={[styles.freqText, frequencyMode === mode && styles.freqTextActive]}>
                {FREQUENCY_LABELS[mode] || mode}
              </Text>
            </TouchableOpacity>
          ))}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: 16,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
  },
  label: {
    fontSize: 16,
    fontWeight: "600",
    color: "#222",
  },
  hint: {
    fontSize: 12,
    color: "#64748b",
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#444",
    marginTop: 16,
    marginBottom: 4,
  },
  optionLabel: {
    fontSize: 14,
    color: "#333",
  },
  freqOption: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    marginBottom: 4,
    backgroundColor: "#f8fafc",
  },
  freqOptionActive: {
    backgroundColor: "#dbeafe",
  },
  freqText: {
    fontSize: 14,
    color: "#444",
  },
  freqTextActive: {
    color: "#2563eb",
    fontWeight: "600",
  },
  smallBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: "#e2e8f0",
    borderRadius: 6,
  },
  smallBtnText: {
    fontSize: 13,
    color: "#475569",
  },
});
