import { StyleSheet } from "react-native";
import {
  colors,
  spacing,
  radius,
  typography,
  shadows,
  chip as chipTokens,
  badge as badgeTokens,
} from "../designTokens";

/**
 * Premium UI system primitives.
 * Goal: unify card rhythm / CTAs / chips / text hierarchy incrementally.
 * Safe to adopt per-component (no logic changes).
 */
export const premium = StyleSheet.create({
  // ─── Section rhythm ────────────────────────────────────────────────────
  section: { marginTop: spacing.section },
  sectionTight: { marginTop: spacing.xl },

  // ─── Cards ────────────────────────────────────────────────────────────
  cardBase: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
    ...shadows.sm,
  },
  cardHero: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.xl,
    ...shadows.lg,
  },
  cardInset: {
    backgroundColor: "rgba(8, 16, 30, 0.70)",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: "rgba(31, 46, 69, 0.90)",
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.base,
  },

  // ─── Typography ───────────────────────────────────────────────────────
  kicker: {
    fontSize: typography.xs,
    color: colors.slate.muted,
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  /** Kicker on dark panels (e.g. cardInset) — higher contrast than slate.muted */
  kickerOnDarkInset: {
    fontSize: typography.xs,
    color: "#cbd5e1",
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  /** Kicker / label on light or warm surfaces (white, cream) */
  kickerOnLight: {
    fontSize: typography.xs,
    color: "#92400e",
    fontWeight: typography.weight.semibold,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  title: {
    fontSize: typography.lg,
    color: colors.text.primary,
    fontWeight: typography.weight.extrabold,
    letterSpacing: 0.2,
  },
  body: {
    fontSize: typography.md,
    color: colors.text.secondary,
    lineHeight: Math.round(typography.md * typography.lineHeight.relaxed),
  },
  muted: {
    fontSize: typography.sm,
    color: colors.text.muted,
    lineHeight: Math.round(typography.sm * typography.lineHeight.relaxed),
  },
  /** Secondary line on dark inset cards (readable vs muted grey on navy) */
  mutedOnDarkInset: {
    fontSize: typography.sm,
    color: "#e2e8f0",
    lineHeight: Math.round(typography.sm * typography.lineHeight.relaxed),
  },

  // ─── CTAs ─────────────────────────────────────────────────────────────
  ctaPrimary: {
    backgroundColor: colors.success.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaPrimaryText: {
    color: colors.text.inverse,
    fontSize: typography.md,
    fontWeight: typography.weight.extrabold,
  },
  ctaSecondary: {
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    backgroundColor: "transparent",
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaSecondaryText: {
    color: colors.accent.primary,
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
  },
  ctaGhost: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: "rgba(148, 163, 184, 0.18)",
    backgroundColor: "rgba(15, 23, 42, 0.35)",
  },
  ctaGhostText: {
    color: colors.text.secondary,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },

  // ─── Chips ────────────────────────────────────────────────────────────
  chipBaseSm: {
    paddingVertical: chipTokens.sm.paddingVertical,
    paddingHorizontal: chipTokens.sm.paddingHorizontal,
    borderRadius: chipTokens.sm.borderRadius,
    borderWidth: 1,
  },
  chipSuccess: { backgroundColor: colors.success.bg, borderColor: colors.success.border },
  chipNeutral: {
    backgroundColor: badgeTokens.neutral.backgroundColor,
    borderColor: colors.surface.cardBorder,
  },
  chipAmber: { backgroundColor: colors.amber.bg, borderColor: colors.amber.border },
  chipTextSuccess: {
    color: colors.success.text,
    fontSize: chipTokens.sm.fontSize,
    fontWeight: chipTokens.sm.fontWeight,
  },
  chipTextNeutral: {
    color: colors.slate.text,
    fontSize: chipTokens.sm.fontSize,
    fontWeight: chipTokens.sm.fontWeight,
  },
  chipTextAmber: {
    color: colors.amber.text,
    fontSize: chipTokens.sm.fontSize,
    fontWeight: chipTokens.sm.fontWeight,
  },

  // ─── Orbs / Pills ─────────────────────────────────────────────────────
  aiOrb: {
    width: 34,
    height: 34,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(147, 197, 253, 0.10)",
    borderWidth: 1,
    borderColor: "rgba(147, 197, 253, 0.22)",
  },
  aiOrbText: {
    fontSize: typography.xs,
    fontWeight: typography.weight.extrabold,
    color: colors.accent.primary,
    letterSpacing: 0.2,
  },
  pill: {
    paddingVertical: 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(147, 197, 253, 0.22)",
    backgroundColor: "rgba(147, 197, 253, 0.10)",
  },
  pillText: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
    color: colors.accent.primary,
  },

  // ─── Button sizes (44px minimum tap target per Apple HIG) ─────────────
  btnLg: {
    paddingVertical: 16,
    paddingHorizontal: spacing.xl,
    borderRadius: radius.lg,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 52,
  },
  btnMd: {
    paddingVertical: 12,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
  },
  btnSm: {
    paddingVertical: 8,
    paddingHorizontal: spacing.base,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 36,
  },
  btnTextLg: { fontSize: 16, fontWeight: typography.weight.bold, fontFamily: "Inter_700Bold" },
  btnTextMd: { fontSize: 14, fontWeight: typography.weight.semibold, fontFamily: "Inter_600SemiBold" },
  btnTextSm: { fontSize: 12, fontWeight: typography.weight.semibold, fontFamily: "Inter_600SemiBold" },

  // ─── Input / Form fields ─────────────────────────────────────────────
  input: {
    backgroundColor: colors.surface.elevated,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontSize: typography.md,
    color: colors.text.primary,
    minHeight: 48,
  },
  inputFocused: {
    borderColor: colors.accent.primary,
    borderWidth: 1.5,
  },

  // ─── Dividers ────────────────────────────────────────────────────────
  divider: {
    height: 1,
    backgroundColor: colors.surface.cardBorder,
    marginVertical: spacing.lg,
  },
  dividerThin: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: "rgba(148, 163, 184, 0.15)",
    marginVertical: spacing.base,
  },

  // ─── List items ──────────────────────────────────────────────────────
  listItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
    gap: spacing.base,
    minHeight: 48,
  },
  listItemText: {
    fontSize: typography.md,
    color: colors.text.primary,
    fontWeight: typography.weight.medium,
    flex: 1,
  },
  listItemMuted: {
    fontSize: typography.sm,
    color: colors.text.muted,
    fontWeight: typography.weight.regular,
  },

  // ─── Modal/Sheet footer ──────────────────────────────────────────────
  sheetFooter: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
    backgroundColor: colors.surface.card,
  },

  // ─── Icon utility button (consistent ⚙ / ⋯ / close) ───────────────────
  iconBtn: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: "rgba(148, 163, 184, 0.18)",
    backgroundColor: "rgba(15, 23, 42, 0.35)",
    alignItems: "center",
    justifyContent: "center",
  },
  iconBtnText: {
    color: colors.text.secondary,
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
  },
});

