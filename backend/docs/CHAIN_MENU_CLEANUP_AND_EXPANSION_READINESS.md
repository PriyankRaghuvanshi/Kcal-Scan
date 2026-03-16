# Chain menu foundation: cleanup and expansion readiness

Practical cleanup plan before adding more brands. No architecture change, no new ranking engine, no LLM. Deterministic, low-risk.

---

## 1. Logging cleanup

**Done:** Supabase chain sync debug prints are now gated.

- **File:** `backend/supabase_intelligence_store.py`
- **Change:** All `print("SUPABASE DEBUG ...")` in `upsert_chain_menu_profile` and `upsert_chain_menu_items` are wrapped with `_chain_sync_debug()`.
- **Trigger:** Set env `CHAIN_MENU_SYNC_DEBUG=1` or `SUPABASE_CHAIN_DEBUG=1` to turn debug on; **default is off** (no noisy stdout during sync).

**Optional (low-risk):** Elsewhere in the repo, search for other `print(...)` or `logger.debug(...)` in the chain menu or enrichment path; gate or remove only if clearly temporary debug. Prefer leaving one env-gated debug path rather than deleting it entirely.

---

## 2. Seed and data cleanup

**Done:** Explicit `vegetarian_possible` and `vegan_possible` added where they were missing so seeds and Supabase rows stay consistent.

**Seeds updated:**

- **mcdonalds_au.json** – Hamburger: veg + vegan; McChicken, Filet-O-Fish, Big Mac: false/false.
- **nandos_au.json** – All items chicken: false/false.
- **red_rooster_au.json** – All items chicken: false/false.
- **hungry_jacks_au.json** – All items chicken/burger: false/false.

**Already had explicit flags:** kfc_au, wow_momo_in, haldirams_in.

**Consistency rules going forward:**

- Every new or edited chain seed item must have `vegetarian_possible` and `vegan_possible` (each `true` or `false`).
- After editing any seed, re-sync that chain to Supabase so DB rows match.

**Optional (next wave):** Add the same two fields to remaining chain seeds (e.g. chipotle_us, faasos_in, taco_bell_us, panera_us, barbeque_nation_in) so all chains are explicit before expansion.

---

## 3. Script and docs cleanup

**Scripts to keep and how to use them:**

- **Single-chain verification:** `scripts/verify_enrichment_<chain>_*.py` – run one per chain when changing that chain or debugging. Keep as-is; no need to merge.
- **Diet spot checks (all five):** `scripts/spot_check_diet_enrichment.py` – single entry point for diet behaviour. Keep; run after any diet-related or seed change.
- **Regression / status:** Use `scripts/wave1_top_item_regression.py` (or equivalent) for default top-item regression; run after sync or enrichment changes.

**Docs to tidy:**

- **Consolidate into one “runbook”:** Add or update a short doc (e.g. `docs/CHAIN_MENU_RUNBOOK.md`) that lists:
  - Re-sync command pattern: `python3 -c "from chain_menu_supabase_sync import sync_chain_menu_to_supabase; print(sync_chain_menu_to_supabase('CHAIN_KEY', 'MARKET'))"`
  - Full diet spot check: `python3 scripts/spot_check_diet_enrichment.py`
  - Where verification scripts live and when to run which (per-chain vs diet vs regression).
- **Point to cleanup/expansion doc:** In `data/chains/README.md` or rollout docs, add a line that points to this cleanup doc and to the runbook so “clean and ready for expansion” is easy to find.

**Low-risk tidy:** Merge or cross-link overlapping rollout/spot-check docs (e.g. DIET_SPOT_CHECK_PLAN.md, KFC_VEGAN_FIX_AND_RETEST.md, WOW_MOMO_HALDIRAMS_VEG_FIX_AND_RETEST.md) so they reference the runbook and this doc instead of duplicating commands.

---

## 4. Optional tests

**Add only if you want extra safety; not required for “clean and ready”:**

- **Diet enrichment:** You already have `tests/test_diet_enrichment.py` covering vegetarian, vegan, no-safe-option, omnivore. Optional: one test that asserts `diet_filter_applied` and `no_diet_safe_candidates` on the payload shape for a known chain/diet pair (e.g. KFC vegan → None + True).
- **Sync no-debug by default:** Optional: small test that, without setting `CHAIN_MENU_SYNC_DEBUG`, runs a sync path and asserts no `SUPABASE DEBUG` string appears in captured stdout (if you capture logs in tests). Skip if your test harness doesn’t capture print.

**Do not add:** New ranking engine tests, LLM tests, or broad integration tests that would slow the pipeline. Keep tests focused on sync + enrichment + diet behaviour.

---

## 5. Cleanup success criteria

The foundation is **“clean and ready for expansion”** when:

1. **Sync:** Re-sync of any hardened chain (e.g. kfc AU, mcdonalds AU, wow_momo IN, haldirams IN) completes with `ok: True` and expected `item_count`, and no debug spam in stdout unless `CHAIN_MENU_SYNC_DEBUG=1`.
2. **Seeds:** All hardened chain seeds have explicit `vegetarian_possible` and `vegan_possible` on every item; no reliance on “null means false” for diet filtering in production.
3. **Diet behaviour:** Full diet spot-check script passes for McDonald’s vegetarian, Wow! Momo vegetarian, Haldiram’s vegetarian, Nando’s vegan, KFC vegan (top_item or no_diet_safe_candidates as already validated).
4. **Regression:** Existing regression/status script (e.g. wave1 top-item or equivalent) still passes for default (omnivore) top items.
5. **Docs:** One runbook or single “how to sync and verify” doc exists and points to this cleanup doc; no need to hunt across many files to run sync + spot-check + regression.

---

## 6. Recommended next expansion step

**Immediately after cleanup:**

1. Run the full diet spot-check script once in your target environment (with Supabase and latest synced data) and confirm all five checks match the expected behaviour above.
2. Re-sync any chain whose seed you changed (mcdonalds, nandos, red_rooster, hungry_jacks) so Supabase rows have the new flags.
3. Add or update the short runbook so “sync → spot-check → regression” is one place.

**Then expand:**

- Add the **next brand(s)** using the same pipeline: add or edit a seed under `data/chains/` with explicit `vegetarian_possible` and `vegan_possible`, run `sync_chain_menu_to_supabase(chain_key, market_tag)`, then run the diet spot-check (and, if applicable, a small verify script for that chain). No new architecture; reuse existing sync + enrichment + diet filtering.
