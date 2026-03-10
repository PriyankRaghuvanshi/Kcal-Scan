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

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    normalizeHealthyPlacesResponse,
    getHealthyItemLineLabel,
    getHealthyPanelItemHeading,
  };
}
