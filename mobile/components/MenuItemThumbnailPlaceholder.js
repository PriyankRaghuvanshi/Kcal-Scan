import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

const THEMES = {
  protein: {
    colors: ["#166534", "#22c55e", "#86efac"],
    glow: "rgba(187, 247, 208, 0.28)",
  },
  carb: {
    colors: ["#b45309", "#f59e0b", "#fcd34d"],
    glow: "rgba(254, 215, 170, 0.24)",
  },
  drink: {
    colors: ["#1d4ed8", "#0ea5e9", "#7dd3fc"],
    glow: "rgba(191, 219, 254, 0.24)",
  },
  dessert: {
    colors: ["#be185d", "#ec4899", "#f9a8d4"],
    glow: "rgba(251, 207, 232, 0.28)",
  },
};

const DESSERT_TOKENS = [
  "dessert",
  "cake",
  "brownie",
  "cookie",
  "donut",
  "doughnut",
  "pastry",
  "waffle",
  "ice cream",
  "gelato",
  "sundae",
  "froyo",
  "frozen yogurt",
  "custard",
  "cheesecake",
  "sweet",
  "chocolate",
  "truffle",
  "muffin",
];

const DRINK_TOKENS = [
  "drink",
  "beverage",
  "smoothie",
  "shake",
  "juice",
  "soda",
  "cola",
  "coffee",
  "tea",
  "latte",
  "frappe",
  "mojito",
  "lemonade",
  "milk",
];

const PROTEIN_TOKENS = [
  "protein",
  "chicken",
  "beef",
  "steak",
  "turkey",
  "tuna",
  "salmon",
  "fish",
  "prawn",
  "shrimp",
  "paneer",
  "tofu",
  "egg",
  "omelette",
  "kebab",
  "meat",
  "bbq",
  "grilled",
  "tikka",
  "sausage",
];

const CARB_TOKENS = [
  "pizza",
  "pasta",
  "noodle",
  "rice",
  "burger",
  "sandwich",
  "sub",
  "wrap",
  "burrito",
  "taco",
  "naan",
  "bread",
  "fries",
  "chips",
  "bagel",
  "toast",
];

function toNumber(value) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function firstLetter(value) {
  const match = String(value || "").trim().match(/[A-Za-z0-9]/);
  return match ? match[0].toUpperCase() : "?";
}

function collectSignals(item, fallbackName) {
  const safeItem = item && typeof item === "object" ? item : {};
  const textParts = [
    safeItem.item_name,
    safeItem.name,
    fallbackName,
    safeItem.category,
    safeItem.item_type,
    safeItem.product_type,
    safeItem.menu_category,
    safeItem.category_name,
    safeItem.primary_type,
    safeItem.display_label,
  ]
    .map(normalizeText)
    .filter(Boolean);

  const negativeFlags = Array.isArray(safeItem.negative_flags)
    ? safeItem.negative_flags.map(normalizeText).filter(Boolean)
    : [];

  return {
    text: textParts.join(" "),
    negativeFlags,
    protein: toNumber(safeItem.estimated_protein_g ?? safeItem.protein_g ?? safeItem.best_item_protein),
    carbs: toNumber(safeItem.estimated_carbs_g ?? safeItem.carbs_g ?? safeItem.best_item_carbs),
  };
}

function includesAnyToken(text, tokens) {
  return tokens.some((token) => text.includes(token));
}

export function getMenuItemPlaceholderTheme(item, fallbackName) {
  const { text, negativeFlags, protein, carbs } = collectSignals(item, fallbackName);

  if (negativeFlags.includes("dessert_heavy") || includesAnyToken(text, DESSERT_TOKENS)) {
    return THEMES.dessert;
  }
  if (negativeFlags.includes("sugary_drink") || includesAnyToken(text, DRINK_TOKENS)) {
    return THEMES.drink;
  }
  if (includesAnyToken(text, PROTEIN_TOKENS)) {
    return THEMES.protein;
  }
  if (includesAnyToken(text, CARB_TOKENS)) {
    return THEMES.carb;
  }
  if (protein != null || carbs != null) {
    if ((protein || 0) >= Math.max(carbs || 0, 18)) return THEMES.protein;
    if ((carbs || 0) >= Math.max(protein || 0, 18)) return THEMES.carb;
  }
  return THEMES.protein;
}

export function MenuItemThumbnailPlaceholder({
  item,
  fallbackName,
  style,
  textStyle,
}) {
  const label = String(
    (item && typeof item === "object" && (item.item_name || item.name)) || fallbackName || "Menu item"
  ).trim();
  const theme = getMenuItemPlaceholderTheme(item, label);

  return (
    <LinearGradient
      colors={theme.colors}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[styles.base, style]}
    >
      <View pointerEvents="none" style={[styles.glow, { backgroundColor: theme.glow }]} />
      <View pointerEvents="none" style={styles.sheen} />
      <Text numberOfLines={1} style={[styles.letter, textStyle]}>
        {firstLetter(label)}
      </Text>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
  },
  glow: {
    position: "absolute",
    width: "92%",
    height: "92%",
    borderRadius: 999,
    transform: [{ translateY: 6 }],
  },
  sheen: {
    position: "absolute",
    top: -12,
    left: -10,
    width: "72%",
    height: "55%",
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.18)",
    transform: [{ rotate: "-18deg" }],
  },
  letter: {
    color: "#f8fafc",
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: 0.6,
    textShadowColor: "rgba(15, 23, 42, 0.35)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 8,
  },
});
