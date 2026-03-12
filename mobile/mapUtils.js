/**
 * Map utilities: coordinate normalization, visible markers from filtered places.
 */

function num(v) {
  if (v == null || v === "") return NaN;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

/**
 * Extract lat/lng from a place. Handles geometry.location or top-level lat/lng.
 * @param {object} place - Backend place payload
 * @returns {{ lat: number, lng: number } | null}
 */
export function getPlaceCoords(place) {
  if (!place || typeof place !== "object") return null;
  const lat = num(place.lat ?? place.latitude);
  const lng = num(place.lng ?? place.longitude);
  if (Number.isFinite(lat) && Number.isFinite(lng)) return { lat, lng };
  const loc = place.geometry?.location;
  if (loc && typeof loc === "object") {
    const glat = num(loc.lat);
    const glng = num(loc.lng);
    if (Number.isFinite(glat) && Number.isFinite(glng)) return { lat: glat, lng: glng };
  }
  return null;
}

/**
 * Filter places for map visibility by filter key. Matches backend payload fields.
 * @param {object[]} places - Healthy places from API
 * @param {string} filterKey - all | high_protein | under_600 | fits_today | cut_friendly | best_right_now
 * @returns {object[]} Filtered places
 */
export function getVisibleMarkers(places, filterKey) {
  const rows = Array.isArray(places) ? places.filter((p) => p && typeof p === "object") : [];
  const key = String(filterKey || "all").trim().toLowerCase();
  if (key === "all") return rows;
  if (key === "high_protein") return rows.filter((p) => num(p.estimated_protein_g ?? p.best_item_protein) >= 30);
  if (key === "under_600")
    return rows.filter((p) => {
      const cal = num(p.estimated_calories ?? p.best_item_calories);
      return cal > 0 && cal <= 600;
    });
  if (key === "fits_today")
    return rows.filter((p) => p.fit_for_today === true || String(p.decision_today || "").toUpperCase() === "YES");
  if (key === "cut_friendly") return rows.filter((p) => Boolean(p.cut_friendly || p.fat_loss_friendly));
  if (key === "best_right_now") {
    const score100 = (p) => num(p.display_rank_score_100 ?? p.health_score_100 ?? (p.health_score ?? 0) * 10);
    const rank = (p) => num(p.map_rank);
    const scored = rows.filter((p) => (Number.isFinite(rank(p)) && rank(p) <= 5) || score100(p) >= 60);
    return scored.length ? scored : rows.slice(0, 5);
  }
  return rows;
}

/**
 * Check if a place has valid coordinates for map display.
 * @param {object} place
 * @returns {boolean}
 */
export function hasValidCoords(place) {
  const c = getPlaceCoords(place);
  return c != null && Number.isFinite(c.lat) && Number.isFinite(c.lng);
}

/**
 * Top N places from visible list (backend order).
 * @param {object[]} places - Visible places (already filtered)
 * @param {number} limit
 * @returns {object[]}
 */
export function getTopRankedMarkers(places, limit = 3) {
  const rows = Array.isArray(places) ? places : [];
  return rows.slice(0, limit);
}

/**
 * Which place to show selected: current if still visible, else top visible.
 * @param {object[]} visiblePlaces
 * @param {object|null} currentSelectedPlace
 * @param {string} currentSelectedId
 * @param {function} getStableId
 * @returns {{ place: object|null, index: number }}
 */
export function getInitialSelectedPlace(visiblePlaces, currentSelectedPlace, currentSelectedId, getStableId) {
  const rows = Array.isArray(visiblePlaces) ? visiblePlaces : [];
  if (!rows.length) return { place: null, index: -1 };
  const id = String(currentSelectedId || "").trim();
  if (id) {
    const idx = rows.findIndex((p, i) => getStableId(p, i) === id);
    if (idx >= 0) return { place: rows[idx], index: idx };
  }
  return { place: rows[0], index: 0 };
}

/**
 * Whether to use strong "Best nearby" hero language.
 * False for generic fallback, needs menu check, or low confidence.
 */
export function shouldUseStrongBestNearbyLabel(place) {
  if (!place || typeof place !== "object") return false;
  if (place.best_item_is_generic_fallback) return false;
  const conf = String(place.confidence_label || "").trim();
  const rec = String(place.recommendation_label || "").trim();
  if (conf === "Needs menu check" || rec === "Needs menu check") return false;
  const score = num(place.display_rank_score_100 ?? place.health_score_100);
  if (!Number.isFinite(score) || score < 65) return false;
  const source = String(place.menu_item_source || place.menu_items_source || "").toLowerCase();
  if (source === "real_menu" || source === "real menu") return true;
  if (rec === "Best pick" || rec === "Strong option") return true;
  return false;
}

/**
 * Hero label for best-nearby messaging. Strong only when confident.
 * @param {object} place
 * @param {number} rankPosition - 1, 2, 3 or null
 * @returns {string}
 */
export function getBestNearbyLabel(place, rankPosition) {
  if (!place || typeof place !== "object") return "";
  const strong = shouldUseStrongBestNearbyLabel(place);
  const rec = String(place.recommendation_label || "").trim();
  const isGeneric = place.best_item_is_generic_fallback;
  const needsCheck = rec === "Needs menu check" || String(place.confidence_label || "").trim() === "Needs menu check";

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

/**
 * Visual tier for marker: 1 = best, 2 = #2, 3 = #3, 0 = normal.
 * @param {object} place
 * @param {object[]} visiblePlaces
 * @param {function} getStableId
 * @returns {number}
 */
export function getMarkerVisualTier(place, visiblePlaces, getStableId) {
  const rows = Array.isArray(visiblePlaces) ? visiblePlaces : [];
  if (!rows.length || !place || !getStableId) return 0;
  const idx = rows.findIndex((p, i) => getStableId(p, i) === getStableId(place, 0));
  if (idx < 0) return 0;
  if (idx === 0) return 1;
  if (idx === 1) return 2;
  if (idx === 2) return 3;
  return 0;
}
