# Smart Food Alerts – Mobile Integration

This doc describes how Smart Food Alerts work on mobile: fetching, display filtering, local suppression, and future push integration.

## Overview

Smart Food Alerts surface high-value nearby food options when they fit the user's goals (e.g., protein rescue, post-workout, late-night damage control). The mobile layer:

1. Fetches candidates from the backend
2. Applies local user settings and suppression
3. Displays alerts in-app via preview card and inbox
4. Tracks open/dismiss for UX and future analytics

## How Alerts Are Fetched

- **API**: `GET /smart-food-alerts/candidates` via `smartAlertsApi.js`
- **Params**: `lat`, `lng`, `user_id`, `local_hour`, `remaining_calories`, `remaining_protein_g`, `goal`, `ignored_streak`, etc.
- **Fetch points**:
  - After Healthy Nearby loads (when coords are available)
  - App returning to foreground (if coords + userId + enabled)
  - Pull-to-refresh in Smart Alert Inbox
- **Cooldown**: ~5 minutes between fetches to avoid over-polling

## How Category Settings Work

Stored in `smartAlertState` (AsyncStorage):

- **Master toggle** (`enabled`): Master on/off for Smart Alerts
- **Categories**: Per-type toggles (protein_rescue, post_workout_recovery, late_night_damage_control, worked_before_repeat, habit_rescue)
- **Frequency**: `smart_only` (recommended), `normal`, `low`

Local filtering is applied **after** the backend response: if a category is off, that alert type is not shown even if the backend returned it.

## Local Suppression / Deduplication

The mobile layer adds a local anti-spam layer on top of backend eligibility:

1. **Dismissed alerts**: Once dismissed, an alert is not shown again (by ID)
2. **Venue suppression**: After open or dismiss, that venue is suppressed locally for ~4 hours
3. **Same-alert dedupe**: Recently opened alerts are not re-shown within ~1 hour
4. **Frequency mode "low"**: Extra cooldown after dismissal (~2h) before showing more alerts
5. **Deterministic IDs**: `alert_type::place_id::best_item_name` (matches backend; no date for push/inbox consistency)

## Backend vs Mobile

| Layer            | Responsibility                          |
|------------------|------------------------------------------|
| Backend          | Eligibility scoring, anti-spam, candidate selection |
| Mobile fetch     | Calling API with context params          |
| Mobile filtering | User settings, local suppression, dedupe |
| Future push      | Delivery channel; backend decides *what* to send, mobile controls *how much* |

## Push Permission Flow

1. When Smart Alerts are **enabled** and user is signed in:
   - App checks current notification permission status
   - If granted: fetches Expo push token and registers with backend
   - If not granted: user can tap "Enable" in Smart Alert Settings to request permission
   - If permission denied: user can tap "Open settings" to go to system settings
2. Permission is requested only when appropriate (Smart Alerts on, user logged in)
3. Same session: we avoid repeatedly prompting if user already declined

## Token Registration Lifecycle

- **Register**: When Smart Alerts enabled + permission granted, `POST /push/register` with `user_id`, `expo_push_token`, `platform`
- **Unregister**: When Smart Alerts disabled or user logs out, `POST /push/unregister`
- **Persistence**: Token stored in backend `push_token_store`; local state in AsyncStorage (`kcal_push_registration_v1`)
- **Dedupe**: Backend updates existing token if same user+token re-registers

## Notification Open Tracking

When user taps a push notification:

1. `addNotificationResponseReceivedListener` fires
2. `handleNotificationOpen` parses payload (alert_id, place_id, alert_type, etc.)
3. Calls `recordAlertOpened(alertId, placeId)` for local suppression
4. Optionally POSTs `recommendation_opened` to `/meal-decision-event` for backend analytics
5. App navigates to the **exact recommendation/place** when possible (deep-link routing)

## Push Deep-Link Routing

Push payload `data` includes deep-link fields so tapping a notification opens the relevant screen directly.

### Expected deep-link payload shape

| Field | Type | Description |
|-------|------|-------------|
| `alert_id` | string | Stable ID, e.g. `protein_rescue::ChIJ123::6-inch Grilled Chicken` |
| `alert_type` | string | protein_rescue, post_workout_recovery, etc. |
| `place_id` | string | Google Place ID |
| `place_name` | string | e.g. "Subway" |
| `best_item_name` | string | Recommended item |
| `place_lat` | number | Place latitude (for place lookup) |
| `place_lng` | number | Place longitude |
| `display_rank_score_100` | number | Display score |
| `context_mode` | string | default, late_night, etc. |
| `confidence_label` | string | Trust: Verified, Estimated, Needs menu check |
| `recommendation_label` | string | Best pick, Strong option, etc. |
| `chosen_candidate_specificity_tier` | string | Internal tier (used for trust mapping) |
| `menu_item_source` | string | real_menu, chain_registry, heuristic, etc. |
| `matched_local_profile` | boolean | Whether enriched local profile matched |
| `local_profile_source` | string | curated_manual, etc. |
| `used_venue_intelligence_cache` | boolean | Whether cache was used |
| `best_item_is_generic_fallback` | boolean | Whether item is generic heuristic |
| `deep_link` | string | `calorieclick://smart-alert?alert_id=...&place_id=...&place_name=...&best_item_name=...&place_lat=...&place_lng=...` |
| `route_target` | string | `smart_alert_place` (exact place with coords), `smart_alert_inbox` (fallback), or `smart_alert_nearby` |

### Push tap routing behavior

- **open_place**: place_id + place_lat/lng present → open exact place, load nearby with preferredCard
- **open_inbox**: place_id but no coords → open inbox (fallback when local alert may be missing)
- **open_nearby**: no place_id → open Healthy Nearby

| Condition | Behavior |
|-----------|----------|
| `place_id` + `place_lat` + `place_lng` present | **open_place**: Healthy Nearby with place pre-selected (or best match) |
| `place_id` but no coords | **open_inbox**: Smart Alert inbox (highlighted if alert_id matches) |
| No `place_id` | **open_nearby**: Healthy Nearby list |

### Fallback navigation

- **A.** Exact alert/place in inbox or local state → open that Smart Alert / place detail
- **B.** Place not in local state → fetch nearby candidates, try to resolve `place_id`, open match if found
- **C.** Final fallback → Smart Alerts inbox with tapped alert highlighted, or Healthy Nearby

### Key files

- `mobile/deepLinkRouter.js` — `parseSmartAlertDeepLink()`, `resolveSmartAlertNavigationTarget()`
- `mobile/pushNotifications.js` — `parseSmartAlertNotificationData()`, `handleNotificationOpen()`
- `mobile/App.js` — `onNotificationResponse`, `openPlaceFromSmartAlert()`

## Trust Labels and Recommendation Quality

Smart Alerts communicate how trustworthy each recommendation is via user-facing trust labels. The same mapping is used for push, inbox, map, and list surfaces so the same place/alert does not appear "Verified" in one surface and "Needs menu check" in another.

### Trust label mapping

| User-facing label | When used |
|-------------------|-----------|
| **Verified** | exact/cache, real_menu, user_scan, or very strong trusted source |
| **Chain-backed** | ingested chain item or strong chain registry item |
| **Local favorite** | enriched/confirmed local venue profile |
| **Estimated** | strong heuristic, reasonable inference, Best pick / Strong option |
| **Needs menu check** | weak/generic fallback or low-confidence inference |

Internal signals (e.g. `exact_menu_match`, `ingested_chain_item`, `heuristic_cuisine_match_strong`) are **not** shown directly to users. They are mapped to the labels above.

### Hero language rules

Title and hero language align with trust level:

| Trust | Example hero/title |
|-------|--------------------|
| Strong (Verified, Chain-backed, Local favorite) | "Best nearby right now" |
| Moderate (Estimated) | "Good nearby option" |
| Weak (Needs menu check) | "Suggested nearby option", "Check menu before ordering" |

Weak alerts must never use strong hero language such as "Best nearby fit right now".

### When "Menu may vary" appears

The caution note "Menu may vary" is shown only for alerts mapped to **Needs menu check**. It is not shown for Verified, Chain-backed, Local favorite, or Estimated.

### Consistency expectations

- **Push → Inbox**: When a push is tapped and the user lands in the inbox, the alert card shows the same trust label as the push metadata.
- **Push → Place**: When a push opens the exact place on the map/list, the place card uses the same trust logic (from API or push payload).
- **Inbox vs API**: Inbox candidates from the API include trust fields; foreground-received push candidates merge trust metadata from the push payload.

### Implementation

- `mobile/smartAlertTrustLabels.js` — canonical mapping, `getAlertTrustLabel()`, `getAlertTrustTone()`, `shouldShowMenuMayVary()`, `getEffectiveAlertTitle()`
- `mobile/components/ConfidenceBadge.js` — uses smartAlertTrustLabels for consistent tier/label
- `mobile/components/SmartAlertCard.js` — trust badge, softer styling for weak alerts, "Menu may vary"
- `mobile/components/RecommendationCard.js` — uses `shouldShowMenuMayVary()` for consistency

## Foreground Handling

When a notification arrives while app is open:

- Notification is shown via system (if not suppressed)
- Payload is merged into Smart Alert inbox state if it maps to an alert candidate
- No auto-open or duplicate UI spam

## Backend Push Pipeline

The backend can send eligible Smart Food Alerts as real Expo push notifications:

- **POST /push/send-smart-alerts** – Sends top 1 eligible candidate per user; supports `dry_run`
- **POST /push/check-receipts** – Fetches receipts, deactivates invalid tokens
- **POST /push/check-pending-receipts** – Auto-checks pending tickets
- See `backend/docs/EXPO_PUSH_DELIVERY.md` for full flow, dry-run behavior, rollout recommendations

## Key Files

- `mobile/smartAlertsApi.js` – API client
- `mobile/smartAlertState.js` – Settings, suppression, dedupe logic
- `mobile/pushNotifications.js` – Permission, token, registration, listeners
- `mobile/deepLinkRouter.js` – Parse push payload, resolve navigation target for push tap
- `mobile/components/SmartAlertCard.js` – Single alert card UI (trust badge, hero language)
- `mobile/components/SmartAlertInbox.js` – List of alerts
- `mobile/smartAlertTrustLabels.js` – Trust label mapping and helpers
- `mobile/components/SmartAlertSettings.js` – Settings UI (includes push status)
- `mobile/App.js` – Entry point, fetch triggers, modals, push lifecycle, deep-link routing
