/**
 * Venue contribution API helper for Healthy Nearby.
 * Uses existing POST /venue-contributions endpoint.
 */

import { Platform } from "react-native";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

function devLog(...args) {
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    // eslint-disable-next-line no-console
    console.log("[VenueContributionApi]", ...args);
  }
}

async function safePost(path, body) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      devLog("non-200", path, res.status);
      return null;
    }
    return await res.json().catch(() => null);
  } catch (e) {
    devLog("network error", path, String(e?.message || e || ""));
    return null;
  }
}

export function buildVenueContributionPayload({
  place,
  userId,
  contributionType,
  suggestedItemText,
  sourceSurface,
  dietContext,
}) {
  const p = place || {};
  const type = String(contributionType || "better_order_suggestion").trim().toLowerCase();
  const placeId = String(p.place_id || p.id || "").trim();
  const placeName = String(p.place_name || p.name || "").trim();
  const areaKey = String(p.area_key || p.normalized_area_key || "").trim().toLowerCase();
  if (!placeName || !areaKey) {
    return null;
  }

  const payload = {
    place_id: placeId,
    place_name: placeName,
    area_key: areaKey,
    contribution_type: type,
    user_id: String(userId || "").trim(),
    payload: {
      source_surface: sourceSurface || "healthy_nearby_map",
      suggested_item_text: String(suggestedItemText || "").trim(),
      current_recommended_item: String(p.best_item_name || p.best_order || "").trim(),
      diet_context: dietContext || null,
      platform: Platform.OS,
    },
  };
  return payload;
}

export async function postVenueContribution(args) {
  const body = buildVenueContributionPayload(args);
  if (!body) return null;
  return safePost("/venue-contributions", body);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    buildVenueContributionPayload,
    postVenueContribution,
  };
}

