import React, { useState } from "react";
import { Modal, View, Text, TouchableOpacity, StyleSheet } from "react-native";

export function MealFeedbackPrompt({ visible, onSubmit, onSkip, pending }) {
  const [fullness, setFullness] = useState(null);
  const [craving, setCraving] = useState(null);
  const [repeatIntent, setRepeatIntent] = useState(null);
  const [helpedOnTarget, setHelpedOnTarget] = useState(null);

  const disabled = fullness == null && craving == null && repeatIntent == null && helpedOnTarget == null;

  function handleSubmit() {
    if (!onSubmit) return;
    onSubmit({
      fullnessScore: fullness,
      cravingScore: craving,
      repeatIntent,
      helpedOnTarget,
    });
  }

  if (!visible) return null;

  return (
    <Modal transparent animationType="slide" visible={visible}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Text style={styles.title}>How was this meal?</Text>
          {!!pending?.best_item_name && (
            <Text style={styles.subtitle}>{pending.best_item_name}</Text>
          )}
          <View style={styles.section}>
            <Text style={styles.label}>Did it keep you full?</Text>
            <View style={styles.row}>
              {[1, 2, 3, 4, 5].map((v) => (
                <TouchableOpacity
                  key={v}
                  style={[
                    styles.chip,
                    fullness === v && styles.chipSelected,
                  ]}
                  onPress={() => setFullness(v)}
                >
                  <Text style={styles.chipText}>{v}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <View style={styles.section}>
            <Text style={styles.label}>Did cravings hit later?</Text>
            <View style={styles.row}>
              {[1, 2, 3, 4, 5].map((v) => (
                <TouchableOpacity
                  key={v}
                  style={[
                    styles.chip,
                    craving === v && styles.chipSelected,
                  ]}
                  onPress={() => setCraving(v)}
                >
                  <Text style={styles.chipText}>{v}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <View style={styles.sectionRow}>
            <Text style={styles.label}>Would you repeat it?</Text>
            <View style={styles.row}>
              <TouchableOpacity
                style={[styles.chip, repeatIntent === true && styles.chipSelected]}
                onPress={() => setRepeatIntent(true)}
              >
                <Text style={styles.chipText}>Yes</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.chip, repeatIntent === false && styles.chipSelected]}
                onPress={() => setRepeatIntent(false)}
              >
                <Text style={styles.chipText}>No</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={styles.sectionRow}>
            <Text style={styles.label}>Did it help you stay on target?</Text>
            <View style={styles.row}>
              <TouchableOpacity
                style={[styles.chip, helpedOnTarget === true && styles.chipSelected]}
                onPress={() => setHelpedOnTarget(true)}
              >
                <Text style={styles.chipText}>Yes</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.chip, helpedOnTarget === false && styles.chipSelected]}
                onPress={() => setHelpedOnTarget(false)}
              >
                <Text style={styles.chipText}>No</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={styles.footerRow}>
            <TouchableOpacity style={styles.secondaryButton} onPress={onSkip}>
              <Text style={styles.secondaryText}>Not now</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.primaryButton, disabled && styles.primaryButtonDisabled]}
              onPress={handleSubmit}
              disabled={disabled}
            >
              <Text style={styles.primaryText}>Submit</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "center",
    alignItems: "center",
  },
  card: {
    width: "90%",
    backgroundColor: "#101015",
    borderRadius: 16,
    padding: 16,
  },
  title: {
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 4,
    color: "#fff",
  },
  subtitle: {
    fontSize: 14,
    color: "#ddd",
    marginBottom: 12,
  },
  section: {
    marginBottom: 12,
  },
  sectionRow: {
    marginBottom: 10,
  },
  label: {
    fontSize: 14,
    color: "#ccc",
    marginBottom: 6,
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#444",
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginRight: 6,
    marginBottom: 4,
  },
  chipSelected: {
    borderColor: "#41d36c",
    backgroundColor: "#183021",
  },
  chipText: {
    color: "#fff",
    fontSize: 13,
  },
  footerRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    marginTop: 8,
    gap: 10,
  },
  primaryButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: "#41d36c",
  },
  primaryButtonDisabled: {
    opacity: 0.5,
  },
  primaryText: {
    color: "#02040a",
    fontWeight: "600",
  },
  secondaryButton: {
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  secondaryText: {
    color: "#aaa",
  },
});

export default MealFeedbackPrompt;

