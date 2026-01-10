import io
import os
import logging
import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

app = FastAPI(title="Kcal Scan API")

# ✅ CORS (keep wide for now; lock down later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# ✅ Log EVERY request so we can see what iPhone is calling
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp

@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-usda-v1"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "railway-usda-v1",
        "usda_key_loaded": bool(USDA_API_KEY),
    }

# (Optional) Explicit OPTIONS handler for debugging
@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)


# -------------------------------------------------------
# ✅ USDA HELPERS
# -------------------------------------------------------

def usda_search_food(query: str):
    """
    Search USDA foods by name; returns the best match.
    """
    if not USDA_API_KEY:
        raise RuntimeError("USDA_API_KEY is missing in environment.")

    payload = {
        "query": query,
        "pageSize": 5,
        "pageNumber": 1,
    }

    r = requests.post(f"{USDA_SEARCH_URL}?api_key={USDA_API_KEY}", json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()

    foods = data.get("foods", [])
    if not foods:
        return None

    return foods[0]


def get_kcal_per_100g(usda_food: dict):
    """
    Extract kcal per 100g from USDA response.
    USDA stores calories in "foodNutrients".
    """
    nutrients = usda_food.get("foodNutrients", [])
    for n in nutrients:
        name = (n.get("nutrientName") or "").lower()
        unit = (n.get("unitName") or "").lower()
        value = n.get("value")

        # Energy / Calories
        if value is None:
            continue

        if "energy" in name and ("kcal" in unit or "calorie" in name):
            return float(value)

        # Sometimes nutrientName = "Energy" unitName = "KCAL"
        if name == "energy" and unit == "kcal":
            return float(value)

    return None


# -------------------------------------------------------
# ✅ Test endpoint to confirm USDA works on Railway
# -------------------------------------------------------
@app.get("/usda/search")
def usda_search(query: str = Query(..., min_length=2)):
    try:
        food = usda_search_food(query)
        if not food:
            return {"query": query, "found": False, "foods": []}

        kcal100 = get_kcal_per_100g(food)
        return {
            "query": query,
            "found": True,
            "description": food.get("description"),
            "brandName": food.get("brandName"),
            "fdcId": food.get("fdcId"),
            "kcal_per_100g": kcal100,
        }
    except Exception as e:
        logger.exception("USDA search failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# -------------------------------------------------------
# ✅ Analyze endpoint (USDA powered)
# -------------------------------------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        logger.info(f"Image received: {img.size}")

        # ✅ TEMP FOOD DETECTION (placeholder until AI vision)
        # Later we will replace this with AI vision model.
        detected_foods = ["apple"]  # start simple to verify USDA works end-to-end

        items = []
        total_kcal = 0

        for food_name in detected_foods:
            usda_food = usda_search_food(food_name)
            if not usda_food:
                items.append({
                    "name": food_name,
                    "grams": 100,
                    "kcal": 0,
                    "confidence": 0.4,
                    "source": "usda",
                    "note": "Not found in USDA"
                })
                continue

            kcal_per_100g = get_kcal_per_100g(usda_food) or 0.0

            grams = 150  # placeholder portion size; later AI portion estimator
            kcal = round((kcal_per_100g * grams) / 100.0, 1)

            items.append({
                "name": food_name,
                "grams": grams,
                "kcal": kcal,
                "confidence": 0.85,
                "source": "usda",
                "usda_description": usda_food.get("description"),
                "fdcId": usda_food.get("fdcId"),
                "kcal_per_100g": kcal_per_100g,
            })

            total_kcal += kcal

        return {"total_kcal": round(total_kcal, 1), "items": items}

    except Exception as e:
        logger.exception("Analyze failed")
        return JSONResponse({"error": str(e)}, status_code=500)

