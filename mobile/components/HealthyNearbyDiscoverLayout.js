/**
 * Discover-style Healthy Nearby — colourful layout aligned with promo mock.
 */

import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Platform } from "react-native";
import MapView, { Marker } from "react-native-maps";
import { LinearGradient } from "expo-linear-gradient";
import { HealthyMapFilters } from "./HealthyMapFilters";
import { HealthyNearbyGridTile } from "./HealthyNearbyGridTile";
import { getPlaceCoords } from "../mapUtils";
import { spacing, radius, typography, shadows } from "../designTokens";

const ACCENT_PURPLE = "#a855f7";
const ACCENT_PINK = "#ec4899";
const ACCENT_MINT = "#4ade80";

function NumberedMarker({ number, isSelected, tierColor }) {
  return (
    <View
      style={[
        markerStyles.bubble,
        {
          backgroundColor: isSelected ? ACCENT_MINT : tierColor,
          borderWidth: 2.5,
          borderColor: "#fff",
        },
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
    ...shadows.sm,
  },
  bubbleText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "900",
  },
});

const MAP_HEIGHT = Platform.OS === "android" ? 188 : 212;

/** iOS map with slightly warmer / clearer feel */
const MAP_CUSTOM_STYLE = [
  { elementType: "geometry", stylers: [{ saturation: -12 }, { lightness: 8 }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#4b5563" }] },
  {
    featureType: "poi.park",
    elementType: "geometry",
    stylers: [{ color: "#bbf7d0" }],
  },
  {
    featureType: "water",
    elementType: "geometry",
    stylers: [{ color: "#93c5fd" }],
  },
];

export function HealthyNearbyDiscoverLayout({
  places = [],
  filterKey = "all",
  onFilterChange,
  selectedPlaceStableId = "",
  onSelectPlace,
  userCoords,
  focusCoords,
  onLoadPlaces,
  onRefreshAroundMe,
  busy = false,
  error = "",
  formatDistanceFromMeters,
  getPlaceStableId,
  onOpenFiltersInfo,
}) {
  const mapRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const useSafeAndroidPreview = Platform.OS === "android";

  const markersWithCoords = (Array.isArray(places) ? places : [])
    .map((place, idx) => ({ place, idx, coords: getPlaceCoords(place) }))
    .filter((x) => x.coords != null);

  const selectedStableId = String(selectedPlaceStableId || "").trim();

  useEffect(() => {
    if (onLoadPlaces && !busy && Array.isArray(places) && places.length === 0 && userCoords) {
      onLoadPlaces();
    }
  }, [onLoadPlaces, busy, places?.length, userCoords]);

  const region = (() => {
    const c = focusCoords || userCoords || markersWithCoords[0]?.coords;
    if (c && Number.isFinite(c.lat) && Number.isFinite(c.lng)) {
      return {
        latitude: c.lat,
        longitude: c.lng,
        latitudeDelta: 0.032,
        longitudeDelta: 0.032,
      };
    }
    return {
      latitude: 37.7749,
      longitude: -122.4194,
      latitudeDelta: 0.06,
      longitudeDelta: 0.06,
    };
  })();

  const handleMarkerPress = (place, idx) => {
    if (onSelectPlace && place) onSelectPlace(place, idx);
  };

  const gridData = (Array.isArray(places) ? places : []).slice(0, 20);

  const gridRows = [];
  for (let i = 0; i < gridData.length; i += 2) {
    gridRows.push(gridData.slice(i, i + 2));
  }

  return (
    <View style={styles.root}>
      {/* Rainbow border frame around map */}
      <LinearGradient
        colors={[ACCENT_PINK, ACCENT_PURPLE, "#3b82f6", ACCENT_MINT]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.mapFrame}
      >
        <View style={styles.mapCard}>
          <MapView
            ref={mapRef}
            style={styles.map}
            initialRegion={region}
            showsUserLocation={!!userCoords}
            mapType="standard"
            liteMode={useSafeAndroidPreview}
            moveOnMarkerPress={false}
            toolbarEnabled={false}
            scrollEnabled={!useSafeAndroidPreview}
            zoomEnabled={!useSafeAndroidPreview}
            rotateEnabled={false}
            pitchEnabled={false}
            pointerEvents={useSafeAndroidPreview ? "none" : "auto"}
            customMapStyle={Platform.OS === "ios" ? MAP_CUSTOM_STYLE : undefined}
            onMapReady={() => setMapReady(true)}
          >
            {mapReady &&
              markersWithCoords.map(({ place, idx, coords }) => {
                const stableId = getPlaceStableId ? getPlaceStableId(place, idx) : null;
                const isSelected = Boolean(selectedStableId && stableId === selectedStableId);
                const tier = idx === 0 ? 1 : idx === 1 ? 2 : idx === 2 ? 3 : 0;
                // #1 = promo-style red pin, others warm accent stack
                const tierColor =
                  tier === 1
                    ? "#ef4444"
                    : tier === 2
                    ? "#f97316"
                    : tier === 3
                    ? "#eab308"
                    : "#64748b";
                const useNumberedPin = !useSafeAndroidPreview && tier >= 1 && tier <= 3;
                return (
                  <Marker
                    key={stableId || `d-${idx}`}
                    coordinate={{ latitude: coords.lat, longitude: coords.lng }}
                    onPress={() => handleMarkerPress(place, idx)}
                    tracksViewChanges={false}
                    {...(useNumberedPin
                      ? {}
                      : {
                          pinColor: isSelected ? ACCENT_PURPLE : tierColor,
                        })}
                  >
                    {useNumberedPin ? (
                      <NumberedMarker number={tier} isSelected={isSelected} tierColor={tierColor} />
                    ) : null}
                  </Marker>
                );
              })}
          </MapView>
          <LinearGradient
            colors={["transparent", "rgba(15,18,28,0.35)"]}
            style={styles.mapBottomFade}
            pointerEvents="none"
          />
          <View style={styles.filtersOverlay}>
            <HealthyMapFilters activeKey={filterKey} onSelect={onFilterChange} />
          </View>
          {busy ? (
            <View style={styles.mapLoading}>
              <ActivityIndicator color={ACCENT_MINT} size="large" />
            </View>
          ) : null}
          {error ? (
            <View style={styles.mapError}>
              <Text style={styles.mapErrorText} numberOfLines={2}>
                {error}
              </Text>
            </View>
          ) : null}
          {useSafeAndroidPreview ? (
            <View pointerEvents="none" style={styles.androidPreviewBadge}>
              <Text style={styles.androidPreviewBadgeText}>Map preview on Android. Use Map or List below.</Text>
            </View>
          ) : null}
        </View>
      </LinearGradient>

      <LinearGradient
        colors={["#1a1530", "#121826", "#0d1117"]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.introCard}
      >
        <LinearGradient
          colors={[ACCENT_PURPLE, ACCENT_PINK]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={styles.introAccentStrip}
        />
        <View style={styles.introTextCol}>
          <Text style={styles.introTitle}>Healthy Nearby</Text>
          <Text style={styles.introBody}>
            Healthy Nearby helps you choose what fits your calories, protein, and goals.
          </Text>
        </View>
        <TouchableOpacity
          style={styles.introIconBtnWrap}
          onPress={onOpenFiltersInfo || onRefreshAroundMe}
          activeOpacity={0.85}
          disabled={!onOpenFiltersInfo && !onRefreshAroundMe}
        >
          <LinearGradient
            colors={["#4b5563", "#1f2937"]}
            style={styles.introIconBtn}
          >
            <Text style={styles.introIconGlyph}>⚙</Text>
          </LinearGradient>
        </TouchableOpacity>
      </LinearGradient>

      <TouchableOpacity
        style={styles.smartRowOuter}
        activeOpacity={0.75}
        onPress={onRefreshAroundMe}
        disabled={!onRefreshAroundMe || busy}
      >
        <LinearGradient
          colors={["rgba(74,222,128,0.2)", "rgba(168,85,247,0.18)"]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={styles.smartRow}
        >
          <Text style={styles.smartTitle}>Smart recommendation</Text>
          <LinearGradient colors={[ACCENT_PURPLE, ACCENT_PINK]} style={styles.smartChevronPill}>
            <Text style={styles.smartChevron}>›</Text>
          </LinearGradient>
        </LinearGradient>
      </TouchableOpacity>

      {gridData.length === 0 && !busy ? (
        <Text style={styles.emptyGrid}>Load the food map to see picks here.</Text>
      ) : (
        <View style={styles.gridContent}>
          {gridRows.map((pair, rowIdx) => (
            <View key={`row-${rowIdx}`} style={styles.gridRow}>
              {pair.map((item, colIdx) => {
                const index = rowIdx * 2 + colIdx;
                const key = String(getPlaceStableId?.(item, index) || item?.place_id || `g-${index}`);
                return (
                  <HealthyNearbyGridTile
                    key={key}
                    place={item}
                    index={index}
                    formatDistance={formatDistanceFromMeters}
                    selected={selectedStableId}
                    getStableId={getPlaceStableId}
                    onPress={(p, idx) => handleMarkerPress(p, idx)}
                  />
                );
              })}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    marginTop: spacing.sm,
  },
  mapFrame: {
    borderRadius: radius.xl + 2,
    padding: 3,
    ...Platform.select({
      ios: {
        shadowColor: ACCENT_PURPLE,
        shadowOffset: { width: 0, height: 10 },
        shadowOpacity: 0.35,
        shadowRadius: 16,
      },
      android: { elevation: 12 },
    }),
  },
  mapCard: {
    borderRadius: radius.xl,
    overflow: "hidden",
    height: MAP_HEIGHT,
    backgroundColor: "#ffffff",
  },
  map: {
    ...StyleSheet.absoluteFillObject,
  },
  mapBottomFade: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    height: 48,
  },
  filtersOverlay: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 8,
    alignItems: "center",
  },
  mapLoading: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(17,24,39,0.35)",
    alignItems: "center",
    justifyContent: "center",
  },
  mapError: {
    position: "absolute",
    left: 8,
    right: 8,
    bottom: 48,
    backgroundColor: "rgba(190,24,93,0.92)",
    padding: spacing.sm,
    borderRadius: radius.md,
  },
  mapErrorText: {
    color: "#fce7f3",
    fontSize: typography.sm,
    textAlign: "center",
  },
  androidPreviewBadge: {
    position: "absolute",
    left: spacing.sm,
    right: spacing.sm,
    bottom: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: "rgba(17, 24, 39, 0.72)",
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  androidPreviewBadgeText: {
    color: "#fff",
    fontSize: typography.xs,
    fontWeight: typography.weight.medium,
    textAlign: "center",
  },
  introCard: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: radius.xl,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.md,
    borderWidth: 1,
    borderColor: "rgba(245,158,11,0.42)",
    overflow: "hidden",
  },
  introAccentStrip: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 5,
    borderTopLeftRadius: radius.xl,
    borderBottomLeftRadius: radius.xl,
  },
  introTextCol: {
    flex: 1,
    paddingLeft: spacing.sm + 2,
    paddingRight: spacing.sm,
  },
  introTitle: {
    color: "#ffffff",
    fontSize: Platform.OS === "android" ? 17 : 19,
    fontWeight: "800",
    letterSpacing: -0.3,
  },
  introBody: {
    color: "#c4b5fd",
    fontSize: Platform.OS === "android" ? 13 : 14,
    marginTop: 6,
    lineHeight: Platform.OS === "android" ? 18 : 21,
    fontWeight: "500",
  },
  introIconBtnWrap: {
    borderRadius: 22,
    overflow: "hidden",
  },
  introIconBtn: {
    width: 46,
    height: 46,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
  },
  introIconGlyph: {
    color: "#fde68a",
    fontSize: 22,
  },
  smartRowOuter: {
    marginTop: Platform.OS === "android" ? spacing.md : spacing.lg,
    marginBottom: spacing.sm,
    borderRadius: 16,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(245,158,11,0.42)",
  },
  smartRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: Platform.OS === "android" ? 10 : 12,
    paddingHorizontal: Platform.OS === "android" ? 14 : 16,
  },
  smartTitle: {
    color: "#fff7ed",
    fontSize: Platform.OS === "android" ? 15 : 17,
    fontWeight: "800",
    letterSpacing: -0.2,
  },
  smartChevronPill: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  smartChevron: {
    color: "#fff",
    fontSize: 22,
    fontWeight: "600",
    marginTop: -2,
  },
  gridContent: {
    paddingBottom: spacing.lg,
  },
  gridRow: {
    justifyContent: "space-between",
    gap: 0,
  },
  emptyGrid: {
    color: "#92400e",
    fontSize: typography.sm,
    textAlign: "center",
    marginTop: spacing.md,
    marginBottom: spacing.lg,
    fontWeight: "600",
  },
});
