import io
import os
import json
import time
import logging
import traceback
import datetime as dt
from typing import Any, Dict, Optional, List

import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import google.generativeai as genai

# -------------------- LOGGING --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

# -------------------- APP --------------------
app = FastAPI(title="Kcal Scan API", version="1.0.0")

# --- DEBUG CRASH HANDLER (Fixes silent 502 errors) ---
# This forces the server to print the actual error to the response
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    error_msg = traceback.format_exc()
    logger.error(f"CRASH: {error_msg}")
    return PlainTextResponse(f"SERVER CRASH: {error_msg}", status_code=500)

@app.get("/__whoami")
def whoami():
    return {"whoami": "NEW_BACKEND_WITH_DEBUGGER", "ts": dt.datetime.utcnow().isoformat()}

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

OPENFOODFACTS_BASE = os.getenv("OPENFOODFACTS_BASE", "https://world.openfoodfacts.org/api/v2").strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Table names (Supabase)
TBL_PLAN_LIMITS = "plan_limits"
TBL_USER_USAGE = "user_usage"
TBL_BARCODE = "barcode_products"

# Plans
DEFAULT_PLAN = "free"
PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"]
PLAN_RANK = {p: i for i, p in enumerate(PLAN_ORDER)}

def plan_at_least(current: Any, required: str) -> bool:
    """Return True if current plan >= required."""
    cur = current
    if isinstance(cur, dict):
        cur = cur.get("plan")
    cur = (cur or DEFAULT_PLAN)
    if not isinstance(cur, str):
        cur = str(cur)
    cur = cur.lower().strip()

    req = (required or DEFAULT_PLAN)
    if not isinstance(req, str):
        req = str(req)
    req = req.lower().strip()

    if cur not in PLAN_RANK: cur = DEFAULT_PLAN
    if req not in PLAN_RANK: req = DEFAULT_PLAN

    return PLAN_RANK.get(cur, 0) >= PLAN_RANK.get(req, 0)

def require_plan(current: Any, required: str, feature: str):
    """Raise HTTP 402 when current plan is below required plan."""
    cur = current
    if isinstance(cur, dict):
        cur = cur.get("plan")
    current_plan = (cur or DEFAULT_PLAN)
    if not isinstance(current_plan, str):
        current_plan = str(current_plan)
    current_plan = current_plan.lower().strip()

    if not plan_at_least(current_plan, required):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "upgrade_required",
                "feature": feature,
                "required_plan": required,
                "current_plan": current_plan,
            },
        )

# -------------------- MIDDLEWARE --------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp

# -------------------- BASIC ROUTES --------------------
@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-v1"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "railway-v1"}

@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)

# -------------------- VALIDATION HELPERS --------------------
def _require_usda_key():
    if not USDA_API_KEY:
        raise HTTPException(status_code=500, detail="USDA_API_KEY is not set on the server (Railway Variables).")

def _require_gemini_key():
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set on the server (Railway Variables).")

def _require_supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set on server.")

def _safe_float(x, default=None):
    try:
        if x is None: return default
        return float(x)
    except Exception:
        return default

def _today_date() -> dt.date:
    return dt.datetime.utcnow().date()

def _month_start(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)

def _digits_only(s: str) -> str:
    return "".join([c for c in (s or "").strip() if c.isdigit()])

# -------------------- SUPABASE REST HELPERS --------------------
def supabase_headers() -> Dict[str, str]:
    _require_supabase()
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

def sb_get_one(table: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.get(url, headers=supabase_headers(), params=params, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail={"error": "Supabase read failed", "raw": r.text})
    rows = r.json() or []
    return rows[0] if rows else None

def sb_upsert(table: str, row: Dict[str, Any], on_conflict: str) -> Dict[str, Any]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    params = {"on_conflict": on_conflict}

    r = requests.post(url, headers=headers, params=params, data=json.dumps(row), timeout=20)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail={"error": "Supabase upsert failed", "raw": r.text})

    rows = r.json() or []
    return rows[0] if rows else row

def sb_patch(table: str, match: Dict[str, str], patch: Dict[str, Any]) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"select": "user_id"}
    params.update(match)
    headers = supabase_headers()
    headers["Prefer"] = "return=minimal"
    r = requests.patch(url, headers=headers, params=params, data=json.dumps(patch), timeout=20)
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail={"error": "Supabase update failed", "raw": r.text})


# -------------------- PLAN / USAGE --------------------
def get_plan_limits(plan: str) -> Dict[str, int]:
    """Reads from plan_limits or returns hardcoded defaults."""
    _require_supabase()
    row = sb_get_one(
        TBL_PLAN_LIMITS,
        params={
            "select": "plan,daily_limit,monthly_limit",
            "plan": f"eq.{plan}",
            "limit": "1",
        },
    )
    if not row:
        if plan == "free": return {"daily_limit": 25, "monthly_limit": 25}
        if plan == "elite": return {"daily_limit": 15, "monthly_limit": 50}
        if plan == "advanced": return {"daily_limit": 20, "monthly_limit": 100}
        if plan == "pro": return {"daily_limit": 25, "monthly_limit": 1000}
        if plan == "infinite": return {"daily_limit": 30, "monthly_limit": 10000}
        return {"daily_limit": 3, "monthly_limit": 25}

    return {
        "daily_limit": int(row.get("daily_limit") or 0),
        "monthly_limit": int(row.get("monthly_limit") or 0),
    }

def get_or_init_usage(user_id: str) -> Dict[str, Any]:
    _require_supabase()
    row = sb_get_one(
        TBL_USER_USAGE,
        params={
            "select": "user_id,plan,remaining_day,remaining_month,day_reset,month_reset,updated_at",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    today = _today_date()
    mstart = _month_start(today)

    if not row:
        plan = DEFAULT_PLAN
        lim = get_plan_limits(plan)
        new_row = {
            "user_id": user_id,
            "plan": plan,
            "remaining_day": lim["daily_limit"],
            "remaining_month": lim["monthly_limit"],
            "day_reset": str(today),
            "month_reset": str(mstart),
            "updated_at": dt.datetime.utcnow().isoformat(),
        }
        stored = sb_upsert(TBL_USER_USAGE, new_row, on_conflict="user_id")
        return stored

    return row

def normalize_resets(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    If day/month changed, reset counters to plan limits.
    Now correctly enforces free plan caps if downgrading.
    """
    user_id = row["user_id"]
    plan = (row.get("plan") or DEFAULT_PLAN).lower()

    today = _today_date()
    mstart = _month_start(today)

    def parse_date(x) -> Optional[dt.date]:
        if not x: return None
        if isinstance(x, dt.date): return x
        try: return dt.date.fromisoformat(str(x)[:10])
        except Exception: return None

    day_reset = parse_date(row.get("day_reset"))
    month_reset = parse_date(row.get("month_reset"))

    lim = get_plan_limits(plan)
    patch: Dict[str, Any] = {}

    # === FIX: Enforcement for Free Plan downgrades ===
    if plan == "free":
        # If user is free but has excess scans (from previous Pro), clamp them down
        current_rem_month = int(row.get("remaining_month") or 0)
        if current_rem_month > lim["monthly_limit"]:
            patch["remaining_month"] = lim["monthly_limit"]
            patch["remaining_day"] = lim["daily_limit"]
    
    # Standard Time-based Reset
    if month_reset != mstart:
        if plan != "free": # Free plan doesn't reset monthly (lifetime)
             patch["remaining_month"] = lim["monthly_limit"]
        patch["month_reset"] = str(mstart)

    if day_reset != today:
        patch["remaining_day"] = lim["daily_limit"]
        patch["day_reset"] = str(today)

    if patch:
        patch["updated_at"] = dt.datetime.utcnow().isoformat()
        sb_patch(TBL_USER_USAGE, {"user_id": f"eq.{user_id}"}, patch)
        row.update(patch)

    return row

def consume_one_scan(user_id: str) -> Dict[str, Any]:
    row = get_or_init_usage(user_id)
    row = normalize_resets(row)

    rem_day = int(row.get("remaining_day") or 0)
    rem_month = int(row.get("remaining_month") or 0)

    if rem_day <= 0 or rem_month <= 0:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Scan limit reached",
                "remaining_day": rem_day,
                "remaining_month": rem_month,
                "plan": row.get("plan"),
            },
        )

    rem_day -= 1
    rem_month -= 1
    patch = {
        "remaining_day": rem_day,
        "remaining_month": rem_month,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    sb_patch(TBL_USER_USAGE, {"user_id": f"eq.{user_id}"}, patch)
    row.update(patch)
    return row

def set_user_plan(user_id: str, plan: str) -> Dict[str, Any]:
    """
    Sets the user's plan.
    FIX: Only resets counters if the plan effectively changes.
    """
    plan = (plan or DEFAULT_PLAN).lower()
    if plan not in PLAN_ORDER:
        plan = DEFAULT_PLAN

    # 1. Fetch existing to compare
    existing = get_or_init_usage(user_id)
    current_plan = (existing.get("plan") or DEFAULT_PLAN).lower()

    # If plan is the same, DO NOT reset counters (prevents "Restore" exploit)
    if current_plan == plan:
        return existing

    lim = get_plan_limits(plan)
    today = _today_date()
    mstart = _month_start(today)

    row = {
        "user_id": user_id,
        "plan": plan,
        "remaining_day": lim["daily_limit"],
        "remaining_month": lim["monthly_limit"],
        "day_reset": str(today),
        "month_reset": str(mstart),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    stored = sb_upsert(TBL_USER_USAGE, row, on_conflict="user_id")
    return stored

def get_user_plan(user_id: str) -> str:
    row = get_or_init_usage(user_id)
    return (row.get("plan") or DEFAULT_PLAN).lower()

def require_user_id(x_user_id: Optional[str], user_id: Optional[str]) -> str:
    uid = (x_user_id or user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id. Pass X-User-Id header or ?user_id=...")
    return uid


@app.get("/usage")
def usage(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    row = get_or_init_usage(uid)
    row = normalize_resets(row)
    return {
        "user_id": uid,
        "plan": row.get("plan"),
        "remaining_day": int(row.get("remaining_day") or 0),
        "remaining_month": int(row.get("remaining_month") or 0),
        "day_reset": row.get("day_reset"),
        "month_reset": row.get("month_reset"),
    }

@app.post("/plan/sync")
def plan_sync(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    entitlement = (payload.get("entitlement") or DEFAULT_PLAN).lower()
    stored = set_user_plan(uid, entitlement)
    return {"ok": True, "plan": stored.get("plan")}


# -------------------- USDA --------------------
def usda_search_best(query: str) -> Optional[Dict[str, Any]]:
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
    if not foods: return None
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

def extract_macros_per_100g(food_details: dict) -> Dict[str, float]:
    kcal = protein = carbs = fat = None
    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "")
        name = (nutrient.get("name") or "").lower()
        amount = n.get("amount")
        if amount is None: continue
        unit = (nutrient.get("unitName") or "").lower()

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
        raise HTTPException(status_code=502, detail={"error": "USDA missing macros", "missing": missing})

    return {
        "kcal_per_100g": kcal,
        "protein_g_per_100g": protein,
        "carbs_g_per_100g": carbs,
        "fat_g_per_100g": fat,
    }

# -------------------- GEMINI FOOD DETECTION --------------------
def gemini_detect_foods(image_bytes: bytes) -> List[Dict[str, Any]]:
    _require_gemini_key()
    model = genai.GenerativeModel("gemini-1.5-flash")

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
- Use simple, USDA-friendly names.
- grams must be positive.
- confidence 0..1.
"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    for attempt in range(4):
        try:
            resp = model.generate_content([prompt, img])
            text = (resp.text or "").strip()
            # Cleanup markdown if gemini adds it
            if text.startswith("```json"): text = text[7:]
            if text.endswith("```"): text = text[:-3]
            
            data = json.loads(text)
            items = data.get("items", [])
            cleaned = []
            for it in items:
                name = str(it.get("name", "")).strip()
                grams = float(it.get("grams", 0) or 0)
                conf = float(it.get("confidence", 0) or 0)
                if name and grams > 0:
                    cleaned.append({"name": name, "grams": grams, "confidence": conf})
            if not cleaned: raise ValueError("No items")
            return cleaned
        except Exception:
            time.sleep(0.6 * (attempt + 1))

    raise HTTPException(status_code=502, detail={"error": "Gemini failed / invalid JSON"})

# -------------------- BARCODE --------------------
def openfoodfacts_lookup(barcode: str) -> Dict[str, Any]:
    url = f"{OPENFOODFACTS_BASE}/product/{barcode}.json"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenFoodFacts failed: {r.text}")
    data = r.json() or {}
    if data.get("status") != 1:
        raise HTTPException(status_code=404, detail={"error": "Barcode not found"})

    product = data.get("product") or {}
    nutr = product.get("nutriments") or {}
    kcal_100g = _safe_float(nutr.get("energy-kcal_100g"))
    if kcal_100g is None:
        kj_100g = _safe_float(nutr.get("energy_100g"))
        if kj_100g is not None: kcal_100g = kj_100g / 4.184

    protein = _safe_float(nutr.get("proteins_100g"), 0.0) or 0.0
    carbs = _safe_float(nutr.get("carbohydrates_100g"), 0.0) or 0.0
    fat = _safe_float(nutr.get("fat_100g"), 0.0) or 0.0
    
    if kcal_100g is None:
        raise HTTPException(status_code=502, detail={"error": "OpenFoodFacts missing energy"})

    return {
        "barcode": barcode,
        "name": (product.get("product_name") or product.get("generic_name") or "Unknown").strip(),
        "brand": (product.get("brands") or "").strip() or None,
        "kcal_per_100g": float(kcal_100g),
        "protein_g_per_100g": float(protein),
        "carbs_g_per_100g": float(carbs),
        "fat_g_per_100g": float(fat),
        "serving_size_g": None,
        "source": "openfoodfacts",
        "raw": data,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

def supabase_get_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    _require_supabase()
    return sb_get_one(TBL_BARCODE, params={"barcode": f"eq.{barcode}", "limit": "1"})

def supabase_upsert_barcode(row: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    return sb_upsert(TBL_BARCODE, row, on_conflict="barcode")

@app.get("/barcode/{code}")
def barcode_lookup(
    code: str,
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    plan = get_user_plan(uid)
    require_plan(plan, "elite", feature="barcode")
    usage_row = consume_one_scan(uid)

    barcode = _digits_only(code)
    if not barcode:
        raise HTTPException(status_code=400, detail={"error": "Invalid barcode"})

    cached = supabase_get_barcode(barcode)
    if cached:
        return {
            "source": "barcode", "barcode": cached["barcode"], "name": cached["name"], "brand": cached["brand"],
            "per_100g": {
                "kcal": float(cached["kcal_per_100g"] or 0),
                "protein_g": float(cached["protein_g_per_100g"] or 0),
                "carbs_g": float(cached["carbs_g_per_100g"] or 0),
                "fat_g": float(cached["fat_g_per_100g"] or 0),
            },
            "source_db": cached["source"],
            "usage": usage_row,
        }

    off = openfoodfacts_lookup(barcode)
    stored = supabase_upsert_barcode(off)
    return {
        "source": "barcode", "barcode": stored["barcode"], "name": stored["name"], "brand": stored["brand"],
        "per_100g": {
            "kcal": float(stored["kcal_per_100g"] or 0),
            "protein_g": float(stored["protein_g_per_100g"] or 0),
            "carbs_g": float(stored["carbs_g_per_100g"] or 0),
            "fat_g": float(stored["fat_g_per_100g"] or 0),
        },
        "source_db": "openfoodfacts",
        "usage": usage_row,
    }

# -------------------- COACHING (PRO+) --------------------
LEUCINE_THRESHOLD_G = float(os.getenv("LEUCINE_THRESHOLD_G", "2.5") or 2.5)

PROTEIN_BV_MAP = [
    ("whey", 104), ("isolate", 104), ("casein", 91), ("milk", 91), ("egg", 100),
    ("chicken", 80), ("turkey", 80), ("fish", 83), ("beef", 80), ("pork", 80),
    ("soy", 74), ("tofu", 74), ("lentil", 60), ("beans", 60), ("wheat", 64), ("rice", 60),
]

def estimate_protein_bv(items: List[Dict[str, Any]]) -> int:
    total_p = 0.0
    weighted = 0.0
    for it in items or []:
        name = (it.get("name") or "").lower()
        p = float((it.get("macros") or {}).get("protein_g") or 0.0)
        bv = 70
        for key, val in PROTEIN_BV_MAP:
            if key in name:
                bv = val
                break
        total_p += p
        weighted += p * bv
    if total_p <= 0: return 70
    return int(round(weighted / total_p))

def estimate_glycemic_load(carbs_g: float, items: List[Dict[str, Any]]) -> float:
    # Heuristic: Simple GL estimate
    gl = carbs_g * 0.45 
    names = " ".join([(x.get("name") or "").lower() for x in items])
    if any(s in names for s in ["soda", "sugar", "candy", "cake", "cookie", "syrup", "juice", "chocolate", "ice cream"]):
        gl *= 1.3
    return round(gl, 1)

def estimate_nova_group(items: List[Dict[str, Any]]) -> str:
    names = " ".join([(x.get("name") or "").lower() for x in items])
    ultra = ["cola", "soda", "nugget", "sausage", "hot dog", "instant", "chips", "candy", "cookie", "cake", "protein bar", "margarine"]
    whole = ["egg", "milk", "yogurt", "chicken", "fish", "beef", "rice", "oats", "banana", "apple", "spinach"]
    
    if any(k in names for k in ultra): return "High"
    if any(k in names for k in whole): return "Low"
    return "Medium"

def compute_satiety_score(total_kcal: float, totals: Dict[str, float], total_grams: float) -> int:
    protein_g = float(totals.get("protein_g") or 0.0)
    fat_g = float(totals.get("fat_g") or 0.0)
    carbs_g = float(totals.get("carbs_g") or 0.0)

    if total_kcal <= 0 or total_grams <= 0: return 50
    ed = float(total_kcal) / float(total_grams)
    protein_pct = (protein_g * 4.0 / float(total_kcal)) * 100.0 if total_kcal else 0.0
    
    score = 50.0 + min(25.0, protein_pct * 0.6) + max(-15.0, min(20.0, (1.5 - ed) * 12.0))
    fat_pct = ((fat_g * 9.0) / float(total_kcal)) * 100.0 if total_kcal else 0.0
    if fat_pct > 45: score -= 8
    
    return int(max(0, min(100, round(score))))

def compute_coaching(payload: Dict[str, Any]) -> Dict[str, Any]:
    total_kcal = float(payload.get("total_kcal") or 0.0)
    totals = payload.get("totals") or {}
    items = payload.get("items") or []

    total_grams = sum([float(it.get("grams") or 0) for it in items])
    protein_g = float(totals.get("protein_g") or 0.0)
    carbs_g = float(totals.get("carbs_g") or 0.0)

    leucine_est_g = protein_g * 0.08
    bv = estimate_protein_bv(items)
    bioavailable_protein_g = protein_g * (float(bv) / 100.0)
    satiety = compute_satiety_score(total_kcal, totals, total_grams)
    
    # NEW METRICS
    gly_load = estimate_glycemic_load(carbs_g, items)
    nova = estimate_nova_group(items)

    return {
        "satiety_score": satiety,
        "protein_bv": bv,
        "bioavailable_protein_g": round(bioavailable_protein_g, 1),
        "leucine_g": round(leucine_est_g, 2),
        "mps_threshold_g": LEUCINE_THRESHOLD_G,
        "mps_triggered": bool(leucine_est_g >= LEUCINE_THRESHOLD_G),
        "glycemic_load": gly_load,
        "nova_label": nova
    }

@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    usage_row = consume_one_scan(uid)

    contents = await file.read()
    if not contents: raise HTTPException(status_code=400, detail="Empty file")

    detected_items = gemini_detect_foods(contents)
    
    results = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0

    for d in detected_items:
        name = d["name"]
        grams = float(d["grams"])
        best = usda_search_best(name)
        if not best: continue

        details = usda_food_details(int(best["fdcId"]))
        macros100 = extract_macros_per_100g(details)
        factor = grams / 100.0

        kcal = macros100["kcal_per_100g"] * factor
        p = macros100["protein_g_per_100g"] * factor
        c = macros100["carbs_g_per_100g"] * factor
        f = macros100["fat_g_per_100g"] * factor

        results.append({
            "name": name, "grams": round(grams, 1), "kcal": round(kcal, 1),
            "macros": {"protein_g": round(p, 1), "carbs_g": round(c, 1), "fat_g": round(f, 1)}
        })
        total_kcal += kcal
        total_p += p; total_c += c; total_f += f

    plan = (usage_row.get("plan") or DEFAULT_PLAN).lower()
    coaching_enabled = plan_at_least(plan, "pro")

    response = {
        "source": "photo",
        "total_kcal": round(total_kcal, 1),
        "totals": {"protein_g": round(total_p, 1), "carbs_g": round(total_c, 1), "fat_g": round(total_f, 1)},
        "items": results,
        "usage": usage_row,
    }

    if coaching_enabled:
        response["coaching"] = compute_coaching(response)
    else:
        response["locked"] = {"feature": "coaching", "required_plan": "pro"}

    return response
