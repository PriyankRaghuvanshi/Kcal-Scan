// mobile/src/lib/revenuecat.js
import { Platform } from "react-native";
import Purchases from "react-native-purchases";

const RC_IOS_KEY = process.env.EXPO_PUBLIC_RC_IOS_KEY || "";
const RC_ANDROID_KEY = process.env.EXPO_PUBLIC_RC_ANDROID_KEY || "";
const OFFERING_ID = process.env.EXPO_PUBLIC_RC_OFFERING || "main";

// Your entitlements in RevenueCat (you told me these exact IDs)
export const ENTITLEMENTS = ["elite", "advanced", "pro", "infinite"];

function getApiKey() {
  const key = Platform.OS === "ios" ? RC_IOS_KEY : RC_ANDROID_KEY;
  if (!key) throw new Error(`Missing RevenueCat key for ${Platform.OS}`);
  return key;
}

export async function configurePurchases(appUserID) {
  // RevenueCat requires native build (not Expo Go)
  Purchases.setLogLevel(Purchases.LOG_LEVEL.DEBUG);

  const apiKey = getApiKey();
  await Purchases.configure({ apiKey, appUserID: appUserID || null });
}

export async function getMainOffering() {
  const offerings = await Purchases.getOfferings();
  const main = offerings?.all?.[OFFERING_ID] || offerings?.current;
  if (!main) throw new Error("No RevenueCat offering found (check offering identifier)");
  return main;
}

export function getActiveEntitlement(customerInfo) {
  const active = customerInfo?.entitlements?.active || {};
  // Return the first matching entitlement in priority order
  for (const id of ["infinite", "pro", "advanced", "elite"]) {
    if (active[id]) return id;
  }
  return "free";
}

export async function purchasePackage(pkg) {
  const { customerInfo } = await Purchases.purchasePackage(pkg);
  return customerInfo;
}

export async function restorePurchases() {
  const customerInfo = await Purchases.restorePurchases();
  return customerInfo;
}

export async function getCustomerInfo() {
  return await Purchases.getCustomerInfo();
}

