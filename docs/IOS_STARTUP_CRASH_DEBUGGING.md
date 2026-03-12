# iOS Startup Crash Debugging (TestFlight)

## Crash signature (current)
- Crash type: `EXC_CRASH` / `SIGABRT` / `Abort trap: 6`
- Queue: `com.facebook.react.ExceptionsManagerQueue`
- `abort() called`
- Repeated app image offsets across builds 128/129:
  - `1753540`
  - `2214116`
  - `2216736`

This usually means an uncaught JS/native bridge exception escalated to RN fatal handling.

## Required workflow: symbolicate first
Do not guess from raw offsets. Symbolicate with matching archive + dSYMs.

### 1) Open Xcode Organizer
1. Open Xcode.
2. `Window` -> `Organizer`.
3. Select your app (`CalorieClickAI`).
4. Go to `Crashes`.

### 2) Match crash to build
Use:
- App version
- Build number
- Incident timestamp
- Device + iOS version

For this issue, compare build `128` and `129` startup crashes.

### 3) Ensure symbols exist
- Confirm matching app archive exists in Organizer `Archives`.
- Confirm corresponding dSYMs are downloaded/available.
- If symbols are missing, re-download symbols from App Store Connect / Xcode.

### 4) Read symbolicated frames
Focus on:
- First app frame on `ExceptionsManagerQueue`
- App frames around repeated offsets
- Any bridge callback / notification / deep-link / startup hydration path

### 5) Map symbolicated method back to source
Map to code paths in:
- `mobile/App.js` startup effects
- `mobile/pushNotifications.js`
- `mobile/deepLinkRouter.js`
- `mobile/smartAlertState.js`
- `mobile/components/AdminOpsDashboard.js`

## Startup mitigation now in code
Current launch hardening includes:
- Launch-phase tracing (`boot_start`, hydration start/end, notification parse/open, startup complete)
- Global JS error context logging with phase + active screen
- Defensive parse helpers:
  - `safeParseJson`
  - `safeArray`
  - `safeObject`
  - `safeGetSmartAlertPayload`
  - `safeGetOpsDashboardSummary`
- Notification open/receive handlers wrapped in try/catch
- Malformed startup payload fallback to safe nearby/home flow
- Error boundary at app root (`mobile/errorBoundary.js`)

## Quick triage checklist for next crash
1. Confirm build number + app version in crash.
2. Symbolicate in Organizer.
3. Identify first symbolicated app frame.
4. Check launch trace logs around the same run:
   - `[LaunchTrace:app_launch] ...`
   - `[GlobalError] ...`
5. Reproduce with malformed payload tests before shipping.

## Validation scenarios
Run these before release:
- malformed notification payload (missing ids/coords/metadata)
- malformed deep-link URL params
- corrupted AsyncStorage JSON values for startup keys
- partial admin dashboard payload
- app launch with no network + stale cache

## Notes
- Repeated offsets across builds strongly suggest same uncaught startup code path.
- Shipping additional features should be paused until symbolicated frame confirms root cause is closed.

## Clean release steps (avoid ITMS-90189)
1. Keep app version at `1.0.6` unless marketing release requires version bump.
2. Ensure iOS production profile uses `autoIncrement: "buildNumber"` in `/Users/priyankraghuvanshi/projects/kcal-photo-app/mobile/eas.json`.
3. Build and auto-submit from `/Users/priyankraghuvanshi/projects/kcal-photo-app/mobile`:
   - `npx eas-cli build --platform ios --profile production_auto_submit --auto-submit --non-interactive`
4. Confirm new build number is greater than previous uploaded build (for example, after `131`, next must be `132+`).
5. In App Store Connect TestFlight, validate startup on cold launch before wider rollout.
