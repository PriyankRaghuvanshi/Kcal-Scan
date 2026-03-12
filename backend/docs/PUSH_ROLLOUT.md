# Push Rollout – Staged iOS Release Path

Staged rollout controls for Smart Food Alerts push, from allowlist testing to production.

## Rollout Modes

| Mode | Description |
|------|-------------|
| `disabled` | No real sends (default when EXPO_PUSH_SENDING_ENABLED=false) |
| `allowlist_only` | Only users in PUSH_TEST_USER_IDS receive real pushes |
| `active_users_only` | Only users active within PUSH_ACTIVE_USER_DAYS |
| `percentage` | Deterministic N% of users (PUSH_ROLLOUT_PERCENT) |
| `all` | All users with token and passing fatigue checks |

**Default:** When `EXPO_PUSH_SENDING_ENABLED=true` but `PUSH_REAL_SEND_MODE` is unset, defaults to `allowlist_only`.

## Env Vars

| Var | Default | Description |
|-----|---------|-------------|
| `EXPO_PUSH_SENDING_ENABLED` | false | Master switch for real push sends |
| `PUSH_REAL_SEND_MODE` | allowlist_only (if enabled) | disabled, allowlist_only, active_users_only, percentage, all |
| `PUSH_TEST_USER_IDS` | "" | Comma-separated user IDs for allowlist |
| `PUSH_ROLLOUT_PERCENT` | 0 | 0–100 for percentage mode |
| `PUSH_ACTIVE_USER_DAYS` | 7 | Days within which user must have activity |
| `PUSH_MAX_PER_6H` | 1 | Max pushes per user per 6 hours |
| `PUSH_MAX_PER_24H` | 2 | Max pushes per user per 24 hours |

## Active-User Rule

A user is "active" if any of:

- **meal_decision_events**: Any event (recommendation_opened, recommendation_viewed, place_opened, etc.) in last `PUSH_ACTIVE_USER_DAYS`
- **push_token_store**: Token `last_seen_at` or `updated_at` within last `PUSH_ACTIVE_USER_DAYS`

If neither signal exists, user is treated as inactive (conservative).

In `active_users_only` mode, user must also:

- Have at least one active registered push token
- Pass fatigue checks (PUSH_MAX_PER_6H, PUSH_MAX_PER_24H)

## Percentage Rollout

Deterministic hashing: `sha256(user_id)` → bucket 0–99.

- `PUSH_ROLLOUT_PERCENT=10` → buckets 0–9 eligible
- Same user always in same bucket; consistent across requests

## Frequency Guardrails

- **PUSH_MAX_PER_6H**: Max real pushes per user in rolling 6h window
- **PUSH_MAX_PER_24H**: Max real pushes per user in rolling 24h window
- In addition to existing: `duplicate_recently_sent` (same alert to same token in 6h)
- Suppression reasons: `fatigue_limit_6h`, `fatigue_limit_24h`, `duplicate_recently_sent`, `no_tokens`

## Dry-Run

- `dry_run=true` **always** allowed
- Bypasses rollout mode, push_disabled, fatigue
- No real HTTP call to Expo; simulated tickets

## Response Fields

`POST /push/send-smart-alerts` returns:

- `real_send_allowed`: Whether real send was allowed
- `real_send_reason`: allowed_allowlist, allowlist_blocked, inactive_user, percentage_blocked, dry_run, etc.
- `rollout_mode`: Current mode
- `user_active_eligible`: Whether user passed active check
- `percentage_bucket`: 0–99 (if applicable)
- `percentage_allowed`: Whether user in rollout percent (if applicable)

## Observability

`GET /push/rollout/status` returns:

- `sending_enabled`, `rollout_mode`, `rollout_percent`, `active_user_days`, `max_per_6h`, `max_per_24h`
- `allowlist_count`
- `recent_sent_count`, `recent_receipt_ok_count`, `recent_receipt_error_count` (from delivery store)

## Recommended Production Rollout Order

1. **allowlist_only** – Internal testers
2. **active_users_only** – Engaged users who opened app recently
3. **percentage** 5% – Small production cohort
4. **percentage** 10% – Expand
5. **percentage** 25% – Broader
6. **all** – Full production

## Example Env for Final iOS Release

```
EXPO_PUSH_SENDING_ENABLED=true
PUSH_REAL_SEND_MODE=percentage
PUSH_ROLLOUT_PERCENT=10
PUSH_ACTIVE_USER_DAYS=7
PUSH_MAX_PER_6H=1
PUSH_MAX_PER_24H=2
PUSH_TEST_USER_IDS=internal1,internal2
```

## Batch Sending

See **PUSH_BATCH_SENDING.md** for batch Smart Alert sending, scheduler usage, and `POST /push/send-smart-alerts/batch`.

## Key Files

- `backend/push_rollout.py` – can_send_real_push, get_user_push_eligibility, is_user_in_rollout_percentage
- `backend/main.py` – /push/send-smart-alerts, /push/rollout/status, /push/send-smart-alerts/batch
