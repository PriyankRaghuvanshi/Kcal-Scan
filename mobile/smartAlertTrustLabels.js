/**
 * Smart Alert Trust Labels – Single source of truth for recommendation trust mapping.
 * Maps backend/source signals to user-facing labels. Used by SmartAlertCard, inbox,
 * ConfidenceBadge, and push-open flows. Do NOT expose raw internal terms to users.
 */

/** User-facing trust labels */
export const TRUST_LABELS = {
  verified: "Verified",
  chain_backed: "Chain-backed",
  local_favorite: "Local favorite",
  estimated: "Estimated",
  needs_menu_check: "Needs menu check",
};

/** Trust tones for visual hierarchy: strong / medium / weak */
export const TRUST_TONES = {
  strong: "strong",
  medium: "medium",
  weak: "weak",
};

/**
 * Map backend signals to user-facing trust label.
 * @param {object} alertOrPlace – Alert candidate or place with confidence_label, menu_item_source,
 *   chosen_candidate_specificity_tier, matched_local_profile, local_profile_source,
 *   used_venue_intelligence_cache, best_item_is_generic_fallback
 * @returns {string} One of: Verified | Chain-backed | Local favorite | Estimated | Needs menu check
 */
export function getAlertTrustLabel(alertOrPlace) {
  if (!alertOrPlace || typeof alertOrPlace !== "object") {
    return TRUST_LABELS.needs_menu_check;
  }

  const conf = String(alertOrPlace.confidence_label || "").trim();
  const rec = String(alertOrPlace.recommendation_label || "").trim();
  const source = String(alertOrPlace.menu_item_source || alertOrPlace.best_item_source || "")
    .trim()
    .toLowerCase();
  const tier = String(alertOrPlace.chosen_candidate_specificity_tier || "")
    .trim()
    .toLowerCase();
  const matchedLocal = Boolean(
    alertOrPlace.matched_local_profile || alertOrPlace._matched_local_profile
  );
  const localProfileSource = String(
    alertOrPlace.local_profile_source || alertOrPlace._local_profile_source || ""
  )
    .trim()
    .toLowerCase();
  const usedCache = Boolean(
    alertOrPlace.used_venue_intelligence_cache || alertOrPlace._used_venue_intelligence_cache
  );
  const isGeneric = Boolean(alertOrPlace.best_item_is_generic_fallback);

  // Item-level provenance gate: if backend provides item_provenance, use it as
  // the primary trust signal.  This prevents covered chains from showing
  // Verified / Chain-backed when the displayed item is actually a fallback.
  const provenance = String(alertOrPlace.item_provenance || "").trim().toLowerCase();
  const coveredChainNeutral = Boolean(alertOrPlace.covered_chain_neutral);

  // When item_provenance is present, prefer it over legacy heuristic signals.
  // This prevents covered chains from showing Chain-backed when the item is a suggestion.
  if (provenance === "exact_chain_menu") return TRUST_LABELS.chain_backed;
  if (provenance === "exact_menu") return TRUST_LABELS.verified;
  if (provenance === "heuristic_suggestion") return TRUST_LABELS.estimated;
  if (provenance === "generic_fallback" || provenance === "none") return TRUST_LABELS.needs_menu_check;

  // E. Needs menu check – weak/generic fallback or low-confidence
  if (isGeneric) return TRUST_LABELS.needs_menu_check;
  if (conf === "Needs menu check" || rec === "Needs menu check") return TRUST_LABELS.needs_menu_check;
  if (tier === "generic_fallback") return TRUST_LABELS.needs_menu_check;
  if (tier === "heuristic_cuisine_match_weak") return TRUST_LABELS.needs_menu_check;

  // A. Verified – exact/cache or very strong trusted source.
  // `official_published` = item came from the brand's own published
  // nutrition data (McDonald's, Chipotle, etc.) — highest-trust tier.
  if (conf === "Verified") return TRUST_LABELS.verified;
  if (
    source &&
    [
      "real_menu",
      "user_scan",
      "exact_menu_cache",
      "menu_intelligence_store",
      "structured_menu",
      "official_published",
    ].includes(source)
  ) {
    return TRUST_LABELS.verified;
  }
  if (tier === "exact_menu_match" && (usedCache || source === "exact_menu_cache")) {
    return TRUST_LABELS.verified;
  }

  // B. Chain-backed – ingested chain item or strong chain registry
  if (conf === "Chain-backed") return TRUST_LABELS.chain_backed;
  if (
    source &&
    ["ingested_chain_item", "chain_registry"].includes(source)
  ) {
    return TRUST_LABELS.chain_backed;
  }
  if (tier === "chain_registry") return TRUST_LABELS.chain_backed;

  // C. Local favorite – enriched/confirmed local venue profile
  if (matchedLocal && localProfileSource) return TRUST_LABELS.local_favorite;
  if (
    source &&
    ["enriched_local_profile", "local_venue_profile", "exact_local_profile"].includes(source)
  ) {
    return TRUST_LABELS.local_favorite;
  }
  if (
    tier &&
    ["enriched_local_profile", "exact_local_profile"].includes(tier)
  ) {
    return TRUST_LABELS.local_favorite;
  }

  // D. Estimated – strong heuristic / reasonable inference.
  // `llm_curated` = brand-knowledge-grounded dish authored for thin chains
  // (e.g. Barista, Goli Vada Pav, Keventers) with 0.78-0.85 confidence.
  // `seed_estimated` / `seed_template` = original scaffolded seed data.
  if (conf === "Estimated") return TRUST_LABELS.estimated;
  if (rec === "Best pick" || rec === "Strong option") return TRUST_LABELS.estimated;
  if (tier === "heuristic_cuisine_match_strong" || tier === "menu_inferred") {
    return TRUST_LABELS.estimated;
  }
  if (
    source &&
    ["llm_inferred", "llm_curated", "seed_estimated", "seed_template"].includes(source)
  ) {
    return TRUST_LABELS.estimated;
  }

  // Default for unknown/heuristic
  return TRUST_LABELS.estimated;
}

/**
 * Get trust tone for visual styling: strong / medium / weak.
 * @param {object} alertOrPlace
 * @returns {string}
 */
export function getAlertTrustTone(alertOrPlace) {
  const label = getAlertTrustLabel(alertOrPlace);
  if (
    label === TRUST_LABELS.verified ||
    label === TRUST_LABELS.chain_backed ||
    label === TRUST_LABELS.local_favorite
  ) {
    return TRUST_TONES.strong;
  }
  if (label === TRUST_LABELS.estimated) return TRUST_TONES.medium;
  return TRUST_TONES.weak;
}

/**
 * Whether to show "Menu may vary" or similar caution note.
 * @param {object} alertOrPlace
 * @returns {boolean}
 */
export function shouldShowMenuMayVary(alertOrPlace) {
  const label = getAlertTrustLabel(alertOrPlace);
  return label === TRUST_LABELS.needs_menu_check;
}

/**
 * Optional short specificity cue (e.g. "From nearby venue data").
 * Only for weaker alerts; null for strong ones.
 * @param {object} alertOrPlace
 * @returns {string|null}
 */
export function getAlertSpecificityCue(alertOrPlace) {
  const label = getAlertTrustLabel(alertOrPlace);
  if (label === TRUST_LABELS.needs_menu_check) {
    return "Estimated from nearby venue data";
  }
  if (label === TRUST_LABELS.estimated) {
    return null; // Don't clutter; "Menu may vary" is enough when shown
  }
  return null;
}

/**
 * Trust-aware effective title for alert cards.
 * Weak alerts must not use strong titles like "Best nearby fit right now".
 * @param {object} candidate – Alert candidate with title, body
 * @returns {string} Title to display (possibly softened for weak trust)
 */
export function getEffectiveAlertTitle(candidate) {
  if (!candidate || typeof candidate !== "object") return "Nearby option";
  const title = String(candidate.title || "").trim();
  const label = getAlertTrustLabel(candidate);
  if (label !== TRUST_LABELS.needs_menu_check) return title || "Nearby option";
  const strongTitles = [
    "best nearby fit right now",
    "best nearby right now",
    "best fit for your goal",
  ];
  const lower = title.toLowerCase();
  if (strongTitles.some((t) => lower.includes(t))) {
    return "Suggested nearby option";
  }
  return title || "Nearby option";
}

/**
 * Trust-aware hero language for alert cards.
 * Strong: "Best nearby right now", "Best fit for your goal"
 * Moderate: "Good nearby option", "Likely best nearby"
 * Weak: "Suggested nearby option", "Check menu before ordering"
 * @param {object} alertOrPlace
 * @param {number} [rankPosition] – 1, 2, 3 for rank-specific wording
 * @returns {string}
 */
export function getAlertHeroLabel(alertOrPlace, rankPosition = 1) {
  const tone = getAlertTrustTone(alertOrPlace);
  const label = getAlertTrustLabel(alertOrPlace);

  if (rankPosition === 2) return "#2 nearby";
  if (rankPosition === 3) return "#3 nearby";

  if (tone === TRUST_TONES.strong) {
    return "Best nearby right now";
  }
  if (tone === TRUST_TONES.medium) {
    return "Good nearby option";
  }
  if (label === TRUST_LABELS.needs_menu_check) {
    return "Check menu before ordering";
  }
  return "Suggested nearby option";
}

/**
 * Infer confidence tier for ConfidenceBadge styling.
 * Mirrors getAlertTrustLabel but returns tier key for badge styles.
 * @param {object} alertOrPlace
 * @returns {string} verified | chain_backed | local_favorite | estimated | needs_menu_check
 */
export function getTrustTierForBadge(alertOrPlace) {
  const label = getAlertTrustLabel(alertOrPlace);
  const map = {
    [TRUST_LABELS.verified]: "verified",
    [TRUST_LABELS.chain_backed]: "chain_backed",
    [TRUST_LABELS.local_favorite]: "local_favorite",
    [TRUST_LABELS.estimated]: "estimated",
    [TRUST_LABELS.needs_menu_check]: "needs_menu_check",
  };
  return map[label] || "needs_menu_check";
}
