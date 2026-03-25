/**
 * Healthy Nearby normalization and wording helpers.
 * Single source of truth for sectioned flattening and recommendation/confidence wording.
 */

/**
 * Normalize /places/healthy response. In sectioned mode, items are derived by
 * flattening sections in order; we never trust response.places as primary ordering.
 *
 * @param {object} response - Raw API response
 * @returns {{ items: object[], sortMode: "flat_score" | "sectioned", sections?: Array<{ name: string, items: object[] }> }}
 */
export function normalizeHealthyPlacesResponse(response) {
  if (!response || typeof response !== "object") {
    return { items: [], sortMode: "flat_score", sections: undefined };
  }
  const sortModeRaw = String(response.sort_mode || "flat_score").trim().toLowerCase();

  if (sortModeRaw === "flat_score") {
    const items = Array.isArray(response.items)
      ? response.items.filter((x) => x && typeof x === "object")
      : [];
    return { items, sortMode: "flat_score" };
  }

  if (sortModeRaw === "sectioned") {
    const sections = Array.isArray(response.sections) ? response.sections : undefined;
    if (sections && sections.length > 0) {
      const items = sections.flatMap((section) =>
        Array.isArray(section?.items) ? section.items.filter((x) => x && typeof x === "object") : []
      );
      return { items, sortMode: "sectioned", sections };
    }
    const fallbackItems = Array.isArray(response.places)
      ? response.places.filter((x) => x && typeof x === "object")
      : [];
    return { items: fallbackItems, sortMode: "sectioned", sections: undefined };
  }

  const items = Array.isArray(response.items)
    ? response.items.filter((x) => x && typeof x === "object")
    : [];
  return { items, sortMode: "flat_score" };
}

/**
 * Item line label for card/panel based on recommendation_label.
 * Keeps "Best pick" / "Strong option" as Recommended, generic as Suggested, needs-check as Possible.
 */
export function getHealthyItemLineLabel(recommendationLabel) {
  const label = String(recommendationLabel || "").trim();
  if (label === "Best pick" || label === "Strong option" || label === "Likely healthy option") {
    return "Recommended";
  }
  if (label === "Suggested healthier pick") {
    return "Suggested option";
  }
  if (label === "Needs menu check") {
    return "Possible option";
  }
  return label || "Option";
}

/**
 * Hero label for card (Best nearby right now, Best fit for your goal, etc.).
 * Strong only when confident; weak fallback uses softer wording.
 * Aligns with mapUtils.getBestNearbyLabel logic.
 */
export function getRecommendationHeroLabel(place, rankPosition) {
  if (!place || typeof place !== "object") return "";
  const isGeneric = Boolean(place.best_item_is_generic_fallback);
  const conf = String(place.confidence_label || "").trim();
  const rec = String(place.recommendation_label || "").trim();
  const needsCheck = conf === "Needs menu check" || rec === "Needs menu check";
  const score = Number(place.display_rank_score_100 ?? place.health_score_100 ?? 0);
  const source = String(place.menu_item_source || place.menu_items_source || "").toLowerCase();
  const strong =
    !isGeneric &&
    !needsCheck &&
    Number.isFinite(score) &&
    score >= 65 &&
    (source === "real_menu" || source === "real menu" || rec === "Best pick" || rec === "Strong option");

  if (rankPosition === 1) {
    if (strong) return "Best nearby right now";
    if (rec === "Best pick" || rec === "Strong option") return "Best fit for your goal";
    if (needsCheck || isGeneric) return "Likely best nearby";
    return "Top pick nearby";
  }
  if (rankPosition === 2) return "#2 nearby";
  if (rankPosition === 3) return "#3 nearby";
  return "";
}

/** Goal Coach preferred modes (align with goalCoachUtils.PREFERRED_MODES). */
const PREFERRED_MODES = {
  PROTEIN_RESCUE: "protein_rescue",
  LIGHTER_OPTION: "lighter_option",
  DINNER_RECOVERY: "dinner_recovery",
  LOGGING_SUPPORT: "logging_support",
  BEST_FIT_TODAY: "best_fit_today",
};

/**
 * Banner text when Healthy Nearby is opened from Goal Coach context.
 * Uses preferred_mode and remaining numbers for concise copy.
 */
export function getGoalCoachBannerText(ctx) {
  if (!ctx || typeof ctx !== "object") return null;
  const mode = String(ctx.preferred_mode || "").trim();
  const protein = ctx.remaining_protein_g != null ? Number(ctx.remaining_protein_g) : null;
  const cal = ctx.remaining_calories != null ? Number(ctx.remaining_calories) : null;
  const proteinOk = Number.isFinite(protein) && protein > 0;
  const calOk = Number.isFinite(cal) && cal > 0;

  if (mode === PREFERRED_MODES.PROTEIN_RESCUE && proteinOk) {
    return `Goal Coach: you still need ~${Math.round(protein)}g protein today${calOk ? ` • ${Math.round(cal)} kcal left` : ""}`;
  }
  if (mode === PREFERRED_MODES.LIGHTER_OPTION) {
    return "Goal Coach: calories are tighter now — lighter protein option recommended";
  }
  if (mode === PREFERRED_MODES.DINNER_RECOVERY && proteinOk) {
    return `Goal Coach: close your protein gap (~${Math.round(protein)}g left)`;
  }
  if (mode === PREFERRED_MODES.LOGGING_SUPPORT) {
    return "Goal Coach: find a place that fits your plan";
  }
  if (proteinOk || calOk) {
    return [
      proteinOk ? `~${Math.round(protein)}g protein left` : "",
      calOk ? `${Math.round(cal)} kcal left` : "",
    ]
      .filter(Boolean)
      .join(" • ") || null;
  }
  return null;
}

/**
 * Hero label for bottom card when opened from Goal Coach (overrides default rank copy).
 */
export function getGoalCoachHeroLabel(preferredMode) {
  const mode = String(preferredMode || "").trim();
  if (mode === PREFERRED_MODES.PROTEIN_RESCUE) return "Best protein-focused next move";
  if (mode === PREFERRED_MODES.LIGHTER_OPTION) return "Lighter option that still helps your target";
  if (mode === PREFERRED_MODES.DINNER_RECOVERY) return "Best protein-focused next move";
  if (mode === PREFERRED_MODES.LOGGING_SUPPORT) return "Best fit for your goal";
  return "Best fit for today";
}

/**
 * Panel item heading for selected place. Avoids strong certainty when
 * confidence is "Needs menu check" or best_item_is_generic_fallback.
 */
export function getHealthyPanelItemHeading(place) {
  const rec = String(place?.recommendation_label || "").trim();
  const conf = String(place?.confidence_label || "").trim();
  const isGeneric = Boolean(place?.best_item_is_generic_fallback);
  const needsCheck = conf === "Needs menu check" || rec === "Needs menu check";
  if (isGeneric) {
    return "Suggested option";
  }
  if (needsCheck) {
    return getHealthyItemLineLabel(rec);
  }
  if (rec === "Best pick" || rec === "Strong option") {
    return "Recommended";
  }
  return getHealthyItemLineLabel(rec);
}

/**
 * Collect swap / skip / add hints from a recommendation card or similar object.
 * Mirrors App.js / RecommendationCard.js logic for consistent copy.
 */
export function extractSwapSuggestions(...sources) {
  const out = [];
  const seen = new Set();

  function pushLine(raw) {
    const text = String(raw || "").trim().replace(/\s+/g, " ");
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  }

  function asSkipLine(raw) {
    const text = String(raw || "").trim();
    if (!text) return "";
    return /^skip\s+/i.test(text) ? text : `Skip ${text}`;
  }

  function asAddLine(raw) {
    const text = String(raw || "").trim();
    if (!text) return "";
    return /^(add|choose|pick|go for)\s+/i.test(text) ? text : `Add ${text}`;
  }

  for (const src of sources) {
    if (!src || typeof src !== "object") continue;
    const swaps = Array.isArray(src?.swap_suggestions) ? src.swap_suggestions : [];
    swaps.forEach((row) => pushLine(row));

    if (Array.isArray(src?.skip_items)) {
      src.skip_items.forEach((row) => pushLine(asSkipLine(row)));
    }
    if (Array.isArray(src?.add_items)) {
      src.add_items.forEach((row) => pushLine(asAddLine(row)));
    }

    pushLine(src?.swap_suggestion);
    pushLine(src?.better_swap);
  }

  return out.slice(0, 3);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    normalizeHealthyPlacesResponse,
    getHealthyItemLineLabel,
    getHealthyPanelItemHeading,
    getRecommendationHeroLabel,
    getGoalCoachBannerText,
    getGoalCoachHeroLabel,
    extractSwapSuggestions,
  };
}
