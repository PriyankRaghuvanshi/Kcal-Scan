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
   - Takes **top 1** only (initial conservative rule)
   - Gets active tokens via `list_tokens_for_user`
   - Skips tokens that recently received same alert (6h dedupe)
   - Creates delivery records
   - Sends to Expo (or simulated if dry_run)

3. Response: candidates_considered, eligible_count, notifications_attempted, tickets_received, dry_run

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

## Rollout Recommendations

1. **Dev/staging**: `dry_run=true` only
2. **Prod**: Set `EXPO_PUSH_SENDING_ENABLED=true` only when ready
3. **Internal users**: Enable for selected user IDs first
4. **Top 1 per run**: Currently enforced; can relax later

## Batching

- Messages batched in chunks of 50
- Expo allows up to 100 per request
- Receipt lookup: up to 1000 IDs per request

## Key Files

- `backend/expo_push_service.py` – message build, send, receipts
- `backend/push_delivery_store.py` – delivery logging
- `backend/push_token_store.py` – token registry, deactivation
- `backend/main.py` – `/push/send-smart-alerts`, `/push/check-receipts`, `/push/check-pending-receipts`
