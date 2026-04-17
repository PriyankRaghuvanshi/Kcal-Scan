# CalorieClick Family Habits Scoping Notes

## Why this stays inside CalorieClick

- This feature is a parent-first food-routine module, not a separate family-health product.
- The strongest MVP value is helping with dinner structure, exposures, rescue nights, and weekly food-routine resets inside the app parents already use for meal decisions.
- It reuses CalorieClick auth, app shell, Supabase patterns, and deterministic meal logic, so shipping it inside the current product is lower-risk and faster than spinning up a separate repo.

## Intentionally out of scope

- wearable integrations
- sleep, stress, behavior, or mood tracking outside meal routines
- medication, symptom, diagnosis, doctor, or preventive-health features
- broad family-health monitoring or family-health dashboards
- expanding Lunchbox support into a full MVP pillar

## What would trigger a future separate repo or product

- The feature starts needing non-food clinical, developmental, or monitoring workflows.
- It requires a dedicated caregiver or household operating model that no longer fits naturally inside the CalorieClick meal shell.
- The roadmap shifts from food-routine support toward a broader family-health platform with its own data model, navigation, compliance posture, and positioning.
