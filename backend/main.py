import os
import io
import logging
import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

USDA_API_KEY = os.getenv("USDA_API_KEY", "")

app = FastAPI(title="Kcal Scan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp

@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-v1"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "railway-v1"}

@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)


# -------------------------
# USDA helpers
# -------------------------
def usda_search_food(query: str):
    """Search USDA and return best food match"""
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {"api_key": USDA_API_KEY}
    payload = {"query": query, "pageSize": 5}

    r = requests.post(url, params=params, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()

    foods = data.get("foods", [])
    if not foods:
        return None

    best = foods[0]
    return {
        "description": best.get("description") or query,
        "fdcId": best.get("fdcId"),
        "brandName": best.get("brandName")
    }


def usda_get_nutrients(fdc_id: int):
    """Fetch nutrient details by fdcId"""
    url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
    params = {"api_key": USDA_API_KEY}

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    nutrients = data.get("foodNutrients", [])

    kcal = 0
    protein = 0
    carbs = 0
    fat = 0

    # USDA nutrient names vary - match robustly
    for n in nutrients:
        nutrient = (n.get("nutrient") or {})
        name = (nutrient.get("name") or "").lower()
        unit = (nutrient.get("unitName") or "").lower()
        value = n.get("amount")

        if value is None:
            continue

        if "energy" in name and unit in ["kcal"]:
            kcal = float(value)

        elif "protein" in name and unit == "g":
            protein = float(value)

        elif "carbohydrate" in name and unit == "g":
            carbs = float(value)

        elif "total lipid" in name and unit == "g":
            fat = float(value)

    return {
        "kcal_per_100g": kcal,
        "protein_per_100g": protein,
        "carbs_per_100g": carbs,
        "fat_per_100g": fat,
    }


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not USDA_API_KEY:
        return {"error": "Missing USDA_API_KEY environment variable"}

    # read + validate image
    contents = await file.read()
    _ = Image.open(io.BytesIO(contents)).convert("RGB")

    # ✅ TEMP: simulate "AI vision" food detection (you can replace later)
    detected_food = "khichdi"  # TODO: Gemini/OpenAI image detection later
    grams = 280

    # 1) search USDA
    match = usda_search_food(detected_food)
    if not match:
        return {"error": f"No USDA match found for '{detected_food}'"}

    # 2) fetch nutrient details
    nutr = usda_get_nutrients(match["fdcId"])

    # scale by grams (USDA values are per 100g)
    factor = grams / 100.0

    item = {
        "name": match["description"].lower(),
        "grams": grams,
        "kcal": round(nutr["kcal_per_100g"] * factor, 1),
        "protein_g": round(nutr["protein_per_100g"] * factor, 1),
        "carbs_g": round(nutr["carbs_per_100g"] * factor, 1),
        "fat_g": round(nutr["fat_per_100g"] * factor, 1),
        "confidence": 0.9,
        "fdcId": match["fdcId"],
    }

    total = item["kcal"]

    return {
        "total_kcal": total,
        "total_macros": {
            "protein_g": item["protein_g"],
            "carbs_g": item["carbs_g"],
            "fat_g": item["fat_g"],
        },
        "items": [item]
    }

