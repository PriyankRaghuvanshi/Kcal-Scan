import io
import os
import logging
import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

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

def usda_search(query: str):
    _require_usda_key()

    # Prefer higher-quality data types first; include branded as needed.
    payload = {
        "query": query,
        "pageSize": 5,
        "pageNumber": 1,
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        # You can also restrict with "sortBy": "dataType.keyword", but not required.
    }

    r = requests.post(
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        json=payload,
        timeout=20,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA search failed: {r.text}")

    data = r.json()
    foods = data.get("foods", [])
    if not foods:
        return None
    return foods[0]  # pick best match (we can improve ranking later)

def usda_food_details(fdc_id: int):
    _require_usda_key()

    r = requests.get(
        f"{USDA_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=20,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA food details failed: {r.text}")
    return r.json()

def extract_macros_from_usda(food_details: dict):
    """
    Returns kcal, protein_g, carbs_g, fat_g per 100g — USDA only.
    Supports both:
      - foodNutrients[].nutrient.number + amount
      - labelNutrients (branded)
    """

    # 1) Branded label nutrients (often easiest)
    label = food_details.get("labelNutrients") or {}
    # label keys typically: calories, protein, carbohydrates, fat (units vary; calories is kcal)
    if label:
        kcal = label.get("calories", {}).get("value")
        protein = label.get("protein", {}).get("value")
        carbs = label.get("carbohydrates", {}).get("value")
        fat = label.get("fat", {}).get("value")
        # If these exist, treat them as per serving on label, NOT per 100g.
        # For USDA-only accuracy, we should use foodNutrients per 100g when available.
        # We'll only use labelNutrients if foodNutrients is missing macros entirely.
    else:
        kcal = protein = carbs = fat = None

    # 2) Standard nutrients per 100g (Foundation/Survey/SR Legacy commonly)
    kcal2 = protein2 = carbs2 = fat2 = None

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        amount = n.get("amount")

        if amount is None:
            continue

        # Nutrient numbers are the most stable:
        # 208 Energy (kcal), 203 Protein, 205 Carbs, 204 Total lipid (fat)
        if number == "208" or "energy" in name:
            kcal2 = float(amount)
        elif number == "203" or name == "protein":
            protein2 = float(amount)
        elif number == "205" or "carbohydrate" in name:
            carbs2 = float(amount)
        elif number == "204" or "total lipid" in name or ("fat" in name and "saturated" not in name):
            fat2 = float(amount)

    # Prefer per-100g foodNutrients when available
    kcal_final = kcal2 if kcal2 is not None else kcal
    protein_final = protein2 if protein2 is not None else protein
    carbs_final = carbs2 if carbs2 is not None else carbs
    fat_final = fat2 if fat2 is not None else fat

    # Hard fail if missing: USDA-only, no guessing
    missing = [k for k, v in {
        "kcal": kcal_final,
        "protein_g": protein_final,
        "carbs_g": carbs_final,
        "fat_g": fat_final
    }.items() if v is None]

    if missing:
        # Provide debugging info so we can adjust filters / result choice
        nutrient_numbers = []
        for n in food_details.get("foodNutrients", []) or []:
            nutrient = n.get("nutrient") or {}
            nutrient_numbers.append({
                "number": nutrient.get("number"),
                "name": nutrient.get("name"),
                "amount": n.get("amount"),
                "unit": nutrient.get("unitName"),
            })

        raise HTTPException(
            status_code=502,
            detail={
                "error": "USDA did not provide required macros for this item",
                "missing": missing,
                "fdcId": food_details.get("fdcId"),
                "description": food_details.get("description"),
                "dataType": food_details.get("dataType"),
                "hint": "Try a different USDA match or adjust dataType filters/ranking.",
                "availableNutrientsSample": nutrient_numbers[:25],
                "labelNutrients": food_details.get("labelNutrients"),
            },
        )

    return {
        "kcal_per_100g": float(kcal_final),
        "protein_g_per_100g": float(protein_final),
        "carbs_g_per_100g": float(carbs_final),
        "fat_g_per_100g": float(fat_final),
    }

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()
    _ = Image.open(io.BytesIO(contents)).convert("RGB")

    # -------------------------
    # TODO: Replace this list with your Gemini detection output:
    # Each item should be: { "name": str, "grams": float/int, "confidence": float }
    detected_items = [
        {"name": "cucumber", "grams": 250, "confidence": 0.85},
    ]
    # -------------------------

    results = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0

    for d in detected_items:
        name = d["name"]
        grams = float(d.get("grams") or 0)
        conf = float(d.get("confidence") or 0)

        best = usda_search(name)
        if not best:
            raise HTTPException(status_code=404, detail=f"No USDA match for '{name}'")

        fdc_id = int(best["fdcId"])
        details = usda_food_details(fdc_id)
        macros = extract_macros_from_usda(details)

        factor = grams / 100.0

        kcal = macros["kcal_per_100g"] * factor
        p = macros["protein_g_per_100g"] * factor
        c = macros["carbs_g_per_100g"] * factor
        f = macros["fat_g_per_100g"] * factor

        results.append({
            "name": name,
            "grams": grams,
            "confidence": conf,
            "usda": {
                "fdcId": fdc_id,
                "description": details.get("description"),
                "dataType": details.get("dataType"),
            },
            "kcal": round(kcal, 1),
            "protein_g": round(p, 1),
            "carbs_g": round(c, 1),
            "fat_g": round(f, 1),
        })

        total_kcal += kcal
        total_p += p
        total_c += c
        total_f += f

    return {
        "total_kcal": round(total_kcal, 1),
        "protein_g": round(total_p, 1),
        "carbs_g": round(total_c, 1),
        "fat_g": round(total_f, 1),
        "items": results,
    }

