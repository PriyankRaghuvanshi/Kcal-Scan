import React, { useMemo } from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";

function clean(s) {
  return String(s || "").replace(/\s+/g, " ").trim();
}

export function CoachVoiceBlock({
  coachVoice,
  toneLabel,
  modeLabel,
  compact,
  showOneAction = true,
}) {
  const empathy = clean(coachVoice?.empathy_line);
  const insight = clean(coachVoice?.insight_line);
  const takeaway = insight || empathy;
  const hasAny = Boolean(takeaway);
  const actionTitle = clean(coachVoice?.one_action?.title);
  const steps = Array.isArray(coachVoice?.one_action?.steps) ? coachVoice.one_action.steps.map(clean).filter(Boolean) : [];
  const why = clean(coachVoice?.why_this_action);
  const disclaimer = clean(coachVoice?.safety_disclaimer);

  const headerRight = useMemo(() => {
    const parts = [];
    const t = clean(toneLabel);
    const m = clean(modeLabel);
    if (t) parts.push(t);
    if (m && m !== t) parts.push(m);
    return parts.join(" · ");
  }, [toneLabel, modeLabel]);

  if (!coachVoice || !hasAny) return null;

  return (
    <View style={[styles.wrap, compact && styles.wrapCompact]}>
      <View style={styles.headerRow}>
        <View style={styles.coachTag}>
          <View style={styles.coachDot} />
          <Text style={styles.coachTagText}>Coach</Text>
        </View>
        {headerRight ? (
          <View style={styles.metaPill}>
            <Text style={styles.metaPillText} numberOfLines={1}>
              {headerRight}
            </Text>
          </View>
        ) : null}
      </View>

      <Text style={[styles.takeaway, compact && styles.takeawayCompact]} numberOfLines={compact ? 3 : 6}>
        {takeaway}
      </Text>

      {showOneAction && actionTitle ? (
        <View style={styles.oneThingBlock}>
          <Text style={styles.oneThingLabel}>If you do one thing</Text>
          <Text style={styles.oneThingTitle} numberOfLines={2}>
            {actionTitle}
          </Text>
          {!compact && steps.length ? (
            <View style={{ marginTop: spacing.sm }}>
              {steps.slice(0, 3).map((s, i) => (
                <Text key={`${s}-${i}`} style={styles.step} numberOfLines={2}>
                  · {s}
                </Text>
              ))}
            </View>
          ) : null}
          {!compact && why ? (
            <Text style={styles.why} numberOfLines={3}>
              {why}
            </Text>
          ) : null}
        </View>
      ) : null}

      {!compact && disclaimer ? (
        <Text style={styles.disclaimer} numberOfLines={3}>
          {disclaimer}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1,
    borderColor: "rgba(31, 46, 69, 0.9)",
    backgroundColor: "rgba(8, 16, 30, 0.7)",
    borderRadius: radius.xl,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  wrapCompact: {
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  coachTag: {
    flexDirection: "row",
    alignItems: "center",
  },
  coachDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: colors.accent.primary,
    marginRight: spacing.sm,
  },
  coachTagText: {
    fontSize: typography.sm,
    fontWeight: typography.weight.extrabold,
    color: colors.text.secondary,
    letterSpacing: 0.2,
  },
  metaPill: {
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(147, 197, 253, 0.22)",
    backgroundColor: "rgba(147, 197, 253, 0.10)",
    marginLeft: spacing.base,
    maxWidth: "55%",
  },
  metaPillText: {
    fontSize: typography.xs,
    color: colors.accent.primary,
    fontWeight: typography.weight.semibold,
  },
  takeaway: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    lineHeight: typography.md * typography.lineHeight.relaxed,
  },
  takeawayCompact: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.secondary,
  },
  oneThingBlock: {
    marginTop: spacing.lg,
    paddingTop: spacing.base,
    borderTopWidth: 1,
    borderTopColor: "rgba(31, 46, 69, 0.65)",
  },
  oneThingLabel: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: spacing.xs,
  },
  oneThingTitle: {
    fontSize: typography.sm,
    color: colors.success.text,
    fontWeight: typography.weight.extrabold,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
  },
  step: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
    marginBottom: spacing.xs,
  },
  why: {
    marginTop: spacing.sm,
    fontSize: typography.xs,
    color: colors.slate.text,
    lineHeight: typography.xs * 1.45,
  },
  disclaimer: {
    marginTop: spacing.base,
    fontSize: typography.xs,
    color: colors.text.muted,
    lineHeight: typography.xs * 1.4,
  },
});

