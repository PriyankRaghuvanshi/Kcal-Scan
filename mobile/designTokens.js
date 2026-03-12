/**
 * CalorieClick Design Tokens
 * Premium, calm, actionable, trustworthy.
 * Figma-friendly: token-driven styling for future design system sync.
 */

// ─── Colors ─────────────────────────────────────────────────────────────

export const colors = {
  // Primary surface (dark theme dominant in app)
  surface: {
    primary: "#0a0f18",
    elevated: "#0f1624",
    card: "#060e1c",
    cardBorder: "#1a2642",
    overlay: "rgba(0,15,30,0.92)",
  },
  // Light theme surfaces (Smart Alerts, some cards)
  surfaceLight: {
    primary: "#ffffff",
    elevated: "#f8fafc",
    card: "#ffffff",
    cardBorder: "#e2e8f0",
  },

  // Strong fit / good choice / verified
  success: {
    primary: "#22c55e",
    muted: "#16a34a",
    bg: "#0f4126",
    border: "#15803d",
    text: "#4ade80",
  },

  // Estimated / caution / needs menu check
  amber: {
    primary: "#f59e0b",
    muted: "#d97706",
    bg: "#451a03",
    border: "#78350f",
    text: "#fcd34d",
  },

  // Secondary content, hints
  slate: {
    primary: "#64748b",
    muted: "#94a3b8",
    subtle: "#64748b",
    text: "#94a3b8",
  },

  // Strong warnings only
  warning: {
    primary: "#ef4444",
    text: "#fca5a5",
  },

  // Accent (links, subtle highlights)
  accent: {
    primary: "#93c5fd",
    muted: "#94b8d9",
  },

  // Text hierarchy
  text: {
    primary: "#f8fafc",
    secondary: "#e2e8f0",
    muted: "#94a3b8",
    inverse: "#0f172a",
  },

  textLight: {
    primary: "#0f172a",
    secondary: "#334155",
    muted: "#64748b",
  },
};

// ─── Spacing ─────────────────────────────────────────────────────────────

export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 6,
  md: 8,
  base: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  section: 28,
};

// ─── Radius ─────────────────────────────────────────────────────────────

export const radius = {
  xs: 6,
  sm: 8,
  md: 10,
  lg: 12,
  xl: 16,
  xxl: 20,
  pill: 999,
};

// ─── Typography ─────────────────────────────────────────────────────────────

export const typography = {
  // Sizes
  xs: 11,
  sm: 12,
  base: 13,
  md: 14,
  lg: 15,
  xl: 16,
  xxl: 18,
  hero: 20,

  // Weights (Platform uses string)
  weight: {
    regular: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
    extrabold: "800",
  },

  // Line heights (multiplier)
  lineHeight: {
    tight: 1.2,
    normal: 1.35,
    relaxed: 1.5,
  },
};

// ─── Shadows / Elevation ──────────────────────────────────────────────────

export const shadows = {
  sm: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  md: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 4,
  },
  lg: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 8,
  },
};

// ─── Badge Styles ───────────────────────────────────────────────────────────

export const badge = {
  // Strong / verified
  strong: {
    backgroundColor: colors.success.bg,
    borderColor: colors.success.border,
    color: colors.success.text,
    borderWidth: 1,
  },
  // Estimated / local favorite
  estimated: {
    backgroundColor: colors.amber.bg,
    borderColor: colors.amber.border,
    color: colors.amber.text,
    borderWidth: 1,
  },
  // Weak / needs menu check
  weak: {
    backgroundColor: "rgba(100,116,139,0.2)",
    borderColor: colors.slate.primary,
    color: colors.slate.text,
    borderWidth: 1,
  },
  // Neutral chip
  neutral: {
    backgroundColor: "rgba(30,58,95,0.5)",
    borderColor: colors.surface.cardBorder,
    color: colors.slate.text,
    borderWidth: 1,
  },
};

// ─── Chip Styles ───────────────────────────────────────────────────────────

export const chip = {
  sm: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
  },
  md: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.md,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
};

// ─── Card Variants ─────────────────────────────────────────────────────────

export const cardVariant = {
  strong: "strong",
  estimated: "estimated",
  weak: "weak",
};
