#!/usr/bin/env python3
"""Validate coach phrase bank templates and smoke-test dynamic copy."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as m  # noqa: E402

_FMT = {
    "summary_fact": "Protein gap is about 12.0g, which is currently the main limiter.",
    "impact": "Higher UPF exposure can reduce satiety stability and increase snacking risk.",
    "one_change": "Add one protein anchor at your next meal and repeat at lunch/dinner.",
    "bottleneck_label": "protein",
}


def _validate_bank(name: str, bank: dict) -> list[str]:
    errs: list[str] = []
    for style, lines in bank.items():
        for i, tmpl in enumerate(lines):
            try:
                out = str(tmpl).format(**_FMT).strip()
                if not out:
                    errs.append(f"{name}[{style!r}][{i}] empty after format")
            except Exception as e:
                errs.append(f"{name}[{style!r}][{i}]: {e} | tmpl={tmpl!r}")
    return errs


def _validate_inspiration() -> list[str]:
    errs: list[str] = []
    for style, lines in m._COACH_INSPIRATION_STYLE_BANK.items():
        for i, line in enumerate(lines):
            s = str(line)
            if "{" in s and "}" in s:
                try:
                    s.format(**_FMT)
                except KeyError as e:
                    errs.append(f"inspiration[{style!r}][{i}] unexpected brace: {e} | line={s!r}")
    return errs


class CoachPhraseBankTests(unittest.TestCase):
    def test_summary_bank_formats(self) -> None:
        errs = _validate_bank("summary", m._COACH_SUMMARY_STYLE_BANK)
        self.assertEqual(errs, [], "\n".join(errs))

    def test_why_bank_formats(self) -> None:
        errs = _validate_bank("why", m._COACH_WHY_STYLE_BANK)
        self.assertEqual(errs, [], "\n".join(errs))

    def test_action_bank_formats(self) -> None:
        errs = _validate_bank("action", m._COACH_ACTION_STYLE_BANK)
        self.assertEqual(errs, [], "\n".join(errs))

    def test_inspiration_no_bad_braces(self) -> None:
        errs = _validate_inspiration()
        self.assertEqual(errs, [], "\n".join(errs))

    def test_apply_dynamic_coach_copy_smoke(self) -> None:
        norm = {
            "goals": {"kcal": 2000, "protein_g": 140, "fiber_g": 35},
            "consumed": {"kcal": 2320, "protein_g": 100, "fiber_g": 20},
            "signals": {"ultra_processed_avg": 4.5, "avg_glycemic_load": 15, "avg_satiety": 60},
            "meal_timing": {"late_calories_pct": 25},
        }
        wp = {"days_tracked": 2, "upf_avg": 4.5}
        for tone in ("supportive", "strict", "funny", "indian_coach"):
            out = m._apply_dynamic_coach_copy(
                {"tone_used": tone, "fat_loss_score": 55},
                norm,
                user_id="u_test",
                day_iso="2026-03-24",
                scan_id="scan_a",
                scan_count=1,
                recent_messages=[],
                weekly_predictive=wp,
            )
            self.assertIn("one_sentence_summary", out)
            self.assertIn("why_it_matters", out)
            self.assertIn("if_you_do_one_thing", out)
            self.assertIn(out.get("coach_relationship_stance"), ("warm_reset", "accountability", "steady"))


if __name__ == "__main__":
    unittest.main()
