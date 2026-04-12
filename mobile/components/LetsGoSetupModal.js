/**
 * Let's Go Goal Coach – setup flow modal.
 * Collects goal_type, timeframe, pace_mode, training_days, diet_preference, optional weight.
 */

import React, { useState } from "react";
import { View, Text, TouchableOpacity, Modal, StyleSheet, ScrollView, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";
import { GOAL_TYPES, PACE_MODES } from "../utils/goalCoachUtils";

const GOAL_LABELS = { fat_loss: "Fat loss", muscle_gain: "Muscle gain", recomp: "Recomp", maintain: "Maintain" };
const PACE_LABELS = { easy: "Easy", balanced: "Balanced", serious: "Serious" };

/** Quick presets: { id, label, goal_preset, goal_type, timeframe_weeks } */
const GOAL_PRESETS = [
  { id: "fat_loss_90", label: "Fat loss in 90 days", goal_preset: "fat_loss_90", goal_type: "fat_loss", timeframe_weeks: 13 },
  { id: "comp_prep", label: "Comp prep", goal_preset: "comp_prep", goal_type: "fat_loss", timeframe_weeks: 14 },
  { id: "recomp", label: "Recomp", goal_preset: "recomp", goal_type: "recomp", timeframe_weeks: 8 },
  { id: "maintain", label: "Maintain", goal_preset: "maintain", goal_type: "maintain", timeframe_weeks: 12 },
];

export function LetsGoSetupModal({ visible, onClose, onSubmit, loading = false }) {
  const [goalPreset, setGoalPreset] = useState(null);
  const [goalType, setGoalType] = useState("fat_loss");
  const [paceMode, setPaceMode] = useState("balanced");
  const [timeframeWeeks, setTimeframeWeeks] = useState("8");
  const [trainingDays, setTrainingDays] = useState("3");
  const [dietPreference, setDietPreference] = useState("non_veg");
  const [currentWeight, setCurrentWeight] = useState("");
  const [targetWeight, setTargetWeight] = useState("");

  const applyPreset = (preset) => {
    if (!preset) {
      setGoalPreset(null);
      return;
    }
    setGoalPreset(preset.id);
    setGoalType(preset.goal_type);
    setTimeframeWeeks(String(preset.timeframe_weeks));
  };

  const handleSubmit = () => {
    const weeks = Math.max(4, Math.min(52, parseInt(timeframeWeeks, 10) || 8));
    const days = Math.max(0, Math.min(7, parseInt(trainingDays, 10) || 3));
    const preset = GOAL_PRESETS.find((p) => p.id === goalPreset);
    onSubmit({
      goal_type: goalType,
      pace_mode: paceMode,
      timeframe_weeks: weeks,
      training_days_per_week: days,
      diet_preference: dietPreference || undefined,
      current_weight: currentWeight ? parseFloat(currentWeight) : undefined,
      target_weight: targetWeight ? parseFloat(targetWeight) : undefined,
      ...(preset ? { goal_preset: preset.goal_preset } : {}),
    });
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.overlay}
      >
        <View style={styles.sheet}>
          <View style={styles.header}>
            <Text style={styles.title}>Let's Go Goal Coach</Text>
            <Text style={styles.subtitle}>Set your goal and we'll build a starter plan.</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeText}>Close</Text>
            </TouchableOpacity>
          </View>

          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.label}>Quick presets</Text>
            <View style={styles.chipRow}>
              {GOAL_PRESETS.map((p) => (
                <TouchableOpacity
                  key={p.id}
                  onPress={() => applyPreset(goalPreset === p.id ? null : p)}
                  style={[styles.chip, goalPreset === p.id && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, goalPreset === p.id && styles.chipTextSelected]} numberOfLines={1}>
                    {p.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Goal</Text>
            <View style={styles.chipRow}>
              {GOAL_TYPES.map((g) => (
                <TouchableOpacity
                  key={g}
                  onPress={() => { setGoalPreset(null); setGoalType(g); }}
                  style={[styles.chip, goalType === g && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, goalType === g && styles.chipTextSelected]}>{GOAL_LABELS[g] || g}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Pace</Text>
            <View style={styles.chipRow}>
              {PACE_MODES.map((p) => (
                <TouchableOpacity
                  key={p}
                  onPress={() => setPaceMode(p)}
                  style={[styles.chip, paceMode === p && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, paceMode === p && styles.chipTextSelected]}>{PACE_LABELS[p] || p}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Timeframe (weeks)</Text>
            <TextInput
              style={styles.input}
              value={timeframeWeeks}
              onChangeText={(v) => { setGoalPreset(null); setTimeframeWeeks(v); }}
              keyboardType="number-pad"
              placeholder="8"
              placeholderTextColor={colors.slate.muted}
            />

            <Text style={styles.label}>Training days per week</Text>
            <TextInput
              style={styles.input}
              value={trainingDays}
              onChangeText={setTrainingDays}
              keyboardType="number-pad"
              placeholder="3"
              placeholderTextColor={colors.slate.muted}
            />

            <Text style={styles.label}>Diet (optional)</Text>
            <View style={styles.chipRow}>
              {["non_veg", "vegetarian", "vegan"].map((d) => (
                <TouchableOpacity
                  key={d}
                  onPress={() => setDietPreference(d)}
                  style={[styles.chip, dietPreference === d && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, dietPreference === d && styles.chipTextSelected]}>
                    {d === "non_veg" ? "Non-veg" : d === "vegetarian" ? "Veg" : "Vegan"}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Current weight (kg, optional)</Text>
            <TextInput
              style={styles.input}
              value={currentWeight}
              onChangeText={setCurrentWeight}
              keyboardType="decimal-pad"
              placeholder="e.g. 82"
              placeholderTextColor={colors.slate.muted}
            />

            <Text style={styles.label}>Target weight (kg, optional)</Text>
            <TextInput
              style={styles.input}
              value={targetWeight}
              onChangeText={setTargetWeight}
              keyboardType="decimal-pad"
              placeholder="e.g. 76"
              placeholderTextColor={colors.slate.muted}
            />

            <TouchableOpacity
              onPress={handleSubmit}
              style={[styles.submitBtn, loading && styles.submitBtnDisabled]}
              disabled={loading}
            >
              <Text style={styles.submitText}>{loading ? "Creating…" : "Start my plan"}</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface.elevated,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    maxHeight: "90%",
  },
  header: {
    padding: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface.cardBorder,
  },
  title: {
    fontSize: typography.xxl,
    fontWeight: typography.weight.bold,
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  subtitle: {
    fontSize: typography.sm,
    color: colors.slate.text,
    marginBottom: spacing.md,
  },
  closeBtn: {
    alignSelf: "flex-end",
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  closeText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
  },
  body: {
    // ScrollView style only controls the scroll viewport layout.
    flexGrow: 0,
  },
  bodyContent: {
    // ScrollView content must get padding via contentContainerStyle, not style,
    // otherwise paddingBottom is silently ignored and the last button sits flush
    // against the keyboard.
    padding: spacing.xl,
    paddingBottom: spacing.xxl * 2,
  },
  label: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.slate.text,
    marginBottom: spacing.sm,
    marginTop: spacing.base,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    backgroundColor: "rgba(26,38,66,0.6)",
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
  },
  chipSelected: {
    borderColor: colors.success.primary,
    backgroundColor: colors.success.bg,
  },
  chipText: {
    fontSize: typography.sm,
    color: colors.text.secondary,
  },
  chipTextSelected: {
    color: colors.success.text,
  },
  input: {
    backgroundColor: "rgba(26,38,66,0.6)",
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    borderRadius: radius.md,
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
    fontSize: typography.md,
    color: colors.text.primary,
  },
  submitBtn: {
    backgroundColor: colors.success.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.base,
    alignItems: "center",
    marginTop: spacing.xxl,
  },
  submitBtnDisabled: {
    opacity: 0.7,
  },
  submitText: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.inverse,
  },
});
