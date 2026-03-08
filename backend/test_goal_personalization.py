import unittest

from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from menu_item_scoring import rank_menu_items_for_place, recommend_menu_items_for_place
from personalization_profiles import PersonalizationGoal


class GoalPersonalizationTests(unittest.TestCase):
    def test_place_ranking_differs_by_goal(self):
        places = [
            {"name": "Healthy Salad Vegan Spot", "types": ["restaurant", "meal_takeaway"]},
            {"name": "Protein Grill Steak House", "types": ["restaurant", "meal_takeaway"]},
        ]

        fat_scores = {
            p["name"]: float(score_healthy_place(p, personalization_goal=PersonalizationGoal.FAT_LOSS)["health_score"])
            for p in places
        }
        muscle_scores = {
            p["name"]: float(score_healthy_place(p, personalization_goal=PersonalizationGoal.MUSCLE_GAIN)["health_score"])
            for p in places
        }

        fat_top = max(fat_scores, key=fat_scores.get)
        muscle_top = max(muscle_scores, key=muscle_scores.get)
        self.assertNotEqual(fat_top, muscle_top)

    def test_default_score_and_menu_are_stable_without_goal(self):
        place = {"name": "Sushi Poke Bowl Kitchen", "types": ["restaurant"]}

        base = score_healthy_place(place)
        explicit_none = score_healthy_place(place, personalization_goal=None)

        self.assertEqual(float(base["health_score"]), float(explicit_none["health_score"]))

        menu_base = recommend_menu_items_for_place(place)
        menu_none = recommend_menu_items_for_place(place, personalization_goal=None)
        self.assertEqual(menu_base.get("top_item"), menu_none.get("top_item"))

    def test_personalized_fields_present_when_goal_provided(self):
        place = {"name": "Urban Sushi Hub", "types": ["restaurant", "meal_takeaway"]}
        out = suggest_best_order_for_place(
            place,
            health_score=7.2,
            personalization_goal=PersonalizationGoal.KETO,
        )

        self.assertEqual(out.get("personalization_goal"), "keto")
        self.assertTrue(str(out.get("personalized_best_order") or "").strip())
        self.assertTrue(str(out.get("personalized_reason") or "").strip())

    def test_menu_item_scoring_is_goal_aware(self):
        place = {"name": "Urban Mixed Kitchen", "types": ["restaurant"]}
        items = [
            {"item_name": "Chicken rice bowl", "estimated_calories": 650, "estimated_protein_g": 35},
            {"item_name": "Salmon avocado bowl", "estimated_calories": 620, "estimated_protein_g": 32},
            {"item_name": "Lean chicken wrap", "estimated_calories": 520, "estimated_protein_g": 34},
        ]

        default_ranked = rank_menu_items_for_place(place, items)
        keto_ranked = rank_menu_items_for_place(place, items, personalization_goal=PersonalizationGoal.KETO)

        self.assertEqual(len(default_ranked), len(keto_ranked))
        self.assertNotEqual(
            [int(x.get("item_score", 0)) for x in default_ranked],
            [int(x.get("item_score", 0)) for x in keto_ranked],
        )
        self.assertEqual(keto_ranked[0].get("personalization_goal"), "keto")


if __name__ == "__main__":
    unittest.main()
