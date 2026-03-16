/**
 * Helpers for Healthy Nearby request identity and location/context keys.
 * Pure functions so they can be unit-tested easily.
 */

import { haversineKm } from "../mapUtils";

export function buildHealthyNearbyContextKey({
  lat,
  lng,
  radiusM,
  goal,
  cutMode,
  filterKey,
}) {
  const latNum = Number(lat);
  const lngNum = Number(lng);
  if (!Number.isFinite(latNum) || !Number.isFinite(lngNum)) return "";
  const rLat = latNum.toFixed(3); // ~100–150m
  const rLng = lngNum.toFixed(3);
  const rRadius = Math.round(Number(radiusM) || 0);
  const g = String(goal || "").trim().toLowerCase();
  const cut = cutMode ? "1" : "0";
  const f = String(filterKey || "all").trim().toLowerCase();
  return `lat=${rLat}:lng=${rLng}:radius=${rRadius}:goal=${g}:cut=${cut}:filter=${f}`;
}

export function hasMaterialLocationChange(prev, next, thresholdMeters = 200) {
  if (!prev || !next) return true;
  const lat1 = Number(prev.lat);
  const lng1 = Number(prev.lng);
  const lat2 = Number(next.lat);
  const lng2 = Number(next.lng);
  if (
    !Number.isFinite(lat1) ||
    !Number.isFinite(lng1) ||
    !Number.isFinite(lat2) ||
    !Number.isFinite(lng2)
  ) {
    return true;
  }
  const km = haversineKm(lat1, lng1, lat2, lng2);
  if (!Number.isFinite(km) || km === null) return true;
  return km * 1000 >= thresholdMeters;
}

export function shouldApplyHealthyNearbyResponse(requestId, latestId, contextKey, latestKey) {
  return requestId === latestId && contextKey === latestKey;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    buildHealthyNearbyContextKey,
    hasMaterialLocationChange,
    shouldApplyHealthyNearbyResponse,
  };
}

