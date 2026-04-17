/**
 * BestOrderEvidence – additive trust/evidence UI for "Best order right now".
 * Renders nothing when evidence fields are missing.
 */
import React, { useMemo, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Linking } from "react-native";
import { colors, spacing, radius, typography } from "../designTokens";

function safeStr(v) {
  return String(v ?? "").trim();
}
function safeNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function mapConfidenceLabelToTier(confidenceLabel) {
  const lbl = safeStr(confidenceLabel);
  if (lbl === "Verified") return "verified";
  if (lbl === "Chain-backed" || lbl === "Chain menu") return "chain_backed";
  if (lbl === "Estimated") return "estimated";
  if (lbl === "Needs menu check") return "needs_menu_check";
  return "";
}

function resolveEvidenceFields(payload, mode) {
  const p = payload && typeof payload === "object" ? payload : {};
  if (mode === "card") {
    return {
      tier: safeStr(p.recommended_order_trust_tier),
      strength: safeNum(p.recommended_order_evidence_strength),
      summary: safeStr(p.recommended_order_evidence_summary),
      reasons: Array.isArray(p.recommended_order_evidence_reasons) ? p.recommended_order_evidence_reasons : [],
      url: safeStr(p.recommended_order_citation_url),
      fallbackConfidenceLabel: safeStr(p.confidence_label),
      verifiedStatus: safeStr(p.recommended_order_verified_status || p.verified_status),
      isVerified: Boolean(p.recommended_order_is_verified ?? p.is_verified),
      verifiedReasons: Array.isArray(p.recommended_order_verified_reason_codes)
        ? p.recommended_order_verified_reason_codes
        : (Array.isArray(p.verified_reason_codes) ? p.verified_reason_codes : []),
      verifiedPolicyVersion: safeStr(p.recommended_order_verified_policy_version || p.verified_policy_version),
    };
  }
  return {
    tier: safeStr(p.best_order_trust_tier),
    strength: safeNum(p.best_order_evidence_strength),
    summary: safeStr(p.best_order_evidence_summary),
    reasons: Array.isArray(p.best_order_evidence_reasons) ? p.best_order_evidence_reasons : [],
    url: safeStr(p.best_order_citation_url),
    fallbackConfidenceLabel: safeStr(p.confidence_label),
    verifiedStatus: safeStr(p.best_order_verified_status || p.verified_status),
    isVerified: Boolean(p.best_order_is_verified ?? p.is_verified),
    verifiedReasons: Array.isArray(p.best_order_verified_reason_codes)
      ? p.best_order_verified_reason_codes
      : (Array.isArray(p.verified_reason_codes) ? p.verified_reason_codes : []),
    verifiedPolicyVersion: safeStr(p.best_order_verified_policy_version || p.verified_policy_version),
  };
}

function tierLabel(tier) {
  if (tier === "verified") return "Verified";
  if (tier === "chain_backed") return "Chain menu";
  if (tier === "estimated") return "Estimated";
  if (tier === "needs_menu_check") return "Needs menu check";
  return "";
}

function tierTone(tier, dark) {
  const text = dark ? colors.text.primary : colors.textLight.primary;
  const muted = dark ? colors.slate.text : colors.textLight.muted;
  if (tier === "verified") return { bg: "#062315", border: "#1f8f4d", text: "#86efac" };
  if (tier === "chain_backed") return { bg: "#061a2a", border: "#2563eb", text: "#93c5fd" };
  if (tier === "estimated") return { bg: "#22160a", border: "#f59e0b", text: "#fbbf24" };
  if (tier === "needs_menu_check") return { bg: dark ? "#0b1220" : "#eef2ff", border: dark ? "#334155" : "#c7d2fe", text: muted || text };
  return { bg: "transparent", border: "transparent", text: muted || text };
}

async function openUrlSafe(url) {
  const u = safeStr(url);
  if (!u) return;
  try {
    const ok = await Linking.canOpenURL(u);
    if (ok) await Linking.openURL(u);
  } catch {}
}

export function BestOrderTrustBadge({ tier, dark = true, compact = false, style }) {
  const t = safeStr(tier);
  const label = tierLabel(t);
  if (!label) return null;
  const tone = tierTone(t, dark);
  return (
    <View
      style={[
        styles.badge,
        compact && styles.badgeCompact,
        { backgroundColor: tone.bg, borderColor: tone.border },
        style,
      ]}
    >
      <Text style={[styles.badgeText, { color: tone.text }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

function VerifiedChip({ compact = false, style }) {
  return (
    <View style={[styles.verifiedChip, compact && styles.verifiedChipCompact, style]}>
      <Text style={styles.verifiedChipText} numberOfLines={1}>
        Verified
      </Text>
    </View>
  );
}

export function BestOrderEvidenceSummary({ summary, dark = true, compact = false, style }) {
  const text = safeStr(summary);
  if (!text) return null;
  const color = dark ? colors.slate.text : colors.textLight.muted;
  return (
    <Text
      style={[
        styles.summary,
        compact && styles.summaryCompact,
        { color },
        style,
      ]}
      numberOfLines={1}
    >
      {text}
    </Text>
  );
}

export function BestOrderProofDrawer({
  reasons,
  citationUrl,
  dark = true,
  compact = false,
  screenshotMode,
  style,
}) {
  const isScreenshot = Boolean(screenshotMode);
  function formatEvidenceReason(raw) {
    const r = safeStr(raw);
    if (!r) return null;

    // Backend may emit machine-friendly sentences like:
    // "User confirmed availability."
    // Render them in a cleaner, more natural UI form.
    const m = r.match(/^user\s+confirmed\s+(.*)$/i);
    if (m && m[1]) {
      const rest = String(m[1] || "").trim().replace(/\.$/, "");
      return { text: `Confirmed by users: ${rest}${rest.endsWith(".") ? "" : "."}`, isUserConfirmed: true };
    }

    return { text: r, isUserConfirmed: false };
  }

  const list = Array.isArray(reasons)
    ? reasons
        .filter(Boolean)
        .map((r) => formatEvidenceReason(r))
        .filter(Boolean)
    : [];
  const url = safeStr(citationUrl);
  const hasContent = list.length > 0 || Boolean(url);
  const [open, setOpen] = useState(false);
  if (!hasContent) return null;
  if (isScreenshot) return null;

  const textPrimary = dark ? colors.text.primary : colors.textLight.primary;
  const textMuted = dark ? colors.slate.text : colors.textLight.muted;

  return (
    <View style={[styles.drawerWrap, style]}>
      <TouchableOpacity
        style={styles.drawerToggle}
        onPress={() => setOpen((v) => !v)}
        activeOpacity={0.8}
      >
        <Text style={[styles.drawerToggleText, { color: textMuted }]} numberOfLines={1}>
          {open ? "Hide proof" : "Why this pick?"}
        </Text>
      </TouchableOpacity>
      {open ? (
        <View style={[styles.drawerBody, compact && styles.drawerBodyCompact]}>
          {list.slice(0, 4).map((row, idx) => (
            <Text
              key={`ev-${idx}`}
              style={[styles.reason, { color: row?.isUserConfirmed ? colors.accent.primary : textPrimary }]}
              numberOfLines={2}
            >
              • {row?.text}
            </Text>
          ))}
          {url ? (
            <TouchableOpacity
              style={styles.sourceLinkWrap}
              onPress={() => void openUrlSafe(url)}
              activeOpacity={0.8}
            >
              <Text style={[styles.sourceLink, { color: colors.accent.primary }]} numberOfLines={1}>
                Source
              </Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

export function BestOrderEvidenceBlock({
  payload,
  mode = "place", // "place" | "card"
  dark = true,
  compact = false,
  screenshotMode,
  style,
}) {
  const resolved = useMemo(() => resolveEvidenceFields(payload, mode), [payload, mode]);

  const tier =
    safeStr(resolved.tier) ||
    mapConfidenceLabelToTier(resolved.fallbackConfidenceLabel);
  const strength = resolved.strength;
  const summary = resolved.summary;
  const reasons = resolved.reasons;
  const url = resolved.url;
  const verifiedStatus = safeStr(resolved.verifiedStatus).toLowerCase();
  const isVerified = Boolean(resolved.isVerified);

  const hasAny =
    Boolean(tier) ||
    Boolean(summary) ||
    (Array.isArray(reasons) && reasons.length > 0) ||
    Boolean(url);
  if (!hasAny) return null;

  function summaryFromUserConfirmedReasons(userReasons) {
    // Only summarize user-confirmed reasons; do not alter proof drawer bullets.
    const normalized = (userReasons || [])
      .filter(Boolean)
      .map((r) => safeStr(r))
      .filter(Boolean);

    const byPrefix = (prefix) => normalized.find((r) => r.toLowerCase().startsWith(prefix.toLowerCase()));

    const cardType = String(payload?.card_type || "").trim().toLowerCase();
    const distM = safeNum(payload?.distance_meters);
    const isHere =
      mode === "card" &&
      cardType === "best_right_now" &&
      distM != null &&
      Number.isFinite(distM) &&
      distM >= 0 &&
      distM <= 100;

    // Decision cards: surface "here" vs "nearby" with the conservative heuristic.
    if (mode === "card") {
      if (byPrefix("User confirmed availability.")) return isHere ? "Usually available here" : "Usually available nearby";
      if (byPrefix("User confirmed they ordered this.")) return isHere ? "Often ordered here" : "Often ordered nearby";
      if (byPrefix("User confirmed sauce-by-default assumption.")) return isHere ? "Sauce usually included here" : "Sauce usually included nearby";
      if (byPrefix("User confirmed portion looked standard.")) return isHere ? "Portion usually standard here" : "Portion usually standard nearby";
      return "";
    }

    // Place cards: never claim "here".
    if (mode === "place") {
      if (byPrefix("User confirmed availability.")) return "Usually available at this location";
      if (byPrefix("User confirmed they ordered this.")) return "Often ordered at this location";
      if (byPrefix("User confirmed sauce-by-default assumption.")) return "Sauce usually included at this location";
      if (byPrefix("User confirmed portion looked standard.")) return "Portion usually standard at this location";
      return "";
    }

    return "";
  }

  const displaySummary = (() => {
    const userSummary = summaryFromUserConfirmedReasons(reasons);
    if (userSummary) return userSummary;

    // Prefer backend-provided summary to avoid fabricating copy.
    if (summary) return summary;

    // If backend summary is missing, fall back to exact tier phrases used by backend.
    if (tier === "verified") return "Evidence-backed pick.";
    if (tier === "chain_backed") return "Chain-backed pick.";
    if (tier === "estimated") return "Estimated pick — confirm if menu varies.";
    if (tier === "needs_menu_check") return "Needs menu check.";
    return "";
  })();

  // Keep compact cards tight: show summary only when it's strong or explicit.
  const showSummary =
    !compact ||
    Boolean(displaySummary && displaySummary.length) ||
    (strength != null && strength >= 0.72) ||
    tier === "verified" ||
    tier === "chain_backed";

  const showAssumptionChips = (() => {
    if (Boolean(screenshotMode)) return false;
    if (mode !== "card") return false; // Decision cards only (phase 1).
    const p = payload && typeof payload === "object" ? payload : {};
    if (typeof p.__setAssumptionPreset !== "function") return false;
    if (!Array.isArray(reasons) || reasons.length <= 0) return false;
    const normalized = reasons.map((r) => safeStr(r)).filter(Boolean);
    const hasSauce = normalized.some((r) => /^user\s+confirmed\s+sauce-by-default\s+assumption\.\s*$/i.test(r));
    const hasPortion = normalized.some((r) => /^user\s+confirmed\s+portion\s+looked\s+standard\.\s*$/i.test(r));
    return Boolean(hasSauce || hasPortion);
  })();

  const assumptionPreset =
    payload && typeof payload === "object" && payload.__assumptionPreset && typeof payload.__assumptionPreset === "object"
      ? payload.__assumptionPreset
      : {};
  const setAssumptionPreset =
    payload && typeof payload === "object" && typeof payload.__setAssumptionPreset === "function"
      ? payload.__setAssumptionPreset
      : null;

  return (
    <View style={[styles.block, compact && styles.blockCompact, style]}>
      <View style={styles.topRow}>
        <BestOrderTrustBadge tier={tier} dark={dark} compact={compact} />
        {isVerified && verifiedStatus === "verified" && !Boolean(screenshotMode) ? (
          <VerifiedChip compact={compact} />
        ) : null}
        {showSummary ? (
          <BestOrderEvidenceSummary summary={displaySummary} compact={compact} style={styles.summaryInline} />
        ) : null}
      </View>

      {showAssumptionChips ? (
        <View style={styles.assumptionWrap}>
          <Text style={styles.assumptionLabel} numberOfLines={1}>
            Recommended assumptions
          </Text>
          <View style={styles.assumptionRow}>
            {(() => {
              const normalized = Array.isArray(reasons) ? reasons.map((r) => safeStr(r)).filter(Boolean) : [];
              const hasSauce = normalized.some((r) => /^user\s+confirmed\s+sauce-by-default\s+assumption\.\s*$/i.test(r));
              const hasPortion = normalized.some((r) => /^user\s+confirmed\s+portion\s+looked\s+standard\.\s*$/i.test(r));
              const chips = [];
              if (hasSauce) {
                chips.push({
                  key: "assume_sauce_included",
                  label: "Assume sauce included",
                });
              }
              if (hasPortion) {
                chips.push({
                  key: "use_standard_portion",
                  label: "Use standard portion",
                });
              }
              return chips.slice(0, 2).map((chip) => {
                const active = Boolean(assumptionPreset?.[chip.key]);
                return (
                  <TouchableOpacity
                    key={chip.key}
                    style={[styles.assumptionChip, active && styles.assumptionChipActive]}
                    onPress={() => {
                      if (typeof setAssumptionPreset !== "function") return;
                      setAssumptionPreset({ [chip.key]: !active });
                    }}
                    activeOpacity={0.85}
                  >
                    <Text style={[styles.assumptionChipText, active && styles.assumptionChipTextActive]} numberOfLines={1}>
                      {chip.label}
                    </Text>
                  </TouchableOpacity>
                );
              });
            })()}
          </View>
          {(Boolean(assumptionPreset?.assume_sauce_included) || Boolean(assumptionPreset?.use_standard_portion)) ? (
            <Text style={styles.assumptionHelper} numberOfLines={1}>
              Saved for this recommendation
            </Text>
          ) : null}
        </View>
      ) : null}

      <BestOrderProofDrawer
        reasons={reasons}
        citationUrl={url}
        dark={dark}
        compact={compact}
        screenshotMode={screenshotMode}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  block: {
    marginTop: spacing.sm,
  },
  blockCompact: {
    marginTop: spacing.xs,
  },
  topRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
  },
  badge: {
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  badgeCompact: {
    paddingVertical: 3,
    paddingHorizontal: 7,
  },
  badgeText: {
    fontSize: typography.xs,
    fontWeight: "700",
  },
  verifiedChip: {
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "#16a34a",
    backgroundColor: "#052e16",
  },
  verifiedChipCompact: {
    paddingVertical: 3,
    paddingHorizontal: 7,
  },
  verifiedChipText: {
    fontSize: typography.xs,
    fontWeight: "700",
    color: "#86efac",
  },
  summary: {
    fontSize: typography.xs,
    lineHeight: typography.xs * typography.lineHeight.normal,
  },
  summaryCompact: {
    fontSize: 11,
  },
  summaryInline: {
    flexShrink: 1,
  },
  assumptionWrap: {
    marginTop: 6,
  },
  assumptionLabel: {
    fontSize: typography.xs,
    fontWeight: "700",
    color: colors.slate.text,
    marginBottom: 6,
  },
  assumptionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
  },
  assumptionChip: {
    borderWidth: 1,
    borderColor: "#294268",
    backgroundColor: "#0c182c",
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    marginRight: 8,
    marginBottom: 8,
  },
  assumptionChipActive: {
    borderColor: "#22c55e",
    backgroundColor: "#0d2c1a",
  },
  assumptionChipText: {
    fontSize: typography.xs,
    color: "#e5e7eb",
    fontWeight: "700",
  },
  assumptionChipTextActive: {
    color: "#bbf7d0",
  },
  assumptionHelper: {
    fontSize: typography.xs,
    color: colors.slate.text,
    marginTop: 2,
  },
  drawerWrap: {
    marginTop: 6,
  },
  drawerToggle: {
    alignSelf: "flex-start",
    paddingVertical: 2,
    paddingHorizontal: 2,
  },
  drawerToggleText: {
    fontSize: typography.xs,
    fontWeight: "600",
  },
  drawerBody: {
    marginTop: 6,
    padding: 10,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: "#243244",
    backgroundColor: "#0b1220",
  },
  drawerBodyCompact: {
    padding: 9,
  },
  reason: {
    fontSize: typography.xs,
    lineHeight: typography.xs * typography.lineHeight.relaxed,
    marginBottom: 4,
  },
  sourceLinkWrap: {
    marginTop: 6,
    alignSelf: "flex-start",
  },
  sourceLink: {
    fontSize: typography.xs,
    fontWeight: "700",
  },
});

