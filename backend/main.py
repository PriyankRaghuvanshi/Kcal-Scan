# backend/main.py
import io
import os
import json
import logging
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

app = FastAPI(title="Kcal Scan API")

# ✅ CORS (wide for now; lock down later)
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


# ------------------- Middleware / Health -------------------
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


# ------------------- Helpers -------------------
def _require_usda_key():
    if not USDA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="USDA_API_KEY is not set on the server (Railway Variables).",
        )


def _require_gemini_key():
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not set on the server (Railway Variables).",
        )


def _to_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def usda_search(query: str, data_types: Optional[List[str]] = None, page_size: int = 8) -> List[Dict[str, Any]]:
    """
    Returns a list of USDA search results (foods).
    """
    _require_usda_key()
    payload = {
        "query": query,
        "pageSize": page_size,
        "pageNumber": 1,
        "requireAllWords": False,
    }
    if data_types:
        payload["dataType"] = data_types

    r = requests.post(
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        json=payload,
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA search failed: {r.text}")

    foods = (r.json() or {}).get("foods", []) or []
    return foods


def usda_search_best(query: str) -> Optional[Dict[str, Any]]:
    """
    Pick best match for a text query.
    Prefer non-branded (cleaner nutrients) first.
    """
    foods = usda_search(
        query=query,
        data_types=["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        page_size=10,
    )
    if not foods:
        return None

    non_branded = [f for f in foods if f.get("dataType") != "Branded"]
    return non_branded[0] if non_branded else foods[0]


def usda_food_details(fdc_id: int) -> Dict[str, Any]:
    _require_usda_key()
    r = requests.get(
        f"{USDA_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA food details failed: {r.text}")
    return r.json()


def extract_macros_per_100g(food_details: Dict[str, Any]) -> Dict[str, float]:
    """
    Returns macros per 100g using nutrient numbers (USDA foodNutrients).
      208 Energy (kcal)
      203 Protein
      205 Carbohydrate, by difference
      204 Total lipid (fat)
    USDA-only, no guessing. If missing, raises 502.
    """
    kcal = protein = carbs = fat = None

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        unit = (nutrient.get("unitName") or "").lower()
        amount = n.get("amount")

        if amount is None:
            continue

        # Energy (kcal) – keep it safe
        if number == "208" or ("energy" in name and "kcal" in unit):
            kcal = float(amount)
        elif number == "203" or name == "protein":
            protein = float(amount)
        elif number == "205" or "carbohydrate" in name:
            carbs = float(amount)
        elif number == "204" or "total lipid" in name:
            fat = float(amount)

    missing = [k for k, v in {"kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat}.items() if v is None]
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
        "kcal_per_100g": float(kcal),
        "protein_g_per_100g": float(protein),
        "carbs_g_per_100g": float(carbs),
        "fat_g_per_100g": float(fat),
    }


def extract_macros_branded_best(food_details: Dict[str, Any]) -> Dict[str, float]:
    """
    For Branded foods:
    - If labelNutrients exist AND servingSize is in grams, convert per-serving -> per-100g
    - Else fallback to nutrient-number extraction
    Also returns default_grams (serving size if known else 100).
    """
    label = food_details.get("labelNutrients") or {}
    serving_size = food_details.get("servingSize")
    serving_unit = (food_details.get("servingSizeUnit") or "").lower()

    # label nutrients typically are per serving (not per 100g) — convert if serving size is grams
    if label and serving_size and ("g" in serving_unit):
        ss = _to_float(serving_size)
        if ss and ss > 0:
            kcal = _to_float((label.get("calories") or {}).get("value"))
            protein = _to_float((label.get("protein") or {}).get("value"))
            carbs = _to_float((label.get("carbohydrates") or {}).get("value"))
            fat = _to_float((label.get("fat") or {}).get("value"))

            if kcal is not None and protein is not None and carbs is not None and fat is not None:
                factor = 100.0 / ss
                return {
                    "kcal_per_100g": kcal * factor,
                    "protein_g_per_100g": protein * factor,
                    "carbs_g_per_100g": carbs * factor,
                    "fat_g_per_100g": fat * factor,
                    "default_grams": float(ss),
                }

    # fallback: nutrient numbers (often per 100g for many items)
    macros = extract_macros_per_100g(food_details)
    macros["default_grams"] = 100.0
    return macros


def gemini_detect_foods(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Gemini returns list of:
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
    { "name": "chicken biryani", "grams": 280, "confidence": 0.72 }
  ]
}

Rules:
- Use common, USDA-friendly names.
- grams must be a number (not a string).
- confidence must be 0 to 1.
- Always return at least 1 item (best guess). Never return empty.
"""

    # Provide image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    resp = model.generate_content([prompt, img])
    text = (resp.text or "").strip()

    try:
        data = json.loads(text)
        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError("No items list")

        cleaned = []
        for it in items:
            name = str(it.get("name", "")).strip()
            grams = _to_float(it.get("grams"))
            conf = _to_float(it.get("confidence")) or 0.0
            if name and grams and grams > 0:
                cleaned.append({"name": name, "grams": float(grams), "confidence": float(conf)})

        if not cleaned:
            raise ValueError("No usable items")
        return cleaned

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "Gemini returned invalid JSON", "raw": text, "exception": str(e)},
        )


# ------------------- Routes -------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Photo -> Gemini detect foods -> USDA macros -> totals.
    """
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

        results.append(
            {
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
                },
            }
        )

        total_kcal += kcal
        total_p += p
        total_c += c
        total_f += f

    return {
        "source": "photo",
        "total_kcal": round(total_kcal, 1),
        "totals": {
            "protein_g": round(total_p, 1),
            "carbs_g": round(total_c, 1),
            "fat_g": round(total_f, 1),
        },
        "items": results,
    }


@app.get("/barcode/{code}")
def barcode_lookup(code: str = Path(..., min_length=6, max_length=18)):
    """
    Barcode (UPC/EAN/GTIN) -> USDA Branded lookup -> return macros.
    Response matches /analyze shape so the app can reuse UI.
    """
    _require_usda_key()
    query = code.strip()

    foods = usda_search(query=query, data_types=["Branded"], page_size=10)
    if not foods:
        raise HTTPException(status_code=404, detail={"error": "No USDA branded match for barcode", "barcode": query})

    # Prefer exact gtinUpc match if present
    exact = [f for f in foods if str(f.get("gtinUpc") or "").strip() == query]
    best = exact[0] if exact else foods[0]

    fdc_id = int(best["fdcId"])
    details = usda_food_details(fdc_id)

    macros100 = extract_macros_branded_best(details)
    grams = float(macros100.get("default_grams") or 100.0)

    factor = grams / 100.0
    kcal = macros100["kcal_per_100g"] * factor
    p = macros100["protein_g_per_100g"] * factor
    c = macros100["carbs_g_per_100g"] * factor
    f = macros100["fat_g_per_100g"] * factor

    item_name = details.get("description") or best.get("description") or "Branded food"

    return {
        "source": "barcode",
        "barcode": query,
        "total_kcal": round(kcal, 1),
        "totals": {
            "protein_g": round(p, 1),
            "carbs_g": round(c, 1),
            "fat_g": round(f, 1),
        },
        "items": [
            {
                "name": item_name,
                "grams": round(grams, 1),  # serving size if known, else 100
                "confidence": 1.0,
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
                    "gtinUpc": details.get("gtinUpc"),
                    "brandOwner": details.get("brandOwner"),
                },
            }
        ],
    }

