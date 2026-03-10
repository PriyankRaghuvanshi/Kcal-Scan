# Push Token Registration

Backend endpoints for Expo push token registration, used by Smart Food Alerts push notifications.

For actual push sending, receipts, and delivery logging, see **EXPO_PUSH_DELIVERY.md**.

## Endpoints

### POST /push/register

Register or update an Expo push token for a user.

**Payload:**
```json
{
  "user_id": "u123",
  "expo_push_token": "ExponentPushToken[...]",
  "platform": "ios",
  "device_name": "iPhone 14",
  "app_version": "1.0.3"
}
```

**Required:** `user_id`, `expo_push_token` (must start with `ExponentPushToken[`)

**Behavior:** Dedupes by user_id + expo_push_token. Updates existing record if already registered.

### POST /push/unregister

Mark a token inactive.

**Payload:**
```json
{
  "user_id": "u123",
  "expo_push_token": "ExponentPushToken[...]"
}
```

**Required:** `user_id`, `expo_push_token`

## Stored Token Shape

- `user_id`
- `expo_push_token`
- `platform` (ios | android)
- `device_name`
- `app_version`
- `active`
- `created_at`
- `updated_at`
- `last_seen_at`

## Store

- **File:** `backend/data/push_token_store.json` (or `PUSH_TOKEN_STORE_PATH` env override)
- **Module:** `push_token_store.py`
- **List tokens:** `list_tokens_for_user(user_id, active_only=True)` for future push sending
