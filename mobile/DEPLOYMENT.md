# Mobile deployment — always ship the latest JS bundle

If TestFlight / App Store shows **old login UI** or **old screens**, the device is almost always running an **older native binary** or an **EAS-cached** JS bundle. Follow this checklist.

## 1. Confirm entry point (this repo)

- Root component: `mobile/index.js` → `import App from './App'` → **`mobile/App.js`**.
- Run **only** from the `mobile` folder: `cd mobile && npx expo start`.

## 2. Local dev: clear Metro cache

```bash
cd mobile
npx expo start -c
```

Uninstall the app from the simulator/device and reinstall if the UI still looks stale.

## 3. Production iOS (EAS): force a fresh JS bundle

EAS may reuse cached layers. After **meaningful JS changes**:

1. Bump **`app.json`** → `"version"` (e.g. `1.0.8` → `1.0.9`).
2. Bump **`eas.json`** → `build.production.cache.key` (e.g. `production-v5-…` → new suffix) **or** pass **`--clear-cache`** once.
3. Use the **fresh** build command:

```bash
cd mobile
npm run ios:build:production:fresh
```

4. Install the **new** build from TestFlight. **Old builds keep old JS** until you upgrade.

## 4. Verify you got the new bundle

On the **login** screen, check the gray line at the bottom:

- **`Build 1.0.8 · <number>`** — `1.0.8` comes from `app.json`; the second token is the **native build** from the store binary.

If that line is **missing** or shows an **older version**, you are not on the latest submitted build.

## 5. Common mistakes

| Symptom | Cause |
|--------|--------|
| Old UI after “deploy” | Opened **old TestFlight build**; install latest build number. |
| Changes in Git but not on phone | **No new EAS build** submitted; App Store does not pull from Git by itself. |
| Expo Go looks wrong | **Expo Go** bundles differently; use **development** or **production** dev client / store build for parity. |
| Two apps on device | Wrong icon (duplicate bundle); remove old installs. |

## 6. Backend / API

JS changes to **API URL** still require a **new native build** if you changed native config; `EXPO_PUBLIC_*` env for EAS is baked at **build** time in `eas.json` → `env`.

## 7. One-command latest TestFlight flow

```bash
cd mobile
git rev-parse --short HEAD
npm run ios:release:fresh
```

- First command prints the exact commit you are shipping.
- `ios:release:fresh` always builds with `--clear-cache` and auto-submits, avoiding stale cached bundles.
