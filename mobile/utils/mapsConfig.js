import Constants from "expo-constants";

/**
 * Google Maps key for react-native-maps on Android.
 * `android.config.googleMaps.apiKey` is applied at native prebuild but is not always present on
 * `Constants.expoConfig` in release binaries, so we also read `extra` and EXPO_PUBLIC_*.
 */
export function getGoogleMapsApiKey() {
  const ec = Constants.expoConfig;
  const fromExtra = ec?.extra?.GOOGLE_MAPS_API_KEY;
  const fromAndroid = ec?.android?.config?.googleMaps?.apiKey;
  const fromEnv =
    typeof process !== "undefined" && process.env?.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY
      ? process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY
      : "";
  return String(fromExtra || fromAndroid || fromEnv || "").trim();
}

export function hasGoogleMapsKeyForAndroid() {
  return Boolean(getGoogleMapsApiKey());
}
