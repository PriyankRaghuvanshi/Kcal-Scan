import Purchases from "react-native-purchases";
import { Platform } from "react-native";

export function getActiveEntitlement(customerInfo) {
  const active = customerInfo?.entitlements?.active || {};
  const keys = Object.keys(active);
  if (keys.length === 0) return "free";

  // If multiple are active, pick “highest”
  const priority = ["infinite", "pro", "advanced", "elite"]; // adjust if you want different ordering
  for (const k of priority) if (keys.includes(k)) return k;
  return keys[0];
}

export async function configurePurchases(apiKey, appUserID) {
  if (!apiKey) throw new Error("Missing RevenueCat API key");
  await Purchases.configure({
    apiKey,
    appUserID,
  });

  // Optional: helpful logs in dev
  Purchases.setLogLevel(Purchases.LOG_LEVEL.DEBUG);
}

export async function fetchMainOffering() {
  const offerings = await Purchases.getOfferings();
  const main = offerings?.all?.main || offerings?.current; // prefer "main"
  if (!main) throw new Error("No offering available (main/current).");
  return main;
}

export async function purchasePackage(pkg) {
  const { customerInfo } = await Purchases.purchasePackage(pkg);
  return customerInfo;
}

export async function restorePurchases() {
  const info = await Purchases.restorePurchases();
  return info;
}

export function isIOS() {
  return Platform.OS === "ios";
}

