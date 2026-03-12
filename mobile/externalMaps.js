/**
 * Open place in external maps (Apple Maps, Google Maps).
 * Uses platform-specific URLs for directions and place search.
 */

import { Platform, Linking, Alert } from "react-native";

function num(v) {
  if (v == null || v === "") return NaN;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

function getCoords(place) {
  if (!place || typeof place !== "object") return null;
  const lat = num(place.lat ?? place.latitude ?? place.place_lat);
  const lng = num(place.lng ?? place.longitude ?? place.place_lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat, lng };
}

function getName(place) {
  if (!place) return "";
  return String(place.place_name ?? place.name ?? "").trim() || "Restaurant";
}

/**
 * Open directions to a place. Uses Apple Maps on iOS, Google Maps on Android.
 * @param {object} place - Place with lat/lng and name
 */
export async function openDirections(place) {
  const coords = getCoords(place);
  if (!coords) {
    Alert.alert("Directions unavailable", "Location not found for this place.");
    return;
  }
  const name = encodeURIComponent(getName(place));
  let url;
  if (Platform.OS === "ios") {
    url = `maps://maps.apple.com/?daddr=${coords.lat},${coords.lng}&dirflg=d`;
  } else {
    url = `https://www.google.com/maps/dir/?api=1&destination=${coords.lat},${coords.lng}`;
  }
  try {
    const supported = await Linking.canOpenURL(url);
    if (supported) {
      await Linking.openURL(url);
    } else {
      await Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${coords.lat},${coords.lng}`);
    }
  } catch (e) {
    Alert.alert("Map unavailable", String((e && e.message) || e || "").slice(0, 160));
  }
}

/**
 * Open place in external map app (search by name + coords).
 * @param {object} place - Place with lat/lng and name
 */
export async function openPlaceInMaps(place) {
  const coords = getCoords(place);
  if (!coords) {
    Alert.alert("Map unavailable", "Location not found for this place.");
    return;
  }
  const name = encodeURIComponent(getName(place));
  let url;
  if (Platform.OS === "ios") {
    url = `maps://maps.apple.com/?q=${name}&ll=${coords.lat},${coords.lng}`;
  } else {
    url = `https://www.google.com/maps/search/?api=1&query=${coords.lat},${coords.lng}`;
  }
  try {
    const supported = await Linking.canOpenURL(url);
    if (supported) {
      await Linking.openURL(url);
    } else {
      await Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${coords.lat},${coords.lng}`);
    }
  } catch (e) {
    Alert.alert("Map unavailable", String((e && e.message) || e || "").slice(0, 160));
  }
}

/**
 * Build Google Maps URL for fallback (e.g. when maps:// fails).
 */
export function buildGoogleMapsDirectionsUrl(lat, lng) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}
