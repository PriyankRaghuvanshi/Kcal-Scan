/**
 * QuickAddSheet — text-based manual meal logging.
 * User types "chicken biryani 1 plate" → backend estimates macros → logs meal.
 */
import React, { useState, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Modal,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  PanResponder,
  StyleSheet,
} from "react-native";
import { BlurView } from "expo-blur";
import { PressableScale } from "./PressableScale";

export function QuickAddSheet({ visible, onClose, onSubmit, busy }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);

  const panRef = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, g) => g.dy > 8 && Math.abs(g.dy) > Math.abs(g.dx),
      onPanResponderRelease: (_, g) => {
        if (g.dy > 80) handleClose();
      },
    })
  ).current;

  const handleClose = () => {
    setText("");
    setResult(null);
    onClose?.();
  };

  const handleSubmit = async () => {
    if (!text.trim() || busy) return;
    const res = await onSubmit?.(text.trim());
    if (res) setResult(res);
  };

  if (!visible) return null;

  return (
    <Modal visible transparent animationType="slide" onRequestClose={handleClose}>
      <KeyboardAvoidingView
        style={s.overlay}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {Platform.OS === "ios" ? (
          <BlurView intensity={40} tint="dark" style={StyleSheet.absoluteFill}>
            <TouchableOpacity style={s.backdrop} activeOpacity={1} onPress={handleClose} />
          </BlurView>
        ) : (
          <TouchableOpacity style={s.backdrop} activeOpacity={1} onPress={handleClose} />
        )}
        <View style={s.sheet} {...panRef.panHandlers}>
          <View style={s.handleRow}>
            <View style={s.handle} />
          </View>

          <Text style={s.title}>Quick Add</Text>
          <Text style={s.subtitle}>Type what you ate — we'll estimate the macros</Text>

          <TextInput
            style={s.input}
            placeholder="e.g. chicken biryani, 1 plate"
            placeholderTextColor="#64748b"
            value={text}
            onChangeText={setText}
            autoFocus
            returnKeyType="done"
            onSubmitEditing={handleSubmit}
            multiline={false}
          />

          {result ? (
            <View style={s.resultCard}>
              <Text style={s.resultName} numberOfLines={2}>{result.meal_name || text}</Text>
              <View style={s.resultChips}>
                <View style={s.chip}><Text style={s.chipText}>🔥 {result.total_calories || 0} kcal</Text></View>
                <View style={s.chip}><Text style={s.chipText}>💪 {result.total_protein_g || 0}g protein</Text></View>
                <View style={s.chip}><Text style={s.chipText}>🍞 {result.total_carbs_g || 0}g carbs</Text></View>
                <View style={s.chip}><Text style={s.chipText}>🧈 {result.total_fat_g || 0}g fat</Text></View>
              </View>
              <Text style={s.resultSource}>
                {result.source === "chain_db_match" ? "✅ Matched from real menu data" : "📊 AI estimated"}
              </Text>
              <TouchableOpacity style={s.ctaDone} onPress={handleClose} activeOpacity={0.8}>
                <Text style={s.ctaDoneText}>Done — Meal Logged ✓</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <PressableScale
              style={[s.cta, (!text.trim() || busy) && s.ctaDisabled]}
              onPress={handleSubmit}
              disabled={!text.trim() || busy}
              haptic
            >
              {busy ? (
                <ActivityIndicator color="#052e16" size="small" />
              ) : (
                <Text style={s.ctaText}>Log This Meal</Text>
              )}
            </PressableScale>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(0,0,0,0.55)" },
  sheet: {
    backgroundColor: "#0f1624",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  handleRow: { alignItems: "center", paddingTop: 10, paddingBottom: 6 },
  handle: { width: 40, height: 5, borderRadius: 3, backgroundColor: "#334155" },

  title: { fontSize: 22, fontWeight: "800", color: "#f8fafc", marginTop: 12, fontFamily: "Inter_800ExtraBold" },
  subtitle: { fontSize: 14, color: "#94a3b8", marginTop: 4, marginBottom: 16, fontFamily: "Inter_400Regular" },

  input: {
    backgroundColor: "#0c1220",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: "#f8fafc",
    borderWidth: 1.5,
    borderColor: "#1e293b",
    marginBottom: 16,
    fontFamily: "Inter_400Regular",
    minHeight: 50,
  },

  cta: { backgroundColor: "#22c55e", paddingVertical: 16, borderRadius: 14, alignItems: "center", minHeight: 52 },
  ctaDisabled: { opacity: 0.4 },
  ctaText: { fontSize: 16, fontWeight: "700", color: "#052e16", fontFamily: "Inter_700Bold" },

  resultCard: {
    backgroundColor: "#0a1628",
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: "#1e3a5f",
    gap: 10,
  },
  resultName: { fontSize: 18, fontWeight: "700", color: "#f8fafc" },
  resultChips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: "#1e293b" },
  chipText: { fontSize: 12, fontWeight: "600", color: "#e2e8f0" },
  resultSource: { fontSize: 12, color: "#94a3b8", fontStyle: "italic" },

  ctaDone: { backgroundColor: "#22c55e", paddingVertical: 14, borderRadius: 12, alignItems: "center", marginTop: 4 },
  ctaDoneText: { fontSize: 15, fontWeight: "700", color: "#052e16" },
});
