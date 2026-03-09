import unittest

from share_card_formatter import build_best_order_share_card


class ShareCardFormatterTests(unittest.TestCase):
    def test_field_presence_and_score_scaling(self):
        card = build_best_order_share_card(
            place_name="Nando's",
            health_score=8.8,
            best_order="Half chicken + salad",
            estimated_calories=540,
            estimated_protein_g=48,
            subtitle="High protein and better calorie control for your cut.",
            recommended_badges=["High-protein options likely"],
            order_strategy_tags=["fat_loss_friendly", "high_protein"],
            cut_friendly=True,
            fat_loss_friendly=True,
        )

        required = {
            "title",
            "restaurant_name",
            "place_name",
            "health_score",
            "order_name",
            "best_order",
            "estimated_calories",
            "estimated_protein_g",
            "calories_saved",
            "hero_line",
            "badge",
            "subtitle",
            "badges",
            "share_card_version",
        }
        self.assertTrue(required.issubset(card.keys()))
        self.assertEqual(card["title"], "Smarter Order")
        self.assertEqual(card["health_score"], 88)

    def test_wording_length_sanity(self):
        card = build_best_order_share_card(
            place_name="Very long place name that should be clipped for mobile-friendly share card rendering",
            health_score=92,
            best_order="Very long best order string that should not overflow the share card and should stay social-ready",
            estimated_calories=610,
            estimated_protein_g=36,
            subtitle="This subtitle is intentionally verbose to verify clipping so cards stay short, consumer-friendly, and readable in social previews.",
            recommended_badges=["Calorie-control friendly", "High-protein options likely"],
            order_strategy_tags=["high_protein", "calorie_control", "fat_loss_friendly"],
        )

        self.assertLessEqual(len(card["title"]), 28)
        self.assertLessEqual(len(card["restaurant_name"]), 40)
        self.assertLessEqual(len(card["order_name"]), 64)
        self.assertLessEqual(len(card["subtitle"]), 72)

    def test_badges_are_deduped_and_capped(self):
        card = build_best_order_share_card(
            place_name="Protein Grill",
            health_score=7.9,
            best_order="Grilled chicken bowl",
            estimated_calories=520,
            estimated_protein_g=42,
            subtitle="High protein and better calorie control.",
            recommended_badges=[
                "High-protein options likely",
                "Calorie-control friendly",
                "Satiety-friendly picks",
            ],
            order_strategy_tags=["high_protein", "calorie_control", "fat_loss_friendly", "high_satiety"],
            cut_friendly=True,
            fat_loss_friendly=True,
        )

        self.assertGreaterEqual(len(card["badges"]), 1)
        self.assertLessEqual(len(card["badges"]), 1)
        self.assertIn("Fat Loss Friendly", card["badges"])


if __name__ == "__main__":
    unittest.main()
