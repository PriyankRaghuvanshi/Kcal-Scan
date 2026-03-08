from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_scan_nutrition_success():
    payload = {
        "meal_scan": {
            "meal_name": "Chicken rice bowl",
            "calories": 640,
            "protein_g": 42,
            "carbs_g": 58,
            "fat_g": 18,
            "fiber_g": 9,
            "sugar_g": 7,
            "sodium_mg": 980,
            "confidence": 0.87,
            "scan_source": "camera",
            "flags": ["high_protein"],
        },
        "supplement_scan": {
            "product_name": "Whey Isolate",
            "brand": "Demo",
            "servings_per_day": 1,
            "calories": 120,
            "protein_g": 24,
            "carbs_g": 3,
            "fat_g": 1,
            "sugar_g": 1,
            "sodium_mg": 80,
            "caffeine_mg": 0,
            "authenticity_score": 86,
            "risk_flags": [],
        },
        "user_profile": {
            "goal": "fat_loss",
            "target_calories": 2100,
            "target_protein_g": 160,
            "workout_day": True,
            "meal_window": "lunch",
        },
    }

    response = client.post("/api/v1/nutrition/scan", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["focus"] == "fat_loss_intelligence"
    assert "insights" in body
    assert "fat_loss_score" in body["insights"]
    assert "recommendations" in body["insights"]


def test_scan_nutrition_requires_meal_scan():
    response = client.post("/api/v1/nutrition/scan", json={})
    assert response.status_code == 422
