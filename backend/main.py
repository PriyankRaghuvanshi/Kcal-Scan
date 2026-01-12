# main.py
import io
import os
import json
import logging
from typing import Any, Dict, Optional

import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import google.generativeai as genai

# Optional (for quota errors) - safe import guard
try:
    from google.api_core.exceptions import ResourceExhausted
except Exception:  # pragma: no cover
    ResourceExhausted = Exception

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

# -------------------- ENV --------------------
USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Supabase (REST / PostgREST) - use SERVICE ROLE only on backend
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# OpenFoodFacts (global barcode DB)
OPENFOODFACTS_BASE = "https://world.openfoodfacts.org/api/v2"

# -------------------- MIDDLEWARE --------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp

# -------------------- BASIC --------------------
@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-v1"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "railway-v1"}

@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)

# -------------------- HELPERS --------------------
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

def _require_supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set on server (Railway Variables).",
        )

def supabase_headers() -> Dict[str, str]:
    # service role key for server-to-server only
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

def _safe_float(x, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

# -------------------- USDA --------------------
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
    """
    kcal = protein = carbs = fat = None

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        amount = n.get("amount")
        if amount is None:
            continue

        unit = (nutrient.get("unitName") or "").lower()

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

# -------------------- GEMINI (IMAGE -> foods list) --------------------
def gemini_detect_foods(image_bytes: bytes):
    """
    Returns list of:
      { "name": str, "grams": number, "confidence": number }
    """
    _require_gemini_key()

    # NOTE: Use a stable model string you’ve already deployed; adjust if needed.
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
- grams must be a number.
- confidence from 0 to 1.
- If you are unsure, still return best guess; do NOT return empty.
"""

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    try:
        resp = model.generate_content([prompt, img])
        text = (resp.text or "").strip()
    except ResourceExhausted as e:
        # Gemini quota exceeded -> return 429 (not 500)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Gemini quota exceeded",
                "hint": "Upgrade Gemini API billing / raise quota / add rate limiting.",
                "exception": str(e),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail={"error": "Gemini call failed", "exception": str(e)})

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
        raise HTTPException(
            status_code=502,
            detail={"error": "Gemini returned invalid JSON", "raw": text, "exception": str(e)},
        )

# -------------------- BARCODE: OpenFoodFacts -> Supabase Cache --------------------
def openfoodfacts_lookup(barcode: str) -> Dict[str, Any]:
    # API v2: /product/{code}.json
    url = f"{OPENFOODFACTS_BASE}/product/{barcode}.json"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenFoodFacts failed: {r.text}")

    data = r.json() or {}
    status = data.get("status")
    if status != 1:
        # Not found
        raise HTTPException(status_code=404, detail={"error": "Barcode not found", "barcode": barcode})

    product = data.get("product") or {}
    nutr = product.get("nutriments") or {}

    # energy: prefer kcal_100g; else kJ -> kcal
    kcal_100g = _safe_float(nutr.get("energy-kcal_100g"))
    if kcal_100g is None:
        kj_100g = _safe_float(nutr.get("energy_100g"))
        if kj_100g is not None:
            kcal_100g = kj_100g / 4.184  # kJ to kcal

    protein = _safe_float(nutr.get("proteins_100g"), 0.0) or 0.0
    carbs = _safe_float(nutr.get("carbohydrates_100g"), 0.0) or 0.0
    fat = _safe_float(nutr.get("fat_100g"), 0.0) or 0.0

    name = (product.get("product_name") or product.get("generic_name") or "").strip()
    brand = (product.get("brands") or "").strip()

    if kcal_100g is None:
        # Still return something, but this is a nutrition gap
        raise HTTPException(
            status_code=502,
            detail={
                "error": "OpenFoodFacts missing energy per 100g",
                "barcode": barcode,
                "name": name,
                "brand": brand,
            },
        )

    return {
        "barcode": barcode,
        "name": name or "Unknown product",
        "brand": brand or None,
        "kcal_per_100g": float(kcal_100g),
        "protein_g_per_100g": float(protein),
        "carbs_g_per_100g": float(carbs),
        "fat_g_per_100g": float(fat),
        "serving_size_g": None,  # per your request: return per 100g only
        "source": "openfoodfacts",
        "raw": data,  # keep full payload for debugging/traceability
    }

def supabase_get_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    _require_supabase()

    # GET single row by barcode
    url = f"{SUPABASE_URL}/rest/v1/barcode_products"
    params = {
        "select": "id,barcode,name,brand,kcal_per_100g,protein_g_per_100g,carbs_g_per_100g,fat_g_per_100g,serving_size_g,source,raw,created_at,updated_at",
        "barcode": f"eq.{barcode}",
        "limit": "1",
    }

    r = requests.get(url, headers=supabase_headers(), params=params, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail={"error": "Supabase read failed", "raw": r.text})

    rows = r.json() or []
    return rows[0] if rows else None

def supabase_upsert_barcode(row: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()

    # UPSERT by barcode
    url = f"{SUPABASE_URL}/rest/v1/barcode_products"
    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    # on_conflict requires unique constraint on barcode
    params = {"on_conflict": "barcode"}

    r = requests.post(url, headers=headers, params=params, data=json.dumps(row), timeout=20)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail={"error": "Supabase upsert failed", "raw": r.text})

    rows = r.json() or []
    return rows[0] if rows else row

@app.get("/barcode/{barcode}")
def barcode_lookup(barcode: str):
    """
    Returns nutrition PER 100g only.
    Flow:
      1) Supabase cache hit -> return
      2) OpenFoodFacts -> normalize -> upsert -> return
    """
    barcode = (barcode or "").strip()
    if not barcode.isdigit() or len(barcode) < 8:
        raise HTTPException(status_code=400, detail={"error": "Invalid barcode", "barcode": barcode})

    # 1) Cache
    cached = supabase_get_barcode(barcode)
    if cached:
        return {
            "barcode": cached.get("barcode"),
            "name": cached.get("name"),
            "brand": cached.get("brand"),
            "per_100g": {
                "kcal": float(cached.get("kcal_per_100g") or 0),
                "protein_g": float(cached.get("protein_g_per_100g") or 0),
                "carbs_g": float(cached.get("carbs_g_per_100g") or 0),
                "fat_g": float(cached.get("fat_g_per_100g") or 0),
            },
            "source": cached.get("source"),
            "cached": True,
        }

    # 2) Global lookup
    off = openfoodfacts_lookup(barcode)

    # 3) Upsert into Supabase
    stored = supabase_upsert_barcode(off)

    return {
        "barcode": stored.get("barcode"),
        "name": stored.get("name"),
        "brand": stored.get("brand"),
        "per_100g": {
            "kcal": float(stored.get("kcal_per_100g") or 0),
            "protein_g": float(stored.get("protein_g_per_100g") or 0),
            "carbs_g": float(stored.get("carbs_g_per_100g") or 0),
            "fat_g": float(stored.get("fat_g_per_100g") or 0),
        },
        "source": stored.get("source") or "openfoodfacts",
        "cached": False,
    }

# -------------------- IMAGE ANALYZE (existing) --------------------
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

