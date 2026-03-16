# Chain menu: sync and verification runbook

Quick reference for syncing chain seeds to Supabase and running verification. See `CHAIN_MENU_CLEANUP_AND_EXPANSION_READINESS.md` for cleanup and expansion.

**Prerequisites:** From `backend/`, with Supabase env set (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`).

---

## Re-sync one chain

```bash
cd backend && python3 -c "
from chain_menu_supabase_sync import sync_chain_menu_to_supabase
print(sync_chain_menu_to_supabase('CHAIN_KEY', 'MARKET'))
"
```

Examples: `('kfc', 'AU')`, `('mcdonalds', 'AU')`, `('wow_momo', 'IN')`, `('haldirams', 'IN')`, `('nandos', 'AU')`, `('red_rooster', 'AU')`, `('hungry_jacks', 'AU')`.

Success: `{"ok": True, "chain_key": "...", "market_tag": "...", "item_count": N}`.

---

## Diet spot checks (all five)

```bash
cd backend && python3 scripts/spot_check_diet_enrichment.py
```

Covers: McDonald's veg, Wow! Momo veg, Haldiram's veg, Nando's vegan, KFC vegan. Expect veg tops or `no_diet_safe_candidates: True` + `top_menu_item: None` for vegan-only chains with no vegan items.

---

## Per-chain enrichment verification

Run the script for the chain you changed:

- `python3 scripts/verify_enrichment_mcdonalds_au.py`
- `python3 scripts/verify_enrichment_nandos_kfc_au.py`
- `python3 scripts/verify_enrichment_red_rooster_hungry_jacks_au.py`
- `python3 scripts/verify_enrichment_wow_momo_haldirams.py`
- etc.

---

## Regression (default top items)

```bash
cd backend && python3 scripts/wave1_top_item_regression.py
```

(Or your project’s equivalent regression script.) Confirms default (omnivore) top items still match expectations after any sync or code change.

---

## Debug sync (noisy logs)

To turn on Supabase chain sync debug prints:

```bash
export CHAIN_MENU_SYNC_DEBUG=1
# then run sync as above
```
