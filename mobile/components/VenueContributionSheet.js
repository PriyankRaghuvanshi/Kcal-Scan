/**
 * VenueContributionSheet – lightweight feedback sheet for Healthy Nearby.
 */

import React, { useState } from "react";
import { View, Text, TouchableOpacity, TextInput, StyleSheet, Modal } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";

const CHIP_OPTIONS = [
  { key: "better_order_suggestion", label: "Better order suggestion" },
  { key: "vegetarian_option_missing", label: "Vegetarian option missing" },
  { key: "vegan_option_missing", label: "Vegan option missing" },
  { key: "item_not_on_menu", label: "Item not on menu" },
  { key: "menu_item_correction", label: "Macros look wrong" },
];

export function VenueContributionSheet({
  visible,
  onClose,
  onSubmit,
}) {
  const [selectedType, setSelectedType] = useState("better_order_suggestion");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!onSubmit) return;
    setSubmitting(true);
    try {
      await onSubmit({
        contributionType: selectedType,
        suggestedItemText: text,
      });
      setText("");
      setSelectedType("better_order_suggestion");
    } finally {
      setSubmitting(false);
      onClose && onClose();
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <Text style={styles.title}>Improve this recommendation</Text>
          <Text style={styles.subtitle}>Pick one and optionally tell us what to suggest instead.</Text>
          <View style={styles.chipRow}>
            {CHIP_OPTIONS.map((opt) => {
              const active = selectedType === opt.key;
              return (
                <TouchableOpacity
                  key={opt.key}
                  style={[styles.chip, active ? styles.chipActive : null]}
                  onPress={() => setSelectedType(opt.key)}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TextInput
            style={styles.input}
            placeholder="What should we suggest instead? (optional)"
            placeholderTextColor={colors.slate.text}
            value={text}
            onChangeText={setText}
            multiline
          />
          <View style={styles.actions}>
            <TouchableOpacity style={styles.secondaryBtn} onPress={onClose} disabled={submitting}>
              <Text style={styles.secondaryText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={handleSubmit}
              disabled={submitting}
            >
              <Text style={styles.primaryText}>{submitting ? "Sending…" : "Send feedback"}</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.footerText}>Thanks — this helps improve future recommendations.</Text>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: colors.surface.card,
    padding: spacing.lg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  title: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
  },
  subtitle: {
    marginTop: spacing.xs,
    fontSize: typography.sm,
    color: colors.slate.text,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
  },
  chipActive: {
    backgroundColor: colors.success.bg,
    borderColor: colors.success.border,
  },
  chipText: {
    fontSize: typography.sm,
    color: colors.text.primary,
  },
  chipTextActive: {
    color: colors.success.text,
    fontWeight: typography.weight.semibold,
  },
  input: {
    marginTop: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    padding: spacing.md,
    fontSize: typography.sm,
    color: colors.text.primary,
    minHeight: 60,
  },
  actions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  primaryBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: colors.success.primary,
  },
  primaryText: {
    color: "#000",
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  secondaryBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
  },
  secondaryText: {
    color: colors.slate.text,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  footerText: {
    marginTop: spacing.sm,
    fontSize: typography.xs,
    color: colors.slate.text,
  },
});

