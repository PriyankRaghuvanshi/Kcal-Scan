import unittest

from swap_rules import generate_swaps_for_item


def _place(name: str, types=None):
    return {"name": name, "types": types or []}


class TestSwapRules(unittest.TestCase):
    def test_subway_swaps(self):
        swaps, debug = generate_swaps_for_item(
            place=_place("Subway", ["sandwich"]),
            item_name="6-inch grilled chicken sub, extra salad, light sauce",
            estimated_calories=390,
            estimated_protein_g=30,
            cuisine_hint="subway sandwich",
            menu_item_source="chain_registry",
            menu_item_confidence=0.9,
            cut_mode=True,
        )
        labels = [s.get("swap_label") for s in swaps]
        self.assertGreaterEqual(len(swaps), 1)
        self.assertTrue(
            any("mayo" in str(l).lower() or "sauce" in str(l).lower() or "drink" in str(l).lower() for l in labels),
            msg=f"labels={labels}",
        )

    def test_pizza_swaps(self):
        swaps, _ = generate_swaps_for_item(
            place=_place("Pizza Hut", ["pizza"]),
            item_name="Thin crust personal pizza",
            estimated_calories=580,
            estimated_protein_g=28,
            cuisine_hint="pizza",
            menu_item_source="heuristic",
            menu_item_confidence=0.55,
            cut_mode=True,
        )
        labels = " | ".join(str(s.get("swap_label") or "") for s in swaps).lower()
        self.assertTrue(("slice" in labels) or ("2" in labels), msg=f"labels={labels}")
        self.assertTrue(("skip" in labels) or ("no" in labels), msg=f"labels={labels}")
        # No unrealistic protein substitutions
        self.assertFalse(any("whey" in str(s.get("modified_item_name") or "").lower() for s in swaps))

    def test_cafe_swaps(self):
        swaps, _ = generate_swaps_for_item(
            place=_place("Corner Cafe", ["cafe"]),
            item_name="Grilled chicken wrap",
            estimated_calories=480,
            estimated_protein_g=28,
            cuisine_hint="cafe",
            menu_item_source="real_menu",
            menu_item_confidence=0.8,
            cut_mode=True,
        )
        labels = [str(s.get("swap_label") or "").lower() for s in swaps]
        self.assertTrue(any("sauce" in l or "aioli" in l for l in labels))
        self.assertTrue(any("pastry" in l or "side" in l for l in labels))

    def test_indian_swaps(self):
        swaps, _ = generate_swaps_for_item(
            place=_place("Darbar Indian", ["indian"]),
            item_name="Butter chicken + naan",
            estimated_calories=780,
            estimated_protein_g=32,
            cuisine_hint="indian",
            menu_item_source="heuristic",
            menu_item_confidence=0.55,
            cut_mode=True,
        )
        labels = " | ".join(str(s.get("swap_label") or "") for s in swaps).lower()
        self.assertTrue("tandoori" in labels or "roti" in labels or "skip fried" in labels)

    def test_juice_swaps_conservative(self):
        swaps, debug = generate_swaps_for_item(
            place=_place("Fresh Juice Bar", ["juice"]),
            item_name="Fruit smoothie",
            estimated_calories=380,
            estimated_protein_g=8,
            cuisine_hint="juice smoothie",
            menu_item_source="heuristic",
            menu_item_confidence=0.45,
            cut_mode=True,
        )
        # Should include lower sugar guidance; should not confidently invent protein add-on
        labels = " | ".join(str(s.get("swap_label") or "") for s in swaps).lower()
        self.assertIn("sugar", labels)
        self.assertFalse(any("protein" in str(s.get("swap_type") or "").lower() and s.get("protein_delta", 0) >= 15 for s in swaps))


if __name__ == "__main__":
    unittest.main()

