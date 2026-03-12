/**
 * Deep-link router for Smart Food Alerts.
 * Parses push payload and resolves navigation targets.
 * Push tap → exact recommendation/place detail when possible.
 */

const DEEP_LINK_SCHEME = "calorieclick";
const ROUTE_SMART_ALERT_PLACE = "smart_alert_place";
const ROUTE_SMART_ALERT_INBOX = "smart_alert_inbox";

/**
 * Parse Smart Alert deep-link or push data payload.
 * Includes trust metadata for consistent label display when opening from push.
 * @param {string|object} urlOrData - URL string (calorieclick://...) or push data object
 * @returns {{ alert_id: string, place_id: string, place_name: string, best_item_name: string, place_lat: number|null, place_lng: number|null, route_target: string, display_rank_score_100: number|null, context_mode: string, confidence_label?: string, recommendation_label?: string, chosen_candidate_specificity_tier?: string, menu_item_source?: string, matched_local_profile?: boolean, local_profile_source?: string, used_venue_intelligence_cache?: boolean, best_item_is_generic_fallback?: boolean }}
 */
export function parseSmartAlertDeepLink(urlOrData) {
  const empty = {
    alert_id: "",
    place_id: "",
    place_name: "",
    best_item_name: "",
    place_lat: null,
    place_lng: null,
    route_target: ROUTE_SMART_ALERT_INBOX,
    display_rank_score_100: null,
    context_mode: "",
  };

  if (!urlOrData) return empty;

  if (typeof urlOrData === "object") {
    const d = urlOrData;
    const out = {
      alert_id: String(d.alert_id || "").trim(),
      place_id: String(d.place_id || "").trim(),
      place_name: String(d.place_name || "").trim(),
      best_item_name: String(d.best_item_name || "").trim(),
      place_lat: typeof d.place_lat === "number" ? d.place_lat : null,
      place_lng: typeof d.place_lng === "number" ? d.place_lng : null,
      route_target: String(d.route_target || ROUTE_SMART_ALERT_INBOX).trim() || ROUTE_SMART_ALERT_INBOX,
      display_rank_score_100: typeof d.display_rank_score_100 === "number" ? d.display_rank_score_100 : null,
      context_mode: String(d.context_mode || "").trim(),
    };
    if (d.confidence_label) out.confidence_label = String(d.confidence_label).trim();
    if (d.recommendation_label) out.recommendation_label = String(d.recommendation_label).trim();
    if (d.chosen_candidate_specificity_tier) out.chosen_candidate_specificity_tier = String(d.chosen_candidate_specificity_tier).trim();
    if (d.menu_item_source) out.menu_item_source = String(d.menu_item_source).trim();
    if (d.matched_local_profile === true) out.matched_local_profile = true;
    if (d.local_profile_source) out.local_profile_source = String(d.local_profile_source).trim();
    if (d.used_venue_intelligence_cache === true) out.used_venue_intelligence_cache = true;
    if (d.best_item_is_generic_fallback === true) out.best_item_is_generic_fallback = true;
    if (d.alert_type) out.alert_type = String(d.alert_type).trim();
    return out;
  }

  const url = String(urlOrData || "").trim();
  if (!url || !url.includes("smart-alert")) return empty;

  try {
    const parsed = new URL(url);
    if (parsed.protocol?.replace(":", "") !== DEEP_LINK_SCHEME) return empty;
    const params = Object.fromEntries(parsed.searchParams.entries());
    return {
      alert_id: String(params.alert_id || "").trim(),
      place_id: String(params.place_id || "").trim(),
      place_name: String(params.place_name || "").trim(),
      best_item_name: String(params.best_item_name || "").trim(),
      place_lat: params.place_lat ? parseFloat(params.place_lat) : null,
      place_lng: params.place_lng ? parseFloat(params.place_lng) : null,
      route_target: String(params.route_target || ROUTE_SMART_ALERT_INBOX).trim() || ROUTE_SMART_ALERT_INBOX,
      display_rank_score_100: params.display_rank_score_100 ? parseFloat(params.display_rank_score_100) : null,
      context_mode: String(params.context_mode || "").trim(),
    };
  } catch {
    return empty;
  }
}

/**
 * Resolve navigation target from parsed deep-link payload.
 * @param {object} parsed - From parseSmartAlertDeepLink
 * @returns {{ action: 'open_place'|'open_inbox'|'open_nearby', place_id: string|null, place_lat: number|null, place_lng: number|null, place_name: string, best_item_name: string, alert_id: string }}
 */
export function resolveSmartAlertNavigationTarget(parsed) {
  const p = parsed || {};
  const placeId = String(p.place_id || "").trim();
  const placeLat = p.place_lat;
  const placeLng = p.place_lng;
  const hasCoords = typeof placeLat === "number" && typeof placeLng === "number" && Number.isFinite(placeLat) && Number.isFinite(placeLng);

  if (placeId && hasCoords) {
    return {
      action: "open_place",
      place_id: placeId,
      place_lat: placeLat,
      place_lng: placeLng,
      place_name: String(p.place_name || "").trim(),
      best_item_name: String(p.best_item_name || "").trim(),
      alert_id: String(p.alert_id || "").trim(),
    };
  }

  if (placeId) {
    return {
      action: "open_inbox",
      place_id: placeId,
      place_lat: null,
      place_lng: null,
      place_name: String(p.place_name || "").trim(),
      best_item_name: String(p.best_item_name || "").trim(),
      alert_id: String(p.alert_id || "").trim(),
    };
  }

  return {
    action: "open_nearby",
    place_id: null,
    place_lat: null,
    place_lng: null,
    place_name: "",
    best_item_name: "",
    alert_id: String(p.alert_id || "").trim(),
  };
}
