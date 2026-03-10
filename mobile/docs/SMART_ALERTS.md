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
5. **Deterministic IDs**: `alert_type::place_id::best_item_name::date` for stable deduplication

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
5. App can navigate to Healthy Nearby (future deep_link support)

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
- `mobile/components/SmartAlertCard.js` – Single alert card UI
- `mobile/components/SmartAlertInbox.js` – List of alerts
- `mobile/components/SmartAlertSettings.js` – Settings UI (includes push status)
- `mobile/App.js` – Entry point, fetch triggers, modals, push lifecycle
