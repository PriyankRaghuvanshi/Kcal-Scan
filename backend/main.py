import io
import os
import json
import logging
import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

app = FastAPI(title="Kcal Scan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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

def _require_usda_key():
    if not USDA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="USDA_API_KEY is not set on the server (Railway Variables)."
        )

def _require_gemini_key():
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not set on the server (Railway Variables)."
        )

def usda_search_best(query: str):
    _require_usda_key()

    payload = {
        "query": query,
        "pageSize": 8,
        "pageNumber": 1,
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        "requireAllWords": False,
    }

    r = requests.post(
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        json=payload,
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA search failed: {r.text}")

    foods = (r.json() or {}).get("foods", []) or []
    if not foods:
        return None

    # Prefer non-branded first (usually cleaner nutrients); fallback to top result
    non_branded = [f for f in foods if f.get("dataType") != "Branded"]
    return (non_branded[0] if non_branded else foods[0])

def usda_food_details(fdc_id: int):
    _require_usda_key()

    r = requests.get(
        f"{USDA_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA food details failed: {r.text}")
    return r.json()

def extract_macros_per_100g(food_details: dict):
    """
    Returns kcal, protein_g, carbs_g, fat_g per 100g based on foodNutrients nutrient numbers:
      208 Energy (kcal)
      203 Protein
      205 Carbohydrate, by difference
      204 Total lipid (fat)
    USDA-only. No guessing.
    """
    kcal = protein = carbs = fat = None

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        amount = n.get("amount")
        if amount is None:
            continue

        if number == "208" or ("energy" in name and "kcal" in (nutrient.get("unitName") or "").lower()):
            kcal = float(amount)
        elif number == "203" or name == "protein":
            protein = float(amount)
        elif number == "205" or "carbohydrate" in name:
            carbs = float(amount)
        elif number == "204" or "total lipid" in name:
            fat = float(amount)

    missing = [k for k, v in {
        "kcal": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat
    }.items() if v is None]

    if missing:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "USDA did not provide required macros for this item",
                "missing": missing,
                "fdcId": food_details.get("fdcId"),
                "description": food_details.get("description"),
                "dataType": food_details.get("dataType"),
            },
        )

    return {
        "kcal_per_100g": kcal,
        "protein_g_per_100g": protein,
        "carbs_g_per_100g": carbs,
        "fat_g_per_100g": fat,
    }

def gemini_detect_foods(image_bytes: bytes):
    """
    Returns list of:
      { "name": str, "grams": number, "confidence": number }
    """
    _require_gemini_key()

    model = genai.GenerativeModel("gemini-3-flash-preview")

    prompt = """
You are a food recognition assistant.
From the image, detect the foods visible and estimate grams for each item.

Return ONLY valid JSON (no markdown) in this format:
{
  "items": [
    { "name": "chicken biryani", "grams": 280, "confidence": 0.72 },
    ...
  ]
}

Rules:
- Use common, USDA-friendly names.
- grams must be a number.
- confidence from 0 to 1.
- If you are unsure, still return best guess; do NOT return empty.
"""

    # Provide the image as inline data
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    resp = model.generate_content([prompt, img])
    text = (resp.text or "").strip()

    # Attempt to parse JSON safely
    try:
        data = json.loads(text)
        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("No items list")
        cleaned = []
        for it in items:
            name = str(it.get("name", "")).strip()
            grams = float(it.get("grams", 0) or 0)
            conf = float(it.get("confidence", 0) or 0)
            if name and grams > 0:
                cleaned.append({"name": name, "grams": grams, "confidence": conf})
        if not cleaned:
            raise ValueError("No usable items")
        return cleaned
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Gemini returned invalid JSON", "raw": text, "exception": str(e)})

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate image
    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    # 1) Detect foods (Gemini)
    detected_items = gemini_detect_foods(contents)
    logger.info(f"Detected items: {detected_items}")

    # 2) USDA macro lookup + totals
    results = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0

    for d in detected_items:
        name = d["name"]
        grams = float(d["grams"])
        conf = float(d.get("confidence", 0))

        best = usda_search_best(name)
        if not best:
            raise HTTPException(status_code=404, detail=f"No USDA match for '{name}'")

        fdc_id = int(best["fdcId"])
        details = usda_food_details(fdc_id)
        macros100 = extract_macros_per_100g(details)

        factor = grams / 100.0
        kcal = macros100["kcal_per_100g"] * factor
        p = macros100["protein_g_per_100g"] * factor
        c = macros100["carbs_g_per_100g"] * factor
        f = macros100["fat_g_per_100g"] * factor

        results.append({
            "name": name,
            "grams": round(grams, 1),
            "confidence": round(conf, 2),
            "kcal": round(kcal, 1),
            "macros": {
                "protein_g": round(p, 1),
                "carbs_g": round(c, 1),
                "fat_g": round(f, 1),
            },
            "usda": {
                "fdcId": fdc_id,
                "description": details.get("description"),
                "dataType": details.get("dataType"),
            }
        })

        total_kcal += kcal
        total_p += p
        total_c += c
        total_f += f

    return {
        "total_kcal": round(total_kcal, 1),
        "totals": {
            "protein_g": round(total_p, 1),
            "carbs_g": round(total_c, 1),
            "fat_g": round(total_f, 1),
        },
        "items": results,
    }

