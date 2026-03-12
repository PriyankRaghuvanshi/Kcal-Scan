# Push Batch Sending – Smart Alert Batch Orchestration

Batch scheduled Smart Alert sending for all eligible users. Scheduler-friendly, production-safe.

## Purpose

- Find eligible users with active push tokens **and** stored last-known location
- Apply rollout rules (allowlist / active_users_only / percentage / all)
- Send at most one alert per user per batch run
- Respect fatigue limits and duplicate suppression
- Provide observable, production-debuggable batch results

## Endpoints

### `POST /push/send-smart-alerts/batch`

Trigger batch Smart Alert send.

**Body:**
```json
{
  "limit_users": 200,
  "dry_run": true
}
```

| Field        | Default | Description                                              |
|-------------|---------|----------------------------------------------------------|
| `limit_users` | 500 (env) | Max users to consider (1–2000). Uses `PUSH_BATCH_USER_LIMIT` if not provided. |
| `dry_run`     | **true**  | **Requires explicit `dry_run: false` for real sends.**   |

**Response:** Batch summary with counts and sample results.

### `GET /push/send-smart-alerts/batch/status`

Config/health summary for batch sending: rollout mode, user limits, eligible user estimate.

## Eligibility Logic

A user is batch-eligible only if:

1. Has at least one active push token
2. Has stored last-known location (from `/places/healthy` or `/push/send-smart-alerts` with `user_id`)
3. Passes rollout mode (allowlist / active_users_only / percentage / all)
4. Passes fatigue checks (PUSH_MAX_PER_6H, PUSH_MAX_PER_24H)
5. Not globally suppressed (push_disabled, rollout_disabled)

## User Location Storage

Location is stored when:

- User calls `GET /places/healthy` with `user_id` in query
- User calls `POST /push/send-smart-alerts` (includes `user_id`, `lat`, `lng`)

Mobile app should pass `user_id` when fetching nearby places so batch can use their last location.

## Config (Env)

| Var                          | Default | Description                         |
|------------------------------|---------|-------------------------------------|
| `PUSH_BATCH_USER_LIMIT`      | 500     | Max users per batch (1–2000)        |
| `PUSH_BATCH_SAMPLE_RESULTS_LIMIT` | 25 | Sample results in batch summary (0–200) |

## Batch Result Shape

```json
{
  "ok": true,
  "dry_run": false,
  "users_considered": 120,
  "users_eligible": 80,
  "users_skipped": 40,
  "alerts_sent": 22,
  "alerts_suppressed": 58,
  "receipt_candidates": 22,
  "skip_reasons": {
    "no_location": 15,
    "inactive_user": 20,
    "allowlist_blocked": 0,
    "percentage_blocked": 5,
    "duplicate_recently_sent": 0,
    "fatigue_limit_24h": 0
  },
  "sample_results": [
    {
      "user_id": "uuid",
      "sent": true,
      "skipped": false,
      "real_send_reason": "allowed_active_user",
      "candidate_sent_rank": 1,
      "alert_type": "protein_rescue",
      "place_name": "Subway"
    }
  ],
  "rollout_mode": "active_users_only"
}
```

## Scheduler Usage

Intended to be triggered by:

- **Railway** scheduled job (cron)
- **GitHub Actions** cron
- External scheduler (cron, Cloud Scheduler, etc.)
- Internal worker (future)

### Recommended Railway / Cron Config

| Setting | Value |
|---------|-------|
| Schedule | Every 30 minutes (`0 */30 * * *` or `*/30 * * * *`) |
| HTTP method | POST |
| URL | `https://<your-app>.railway.app/push/send-smart-alerts/batch` |
| Body | `{"limit_users": 500, "dry_run": false}` |
| Headers | `Content-Type: application/json` |

**Important:** Use `dry_run: true` initially to validate; switch to `dry_run: false` only after confirming rollout settings.

**Example request:**
```bash
curl -X POST https://your-api.railway.app/push/send-smart-alerts/batch \
  -H "Content-Type: application/json" \
  -d '{"limit_users": 500, "dry_run": false}'
```

## Recommended Production Config

- **Cadence:** every 30 minutes
- **Rollout:** `active_users_only` initially, then `percentage` (e.g. 10%)
- **Fatigue:** `PUSH_MAX_PER_6H=1`, `PUSH_MAX_PER_24H=2`
- **Limit:** `PUSH_BATCH_USER_LIMIT=500`
- **dry_run:** Explicit `false` for real sends; default is `true`

## Safe Rollout Order

1. Run with `dry_run=true` for a few days; inspect `batch/status` and batch results.
2. Enable `dry_run=false` during low-traffic windows.
3. Monitor `skip_reasons`, `alerts_sent`, receipt check results.
4. Scale `PUSH_BATCH_USER_LIMIT` and rollout mode as needed.

## Key Files

- `backend/push_batch_sender.py` – batch orchestration
- `backend/push_send_flow.py` – per-user send logic
- `backend/user_last_location_store.py` – location persistence
- `backend/main.py` – batch endpoints
