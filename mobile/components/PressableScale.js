/**
 * PressableScale — Premium press feedback component.
 * Scales down to 0.97 on press + optional haptic. Wraps children.
 * Use instead of TouchableOpacity for premium feel on CTAs and cards.
 */
import React, { useRef } from "react";
import { Animated, Pressable } from "react-native";
import * as Haptics from "expo-haptics";

export function PressableScale({
  onPress,
  style,
  children,
  haptic = false,
  scaleDown = 0.97,
  disabled = false,
  ...rest
}) {
  const scale = useRef(new Animated.Value(1)).current;

  const onPressIn = () => {
    Animated.spring(scale, {
      toValue: scaleDown,
      useNativeDriver: true,
      speed: 50,
      bounciness: 4,
    }).start();
  };

  const onPressOut = () => {
    Animated.spring(scale, {
      toValue: 1,
      useNativeDriver: true,
      speed: 40,
      bounciness: 6,
    }).start();
  };

  const handlePress = () => {
    if (disabled) return;
    if (haptic) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }
    onPress?.();
  };

  return (
    <Pressable
      onPressIn={onPressIn}
      onPressOut={onPressOut}
      onPress={handlePress}
      disabled={disabled}
      {...rest}
    >
      <Animated.View style={[style, { transform: [{ scale }] }]}>
        {children}
      </Animated.View>
    </Pressable>
  );
}
