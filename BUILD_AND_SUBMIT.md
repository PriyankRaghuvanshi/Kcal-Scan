# CalorieClick AI — Build & Submit Checklist

> Instructions for Codex (or any CI agent) to build and submit the app.
> Human review steps are marked with 👤.

---

## 0. Prerequisites (one-time, already done)

- [x] EAS CLI installed (`npm i -g eas-cli@latest`)
- [x] Logged in to Expo (`eas whoami`)
- [x] Apple credentials configured in EAS (signing cert + provisioning)
- [x] Google Play service account JSON at `mobile/credentials/google-play-service-account.json` (git-ignored)
- [x] RevenueCat iOS key in `app.json` → `extra.REVENUECAT_IOS_API_KEY`
- [x] RevenueCat Android key in `eas.json` → `EXPO_PUBLIC_RC_ANDROID_KEY`
- [x] Supabase anon key in `eas.json` → `EXPO_PUBLIC_SUPABASE_ANON_KEY`
- [x] App Store Connect `ascAppId` in `eas.json` → `6757768893`

---

## 1. Pre-build sanity checks

Run all of these **before** starting a build. Fix any failures first.

```bash
cd mobile

# 1a. Syntax check — catches missing brackets, bad JSX, etc.
node --check App.js

# 1b. Dependency install — clean slate
rm -rf node_modules && npm install

# 1c. Expo doctor — catches SDK mismatches and plugin issues
npx expo-doctor@latest

# 1d. Quick unit tests (if any)
npm test -- --passWithNoTests
```

### What to verify

| Check | Pass criteria |
|-------|---------------|
| `node --check App.js` | Exit code 0, no output |
| `npm install` | No `npm ERR!` lines |
| `npx expo-doctor` | No errors (warnings about unused deps are OK) |
| `npm test` | All tests pass or no tests found |

---

## 2. Bump version

The **build number** (`ios.buildNumber` / `android.versionCode`) auto-increments
via `"autoIncrement": true` in `eas.json`, so **do not** touch those.

Only bump the **user-facing version** when shipping new features:

```bash
# Example: 1.0.11 → 1.0.12
# Edit mobile/app.json → expo.version
```

> 👤 **Human decides** whether this is a patch, minor, or major bump.

---

## 3. Build — iOS

```bash
cd mobile

# Standard production build (uses EAS cache)
npm run ios:build:production

# OR fresh build (clears native cache — use after SDK upgrades or plugin changes)
npm run ios:build:production:fresh
```

**What these run:**

```
eas build --platform ios --profile production --non-interactive
```

### Monitor the build

```bash
eas build:list --platform ios --limit 3
# or open the URL printed after build starts
```

| Status | Action |
|--------|--------|
| `FINISHED` | Proceed to submit |
| `ERRORED` | Read build logs → fix → rebuild |
| `CANCELLED` | Re-trigger |

---

## 4. Build — Android

```bash
cd mobile
npm run android:build:production
```

### Monitor

```bash
eas build:list --platform android --limit 3
```

---

## 5. Submit — iOS (to App Store Connect / TestFlight)

### Option A: Auto-submit (build + submit in one step)

```bash
cd mobile
npm run ios:release
# or fresh:
npm run ios:release:fresh
```

This uses the `production_auto_submit` profile which triggers `--auto-submit`.

### Option B: Submit an existing build

```bash
cd mobile
npm run ios:submit:production
# submits the latest successful iOS production build
```

### What happens next

1. Binary uploads to App Store Connect.
2. Apple processes it (5–15 min).
3. It appears in **TestFlight** → ready for internal testing.
4. 👤 **Human submits for App Review** from App Store Connect when ready.

---

## 6. Submit — Android (to Google Play internal track)

```bash
cd mobile
npm run android:submit:production
```

This uploads to the **internal** track as a **draft**.

> 👤 **Human promotes** from internal → closed testing → production in Google Play Console.

---

## 7. Post-submit verification

### iOS (TestFlight)

- [ ] Open TestFlight on a physical device
- [ ] Cold launch — app loads without crash
- [ ] Sign in → daily summary strip shows correct data (or "Log a meal…")
- [ ] Scan a meal photo → result appears
- [ ] Coach tab loads
- [ ] Healthy Nearby loads with location
- [ ] Check subscription paywall opens
- [ ] Check Apple Health sync (if enabled)

### Android (internal track)

- [ ] Install from Play Console internal link
- [ ] Same checks as above (minus Apple Health)

---

## 8. One-liner: full iOS release

If everything is verified and you want build + submit in a single command:

```bash
cd mobile && npm run ios:release
```

---

## Quick reference: all npm scripts

| Script | What it does |
|--------|-------------|
| `ios:build:production` | EAS build iOS (cached) |
| `ios:build:production:fresh` | EAS build iOS (no cache) |
| `ios:submit:production` | Submit latest iOS build to ASC |
| `ios:release` | Build + auto-submit iOS |
| `ios:release:fresh` | Build (no cache) + auto-submit iOS |
| `android:build:production` | EAS build Android |
| `android:submit:production` | Submit latest Android build to Play |
| `android:release` | Build + submit Android |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Xcode must be installed` | EAS Cloud builds don't need local Xcode. If building locally, install Xcode 16+. |
| `Missing provisioning profile` | Run `eas credentials` → select iOS → let EAS manage. |
| `Build fails on native module` | Try `--clear-cache` (fresh build). Check plugin versions match Expo SDK. |
| `Submit fails: "No matching build"` | Ensure latest build status is `FINISHED`: `eas build:list --platform ios --limit 1` |
| `Submit fails: ASC auth` | Re-run `eas credentials` or set `EXPO_APPLE_APP_SPECIFIC_PASSWORD`. |
| `Google Play: "APK not signed"` | Ensure `serviceAccountKeyPath` points to valid JSON and has correct permissions. |
| `App crashes on launch` | Check for null-safety issues in `App.js` (the `num()` + `Number.isFinite` pattern). |

---

## Codex-specific instructions

When Codex is asked to "build and submit":

1. **Always run pre-build checks first** (Section 1). Do not skip.
2. **Never modify** `eas.json` credentials, API keys, or `ascAppId` unless explicitly asked.
3. **Never commit** `credentials/`, `.env*.local`, or any file containing secrets.
4. **Bump `app.json` version** only if the human confirms a version bump.
5. **Use `--non-interactive`** on all EAS commands (already set in npm scripts).
6. **Monitor builds** by polling `eas build:list` — do not assume success.
7. **If a build fails**, read the build logs (`eas build:view`), fix the issue, and rebuild.
8. **After submit**, remind the human to check TestFlight / Play Console.
9. **Cache key** in `eas.json` should be updated when native dependencies change
   (e.g., new Expo SDK, new native plugin). Format: `production-v{N}-{YYYYMMDD}-{description}`.
10. **Do not run** `expo prebuild` unless specifically asked — EAS Cloud handles it.
