/**
 * Healthy Nearby map screen: real MapView with markers, filters, bottom card.
 * Uses design tokens for overlay and empty states.
 */

import React, { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
} from "react-native";
import MapView, { Marker } from "react-native-maps";
import { HealthyMapFilters } from "./HealthyMapFilters";
import { HealthyPlaceBottomCard } from "./HealthyPlaceBottomCard";
import { getPlaceCoords } from "../mapUtils";
import { colors, spacing, radius, typography } from "../designTokens";

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

export function HealthyNearbyMapScreen({
  places = [],
  filterKey = "all",
  onFilterChange,
  selectedPlace,
  onSelectPlace,
  userCoords,
  focusCoords,
  onLoadPlaces,
  onSearchWider,
  busy = false,
  error = "",
  formatDistanceFromMeters,
  getPlaceStableId,
  onScanMenu,
}) {
  const mapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const initialCenterDone = useRef(false);

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

  return (
    <View style={styles.container}>
      <View style={styles.mapWrap}>
        <MapView
          ref={mapRef}
          style={styles.map}
          initialRegion={region}
          showsUserLocation={!!userCoords}
          showsMyLocationButton={!!userCoords}
          mapType={Platform.OS === "ios" ? "mutedStandard" : "standard"}
          onMapReady={() => setMapReady(true)}
        >
          {markersWithCoords.map(({ place, idx, coords }) => {
            const stableId = getPlaceStableId ? getPlaceStableId(place, idx) : null;
            const isSelected = Boolean(selectedStableId && stableId === selectedStableId);
            const tier = idx === 0 ? 1 : idx === 1 ? 2 : idx === 2 ? 3 : 0;
            const tierColor =
              isSelected ? colors.success.primary
              : tier === 1 ? colors.success.primary
              : tier === 2 ? colors.success.muted
              : tier === 3 ? colors.success.border
              : colors.slate.primary;

            return (
              <Marker
                key={stableId || `m-${idx}`}
                coordinate={{ latitude: coords.lat, longitude: coords.lng }}
                onPress={() => handleMarkerPress(place, idx)}
                pinColor={tierColor}
                opacity={isSelected ? 1 : tier > 0 ? 0.95 : 0.85}
                title={String(place?.place_name ?? place?.name ?? "Place").slice(0, 40)}
              />
            );
          })}
        </MapView>

        {/* Filter chips */}
        <View style={styles.filtersOverlay}>
          <HealthyMapFilters activeKey={filterKey} onSelect={onFilterChange} />
        </View>

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
      </View>

      {/* Bottom card: selected place or empty state */}
      <View style={styles.bottomCard}>
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
    backgroundColor: colors.surface.primary,
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
    backgroundColor: colors.surface.overlay,
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
  bottomCard: {
    backgroundColor: colors.surface.card,
  },
  emptyState: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    alignItems: "center",
  },
  emptyTitle: {
    color: colors.accent.primary,
    fontSize: typography.lg,
    fontWeight: typography.weight.semibold,
  },
  emptyHint: {
    color: colors.slate.primary,
    fontSize: typography.sm,
    marginTop: spacing.xs,
  },
  searchWiderBtn: {
    marginTop: spacing.base,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface.elevated,
    borderWidth: 1,
    borderColor: colors.surface.cardBorder,
  },
  searchWiderBtnText: {
    color: colors.accent.muted,
    fontSize: typography.base,
    fontWeight: typography.weight.semibold,
  },
});
