import io
import os
import json
import time
import re
import logging
import requests
from typing import Any, Dict, List, Optional, Tuple
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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview").strip()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ---------------------------
# Middleware / health
# ---------------------------
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


# ---------------------------
# Helpers: env requirements
# ---------------------------
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


# ---------------------------
# Helpers: retries
# ---------------------------
def _sleep_backoff(attempt: int):
    # 0, 0.4, 0.8 seconds
    time.sleep(0.4 * (2 ** max(0, attempt - 1)))

def http_post_json(url: str, *, params: dict, payload: dict, timeout: int = 25, retries: int = 2) -> requests.Response:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, params=params, json=payload, timeout=timeout)
            return r
        except Exception as e:
            last_exc = e
            logger.warning(f"POST retry {attempt}/{retries} failed: {e}")
            _sleep_backoff(attempt)
    raise HTTPException(status_code=502, detail=f"HTTP POST failed after retries: {str(last_exc)}")

def http_get(url: str, *, params: dict, timeout: int = 25, retries: int = 2) -> requests.Response:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            return r
        except Exception as e:
            last_exc = e
            logger.warning(f"GET retry {attempt}/{retries} failed: {e}")
            _sleep_backoff(attempt)
    raise HTTPException(status_code=502, detail=f"HTTP GET failed after retries: {str(last_exc)}")


# ---------------------------
# USDA: search + scoring
# ---------------------------
_DATA_TYPE_WEIGHT = {
    "Foundation": 6,
    "SR Legacy": 5,
    "Survey (FNDDS)": 4,
    "Branded": 1,
}

def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tokenize(s: str) -> List[str]:
    s = _norm(s)
    return [t for t in s.split(" ") if t]

def _score_usda_candidate(query: str, food: dict) -> float:
    """
    Higher is better.
    Combines datatype quality + description match.
    """
    q = _norm(query)
    desc = _norm(food.get("description") or "")
    dt = food.get("dataType") or ""

    score = 0.0
    score += _DATA_TYPE_WEIGHT.get(dt, 0)

    # exact / contains boosts
    if desc == q:
        score += 6
    if q and q in desc:
        score += 4

    # token overlap
    q_tokens = set(_tokenize(q))
    d_tokens = set(_tokenize(desc))
    if q_tokens:
        overlap = len(q_tokens & d_tokens) / max(1, len(q_tokens))
        score += overlap * 4.0

    # penalties for noisy branded descriptions
    if dt == "Branded":
        score -= 1.0
        # product-like descriptions often have tons of tokens
        if len(d_tokens) > 12:
            score -= 0.5

    return score

def usda_search_candidates(query: str, page_size: int = 8) -> List[dict]:
    _require_usda_key()

    payload = {
        "query": query,
        "pageSize": page_size,
        "pageNumber": 1,
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        "requireAllWords": False,
    }

    r = http_post_json(
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        payload=payload,
        timeout=25,
        retries=2,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA search failed: {r.text}")

    foods = (r.json() or {}).get("foods", []) or []
    return foods

def usda_pick_best(query: str, foods: List[dict]) -> Optional[dict]:
    if not foods:
        return None
    scored = [(food, _score_usda_candidate(query, food)) for food in foods]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_food, best_score = scored[0]
    logger.info(f"USDA best match for '{query}': {best_food.get('description')} ({best_food.get('dataType')}) score={best_score:.2f}")
    return best_food

def usda_food_details(fdc_id: int) -> dict:
    _require_usda_key()
    r = http_get(
        f"{USDA_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=25,
        retries=2,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"USDA food details failed: {r.text}")
    return r.json()

def extract_macros_per_100g(food_details: dict) -> dict:
    """
    Returns kcal, protein_g, carbs_g, fat_g per 100g using USDA nutrient numbers:
      208 Energy (kcal)
      268 Energy (kJ) (fallback -> convert to kcal)
      203 Protein
      205 Carbohydrate, by difference
      204 Total lipid (fat)
    USDA-only. No guessing.
    """
    kcal = protein = carbs = fat = None
    kj = None

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        amount = n.get("amount")
        if amount is None:
            continue

        if number == "208":
            kcal = float(amount)
        elif number == "268":
            kj = float(amount)
        elif number == "203":
            protein = float(amount)
        elif number == "205":
            carbs = float(amount)
        elif number == "204":
            fat = float(amount)

    # convert kJ to kcal if kcal missing
    if kcal is None and kj is not None:
        kcal = kj / 4.184

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
        "kcal_per_100g": float(kcal),
        "protein_g_per_100g": float(protein),
        "carbs_g_per_100g": float(carbs),
        "fat_g_per_100g": float(fat),
    }

def usda_lookup_best_macros(query: str) -> Tuple[dict, dict, dict]:
    """
    Try multiple USDA candidates until we find one with complete macros.
    Returns (chosen_search_food, chosen_details, macros100)
    """
    foods = usda_search_candidates(query, page_size=8)
    if not foods:
        raise HTTPException(status_code=404, detail=f"No USDA match for '{query}'")

    # sort by score and try in that order
    scored = [(f, _score_usda_candidate(query, f)) for f in foods]
    scored.sort(key=lambda x: x[1], reverse=True)

    last_err = None
    for food, score in scored[:8]:
        try:
            fdc_id = int(food["fdcId"])
            details = usda_food_details(fdc_id)
            macros100 = extract_macros_per_100g(details)
            logger.info(f"USDA selected fdcId={fdc_id} dt={details.get('dataType')} desc='{details.get('description')}' score={score:.2f}")
            return (food, details, macros100)
        except HTTPException as e:
            last_err = e
            # keep trying next candidate
            continue

    # if we got here, all candidates failed macros extraction
    if last_err:
        raise last_err
    raise HTTPException(status_code=502, detail=f"USDA lookup failed for '{query}' (no usable candidates)")


# ---------------------------
# Gemini: strict JSON + repair
# ---------------------------
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

def _extract_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return None
    return m.group(0).strip()

def _gemini_model():
    return genai.GenerativeModel(GEMINI_MODEL)

def gemini_repair_to_json(raw_text: str) -> Dict[str, Any]:
    """
    Last resort: ask Gemini to convert raw output into strict JSON.
    """
    model = _gemini_model()
    prompt = f"""
Convert the following into STRICT valid JSON ONLY (no markdown, no commentary).
Must match schema:
{{
  "items": [
    {{ "name": "food name", "grams": 123, "confidence": 0.8, "alternates": ["alt1","alt2"] }}
  ]
}}

Text to convert:
{raw_text}
"""
    resp = model.generate_content([prompt])
    fixed = (resp.text or "").strip()
    fixed_json = _extract_json_object(fixed) or fixed
    return json.loads(fixed_json)

def gemini_detect_foods(image_bytes: bytes) -> List[dict]:
    """
    Returns list of:
      { "name": str, "grams": float, "confidence": float, "alternates": [str...] }
    """
    _require_gemini_key()

    model = _gemini_model()

    prompt = """
You are a food recognition assistant.
From the image, detect the foods visible and estimate grams for each item.

Return ONLY valid JSON (no markdown, no explanations) in this format:
{
  "items": [
    { "name": "chicken biryani", "grams": 280, "confidence": 0.72, "alternates": ["veg biryani","pulao"] }
  ]
}

Rules:
- Use common, USDA-friendly names (generic foods).
- grams must be a number > 0.
- confidence must be between 0 and 1.
- alternates must be an array of strings (can be empty).
- If unsure, still return best guess; do NOT return empty items.
"""

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # small retry in case Gemini has transient issues
    last_text = ""
    for attempt in range(3):
        try:
            resp = model.generate_content([prompt, img])
            text = (resp.text or "").strip()
            last_text = text

            # 1) direct parse
            try:
                data = json.loads(text)
            except Exception:
                # 2) extract first {...} and parse
                maybe = _extract_json_object(text)
                if maybe:
                    data = json.loads(maybe)
                else:
                    # 3) repair pass
                    data = gemini_repair_to_json(text)

            items = data.get("items", [])
            if not isinstance(items, list) or not items:
                raise ValueError("No items list")

            cleaned = []
            for it in items:
                name = str(it.get("name", "")).strip()
                grams = float(it.get("grams", 0) or 0)
                conf = float(it.get("confidence", 0) or 0)
                alts = it.get("alternates") or []
                if not isinstance(alts, list):
                    alts = []
                alts = [str(a).strip() for a in alts if str(a).strip()]

                if name and grams > 0:
                    cleaned.append({
                        "name": name,
                        "grams": grams,
                        "confidence": max(0.0, min(1.0, conf)),
                        "alternates": alts[:5],
                    })

            if not cleaned:
                raise ValueError("No usable items after cleaning")

            return cleaned

        except Exception as e:
            logger.warning(f"Gemini detect attempt {attempt}/2 failed: {e}")
            _sleep_backoff(attempt)

    raise HTTPException(
        status_code=502,
        detail={"error": "Gemini returned invalid JSON", "raw": last_text[:4000]},
    )


# ---------------------------
# API: /analyze
# ---------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    # validate image
    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    # 1) detect foods
    detected_items = gemini_detect_foods(contents)
    logger.info(f"Detected items: {detected_items}")

    # 2) USDA lookup for each item (+ alternates)
    results = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0

    for d in detected_items:
        grams = float(d["grams"])
        conf = float(d.get("confidence", 0))

        # Try main name first, then alternates if USDA fails
        queries_to_try = [d["name"]] + (d.get("alternates") or [])

        chosen_food = chosen_details = chosen_macros100 = None
        chosen_query = None
        last_err = None

        for q in queries_to_try[:6]:
            try:
                food, details, macros100 = usda_lookup_best_macros(q)
                chosen_food, chosen_details, chosen_macros100 = food, details, macros100
                chosen_query = q
                break
            except HTTPException as e:
                last_err = e
                continue

        if not chosen_details or not chosen_macros100:
            # USDA-only: hard fail after trying candidates/alternates
            if last_err:
                raise last_err
            raise HTTPException(status_code=502, detail=f"USDA lookup failed for item '{d['name']}'")

        factor = grams / 100.0
        kcal = chosen_macros100["kcal_per_100g"] * factor
        p = chosen_macros100["protein_g_per_100g"] * factor
        c = chosen_macros100["carbs_g_per_100g"] * factor
        f = chosen_macros100["fat_g_per_100g"] * factor

        results.append({
            "name": d["name"],
            "grams": round(grams, 1),
            "confidence": round(conf, 2),
            "kcal": round(kcal, 1),
            "macros": {
                "protein_g": round(p, 1),
                "carbs_g": round(c, 1),
                "fat_g": round(f, 1),
            },
            "usda": {
                "matched_query": chosen_query,
                "fdcId": int(chosen_details.get("fdcId")),
                "description": chosen_details.get("description"),
                "dataType": chosen_details.get("dataType"),
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

