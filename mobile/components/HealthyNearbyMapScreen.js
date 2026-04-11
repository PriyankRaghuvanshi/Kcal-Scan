/**
 * Healthy Nearby map screen: real MapView with markers, filters, bottom card.
 * Engaging store-locator style (like McDonald's / Hungry Jack's): numbered pins,
 * "X places nearby" header, place strip, bottom sheet card, recenter FAB.
 */

import React, { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  ScrollView,
} from "react-native";
import { hasGoogleMapsKeyForAndroid } from "../utils/mapsConfig";

let MapView = null;
let Marker = null;
try {
  const Maps = require("react-native-maps");
  MapView = Maps.default;
  Marker = Maps.Marker;
} catch (_) {}
import { HealthyMapFilters } from "./HealthyMapFilters";
import { HealthyPlaceBottomCard } from "./HealthyPlaceBottomCard";
import { getPlaceCoords } from "../mapUtils";
import { getGoalCoachBannerText, getGoalCoachHeroLabel } from "../healthyNearbyUtils";
import { colors, spacing, radius, typography, shadows } from "../designTokens";

const DEFAULT_REGION = {
  latitude: 37.7749,
  longitude: -122.4194,
  latitudeDelta: 0.04,
  longitudeDelta: 0.04,
};

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Numbered marker for top 3 (store-locator style). */
function NumberedMarker({ number, isSelected, tierColor }) {
  return (
    <View
      style={[
        markerStyles.bubble,
        { backgroundColor: isSelected ? colors.success.primary : tierColor },
      ]}
    >
      <Text style={markerStyles.bubbleText}>{number}</Text>
    </View>
  );
}

const markerStyles = StyleSheet.create({
  bubble: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#fff",
    ...shadows.sm,
  },
  bubbleText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "800",
  },
});

export function HealthyNearbyMapScreen({
  places = [],
  filterKey = "all",
  onFilterChange,
  selectedPlace,
  onSelectPlace,
  userCoords,
  focusCoords,
  onLoadPlaces,
  onRefreshAroundMe,
  onSearchWider,
  busy = false,
  error = "",
  formatDistanceFromMeters,
  getPlaceStableId,
  onScanMenu,
  onOpenDirections,
  goalCoachContext = null,
}) {
  const mapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const initialCenterDone = useRef(false);
  const useSafeAndroidMap = Platform.OS === "android";

  const markersWithCoords = (Array.isArray(places) ? places : [])
    .map((place, idx) => ({ place, idx, coords: getPlaceCoords(place) }))
    .filter((x) => x.coords != null);

  const selectedStableId = selectedPlace && getPlaceStableId
    ? getPlaceStableId(selectedPlace, 0)
    : null;

  // Initial load: fetch places if empty
  useEffect(() => {
    if (onLoadPlaces && !busy && Array.isArray(places) && places.length === 0 && userCoords) {
      onLoadPlaces();
    }
  }, [onLoadPlaces, busy, places?.length, userCoords]);

  // Center map on focus (best place) or user or first marker, once on initial ready
  useEffect(() => {
    if (!mapRef.current || !mapReady || initialCenterDone.current) return;
    const coords = focusCoords || userCoords || (markersWithCoords[0]?.coords);
    if (coords && Number.isFinite(coords.lat) && Number.isFinite(coords.lng)) {
      initialCenterDone.current = true;
      mapRef.current.animateToRegion({
        latitude: coords.lat,
        longitude: coords.lng,
        latitudeDelta: 0.03,
        longitudeDelta: 0.03,
      });
    }
  }, [mapReady, focusCoords, userCoords, markersWithCoords.length]);

  // When user selects a place, animate map to that marker (store-locator feel)
  const selectedCoordsRef = useRef(null);
  useEffect(() => {
    if (!mapRef.current || !mapReady || !selectedPlace) return;
    const idx = (places || []).findIndex((p, i) =>
      getPlaceStableId && getPlaceStableId(p, i) === selectedStableId
    );
    const item = idx >= 0 ? markersWithCoords.find((m) => m.idx === idx) : null;
    const coords = item?.coords || getPlaceCoords(selectedPlace);
    if (coords && Number.isFinite(coords.lat) && Number.isFinite(coords.lng)) {
      selectedCoordsRef.current = coords;
      mapRef.current.animateToRegion({
        latitude: coords.lat,
        longitude: coords.lng,
        latitudeDelta: 0.012,
        longitudeDelta: 0.012,
      });
    }
  }, [selectedPlace, selectedStableId, mapReady, places, markersWithCoords]);

  const region = (() => {
    const c = focusCoords || userCoords || (markersWithCoords[0]?.coords);
    if (c && Number.isFinite(c.lat) && Number.isFinite(c.lng)) {
      return {
        latitude: c.lat,
        longitude: c.lng,
        latitudeDelta: 0.035,
        longitudeDelta: 0.035,
      };
    }
    return DEFAULT_REGION;
  })();

  const handleMarkerPress = (place, idx) => {
    if (onSelectPlace && place) {
      onSelectPlace(place, idx);
    }
  };

  const ctx = goalCoachContext && typeof goalCoachContext === "object" ? goalCoachContext : null;
  const bannerText = ctx ? getGoalCoachBannerText(ctx) : null;
  const heroLabelOverride = ctx?.preferred_mode ? getGoalCoachHeroLabel(ctx.preferred_mode) : null;

  const handleRecenter = () => {
    if (!mapRef.current || !userCoords || !Number.isFinite(userCoords.lat)) return;
    mapRef.current.animateToRegion({
      latitude: userCoords.lat,
      longitude: userCoords.lng,
      latitudeDelta: 0.03,
      longitudeDelta: 0.03,
    });
  };

  const placeCount = markersWithCoords.length;

  const canRenderMap = MapView && Marker && (Platform.OS === "ios" || hasGoogleMapsKeyForAndroid());

  return (
    <View style={styles.container}>
      {bannerText ? (
        <View style={styles.goalCoachBanner}>
          <Text style={styles.goalCoachBannerText} numberOfLines={2}>
            {bannerText}
          </Text>
        </View>
      ) : null}

      {/* Header: "X places nearby" – store-locator style */}
      <View style={styles.headerBar}>
        <Text style={styles.headerTitle}>
          {placeCount > 0
            ? `${placeCount} place${placeCount !== 1 ? "s" : ""} nearby`
            : "Places nearby"}
        </Text>
        <Text style={styles.headerSubtitle}>
          {placeCount > 0 ? "Tap a place or pick from the list below" : "Finding restaurants near you…"}
        </Text>
      </View>

      <View style={styles.mapWrap}>
        {canRenderMap ? (
        <MapView
          ref={mapRef}
          style={styles.map}
          initialRegion={region}
          showsUserLocation={!!userCoords}
          showsMyLocationButton={!!userCoords}
          mapType={Platform.OS === "ios" ? "mutedStandard" : "standard"}
          moveOnMarkerPress={false}
          toolbarEnabled={false}
          rotateEnabled={!useSafeAndroidMap}
          onMapReady={() => setMapReady(true)}
        >
          {mapReady && markersWithCoords.map(({ place, idx, coords }) => {
            const stableId = getPlaceStableId ? getPlaceStableId(place, idx) : null;
            const isSelected = Boolean(selectedStableId && stableId === selectedStableId);
            const tier = idx === 0 ? 1 : idx === 1 ? 2 : idx === 2 ? 3 : 0;
            const tierColor =
              tier === 1 ? colors.success.primary
              : tier === 2 ? colors.success.muted
              : tier === 3 ? colors.success.border
              : colors.slate.primary;
            const useNumberedPin = !useSafeAndroidMap && tier >= 1 && tier <= 3;

            return (
              <Marker
                key={stableId || `m-${idx}`}
                coordinate={{ latitude: coords.lat, longitude: coords.lng }}
                onPress={() => handleMarkerPress(place, idx)}
                tracksViewChanges={false}
                title={String(place?.place_name ?? place?.name ?? "Place").slice(0, 40)}
                {...(useNumberedPin
                  ? {}
                  : {
                      pinColor: isSelected ? colors.success.primary : tierColor,
                      opacity: isSelected ? 1 : 0.9,
                    })}
              >
                {useNumberedPin ? (
                  <NumberedMarker
                    number={tier}
                    isSelected={isSelected}
                    tierColor={tierColor}
                  />
                ) : null}
              </Marker>
            );
          })}
        </MapView>
        ) : (
        <View style={styles.mapFallback}>
          <Text style={styles.mapFallbackTitle}>Map unavailable</Text>
          <Text style={styles.mapFallbackBody}>
            {Platform.OS === "android"
              ? "Google Maps API key is not configured for this build. Places are listed below."
              : "Map component could not load. Places are listed below."}
          </Text>
        </View>
        )}

        {/* Filter chips – horizontal scroll */}
        <View style={styles.filtersOverlay}>
          <HealthyMapFilters activeKey={filterKey} onSelect={onFilterChange} />
        </View>

        {/* Recenter FAB */}
        {userCoords && Number.isFinite(userCoords.lat) && (
          <TouchableOpacity
            style={styles.recenterFab}
            onPress={handleRecenter}
            activeOpacity={0.85}
          >
            <Text style={styles.recenterFabIcon}>◎</Text>
            <Text style={styles.recenterFabLabel}>Me</Text>
          </TouchableOpacity>
        )}

        {/* Refresh around me: re-fetch nearby places using latest GPS */}
        {onRefreshAroundMe && (
          <TouchableOpacity
            style={styles.refreshFab}
            onPress={onRefreshAroundMe}
            activeOpacity={0.85}
            disabled={busy}
          >
            <Text style={styles.refreshFabIcon}>⟳</Text>
            <Text style={styles.refreshFabLabel}>{busy ? "Refreshing…" : "Refresh"}</Text>
          </TouchableOpacity>
        )}

        {/* Loading overlay */}
        {busy && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="small" color={colors.success.primary} />
            <Text style={styles.loadingText}>Loading nearby places…</Text>
          </View>
        )}

        {/* Error overlay */}
        {error ? (
          <View style={styles.errorOverlay}>
            <Text style={styles.errorText}>{error}</Text>
            {onLoadPlaces ? (
              <TouchableOpacity
                style={styles.retryBtn}
                onPress={() => onLoadPlaces()}
                disabled={busy}
              >
                <Text style={styles.retryBtnText}>Retry</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}

        {useSafeAndroidMap ? (
          <View pointerEvents="none" style={styles.androidMapHint}>
            <Text style={styles.androidMapHintText}>Android map mode uses a lighter preview for stability.</Text>
          </View>
        ) : null}
      </View>

      {/* Place strip: tap to select (like McDonald's store list) */}
      {placeCount > 0 && (
        <View style={styles.placeStripWrap}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.placeStripContent}
          >
            {markersWithCoords.slice(0, 12).map(({ place, idx }, i) => {
              const stableId = getPlaceStableId ? getPlaceStableId(place, idx) : null;
              const isSelected = Boolean(selectedStableId && stableId === selectedStableId);
              const name = String(place?.place_name ?? place?.name ?? "Place").trim() || "Place";
              const dist = place?.distance_meters != null && formatDistanceFromMeters
                ? formatDistanceFromMeters(place.distance_meters)
                : null;
              const rank = idx < 3 ? idx + 1 : null;
              return (
                <TouchableOpacity
                  key={stableId || `strip-${idx}`}
                  style={[styles.placePill, isSelected && styles.placePillSelected]}
                  onPress={() => handleMarkerPress(place, idx)}
                  activeOpacity={0.8}
                >
                  {rank != null && (
                    <View style={styles.placePillRank}>
                      <Text style={styles.placePillRankText}>{rank}</Text>
                    </View>
                  )}
                  <Text style={[styles.placePillName, isSelected && styles.placePillNameSelected]} numberOfLines={1}>
                    {name}
                  </Text>
                  {dist ? (
                    <Text style={styles.placePillDist} numberOfLines={1}>{dist}</Text>
                  ) : null}
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      )}

      {/* Bottom card: sheet style with handle */}
      <View style={styles.bottomCard}>
        <View style={styles.sheetHandleWrap}>
          <View style={styles.sheetHandle} />
        </View>
        {selectedPlace ? (
          <HealthyPlaceBottomCard
            place={selectedPlace}
            rankPosition={
              (() => {
                const idx = (places || []).findIndex((p, i) =>
                  getPlaceStableId && getPlaceStableId(p, i) === selectedStableId
                );
                return idx >= 0 && idx < 3 ? idx + 1 : null;
              })()
            }
            heroLabelOverride={heroLabelOverride}
            onDirections={onOpenDirections}
            onScanMenu={onScanMenu}
          />
        ) : (
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>
              {markersWithCoords.length > 0
                ? "Tap a place to compare options"
                : filterKey === "all"
                ? "No nearby places found yet"
                : "No nearby places match this filter"}
            </Text>
            <Text style={styles.emptyHint}>
              {markersWithCoords.length > 0
                ? `${markersWithCoords.length} nearby places on the map`
                : filterKey !== "all"
                ? "Try All to see more"
                : "Try a wider search"}
            </Text>
            {markersWithCoords.length === 0 && filterKey !== "all" ? (
              <TouchableOpacity
                style={styles.searchWiderBtn}
                onPress={() => onFilterChange && onFilterChange("all")}
                activeOpacity={0.8}
              >
                <Text style={styles.searchWiderBtnText}>Show all nearby places</Text>
              </TouchableOpacity>
            ) : onSearchWider && markersWithCoords.length === 0 && filterKey === "all" ? (
              <TouchableOpacity
                style={styles.searchWiderBtn}
                onPress={onSearchWider}
                disabled={busy}
              >
                <Text style={styles.searchWiderBtnText}>
                  {busy ? "Searching…" : "Search wider area (8 km)"}
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff8eb",
  },
  goalCoachBanner: {
    backgroundColor: "#fff3cd",
    borderBottomWidth: 1,
    borderBottomColor: "#f7b500",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
  },
  goalCoachBannerText: {
    fontSize: typography.sm,
    color: "#92400e",
    fontWeight: typography.weight.semibold,
  },
  mapWrap: {
    flex: 1,
    position: "relative",
  },
  map: {
    width: "100%",
    height: "100%",
  },
  filtersOverlay: {
    position: "absolute",
    top: 8,
    left: 8,
    right: 8,
    paddingVertical: 6,
  },
  loadingOverlay: {
    position: "absolute",
    top: 60,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md,
    padding: spacing.base,
    backgroundColor: "rgba(17,24,39,0.78)",
    borderRadius: radius.lg,
  },
  loadingText: {
    color: colors.accent.muted,
    fontSize: typography.base,
  },
  errorOverlay: {
    position: "absolute",
    top: 60,
    left: spacing.lg,
    right: spacing.lg,
    padding: spacing.base,
    backgroundColor: "rgba(120,20,20,0.9)",
    borderRadius: radius.lg,
  },
  errorText: {
    color: colors.warning.text,
    fontSize: typography.base,
  },
  androidMapHint: {
    position: "absolute",
    left: spacing.sm,
    right: spacing.sm,
    bottom: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: "rgba(15, 23, 42, 0.7)",
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  androidMapHintText: {
    color: "#fff",
    fontSize: typography.xs,
    fontWeight: typography.weight.medium,
    textAlign: "center",
  },
  retryBtn: {
    marginTop: 8,
    paddingVertical: 6,
    alignSelf: "flex-start",
  },
  retryBtnText: {
    color: colors.amber.text,
    fontSize: typography.base,
    fontWeight: typography.weight.semibold,
  },
  headerBar: {
    backgroundColor: "#ffffff",
    borderBottomWidth: 1,
    borderBottomColor: "#f7b500",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  headerTitle: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
    color: "#111827",
  },
  headerSubtitle: {
    fontSize: typography.sm,
    color: "#6b7280",
    marginTop: 2,
  },
  recenterFab: {
    position: "absolute",
    bottom: 24,
    right: 16,
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "#ffbc0d",
    borderWidth: 1,
    borderColor: "#e0a800",
    alignItems: "center",
    justifyContent: "center",
    ...shadows.md,
  },
  recenterFabIcon: {
    fontSize: 18,
    color: "#111827",
  },
  recenterFabLabel: {
    fontSize: 10,
    color: "#1f2937",
    fontWeight: typography.weight.bold,
    marginTop: -2,
  },
  refreshFab: {
    position: "absolute",
    bottom: 82,
    right: 16,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.base,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,188,13,0.95)",
    ...shadows.sm,
  },
  refreshFabIcon: {
    color: "#1f2937",
    marginRight: 4,
    fontSize: 14,
  },
  refreshFabLabel: {
    color: "#1f2937",
    fontSize: typography.xs,
    fontWeight: "600",
  },
  placeStripWrap: {
    backgroundColor: "#fffaf0",
    borderTopWidth: 1,
    borderTopColor: "#f7b500",
    maxHeight: 88,
  },
  placeStripContent: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingRight: spacing.xxl,
  },
  placePill: {
    minWidth: 120,
    maxWidth: 160,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.base,
    borderRadius: radius.lg,
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#f7b500",
  },
  placePillSelected: {
    borderColor: "#f59e0b",
    backgroundColor: "#fff3cd",
  },
  placePillRank: {
    position: "absolute",
    top: 4,
    right: 6,
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: "#f59e0b",
    alignItems: "center",
    justifyContent: "center",
  },
  placePillRankText: {
    fontSize: 10,
    fontWeight: "800",
    color: "#fff",
  },
  placePillName: {
    fontSize: typography.sm,
    fontWeight: typography.weight.semibold,
    color: "#111827",
    paddingRight: 20,
  },
  placePillNameSelected: {
    color: "#92400e",
  },
  placePillDist: {
    fontSize: typography.xs,
    color: "#6b7280",
    marginTop: 2,
  },
  bottomCard: {
    backgroundColor: "#ffffff",
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingTop: 12,
    paddingHorizontal: 16,
    paddingBottom: 12,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: -4 },
    elevation: 12,
  },
  sheetHandleWrap: {
    alignItems: "center",
    paddingTop: 6,
    paddingBottom: 6,
  },
  sheetHandle: {
    width: 44,
    height: 4,
    borderRadius: 999,
    backgroundColor: "#e5e7eb",
  },
  emptyState: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    alignItems: "center",
  },
  emptyTitle: {
    color: "#111827",
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
  },
  emptyHint: {
    color: "#6b7280",
    fontSize: typography.sm,
    marginTop: spacing.xs,
  },
  searchWiderBtn: {
    marginTop: spacing.base,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: "#ffbc0d",
    borderWidth: 1,
    borderColor: "#e0a800",
  },
  searchWiderBtnText: {
    color: "#1f2937",
    fontSize: typography.base,
    fontWeight: typography.weight.semibold,
  },
  mapFallback: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f3f4f6",
    padding: spacing.xl,
  },
  mapFallbackTitle: {
    fontSize: typography.xl,
    fontWeight: typography.weight.bold,
    color: "#111827",
    marginBottom: spacing.sm,
  },
  mapFallbackBody: {
    fontSize: typography.base,
    color: "#6b7280",
    textAlign: "center",
    lineHeight: 22,
  },
});
