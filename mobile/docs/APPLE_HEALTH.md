# Apple Health (HealthKit) integration

The app can write **meal nutrition** (from food scans) and **weight** (from Let's Go journey) to iPhone Health.

## Behavior

- **Food scans:** After a successful meal analysis, calories, protein, carbs, fat, and fiber are written to Health as a single "CalorieClick meal" entry for that time.
- **Weight:** When the user logs weight in the Goal Coach Progress section, the value is written to Health (Body Measurements → Weight).
- **iOS only.** The integration no-ops on Android and when the HealthKit native module is not linked.

## Enabling HealthKit (iOS) — done at build time

HealthKit is **enabled automatically when you build**:

1. **Dependency:** `react-native-health` is in `package.json`. Run `npm install` (you already did this).

2. **Capability:** In `app.json`, `ios.entitlements` includes `com.apple.developer.healthkit: true`. When you run **EAS Build** (`eas build --platform ios` or your `npm run ios:build:production`), EAS syncs this with Apple and the built app has HealthKit enabled. No manual Xcode step is required for EAS Build.

3. **Usage descriptions:** `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription` are already in `app.json` → `ios.infoPlist`. They are baked into the build.

4. **Native link:** For a **development build** (e.g. `npx expo run:ios`), run `cd ios && pod install` after `npm install` so the HealthKit native code is linked. For **EAS Build**, the cloud build runs `pod install` for you.

**Summary:** Run your normal iOS build (EAS or `expo run:ios`). HealthKit will be enabled in the built app. It does **not** work in Expo Go; use a dev client or production build.

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
