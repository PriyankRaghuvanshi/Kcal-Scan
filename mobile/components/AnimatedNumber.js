/**
 * AnimatedNumber — Counts up from 0 to target value on mount.
 * Premium feel: numbers "arrive" instead of appearing instantly.
 */
import React, { useEffect, useRef, useState } from "react";
import { Text, Animated } from "react-native";

export function AnimatedNumber({
  value = 0,
  duration = 600,
  style,
  suffix = "",
  prefix = "",
  decimals = 0,
}) {
  const [display, setDisplay] = useState(0);
  const animRef = useRef(new Animated.Value(0)).current;
  const prevValue = useRef(0);

  useEffect(() => {
    const from = prevValue.current;
    const to = Number(value) || 0;
    prevValue.current = to;

    animRef.setValue(0);
    const listener = animRef.addListener(({ value: v }) => {
      const current = from + (to - from) * v;
      setDisplay(decimals > 0 ? current.toFixed(decimals) : Math.round(current));
    });

    Animated.timing(animRef, {
      toValue: 1,
      duration,
      useNativeDriver: false,
    }).start();

    return () => animRef.removeListener(listener);
  }, [value]);

  return (
    <Text style={style}>
      {prefix}{display}{suffix}
    </Text>
  );
}
