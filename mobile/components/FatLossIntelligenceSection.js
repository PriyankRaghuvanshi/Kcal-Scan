/**
 * Fat Loss Intelligence – premium AI coaching dashboard.
 * Refinements: no gap (margins only), weekly hero labeled as weekly,
 * card spacing from wrapper, weekly wins/risks stacked vertically,
 * CTAs stacked for mobile safety.
 */

import React from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function FatLossIntelligenceSection({
  // Data
  weeklyReport,
  coachDaily,
  coachVoice,
  // Loading / error
  weeklyReportBusy,
  coachBusy,
  coachErr,
  // Access
  canCoaching,
  coachProfile,
  plan,
  coachUpgradeBody,
  coachPreviewTiles,
  previewPhotoUri,
  showCoachDebug,
  // Handlers
  onCoachTitleTap,
  onProfilePress,
  onRefreshPress,
  onWeeklyPress,
  onShareWeeklyCard,
  onOpenPaywall,
  onOpenPaywallAllPlans,
  setCoachProfileDraft,
  setCoachProfileModal,
  setShowCoachDebug,
  setAdminOpsVisible,
  ensureDailyCoach,
  fetchWeeklyReport,
  openPaywall,
  // Optional: score tone helper (from App or inline)
  scoreTone,
  clampPct,
  fliUpdatedLabel,
}) {
  const coachTone = scoreTone
    ? scoreTone(coachDaily?.fat_loss_score)
    : { color: colors.success.primary, label: "On track", bg: colors.success.bg };
  const coachBadgeText =
    coachDaily?.fli_source === "llm" || coachDaily?.source === "llm"
      ? "Live"
      : coachDaily?.fli_source === "cached_llm" || coachDaily?.source === "cache"
      ? "Cached"
      : "Rules";
  const coachIsLive = coachBadgeText === "Live";

  if (!canCoaching) {
    return (
      <View style={styles.sectionWrapper}>
        <View style={styles.card}>
          <View style={styles.headerRow}>
            <TouchableOpacity onPress={onCoachTitleTap} activeOpacity={0.9}>
              <Text style={styles.sectionTitle}>Fat Loss Intelligence</Text>
            </TouchableOpacity>
            <View style={styles.badgePro}>
              <Text style={styles.badgeProText}>Pro</Text>
            </View>
          </View>
          <Text style={styles.sectionSub}>
            Daily and weekly AI insights based on your scans.
          </Text>
          <Text style={[styles.bodyText, { marginTop: spacing.base }]}>
            {typeof coachUpgradeBody === "function" ? coachUpgradeBody(plan) : coachUpgradeBody}
          </Text>
          {Array.isArray(coachPreviewTiles) && coachPreviewTiles.length > 0 ? (
            <View style={styles.previewTiles}>
              {coachPreviewTiles.slice(0, 3).map((tile) => (
                <View key={tile.key} style={styles.previewTile}>
                  <Text style={styles.previewTileUnlock}>{String(tile.unlock || "").trim()}</Text>
                  <Text style={styles.previewTileTitle}>{String(tile.title || "").trim()}</Text>
                  <Text style={styles.previewTileSub}>{String(tile.subtitle || "").trim()}</Text>
                </View>
              ))}
            </View>
          ) : null}
          <TouchableOpacity style={styles.ctaPrimary} onPress={() => openPaywall?.("pro")} activeOpacity={0.9}>
            <Text style={styles.ctaPrimaryText}>Unlock with Pro</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.ctaLink} onPress={onOpenPaywallAllPlans} activeOpacity={0.8}>
            <Text style={styles.ctaLinkText}>See all plans</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.sectionWrapper}>
      {/* Header */}
      <View style={styles.headerRow}>
        <TouchableOpacity onPress={onCoachTitleTap} activeOpacity={0.9}>
          <Text style={styles.sectionTitle}>Fat Loss Intelligence</Text>
        </TouchableOpacity>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.headerActions}
        >
          <TouchableOpacity style={styles.headerBtn} onPress={onProfilePress}>
            <Text style={styles.headerBtnText}>Profile</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerBtn} onPress={onRefreshPress} disabled={coachBusy}>
            <Text style={styles.headerBtnText}>{coachBusy ? "…" : "Refresh"}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerBtn} onPress={onWeeklyPress} disabled={weeklyReportBusy}>
            <Text style={styles.headerBtnText}>{weeklyReportBusy ? "…" : "Weekly"}</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>
      <Text style={styles.sectionSub}>
        {coachProfile
          ? `${coachProfile?.goal_type || "fat_loss"} • ${coachProfile?.diet_style || "non-veg"} • ${Math.round(num(coachProfile?.training_days_per_week) || 0)} day(s)/week`
          : "Daily and weekly AI insights based on your scans."}
      </Text>

      {coachErr ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{coachErr}</Text>
        </View>
      ) : null}

      {coachBusy && !coachDaily ? (
        <View style={styles.card}>
          <ActivityIndicator color={colors.success.primary} />
          <Text style={[styles.bodyText, { marginTop: spacing.base }]}>Loading insights…</Text>
        </View>
      ) : (
        <>
          {/* 1. Hero: Readiness this week (weekly-derived; not "today") */}
          {weeklyReport ? (
            <View style={[styles.cardSpacer, styles.heroCard]}>
              <FLIHeroReadinessCard weeklyReport={weeklyReport} />
            </View>
          ) : null}

          {/* 2. Daily score + one thing (from coachDaily) */}
          {coachDaily ? (
            <View style={styles.cardSpacer}>
              <View style={styles.card}>
                <FLIDailyFocusCard coachDaily={coachDaily} coachTone={coachTone} clampPct={clampPct} fliUpdatedLabel={fliUpdatedLabel} />
              </View>
            </View>
          ) : null}

          {/* 3. Coach voice */}
          {coachVoice ? (
            <View style={styles.cardSpacer}>
              <View style={styles.card}>
                <FLICoachVoiceCard coachVoice={coachVoice} />
              </View>
            </View>
          ) : null}

          {/* 4. Weekly report – vertical stack (wins then risks), stacked CTAs */}
          {weeklyReport ? (
            <View style={styles.cardSpacer}>
              <View style={styles.card}>
                <FLIWeeklyReportCard
                  weeklyReport={weeklyReport}
                  onShare={onShareWeeklyCard}
                  shareDisabled={weeklyReportBusy}
                />
              </View>
            </View>
          ) : weeklyReportBusy ? (
            <View style={styles.cardSpacer}>
              <View style={styles.card}>
                <ActivityIndicator color={colors.success.primary} />
                <Text style={[styles.bodyText, { marginTop: spacing.base }]}>Loading weekly report…</Text>
              </View>
            </View>
          ) : null}

          {showCoachDebug && coachDaily ? (
            <View style={styles.cardSpacer}>
              <View style={styles.card}>
                <View style={styles.debugRow}>
                  <Text style={styles.debugTitle}>Debug</Text>
                  <TouchableOpacity style={styles.headerBtn} onPress={() => setAdminOpsVisible?.(true)}>
                    <Text style={styles.headerBtnText}>Ops</Text>
                  </TouchableOpacity>
                </View>
                <Text style={styles.tiny}>source: {String(coachDaily?.source || "-")}</Text>
                <Text style={styles.tiny}>fli_source: {String(coachDaily?.fli_source || "-")}</Text>
              </View>
            </View>
          ) : null}
        </>
      )}
    </View>
  );
}

function FLIHeroReadinessCard({ weeklyReport }) {
  const resilience = num(weeklyReport?.resilience_score) || 0;
  const risk = num(weeklyReport?.risk_score) || 0;

  let band = "Medium";
  let bandColor = colors.amber.text;
  if (resilience >= 75 && risk <= 40) {
    band = "High";
    bandColor = colors.success.text;
  } else if (resilience <= 55 || risk >= 60) {
    band = "Low";
    bandColor = colors.warning.text;
  }

  return (
    <>
      <Text style={styles.heroLabel}>Readiness this week</Text>
      <View style={styles.heroScoreRow}>
        <View>
          <Text style={styles.heroScore}>{Math.round(resilience)}/100</Text>
          <Text style={styles.heroSubScore}>Risk {Math.round(risk)}/100</Text>
        </View>
        <View style={styles.heroBand}>
          <Text style={[styles.heroBandText, { color: bandColor }]}>{band.toUpperCase()}</Text>
        </View>
      </View>
      <Text style={styles.heroHint}>
        Based on protein consistency, UPF, and meal timing over the last 7 days.
      </Text>
    </>
  );
}

function FLIDailyFocusCard({ coachDaily, coachTone, clampPct, fliUpdatedLabel }) {
  const score = num(coachDaily?.fat_loss_score);
  const oneSentence = String(coachDaily?.one_sentence_summary || coachDaily?.coach_summary || "").trim();
  const oneAction = String(coachDaily?.one_action || coachDaily?.if_you_do_one_thing || "").trim();
  const widthPct = typeof clampPct === "function" && score != null ? clampPct(score) : Math.min(100, Math.max(0, score));

  return (
    <>
      <Text style={styles.cardTitle}>Today’s focus</Text>
      <View style={styles.scoreRow}>
        <View style={[styles.scoreOrb, { borderColor: coachTone.color }]}>
          <Text style={styles.scoreOrbValue}>{Math.round(score || 0)}</Text>
          <Text style={styles.scoreOrbUnit}>/100</Text>
        </View>
        <View style={styles.scoreMeta}>
          <View style={[styles.badgePill, { backgroundColor: coachTone.bg, borderColor: coachTone.color }]}>
            <Text style={[styles.badgePillText, { color: coachTone.color }]}>{coachTone.label}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${widthPct}%`, backgroundColor: coachTone.color }]} />
          </View>
          {typeof fliUpdatedLabel === "function" && (
            <Text style={styles.tiny}>{fliUpdatedLabel(coachDaily, false)}</Text>
          )}
        </View>
      </View>
      {oneSentence ? <Text style={styles.bodyText}>{oneSentence}</Text> : null}
      {oneAction ? (
        <View style={styles.oneThingBlock}>
          <Text style={styles.oneThingLabel}>If you do one thing</Text>
          <Text style={styles.oneThingText}>{oneAction}</Text>
        </View>
      ) : null}
    </>
  );
}

function FLICoachVoiceCard({ coachVoice }) {
  const empathy = String(coachVoice?.empathy_line || "").trim();
  const insight = String(coachVoice?.insight_line || "").trim();
  const oneAction = coachVoice?.one_action;
  const steps = Array.isArray(oneAction?.steps) ? oneAction.steps : [];
  const why = String(coachVoice?.why_this_action || "").trim();
  const disclaimer = String(coachVoice?.safety_disclaimer || "").trim();

  return (
    <>
      <Text style={styles.cardTitle}>Coach voice</Text>
      {empathy ? <Text style={styles.bodyText}>{empathy}</Text> : null}
      {insight ? <Text style={[styles.bodyText, { marginTop: spacing.sm }]}>{insight}</Text> : null}
      {oneAction?.title ? (
        <View style={styles.oneThingBlock}>
          <Text style={styles.itemName}>{oneAction.title}</Text>
          {steps.map((s, i) => (
            <Text key={i} style={styles.tiny}>• {String(s || "").trim()}</Text>
          ))}
          {why ? <Text style={[styles.tiny, { marginTop: spacing.xs }]}>{why}</Text> : null}
        </View>
      ) : null}
      {disclaimer ? <Text style={[styles.tiny, { marginTop: spacing.sm }]}>{disclaimer}</Text> : null}
    </>
  );
}

function FLIWeeklyReportCard({ weeklyReport, onShare, shareDisabled }) {
  const wins = (weeklyReport?.top_wins || []).slice(0, 2);
  const risks = (weeklyReport?.top_risks || []).slice(0, 2);
  const weekStart = String(weeklyReport?.week_start || "").trim();
  const weekEnd = String(weeklyReport?.week_end || "").trim();
  const disclaimer = String(weeklyReport?.disclaimer || "").trim();

  return (
    <>
      <Text style={styles.cardTitle}>Weekly pattern</Text>
      {weekStart && weekEnd ? (
        <Text style={styles.tiny}>
          {weekStart} to {weekEnd} • {String(weeklyReport?.confidence_band || "medium")}
        </Text>
      ) : null}
      <Text style={[styles.bodyText, { marginTop: spacing.xs }]}>
        Resilience {Math.round(num(weeklyReport?.resilience_score) || 0)}/100 • Risk{" "}
        {Math.round(num(weeklyReport?.risk_score) || 0)}/100
      </Text>

      {/* Vertical stack: wins then risks (no two-column on small screens) */}
      <View style={styles.weekStack}>
        <Text style={styles.weekStackLabel}>Wins</Text>
        {wins.map((w, i) => (
          <Text key={`w-${i}`} style={styles.bullet}>• {String(w?.title || "").trim()}</Text>
        ))}
      </View>
      <View style={styles.weekStack}>
        <Text style={styles.weekStackLabel}>Risks</Text>
        {risks.map((r, i) => (
          <Text key={`r-${i}`} style={styles.bullet}>• {String(r?.title || "").trim()}</Text>
        ))}
      </View>
      {disclaimer ? <Text style={[styles.tiny, { marginTop: spacing.base }]}>{disclaimer}</Text> : null}

      {/* Stacked CTAs – mobile-safe vertical layout */}
      <View style={styles.ctaStack}>
        <TouchableOpacity style={styles.ctaPrimary} onPress={onShare} disabled={shareDisabled} activeOpacity={0.9}>
          <Text style={styles.ctaPrimaryText}>{shareDisabled ? "…" : "Share weekly card"}</Text>
        </TouchableOpacity>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  sectionWrapper: {
    marginTop: spacing.xl,
    marginBottom: spacing.xl,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.xs,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    marginLeft: spacing.base,
  },
  headerBtn: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.base,
    marginLeft: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    backgroundColor: colors.surface.primary,
  },
  headerBtnText: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    fontWeight: typography.weight.semibold,
  },
  sectionTitle: {
    fontSize: typography.lg,
    fontWeight: typography.weight.extrabold,
    color: colors.text.primary,
  },
  sectionSub: {
    marginTop: spacing.xs,
    marginBottom: spacing.base,
    fontSize: typography.sm,
    color: colors.text.secondary,
  },
  badgePro: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.amber.bg,
    borderWidth: 1,
    borderColor: colors.amber.border,
  },
  badgeProText: {
    fontSize: typography.xs,
    color: colors.amber.text,
    fontWeight: typography.weight.semibold,
  },
  errorBanner: {
    marginBottom: spacing.base,
    padding: spacing.base,
    borderRadius: radius.lg,
    backgroundColor: "rgba(239,68,68,0.12)",
    borderWidth: 1,
    borderColor: colors.warning.primary,
  },
  errorText: {
    fontSize: typography.sm,
    color: colors.warning.text,
  },
  cardSpacer: {
    marginTop: spacing.lg,
  },
  card: {
    backgroundColor: colors.surface.card,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
  },
  heroCard: {
    ...shadows.md,
  },
  cardTitle: {
    fontSize: typography.lg,
    fontWeight: typography.weight.extrabold,
    color: colors.text.primary,
    marginBottom: spacing.sm,
  },
  bodyText: {
    fontSize: typography.md,
    color: colors.text.secondary,
    lineHeight: typography.md * 1.45,
  },
  tiny: {
    fontSize: typography.sm,
    color: colors.text.muted,
  },
  /* Hero */
  heroLabel: {
    fontSize: typography.sm,
    color: colors.text.muted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  heroScoreRow: {
    marginTop: spacing.sm,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  heroScore: {
    fontSize: 28,
    fontWeight: typography.weight.extrabold,
    color: colors.text.primary,
  },
  heroSubScore: {
    marginTop: spacing.xs,
    fontSize: typography.md,
    color: colors.text.secondary,
  },
  heroBand: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.base,
    borderRadius: radius.pill,
    backgroundColor: colors.surface.primary,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
  },
  heroBandText: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
  },
  heroHint: {
    marginTop: spacing.base,
    fontSize: typography.sm,
    color: colors.text.muted,
  },
  /* Daily focus */
  scoreRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.base,
  },
  scoreOrb: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.base,
  },
  scoreOrbValue: {
    fontSize: typography.xxl,
    fontWeight: typography.weight.extrabold,
    color: colors.text.primary,
  },
  scoreOrbUnit: {
    fontSize: typography.sm,
    color: colors.text.muted,
  },
  scoreMeta: {
    flex: 1,
  },
  badgePill: {
    alignSelf: "flex-start",
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  badgePillText: {
    fontSize: typography.xs,
    fontWeight: typography.weight.semibold,
  },
  progressTrack: {
    marginTop: spacing.sm,
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.surface.primary,
  },
  progressFill: {
    height: 6,
    borderRadius: 999,
  },
  oneThingBlock: {
    marginTop: spacing.lg,
  },
  oneThingLabel: {
    fontSize: typography.sm,
    color: colors.text.muted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  oneThingText: {
    marginTop: spacing.xs,
    fontSize: typography.md,
    color: colors.text.primary,
    fontWeight: typography.weight.semibold,
  },
  itemName: {
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
  },
  /* Weekly – vertical stack */
  weekStack: {
    marginTop: spacing.base,
  },
  weekStackLabel: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
    marginBottom: spacing.xs,
  },
  bullet: {
    fontSize: typography.sm,
    color: colors.text.secondary,
    marginTop: spacing.xs,
  },
  /* CTAs – stacked */
  ctaStack: {
    marginTop: spacing.xl,
  },
  ctaPrimary: {
    paddingVertical: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.success.primary,
    alignItems: "center",
  },
  ctaPrimaryText: {
    fontSize: typography.md,
    fontWeight: typography.weight.bold,
    color: colors.text.inverse,
  },
  ctaLink: {
    marginTop: spacing.base,
    alignItems: "center",
  },
  ctaLinkText: {
    fontSize: typography.sm,
    color: colors.accent.primary,
    textDecorationLine: "underline",
  },
  /* Locked preview */
  previewTiles: {
    marginTop: spacing.lg,
  },
  previewTile: {
    marginTop: spacing.sm,
    padding: spacing.base,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
    backgroundColor: colors.surface.primary,
  },
  previewTileUnlock: {
    fontSize: typography.xs,
    color: colors.text.muted,
    textTransform: "uppercase",
  },
  previewTileTitle: {
    marginTop: spacing.xs,
    fontSize: typography.md,
    fontWeight: typography.weight.semibold,
    color: colors.text.primary,
  },
  previewTileSub: {
    marginTop: spacing.xs,
    fontSize: typography.sm,
    color: colors.text.secondary,
  },
  debugRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  debugTitle: {
    fontSize: typography.sm,
    fontWeight: typography.weight.bold,
    color: colors.text.muted,
  },
});
