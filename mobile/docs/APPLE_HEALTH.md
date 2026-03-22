# Apple Health (HealthKit) integration

The app can write **meal nutrition** (from food scans) and **weight** (from Let's Go journey) to iPhone Health.

## Behavior

- **Food scans:** After a successful meal analysis, calories, protein, carbs, fat, and fiber are written to Health as a single "CalorieClick meal" entry for that time.
- **Weight:** When the user logs weight in the Goal Coach Progress section, the value is written to Health (Body Measurements → Weight).
- **iOS only.** The integration no-ops on Android and when the HealthKit native module is not linked.

## Enabling HealthKit (iOS) — requires Apple capability first

HealthKit needs both app config and Apple provisioning support. Right now the app contains the Health usage descriptions, but the release provisioning profile must also have the HealthKit capability enabled before we can ship a Health-enabled binary.

1. **Dependency:** `react-native-health` is in `package.json`. Run `npm install` (you already did this).

2. **Apple Developer:** In Apple Developer → Identifiers → `com.priyank.calorieclick`, enable the **HealthKit** capability and refresh the App Store provisioning profile.

3. **App config:** Add `ios.entitlements.com.apple.developer.healthkit: true` in `app.json` only after the App ID capability is enabled. If the profile does not support HealthKit yet, EAS iOS builds will fail at Xcode signing.

4. **Usage descriptions:** `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription` are already in `app.json` → `ios.infoPlist`. They are baked into the build.

5. **Native link:** For a **development build** (e.g. `npx expo run:ios`), run `cd ios && pod install` after `npm install` so the HealthKit native code is linked. For **EAS Build**, the cloud build runs `pod install` for you.

**Summary:** HealthKit does **not** work in Expo Go. To ship it in TestFlight/App Store, first enable HealthKit on the Apple App ID and regenerate provisioning, then add the HealthKit entitlement back into `app.json` and rebuild.

## Permissions

On first run (when the user is logged in), the app calls `initAppleHealth()`, which requests write permission for:

- Dietary: Energy Consumed, Protein, Carbohydrates, Fat Total, Fiber  
- Body: Weight  

If the user denies, writes are skipped without breaking the app.

## Code

- **Module:** `mobile/utils/appleHealth.js`  
  - `initAppleHealth(callback)`  
  - `writeNutritionToHealth(opts, callback)`  
  - `writeWeightToHealth(opts, callback)`  
  - `isAppleHealthAvailable()`
- **Wiring:** Meal write after successful `analyzePhoto()`; weight write after successful `submitWeightEntry()` in the Goal Coach section.
