# Wave 1 hardening — test plan

Run from `backend` with Supabase env loaded (e.g. `set -a && source .env && set +a` or export vars).

## 1. Command order

Run in this order:

```bash
cd /Users/priyankraghuvanshi/projects/kcal-photo-app/backend
# Load Supabase env if not already in shell
# set -a && source .env && set +a

# Step 1 — Profile upsert (updated_at)
python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
r = sync_chain_menu_to_supabase('chipotle', 'US')
print('Profile upsert test:', r)
assert r.get('ok') is True, r
print('OK: profile upsert did not error')
"

# Step 2 — Status script
python3 scripts/chain_menu_status.py

# Step 3 — Wave 1 regression
python3 scripts/wave1_top_item_regression.py

# Step 4 — Existing test suites
python3 -m unittest test_chain_menu_supabase_sync -v
python3 -m unittest test_chain_menu_serving_path -v
python3 -m unittest test_chain_menu_ranking -v
```

## 2. Expected success output

- **Step 1:** One line of debug (or none if you removed it), then `Profile upsert test: {'ok': True, 'chain_key': 'chipotle', 'market_tag': 'US', 'item_count': N}` and `OK: profile upsert did not error`. No exception, no `error` in the dict.
- **Step 2:** `chain_keys in profiles:` lists at least the Wave 1 chain keys. Each of the 7 lines shows `N items  [ok]` (N > 0). `Total Wave 1 items:` is a positive number.
- **Step 3:** Single line: `Wave 1 top-item regression: all 7 chains OK`. Exit code 0.
- **Step 4:** Each unittest run ends with `OK` and `Ran N tests`; no FAIL or ERROR.

## 3. Failure interpretation

| What failed | Likely meaning |
|-------------|----------------|
| **Profile upsert still errors** | Supabase still rejects the profile row (e.g. `updated_at` constraint/trigger). Fix: ensure `chain_menu_profiles.updated_at` has `DEFAULT now()` and no NOT NULL constraint that fails when PostgREST merges; or add the optional trigger from `supabase_chain_menu_tables.sql`. Confirm sync sends `updated_at` (it does in current code). |
| **A chain shows `[MISSING]` in status** | That (chain_key, market_tag) has no rows in `chain_menu_items` (sync not run, failed, or FK/constraint blocked items). Re-sync that chain; check `chain_registry` has the chain_key if there’s an FK. |
| **Regression script fails for one chain** | For that chain: enrichment returned None, or `matched_chain_key` / `chain_menu_store` wrong, or `top_menu_item.item_name` didn’t contain any of the expected substrings. Check Supabase has items for that chain/market; check seed and sort order so the intended item wins. |
| **One of the existing test suites fails** | Unit test assertion or mock mismatch (e.g. return shape, import). Fix the test or the code so behaviour stays consistent; don’t change architecture. |
| **Debug logging too noisy** | SUPABASE DEBUG prints still on. Remove them or gate with `if os.getenv("SUPABASE_DEBUG"):` in `supabase_intelligence_store.py`. |

## 4. Final hardening checklist

- [ ] Step 1 runs without exception; sync result has `ok: True` and no `error`.
- [ ] Step 2 shows all 7 Wave 1 chains with `N items  [ok]` (N > 0).
- [ ] Step 3 prints `Wave 1 top-item regression: all 7 chains OK` and exit code 0.
- [ ] Step 4: all three unittest modules pass (test_chain_menu_supabase_sync, test_chain_menu_serving_path, test_chain_menu_ranking).
- [ ] Optional: SUPABASE DEBUG logging removed or gated.

When all are checked, Wave 1 hardening is validated. Proceed to Wave 2 only after this.
