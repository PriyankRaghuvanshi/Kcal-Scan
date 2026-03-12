# Expo Push Delivery for Smart Food Alerts

This doc describes the backend push sending pipeline for Smart Food Alerts.

## Overview

The backend can send eligible Smart Food Alerts as real Expo push notifications. The pipeline:

1. Fetches eligible candidates (same logic as `/smart-food-alerts/candidates`)
2. Selects the top 1 candidate per user (conservative rollout)
3. Maps to active Expo push tokens
4. Builds and sends push messages to Expo Push API
5. Logs deliveries and tickets
6. Fetches receipts later; deactivates invalid tokens

## Send Flow

1. **POST /push/send-smart-alerts** with:
   - `user_id`, `lat`, `lng` (required)
   - `eligible_only` (default true)
   - `dry_run` (default true for safety)
   - `context`: remaining_calories, remaining_protein_g, local_hour, post_workout, late_night, etc.
   - `fatigue`: recent_alerts_count_6h, recent_alerts_count_24h, weekly_alert_count, ignored_streak, etc.

2. Backend:
   - Calls `healthy_places` to get ranked nearby places
   - Builds candidates via `build_smart_food_alert_candidates`
   - Filters by `eligible_to_send` and confidence
   - **Fallback send logic**: Iterates ranked eligible candidates. If #1 is suppressed (duplicate_recently_sent for all tokens), tries #2, then #3, etc. Sends at most one total.
   - Gets active tokens via `list_tokens_for_user`
   - Skips tokens that recently received same alert (6h dedupe)
   - Creates delivery records
   - Sends to Expo (or simulated if dry_run)

3. Response: candidates_considered, eligible_count, candidates_skipped_as_duplicate, candidate_sent_rank, notifications_attempted, tickets_received, final_suppressed_reason (when none sent), dry_run

## Dry-Run Mode

- **dry_run=true**: No real HTTP call to Expo. Simulated tickets returned. Delivery records created with status `dry_run`.
- **dry_run=false**: Real send. Requires `EXPO_PUSH_SENDING_ENABLED=true` (env).
- Dry-run works even when `EXPO_PUSH_SENDING_ENABLED` is false.

## Receipt Check Flow

1. **POST /push/check-receipts** with `ticket_ids` (from send response)
2. Backend calls `https://exp.host/--/api/v2/push/getReceipts`
3. Updates delivery records: `receipt_ok` or `receipt_error`
4. If receipt error is `DeviceNotRegistered`:
   - Marks delivery as `token_deactivated`
   - Deactivates token in push_token_store
5. **POST /push/check-pending-receipts**: Automatically looks up pending tickets from delivery store

## Invalid Token Handling

- `DeviceNotRegistered` in receipts → token deactivated
- Token no longer returned by `list_tokens_for_user(active_only=True)`
- Audit trail in delivery store (status `token_deactivated`)

## Rollout and Staged Release

See **PUSH_ROLLOUT.md** for staged rollout modes (allowlist_only, active_users_only, percentage, all), active-user eligibility, frequency guardrails, and recommended production progression.

Quick reference:
- `EXPO_PUSH_SENDING_ENABLED=true` – master switch
- `PUSH_REAL_SEND_MODE` – allowlist_only (default when enabled), active_users_only, percentage, all
- `GET /push/rollout/status` – config and observability

## Batching

- Messages batched in chunks of 50
- Expo allows up to 100 per request
- Receipt lookup: up to 1000 IDs per request

## Batch Smart Alert Sending

See **PUSH_BATCH_SENDING.md** for:
- `POST /push/send-smart-alerts/batch` – scheduler-friendly batch send
- `GET /push/send-smart-alerts/batch/status` – config and eligible-user estimate
- User location storage for batch (from `/places/healthy` and `/push/send-smart-alerts`)

## Push payload deep-link fields

Every push message `data` object includes deep-link fields so the mobile app can route the user to the exact recommendation when they tap:

| Field | Type | Description |
|-------|------|-------------|
| `alert_id` | string | Stable ID: `{alert_type}::{place_id}::{best_item_name}` |
| `alert_type` | string | protein_rescue, post_workout_recovery, etc. |
| `place_id` | string | Google Place ID |
| `place_name` | string | Display name, e.g. "Subway" |
| `best_item_name` | string | Top recommended item |
| `place_lat` | number | Place latitude (required for direct place opening) |
| `place_lng` | number | Place longitude |
| `display_rank_score_100` | number | Display score |
| `context_mode` | string | default, late_night, etc. |
| `deep_link` | string | `calorieclick://smart-alert?alert_id=...&place_id=...&place_name=...&best_item_name=...&place_lat=...&place_lng=...` |
| `route_target` | string | `smart_alert_place` (coords present), `smart_alert_inbox` (place_id only), or `smart_alert_nearby` |

Mobile routing: if `place_id` + `place_lat` + `place_lng` are present, the app opens Healthy Nearby with that place pre-selected. Otherwise it opens the Smart Alert inbox. See `mobile/docs/SMART_ALERTS.md` for details.

## Key Files

- `backend/expo_push_service.py` – message build, send, receipts, deep-link payload
- `backend/push_delivery_store.py` – delivery logging
- `backend/push_token_store.py` – token registry, deactivation
- `backend/main.py` – `/push/send-smart-alerts`, `/push/check-receipts`, `/push/check-pending-receipts`
