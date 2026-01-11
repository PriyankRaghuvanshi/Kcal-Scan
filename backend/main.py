# backend/main.py
import io
import os
import json
import logging
from typing import Any, Dict, List, Optional

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

# ===================== ENV =====================
USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ===================== MIDDLEWARE/ROUTES =====================
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

# ===================== HELPERS =====================
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

def _is_valid_http_url(url: str) -> bool:
    return isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))

# ===================== USDA =====================
def usda_search_best(query: str) -> Optional[Dict[str, Any]]:
    """
    Search USDA and return best candidate.
    Prefer non-Branded first (usually clean nutrient panel), else fallback to top.
    """
    _require_usda_key()
    q = (query or "").strip()
    if not q:
        return None

    payload = {
        "query": q,
        "pageSize": 10,
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

    non_branded = [f for f in foods if f.get("dataType") != "Branded"]
    return non_branded[0] if non_branded else foods[0]

def usda_search_barcode(upc: str) -> Optional[Dict[str, Any]]:
    """
    Search USDA branded foods by UPC/EAN barcode. Prefer exact gtinUpc match.
    """
    _require_usda_key()
    code = (upc or "").strip()
    if not code:
        return None

    payload = {
        "query": code,
        "pageSize": 25,
        "pageNumber": 1,
        "dataType": ["Branded"],
        "requireAllWords": False,
    }

    r = requests.post(
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        json=payload,
        timeout=25,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA barcode search failed: {r.text}")

    foods = (r.json() or {}).get("foods", []) or []
    if not foods:
        return None

    exact = [f for f in foods if str(f.get("gtinUpc") or "").strip() == code]
    return exact[0] if exact else foods[0]

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
    USDA nutrient numbers:
      208 Energy (kcal)
      203 Protein (g)
      205 Carbohydrate (g)
      204 Total lipid (fat) (g)

    Returns per-100g values.
    USDA-only: if missing, raise 502 (no guessing).
    """
    kcal = protein = carbs = fat = None

    for n in (food_details.get("foodNutrients") or []):
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        unit = (nutrient.get("unitName") or "").lower()
        amount = n.get("amount", None)
        if amount is None:
            continue

        if number == "208" or ("energy" in name and "kcal" in unit):
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
        "fat_g": fat,
    }.items() if v is None]

    if missing:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "USDA did not provide required macros per 100g for this item",
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

def extract_macros_branded(food_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Branded foods might not have per-100g nutrient numbers.
    We try per-100g first; else fallback to labelNutrients per serving.

    Returns either:
      - {kcal_per_100g, protein_g_per_100g, ...}
      OR
      - {kcal_per_serving, protein_g_per_serving, ..., servingSize, servingSizeUnit}
    """
    # 1) Try per-100g nutrient numbers (best)
    try:
        return extract_macros_per_100g(food_details)
    except HTTPException:
        pass

    # 2) Fallback: labelNutrients (usually per serving)
    label = food_details.get("labelNutrients") or {}
    if not label:
        raise HTTPException(status_code=502, detail="USDA branded item missing label nutrients")

    kcal = (label.get("calories") or {}).get("value")
    protein = (label.get("protein") or {}).get("value")
    carbs = (label.get("carbohydrates") or {}).get("value")
    fat = (label.get("fat") or {}).get("value")

    missing = [k for k, v in {
        "kcal": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
    }.items() if v is None]

    if missing:
        raise HTTPException(
            status_code=502,
            detail={"error": "Branded label macros missing", "missing": missing},
        )

    return {
        "kcal_per_serving": float(kcal),
        "protein_g_per_serving": float(protein),
        "carbs_g_per_serving": float(carbs),
        "fat_g_per_serving": float(fat),
        "servingSize": food_details.get("servingSize"),
        "servingSizeUnit": food_details.get("servingSizeUnit"),
    }

# ===================== GEMINI FOOD DETECTION =====================
def gemini_detect_foods(image_bytes: bytes) -> List[Dict[str, Any]]:
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
    { "name": "chicken biryani", "grams": 280, "confidence": 0.72 }
  ]
}

Rules:
- Use common, USDA-friendly names.
- grams must be a NUMBER.
- confidence must be a NUMBER from 0 to 1.
- Return at least 1 item. Do NOT return an empty list.
- Do NOT include any explanation text. JSON only.
"""

    # Validate + pass image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    resp = model.generate_content([prompt, img])
    text = (resp.text or "").strip()

    # Parse strict JSON
    try:
        data = json.loads(text)
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError("No items list")

        cleaned: List[Dict[str, Any]] = []
        for it in items:
            name = str(it.get("name", "")).strip()
            grams = float(it.get("grams", 0) or 0)
            conf = float(it.get("confidence", 0) or 0)
            if name and grams > 0:
                cleaned.append({"name": name, "grams": grams, "confidence": conf})

        if not cleaned:
            raise ValueError("No usable items after cleaning")

        return cleaned

    except Exception as e:
        # Return raw to help debug rare Gemini formatting issues
        raise HTTPException(
            status_code=502,
            detail={"error": "Gemini returned invalid JSON", "raw": text, "exception": str(e)},
        )

# ===================== API: BARCODE =====================
@app.get("/barcode/{code}")
def barcode_lookup(code: str):
    """
    Lookup nutrition for a UPC/EAN barcode using USDA Branded.
    """
    best = usda_search_barcode(code)
    if not best:
        raise HTTPException(status_code=404, detail=f"No USDA match for barcode '{code}'")

    fdc_id = int(best["fdcId"])
    details = usda_food_details(fdc_id)
    macros = extract_macros_branded(details)

    return {
        "barcode": code,
        "name": details.get("description"),
        "brand": details.get("brandOwner") or details.get("brandName"),
        "usda": {
            "fdcId": fdc_id,
            "dataType": details.get("dataType"),
            "gtinUpc": details.get("gtinUpc"),
        },
        "macros": macros,
    }

# ===================== API: ANALYZE PHOTO =====================
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate image early
    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    # 1) Detect foods (Gemini)
    detected_items = gemini_detect_foods(contents)
    logger.info(f"Detected items: {detected_items}")

    # 2) USDA macro lookup + totals
    results: List[Dict[str, Any]] = []
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

        # For photo detection, we enforce per-100g nutrient numbers (more consistent).
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
            },
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

