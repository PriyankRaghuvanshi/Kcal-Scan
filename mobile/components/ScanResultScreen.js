/**
 * Scan Result / Meal Analysis – premium redesign.
 * Preserves all data and handlers; presentation and hierarchy only.
 * No gap; design tokens; React Native / Expo compatible.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, Text, Image, ScrollView, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";
import { premium } from "../ui/premiumSystem";
import { hapticLight, hapticSuccess, layoutEaseInOut } from "../ui/feedback";

// ─── Helpers (safe fallbacks when fields missing) ─────────────────────────

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function round1(x) {
  const n = num(x);
  return n != null ? Math.round(n * 10) / 10 : "—";
}

function _cleanInlineLabel(s) {
  const t = String(s || "")
    .replace(/\s+/g, " ")
    .replace(/\s*[|•·,]\s*$/, "")
    .trim();
  return t;
}

function _clampText(s, maxLen) {
  const t = _cleanInlineLabel(s);
  if (!t) return "";
  if (t.length <= maxLen) return t;
  return t.slice(0, Math.max(0, maxLen - 1)).trimEnd() + "…";
}

/**
 * Returns { label: "Strong" | "Fair" | "Needs work" | "—", color }.
 * Fallback: no data → "—" muted.
 */
export function getMealQualityBadge(result, coaching) {
  const qa = result?.meal_qa?.qa_score;
  if (qa != null) {
    if (num(qa) >= 70) return { label: "Strong", color: colors.success.primary };
    if (num(qa) >= 45) return { label: "Fair", color: colors.amber.primary };
    return { label: "Needs work", color: colors.warning.primary };
  }
  const sat = num(coaching?.satiety_score);
  const upf = num(coaching?.ultra_processed_score);
  if (sat != null && upf != null) {
    if (sat >= 65 && upf < 5) return { label: "Strong", color: colors.success.primary };
    if (sat >= 45 || upf < 7) return { label: "Fair", color: colors.amber.primary };
    return { label: "Needs work", color: colors.warning.primary };
  }
  return { label: "—", color: colors.text.muted };
}

/**
 * Returns { text: string, tone: "success" | "amber" } or null.
 * Uses remainingToday when available; safe when missing.
 */
export function getGoalFitLine(result, remainingToday) {
  if (!result?.total_kcal) return null;
  const kcal = num(result.total_kcal);
  const remKcal = remainingToday != null ? num(remainingToday.kcal) : null;
  const remP = remainingToday != null ? num(remainingToday.protein_g) : null;
  const p = num(result?.totals?.protein_g);
  if (remKcal != null && kcal != null && kcal > remKcal) {
    return { text: "Over today’s calorie budget", tone: "amber" };
  }
  if (remP != null && p != null && remP > 0 && p >= remP * 0.3) {
    return { text: "Great protein choice for today", tone: "success" };
  }
  if (remKcal != null && remKcal > 0 && kcal != null && kcal <= remKcal) {
    return { text: "Fits your plan today", tone: "success" };
  }
  return null;
}

/**
 * Grams protein per 100 kcal — compact quality signal with emoji.
 * @returns {{ emoji: string, line: string } | null}
 */
export function getProteinKcalDensityLine(result) {
  const kcal = num(result?.total_kcal);
  const p = num(result?.totals?.protein_g);
  if (kcal == null || kcal <= 0 || p == null || p < 0) return null;
  const per100 = (p / kcal) * 100;
  const v = Math.round(per100 * 10) / 10;
  const valueStr = `${v}g protein / 100 kcal`;
  if (per100 >= 7.5) return { emoji: "😊", line: `${valueStr} — strong` };
  if (per100 >= 4.5) return { emoji: "😐", line: `${valueStr} — moderate` };
  return { emoji: "😟", line: `${valueStr} — room to improve` };
}

// ─── Hero ────────────────────────────────────────────────────────────────

export function ScanResultHero({ photoUri, result, coaching }) {
  const topCandidate = (result?.top_candidates || [])[0];
  const items = result?.items || [];
  const mealLabel = useMemo(() => {
    const fromCandidate = _cleanInlineLabel(topCandidate?.label);
    if (fromCandidate) return _clampText(fromCandidate, 34);

    const names = (Array.isArray(items) ? items : [])
      .map((i) => (i && typeof i === "object" ? _cleanInlineLabel(i.name) : ""))
      .filter(Boolean);
    if (names.length === 0) return "Meal";

    // Prefer a clean single label; only show a second item if it's short enough.
    const a = _clampText(names[0], 28);
    const bRaw = names[1] ? _cleanInlineLabel(names[1]) : "";
    const b = bRaw ? _clampText(bRaw, 18) : "";
    const combined = b ? `${a} · ${b}` : a;
    return _clampText(combined, 34) || "Meal";
  }, [topCandidate?.label, items]);
  const kcal =
    result?.total_kcal != null
      ? Math.round(num(result.total_kcal))
      : "—";
  const badge = getMealQualityBadge(result || {}, coaching || null);

  return (
    <View style={styles.heroWrap}>
      {photoUri ? (
        <Image source={{ uri: photoUri }} style={styles.heroImage} />
      ) : (
        <View style={styles.heroPlaceholder} />
      )}
      <View style={styles.heroOverlay}>
        <Text style={styles.heroMealLabel} numberOfLines={1}>
          {mealLabel}
        </Text>
        <Text style={styles.heroKcal}>{kcal} kcal</Text>
      </View>
      <View style={[styles.qualityBadge, { borderColor: badge.color }]}>
        <Text style={[styles.qualityBadgeText, { color: badge.color }]}>{badge.label}</Text>
      </View>
    </View>
  );
}

// ─── AI Insight card (one takeaway) ───────────────────────────────────────

export function ScanResultInsightCard({ canCoaching, coaching, locked, onUpgradePress }) {
  if (!canCoaching || locked) {
    return (
      <View style={[premium.cardBase, styles.card]}>
        <Text style={[premium.title, styles.cardTitleSpacing]}>AI insight</Text>
        <View style={styles.lockedBox}>
          <Text style={styles.lockedTitle}>Locked 🔒</Text>
          <Text style={premium.body}>
            Satiety, Protein BV, Leucine, Glycemic load and Ultra-processed score are Pro+.
          </Text>
          <Text style={styles.lockedSub}>Upgrade to Pro or Infinite to unlock these insights.</Text>
          {onUpgradePress ? (
            <TouchableOpacity style={styles.lockedCta} onPress={onUpgradePress} activeOpacity={0.8}>
              <Text style={styles.lockedCtaText}>See plans</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </View>
    );
  }
  if (!coaching) {
    return null;
  }
  const sat = num(coaching.satiety_score);
  const bv = num(coaching.protein_bv_score);
  const firstMessage = Array.isArray(coaching.messages) && coaching.messages[0] ? String(coaching.messages[0]).trim() : null;
  const secondMessage = Array.isArray(coaching.messages) && coaching.messages[1] ? String(coaching.messages[1]).trim() : null;
  const insightLine =
    firstMessage ||
    (sat != null && bv != null
      ? `Satiety ${round1(sat)}/100 · Protein quality ${round1(bv)}/100`
      : sat != null
      ? `Satiety ${round1(sat)}/100 – ${coaching?.layman_terms?.satiety || "How filling this meal is."}`
      : bv != null
      ? `Protein quality ${round1(bv)}/100 – ${coaching?.layman_terms?.protein_bv || "How well your body can use the protein."}`
      : "Coaching insights available in details below.");

  return (
    <View style={[premium.cardBase, styles.card]}>
      <View style={styles.insightHeaderRow}>
        <Text style={[premium.title, styles.cardTitleSpacing]}>AI insight</Text>
        <View style={premium.pill}>
          <Text style={premium.pillText}>Key takeaway</Text>
        </View>
      </View>
      <Text style={premium.body}>{insightLine}</Text>
      {secondMessage ? (
        <Text style={styles.insightSecondary} numberOfLines={2}>
          • {secondMessage}
        </Text>
      ) : null}
    </View>
  );
}

// ─── Items breakdown card ───────────────────────────────────────────────

export function ScanResultItemsCard({ items }) {
  const list = Array.isArray(items) ? items : [];
  if (list.length === 0) return null;

  return (
    <View style={[premium.cardBase, styles.card]}>
      <Text style={[premium.title, styles.cardTitleSpacing]}>What we detected</Text>
      {list.map((it, idx) => (
        <View key={idx} style={styles.itemRow}>
          <Text style={styles.itemName} numberOfLines={2}>
            {it && typeof it === "object" ? String(it.name || "").trim() || "—" : "—"}
          </Text>
          <Text style={styles.itemMeta}>
            {round1(it?.grams)}g · {round1(it?.kcal)} kcal
          </Text>
        </View>
      ))}
    </View>
  );
}

// ─── Clarification card (wraps content from parent) ────────────────────────

export function ScanResultClarificationCard({ title, children }) {
  return (
    <View style={[premium.cardBase, styles.card]}>
      <Text style={[premium.title, styles.cardTitleSpacing]}>{title}</Text>
      {children}
    </View>
  );
}

// ─── Macro summary card ──────────────────────────────────────────────────

export function ScanResultMacroCard({ result }) {
  const t = result?.totals || {};
  const totalKcal = result?.total_kcal != null ? round1(result.total_kcal) : "—";
  const protein = t.protein_g != null ? round1(t.protein_g) : "—";
  const carbs = t.carbs_g != null ? round1(t.carbs_g) : "—";
  const fat = t.fat_g != null ? round1(t.fat_g) : "—";
  const density = getProteinKcalDensityLine(result || {});

  return (
    <View style={[premium.cardBase, styles.card]}>
      <View style={styles.macroRow}>
        <View style={styles.macroItem}>
          <Text style={styles.macroValue}>{totalKcal}</Text>
          <Text style={styles.macroUnit}>kcal</Text>
        </View>
        <View style={styles.macroItem}>
          <Text style={styles.macroValue}>{protein}</Text>
          <Text style={styles.macroUnit}>P</Text>
        </View>
        <View style={styles.macroItem}>
          <Text style={styles.macroValue}>{carbs}</Text>
          <Text style={styles.macroUnit}>C</Text>
        </View>
        <View style={styles.macroItem}>
          <Text style={styles.macroValue}>{fat}</Text>
          <Text style={styles.macroUnit}>F</Text>
        </View>
      </View>
      {density ? (
        <View style={styles.proteinDensityRow}>
          <Text style={styles.proteinDensityEmoji}>{density.emoji}</Text>
          <Text style={styles.proteinDensityText}>{density.line}</Text>
        </View>
      ) : null}
    </View>
  );
}

// ─── Expandable Details card ─────────────────────────────────────────────

export function ScanResultDetailsCard({ expanded, onToggle, children }) {
  return (
    <View style={[premium.cardBase, styles.card]}>
      <TouchableOpacity style={styles.detailsToggle} onPress={onToggle} activeOpacity={0.8}>
        <Text style={styles.detailsToggleText}>{expanded ? "Hide details" : "Show details"}</Text>
      </TouchableOpacity>
      {expanded && children ? <View style={styles.detailsContent}>{children}</View> : null}
    </View>
  );
}

// ─── Main screen ─────────────────────────────────────────────────────────

export function ScanResultScreen({
  result,
  photoUri,
  coaching,
  remainingToday,
  goalCoachDaily,
  canCoaching,
  rerunBusy,
  clarificationSelections,
  onApplyClarification,
  onClearScan,
  onOpenPaywall,
  postScanUpgradeBannerVisible,
  onDismissUpgradeBanner,
  childrenClarification,
  childrenDetails,
  primaryCtaLabel,
  onPrimaryCta,
  disclaimerText,
  disclaimerSources,
  onOpenSourceLink,
  // Optional: show a lightweight reward banner after scan.
  showRewardFeedback,
  // Optional: enable haptics if expo-haptics installed.
  enableHaptics,
  // Optional: screenshot mode (presentation-only).
  screenshotMode,
  /**
   * By default this component renders as a plain View container (no nested scrolling),
   * which is safer when ScanResultScreen is embedded inside an already-scrollable parent (e.g. Home).
   * Set true only when you render ScanResultScreen as a full-screen surface.
   */
  scrollable,
}) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const [justUpdated, setJustUpdated] = useState(false);
  const goalFit = getGoalFitLine(result || {}, remainingToday);
  const hasDetails = childrenDetails != null;
  const Root = scrollable ? ScrollView : View;
  const rootProps = scrollable
    ? { style: styles.container, contentContainerStyle: styles.content, showsVerticalScrollIndicator: false }
    : { style: [styles.container, styles.content] };
  const showPrimary = typeof onPrimaryCta === "function";
  const rewardLine = showRewardFeedback ? String(goalCoachDaily?.win_line || "").trim() : "";
  const rewardProteinStreak = showRewardFeedback ? num(goalCoachDaily?.protein_streak_days) : null;
  const rewardLoggingStreak = showRewardFeedback ? num(goalCoachDaily?.logging_streak_days) : null;
  const isScreenshot = Boolean(screenshotMode);
  const effectiveDetailsExpanded = isScreenshot ? false : detailsExpanded;
  const lastHapticKeyRef = useRef("");
  const prevRerunBusyRef = useRef(Boolean(rerunBusy));

  useEffect(() => {
    const prev = prevRerunBusyRef.current;
    const now = Boolean(rerunBusy);
    prevRerunBusyRef.current = now;
    if (prev && !now) {
      layoutEaseInOut();
      setJustUpdated(true);
      const t = setTimeout(() => setJustUpdated(false), 2200);
      if (enableHaptics) void hapticLight({ key: "scan:rerun_done", cooldownMs: 900 });
      return () => clearTimeout(t);
    }
    return undefined;
  }, [rerunBusy, enableHaptics]);

  useEffect(() => {
    if (!enableHaptics) return;
    if (!rewardLine) return;
    const key = String(result?.analysis_id || result?.meal_id || result?.id || "") + "::" + rewardLine;
    if (!key.trim()) return;
    if (lastHapticKeyRef.current === key) return;
    lastHapticKeyRef.current = key;
    void hapticSuccess({ key: `scan:reward:${key}`, cooldownMs: 3000 });
  }, [enableHaptics, rewardLine, result?.analysis_id, result?.meal_id, result?.id]);

  return (
    <Root {...rootProps}>
      {postScanUpgradeBannerVisible ? (
        <View style={styles.upgradeBanner}>
          <Text style={styles.upgradeBannerText} numberOfLines={2}>
            Get more scans + daily coaching — Upgrade
          </Text>
          <TouchableOpacity
            style={styles.upgradeBannerBtnWrap}
            onPress={() => {
              if (onDismissUpgradeBanner) onDismissUpgradeBanner();
              if (onOpenPaywall) onOpenPaywall(null);
            }}
            activeOpacity={0.8}
          >
            <Text style={styles.upgradeBannerBtn}>See plans</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.upgradeBannerCloseWrap} onPress={onDismissUpgradeBanner} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={styles.upgradeBannerClose}>✕</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={styles.section}>
        <ScanResultHero photoUri={photoUri} result={result} coaching={coaching} />
      </View>

      <View style={styles.section}>
        <ScanResultMacroCard result={result} />
      </View>

      {goalFit ? (
        <View style={styles.section}>
          <Text
            style={[
              styles.goalFitText,
              goalFit.tone === "success" && styles.goalFitSuccess,
              goalFit.tone === "amber" && styles.goalFitAmber,
            ]}
          >
            {goalFit.text}
          </Text>
        </View>
      ) : null}

      {rewardLine ? (
        <View style={styles.section}>
          <View style={styles.rewardBanner}>
            <View style={styles.rewardBannerTop}>
              <View style={styles.rewardDot} />
              <Text style={styles.rewardKicker}>Nice</Text>
              {justUpdated ? (
                <View style={premium.pill}>
                  <Text style={premium.pillText}>Updated</Text>
                </View>
              ) : null}
            </View>
            <Text style={styles.rewardBannerText} numberOfLines={3}>
              {rewardLine}
            </Text>
            {(rewardProteinStreak != null && rewardProteinStreak >= 2) || (rewardLoggingStreak != null && rewardLoggingStreak >= 2) ? (
              <View style={styles.rewardMetaRow}>
                {rewardProteinStreak != null && rewardProteinStreak >= 2 ? (
                  <View style={[premium.chipBaseSm, premium.chipSuccess, styles.rewardMetaChip]}>
                    <Text style={premium.chipTextSuccess}>{Math.round(rewardProteinStreak)}‑day protein</Text>
                  </View>
                ) : null}
                {rewardLoggingStreak != null && rewardLoggingStreak >= 2 ? (
                  <View style={[premium.chipBaseSm, premium.chipNeutral, styles.rewardMetaChip]}>
                    <Text style={premium.chipTextNeutral}>{Math.round(rewardLoggingStreak)}‑day logging</Text>
                  </View>
                ) : null}
              </View>
            ) : null}
          </View>
        </View>
      ) : null}

      {rerunBusy && !isScreenshot ? (
        <View style={styles.section}>
          <View style={styles.rerunBusyCard}>
            <Text style={styles.rerunBusyTitle}>Updating analysis</Text>
            <Text style={styles.rerunBusyText}>Applying your edit and recalculating kcal/macros…</Text>
          </View>
        </View>
      ) : null}

      {(canCoaching || result?.locked) ? (
        <View style={styles.section}>
          <ScanResultInsightCard
            canCoaching={canCoaching}
            coaching={coaching}
            locked={result?.locked}
            onUpgradePress={onOpenPaywall ? () => onOpenPaywall(null) : undefined}
          />
        </View>
      ) : null}

      {(result?.items?.length ?? 0) > 0 ? (
        <View style={styles.section}>
          <ScanResultItemsCard items={result?.items} />
        </View>
      ) : null}

      {childrenClarification ? (
        <View style={styles.section}>
          <ScanResultClarificationCard title="Improve accuracy">{childrenClarification}</ScanResultClarificationCard>
        </View>
      ) : null}

      {hasDetails ? (
        <View style={styles.section}>
          <ScanResultDetailsCard
            expanded={effectiveDetailsExpanded}
            onToggle={() => {
              if (isScreenshot) return;
              layoutEaseInOut();
              if (enableHaptics) void hapticLight({ key: "scan:details_toggle", cooldownMs: 500 });
              setDetailsExpanded((e) => !e);
            }}
          >
            {childrenDetails}
          </ScanResultDetailsCard>
        </View>
      ) : null}

      <View style={styles.section}>
        {showPrimary ? (
          <TouchableOpacity
            style={premium.ctaPrimary}
            onPress={onPrimaryCta}
            disabled={rerunBusy}
            activeOpacity={0.85}
          >
            <Text style={premium.ctaPrimaryText}>{primaryCtaLabel || "Done"}</Text>
          </TouchableOpacity>
        ) : null}
        {onClearScan && !isScreenshot ? (
          <TouchableOpacity
            style={[premium.ctaSecondary, { marginTop: spacing.base }]}
            onPress={onClearScan}
            disabled={rerunBusy}
            activeOpacity={0.8}
          >
            <Text style={premium.ctaSecondaryText}>Clear scan</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      {disclaimerText && !isScreenshot ? (
        <View style={styles.disclaimerSection}>
          <Text style={styles.disclaimerText}>{disclaimerText}</Text>
          {disclaimerSources && disclaimerSources.length > 0 && onOpenSourceLink ? (
            <View style={styles.sourcesList}>
              {disclaimerSources.map((s) => (
                <TouchableOpacity
                  key={s.url || s.title}
                  onPress={() => onOpenSourceLink(s?.url, "Could not open source link.")}
                  style={styles.sourceItem}
                >
                  <Text style={styles.sourceLink}>· {s?.title || s?.url || "Source"}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </Root>
  );
}

// ─── Styles ─────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff8eb",
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.section * 2,
  },
  section: {
    marginBottom: spacing.lg,
  },
  // Local overrides only; base card comes from premium.cardBase.
  card: {},
  cardTitleSpacing: { marginBottom: spacing.base },
  heroWrap: {
    position: "relative",
    borderRadius: radius.xl,
    overflow: "hidden",
    borderWidth: 2,
    borderColor: "#ffbc0d",
    ...shadows.md,
  },
  heroImage: {
    width: "100%",
    aspectRatio: 4 / 3,
    borderRadius: radius.xl,
  },
  heroPlaceholder: {
    width: "100%",
    aspectRatio: 4 / 3,
    backgroundColor: colors.surface.elevated,
    borderRadius: radius.xl,
  },
  heroOverlay: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: spacing.lg,
    backgroundColor: "rgba(17,24,39,0.72)",
  },
  heroMealLabel: {
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
  },
  heroKcal: {
    fontSize: 28,
    fontWeight: typography.weight.extrabold,
    color: colors.text.primary,
    marginTop: spacing.xs,
  },
  qualityBadge: {
    position: "absolute",
    top: spacing.base,
    right: spacing.base,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    backgroundColor: "#fff7e6",
  },
  qualityBadgeText: {
    fontSize: typography.sm,
    fontWeight: typography.weight.bold,
  },
  macroRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "rgba(255,188,13,0.12)",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: "rgba(245,158,11,0.28)",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
  },
  macroItem: {
    alignItems: "center",
  },
  macroValue: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
    color: colors.text.primary,
  },
  macroUnit: {
    fontSize: typography.sm,
    color: colors.text.muted,
    marginTop: spacing.xxs,
  },
  proteinDensityRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.base,
    paddingTop: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
    gap: spacing.sm,
  },
  proteinDensityEmoji: {
    fontSize: typography.hero,
  },
  proteinDensityText: {
    flex: 1,
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.secondary,
    lineHeight: typography.sm * 1.35,
  },
  goalFitText: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    backgroundColor: "rgba(255,255,255,0.7)",
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderWidth: 1,
    borderColor: "rgba(245,158,11,0.30)",
  },
  goalFitSuccess: {
    color: colors.success.text,
  },
  goalFitAmber: {
    color: colors.amber.text,
  },
  rerunBusyText: {
    fontSize: typography.sm,
    color: colors.text.muted,
  },
  insightHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  insightSecondary: {
    marginTop: spacing.sm,
    fontSize: typography.sm,
    color: colors.text.muted,
    lineHeight: typography.sm * typography.lineHeight.relaxed,
  },
  lockedBox: {
    backgroundColor: colors.surface.elevated,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    padding: spacing.base,
  },
  lockedTitle: {
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
    color: colors.text.primary,
    marginBottom: spacing.sm,
  },
  lockedSub: {
    fontSize: typography.sm,
    color: colors.text.muted,
    marginTop: spacing.xs,
  },
  lockedCta: {
    marginTop: spacing.base,
    alignSelf: "flex-start",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
  },
  lockedCtaText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
    fontWeight: typography.weight.semibold,
  },
  itemRow: {
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface.cardBorder,
  },
  itemName: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
  },
  itemMeta: {
    fontSize: typography.sm,
    color: colors.text.muted,
    marginTop: spacing.xs,
  },
  upgradeBanner: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.base,
    padding: spacing.base,
    backgroundColor: "#ffefc8",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: "#f7b500",
  },
  upgradeBannerText: {
    flex: 1,
    fontSize: typography.sm,
    color: "#7c2d12",
  },
  upgradeBannerBtnWrap: {
    marginLeft: spacing.sm,
  },
  upgradeBannerBtn: {
    fontSize: typography.sm,
    color: "#92400e",
    fontWeight: typography.weight.semibold,
  },
  upgradeBannerCloseWrap: {
    marginLeft: spacing.sm,
    padding: spacing.xs,
  },
  upgradeBannerClose: {
    fontSize: typography.sm,
    color: "#92400e",
  },
  detailsToggle: {
    paddingVertical: spacing.base,
  },
  detailsToggleText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
    fontWeight: typography.weight.semibold,
  },
  detailsContent: {
    marginTop: spacing.sm,
    paddingTop: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.surface.cardBorder,
  },
  // CTA styles now sourced from premium system.
  disclaimerSection: {
    marginTop: spacing.xl,
    paddingTop: spacing.lg,
  },
  disclaimerText: {
    fontSize: typography.xs,
    color: colors.text.muted,
    lineHeight: typography.xs * 1.4,
  },
  rewardBanner: {
    backgroundColor: "rgba(255, 188, 13, 0.18)",
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: "rgba(245, 158, 11, 0.40)",
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
  },
  rewardBannerTop: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  rewardDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: "#f59e0b",
    marginRight: spacing.sm,
  },
  rewardKicker: {
    fontSize: typography.sm,
    fontWeight: typography.weight.extrabold,
    color: "#92400e",
    letterSpacing: 0.2,
  },
  rewardBannerText: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: "#7c2d12",
    lineHeight: typography.md * typography.lineHeight.relaxed,
  },
  rewardMetaRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.base,
  },
  rewardMetaChip: {
    marginRight: spacing.sm,
  },
  rerunBusyCard: {
    backgroundColor: colors.surface.elevated,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.base,
    paddingHorizontal: spacing.lg,
  },
  rerunBusyTitle: {
    fontSize: typography.sm,
    fontWeight: typography.weight.extrabold,
    color: colors.text.secondary,
    marginBottom: spacing.xs,
  },
  sourcesList: {
    marginTop: spacing.base,
  },
  sourceItem: {
    marginBottom: spacing.sm,
  },
  sourceLink: {
    fontSize: typography.xs,
    color: colors.accent.primary,
  },
});
