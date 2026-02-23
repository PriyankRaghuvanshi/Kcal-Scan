import io
import os
import json
import time
import re
import hashlib
import logging
import datetime as dt
from typing import Any, Dict, Optional, List
from zoneinfo import ZoneInfo

import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import google.generativeai as genai
import coach_daily_logic as coach_logic

# -------------------- LOGGING --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

# -------------------- APP --------------------
app = FastAPI(title="Kcal Scan API", version="1.0.0")

@app.get("/__whoami")
def whoami():
    return {"whoami": "NEW_BACKEND_WITH_USAGE", "ts": dt.datetime.utcnow().isoformat()}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later
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
TBL_USER_GOALS = "user_goals"
TBL_DAILY_TOTALS = "daily_totals"
TBL_DAILY_SUMMARY = "daily_summary"
TBL_MEAL_EVENTS = "meal_events"
TBL_DAILY_METRICS = "daily_metrics"
TBL_WEEKLY_INSIGHTS = "weekly_insights"

# Plans (your requirements)
DEFAULT_PLAN = "free"
PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"]
COACH_LLM_MODEL = os.getenv("COACH_LLM_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
BEHAVIOR_ENGINE_VERSION = "phase_3_1_v1"

# Goal defaults used when an older schema is missing one or more goal columns.
DEFAULT_DAILY_GOALS = {
    "kcal": 2000.0,
    "protein_g": 150.0,
    "carbs_g": 200.0,
    "fat_g": 70.0,
    "fiber_g": 30.0,
}


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
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _parse_tz_offset_min(v: Optional[Any]) -> Optional[int]:
    if v is None:
        return None
    try:
        n = int(float(v))
    except Exception:
        return None
    if n < -840 or n > 840:
        return None
    return n

def _today_date(tz: Optional[str] = None, tz_offset_min: Optional[Any] = None) -> dt.date:
    """
    Returns "today" in client local time when timezone info is provided.
    Fallback is UTC date for backward compatibility.
    """
    now_utc = dt.datetime.now(dt.timezone.utc)
    tz_name = (tz or "").strip()
    if tz_name:
        try:
            return now_utc.astimezone(ZoneInfo(tz_name)).date()
        except Exception:
            logger.warning(f"Invalid timezone '{tz_name}', falling back to offset/UTC.")

    off = _parse_tz_offset_min(tz_offset_min)
    if off is not None:
        return (now_utc + dt.timedelta(minutes=off)).date()

    return now_utc.date()

def _month_start(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)

def _digits_only(s: str) -> str:
    return "".join([c for c in (s or "").strip() if c.isdigit()])


# -------------------- PLAN GATING HELPERS (NEW) --------------------
def plan_at_least(current: str, required: str) -> bool:
    try:
        return PLAN_ORDER.index((current or DEFAULT_PLAN).lower()) >= PLAN_ORDER.index(required.lower())
    except ValueError:
        return False

def require_plan(current: str, required: str, feature: str):
    if not plan_at_least(current, required):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "upgrade_required",
                "feature": feature,
                "required_plan": required,
                "current_plan": (current or DEFAULT_PLAN).lower(),
            },
        )


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


def sb_get_many(table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.get(url, headers=supabase_headers(), params=params, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail={"error": "Supabase list read failed", "raw": r.text})
    rows = r.json() or []
    return rows if isinstance(rows, list) else []

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

def sb_insert(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = supabase_headers()
    headers["Prefer"] = "return=representation"
    r = requests.post(url, headers=headers, data=json.dumps(row), timeout=20)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail={"error": "Supabase insert failed", "raw": r.text})
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


def _http_exc_raw(e: Exception) -> str:
    if isinstance(e, HTTPException):
        detail = e.detail if isinstance(e.detail, dict) else {"raw": str(e.detail)}
        return str(detail.get("raw") or detail.get("error") or detail)
    return str(e)


def _extract_unknown_column(raw: str) -> Optional[str]:
    text = raw or ""
    patterns = [
        r'column "([^"]+)"',
        r"column '([^']+)'",
        r"Could not find the '([^']+)' column",
        r"record .* has no field \"([^\"]+)\"",
        r"record .* has no field '([^']+)'",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _sb_insert_with_column_fallback(table: str, row: Dict[str, Any], locked_cols: Optional[set] = None) -> Dict[str, Any]:
    payload = dict(row or {})
    locked = locked_cols or set()
    max_attempts = max(1, len(payload))
    for _ in range(max_attempts):
        try:
            return sb_insert(table, payload)
        except Exception as e:
            raw = _http_exc_raw(e)
            bad_col = _extract_unknown_column(raw)
            if bad_col and bad_col in payload and bad_col not in locked:
                logger.warning(f"Dropping unknown column during insert: {bad_col}")
                payload.pop(bad_col, None)
                continue
            raise
    return payload


def _sb_patch_with_column_fallback(table: str, match: Dict[str, str], patch: Dict[str, Any], locked_cols: Optional[set] = None) -> Dict[str, Any]:
    payload = dict(patch or {})
    locked = locked_cols or set()
    max_attempts = max(1, len(payload))
    for _ in range(max_attempts):
        try:
            sb_patch(table, match, payload)
            return payload
        except Exception as e:
            raw = _http_exc_raw(e)
            bad_col = _extract_unknown_column(raw)
            if bad_col and bad_col in payload and bad_col not in locked:
                logger.warning(f"Dropping unknown column during patch: {bad_col}")
                payload.pop(bad_col, None)
                continue
            raise
    return payload



# -------------------- GOALS / DAILY TOTALS --------------------
GOAL_KEY_ALIASES = {
    "kcal": ("kcal", "kcal_goal"),
    "protein_g": ("protein_g", "protein_goal_g"),
    "carbs_g": ("carbs_g", "carbs_goal_g"),
    "fat_g": ("fat_g", "fat_goal_g"),
    "fiber_g": ("fiber_g", "fiber_goal_g"),
    "vitamin_d_ug": ("vitamin_d_ug", "vitamin_d_goal_ug"),
    "vitamin_b12_ug": ("vitamin_b12_ug", "vitamin_b12_goal_ug"),
    "iron_mg": ("iron_mg", "iron_goal_mg"),
    "magnesium_mg": ("magnesium_mg", "magnesium_goal_mg"),
}
GOAL_STORAGE_MODERN = {
    "kcal_goal": ("kcal_goal", "kcal"),
    "protein_goal_g": ("protein_goal_g", "protein_g"),
    "carbs_goal_g": ("carbs_goal_g", "carbs_g"),
    "fat_goal_g": ("fat_goal_g", "fat_g"),
    "fiber_goal_g": ("fiber_goal_g", "fiber_g"),
    "vitamin_d_goal_ug": ("vitamin_d_goal_ug", "vitamin_d_ug"),
    "vitamin_b12_goal_ug": ("vitamin_b12_goal_ug", "vitamin_b12_ug"),
    "iron_goal_mg": ("iron_goal_mg", "iron_mg"),
    "magnesium_goal_mg": ("magnesium_goal_mg", "magnesium_mg"),
}
GOAL_STORAGE_LEGACY = {
    "kcal": ("kcal", "kcal_goal"),
    "protein_g": ("protein_g", "protein_goal_g"),
    "carbs_g": ("carbs_g", "carbs_goal_g"),
    "fat_g": ("fat_g", "fat_goal_g"),
    "fiber_g": ("fiber_g", "fiber_goal_g"),
    "vitamin_d_ug": ("vitamin_d_ug", "vitamin_d_goal_ug"),
    "vitamin_b12_ug": ("vitamin_b12_ug", "vitamin_b12_goal_ug"),
    "iron_mg": ("iron_mg", "iron_goal_mg"),
    "magnesium_mg": ("magnesium_mg", "magnesium_goal_mg"),
}


def _first_present_float(src: Dict[str, Any], keys: tuple) -> Optional[float]:
    for k in keys:
        if k in src and src.get(k) is not None:
            v = _safe_float(src.get(k))
            if v is not None:
                return v
    return None


def _normalize_goals_record(user_id: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = row or {}
    out: Dict[str, Any] = {
        "user_id": src.get("user_id") or user_id,
        "updated_at": src.get("updated_at"),
    }
    for canonical, aliases in GOAL_KEY_ALIASES.items():
        val = _first_present_float(src, aliases)
        if val is None and canonical in DEFAULT_DAILY_GOALS:
            val = float(DEFAULT_DAILY_GOALS[canonical])
        out[canonical] = val

    # Backward compatibility for older clients expecting *_goal fields.
    out["kcal_goal"] = out.get("kcal")
    out["protein_goal_g"] = out.get("protein_g")
    out["carbs_goal_g"] = out.get("carbs_g")
    out["fat_goal_g"] = out.get("fat_g")
    out["fiber_goal_g"] = out.get("fiber_g")
    out["vitamin_d_goal_ug"] = out.get("vitamin_d_ug")
    out["vitamin_b12_goal_ug"] = out.get("vitamin_b12_ug")
    out["iron_goal_mg"] = out.get("iron_mg")
    out["magnesium_goal_mg"] = out.get("magnesium_mg")
    return out


def _goal_payload_for_storage(user_id: str, goals: Dict[str, Any], mapping: Dict[str, tuple]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {"user_id": user_id, "updated_at": dt.datetime.utcnow().isoformat()}
    src = goals or {}
    for target, aliases in mapping.items():
        v = _first_present_float(src, aliases)
        if v is not None:
            clean[target] = v
    return clean


def _merge_missing_goal_values_for_response(
    user_id: str,
    normalized: Dict[str, Any],
    persisted_row: Optional[Dict[str, Any]],
    incoming: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    If some goal columns are absent in DB schema (for example, fiber_goal_g),
    preserve the just-sent values in API response so UI remains consistent.
    """
    out = dict(normalized or {})
    src = persisted_row or {}
    incoming_norm = _normalize_goals_record(user_id, incoming or {})
    for canonical, aliases in GOAL_KEY_ALIASES.items():
        persisted_val = _first_present_float(src, aliases)
        if persisted_val is None and incoming_norm.get(canonical) is not None:
            out[canonical] = incoming_norm.get(canonical)

    out["kcal_goal"] = out.get("kcal")
    out["protein_goal_g"] = out.get("protein_g")
    out["carbs_goal_g"] = out.get("carbs_g")
    out["fat_goal_g"] = out.get("fat_g")
    out["fiber_goal_g"] = out.get("fiber_g")
    out["vitamin_d_goal_ug"] = out.get("vitamin_d_ug")
    out["vitamin_b12_goal_ug"] = out.get("vitamin_b12_ug")
    out["iron_goal_mg"] = out.get("iron_mg")
    out["magnesium_goal_mg"] = out.get("magnesium_mg")
    return out


def _sb_upsert_with_column_fallback(table: str, row: Dict[str, Any], on_conflict: str) -> Dict[str, Any]:
    """
    Tries upsert and drops unknown columns if schema differs across deploys.
    """
    payload = dict(row or {})
    max_attempts = max(1, len(payload))
    for _ in range(max_attempts):
        try:
            return sb_upsert(table, payload, on_conflict=on_conflict)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {"raw": str(e.detail)}
            raw = str(detail.get("raw") or "")
            m = re.search(r'column "([^"]+)"', raw)
            if m:
                bad_col = m.group(1)
                if bad_col in payload and bad_col not in ("user_id",):
                    logger.warning(f"Dropping unknown column during upsert: {bad_col}")
                    payload.pop(bad_col, None)
                    continue
            raise
    return payload


def get_user_goals_raw(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Reads from user_goals (recommended schema):
      user_id uuid primary key references auth.users(id),
      kcal_goal numeric,
      protein_goal_g numeric,
      carbs_goal_g numeric,
      fat_goal_g numeric,
      vitamin_d_goal_ug numeric,
      vitamin_b12_goal_ug numeric,
      iron_goal_mg numeric,
      magnesium_goal_mg numeric,
      updated_at timestamptz not null default now()
    All fields optional; app can show remaining if present.
    """
    _require_supabase()
    row = sb_get_one(
        TBL_USER_GOALS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    return row


def get_user_goals(user_id: str) -> Dict[str, Any]:
    return _normalize_goals_record(user_id, get_user_goals_raw(user_id))


def upsert_user_goals(user_id: str, goals: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    incoming = goals or {}
    existing = get_user_goals_raw(user_id) or {}

    has_legacy_cols = any(k in existing for k in GOAL_STORAGE_LEGACY.keys())
    write_orders = (
        (GOAL_STORAGE_LEGACY, GOAL_STORAGE_MODERN)
        if has_legacy_cols
        else (GOAL_STORAGE_MODERN, GOAL_STORAGE_LEGACY)
    )

    last_err: Optional[Exception] = None
    for mapping in write_orders:
        clean = _goal_payload_for_storage(user_id, incoming, mapping)
        if len(clean.keys()) <= 2:
            continue
        try:
            if existing:
                patch_payload = {k: v for k, v in clean.items() if k != "user_id"}
                _sb_patch_with_column_fallback(
                    TBL_USER_GOALS,
                    {"user_id": f"eq.{user_id}"},
                    patch_payload,
                )
                refreshed = get_user_goals_raw(user_id)
                stored = refreshed if refreshed else clean
            else:
                stored = _sb_insert_with_column_fallback(
                    TBL_USER_GOALS,
                    clean,
                    locked_cols={"user_id"},
                )
            normalized = _normalize_goals_record(user_id, stored)
            return _merge_missing_goal_values_for_response(user_id, normalized, stored, incoming)
        except Exception as e:
            last_err = e
            continue

    # Final fallback: patch only columns that actually exist in the current row.
    # This prevents one missing column (e.g., carbs_g) from blocking all goal updates.
    if existing:
        try:
            patch_payload: Dict[str, Any] = {"updated_at": dt.datetime.utcnow().isoformat()}
            existing_cols = {k for k in existing.keys() if k not in {"user_id", "updated_at"}}
            for col in sorted(existing_cols):
                v = _first_present_float(incoming, (col,))
                if v is not None:
                    patch_payload[col] = v
            if len(patch_payload.keys()) > 1:
                _sb_patch_with_column_fallback(TBL_USER_GOALS, {"user_id": f"eq.{user_id}"}, patch_payload)
                refreshed = get_user_goals_raw(user_id)
                base_row = refreshed if refreshed else existing
                normalized = _normalize_goals_record(user_id, base_row)
                return _merge_missing_goal_values_for_response(user_id, normalized, base_row, incoming)
        except Exception as e:
            last_err = e

    if last_err:
        raise last_err
    return get_user_goals(user_id)

def _day_iso(d: Optional[str], tz: Optional[str] = None, tz_offset_min: Optional[Any] = None) -> str:
    if d:
        try:
            return dt.date.fromisoformat(str(d)[:10]).isoformat()
        except Exception:
            pass
    return _today_date(tz=tz, tz_offset_min=tz_offset_min).isoformat()


def _iso_to_date_safe(v: Optional[str], fallback: Optional[dt.date] = None) -> dt.date:
    if v:
        try:
            return dt.date.fromisoformat(str(v)[:10])
        except Exception:
            pass
    return fallback or _today_date()


def _week_start_monday(day_iso: Optional[str]) -> str:
    d = _iso_to_date_safe(day_iso)
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def _week_end_from_start(week_start_iso: str) -> str:
    ws = _iso_to_date_safe(week_start_iso)
    return (ws + dt.timedelta(days=6)).isoformat()


def _event_local_context(
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> Dict[str, Any]:
    now_utc = dt.datetime.now(dt.timezone.utc)
    local_dt: dt.datetime
    tz_name = (tz or "").strip()
    if tz_name:
        try:
            local_dt = now_utc.astimezone(ZoneInfo(tz_name))
        except Exception:
            off = _parse_tz_offset_min(tz_offset_min)
            if off is None:
                local_dt = now_utc
            else:
                local_dt = now_utc + dt.timedelta(minutes=off)
    else:
        off = _parse_tz_offset_min(tz_offset_min)
        local_dt = now_utc if off is None else now_utc + dt.timedelta(minutes=off)

    return {
        "created_at_utc": now_utc.isoformat(),
        "event_day_local": local_dt.date().isoformat(),
        "event_hour_local": int(local_dt.hour),
        "event_time_local": local_dt.isoformat(),
        "tz": tz_name or None,
        "tz_offset_min": _parse_tz_offset_min(tz_offset_min),
    }

DAILY_VALUE_ALIASES = {
    "total_kcal": ("total_kcal", "kcal", "calories"),
    "protein_g": ("protein_g", "protein"),
    "carbs_g": ("carbs_g", "carbs", "carbohydrates_g"),
    "fat_g": ("fat_g", "fat"),
    "fiber_g": ("fiber_g",),
    "sugar_g": ("sugar_g",),
    "sodium_mg": ("sodium_mg",),
    "vitamin_d_ug": ("vitamin_d_ug",),
    "vitamin_b12_ug": ("vitamin_b12_ug",),
    "iron_mg": ("iron_mg",),
    "magnesium_mg": ("magnesium_mg",),
}
DAILY_STORAGE_MODERN = {k: k for k in DAILY_VALUE_ALIASES.keys()}
DAILY_STORAGE_LEGACY = {**DAILY_STORAGE_MODERN, "total_kcal": "kcal"}


def _normalize_daily_values(src: Optional[Dict[str, Any]]) -> Dict[str, float]:
    row = src or {}
    out: Dict[str, float] = {}
    for canonical, aliases in DAILY_VALUE_ALIASES.items():
        out[canonical] = _first_present_float(row, aliases) or 0.0
    return out


def _normalize_daily_totals_record(user_id: str, day_iso: str, row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    src = row or {}
    vals = _normalize_daily_values(src)
    out: Dict[str, Any] = {
        "user_id": src.get("user_id") or user_id,
        "day": src.get("day") or day_iso,
        "updated_at": src.get("updated_at"),
    }
    out.update(vals)
    # App compatibility alias
    out["kcal"] = out.get("total_kcal", 0.0)
    return out


def _daily_payload_for_storage(user_id: str, day_iso: str, values: Dict[str, float], mapping: Dict[str, str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"user_id": user_id, "day": day_iso, "updated_at": dt.datetime.utcnow().isoformat()}
    for canonical, target_col in mapping.items():
        payload[target_col] = float(values.get(canonical) or 0.0)
    return payload


def get_daily_totals(
    user_id: str,
    day: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Reads from daily_totals (recommended schema):
      user_id uuid,
      day date,
      total_kcal numeric default 0,
      protein_g numeric default 0,
      carbs_g numeric default 0,
      fat_g numeric default 0,
      fiber_g numeric default 0,
      sugar_g numeric default 0,
      sodium_mg numeric default 0,
      vitamin_d_ug numeric default 0,
      vitamin_b12_ug numeric default 0,
      iron_mg numeric default 0,
      magnesium_mg numeric default 0,
      updated_at timestamptz not null default now(),
      primary key (user_id, day)
    """
    _require_supabase()
    day_iso = _day_iso(day, tz=tz, tz_offset_min=tz_offset_min)
    raw = sb_get_one(
        TBL_DAILY_TOTALS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "day": f"eq.{day_iso}",
            "limit": "1",
        },
    )
    return _normalize_daily_totals_record(user_id, day_iso, raw)

def add_to_daily_totals(
    user_id: str,
    increments: Dict[str, Any],
    day: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Adds the meal totals to daily_totals row for (user_id, day).
    Non-atomic read+write is OK for MVP.
    """
    _require_supabase()
    day_iso = _day_iso(day, tz=tz, tz_offset_min=tz_offset_min)
    raw_current = sb_get_one(
        TBL_DAILY_TOTALS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "day": f"eq.{day_iso}",
            "limit": "1",
        },
    )
    current_vals = _normalize_daily_values(raw_current)
    increment_vals = _normalize_daily_values(increments)

    next_vals: Dict[str, float] = {}
    for k in DAILY_VALUE_ALIASES.keys():
        next_vals[k] = float(current_vals.get(k, 0.0)) + float(increment_vals.get(k, 0.0))

    has_legacy_kcal = bool(raw_current and "kcal" in raw_current and "total_kcal" not in raw_current)
    mapping_order = (
        (DAILY_STORAGE_LEGACY, DAILY_STORAGE_MODERN)
        if has_legacy_kcal
        else (DAILY_STORAGE_MODERN, DAILY_STORAGE_LEGACY)
    )

    last_err: Optional[Exception] = None
    for mapping in mapping_order:
        payload = _daily_payload_for_storage(user_id, day_iso, next_vals, mapping)
        try:
            if raw_current:
                patch_payload = {k: v for k, v in payload.items() if k not in ("user_id", "day")}
                _sb_patch_with_column_fallback(
                    TBL_DAILY_TOTALS,
                    {"user_id": f"eq.{user_id}", "day": f"eq.{day_iso}"},
                    patch_payload,
                )
                refreshed = sb_get_one(
                    TBL_DAILY_TOTALS,
                    params={
                        "select": "*",
                        "user_id": f"eq.{user_id}",
                        "day": f"eq.{day_iso}",
                        "limit": "1",
                    },
                )
                stored = refreshed if refreshed else payload
            else:
                stored = _sb_insert_with_column_fallback(
                    TBL_DAILY_TOTALS,
                    payload,
                    locked_cols={"user_id", "day"},
                )
            return _normalize_daily_totals_record(user_id, day_iso, stored)
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return _normalize_daily_totals_record(user_id, day_iso, {"user_id": user_id, "day": day_iso, **next_vals})

def build_daily_summary(
    user_id: str,
    day: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> Dict[str, Any]:
    totals = dict(get_daily_totals(user_id, day, tz=tz, tz_offset_min=tz_offset_min) or {})
    totals["kcal"] = _safe_float(totals.get("total_kcal"), 0.0) or 0.0
    totals["micros"] = {
        "fiber_g": _safe_float(totals.get("fiber_g"), 0.0) or 0.0,
        "vitamin_d_ug": _safe_float(totals.get("vitamin_d_ug"), 0.0) or 0.0,
        "vitamin_b12_ug": _safe_float(totals.get("vitamin_b12_ug"), 0.0) or 0.0,
        "iron_mg": _safe_float(totals.get("iron_mg"), 0.0) or 0.0,
        "magnesium_mg": _safe_float(totals.get("magnesium_mg"), 0.0) or 0.0,
        "sodium_mg": _safe_float(totals.get("sodium_mg"), 0.0) or 0.0,
    }
    goals = get_user_goals(user_id)

    def num(x):
        try:
            return float(x)
        except Exception:
            return None

    # compute remaining where goal exists; expose both legacy and app-friendly key names
    remaining = {}
    mapping = [
        ("kcal", "total_kcal", "kcal"),
        ("protein_g", "protein_g", "protein_g"),
        ("carbs_g", "carbs_g", "carbs_g"),
        ("fat_g", "fat_g", "fat_g"),
        ("fiber_g", "fiber_g", "fiber_g"),
        ("vitamin_d_ug", "vitamin_d_ug", "vitamin_d_ug"),
        ("vitamin_b12_ug", "vitamin_b12_ug", "vitamin_b12_ug"),
        ("iron_mg", "iron_mg", "iron_mg"),
        ("magnesium_mg", "magnesium_mg", "magnesium_mg"),
    ]
    for gk, tk, outk in mapping:
        g = num(goals.get(gk))
        t = num(totals.get(tk))
        if g is not None and t is not None:
            left = max(0.0, g - t)
            remaining[outk] = left
            remaining[f"{outk}_left"] = left

    return {"day": totals.get("day"), "totals": totals, "goals": goals, "remaining": remaining}


# -------------------- PHASE 3.1: BEHAVIOR MEMORY --------------------
def _safe_avg(vals: List[float]) -> float:
    arr = [float(v) for v in vals if v is not None]
    if not arr:
        return 0.0
    return sum(arr) / max(1, len(arr))


def _pct(consumed: float, goal: float) -> float:
    g = float(goal or 0.0)
    if g <= 0:
        return 0.0
    return max(0.0, min(400.0, (float(consumed or 0.0) / g) * 100.0))


def _event_bucket_from_hour(hour: Optional[Any]) -> str:
    h = int(_safe_float(hour, -1) or -1)
    if 5 <= h < 11:
        return "breakfast"
    if 11 <= h < 16:
        return "lunch"
    if 16 <= h < 22:
        return "dinner"
    return "snack"


def _event_num(row: Dict[str, Any], key: str, *aliases: str) -> float:
    src = row if isinstance(row, dict) else {}
    nested = src.get("event_json") if isinstance(src.get("event_json"), dict) else {}
    for k in (key, *aliases):
        if k in src and src.get(k) is not None:
            return float(_safe_float(src.get(k), 0.0) or 0.0)
        if k in nested and nested.get(k) is not None:
            return float(_safe_float(nested.get(k), 0.0) or 0.0)
    return 0.0


def _event_text(row: Dict[str, Any], key: str, *aliases: str) -> str:
    src = row if isinstance(row, dict) else {}
    nested = src.get("event_json") if isinstance(src.get("event_json"), dict) else {}
    for k in (key, *aliases):
        v = src.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
        v2 = nested.get(k)
        if v2 is not None and str(v2).strip():
            return str(v2).strip()
    return ""


def _day_score_from_metric_row(row: Dict[str, Any]) -> float:
    protein_hit = _event_num(row, "protein_hit_pct")
    fiber_hit = _event_num(row, "fiber_hit_pct")
    gl = _event_num(row, "avg_glycemic_load")
    upf = _event_num(row, "ultra_processed_avg")
    late_pct = _event_num(row, "late_calories_pct")
    kcal_delta_pct = abs(_event_num(row, "kcal_delta_pct"))
    score = (
        100.0
        - max(0.0, 100.0 - protein_hit) * 0.24
        - max(0.0, 100.0 - fiber_hit) * 0.16
        - max(0.0, gl - 12.0) * 1.6
        - max(0.0, upf - 2.5) * 6.0
        - max(0.0, late_pct - 35.0) * 0.8
        - max(0.0, kcal_delta_pct - 10.0) * 0.45
    )
    return max(0.0, min(100.0, score))


def _extract_metric_val(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    if not isinstance(row, dict):
        return float(default)
    nested = row.get("metrics_json")
    if isinstance(nested, dict) and nested.get(key) is not None:
        return float(_safe_float(nested.get(key), default) or default)
    return float(_safe_float(row.get(key), default) or default)


def _extract_metric_text(row: Dict[str, Any], key: str, default: str = "") -> str:
    if not isinstance(row, dict):
        return default
    nested = row.get("metrics_json")
    if isinstance(nested, dict) and nested.get(key) is not None and str(nested.get(key)).strip():
        return str(nested.get(key)).strip()
    raw = row.get(key)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return default


def _longest_streak(rows: List[Dict[str, Any]], pred) -> int:
    best = 0
    cur = 0
    for r in rows:
        if pred(r):
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def upsert_meal_event(
    user_id: str,
    day_iso: str,
    *,
    source: str,
    event_type: str,
    totals: Optional[Dict[str, Any]] = None,
    micros: Optional[Dict[str, Any]] = None,
    coaching: Optional[Dict[str, Any]] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    _require_supabase()
    local_ctx = _event_local_context(tz=tz, tz_offset_min=tz_offset_min)
    totals = totals or {}
    coaching = coaching or {}
    hour_local = int(_safe_float(local_ctx.get("event_hour_local"), 0) or 0)
    meal_bucket = _event_bucket_from_hour(hour_local)

    row = {
        "user_id": user_id,
        "day": day_iso,
        "source": str(source or "").strip() or "photo",
        "event_type": str(event_type or "").strip() or "scan",
        "total_kcal": float(_safe_float(totals.get("total_kcal", totals.get("kcal")), 0.0) or 0.0),
        "protein_g": float(_safe_float(totals.get("protein_g"), 0.0) or 0.0),
        "carbs_g": float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0),
        "fat_g": float(_safe_float(totals.get("fat_g"), 0.0) or 0.0),
        "fiber_g": float(_safe_float((micros or {}).get("fiber_g"), 0.0) or 0.0),
        "satiety_score": float(_safe_float(coaching.get("satiety_score"), 0.0) or 0.0),
        "glycemic_load": float(_safe_float((coaching.get("glycemic_load") or {}).get("gl"), 0.0) or 0.0),
        "ultra_processed_score": float(_safe_float(coaching.get("ultra_processed_score"), 0.0) or 0.0),
        "leucine_estimate_g": float(_safe_float(coaching.get("leucine_estimate_g"), 0.0) or 0.0),
        "mps_triggered": bool(coaching.get("mps_triggered")),
        "event_hour_local": hour_local,
        "meal_bucket": meal_bucket,
        "tz": local_ctx.get("tz"),
        "tz_offset_min": local_ctx.get("tz_offset_min"),
        "items_json": items if isinstance(items, list) else [],
        "micros_json": micros if isinstance(micros, dict) else {},
        "event_json": {
            "totals": totals,
            "coaching": coaching,
            "items": items if isinstance(items, list) else [],
            "extra": extra if isinstance(extra, dict) else {},
            "event_time_local": local_ctx.get("event_time_local"),
            "engine_version": BEHAVIOR_ENGINE_VERSION,
        },
        "created_at": local_ctx.get("created_at_utc"),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    _sb_insert_with_column_fallback(TBL_MEAL_EVENTS, row, locked_cols={"user_id", "day"})


def get_meal_events_for_day(user_id: str, day_iso: str) -> List[Dict[str, Any]]:
    _require_supabase()
    rows = sb_get_many(
        TBL_MEAL_EVENTS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "day": f"eq.{day_iso}",
            "order": "created_at.asc",
            "limit": "300",
        },
    )
    return rows if isinstance(rows, list) else []


def compute_daily_metrics_payload(
    user_id: str,
    day_iso: str,
    summary: Dict[str, Any],
    meal_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    totals = (summary or {}).get("totals") or {}
    goals = (summary or {}).get("goals") or {}
    consumed_kcal = float(_safe_float(totals.get("total_kcal", totals.get("kcal")), 0.0) or 0.0)
    consumed_protein = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
    consumed_carbs = float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0)
    consumed_fat = float(_safe_float(totals.get("fat_g"), 0.0) or 0.0)
    consumed_fiber = float(_safe_float(totals.get("fiber_g"), 0.0) or 0.0)

    goal_kcal = float(_safe_float(goals.get("kcal"), DEFAULT_DAILY_GOALS["kcal"]) or DEFAULT_DAILY_GOALS["kcal"])
    goal_protein = float(_safe_float(goals.get("protein_g"), DEFAULT_DAILY_GOALS["protein_g"]) or DEFAULT_DAILY_GOALS["protein_g"])
    goal_carbs = float(_safe_float(goals.get("carbs_g"), DEFAULT_DAILY_GOALS["carbs_g"]) or DEFAULT_DAILY_GOALS["carbs_g"])
    goal_fat = float(_safe_float(goals.get("fat_g"), DEFAULT_DAILY_GOALS["fat_g"]) or DEFAULT_DAILY_GOALS["fat_g"])
    goal_fiber = float(_safe_float(goals.get("fiber_g"), DEFAULT_DAILY_GOALS["fiber_g"]) or DEFAULT_DAILY_GOALS["fiber_g"])

    photo_events = [
        e for e in (meal_events or [])
        if _event_text(e, "source", "event_source").lower() in {"photo", "scan", "meal", ""}
        or _event_text(e, "event_type").lower() in {"photo_analyze", "analyze", "scan"}
    ]
    meals_count = len(photo_events)

    bucket_totals = {"breakfast": 0.0, "lunch": 0.0, "dinner": 0.0, "snack": 0.0}
    late_kcal = 0.0
    satiety_vals: List[float] = []
    gl_vals: List[float] = []
    upf_vals: List[float] = []
    leucine_hits = 0
    for e in photo_events:
        kcal = _event_num(e, "total_kcal", "kcal")
        hour_local = int(_event_num(e, "event_hour_local"))
        b = _event_text(e, "meal_bucket")
        bucket = b if b in bucket_totals else _event_bucket_from_hour(hour_local)
        bucket_totals[bucket] += kcal
        if hour_local >= 19 or hour_local <= 1:
            late_kcal += kcal

        sat = _event_num(e, "satiety_score")
        gl = _event_num(e, "glycemic_load")
        upf = _event_num(e, "ultra_processed_score")
        leu = _event_num(e, "leucine_estimate_g")
        if sat > 0:
            satiety_vals.append(sat)
        if gl > 0:
            gl_vals.append(gl)
        if upf > 0:
            upf_vals.append(upf)
        if leu >= 2.5:
            leucine_hits += 1

    fallback_coaching = build_coaching_payload(
        total_kcal=consumed_kcal,
        protein_g=consumed_protein,
        carbs_g=consumed_carbs,
        fat_g=consumed_fat,
        mps_threshold_g=2.5,
    )
    avg_satiety = round(float(_safe_avg(satiety_vals) or _safe_float(fallback_coaching.get("satiety_score"), 0.0)), 1)
    avg_gl = round(float(_safe_avg(gl_vals) or _safe_float((fallback_coaching.get("glycemic_load") or {}).get("gl"), 0.0)), 1)
    avg_upf = round(float(_safe_avg(upf_vals) or _safe_float(fallback_coaching.get("ultra_processed_score"), 0.0)), 1)

    late_calories_pct = round(((late_kcal / consumed_kcal) * 100.0), 1) if consumed_kcal > 0 else 0.0
    biggest_meal = max(bucket_totals.items(), key=lambda x: float(x[1]))[0] if any(bucket_totals.values()) else "dinner"
    leucine_target = 3

    protein_hit_pct = round(_pct(consumed_protein, goal_protein), 1)
    carbs_hit_pct = round(_pct(consumed_carbs, goal_carbs), 1)
    fat_hit_pct = round(_pct(consumed_fat, goal_fat), 1)
    fiber_hit_pct = round(_pct(consumed_fiber, goal_fiber), 1)
    kcal_hit_pct = round(_pct(consumed_kcal, goal_kcal), 1)
    kcal_delta_pct = round((((consumed_kcal - goal_kcal) / goal_kcal) * 100.0), 1) if goal_kcal > 0 else 0.0

    metrics_json = {
        "day": day_iso,
        "consumed": {
            "kcal": round(consumed_kcal, 1),
            "protein_g": round(consumed_protein, 1),
            "carbs_g": round(consumed_carbs, 1),
            "fat_g": round(consumed_fat, 1),
            "fiber_g": round(consumed_fiber, 1),
        },
        "goals": {
            "kcal": round(goal_kcal, 1),
            "protein_g": round(goal_protein, 1),
            "carbs_g": round(goal_carbs, 1),
            "fat_g": round(goal_fat, 1),
            "fiber_g": round(goal_fiber, 1),
        },
        "hit_pct": {
            "kcal": kcal_hit_pct,
            "protein": protein_hit_pct,
            "carbs": carbs_hit_pct,
            "fat": fat_hit_pct,
            "fiber": fiber_hit_pct,
        },
        "kcal_delta_pct": kcal_delta_pct,
        "signals": {
            "late_calories_pct": late_calories_pct,
            "biggest_meal": biggest_meal,
            "avg_satiety": avg_satiety,
            "avg_glycemic_load": avg_gl,
            "ultra_processed_avg": avg_upf,
            "leucine_triggers_target": leucine_target,
            "leucine_triggers_hit": int(leucine_hits),
            "meals_count": int(meals_count),
        },
        "derived_day_score": round(_day_score_from_metric_row({
            "protein_hit_pct": protein_hit_pct,
            "fiber_hit_pct": fiber_hit_pct,
            "avg_glycemic_load": avg_gl,
            "ultra_processed_avg": avg_upf,
            "late_calories_pct": late_calories_pct,
            "kcal_delta_pct": kcal_delta_pct,
        }), 1),
    }

    return {
        "user_id": user_id,
        "day": day_iso,
        "kcal_goal": round(goal_kcal, 1),
        "protein_goal_g": round(goal_protein, 1),
        "carbs_goal_g": round(goal_carbs, 1),
        "fat_goal_g": round(goal_fat, 1),
        "fiber_goal_g": round(goal_fiber, 1),
        "kcal_consumed": round(consumed_kcal, 1),
        "protein_consumed_g": round(consumed_protein, 1),
        "carbs_consumed_g": round(consumed_carbs, 1),
        "fat_consumed_g": round(consumed_fat, 1),
        "fiber_consumed_g": round(consumed_fiber, 1),
        "kcal_hit_pct": kcal_hit_pct,
        "protein_hit_pct": protein_hit_pct,
        "carbs_hit_pct": carbs_hit_pct,
        "fat_hit_pct": fat_hit_pct,
        "fiber_hit_pct": fiber_hit_pct,
        "kcal_delta_pct": kcal_delta_pct,
        "late_calories_pct": late_calories_pct,
        "biggest_meal": biggest_meal,
        "meals_count": int(meals_count),
        "leucine_triggers_target": int(leucine_target),
        "leucine_triggers_hit": int(leucine_hits),
        "avg_satiety": avg_satiety,
        "avg_glycemic_load": avg_gl,
        "ultra_processed_avg": avg_upf,
        "metrics_json": metrics_json,
        "engine_version": BEHAVIOR_ENGINE_VERSION,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }


def upsert_daily_metrics(user_id: str, day_iso: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    row = dict(payload or {})
    row["user_id"] = user_id
    row["day"] = day_iso
    existing = sb_get_one(
        TBL_DAILY_METRICS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "day": f"eq.{day_iso}",
            "limit": "1",
        },
    )
    if existing:
        patch = {k: v for k, v in row.items() if k not in ("user_id", "day")}
        _sb_patch_with_column_fallback(
            TBL_DAILY_METRICS,
            {"user_id": f"eq.{user_id}", "day": f"eq.{day_iso}"},
            patch,
        )
        refreshed = sb_get_one(
            TBL_DAILY_METRICS,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{day_iso}",
                "limit": "1",
            },
        )
        return refreshed or row
    return _sb_insert_with_column_fallback(TBL_DAILY_METRICS, row, locked_cols={"user_id", "day"})


def get_daily_metrics_window(user_id: str, week_start_iso: str) -> List[Dict[str, Any]]:
    _require_supabase()
    week_end_iso = _week_end_from_start(week_start_iso)
    rows = sb_get_many(
        TBL_DAILY_METRICS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "day": f"gte.{week_start_iso}",
            "order": "day.asc",
            "limit": "20",
        },
    )
    filtered = []
    for r in rows or []:
        day = str((r or {}).get("day") or "")[:10]
        if week_start_iso <= day <= week_end_iso:
            filtered.append(r)
    return filtered


def build_weekly_insight_payload(user_id: str, week_start_iso: str, metric_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    week_end_iso = _week_end_from_start(week_start_iso)
    rows = sorted(metric_rows or [], key=lambda r: str((r or {}).get("day") or ""))
    days = len(rows)

    protein_under_days = sum(1 for r in rows if _extract_metric_val(r, "protein_hit_pct") < 100.0)
    fiber_under_days = sum(1 for r in rows if _extract_metric_val(r, "fiber_hit_pct") < 100.0)
    high_gl_days = sum(1 for r in rows if _extract_metric_val(r, "avg_glycemic_load") >= 25.0)
    high_upf_days = sum(1 for r in rows if _extract_metric_val(r, "ultra_processed_avg") >= 6.5)
    late_days = sum(1 for r in rows if _extract_metric_val(r, "late_calories_pct") >= 45.0)
    protein_under_streak = _longest_streak(rows, lambda r: _extract_metric_val(r, "protein_hit_pct") < 100.0)

    weekend_problem_days = 0
    for r in rows:
        day_iso = str((r or {}).get("day") or "")[:10]
        try:
            d = dt.date.fromisoformat(day_iso)
            is_weekend = d.weekday() >= 5
        except Exception:
            is_weekend = False
        if is_weekend and _extract_metric_val(r, "kcal_delta_pct") > 5.0:
            weekend_problem_days += 1

    satiety_vals = [_extract_metric_val(r, "avg_satiety") for r in rows if _extract_metric_val(r, "avg_satiety") > 0]
    satiety_delta = 0.0
    if satiety_vals:
        half = max(1, len(satiety_vals) // 2)
        satiety_delta = round(_safe_avg(satiety_vals[-half:]) - _safe_avg(satiety_vals[:half]), 1)

    late_vals = [_extract_metric_val(r, "late_calories_pct") for r in rows]
    gl_vals = [_extract_metric_val(r, "avg_glycemic_load") for r in rows]
    upf_vals = [_extract_metric_val(r, "ultra_processed_avg") for r in rows]
    protein_hit_vals = [_extract_metric_val(r, "protein_hit_pct") for r in rows]
    fiber_hit_vals = [_extract_metric_val(r, "fiber_hit_pct") for r in rows]
    day_scores = [_day_score_from_metric_row(r) for r in rows]

    insights: List[str] = []
    if protein_under_streak >= 3:
        insights.append(f"You under-hit protein {protein_under_streak} days in a row.")
    elif protein_under_days >= 4:
        insights.append(f"Protein target was missed on {protein_under_days}/{days} tracked days.")
    if late_days >= 4 and high_gl_days >= 2:
        insights.append(f"Carbs are spiking mostly at night on {late_days}/{days} days.")
    elif late_days >= 4:
        insights.append(f"Calories are clustering late in the day on {late_days}/{days} days.")
    if weekend_problem_days >= 2:
        insights.append("Weekends are driving most calorie overages.")
    if high_gl_days >= 3:
        insights.append(f"Glycemic load ran high on {high_gl_days}/{days} days.")
    if high_upf_days >= 3:
        insights.append(f"Ultra-processed intake stayed elevated on {high_upf_days}/{days} days.")
    if satiety_delta >= 4:
        insights.append(f"Satiety is improving week-over-week (+{satiety_delta}).")
    elif satiety_delta <= -4:
        insights.append(f"Satiety dropped week-over-week ({satiety_delta}).")
    if not insights:
        insights.append("Consistency improved this week; keep protein and fiber anchors stable daily.")

    tomorrow_focus: List[str] = []
    if protein_under_days > 0:
        tomorrow_focus.append("Hit at least 30-40% of your protein goal by lunch.")
    if fiber_under_days > 0:
        tomorrow_focus.append("Add one fiber anchor at lunch and dinner.")
    if late_days > 0:
        tomorrow_focus.append("Shift part of dinner calories earlier in the day.")
    if high_gl_days > 0:
        tomorrow_focus.append("Pair major carb servings with protein and vegetables.")
    if not tomorrow_focus:
        tomorrow_focus.append("Repeat the same meal timing and food quality pattern tomorrow.")

    payload = {
        "week_start": week_start_iso,
        "week_end": week_end_iso,
        "days_tracked": days,
        "insights": insights[:8],
        "tomorrow_focus": tomorrow_focus[:3],
        "patterns": {
            "protein_under_hit_days": int(protein_under_days),
            "protein_under_hit_streak": int(protein_under_streak),
            "fiber_under_hit_days": int(fiber_under_days),
            "high_gl_days": int(high_gl_days),
            "high_upf_days": int(high_upf_days),
            "late_calorie_days": int(late_days),
            "weekend_overage_days": int(weekend_problem_days),
            "satiety_delta": satiety_delta,
        },
        "week_metrics": {
            "avg_day_score": round(_safe_avg(day_scores), 1),
            "avg_protein_hit_pct": round(_safe_avg(protein_hit_vals), 1),
            "avg_fiber_hit_pct": round(_safe_avg(fiber_hit_vals), 1),
            "avg_late_calories_pct": round(_safe_avg(late_vals), 1),
            "avg_glycemic_load": round(_safe_avg(gl_vals), 1),
            "avg_ultra_processed": round(_safe_avg(upf_vals), 1),
            "avg_satiety": round(_safe_avg(satiety_vals), 1) if satiety_vals else 0.0,
        },
        "source_days": [str((r or {}).get("day") or "")[:10] for r in rows],
        "engine_version": BEHAVIOR_ENGINE_VERSION,
        "generated_at": dt.datetime.utcnow().isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["payload_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def upsert_weekly_insight(user_id: str, week_start_iso: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    row = {
        "user_id": user_id,
        "week_start": week_start_iso,
        "week_end": str(payload.get("week_end") or _week_end_from_start(week_start_iso)),
        "days_tracked": int(_safe_float(payload.get("days_tracked"), 0) or 0),
        "payload_hash": str(payload.get("payload_hash") or ""),
        "insights_json": payload,
        "engine_version": str(payload.get("engine_version") or BEHAVIOR_ENGINE_VERSION),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

    existing = sb_get_one(
        TBL_WEEKLY_INSIGHTS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "week_start": f"eq.{week_start_iso}",
            "limit": "1",
        },
    )
    if existing:
        patch = {k: v for k, v in row.items() if k not in ("user_id", "week_start")}
        _sb_patch_with_column_fallback(
            TBL_WEEKLY_INSIGHTS,
            {"user_id": f"eq.{user_id}", "week_start": f"eq.{week_start_iso}"},
            patch,
        )
        refreshed = sb_get_one(
            TBL_WEEKLY_INSIGHTS,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "week_start": f"eq.{week_start_iso}",
                "limit": "1",
            },
        )
        return refreshed or row

    return _sb_insert_with_column_fallback(TBL_WEEKLY_INSIGHTS, row, locked_cols={"user_id", "week_start"})


def get_weekly_insight_payload(user_id: str, week_start_iso: str) -> Optional[Dict[str, Any]]:
    _require_supabase()
    row = sb_get_one(
        TBL_WEEKLY_INSIGHTS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "week_start": f"eq.{week_start_iso}",
            "limit": "1",
        },
    )
    if not row:
        return None
    for k in ("insights_json", "weekly_json", "payload_json", "insights", "payload"):
        val = row.get(k)
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return None


def recompute_behavior_memory(
    user_id: str,
    day_iso: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> Dict[str, Any]:
    _require_supabase()
    target_day = _day_iso(day_iso, tz=tz, tz_offset_min=tz_offset_min)
    summary = build_daily_summary(user_id, target_day, tz=tz, tz_offset_min=tz_offset_min)
    try:
        events = get_meal_events_for_day(user_id, target_day)
    except Exception:
        events = []

    daily_payload = compute_daily_metrics_payload(user_id, target_day, summary, events)
    upsert_daily_metrics(user_id, target_day, daily_payload)

    week_start_iso = _week_start_monday(target_day)
    week_rows = get_daily_metrics_window(user_id, week_start_iso)
    weekly_payload = build_weekly_insight_payload(user_id, week_start_iso, week_rows)
    upsert_weekly_insight(user_id, week_start_iso, weekly_payload)

    return {
        "day": target_day,
        "week_start": week_start_iso,
        "daily_metrics": daily_payload,
        "weekly_insights": weekly_payload,
    }


# -------------------- PLAN / USAGE --------------------
def get_plan_limits(plan: str) -> Dict[str, int]:
    """
    Reads from plan_limits:
      plan text primary key,
      daily_limit int not null,
      monthly_limit int not null
    """
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
        # safe fallback if table not seeded
        if plan == "free":
            return {"daily_limit": 25, "monthly_limit": 25}
        if plan == "elite":
            return {"daily_limit": 15, "monthly_limit": 50}
        if plan == "advanced":
            return {"daily_limit": 20, "monthly_limit": 100}
        if plan == "pro":
            return {"daily_limit": 25, "monthly_limit": 1000}
        if plan == "infinite":
            return {"daily_limit": 30, "monthly_limit": 10000}
        return {"daily_limit": 3, "monthly_limit": 25}

    return {
        "daily_limit": int(row.get("daily_limit") or 0),
        "monthly_limit": int(row.get("monthly_limit") or 0),
    }

def get_or_init_usage(user_id: str, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """
    user_usage schema expected:
      user_id uuid primary key references auth.users(id),
      plan text not null default 'free',
      remaining_day int not null default 0,
      remaining_month int not null default 0,
      day_reset date not null default current_date,
      month_reset date not null default date_trunc('month', now())::date,
      updated_at timestamptz not null default now()
    """
    _require_supabase()

    row = sb_get_one(
        TBL_USER_USAGE,
        params={
            "select": "user_id,plan,remaining_day,remaining_month,day_reset,month_reset,updated_at",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )

    today = today or _today_date()
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

def normalize_resets(row: Dict[str, Any], today: Optional[dt.date] = None) -> Dict[str, Any]:
    """
    If day/month changed, reset counters to plan limits.
    BUT: If plan is 'free', do not reset (total lifetime limit).
    """
    user_id = row["user_id"]
    plan = (row.get("plan") or DEFAULT_PLAN).lower()

    # --- CRITICAL: Free plan has NO RESETS (Lifetime 25) ---
    if plan == "free":
        return row

    today = today or _today_date()
    mstart = _month_start(today)

    # Parse stored dates
    def parse_date(x) -> Optional[dt.date]:
        if not x:
            return None
        if isinstance(x, dt.date):
            return x
        try:
            return dt.date.fromisoformat(str(x)[:10])
        except Exception:
            return None

    day_reset = parse_date(row.get("day_reset"))
    month_reset = parse_date(row.get("month_reset"))

    lim = get_plan_limits(plan)

    patch: Dict[str, Any] = {}
    if day_reset != today:
        patch["remaining_day"] = lim["daily_limit"]
        patch["day_reset"] = str(today)

    if month_reset != mstart:
        patch["remaining_month"] = lim["monthly_limit"]
        patch["month_reset"] = str(mstart)

    if patch:
        patch["updated_at"] = dt.datetime.utcnow().isoformat()
        sb_patch(TBL_USER_USAGE, {"user_id": f"eq.{user_id}"}, patch)
        row.update(patch)

    return row

def consume_one_scan(user_id: str, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """
    Enforces usage + decrements by 1.
    Raises HTTP 402 if out of scans.
    """
    row = get_or_init_usage(user_id, today=today)
    row = normalize_resets(row, today=today)

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

    # Decrement
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

def set_user_plan(user_id: str, plan: str, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """
    When user purchases a plan, set plan and reset counters immediately.
    """
    plan = (plan or DEFAULT_PLAN).lower()
    if plan not in PLAN_ORDER:
        plan = DEFAULT_PLAN

    lim = get_plan_limits(plan)
    today = today or _today_date()
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


def set_user_plan_no_reset(user_id: str, plan: str, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """\
    Used for *restore* flows.

    Updates the user's plan WITHOUT refilling scan counters.
    This prevents users from spamming "Restore Purchases" to refill scans.

    Behavior:
      - If downgrading, we clamp remaining counts down to the new plan limits.
      - If upgrading, we keep remaining counts as-is (no bonus refills).
    """
    plan = (plan or DEFAULT_PLAN).lower()
    if plan not in PLAN_ORDER:
        plan = DEFAULT_PLAN

    # Ensure row exists and any date-based resets are applied first.
    row = get_or_init_usage(user_id, today=today)
    row = normalize_resets(row, today=today)

    lim = get_plan_limits(plan)
    rem_day = int(row.get("remaining_day") or 0)
    rem_month = int(row.get("remaining_month") or 0)

    # Never increase counters on restore; only clamp down if needed.
    new_rem_day = min(rem_day, int(lim.get("daily_limit") or 0))
    new_rem_month = min(rem_month, int(lim.get("monthly_limit") or 0))

    patch = {
        "plan": plan,
        "remaining_day": new_rem_day,
        "remaining_month": new_rem_month,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    sb_patch(TBL_USER_USAGE, {"user_id": f"eq.{user_id}"}, patch)
    row.update(patch)
    return row

def get_user_plan(user_id: str) -> str:
    row = get_or_init_usage(user_id)
    return (row.get("plan") or DEFAULT_PLAN).lower()

def require_user_id(x_user_id: Optional[str], user_id: Optional[str]) -> str:
    h = (x_user_id or "").strip()
    q = (user_id or "").strip()
    if h and q and h != q:
        raise HTTPException(status_code=401, detail="Conflicting user ids in header and query.")
    uid = h or q
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id. Pass X-User-Id header or ?user_id=...")
    return uid


@app.get("/usage")
def usage(
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    row = get_or_init_usage(uid, today=today_local)
    row = normalize_resets(row, today=today_local)
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
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """\
    Call from mobile after RevenueCat purchase/restore.

    payload:
      { "entitlement": "elite" | "advanced" | "pro" | "infinite", "mode": "purchase"|"restore" }

    IMPORTANT:
    - purchase: sets plan AND refills counters to plan limits (new billing period starts)
    - restore: sets plan BUT does NOT refill counters (prevents restore-spam)
    - if mode is missing, we treat it as "restore" to avoid accidentally resetting scan limits
    """
    uid = require_user_id(x_user_id, user_id)
    entitlement = (payload.get("entitlement") or DEFAULT_PLAN).lower()
    mode = (payload.get("mode") or "restore").lower()  # default safe: no counter reset
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)

    if mode == "restore":
        stored = set_user_plan_no_reset(uid, entitlement, today=today_local)
    else:
        stored = set_user_plan(uid, entitlement, today=today_local)

    return {"ok": True, "plan": stored.get("plan"), "mode": mode}




@app.get("/goals")
def get_goals(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    return {"ok": True, "goals": get_user_goals(uid)}

@app.post("/goals")
def set_goals(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    stored = upsert_user_goals(uid, payload or {})
    return {"ok": True, "goals": stored}

@app.get("/daily/summary")
def daily_summary(
    day: Optional[str] = None,
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    return build_daily_summary(uid, day, tz=tz, tz_offset_min=tz_offset_min)


@app.post("/weekly/recompute")
def weekly_recompute(
    day: Optional[str] = None,
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Recomputes behavior memory for a given day:
      - updates daily_metrics for that day
      - rebuilds weekly_insights cache for that week
    """
    uid = require_user_id(x_user_id, user_id)
    out = recompute_behavior_memory(uid, day_iso=day, tz=tz, tz_offset_min=tz_offset_min)
    return {"ok": True, **out}


@app.get("/weekly/insights")
def weekly_insights(
    week_start: Optional[str] = None,
    day: Optional[str] = None,
    refresh: Optional[bool] = False,
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    anchor_day = _day_iso(day, tz=tz, tz_offset_min=tz_offset_min)
    week_start_iso = _week_start_monday(week_start or anchor_day)

    payload = None if refresh else get_weekly_insight_payload(uid, week_start_iso)
    if not payload:
        rows = get_daily_metrics_window(uid, week_start_iso)
        payload = build_weekly_insight_payload(uid, week_start_iso, rows)
        upsert_weekly_insight(uid, week_start_iso, payload)

    return {
        "ok": True,
        "week_start": week_start_iso,
        "week_end": _week_end_from_start(week_start_iso),
        "insights": payload,
    }


# -------------------- DAILY COACH (LLM INTERPRETER ONLY) --------------------
_COACH_MEM_CACHE: Dict[str, Dict[str, Any]] = {}

_COACH_SYSTEM_PROMPT = (
    "You are a nutrition coaching assistant. "
    "Provide behavior-focused suggestions only. "
    "Do not provide medical advice, diagnosis, treatment, drug, or supplement recommendations. "
    "Use ONLY the provided numbers and context. "
    "Do not invent metrics. "
    "Output strict JSON only."
)


def _coach_mem_key(user_id: str, day_iso: str, payload_hash: str) -> str:
    return f"{user_id}:{day_iso}:{payload_hash}"


def _coach_cache_get(user_id: str, day_iso: str, payload_hash: str) -> Optional[Dict[str, Any]]:
    # 1) Fast in-memory cache
    mem_key = _coach_mem_key(user_id, day_iso, payload_hash)
    hit = _COACH_MEM_CACHE.get(mem_key)
    if isinstance(hit, dict):
        return hit

    # 2) Optional Supabase cache (if table exists)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        row = sb_get_one(
            TBL_DAILY_SUMMARY,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{day_iso}",
                "limit": "1",
            },
        )
    except Exception as e:
        logger.info(f"coach cache read skipped: {e}")
        return None

    if not row:
        return None

    stored_hash = str(
        row.get("payload_hash")
        or row.get("coach_payload_hash")
        or row.get("input_hash")
        or ""
    ).strip()
    if stored_hash and stored_hash != payload_hash:
        return None

    for k in ("coach_json", "coach_daily", "coach_response", "response_json", "response"):
        val = row.get(k)
        if isinstance(val, dict):
            _COACH_MEM_CACHE[mem_key] = val
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    _COACH_MEM_CACHE[mem_key] = parsed
                    return parsed
            except Exception:
                continue
    return None


def _coach_cache_set(user_id: str, day_iso: str, payload_hash: str, coach_resp: Dict[str, Any]) -> None:
    mem_key = _coach_mem_key(user_id, day_iso, payload_hash)
    _COACH_MEM_CACHE[mem_key] = coach_resp

    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return

    payload = {
        "user_id": user_id,
        "day": day_iso,
        "payload_hash": payload_hash,
        "coach_json": coach_resp,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    try:
        existing = sb_get_one(
            TBL_DAILY_SUMMARY,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{day_iso}",
                "limit": "1",
            },
        )
        if existing:
            patch = {k: v for k, v in payload.items() if k not in ("user_id", "day")}
            _sb_patch_with_column_fallback(
                TBL_DAILY_SUMMARY,
                {"user_id": f"eq.{user_id}", "day": f"eq.{day_iso}"},
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_DAILY_SUMMARY,
                payload,
                locked_cols={"user_id", "day"},
            )
    except Exception as e:
        logger.info(f"coach cache write skipped: {e}")


def _coach_user_prompt(
    norm_payload: Dict[str, Any],
    fat_loss_score: int,
    rule_alerts: List[Dict[str, str]],
    weekly_behavior: Optional[Dict[str, Any]] = None,
) -> str:
    allowed_palette = coach_logic.allowed_suggestion_palette(norm_payload)
    compact = {
        "date": norm_payload.get("date"),
        "goals": norm_payload.get("goals"),
        "consumed": norm_payload.get("consumed"),
        "signals": norm_payload.get("signals"),
        "meal_timing": norm_payload.get("meal_timing"),
        "constraints": norm_payload.get("constraints"),
        "profile": norm_payload.get("profile"),
        "fat_loss_score": fat_loss_score,
        "rule_risk_alerts": rule_alerts,
        "behavior_memory_weekly": weekly_behavior or {},
    }
    template = {
        "diagnosis": ["string", "string"],
        "tomorrow_focus": ["string", "string"],
        "actions": [{"title": "string", "why": "string", "how": "string"}],
        "risk_alerts": [{"type": "string", "level": "low|medium|high", "reason": "string"}],
    }
    return (
        "Use this daily nutrition summary and produce coaching text only.\n"
        "Rules:\n"
        "- Keep it practical and behavior-focused.\n"
        "- No medical advice, disease claims, supplements, dosages, or treatment language.\n"
        "- Every action must clearly reference at least one metric keyword from this set: "
        "protein, fiber, glycemic load, ultra-processed, leucine, late calories, kcal, carbs, fat.\n"
        "- Max 3 actions.\n"
        "- Keep language concise.\n\n"
        f"Allowed suggestion palette:\n{json.dumps(allowed_palette, ensure_ascii=True)}\n\n"
        f"Input payload:\n{json.dumps(compact, ensure_ascii=True)}\n\n"
        f"Output JSON shape:\n{json.dumps(template, ensure_ascii=True)}"
    )


def _coerce_coach_response_shape(parsed: Dict[str, Any], rule_alerts: List[Dict[str, str]]) -> Dict[str, Any]:
    diagnosis = parsed.get("diagnosis") if isinstance(parsed.get("diagnosis"), list) else []
    tomorrow_focus = parsed.get("tomorrow_focus") if isinstance(parsed.get("tomorrow_focus"), list) else []
    actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
    risk_alerts = parsed.get("risk_alerts") if isinstance(parsed.get("risk_alerts"), list) else []

    cleaned = {
        "diagnosis": [str(x).strip() for x in diagnosis if str(x).strip()][:4],
        "tomorrow_focus": [str(x).strip() for x in tomorrow_focus if str(x).strip()][:3],
        "actions": [],
        "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, risk_alerts, limit=4),
        "disclaimer": coach_logic.COACH_DISCLAIMER,
    }

    for a in actions[:3]:
        if not isinstance(a, dict):
            continue
        item = {
            "title": str(a.get("title") or "").strip(),
            "why": str(a.get("why") or "").strip(),
            "how": str(a.get("how") or "").strip(),
        }
        if item["why"] and not coach_logic.action_references_metrics(item):
            item["why"] = f"{item['why']} Targets protein/fiber/glycemic load trends."
        if item["title"] and item["why"] and item["how"]:
            cleaned["actions"].append(item)

    return cleaned


def _generate_daily_coach_llm(
    norm_payload: Dict[str, Any],
    fat_loss_score: int,
    rule_alerts: List[Dict[str, str]],
    weekly_behavior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _require_gemini_key()
    model = genai.GenerativeModel(COACH_LLM_MODEL)
    user_prompt = _coach_user_prompt(norm_payload, fat_loss_score, rule_alerts, weekly_behavior=weekly_behavior)
    last_err = ""
    for attempt in range(3):
        try:
            resp = model.generate_content([_COACH_SYSTEM_PROMPT, user_prompt])
            text = (resp.text or "").strip()
            parsed = coach_logic.extract_json_object(text)
            if not isinstance(parsed, dict):
                raise ValueError("LLM did not return valid JSON object.")

            cleaned = _coerce_coach_response_shape(parsed, rule_alerts)
            ok, reason = coach_logic.validate_llm_response_shape(cleaned)
            if not ok:
                raise ValueError(f"LLM JSON failed validation: {reason}")
            return cleaned
        except Exception as e:
            last_err = str(e)
            time.sleep(0.6 * (attempt + 1))
    raise HTTPException(status_code=502, detail={"error": "coach_llm_failed", "raw": last_err[:300]})


@app.post("/coach/daily")
def coach_daily(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    refresh: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Deterministic score + LLM reasoning layer.
    Numbers are always computed by Python rules; LLM only interprets.
    """
    uid = require_user_id(x_user_id, user_id)
    norm = coach_logic.normalize_daily_payload(payload or {})
    if not norm.get("date"):
        norm["date"] = _today_date().isoformat()

    fat_loss_score = coach_logic.compute_fat_loss_score(norm)
    rule_alerts = coach_logic.build_rule_risk_alerts(norm)
    p_hash = coach_logic.payload_hash(norm)
    day_iso = str(norm.get("date") or _today_date().isoformat())
    week_start_iso = _week_start_monday(day_iso)

    weekly_behavior: Optional[Dict[str, Any]] = None
    try:
        weekly_behavior = get_weekly_insight_payload(uid, week_start_iso)
    except Exception as e:
        logger.info(f"weekly insight read skipped in /coach/daily: {e}")
    if not weekly_behavior:
        try:
            week_rows = get_daily_metrics_window(uid, week_start_iso)
            if week_rows:
                weekly_behavior = build_weekly_insight_payload(uid, week_start_iso, week_rows)
                upsert_weekly_insight(uid, week_start_iso, weekly_behavior)
        except Exception as e:
            logger.info(f"weekly insight recompute skipped in /coach/daily: {e}")

    weekly_hash = str((weekly_behavior or {}).get("payload_hash") or "").strip()
    if weekly_hash:
        p_hash = hashlib.sha256(f"{p_hash}:{weekly_hash}".encode("utf-8")).hexdigest()

    cached = _coach_cache_get(uid, day_iso, p_hash) if not refresh else None
    if isinstance(cached, dict):
        out = dict(cached)
        out["fat_loss_score"] = int(fat_loss_score)
        out["disclaimer"] = coach_logic.COACH_DISCLAIMER
        out["date"] = day_iso
        out["reasoning_source"] = str(out.get("reasoning_source") or "cache")
        if isinstance(weekly_behavior, dict):
            out["behavior_memory"] = {
                "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
                "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
                "patterns": weekly_behavior.get("patterns") or {},
                "insights": (weekly_behavior.get("insights") or [])[:4],
            }
        return out

    llm_resp: Optional[Dict[str, Any]] = None
    reasoning_source = "fallback"
    if GEMINI_API_KEY:
        try:
            llm_resp = _generate_daily_coach_llm(norm, fat_loss_score, rule_alerts, weekly_behavior=weekly_behavior)
            reasoning_source = "llm"
        except Exception as e:
            logger.warning(f"Daily coach LLM failed, using fallback: {e}")

    if not llm_resp:
        llm_resp = coach_logic.build_fallback_coach_response(norm, fat_loss_score, rule_alerts)

    final_resp = {
        "date": day_iso,
        "fat_loss_score": int(fat_loss_score),
        "diagnosis": llm_resp.get("diagnosis", []),
        "tomorrow_focus": llm_resp.get("tomorrow_focus", []),
        "actions": llm_resp.get("actions", [])[:3],
        "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, llm_resp.get("risk_alerts", []), limit=4),
        "disclaimer": coach_logic.COACH_DISCLAIMER,
        "reasoning_source": reasoning_source,
        "week_start": week_start_iso,
    }
    if isinstance(weekly_behavior, dict):
        final_resp["behavior_memory"] = {
            "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
            "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
            "patterns": weekly_behavior.get("patterns") or {},
            "insights": (weekly_behavior.get("insights") or [])[:4],
        }

    # Final safety gate. If anything violates guardrails, return deterministic fallback.
    ok, reason = coach_logic.validate_llm_response_shape(final_resp)
    if not ok:
        logger.warning(f"Daily coach response failed safety gate: {reason}")
        fb = coach_logic.build_fallback_coach_response(norm, fat_loss_score, rule_alerts)
        final_resp = {
            "date": day_iso,
            "fat_loss_score": int(fat_loss_score),
            "diagnosis": fb.get("diagnosis", []),
            "tomorrow_focus": fb.get("tomorrow_focus", []),
            "actions": fb.get("actions", [])[:3],
            "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, fb.get("risk_alerts", []), limit=4),
            "disclaimer": coach_logic.COACH_DISCLAIMER,
            "reasoning_source": "fallback",
            "week_start": week_start_iso,
        }
        if isinstance(weekly_behavior, dict):
            final_resp["behavior_memory"] = {
                "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
                "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
                "patterns": weekly_behavior.get("patterns") or {},
                "insights": (weekly_behavior.get("insights") or [])[:4],
            }

    _coach_cache_set(uid, day_iso, p_hash, final_resp)
    return final_resp


# -------------------- HTTP RETRY HELPERS --------------------
def _request_with_retries(method: str, url: str, *, retries: int = 3, timeout: int = 40, retry_statuses=(429, 500, 502, 503, 504), **kwargs):
    """Basic retry wrapper for flaky upstreams (USDA). Always raises JSON-friendly HTTPException."""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.request(method, url, timeout=timeout, **kwargs)
            if r.status_code in retry_statuses and attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            return r
        except requests.exceptions.RequestException as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise HTTPException(
                status_code=503,
                detail={"error": "upstream_timeout", "service": "usda", "message": last_err},
            )

def _is_html(text: str) -> bool:
    t = (text or "").lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html") or "<html" in t[:200]

# -------------------- USDA --------------------
def usda_search_candidates(query: str) -> List[Dict[str, Any]]:
    _require_usda_key()
    payload = {
        "query": query,
        "pageSize": 8,
        "pageNumber": 1,
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        "requireAllWords": False,
    }
    r = _request_with_retries(
        "POST",
        f"{USDA_BASE}/foods/search",
        params={"api_key": USDA_API_KEY},
        json=payload,
        timeout=40,
    )
    if r.status_code != 200:
        raw = r.text
        raise HTTPException(
            status_code=502,
            detail={"error": "usda_search_failed", "status": r.status_code, "raw": (raw or "")[:500], "html": _is_html(raw)},
        )

    foods = (r.json() or {}).get("foods", []) or []
    non_branded = [f for f in foods if f.get("dataType") != "Branded"]
    return non_branded + [f for f in foods if f.get("dataType") == "Branded"]


def usda_search_best(query: str) -> Optional[Dict[str, Any]]:
    candidates = usda_search_candidates(query)
    return candidates[0] if candidates else None

def usda_food_details(fdc_id: int) -> Dict[str, Any]:

    _require_usda_key()
    r = _request_with_retries(
        "GET",
        f"{USDA_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=40,
    )
    if r.status_code != 200:
        raw = r.text
        raise HTTPException(
            status_code=502,
            detail={"error": "usda_details_failed", "status": r.status_code, "fdcId": fdc_id, "raw": (raw or "")[:500], "html": _is_html(raw)},
        )
    return r.json()

def extract_macros_per_100g(food_details: dict) -> Dict[str, float]:
    """
    Uses nutrient numbers:
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
        "kcal_per_100g": kcal,
        "protein_g_per_100g": protein,
        "carbs_g_per_100g": carbs,
        "fat_g_per_100g": fat,
    }



# -------------------- MICRONUTRIENTS (USDA) --------------------
def _convert_unit(amount: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert between g/mg/ug and IU->ug (Vitamin D). Returns None if unsupported."""
    if amount is None:
        return None

    fu = (from_unit or "").strip().lower().replace("µ", "u")
    tu = (to_unit or "").strip().lower().replace("µ", "u")

    if fu == tu:
        return float(amount)

    # IU conversion (only handle Vitamin D; 1 IU = 0.025 µg)
    if fu == "iu" and tu in ("ug", "mcg"):
        return float(amount) * 0.025

    # Mass conversions
    factors = {"g": 1_000_000.0, "mg": 1_000.0, "ug": 1.0, "mcg": 1.0}
    if fu not in factors or tu not in factors:
        return None

    # Convert to µg base then to target
    ug_val = float(amount) * factors[fu]
    return ug_val / factors[tu]


def extract_micros_per_100g(food_details: dict) -> Dict[str, Any]:
    """
    Extract key micronutrients per 100g from USDA food details.

    Nutrient numbers used by USDA:
      - Vitamin D total: 324 (µg) or 328 (IU)
      - Vitamin D2 / D3 (fallback parts): 325 / 326
      - Vitamin B12: 418
      - Iron: 303
      - Magnesium: 304
      - Calcium: 301
      - Potassium: 306
      - Sodium: 307
      - Fiber, total dietary: 291

    Returns values with consistent units:
      vitamin_d_ug, vitamin_b12_ug, iron_mg, magnesium_mg,
      calcium_mg, potassium_mg, sodium_mg, fiber_g
    Missing nutrients are returned as 0.0 (not all foods report all micros).
    """
    wanted = {
        "418": ("vitamin_b12_ug", "ug"),
        "303": ("iron_mg", "mg"),
        "304": ("magnesium_mg", "mg"),
        "301": ("calcium_mg", "mg"),
        "306": ("potassium_mg", "mg"),
        "307": ("sodium_mg", "mg"),
        "291": ("fiber_g", "g"),
    }

    out = {k: 0.0 for _, (k, _) in wanted.items()}

    vd_total_candidates: List[float] = []
    vd_parts_sum = 0.0
    vd_parts_found = False

    for n in food_details.get("foodNutrients", []) or []:
        nutrient = n.get("nutrient") or {}
        number = str(nutrient.get("number") or "").strip()
        nut_name = (nutrient.get("name") or "").strip().lower()

        amount = n.get("amount")
        if amount is None:
            continue

        unit = (nutrient.get("unitName") or "").strip()
        # Vitamin D can appear as total (324/328) or split parts (325 + 326)
        if number in {"324", "328"}:
            conv = _convert_unit(float(amount), unit, "ug")
            if conv is not None:
                vd_total_candidates.append(float(conv))
            continue
        if number in {"325", "326"}:
            conv = _convert_unit(float(amount), unit, "ug")
            if conv is not None:
                vd_parts_sum += float(conv)
                vd_parts_found = True
            continue
        if "vitamin d" in nut_name:
            conv = _convert_unit(float(amount), unit, "ug")
            if conv is not None:
                vd_total_candidates.append(float(conv))
            continue

        if number not in wanted:
            continue

        key, target_unit = wanted[number]
        conv = _convert_unit(float(amount), unit, target_unit)
        if conv is not None:
            out[key] = float(conv)

    if vd_total_candidates:
        out["vitamin_d_ug"] = max(vd_total_candidates)
    elif vd_parts_found:
        out["vitamin_d_ug"] = vd_parts_sum

    # Helpful metadata for UI
    out["_units"] = {
        "vitamin_d_ug": "µg",
        "vitamin_b12_ug": "µg",
        "iron_mg": "mg",
        "magnesium_mg": "mg",
        "calcium_mg": "mg",
        "potassium_mg": "mg",
        "sodium_mg": "mg",
        "fiber_g": "g",
    }
    return out

# -------------------- GEMINI FOOD DETECTION --------------------
def gemini_detect_foods(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Returns list: { name, grams, confidence }
    Retries on rate limit-ish failures.
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
- Use simple, USDA-friendly names.
- grams must be a positive number.
- confidence must be 0..1.
- Never return empty items.
"""

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    last_err = None
    for attempt in range(4):
        try:
            resp = model.generate_content([prompt, img])
            text = (resp.text or "").strip()
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
            last_err = str(e)
            # backoff
            time.sleep(0.6 * (attempt + 1))

    raise HTTPException(status_code=502, detail={"error": "Gemini failed / invalid JSON", "raw": last_err})


# -------------------- BARCODE: OpenFoodFacts -> Supabase Cache --------------------
def openfoodfacts_lookup(barcode: str) -> Dict[str, Any]:
    url = f"{OPENFOODFACTS_BASE}/product/{barcode}.json"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenFoodFacts failed: {r.text}")

    data = r.json() or {}
    if data.get("status") != 1:
        raise HTTPException(status_code=404, detail={"error": "Barcode not found", "barcode": barcode})

    product = data.get("product") or {}
    nutr = product.get("nutriments") or {}

    kcal_100g = _safe_float(nutr.get("energy-kcal_100g"))
    if kcal_100g is None:
        kj_100g = _safe_float(nutr.get("energy_100g"))
        if kj_100g is not None:
            kcal_100g = kj_100g / 4.184

    protein = _safe_float(nutr.get("proteins_100g"), 0.0) or 0.0
    carbs = _safe_float(nutr.get("carbohydrates_100g"), 0.0) or 0.0
    fat = _safe_float(nutr.get("fat_100g"), 0.0) or 0.0

    name = (product.get("product_name") or product.get("generic_name") or "").strip()
    brand = (product.get("brands") or "").strip()

    if kcal_100g is None:
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
        "serving_size_g": None,  # per-100g only
        "source": "openfoodfacts",
        "raw": data,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

def supabase_get_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    _require_supabase()
    return sb_get_one(
        TBL_BARCODE,
        params={
            "select": "id,barcode,name,brand,kcal_per_100g,protein_g_per_100g,carbs_g_per_100g,fat_g_per_100g,serving_size_g,source,raw,updated_at",
            "barcode": f"eq.{barcode}",
            "limit": "1",
        },
    )

def supabase_upsert_barcode(row: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    return sb_upsert(TBL_BARCODE, row, on_conflict="barcode")


# -------------------- BARCODE ENDPOINTS --------------------
@app.get("/barcode/{code}")
def barcode_lookup(
    code: str,
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)

    # 🔒 barcode requires elite+
    plan = get_user_plan(uid)
    require_plan(plan, "elite", feature="barcode")

    # consume scan first (so even cache hits count)
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    usage_row = consume_one_scan(uid, today=today_local)

    barcode = _digits_only(code)
    if not barcode:
        raise HTTPException(status_code=400, detail={"error": "Invalid barcode", "barcode": code})

    # 1) cache
    cached = supabase_get_barcode(barcode)
    if cached:
        try:
            upsert_meal_event(
                uid,
                day_iso=today_local.isoformat(),
                source="barcode",
                event_type="barcode_lookup",
                totals={"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
                micros={},
                coaching={},
                items=[],
                tz=tz,
                tz_offset_min=tz_offset_min,
                extra={
                    "barcode": barcode,
                    "cached": True,
                    "name": cached.get("name"),
                    "brand": cached.get("brand"),
                    "per_100g": {
                        "kcal": float(cached.get("kcal_per_100g") or 0),
                        "protein_g": float(cached.get("protein_g_per_100g") or 0),
                        "carbs_g": float(cached.get("carbs_g_per_100g") or 0),
                        "fat_g": float(cached.get("fat_g_per_100g") or 0),
                    },
                },
            )
        except Exception as e:
            logger.warning(f"Barcode meal event write skipped: {e}")
        return {
            "source": "barcode",
            "barcode": cached.get("barcode"),
            "name": cached.get("name"),
            "brand": cached.get("brand"),
            "per_100g": {
                "kcal": float(cached.get("kcal_per_100g") or 0),
                "protein_g": float(cached.get("protein_g_per_100g") or 0),
                "carbs_g": float(cached.get("carbs_g_per_100g") or 0),
                "fat_g": float(cached.get("fat_g_per_100g") or 0),
            },
            "source_db": cached.get("source"),
            "cached": True,
            "usage": {
                "plan": usage_row.get("plan"),
                "remaining_day": int(usage_row.get("remaining_day") or 0),
                "remaining_month": int(usage_row.get("remaining_month") or 0),
            },
        }

    # 2) OFF
    off = openfoodfacts_lookup(barcode)

    # 3) store
    stored = supabase_upsert_barcode(off)
    try:
        upsert_meal_event(
            uid,
            day_iso=today_local.isoformat(),
            source="barcode",
            event_type="barcode_lookup",
            totals={"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
            micros={},
            coaching={},
            items=[],
            tz=tz,
            tz_offset_min=tz_offset_min,
            extra={
                "barcode": barcode,
                "cached": False,
                "name": stored.get("name"),
                "brand": stored.get("brand"),
                "per_100g": {
                    "kcal": float(stored.get("kcal_per_100g") or 0),
                    "protein_g": float(stored.get("protein_g_per_100g") or 0),
                    "carbs_g": float(stored.get("carbs_g_per_100g") or 0),
                    "fat_g": float(stored.get("fat_g_per_100g") or 0),
                },
            },
        )
    except Exception as e:
        logger.warning(f"Barcode meal event write skipped: {e}")

    return {
        "source": "barcode",
        "barcode": stored.get("barcode"),
        "name": stored.get("name"),
        "brand": stored.get("brand"),
        "per_100g": {
            "kcal": float(stored.get("kcal_per_100g") or 0),
            "protein_g": float(stored.get("protein_g_per_100g") or 0),
            "carbs_g": float(stored.get("carbs_g_per_100g") or 0),
            "fat_g": float(stored.get("fat_g_per_100g") or 0),
        },
        "source_db": stored.get("source") or "openfoodfacts",
        "cached": False,
        "usage": {
            "plan": usage_row.get("plan"),
            "remaining_day": int(usage_row.get("remaining_day") or 0),
            "remaining_month": int(usage_row.get("remaining_month") or 0),
        },
    }

@app.post("/barcode/manual")
def barcode_manual(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Manual add when barcode not found.
    Expected payload:
      {
        "barcode": "xxxx",
        "name": "Product name",
        "brand": "Brand",
        "kcal_per_100g": 123,
        "protein_g_per_100g": 1,
        "carbs_g_per_100g": 2,
        "fat_g_per_100g": 3
      }
    """
    uid = require_user_id(x_user_id, user_id)

    # 🔒 barcode requires elite+
    plan = get_user_plan(uid)
    require_plan(plan, "elite", feature="barcode")

    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    usage_row = consume_one_scan(uid, today=today_local)

    barcode = _digits_only(str(payload.get("barcode") or ""))
    if not barcode:
        raise HTTPException(status_code=400, detail={"error": "Invalid barcode"})

    row = {
        "barcode": barcode,
        "name": (payload.get("name") or "Unknown product").strip(),
        "brand": (payload.get("brand") or None),
        "kcal_per_100g": float(payload.get("kcal_per_100g") or 0),
        "protein_g_per_100g": float(payload.get("protein_g_per_100g") or 0),
        "carbs_g_per_100g": float(payload.get("carbs_g_per_100g") or 0),
        "fat_g_per_100g": float(payload.get("fat_g_per_100g") or 0),
        "serving_size_g": None,
        "source": "manual",
        "raw": payload,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }

    if row["kcal_per_100g"] <= 0:
        raise HTTPException(status_code=400, detail={"error": "kcal_per_100g must be > 0"})

    stored = supabase_upsert_barcode(row)
    try:
        upsert_meal_event(
            uid,
            day_iso=today_local.isoformat(),
            source="barcode",
            event_type="barcode_manual",
            totals={"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
            micros={},
            coaching={},
            items=[],
            tz=tz,
            tz_offset_min=tz_offset_min,
            extra={
                "barcode": barcode,
                "name": stored.get("name"),
                "brand": stored.get("brand"),
                "per_100g": {
                    "kcal": float(stored.get("kcal_per_100g") or 0),
                    "protein_g": float(stored.get("protein_g_per_100g") or 0),
                    "carbs_g": float(stored.get("carbs_g_per_100g") or 0),
                    "fat_g": float(stored.get("fat_g_per_100g") or 0),
                },
            },
        )
    except Exception as e:
        logger.warning(f"Barcode manual meal event write skipped: {e}")
    return {
        "ok": True,
        "stored": True,
        "barcode": stored.get("barcode"),
        "name": stored.get("name"),
        "brand": stored.get("brand"),
        "per_100g": {
            "kcal": float(stored.get("kcal_per_100g") or 0),
            "protein_g": float(stored.get("protein_g_per_100g") or 0),
            "carbs_g": float(stored.get("carbs_g_per_100g") or 0),
            "fat_g": float(stored.get("fat_g_per_100g") or 0),
        },
        "source_db": stored.get("source") or "manual",
        "usage": {
            "plan": usage_row.get("plan"),
            "remaining_day": int(usage_row.get("remaining_day") or 0),
            "remaining_month": int(usage_row.get("remaining_month") or 0),
        },
    }



# -------------------- COACHING (PRO+) --------------------
def clamp(x: float, lo: float, hi: float) -> float:
    try:
        x = float(x)
    except Exception:
        return lo
    return max(lo, min(hi, x))

def round1(x: float) -> float:
    return float(f"{float(x):.1f}")

def leucine_messages(leucine_gap_g: float) -> List[str]:
    """
    Returns simple, user-facing guidance based on how far the meal is from the leucine threshold.
    """
    if leucine_gap_g <= 0:
        return ["✅ Great — muscle-building signal is triggered for this meal."]
    if leucine_gap_g <= 0.4:
        return [
            "Add a little more protein to hit the muscle-building threshold.",
            "Easy add-ons: Greek yogurt, milk, eggs, chicken, or whey."
        ]
    if leucine_gap_g <= 1.0:
        return [
            "You're close — add a moderate protein boost.",
            "Good options: extra chicken/fish/eggs, tofu/tempeh, Greek yogurt, or a protein shake."
        ]
    return [
        "You're quite short — this meal needs more protein to trigger muscle-building.",
        "Add a strong protein portion (e.g., chicken/fish/lean meat/tofu) or a protein shake."
    ]

def estimate_satiety_score(total_kcal: float, protein_g: float, carbs_g: float, fat_g: float) -> float:
    """
    Satiety score (0-100). Heuristic designed for *relative* feedback, not medical accuracy.
    Higher protein and lower energy density generally increase satiety.
    """
    total_kcal = max(1.0, float(total_kcal or 0.0))
    protein_g = max(0.0, float(protein_g or 0.0))
    carbs_g = max(0.0, float(carbs_g or 0.0))
    fat_g = max(0.0, float(fat_g or 0.0))

    # Protein density (g per 1000 kcal)
    p_density = (protein_g / total_kcal) * 1000.0  # 0..200+ typically
    # Fat penalty (fat heavy meals tend to be less "filling per calorie" for many people)
    f_density = (fat_g / total_kcal) * 1000.0

    # Base from protein density, subtract fat density, subtract very high calorie meals a bit.
    score = (p_density * 0.55) - (f_density * 0.25) - (total_kcal / 60.0)

    # Normalize into 0..100 with gentle curve
    score = 50.0 + score
    return clamp(score, 0.0, 100.0)

def estimate_protein_bv_score(protein_g: float, total_kcal: float) -> float:
    """
    Protein bioavailability proxy (0-100). Without a food database of sources,
    we approximate using protein density as a 'quality signal' for practical coaching.
    """
    total_kcal = max(1.0, float(total_kcal or 0.0))
    protein_g = max(0.0, float(protein_g or 0.0))

    # Protein calories fraction
    p_frac = (protein_g * 4.0) / total_kcal  # 0..1
    # Map to 70..100
    score = 70.0 + (p_frac * 40.0) + (min(protein_g, 60.0) / 60.0) * 10.0
    return clamp(score, 0.0, 100.0)

def estimate_glycemic_load(carbs_g: float, gi: float = 72.0) -> Dict[str, Any]:
    """
    GL = carbs(g) * GI / 100. GI default is a general mixed-meal estimate.
    """
    carbs_g = max(0.0, float(carbs_g or 0.0))
    gi = clamp(gi, 0.0, 100.0)
    gl = carbs_g * gi / 100.0

    if gl < 10:
        level = "low"
    elif gl < 20:
        level = "medium"
    elif gl < 40:
        level = "high"
    else:
        level = "very_high"

    return {"gl": round1(gl), "level": level}

def estimate_ultra_processed_score(total_kcal: float, carbs_g: float, fat_g: float) -> float:
    """
    Ultra-processed score (0-10). Heuristic: higher energy + high fat + high refined carbs -> higher score.
    """
    total_kcal = max(1.0, float(total_kcal or 0.0))
    carbs_g = max(0.0, float(carbs_g or 0.0))
    fat_g = max(0.0, float(fat_g or 0.0))

    # density proxy
    carb_frac = (carbs_g * 4.0) / total_kcal
    fat_frac = (fat_g * 9.0) / total_kcal

    score = (carb_frac * 6.0) + (fat_frac * 6.0) + (total_kcal / 800.0) * 4.0
    return clamp(score, 0.0, 10.0)

def build_coaching_payload(total_kcal: float, protein_g: float, carbs_g: float, fat_g: float, mps_threshold_g: float = 2.5) -> Dict[str, Any]:
    sat = estimate_satiety_score(total_kcal, protein_g, carbs_g, fat_g)
    bv = estimate_protein_bv_score(protein_g, total_kcal)

    leucine = clamp(protein_g * 0.08, 0.0, 20.0)  # ~8% of protein is leucine, rough estimate
    mps_threshold_g = float(mps_threshold_g or 2.5)
    mps_triggered = leucine >= mps_threshold_g
    leucine_gap = max(0.0, mps_threshold_g - leucine)

    gl_obj = estimate_glycemic_load(carbs_g, gi=72.0)
    up = estimate_ultra_processed_score(total_kcal, carbs_g, fat_g)

    layman_terms = {
        "satiety": "How filling this meal is (higher = you’ll feel full longer).",
        "protein_bv": "Protein quality (how well your body can use the protein).",
        "leucine": "Leucine is the key amino acid that helps switch on muscle-building.",
        "glycemic_load": "Sugar-spike risk from carbs (higher = bigger blood sugar spike).",
        "ultra_processed": "How processed the food is (higher = more ultra-processed).",
    }

    msgs = []
    msgs.extend(leucine_messages(leucine_gap))
    msgs.append(f"Satiety Score: {round1(sat)}/100 — {layman_terms['satiety']}")
    msgs.append(f"Protein Bioavailability: {round1(bv)}/100 — {layman_terms['protein_bv']}")
    msgs.append(f"Glycemic Load: {gl_obj['gl']} ({gl_obj['level']}) — {layman_terms['glycemic_load']}")
    msgs.append(f"Ultra-Processed Score: {round1(up)}/10 — {layman_terms['ultra_processed']}")

    return {
        "satiety_score": round1(sat),
        "protein_bv_score": round1(bv),
        "leucine_estimate_g": round1(leucine),
        "mps_threshold_g": round1(mps_threshold_g),
        "mps_triggered": bool(mps_triggered),
        "glycemic_load": gl_obj,
        "ultra_processed_score": round1(up),
        "layman_terms": layman_terms,
        "messages": msgs,
    }


# -------------------- ANALYZE (PHOTO) --------------------
@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    day_local_iso = today_local.isoformat()

    # consume scan first (so failures still count? You can change this later.)
    usage_row = consume_one_scan(uid, today=today_local)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    detected_items = gemini_detect_foods(contents)
    logger.info(f"Detected items: {detected_items}")

    results = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0

    # Micronutrient totals (same keys as extract_micros_per_100g, without _units)
    total_micros = {
        "vitamin_d_ug": 0.0,
        "vitamin_b12_ug": 0.0,
        "iron_mg": 0.0,
        "magnesium_mg": 0.0,
        "calcium_mg": 0.0,
        "potassium_mg": 0.0,
        "sodium_mg": 0.0,
        "fiber_g": 0.0,
    }
    item_warnings: List[Dict[str, Any]] = []

    for d in detected_items:
        name = d["name"]
        grams = float(d["grams"])
        conf = float(d.get("confidence", 0))

        candidates = usda_search_candidates(name)
        details = None
        macros100 = None
        micros100 = None
        fdc_id = None
        last_item_err = None
        for cand in candidates[:6]:
            try:
                fdc_id = int(cand["fdcId"])
                maybe_details = usda_food_details(fdc_id)
                maybe_macros = extract_macros_per_100g(maybe_details)
                maybe_micros = extract_micros_per_100g(maybe_details)
                details = maybe_details
                macros100 = maybe_macros
                micros100 = maybe_micros
                break
            except Exception as e:
                last_item_err = str(getattr(e, "detail", e))
                continue

        if not details or not macros100:
            item_warnings.append(
                {
                    "name": name,
                    "warning": "nutrition_lookup_failed",
                    "detail": (last_item_err or "No usable USDA match found")[:220],
                }
            )
            results.append(
                {
                    "name": name,
                    "grams": round(grams, 1),
                    "confidence": round(conf, 2),
                    "kcal": 0.0,
                    "macros": {"protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0},
                    "micros": {},
                    "micros_units": None,
                    "unverified": True,
                }
            )
            continue

        factor = grams / 100.0
        kcal = macros100["kcal_per_100g"] * factor
        p = macros100["protein_g_per_100g"] * factor
        c = macros100["carbs_g_per_100g"] * factor
        f = macros100["fat_g_per_100g"] * factor

        micros = {}
        for k, v in (micros100 or {}).items():
            if k == "_units":
                continue
            micros[k] = round(float(v) * factor, 3)

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
            "micros": micros,
            "micros_units": micros100.get("_units"),

            "usda": {
                "fdcId": fdc_id,
                "description": (details or {}).get("description"),
                "dataType": (details or {}).get("dataType"),
            }
        })

        total_kcal += kcal
        total_p += p
        total_c += c
        total_f += f

        for mk, mv in micros.items():
            if mk in total_micros:
                total_micros[mk] += float(mv)


    # 🔒 coaching is pro+ (we don't block analyze; we just hide coaching fields)
    plan = (usage_row.get("plan") or DEFAULT_PLAN).lower()
    coaching_enabled = plan_at_least(plan, "pro")

    micros_payload = {
        "vitamin_d_ug": round(total_micros["vitamin_d_ug"], 3),
        "vitamin_b12_ug": round(total_micros["vitamin_b12_ug"], 3),
        "iron_mg": round(total_micros["iron_mg"], 3),
        "magnesium_mg": round(total_micros["magnesium_mg"], 3),
        "calcium_mg": round(total_micros["calcium_mg"], 3),
        "potassium_mg": round(total_micros["potassium_mg"], 3),
        "sodium_mg": round(total_micros["sodium_mg"], 3),
        "fiber_g": round(total_micros["fiber_g"], 3),
        "_units": {
            "vitamin_d_ug": "µg",
            "vitamin_b12_ug": "µg",
            "iron_mg": "mg",
            "magnesium_mg": "mg",
            "calcium_mg": "mg",
            "potassium_mg": "mg",
            "sodium_mg": "mg",
            "fiber_g": "g",
        },
    }

    response = {
        "source": "photo",
        "total_kcal": round(total_kcal, 1),
        "totals": {
            "kcal": round(total_kcal, 1),
            "total_kcal": round(total_kcal, 1),
            "protein_g": round(total_p, 1),
            "carbs_g": round(total_c, 1),
            "fat_g": round(total_f, 1),
            "micros": micros_payload,
        },
        "micros": micros_payload,
        "micronutrients": micros_payload,
        "items": results,
        "usage": {
            "plan": usage_row.get("plan"),
            "remaining_day": int(usage_row.get("remaining_day") or 0),
            "remaining_month": int(usage_row.get("remaining_month") or 0),
        },
    }
    if item_warnings:
        response["warnings"] = item_warnings[:8]

    scan_coaching = build_coaching_payload(
        total_kcal=total_kcal,
        protein_g=total_p,
        carbs_g=total_c,
        fat_g=total_f,
        mps_threshold_g=2.5,
    )

    if coaching_enabled:
        # Pro/Infinite get full coaching insights
        response["coaching"] = scan_coaching
    else:
        # Free/Elite/Advanced see a lock hint
        response["locked"] = {"feature": "coaching", "required_plan": "pro"}

    # ---- PHASE 3.1: meal_events (non-blocking) ----
    try:
        upsert_meal_event(
            uid,
            day_iso=day_local_iso,
            source="photo",
            event_type="photo_analyze",
            totals=response.get("totals"),
            micros=micros_payload,
            coaching=scan_coaching,
            items=results,
            tz=tz,
            tz_offset_min=tz_offset_min,
            extra={"plan": plan, "warnings": item_warnings[:8]},
        )
    except Exception as e:
        logger.warning(f"Meal events write skipped: {e}")

    # ---- DAILY TOTALS (non-blocking) ----
    try:
        inc = {
            "total_kcal": float(total_kcal or 0.0),
            "protein_g": float(total_p or 0.0),
            "carbs_g": float(total_c or 0.0),
            "fat_g": float(total_f or 0.0),
            "fiber_g": float(total_micros.get("fiber_g") or 0.0),
            "sodium_mg": float(total_micros.get("sodium_mg") or 0.0),
            "vitamin_d_ug": float(total_micros.get("vitamin_d_ug") or 0.0),
            "vitamin_b12_ug": float(total_micros.get("vitamin_b12_ug") or 0.0),
            "iron_mg": float(total_micros.get("iron_mg") or 0.0),
            "magnesium_mg": float(total_micros.get("magnesium_mg") or 0.0),
        }
        _ = add_to_daily_totals(uid, inc, day=day_local_iso)
        response["daily"] = build_daily_summary(uid, day=day_local_iso)
    except Exception as e:
        logger.warning(f"Daily totals update skipped: {e}")

    # ---- PHASE 3.1: daily_metrics + weekly_insights cache (non-blocking) ----
    try:
        memory = recompute_behavior_memory(uid, day_iso=day_local_iso, tz=tz, tz_offset_min=tz_offset_min)
        if isinstance(memory, dict):
            response["weekly_insights"] = memory.get("weekly_insights")
    except Exception as e:
        logger.warning(f"Behavior memory recompute skipped: {e}")

    return response

