# App Store Review Checklist (CalorieClick AI)

Use this before submitting to reduce rejection risk. The app already implements the items below; verify they are visible and correct in your build.

---

## 1. Crashes & stability

- **Safe linking:** All external links (Privacy Policy, Terms, Health sources, FSSAI verify) use `openURLSafe()` so invalid or failed URLs do not crash the app.
- **Sign out:** `signOut()` checks for `supabase` before calling `supabase.auth.signOut()` so missing env does not throw.
- **Refs:** Camera and scroll refs are null-checked before use.
- **API responses:** `safeJson()` and try/catch around fetch/analyze prevent unhandled rejections from crashing the app.

**Before submit:** Run the app and tap every link (Privacy, Terms, Health sources); use Restore, Delete Account, and sign out. Confirm no crash.

---

## 2. In-App Purchase & subscriptions (Guideline 3.1.2)

- **Service name:** “CalorieClick.ai – Food Scan” is shown in the Upgrade card.
- **Subscription length:** “Monthly (auto-renewing) subscription” with explanation of access for that month.
- **What you get:** Elite (barcode, more scans), Advanced (limits, journey), Pro (coaching), Infinite (all features).
- **Prices:** Each plan shows price per month (or “See App Store” / “Loading…” when RevenueCat is loading). Note: “Prices are shown in the App Store and may vary by country or region.”
- **Restore purchases:** “Restore” button is visible and explains it syncs plan and does not refill scans.
- **Cancellation:** Text states user can “manage or cancel your subscription in Apple ID Settings.”
- **Payment:** “Payment will be charged to your Apple ID account at confirmation of purchase.”

**Before submit:** Complete a test purchase (sandbox) and use Restore. Ensure paywall copy and Upgrade card copy are visible and accurate.

---

## 3. Privacy & data (Guideline 5.1.1)

- **Privacy Policy:** Link in Upgrade card opens your privacy policy URL (currently `https://sites.google.com/view/calorieclickai/privacy-policy`). Must be live and describe data collection and use.
- **Terms / EULA:** Link to Terms of Use (EULA) in Upgrade card (e.g. Apple’s standard EULA or your own).
- **Account deletion:** “Delete Account” in Privacy & Account section with confirmation. Explains permanent deletion of scan history, coach data, goals, AI consent, and login. Backend must actually delete or anonymize data when `/account/delete` is called.

**Before submit:** Confirm privacy policy URL loads. Test Delete Account flow and confirm backend deletes/anonymizes data.

---

## 4. Permissions & usage descriptions

- **Camera:** `NSCameraUsageDescription` (and expo-camera permission text) explain meal and barcode scanning.
- **Photo library:** Read and Add usage descriptions for choosing/saving images.
- **Location:** “We use your location to find healthy food places near you.”
- **HealthKit (iOS):**  
  - `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription` describe writing nutrition and weight to Health.  
  - HealthKit is optional; app works without it (see `utils/appleHealth.js`).

**Before submit:** Confirm all permission prompts and Settings → Privacy strings match app behavior. Do not request Health/Location/Camera before the feature that needs them.

---

## 5. Health & medical (Guideline 1.4.1)

- **Disclaimer:** Health notice states the app is “for informational purposes only and is not medical advice” and advises consulting a health professional.
- **Sources:** Listed health/nutrition sources (USDA, MedlinePlus, etc.) with links.
- **Encryption:** `ITSAppUsesNonExemptEncryption: false` is set in `app.json` if you use only standard encryption.

**Before submit:** Ensure disclaimer and sources are visible where health/nutrition content is shown.

---

## 6. Content & design

- No placeholder or “Lorem ipsum” in production.
- No broken or empty links in the build you submit.
- Subscription and pricing text must be readable (not cut off or hidden).

---

## 7. App Privacy (App Store Connect)

- In App Store Connect → App Privacy, declare:
  - Data linked to identity (e.g. account, usage).
  - Health data if you write to HealthKit (nutrition, weight).
  - Usage data (e.g. scans, feature use) if sent to your backend.
- Purposes (e.g. App Functionality, Analytics) must match your privacy policy.

---

## 8. Quick verification list

| Item | Where to check |
|------|----------------|
| Privacy Policy link | Upgrade card → “Privacy Policy” |
| Terms / EULA link | Upgrade card → “Terms of Use (EULA)” |
| Restore button | Scans left card → “Restore” |
| Subscription text (length, cancel, price) | Upgrade card (scroll) |
| Delete Account | Privacy & Account → “Delete Permanently” |
| Health disclaimer + sources | Health notice card |
| Camera / Location / Health usage strings | iOS Settings → CalorieClick → or first-time prompts |

If any of these are missing or wrong in the build, fix before submission.
