# Wave 1 hardening plan

After Wave 1 rollout (Chipotle, Taco Bell, Panera, Faasos, Wow! Momo, Haldiram's, Barbeque Nation), use this plan before adding more brands.

## 1. Backend and schema cleanup

- **Profile upsert `updated_at`:** Sync now sends `updated_at` (ISO UTC) in the profile row so Supabase accepts the upsert. If your table still errors:
  - Ensure `chain_menu_profiles.updated_at` has `DEFAULT now()`.
  - Optionally add a trigger to set `updated_at = now()` on UPDATE (see comments in `supabase_chain_menu_tables.sql`).
- **Debug logging:** The temporary SUPABASE DEBUG prints in `supabase_intelligence_store` (upsert_chain_menu_profile, upsert_chain_menu_items) can be removed or gated on an env var (e.g. `SUPABASE_DEBUG=1`) once profile upsert is stable.
- **No other schema changes** for hardening; keep existing tables and FKs.

## 2. Ops visibility additions

- **Status script:** Run from backend: `python3 scripts/chain_menu_status.py`. Prints `list_chain_menu_chain_keys()` and, for each Wave 1 (chain_key, market_tag), item count and [ok] or [MISSING]. Use after sync or to verify readiness.
- **Optional HTTP endpoint:** If you expose a status API, add e.g. `GET /chain-menus/status` that returns `{ "chains": list_chain_menu_chain_keys(), "wave1": [ { "chain_key", "market_tag", "item_count" } for each Wave 1 ] }`. Not required for hardening; the script is enough.

## 3. Audit and readiness checks

- **Readiness:** Run `python3 scripts/chain_menu_status.py`. All Wave 1 rows should show `item_count > 0` and [ok].
- **Regression:** Run `python3 scripts/wave1_top_item_regression.py`. It enriches one mock place per Wave 1 chain and checks `matched_chain_key`, `chain_menu_store`, and that `top_menu_item.item_name` contains an expected substring (e.g. "High Protein Bowl" for Chipotle). Exit 0 = all pass; exit 1 = at least one failed (wrong chain, wrong store, or bad top item).
- **Supabase:** Periodically run the SQL from rollout docs to confirm row counts: `select chain_key, market_tag, count(*) from public.chain_menu_items where ... group by 1,2`.

## 4. Tests to add

- **Existing:** Keep and run `test_chain_menu_supabase_sync`, `test_chain_menu_serving_path`, `test_chain_menu_ranking`.
- **Add (optional):** In `test_chain_menu_serving_path.py`, one test that runs `wave1_top_item_regression` logic for a single chain with **mocked** `get_chain_menu_items` (so it doesn’t require Supabase): e.g. mock returns two items (one good, one bad), assert top is the good one. That guards sort order without hitting the DB.
- **No new ranking engine or LLM tests.**

## 5. Regression checks

- **Bad top item:** `wave1_top_item_regression.py` asserts that for each Wave 1 chain, the top item name contains one of the expected substrings (e.g. grilled, high protein, salad). If a seed or sort change pushes a heavy/indulgent item first, the script fails.
- **Hidden chain:** Same script asserts `matched_chain_key` and `chain_menu_store == "supabase"`. If a chain stops matching or falls back to non-Supabase path, the script fails.
- **Run:** After any change to sync, enrichment, or seed data, run `python3 scripts/wave1_top_item_regression.py` (with real Supabase) and fix before merging.

## 6. Hardening success criteria

- [ ] Profile upsert no longer throws (updated_at sent from sync and/or schema fixed).
- [ ] `python3 scripts/chain_menu_status.py` shows all Wave 1 chains with item_count > 0.
- [ ] `python3 scripts/wave1_top_item_regression.py` exits 0 (all 7 chains: correct key, store, and top item).
- [ ] Existing test suites pass: `test_chain_menu_supabase_sync`, `test_chain_menu_serving_path`, `test_chain_menu_ranking`.
- [ ] Optional: SUPABASE DEBUG logging removed or gated.

## 7. Recommended next step after hardening

Only after all criteria in section 6 are met: **proceed to Wave 2** (new brands). Use the same rollout pattern: seed JSON, chain_registry insert, sync, status check, enrichment verification, then add the new chain to `WAVE1_CHAINS` / `WAVE1_CHECKS` (or a Wave 2 list) and re-run the regression script.
