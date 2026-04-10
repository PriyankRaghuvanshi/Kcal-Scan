# Project rules for Codex

- Prefer extending existing CalorieClick meal, scan, coach, and Supabase patterns.
- Never introduce calorie targets or weight-loss framing for children.
- Deterministic logic first; LLM only for wording.
- All family-habit outputs must be calm, practical, and parent-first.
- Reuse current UI components and navigation patterns.
- Add migrations instead of manual schema edits.
- Add tests for ranking, exposure summaries, rescue mapping, and weekly reset logic.
- Keep implementation modular:
  - meal_recommendation_service
  - exposure_service
  - rescue_service
  - weekly_reset_service
  - family_memory_service
- When uncertain, choose the lower-complexity implementation that can ship MVP faster.

## Build & Deploy Safety (MANDATORY)

- **NEVER build or deploy without checking for potential crashes first.**
- Before every EAS build, run through this checklist:
  1. Search for any `nil` / `null` / `undefined` values being passed to native APIs (especially HealthKit, NSDictionary, react-native-health).
  2. Verify the postinstall patch script (`mobile/scripts/patch-health.js`) is in place and runs correctly.
  3. Check that no new native dependencies were added without proper null-safety guards.
  4. Review recent changes for any dictionary/object construction that could insert nil values.
  5. Test that `app.json` has all required permission descriptions and entitlements.
- **ALWAYS ask the user for explicit approval before kicking off a build.** Builds cost money — never auto-trigger.
- If a build crashes, diagnose the root cause from the crash log BEFORE attempting another build.
- Never deploy a half-fixed product. All crash fixes must be verified in code review before rebuilding.
