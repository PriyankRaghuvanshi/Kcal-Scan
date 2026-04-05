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
