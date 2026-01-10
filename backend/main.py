# backend/main.py
import io
import os
import json
import logging
import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

app = FastAPI(title="Kcal Scan API", version="railway-gemini-usda-v1")

# ✅ CORS (wide for now; lock down later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


# ✅ Log every request (helps debug mobile)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp


@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-gemini-usda-v1"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "railway-gemini-usda-v1",
        "usda_key_loaded": bool(USDA_API_KEY),
        "gemini_key_loaded": bool(GEMINI_API_KEY),
    }


# Optional: explicit preflight handler (CORS middleware usually handles this)
@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)


# -----------------------------
# USDA helpers
# -----------------------------
def usda_search_food(query: str):
    if not USDA_API_KEY:
        raise RuntimeError("USDA_API_KEY is missing in environment.")

    payload = {"query": query, "pageSize": 5, "pageNumber": 1}

    r = requests.post(
        f"{USDA_SEARCH_URL}?api_key={USDA_API_KEY}",
        json=payload,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    foods = data.get("foods", [])
    if not foods:
        return None
    return foods[0]


def _pick_nutrient(food_nutrients, name_contains: list[str], unit_prefer: str | None = None):
    """
    Picks first nutrient whose nutrientName contains any keyword.
    Returns float value or 0.0 if missing.
    """
    for n in food_nutrients:
        n_name = (n.get("nutrientName") or "").lower()
        unit = (n.get("unitName") or "").lower()
        val = n.get("value")
        if val is None:
            continue
        if any(k in n_name for k in name_contains):
            if unit_prefer is None or unit == unit_prefer.lower():
                try:
                    return float(val)
                except Exception:
                    return 0.0
    return 0.0


def usda_extract_macros_per_100g(usda_food: dict):
    """
    Returns kcal/protein/carbs/fat per 100g from USDA 'foodNutrients' list.
    Note: search results are usually per 100g (varies by data source).
    """
    nutrients = usda_food.get("foodNutrients", []) or []

    kcal_100g = _pick_nutrient(nutrients, ["energy"], unit_prefer="kcal")
    # Some entries may have unitName 'KCAL' or only energy present; fallback:
    if kcal_100g == 0.0:
        kcal_100g = _pick_nutrient(nutrients, ["energy"])

    protein_100g = _pick_nutrient(nutrients, ["protein"], unit_prefer="g")
    carbs_100g = _pick_nutrient(nutrients, ["carbohydrate"], unit_prefer="g")
    fat_100g = _pick_nutrient(nutrients, ["total lipid", "fat"], unit_prefer="g")

    return {
        "kcal_100g": kcal_100g,
        "protein_100g": protein_100g,
        "carbs_100g": carbs_100g,
        "fat_100g": fat_100g,
        "fdcId": usda_food.get("fdcId"),
        "description": usda_food.get("description"),
        "brandName": usda_food.get("brandName"),
        "dataType": usda_food.get("dataType"),
    }


@app.get("/usda/search")
def usda_search(query: str = Query(..., min_length=2)):
    try:
        food = usda_search_food(query)
        if not food:
            return {"query": query, "found": False}

        n = usda_extract_macros_per_100g(food)
        return {"query": query, "found": True, **n}
    except Exception as e:
        logger.exception("USDA search failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# -----------------------------
# Gemini Vision helpers
# -----------------------------
def gemini_extract_food_items(img: Image.Image):
    """
    Returns list of items: [{name, grams, confidence}]
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in environment.")

    genai.configure(api_key=GEMINI_API_KEY)

    # You can switch to gemini-1.5-flash for speed/cost, pro for accuracy
    model = genai.GenerativeModel("gemini-1.5-pro")

    prompt = """
You are a nutrition assistant.
Look at the food photo and return ONLY valid JSON array.
Each item must be an object:
{name: string, grams: number, confidence: number between 0 and 1}

Rules:
- Use common food names (e.g., "apple", "rice", "dal", "naan", "chicken curry").
- grams is your best estimate for the portion visible.
- confidence is your confidence in the item identification (0-1).
- Return ONLY JSON. No markdown, no extra text.
"""

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    resp = model.generate_content(
        [
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ],
        generation_config={"temperature": 0.2},
    )

    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty response.")

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise RuntimeError(f"Gemini JSON is not a list: {text[:300]}")
        return parsed
    except Exception:
        raise RuntimeError(f"Gemini returned non-JSON (or invalid JSON): {text[:400]}")


# -----------------------------
# Analyze endpoint: Gemini -> USDA
# -----------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image upload")

    # 1) Gemini detects items + grams
    try:
        ai_items = gemini_extract_food_items(img)
    except Exception as e:
        logger.exception("Gemini extraction failed")
        return JSONResponse({"error": str(e)}, status_code=500)

    enriched_items = []
    total_kcal = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    # 2) USDA lookup for each item
    for it in ai_items:
        name = str(it.get("name", "")).strip()
        grams = float(it.get("grams", 0) or 0)
        confidence = float(it.get("confidence", 0) or 0)

        if not name or grams <= 0:
            continue

        try:
            usda_food = usda_search_food(name)
        except Exception as e:
            usda_food = None
            logger.warning(f"USDA search failed for '{name}': {e}")

        if not usda_food:
            enriched_items.append({
                "name": name,
                "grams": grams,
                "confidence": confidence,
                "kcal": 0.0,
                "macros": {"protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
                "source": "usda",
                "note": "Not found in USDA",
            })
            continue

        n = usda_extract_macros_per_100g(usda_food)

        kcal = (n["kcal_100g"] * grams) / 100.0
        protein = (n["protein_100g"] * grams) / 100.0
        carbs = (n["carbs_100g"] * grams) / 100.0
        fat = (n["fat_100g"] * grams) / 100.0

        total_kcal += kcal
        total_protein += protein
        total_carbs += carbs
        total_fat += fat

        enriched_items.append({
            "name": name,
            "grams": grams,
            "confidence": confidence,
            "kcal": round(kcal, 1),
            "macros": {
                "protein_g": round(protein, 1),
                "carbs_g": round(carbs, 1),
                "fat_g": round(fat, 1),
            },
            "source": "usda",
            "usda": {
                "fdcId": n.get("fdcId"),
                "description": n.get("description"),
                "brandName": n.get("brandName"),
                "dataType": n.get("dataType"),
                "kcal_100g": n.get("kcal_100g"),
                "protein_100g": n.get("protein_100g"),
                "carbs_100g": n.get("carbs_100g"),
                "fat_100g": n.get("fat_100g"),
            },
        })

    return {
        "total_kcal": round(total_kcal, 1),
        "totals": {
            "protein_g": round(total_protein, 1),
            "carbs_g": round(total_carbs, 1),
            "fat_g": round(total_fat, 1),
        },
        "items": enriched_items,
    }

