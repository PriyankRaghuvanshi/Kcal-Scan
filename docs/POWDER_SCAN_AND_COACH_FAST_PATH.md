# Powder Scan + Coach Fast Path

## Problem 1: Powder scan accuracy

Protein powders often resolve to the wrong USDA entries (e.g. drink mixes) which yields obviously wrong macros (e.g. 30g scoop → ~14g protein).

### Fix

- Add deterministic detection for **powder-like** items.
- When detected, bypass USDA-first nutrition mapping and use a **supplement macro table**.
- Expose a lightweight confirmation UI so users can confirm **powder type** and **scoop size**.
- Apply confirmations via `/analyze/rerun` without re-uploading the photo.

### Backend behavior

- `backend/scan_food_rules.py`
  - Detects powder-like names (whey/protein powder/isolate/plant/mass gainer/cocoa).
  - Provides realistic defaults (30g serving) for:
    - whey
    - whey_isolate
    - plant_protein
    - mass_gainer
    - cocoa_powder
  - Uses sentinel names: `supplement_powder:<type>` for confirmed rerun swaps.

- `backend/main.py`
  - `_compute_scan_nutrition` checks powder rules **before** USDA resolution.
  - Each scan item may include `_powder_meta`:
    - `is_powder_like`
    - `powder_type_guess`, `powder_type_resolved`
    - `needs_powder_confirmation`
    - `powder_confirmation` (types + scoop sizes)

### Mobile behavior

- `mobile/components/ScanConfirmationChips.js` (internal UI)
  - Shows powder type chips and scoop size chips.

- `mobile/App.js`
  - Renders powder confirmation chips when `_powder_meta.is_powder_like` is present.
  - On selection, calls `/analyze/rerun` with:
    - `swap_item` to `supplement_powder:<type>`
    - `set_item_grams` to chosen scoop grams

## Problem 2: Fat-loss intelligence / coach voice too slow

### Fix

- Daily fat-loss intelligence is **deterministic rules-first** and returns immediately.
- LLM is not used in the request path for `/coach/daily` (prevents blocking).
- Coach voice remains optional UI content; it should never block scan results.

### Backend behavior

- `backend/main.py` `/coach/daily`
  - Returns deterministic `rules` response and avoids LLM call in-request.

### Mobile behavior (existing, recommended)

- UI already shows core scan results without coach voice.
- Consider removing the spinner for coach voice or adding a short timeout so it never feels blocking.

