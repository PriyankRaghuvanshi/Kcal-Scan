/**
 * MacroRing — Circular progress ring for daily macro tracking.
 * Apple Watch Activity Ring style. Shows kcal or protein progress.
 */
import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Circle } from "react-native-svg";

const STROKE = 8;
const DEFAULT_SIZE = 80;

export function MacroRing({
  current = 0,
  target = 2000,
  label = "kcal",
  color = "#22c55e",
  trackColor = "rgba(255,255,255,0.06)",
  size = DEFAULT_SIZE,
  textColor = "#f8fafc",
}) {
  const r = (size - STROKE) / 2;
  const circumference = 2 * Math.PI * r;
  const progress = target > 0 ? Math.min(current / target, 1) : 0;
  const remaining = Math.max(0, target - current);
  const offset = circumference * (1 - progress);

  return (
    <View style={[s.wrap, { width: size, height: size }]}>
      <Svg width={size} height={size} style={s.svg}>
        {/* Track */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={trackColor}
          strokeWidth={STROKE}
          fill="none"
        />
        {/* Progress */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={STROKE}
          fill="none"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          rotation="-90"
          origin={`${size / 2}, ${size / 2}`}
        />
      </Svg>
      <View style={s.center}>
        <Text style={[s.value, { color: textColor }]}>{Math.round(remaining)}</Text>
        <Text style={[s.label, { color }]}>{label}</Text>
      </View>
    </View>
  );
}

export function DailyMacroRings({ kcalCurrent, kcalTarget, proteinCurrent, proteinTarget }) {
  return (
    <View style={s.ringsRow}>
      <MacroRing
        current={kcalCurrent || 0}
        target={kcalTarget || 2000}
        label="kcal left"
        color="#22c55e"
        size={90}
      />
      <MacroRing
        current={proteinCurrent || 0}
        target={proteinTarget || 120}
        label="g protein"
        color="#93c5fd"
        size={90}
      />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  svg: { position: "absolute" },
  center: { alignItems: "center", justifyContent: "center" },
  value: { fontSize: 18, fontWeight: "800", fontFamily: "Inter_800ExtraBold" },
  label: { fontSize: 9, fontWeight: "600", fontFamily: "Inter_600SemiBold", marginTop: 1 },
  ringsRow: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 24,
    paddingVertical: 12,
  },
});
