import Constants from "expo-constants";

/**
 * Android Google Maps native SDK reads the key from the app manifest (Expo:
 * app.json android.config.googleMaps.apiKey or extra.GOOGLE_MAPS_API_KEY).
 * Only mount MapView when this is non-empty so missing config does not crash.
 */
export function getGoogleMapsApiKeyFromExpoConfig() {
  const fromAndroid = String(Constants.expoConfig?.android?.config?.googleMaps?.apiKey || "").trim();
  const fromExtra = String(Constants.expoConfig?.extra?.GOOGLE_MAPS_API_KEY || "").trim();
  return fromAndroid || fromExtra;
}

export function hasGoogleMapsKeyForNativeMap() {
  return Boolean(getGoogleMapsApiKeyFromExpoConfig());
}
