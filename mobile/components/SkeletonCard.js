/**
 * SkeletonCard — shimmer placeholder while Healthy Nearby is loading.
 * Mimics RecommendationCard layout with animated pulse effect.
 */
import React, { useEffect, useRef } from "react";
import { View, Animated, StyleSheet } from "react-native";

function Shimmer({ style }) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return <Animated.View style={[s.bone, style, { opacity }]} />;
}

export function SkeletonCard() {
  return (
    <View style={s.card}>
      {/* Header: name + score */}
      <View style={s.headerRow}>
        <Shimmer style={{ width: "55%", height: 18, borderRadius: 6 }} />
        <Shimmer style={{ width: 36, height: 36, borderRadius: 10 }} />
      </View>

      {/* Confidence badge */}
      <Shimmer style={{ width: 100, height: 14, borderRadius: 4, marginTop: 8 }} />

      {/* Best item row: image + text */}
      <View style={s.bestRow}>
        <Shimmer style={{ width: 56, height: 56, borderRadius: 12 }} />
        <View style={{ flex: 1, gap: 6 }}>
          <Shimmer style={{ width: "80%", height: 16, borderRadius: 5 }} />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Shimmer style={{ width: 70, height: 22, borderRadius: 999 }} />
            <Shimmer style={{ width: 85, height: 22, borderRadius: 999 }} />
          </View>
        </View>
      </View>

      {/* Action row */}
      <View style={s.actionRow}>
        <Shimmer style={{ width: 120, height: 34, borderRadius: 8 }} />
        <Shimmer style={{ width: 80, height: 34, borderRadius: 8 }} />
      </View>
    </View>
  );
}

export function SkeletonCardList({ count = 4 }) {
  return (
    <View style={{ gap: 12 }}>
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={`skel-${i}`} />
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    backgroundColor: "#0f1624",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1e293b",
    padding: 16,
    gap: 12,
  },
  bone: {
    backgroundColor: "#1e293b",
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  bestRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginTop: 4,
  },
  actionRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 4,
  },
});
