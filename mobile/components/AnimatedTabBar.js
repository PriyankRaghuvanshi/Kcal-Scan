/**
 * AnimatedTabBar — Premium bottom navigation with sliding indicator.
 * McDonald's/Instagram-style animated pill that glides between tabs.
 */
import React, { useRef, useEffect } from "react";
import { View, Text, Animated, Dimensions, Platform, StyleSheet } from "react-native";
import { PressableScale } from "./PressableScale";

const SCREEN_W = Dimensions.get("window").width;

export function AnimatedTabBar({
  tabs,
  activeIndex,
  onTabPress,
  badge,
}) {
  const indicatorX = useRef(new Animated.Value(0)).current;
  const tabWidth = SCREEN_W / tabs.length;

  useEffect(() => {
    Animated.spring(indicatorX, {
      toValue: activeIndex * tabWidth,
      useNativeDriver: true,
      speed: 20,
      bounciness: 8,
    }).start();
  }, [activeIndex, tabWidth]);

  return (
    <View style={s.outer}>
      {/* Top gradient hairline */}
      <View style={s.hairline} />

      <View style={s.bar}>
        {/* Sliding indicator */}
        <Animated.View
          style={[
            s.indicator,
            {
              width: tabWidth - 16,
              transform: [{ translateX: Animated.add(indicatorX, 8) }],
            },
          ]}
        />

        {/* Tab items */}
        {tabs.map((t, idx) => {
          const isActive = idx === activeIndex;
          const hasBadge = badge?.[t.key];
          return (
            <PressableScale
              key={t.key}
              style={s.tab}
              onPress={() => onTabPress(t, idx)}
              scaleDown={0.92}
              haptic
            >
              <View style={s.iconWrap}>
                <Text style={[s.icon, isActive && s.iconActive]}>
                  {t.icon}
                </Text>
                {hasBadge ? <View style={s.badgeDot} /> : null}
              </View>
              <Text style={[s.label, isActive && s.labelActive]}>
                {t.label}
              </Text>
            </PressableScale>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  outer: {
    backgroundColor: "#0c1220",
    borderTopWidth: 1,
    borderTopColor: "rgba(26, 38, 66, 0.9)",
  },
  hairline: {
    height: 2,
    backgroundColor: "rgba(34, 197, 94, 0.3)",
  },
  bar: {
    flexDirection: "row",
    alignItems: "stretch",
    justifyContent: "space-between",
    paddingTop: 6,
    paddingBottom: Platform.OS === "ios" ? 22 : 10,
    position: "relative",
  },
  indicator: {
    position: "absolute",
    top: 4,
    height: 44,
    borderRadius: 12,
    backgroundColor: "rgba(34, 197, 94, 0.12)",
  },
  tab: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
  },
  iconWrap: {
    position: "relative",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 22,
  },
  icon: {
    fontSize: 17,
    color: "#64748b",
    fontWeight: "800",
  },
  iconActive: {
    color: "#4ade80",
  },
  label: {
    fontSize: 10,
    fontWeight: "700",
    color: "#64748b",
    marginTop: 2,
    fontFamily: "Inter_700Bold",
  },
  labelActive: {
    color: "#4ade80",
  },
  badgeDot: {
    position: "absolute",
    top: -1,
    right: -6,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#f59e0b",
    borderWidth: 1,
    borderColor: "#000",
  },
});
