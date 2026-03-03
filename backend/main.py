import io
import os
import json
import time
import re
import math
import hashlib
import logging
import datetime as dt
import uuid
import threading
import queue
import random
from collections import deque
from typing import Any, Dict, Optional, List, Tuple, Union, Literal
from zoneinfo import ZoneInfo

import requests
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Header, Body, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def _env_csv_list(name: str, default_csv: str = "") -> List[str]:
    raw = str(os.getenv(name, default_csv) or "").strip()
    if not raw:
        return []
    out: List[str] = []
    seen = set()
    for part in raw.split(","):
        val = str(part or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out

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
TBL_USER_WEEKLY_METRICS = "user_weekly_metrics"
TBL_MEAL_ANALYSES = "meal_analyses"
TBL_ANALYSIS_JOBS = "analysis_jobs"
TBL_ANALYSIS_MEMORY = "analysis_memory"
TBL_MEAL_EDITS = "meal_edits"
TBL_USER_CALIBRATION = "user_calibration"
TBL_COACH_MEMORY = "coach_memory"
TBL_COACH_FEEDBACK = "coach_feedback"
TBL_USER_FOOD_PRIORS = "user_food_priors"
TBL_COACH_VOICE_CACHE = "coach_voice_cache"
TBL_COACH_EVENTS = "coach_events"
TBL_WEEKLY_REPORTS = "weekly_reports"
TBL_PROGRAM_STATUS = "program_status"
TBL_CONFIDENCE_AUDIT = "confidence_audit"
TBL_CONFIDENCE_CALIBRATION_SETTINGS = "confidence_calibration_settings"
TBL_USER_AI_CONSENT = "user_ai_consent"
TBL_SUPPLEMENT_SCANS = "supplement_scans"
TBL_SUPPLEMENT_BRAND_PROFILES = "supplement_brand_profiles"
TBL_SUPPLEMENT_BATCH_PATTERNS = "supplement_batch_patterns"
TBL_SUPPLEMENT_USER_FLAGS = "supplement_user_flags"

# Plans (your requirements)
DEFAULT_PLAN = "free"
PLAN_ORDER = ["free", "elite", "advanced", "pro", "infinite"]
COACH_LLM_MODEL = os.getenv("COACH_LLM_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
BEHAVIOR_ENGINE_VERSION = "phase_3_2_v1"
SCAN_LLM_MODEL = os.getenv("SCAN_LLM_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
COACH_VOICE_LLM_MODEL = os.getenv("COACH_VOICE_LLM_MODEL", COACH_LLM_MODEL).strip() or COACH_LLM_MODEL
COACH_LLM_FALLBACK_MODELS: List[str] = []
COACH_VOICE_FALLBACK_MODELS: List[str] = []
COACH_TONE_REWRITE_FALLBACK_MODELS: List[str] = []
COACH_WEEKLY_REPORT_FALLBACK_MODELS: List[str] = []
try:
    COACH_LLM_TIMEOUT_SEC = max(3.0, min(8.0, float(os.getenv("COACH_LLM_TIMEOUT_SEC", "8").strip() or "8")))
except Exception:
    COACH_LLM_TIMEOUT_SEC = 8.0
try:
    COACH_VOICE_TIMEOUT_SEC = max(3.0, min(8.0, float(os.getenv("COACH_VOICE_TIMEOUT_SEC", "8").strip() or "8")))
except Exception:
    COACH_VOICE_TIMEOUT_SEC = 8.0
try:
    COACH_VOICE_CACHE_TTL_MIN = max(10, min(30, int(float(os.getenv("COACH_VOICE_CACHE_TTL_MIN", "20").strip() or "20"))))
except Exception:
    COACH_VOICE_CACHE_TTL_MIN = 20
ENABLE_CONFIDENCE_AUDIT_LOGGING = _env_flag("ENABLE_CONFIDENCE_AUDIT_LOGGING", True)
ENABLE_DYNAMIC_CONFIDENCE_THRESHOLDS = _env_flag("ENABLE_DYNAMIC_CONFIDENCE_THRESHOLDS", True)
ANALYZE_JOB_DIR = os.getenv("ANALYZE_JOB_DIR", "/tmp/kcal-analyze-jobs").strip() or "/tmp/kcal-analyze-jobs"
try:
    ANALYZE_JOB_POLL_TIMEOUT_SEC = max(30, min(600, int(float(os.getenv("ANALYZE_JOB_POLL_TIMEOUT_SEC", "180")))))
except Exception:
    ANALYZE_JOB_POLL_TIMEOUT_SEC = 180
try:
    SCAN_LLM_TIMEOUT_SEC = max(3.0, min(8.0, float(os.getenv("SCAN_LLM_TIMEOUT_SEC", "8").strip() or "8")))
except Exception:
    SCAN_LLM_TIMEOUT_SEC = 8.0
try:
    SCAN_LLM_MAX_ATTEMPTS = max(1, min(2, int(float(os.getenv("SCAN_LLM_MAX_ATTEMPTS", "2").strip() or "2"))))
except Exception:
    SCAN_LLM_MAX_ATTEMPTS = 2
try:
    SCAN_LLM_BACKOFF_BASE_SEC = max(0.25, min(5.0, float(os.getenv("SCAN_LLM_BACKOFF_BASE_SEC", "0.8").strip() or "0.8")))
except Exception:
    SCAN_LLM_BACKOFF_BASE_SEC = 0.8
try:
    SCAN_LLM_CIRCUIT_FAIL_THRESHOLD = max(2, min(20, int(float(os.getenv("SCAN_LLM_CIRCUIT_FAIL_THRESHOLD", "6").strip() or "6"))))
except Exception:
    SCAN_LLM_CIRCUIT_FAIL_THRESHOLD = 6
try:
    SCAN_LLM_CIRCUIT_OPEN_SEC = max(15, min(600, int(float(os.getenv("SCAN_LLM_CIRCUIT_OPEN_SEC", "90").strip() or "90"))))
except Exception:
    SCAN_LLM_CIRCUIT_OPEN_SEC = 90

# Goal defaults used when an older schema is missing one or more goal columns.
DEFAULT_DAILY_GOALS = {
    "kcal": 2000.0,
    "protein_g": 150.0,
    "carbs_g": 200.0,
    "fat_g": 70.0,
    "fiber_g": 30.0,
}

DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS = {
    "portion": {"confidence_threshold": 0.75, "range_expansion_factor": 1.0},
    "oil": {"confidence_threshold": 0.70, "range_expansion_factor": 1.0},
    "vision": {"confidence_threshold": 0.85, "range_expansion_factor": 1.0},
}
SUPPLEMENT_LEGAL_DISCLAIMER = (
    "CalorieClick Supplement Scanner provides an authenticity confidence score based on pattern analysis "
    "and community data. This is not a definitive determination of genuineness. "
    "We recommend verifying directly with the manufacturer for confirmation."
)
SUPPLEMENT_SUPPORTED_PRODUCT_TYPES = {"whey_protein"}
SUPPLEMENT_REQUIRED_STRUCTURED_KEYS = {
    "brand",
    "variant",
    "barcode",
    "batch_number",
    "mfg_date",
    "expiry_date",
    "ingredients",
    "nutrition_panel",
}
SYSTEM_CALIBRATION_USER_ID = "00000000-0000-0000-0000-000000000000"
_SINGLE_SUPPORTED_GEMINI_MODEL = "gemini-2.5-flash"
DEPRECATED_GEMINI_MODELS = {
    "gemini-2.0-flash-lite",
    "models/gemini-2.0-flash-lite",
    "gemini-3",
    "models/gemini-3",
    "gemini-3-pro",
    "models/gemini-3-pro",
    "gemini-3-flash-preview",
    "models/gemini-3-flash-preview",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-002",
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-pro-002",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-flash-latest",
    "models/gemini-1.5-flash-002",
    "models/gemini-1.5-pro",
    "models/gemini-1.5-pro-latest",
    "models/gemini-1.5-pro-002",
}

# Table-level guardrail: when a Supabase table is missing from schema cache, switch that table to memory fallback.
_DISABLED_SUPABASE_TABLES = set()
_COACH_EVENT_RING: Dict[str, deque] = {}
_TABLE_UNKNOWN_COLS: Dict[str, set] = {}
_UNKNOWN_COL_LOGGED: set = set()
_MISSING_TABLE_LOGGED: set = set()
_TABLE_JSON_FALLBACK_FIELD = {
    "daily_totals": "totals_json",
    "daily_metrics": "metrics_json",
    "weekly_insights": "insights_json",
    "user_weekly_metrics": "metrics_json",
    "meal_analyses": "payload",
    "meal_edits": "edit",
    "analysis_jobs": "result_json",
    "confidence_calibration_settings": "settings",
    "coach_memory": "payload",
    "daily_summary": "coach_json",
}
_TABLE_MIGRATION_HINTS = {
    "coach_memory": "create_coach_memory.sql",
    "coach_events": "create_coach_events.sql",
    "confidence_calibration_settings": "create_confidence_calibration_settings.sql",
    "meal_analyses": "create_meal_analyses.sql",
    "meal_edits": "create_meal_edits.sql",
    "analysis_jobs": "create_analysis_jobs.sql",
    "user_food_priors": "migrate_user_food_priors.sql",
    "user_ai_consent": "create_user_ai_consent.sql",
    "supplement_scans": "create_supplement_scanner.sql",
    "supplement_brand_profiles": "create_supplement_scanner.sql",
    "supplement_batch_patterns": "create_supplement_scanner.sql",
    "supplement_user_flags": "create_supplement_scanner.sql",
}
_EXPECTED_SCHEMA_TABLES = {
    "coach_memory",
    "confidence_calibration_settings",
    "meal_analyses",
    "meal_edits",
    "analysis_jobs",
    "user_food_priors",
    "user_ai_consent",
    "supplement_scans",
    "supplement_brand_profiles",
    "supplement_batch_patterns",
    "supplement_user_flags",
}

_ANALYSIS_JOBS_CACHE: Dict[str, Dict[str, Any]] = {}
_ANALYSIS_JOB_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=2048)
_ANALYSIS_JOB_WORKER_STARTED = False
_ANALYSIS_JOB_WORKER_LOCK = threading.Lock()
_AI_CONSENT_CACHE: Dict[str, Dict[str, Any]] = {}
_SCAN_LLM_CIRCUIT = {
    "state": "closed",
    "fail_count": 0,
    "opened_until": 0.0,
    "last_error": "",
}
_SCAN_LLM_CIRCUIT_LOCK = threading.Lock()


# -------------------- MIDDLEWARE --------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    req_id = str(request.headers.get("X-Request-Id") or "").strip() or _new_request_id()
    request.state.request_id = req_id
    logger.info(f"INCOMING {request.method} {request.url.path} request_id={req_id}")
    resp = await call_next(request)
    try:
        resp.headers["X-Request-Id"] = req_id
    except Exception:
        pass
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code} request_id={req_id}")
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


@app.on_event("startup")
def _startup_analysis_worker():
    _ensure_analysis_worker_started()


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


def _llm_model_candidates(primary_model: str, fallback_models: Optional[List[str]] = None) -> List[str]:
    model_name = _choose_single_llm_model(primary_model, fallback_models)
    return [model_name] if model_name else [_SINGLE_SUPPORTED_GEMINI_MODEL]


def is_deprecated_model(model_name: Any) -> bool:
    name = str(model_name or "").strip().lower()
    if not name:
        return False
    if name in DEPRECATED_GEMINI_MODELS:
        return True
    return "gemini-3" in name


def _choose_single_llm_model(primary_model: str, fallback_models: Optional[List[str]] = None) -> str:
    preferred = str(primary_model or "").strip() or _SINGLE_SUPPORTED_GEMINI_MODEL
    preferred = preferred.replace("models/", "")
    if is_deprecated_model(preferred):
        logger.warning("Deprecated model '%s' configured; forcing %s", preferred, _SINGLE_SUPPORTED_GEMINI_MODEL)
        return _SINGLE_SUPPORTED_GEMINI_MODEL
    if preferred != _SINGLE_SUPPORTED_GEMINI_MODEL:
        logger.warning("Unsupported model '%s' configured; forcing %s", preferred, _SINGLE_SUPPORTED_GEMINI_MODEL)
        return _SINGLE_SUPPORTED_GEMINI_MODEL
    return preferred


def _llm_timeout(limit: float = 10.0, default: float = 8.0) -> float:
    try:
        val = float(COACH_LLM_TIMEOUT_SEC)
    except Exception:
        val = float(default)
    return max(3.0, min(8.0, min(float(limit), val)))


def _scan_llm_timeout() -> float:
    try:
        val = float(SCAN_LLM_TIMEOUT_SEC)
    except Exception:
        val = 8.0
    return max(3.0, min(8.0, val))


def _is_retryable_llm_error(err: Any) -> bool:
    msg = str(err or "").lower()
    if not msg:
        return False
    markers = (
        "timeout",
        "timed out",
        "deadline",
        "429",
        "500",
        "502",
        "503",
        "504",
        "resource exhausted",
        "unavailable",
        "internal error",
        "rate limit",
    )
    return any(m in msg for m in markers)


def _is_timeout_error(err: Any) -> bool:
    msg = str(err or "").lower()
    if not msg:
        return False
    markers = ("timeout", "timed out", "deadline", "504")
    return any(m in msg for m in markers)


def _call_llm_with_timeout(
    prompt: List[Any],
    *,
    model_name: Optional[str] = None,
    timeout_sec: float = 8.0,
    retries: int = 1,
    purpose: str = "llm",
    request_id: str = "",
) -> Tuple[str, str, List[str]]:
    selected_model = _choose_single_llm_model(model_name or COACH_LLM_MODEL, None)
    purpose_key = str(purpose or "").strip().lower()
    if purpose_key.startswith("scan:vision_scan"):
        effective_timeout = 25.0
    else:
        effective_timeout = 8.0
    attempts = max(1, min(2, int(retries or 1) + 1))
    tried_models: List[str] = []
    last_err = ""
    for attempt in range(1, attempts + 1):
        _append_tried_model_once(tried_models, selected_model)
        started = time.time()
        try:
            model = genai.GenerativeModel(selected_model)
            resp = model.generate_content(
                prompt,
                request_options={"timeout": float(effective_timeout)},
            )
            text = str((resp.text or "")).strip()
            if not text:
                raise ValueError("empty response text")
            logger.info(
                "llm_call success purpose=%s request_id=%s model=%s attempt=%s latency_ms=%s",
                purpose,
                request_id,
                selected_model,
                attempt,
                int(max(0, round((time.time() - started) * 1000))),
            )
            return text, selected_model, tried_models
        except Exception as e:
            last_err = str(e)
            logger.warning(
                "llm_call failed purpose=%s request_id=%s model=%s attempt=%s/%s err=%s",
                purpose,
                request_id,
                selected_model,
                attempt,
                attempts,
                last_err[:220],
            )
            if attempt >= attempts or (not _is_retryable_llm_error(last_err)):
                break
            time.sleep(0.35 * attempt)

    raise HTTPException(
        status_code=502,
        detail=(
            {
                "error": "vision_timeout",
                "message": "Image analysis exceeded time limit",
                "raw": str(last_err or "")[:320],
                "tried_models": tried_models,
            }
            if purpose_key.startswith("scan:vision_scan") and _is_timeout_error(last_err)
            else {
                "error": "coach_llm_failed",
                "raw": str(last_err or "")[:320],
                "tried_models": tried_models,
            }
        ),
    )


def _is_retryable_scan_llm_error(err: Any) -> bool:
    text = str(err or "").lower()
    if not text:
        return False
    retry_markers = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "timeout",
        "timed out",
        "deadline",
        "resource exhausted",
        "unavailable",
        "internal error",
    )
    return any(mark in text for mark in retry_markers)


def _scan_circuit_allow() -> Tuple[bool, str]:
    now_ts = time.time()
    with _SCAN_LLM_CIRCUIT_LOCK:
        state = str(_SCAN_LLM_CIRCUIT.get("state") or "closed")
        opened_until = float(_safe_float(_SCAN_LLM_CIRCUIT.get("opened_until"), 0.0) or 0.0)
        if state == "open" and now_ts < opened_until:
            return False, str(_SCAN_LLM_CIRCUIT.get("last_error") or "scan_llm_circuit_open")
        if state == "open" and now_ts >= opened_until:
            _SCAN_LLM_CIRCUIT["state"] = "closed"
            _SCAN_LLM_CIRCUIT["fail_count"] = 0
            _SCAN_LLM_CIRCUIT["opened_until"] = 0.0
            _SCAN_LLM_CIRCUIT["last_error"] = ""
    return True, ""


def _scan_circuit_record_success() -> None:
    with _SCAN_LLM_CIRCUIT_LOCK:
        _SCAN_LLM_CIRCUIT["state"] = "closed"
        _SCAN_LLM_CIRCUIT["fail_count"] = 0
        _SCAN_LLM_CIRCUIT["opened_until"] = 0.0
        _SCAN_LLM_CIRCUIT["last_error"] = ""


def _scan_circuit_record_failure(err_text: str) -> None:
    with _SCAN_LLM_CIRCUIT_LOCK:
        fails = int(_safe_float(_SCAN_LLM_CIRCUIT.get("fail_count"), 0) or 0) + 1
        _SCAN_LLM_CIRCUIT["fail_count"] = fails
        _SCAN_LLM_CIRCUIT["last_error"] = str(err_text or "")[:220]
        if fails >= int(SCAN_LLM_CIRCUIT_FAIL_THRESHOLD):
            _SCAN_LLM_CIRCUIT["state"] = "open"
            _SCAN_LLM_CIRCUIT["opened_until"] = time.time() + float(SCAN_LLM_CIRCUIT_OPEN_SEC)


def _generate_scan_content(
    parts: List[Any],
    *,
    purpose: str,
    request_id: str = "",
    job_id: str = "",
) -> str:
    _require_gemini_key()
    allow, reason = _scan_circuit_allow()
    if not allow:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "scan_llm_circuit_open",
                "message": "Scan model is temporarily throttled. Please retry shortly.",
                "raw": str(reason or "")[:220],
            },
        )
    try:
        text, model_used, _ = _call_llm_with_timeout(
            parts,
            model_name=SCAN_LLM_MODEL,
            timeout_sec=float(_scan_llm_timeout()),
            retries=1,
            purpose=f"scan:{purpose}",
            request_id=request_id,
        )
        _scan_circuit_record_success()
        return text
    except Exception as e:
        if isinstance(e, HTTPException) and isinstance(e.detail, dict):
            if str(e.detail.get("error") or "").strip().lower() == "vision_timeout":
                raise e
        err_text = _http_exc_raw(e)
        _scan_circuit_record_failure(err_text)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "scan_llm_failed",
                "message": "Image analysis could not complete within timeout.",
                "model_used": _choose_single_llm_model(SCAN_LLM_MODEL, None),
                "attempts": 2,
                "raw": str(err_text or "")[:320],
            },
        )


def _tone_mode_from_source(source_value: Any) -> str:
    src = str(source_value or "").strip().lower()
    if src in {"llm", "cache", "cached_llm"}:
        return "llm"
    return "fallback"


def _new_request_id() -> str:
    return str(uuid.uuid4())


def _generate_with_model_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    primary_model: str,
    fallback_models: Optional[List[str]],
    timeout_sec: float,
    primary_attempts: int = 2,
    fallback_attempts: int = 1,
    max_models: int = 4,
) -> Tuple[str, str, List[str]]:
    txt, model_used, tried = _call_llm_with_timeout(
        [system_prompt, user_prompt],
        model_name=_choose_single_llm_model(primary_model, fallback_models),
        timeout_sec=float(_llm_timeout(limit=10.0, default=float(timeout_sec or 8.0))),
        retries=1,
        purpose="coach_fallback_wrapper",
    )
    return txt, model_used, tried


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


# -------------------- Pydantic / Scan Contracts --------------------
def _model_dump(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


def _model_validate(cls: Any, data: Dict[str, Any]):
    if hasattr(cls, "model_validate"):
        return cls.model_validate(data)
    return cls.parse_obj(data)


def _clamp01(v: Any, default: float = 0.0) -> float:
    n = _safe_float(v, default)
    if n is None:
        n = default
    return max(0.0, min(1.0, float(n)))


class ScanCandidateModel(BaseModel):
    candidate_id: str = ""
    label: str
    confidence: float = 0.0
    evidence: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    portion_guess_g: float = 0.0


class ClarifyingQuestionModel(BaseModel):
    ask: str
    options: List[str] = Field(default_factory=list)


class EditableItemModel(BaseModel):
    item_id: str
    name: str
    grams: float
    cooking_method: str = "unknown"
    oil_added_tsp: float = 0.0
    confidence: float = 0.0
    candidate_alternatives: List[str] = Field(default_factory=list)


class EditableContextModel(BaseModel):
    items: List[EditableItemModel] = Field(default_factory=list)


class VisionScanV1Model(BaseModel):
    vision_confidence: float = 0.0
    top_candidates: List[ScanCandidateModel] = Field(default_factory=list)
    clarifying_question: Optional[ClarifyingQuestionModel] = None
    editable_context: EditableContextModel = Field(default_factory=EditableContextModel)
    items: List[EditableItemModel] = Field(default_factory=list)


class MealQAIssueModel(BaseModel):
    issue_type: str
    severity: str = "medium"
    message: str


class MealQAFixModel(BaseModel):
    label: str
    patch: Dict[str, Any] = Field(default_factory=dict)


class MealQAModel(BaseModel):
    qa_score: float = 75.0
    issues: List[MealQAIssueModel] = Field(default_factory=list)
    one_tap_fixes: List[MealQAFixModel] = Field(default_factory=list)
    ask_to_confirm: Optional[str] = None


class SetCookingMethodEdit(BaseModel):
    item_id: str
    method: str


class SetOilAddedEdit(BaseModel):
    item_id: str
    tsp: float


class SwapItemEdit(BaseModel):
    item_id: str
    new_name: str


class PortionMultiplierEdit(BaseModel):
    item_id: str = ""
    multiplier: float


class AnalyzeRerunEditsModel(BaseModel):
    portion_multiplier: Optional[Union[float, PortionMultiplierEdit]] = None
    set_cooking_method: Optional[SetCookingMethodEdit] = None
    set_oil_added_tsp: Optional[SetOilAddedEdit] = None
    swap_item: Optional[SwapItemEdit] = None
    clarifying_answer: Optional[str] = None


class AnalyzeRerunRequestModel(BaseModel):
    analysis_id: str
    edits: AnalyzeRerunEditsModel = Field(default_factory=AnalyzeRerunEditsModel)


def _friendly_rerun_validation_error(exc: Exception) -> Dict[str, Any]:
    field = "edits"
    message = "Invalid rerun edits payload."
    raw = str(exc)[:240]
    try:
        details = exc.errors() if hasattr(exc, "errors") else []
    except Exception:
        details = []
    if isinstance(details, list) and details:
        first = details[0] if isinstance(details[0], dict) else {}
        loc = first.get("loc") if isinstance(first.get("loc"), (list, tuple)) else []
        parts = [str(x) for x in loc if str(x).strip()]
        if parts:
            field = ".".join(parts)
        msg = str(first.get("msg") or "").strip()
        if msg:
            message = f"Invalid value for {field}: {msg}"
    if raw and message == "Invalid rerun edits payload.":
        message = "Invalid rerun edits payload. Please retry with structured edit data."
    return {
        "error_code": "invalid_rerun_payload",
        "message": message,
        "field": field,
        "expected_schema": {
            "portion_multiplier": {"item_id": "string", "multiplier": "number"},
            "set_oil_added_tsp": {"item_id": "string", "tsp": "number"},
            "set_cooking_method": {"item_id": "string", "method": "string"},
            "swap_item": {"item_id": "string", "new_name": "string"},
            "edits_array_action": {
                "type": "set_oil_added_tsp|set_cooking_method|swap_candidate|swap_item|set_portion_multiplier",
                "item_id": "string",
            },
        },
        "raw": raw,
    }


def _extract_items_from_analysis_row(existing: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    row = existing if isinstance(existing, dict) else {}
    items_raw = _parse_jsonish(row.get("items_json"), [])
    if not isinstance(items_raw, list) or not items_raw:
        llm_raw = _parse_jsonish(row.get("llm_outputs_json"), {})
        if isinstance(llm_raw, dict):
            vision_raw = llm_raw.get("vision") if isinstance(llm_raw.get("vision"), dict) else {}
            items_raw = vision_raw.get("items") if isinstance(vision_raw.get("items"), list) else []
    out: List[Dict[str, Any]] = []
    for item in (items_raw or []):
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _default_item_id_from_analysis_row(existing: Optional[Dict[str, Any]]) -> str:
    items_raw = _extract_items_from_analysis_row(existing)
    for idx, item in enumerate(items_raw or []):
        iid = str(item.get("item_id") or "").strip()
        if iid:
            return iid
        name = str(item.get("name") or "").strip()
        if name:
            return f"i{idx + 1}"
    return ""


def _candidate_name_for_item(existing: Optional[Dict[str, Any]], item_id: str, candidate_index: Any) -> str:
    iid = str(item_id or "").strip()
    idx_raw = _safe_float(candidate_index, None)
    idx = int(idx_raw) if idx_raw is not None else -1
    if idx < 0:
        return ""
    for pos, item in enumerate(_extract_items_from_analysis_row(existing)):
        current_id = str(item.get("item_id") or "").strip() or f"i{pos + 1}"
        if iid and current_id != iid:
            continue
        arr = item.get("candidate_alternatives")
        if isinstance(arr, list) and idx < len(arr):
            return str(arr[idx] or "").strip()
    return ""


def _merge_rerun_edit_action(edits: Dict[str, Any], action: Dict[str, Any], default_item_id: str, existing: Optional[Dict[str, Any]]) -> None:
    act = action if isinstance(action, dict) else {}
    action_type = str(act.get("type") or act.get("edit_type") or "").strip().lower()
    if not action_type:
        return
    item_id = str(act.get("item_id") or default_item_id or "").strip()
    if action_type == "set_oil_added_tsp":
        tsp = _safe_float(act.get("tsp", act.get("value")), None)
        if tsp is not None:
            edits["set_oil_added_tsp"] = {"item_id": item_id, "tsp": max(0.0, float(tsp))}
        return
    if action_type == "set_cooking_method":
        method = str(act.get("method") or act.get("value") or "").strip().lower()
        if method:
            edits["set_cooking_method"] = {"item_id": item_id, "method": method}
        return
    if action_type in {"swap_candidate", "swap_item"}:
        new_name = str(act.get("new_name") or act.get("to_name") or act.get("candidate_name") or "").strip()
        if not new_name:
            new_name = _candidate_name_for_item(existing, item_id, act.get("candidate_index"))
        if new_name:
            edits["swap_item"] = {"item_id": item_id, "new_name": new_name}
        return
    if action_type in {"set_portion_g", "set_portion_grams"}:
        grams = _safe_float(act.get("grams", act.get("value")), None)
        if grams is not None and grams > 0:
            edits["portion_multiplier"] = {"item_id": item_id, "multiplier": max(0.3, min(3.0, float(grams) / 100.0))}
        return
    if action_type == "set_portion_multiplier":
        mult = _safe_float(act.get("multiplier", act.get("value")), None)
        if mult is not None:
            edits["portion_multiplier"] = {"item_id": item_id, "multiplier": max(0.3, min(3.0, float(mult)))}
        return
    if action_type in {"clarifying_answer", "set_clarifying_answer"}:
        answer = str(act.get("value") or act.get("clarifying_answer") or "").strip()
        if answer:
            edits["clarifying_answer"] = answer
        return


def _coerce_rerun_payload(
    payload: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    out = dict(src)
    raw_analysis_id = str(src.get("analysis_id") or src.get("scan_id") or "").strip()
    if raw_analysis_id:
        out["analysis_id"] = raw_analysis_id
    edits_raw = src.get("edits")
    if edits_raw is None:
        edits_raw = src.get("edit")
    edits = dict(edits_raw) if isinstance(edits_raw, dict) else {}
    coercion_errors: List[str] = []

    default_item_id = _default_item_id_from_analysis_row(existing)

    if isinstance(edits_raw, list):
        for action in edits_raw:
            if isinstance(action, dict):
                if str(action.get("type") or action.get("edit_type") or "").strip().lower() in {"swap_candidate", "swap_item"}:
                    action_item_id = str(action.get("item_id") or default_item_id or "").strip()
                    if not action_item_id:
                        coercion_errors.append("swap_candidate missing item_id")
                    idx_val = action.get("candidate_index")
                    if idx_val is not None:
                        idx_float = _safe_float(idx_val, None)
                        if idx_float is None:
                            coercion_errors.append("swap_candidate candidate_index must be a number")
                        elif idx_float < 0:
                            coercion_errors.append("swap_candidate candidate_index out of range")
                _merge_rerun_edit_action(edits, action, default_item_id, existing)
    if isinstance(src.get("edit"), dict):
        edit_one = dict(src.get("edit") or {})
        _merge_rerun_edit_action(edits, edit_one, default_item_id, existing)
        for k, v in edit_one.items():
            if k not in edits and k != "type":
                edits[k] = v

    if isinstance(src.get("edits"), dict):
        for k, v in src.get("edits").items():
            if k not in edits:
                edits[k] = v

    clarifying_raw = src.get("clarifying_answer")
    if clarifying_raw is not None and not edits.get("clarifying_answer"):
        clarifying_txt = str(clarifying_raw or "").strip()
        if clarifying_txt:
            edits["clarifying_answer"] = clarifying_txt

    # Allow legacy shape: set_oil_added_tsp: 0 (or "0.5"), and coerce it into the structured object.
    oil_raw = edits.get("set_oil_added_tsp")
    if isinstance(oil_raw, (int, float, str)) and str(oil_raw).strip() != "":
        oil_tsp = _safe_float(oil_raw, None)
        if oil_tsp is not None:
            item_id = ""
            scm = edits.get("set_cooking_method")
            if isinstance(scm, dict):
                item_id = str(scm.get("item_id") or "").strip()
            if not item_id:
                item_id = default_item_id
            edits["set_oil_added_tsp"] = {"item_id": item_id or "", "tsp": max(0.0, float(oil_tsp))}
    elif isinstance(oil_raw, dict):
        oil_tsp = _safe_float(oil_raw.get("tsp"), None)
        if oil_tsp is not None:
            item_id = str(oil_raw.get("item_id") or "").strip() or default_item_id
            edits["set_oil_added_tsp"] = {"item_id": item_id, "tsp": max(0.0, float(oil_tsp))}

    # Allow legacy shape: set_cooking_method: "air_fried"
    scm_raw = edits.get("set_cooking_method")
    if isinstance(scm_raw, str) and scm_raw.strip():
        method = scm_raw.strip().lower()
        item_id = default_item_id
        edits["set_cooking_method"] = {"item_id": item_id or "", "method": method}
    elif isinstance(scm_raw, dict):
        method = str(scm_raw.get("method") or "").strip().lower()
        if method:
            item_id = str(scm_raw.get("item_id") or "").strip() or default_item_id
            edits["set_cooking_method"] = {"item_id": item_id, "method": method}

    # Allow legacy shape: swap_item: "vegetarian aloo curry"
    swap_raw = edits.get("swap_item")
    if isinstance(swap_raw, str) and swap_raw.strip():
        new_name = swap_raw.strip()
        item_id = default_item_id
        edits["swap_item"] = {"item_id": item_id or "", "new_name": new_name}
    elif isinstance(swap_raw, dict):
        new_name = str(swap_raw.get("new_name") or swap_raw.get("to_name") or "").strip()
        if not new_name:
            new_name = _candidate_name_for_item(existing, str(swap_raw.get("item_id") or default_item_id), swap_raw.get("candidate_index"))
        if new_name:
            item_id = str(swap_raw.get("item_id") or "").strip() or default_item_id
            edits["swap_item"] = {"item_id": item_id, "new_name": new_name}

    # Accept shorthand key: swap_candidate with candidate_index/candidate_name.
    swap_candidate_raw = edits.get("swap_candidate")
    if isinstance(swap_candidate_raw, dict):
        item_id = str(swap_candidate_raw.get("item_id") or "").strip() or default_item_id
        if not item_id:
            coercion_errors.append("swap_candidate missing item_id")
        new_name = str(
            swap_candidate_raw.get("candidate_name")
            or swap_candidate_raw.get("new_name")
            or swap_candidate_raw.get("to_name")
            or ""
        ).strip()
        idx_raw = swap_candidate_raw.get("candidate_index")
        if not new_name:
            idx_float = _safe_float(idx_raw, None)
            if idx_raw is not None and idx_float is None:
                coercion_errors.append("swap_candidate candidate_index must be a number")
            elif idx_float is not None and idx_float < 0:
                coercion_errors.append("swap_candidate candidate_index out of range")
            new_name = _candidate_name_for_item(existing, item_id, idx_raw)
            if (idx_raw is not None) and (not new_name):
                coercion_errors.append("swap_candidate candidate_index out of range")
        if new_name:
            edits["swap_item"] = {"item_id": item_id, "new_name": new_name}

    # Allow canonical shape: portion_multiplier: {"item_id":"i1","multiplier":0.85}
    portion_raw = edits.get("portion_multiplier")
    if isinstance(portion_raw, dict):
        mul = _safe_float(portion_raw.get("multiplier"), None)
        if mul is not None:
            item_id = str(portion_raw.get("item_id") or "").strip()
            edits["portion_multiplier"] = {
                "item_id": item_id or default_item_id,
                "multiplier": max(0.3, min(3.0, float(mul))),
            }
    elif isinstance(portion_raw, (int, float, str)) and str(portion_raw).strip() != "":
        mul = _safe_float(portion_raw, None)
        if mul is not None:
            edits["portion_multiplier"] = {
                "item_id": default_item_id,
                "multiplier": max(0.3, min(3.0, float(mul))),
            }

    out["edits"] = edits
    if coercion_errors:
        deduped: List[str] = []
        for msg in coercion_errors:
            txt = str(msg or "").strip()
            if txt and txt not in deduped:
                deduped.append(txt)
        if deduped:
            out["_coercion_errors"] = deduped
    return out


class CoachVoiceMealModel(BaseModel):
    meal_id: str = ""
    ts: str = ""
    label: str = ""
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    confidence: float = 0.0
    notes: str = ""


class CoachVoiceRecentMessageModel(BaseModel):
    advice_key: str = ""
    ts: str = ""
    summary: str = ""


class CoachVoiceProfileModel(BaseModel):
    goal_type: str = "fat_loss"
    diet_style: str = "non-veg"
    training_days_per_week: int = 0
    training_time: str = "evening"


class CoachVoiceRequestModel(BaseModel):
    user_id: str
    day: str
    payload_hash: str = ""
    goals: Dict[str, Any] = Field(default_factory=dict)
    consumed: Dict[str, Any] = Field(default_factory=dict)
    meals: List[CoachVoiceMealModel] = Field(default_factory=list)
    recent_messages: List[CoachVoiceRecentMessageModel] = Field(default_factory=list)
    user_profile: CoachVoiceProfileModel = Field(default_factory=CoachVoiceProfileModel)
    tone_preference: str = "supportive"
    tone_id: str = ""


class CoachFeedbackConfirmedItemModel(BaseModel):
    name: str = ""
    grams: float = 0.0


class CoachFeedbackCorrectionsModel(BaseModel):
    item_id: str = ""
    item_name: str = ""
    food_key: str = ""
    cooking_method: str = ""
    oil_added_tsp: Optional[float] = None
    portion_multiplier: Optional[float] = None
    confirmed_items: List[CoachFeedbackConfirmedItemModel] = Field(default_factory=list)


class CoachFeedbackRequestModel(BaseModel):
    user_id: str
    analysis_id: str = ""
    meal_id: str = ""
    feedback_type: str = "overall"
    rating: Optional[int] = None
    free_text: str = ""
    corrections: CoachFeedbackCorrectionsModel = Field(default_factory=CoachFeedbackCorrectionsModel)


class CoachToneRewriteDiagnosisModel(BaseModel):
    pattern: str
    impact: str


class CoachToneRewriteActionModel(BaseModel):
    title: str
    why: str
    how: str


class CoachToneRewriteClarifyingQuestionModel(BaseModel):
    ask: str
    options: List[str] = Field(default_factory=list)


class CoachToneRewriteMicrocopyModel(BaseModel):
    updating_text: str
    updated_text: str


class CoachToneRewriteCopyChecksModel(BaseModel):
    emoji_count: int = 0
    hinglish_phrase_count: int = 0
    signature_phrase_used: bool = False
    banned_words_found: List[str] = Field(default_factory=list)
    constraints_passed: bool = False
    notes: str = ""


class CoachToneRewriteV1Model(BaseModel):
    tone_id: Literal["supportive", "strict", "funny", "indian_coach"]
    source: Literal["llm_rewrite", "rules_fallback_rewrite"]
    freshness: Literal["updated_now", "updating", "stale_cache"]
    coach_summary: str
    diagnosis: CoachToneRewriteDiagnosisModel
    actions: List[CoachToneRewriteActionModel] = Field(default_factory=list)
    clarifying_question: Optional[CoachToneRewriteClarifyingQuestionModel] = None
    microcopy: CoachToneRewriteMicrocopyModel
    copy_checks: CoachToneRewriteCopyChecksModel


class WeeklyReportRequestModel(BaseModel):
    user_id: str
    week_start: str = ""
    tz: str = ""
    tz_offset_min: Optional[int] = None
    daily_rows: List[Dict[str, Any]] = Field(default_factory=list)
    training_days_per_week: Optional[int] = None
    tone_preference: str = "supportive"


class ProgramCreateRequestModel(BaseModel):
    user_id: str
    program_goal: str = "fat_loss"
    duration_weeks: int = 12
    tone_preference: str = "supportive"
    user_profile: CoachVoiceProfileModel = Field(default_factory=CoachVoiceProfileModel)


class ProgramDailyCheckinRequestModel(BaseModel):
    user_id: str
    date: str = ""
    adherence_score: Optional[float] = None
    notes: str = ""
    signals: Dict[str, Any] = Field(default_factory=dict)


class SupplementIssueReportRequestModel(BaseModel):
    user_id: str
    scan_id: str
    issue_type: str = "suspicious_packaging"
    description: str = ""


_MEAL_ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}


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
    if not rows:
        return None
    row = rows[0] if isinstance(rows[0], dict) else {}
    return _expand_row_from_json_fallback(table, row)


def sb_get_many(table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.get(url, headers=supabase_headers(), params=params, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail={"error": "Supabase list read failed", "raw": r.text})
    rows = r.json() or []
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(_expand_row_from_json_fallback(table, row))
    return out

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


def sb_delete(table: str, match: Dict[str, str]) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {"select": "user_id"}
    params.update(match or {})

    headers = supabase_headers()
    headers["Prefer"] = "return=minimal"

    r = requests.delete(url, headers=headers, params=params, timeout=20)
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail={"error": "Supabase delete failed", "raw": r.text})


def _http_exc_raw(e: Exception) -> str:
    if isinstance(e, HTTPException):
        detail = e.detail if isinstance(e.detail, dict) else {"raw": str(e.detail)}
        return str(detail.get("raw") or detail.get("error") or detail)
    return str(e)


def _table_key(table: Any) -> str:
    return str(table or "").strip().lower()


def _is_missing_table_error(raw: str, table: Any = "") -> bool:
    text = str(raw or "").lower()
    if not text:
        return False
    if ("pgrst205" not in text) and ("could not find the table" not in text):
        return False
    tkey = _table_key(table)
    if not tkey:
        return True
    return (f"'{tkey}'" in text) or (f".{tkey}" in text) or ("could not find the table" in text)


def _is_table_disabled(table: Any) -> bool:
    return _table_key(table) in _DISABLED_SUPABASE_TABLES


def _mark_table_unavailable(table: Any, err: Exception) -> bool:
    tkey = _table_key(table)
    if not tkey:
        return False
    raw = _http_exc_raw(err)
    if not _is_missing_table_error(raw, tkey):
        return False
    if tkey not in _DISABLED_SUPABASE_TABLES:
        _DISABLED_SUPABASE_TABLES.add(tkey)
    if tkey not in _MISSING_TABLE_LOGGED:
        _MISSING_TABLE_LOGGED.add(tkey)
        migration_hint = _TABLE_MIGRATION_HINTS.get(tkey)
        if migration_hint:
            logger.warning(
                f"Supabase table '{tkey}' missing from schema cache; run migration {migration_hint}. "
                "Service is using graceful fallback for now."
            )
        else:
            logger.warning(f"Supabase table '{tkey}' not available; switching to graceful fallback for this table.")
    return True


def _append_tried_model_once(tried_models: List[str], model_name: Any) -> None:
    val = str(model_name or "").strip()
    if not val:
        return
    if val in tried_models:
        return
    tried_models.append(val)


def _missing_schema_debug() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    missing = {
        str(x or "").strip()
        for x in _DISABLED_SUPABASE_TABLES
        if str(x or "").strip() and str(x or "").strip() in _EXPECTED_SCHEMA_TABLES
    }
    for t in sorted(missing):
        if not t:
            continue
        out.append(
            {
                "table": t,
                "migration": str(_TABLE_MIGRATION_HINTS.get(t) or ""),
            }
        )
    return out


def _attach_debug_schema(resp: Dict[str, Any], debug: bool) -> Dict[str, Any]:
    out = dict(resp or {})
    if not bool(debug):
        return out
    dbg = out.get("debug") if isinstance(out.get("debug"), dict) else {}
    dbg = dict(dbg)
    dbg["missing_schema"] = _missing_schema_debug()
    llm_used = str(out.get("model_used") or out.get("llm_model_used") or "").strip()
    llm_tried = out.get("tried_models")
    if not isinstance(llm_tried, list):
        llm_tried = out.get("llm_tried_models")
    if not isinstance(llm_tried, list):
        llm_tried = []
    tried_list: List[str] = []
    for m in llm_tried:
        _append_tried_model_once(tried_list, m)
    llm_error = str(out.get("error_code") or out.get("llm_error_code") or "").strip()
    source_val = str(out.get("source") or out.get("fli_source") or out.get("reasoning_source") or "").strip().lower()
    dbg["llm"] = {
        "source": source_val or "rules",
        "used_model": llm_used,
        "tried_models": tried_list,
        "error": llm_error,
    }
    out["debug"] = dbg
    return out


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


def _is_duplicate_key_error(raw: Any) -> bool:
    text = str(raw or "").lower()
    if not text:
        return False
    return ("23505" in text) or ("duplicate key value violates unique constraint" in text)


def _json_fallback_field_for_table(table: str) -> str:
    return str(_TABLE_JSON_FALLBACK_FIELD.get(_table_key(table)) or "").strip()


def _row_as_json_obj(value: Any) -> Dict[str, Any]:
    parsed = _parse_jsonish(value, {})
    if isinstance(parsed, dict):
        return dict(parsed)
    return {}


def _expand_row_from_json_fallback(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row or {})
    json_field = _json_fallback_field_for_table(table)
    if not json_field:
        return out
    nested = _row_as_json_obj(out.get(json_field))
    for key, value in nested.items():
        if key not in out:
            out[key] = value

    tkey = _table_key(table)
    if tkey == _table_key(TBL_MEAL_ANALYSES):
        analysis_id = str(out.get("analysis_id") or nested.get("analysis_id") or out.get("scan_id") or "").strip()
        if analysis_id:
            out["analysis_id"] = analysis_id
            out.setdefault("scan_id", analysis_id)
    elif tkey == _table_key(TBL_MEAL_EDITS):
        if "edit_patch_json" not in out and isinstance(nested.get("edit_patch_json"), dict):
            out["edit_patch_json"] = nested.get("edit_patch_json")
        if "analysis_id" not in out:
            out["analysis_id"] = str(out.get("scan_id") or nested.get("analysis_id") or "").strip()
    return out


def _merge_unknown_column_into_json_payload(table: str, payload: Dict[str, Any], bad_col: str) -> bool:
    if not bad_col or bad_col not in payload:
        return False
    json_field = _json_fallback_field_for_table(table)
    if not json_field:
        return False
    if bad_col == json_field:
        return False
    try:
        nested = _row_as_json_obj(payload.get(json_field))
        nested[bad_col] = payload.get(bad_col)
        payload[json_field] = nested
        payload.pop(bad_col, None)
        return True
    except Exception:
        return False


def _log_unknown_column_once(table: str, op: str, bad_col: str, moved_to_json: bool) -> None:
    tkey = _table_key(table)
    if not tkey or not bad_col:
        return
    _TABLE_UNKNOWN_COLS.setdefault(tkey, set()).add(bad_col)
    key = (tkey, bad_col, bool(moved_to_json))
    if key in _UNKNOWN_COL_LOGGED:
        return
    _UNKNOWN_COL_LOGGED.add(key)
    if moved_to_json:
        logger.warning(f"Unknown column {bad_col} during {op} on {tkey}; moved to JSON payload fallback.")
    else:
        logger.warning(f"Dropping unknown column during {op}: {bad_col} ({tkey})")


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
                moved = _merge_unknown_column_into_json_payload(table, payload, bad_col)
                if not moved:
                    payload.pop(bad_col, None)
                _log_unknown_column_once(table, "insert", bad_col, moved)
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
                moved = _merge_unknown_column_into_json_payload(table, payload, bad_col)
                if not moved:
                    payload.pop(bad_col, None)
                _log_unknown_column_once(table, "patch", bad_col, moved)
                continue
            raise
    return payload


def _parse_jsonish(v: Any, default: Any):
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return default
    return default


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload or b"").hexdigest()


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(str(path or "").strip(), exist_ok=True)
    except Exception:
        pass


def _analysis_cache_set(row: Dict[str, Any]) -> None:
    aid = str(row.get("analysis_id") or "").strip()
    if not aid:
        return
    _MEAL_ANALYSIS_CACHE[aid] = dict(row)


def _analysis_cache_get(analysis_id: str) -> Optional[Dict[str, Any]]:
    return _MEAL_ANALYSIS_CACHE.get(str(analysis_id or "").strip())


def _analysis_jobs_cache_set(row: Dict[str, Any]) -> None:
    rid = str((row or {}).get("id") or (row or {}).get("job_id") or "").strip()
    if not rid:
        return
    out = dict(row or {})
    out["id"] = rid
    out["job_id"] = rid
    _ANALYSIS_JOBS_CACHE[rid] = out


def _analysis_jobs_cache_get(job_id: str) -> Optional[Dict[str, Any]]:
    return _ANALYSIS_JOBS_CACHE.get(str(job_id or "").strip())


def _analysis_job_file_path(job_id: str) -> str:
    safe_id = str(job_id or "").strip() or str(uuid.uuid4())
    _ensure_dir(ANALYZE_JOB_DIR)
    return os.path.join(ANALYZE_JOB_DIR, f"{safe_id}.img")


def _analysis_job_progress(status: str) -> int:
    s = str(status or "").strip().lower()
    if s == "queued":
        return 5
    if s == "running":
        return 50
    if s == "done":
        return 100
    if s == "failed":
        return 100
    return 0


def _store_analysis_job(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row or {})
    rid = str(payload.get("id") or payload.get("job_id") or "").strip()
    if not rid:
        rid = str(uuid.uuid4())
    payload["id"] = rid
    payload["job_id"] = rid
    payload["updated_at"] = payload.get("updated_at") or _now_utc_naive().isoformat()
    payload["created_at"] = payload.get("created_at") or payload["updated_at"]
    _analysis_jobs_cache_set(payload)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY) or _is_table_disabled(TBL_ANALYSIS_JOBS):
        return payload
    try:
        stored = _sb_insert_with_column_fallback(
            TBL_ANALYSIS_JOBS,
            {
                "id": rid,
                "user_id": str(payload.get("user_id") or "").strip(),
                "status": str(payload.get("status") or "queued").strip().lower() or "queued",
                "created_at": payload["created_at"],
                "updated_at": payload["updated_at"],
                "input_path": str(payload.get("input_path") or "").strip() or None,
                "result_json": payload.get("result_json"),
                "error": str(payload.get("error") or "").strip() or None,
                "request_id": str(payload.get("request_id") or "").strip() or None,
            },
            locked_cols={"id", "user_id"},
        )
        merged = dict(payload)
        merged.update(dict(stored or {}))
        _analysis_jobs_cache_set(merged)
        return merged
    except Exception as e:
        if not _mark_table_unavailable(TBL_ANALYSIS_JOBS, e):
            logger.info(f"analysis job write skipped: {e}")
        return payload


def _patch_analysis_job(job_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    rid = str(job_id or "").strip()
    if not rid:
        return {}
    existing = dict(_analysis_jobs_cache_get(rid) or {})
    updated = dict(existing)
    updated.update(dict(patch or {}))
    updated["id"] = rid
    updated["job_id"] = rid
    updated["updated_at"] = _now_utc_naive().isoformat()
    _analysis_jobs_cache_set(updated)

    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY) or _is_table_disabled(TBL_ANALYSIS_JOBS):
        return updated
    try:
        patch_payload = {
            "status": str(updated.get("status") or "").strip().lower() or None,
            "updated_at": updated.get("updated_at"),
            "result_json": updated.get("result_json"),
            "error": str(updated.get("error") or "").strip() or None,
            "input_path": str(updated.get("input_path") or "").strip() or None,
            "request_id": str(updated.get("request_id") or "").strip() or None,
        }
        _sb_patch_with_column_fallback(TBL_ANALYSIS_JOBS, {"id": f"eq.{rid}"}, patch_payload)
    except Exception as e:
        if not _mark_table_unavailable(TBL_ANALYSIS_JOBS, e):
            logger.info(f"analysis job patch skipped: {e}")
    return updated


def _get_analysis_job(job_id: str) -> Optional[Dict[str, Any]]:
    rid = str(job_id or "").strip()
    if not rid:
        return None
    mem = _analysis_jobs_cache_get(rid)
    if isinstance(mem, dict):
        return dict(mem)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY) or _is_table_disabled(TBL_ANALYSIS_JOBS):
        return None
    try:
        row = sb_get_one(TBL_ANALYSIS_JOBS, params={"select": "*", "id": f"eq.{rid}", "limit": "1"})
        if isinstance(row, dict):
            _analysis_jobs_cache_set(row)
            return dict(row)
    except Exception as e:
        if not _mark_table_unavailable(TBL_ANALYSIS_JOBS, e):
            logger.info(f"analysis job read skipped: {e}")
    return None


def _job_error_text(err: Exception) -> str:
    if isinstance(err, HTTPException):
        detail = err.detail
        if isinstance(detail, dict):
            msg = detail.get("message") or detail.get("error") or detail.get("raw") or detail
            return str(msg)[:360]
        return str(detail)[:360]
    return str(err)[:360]


def _minimal_analysis_fallback_result(job_id: str, request_id: str, error_text: str) -> Dict[str, Any]:
    micros = _build_micros_payload({})
    now_iso = _now_utc_naive().isoformat()
    return {
        "job_id": str(job_id or ""),
        "request_id": str(request_id or ""),
        "source": "fallback",
        "status": "done",
        "analysis_id": "",
        "input_scan_id": "",
        "meal_id": "",
        "total_kcal": 0.0,
        "totals": {
            "kcal": 0.0,
            "total_kcal": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            "micros": micros,
        },
        "micros": micros,
        "micronutrients": micros,
        "items": [],
        "warnings": [
            {
                "type": "analysis_timeout",
                "message": "Analysis timed out; returning safe fallback result.",
            }
        ],
        "error_code": "analysis_timeout",
        "error_message": str(error_text or "")[:220],
        "coach_summary_source": "fallback",
        "fli_source": "rules",
        "source_display": "Coach",
        "updatedAt": now_iso,
        "coach_generated_ts": now_iso,
    }


def _process_analysis_job(job: Dict[str, Any]) -> None:
    info = dict(job or {})
    job_id = str(info.get("job_id") or info.get("id") or "").strip()
    if not job_id:
        return
    user_id = str(info.get("user_id") or "").strip()
    input_path = str(info.get("input_path") or "").strip()
    tz = info.get("tz")
    tz_offset_min = info.get("tz_offset_min")
    request_id = str(info.get("request_id") or _new_request_id())
    started = time.time()
    logger.info("analysis_job start job_id=%s user=%s request_id=%s", job_id, user_id, request_id)
    _patch_analysis_job(job_id, {"status": "running", "error": ""})
    try:
        if not input_path or not os.path.exists(input_path):
            raise HTTPException(status_code=404, detail={"error": "input_not_found", "message": "Job input image not found."})
        with open(input_path, "rb") as f:
            contents = f.read()
        result = _run_analyze_pipeline(
            user_id=user_id,
            image_bytes=contents,
            tz=tz,
            tz_offset_min=tz_offset_min,
            debug=False,
            request_id=request_id,
            job_id=job_id,
        )
        _patch_analysis_job(
            job_id,
            {
                "status": "done",
                "result_json": result,
                "error": "",
            },
        )
        logger.info(
            "analysis_job done job_id=%s user=%s request_id=%s latency_ms=%s",
            job_id,
            user_id,
            request_id,
            int(max(0, round((time.time() - started) * 1000))),
        )
    except Exception as e:
        err_text = _job_error_text(e)
        logger.error("analysis_job failed job_id=%s user=%s request_id=%s err=%s", job_id, user_id, request_id, err_text)
        fallback_result = _minimal_analysis_fallback_result(job_id, request_id, err_text)
        if isinstance(e, HTTPException) and isinstance(e.detail, dict):
            if str(e.detail.get("error") or "").strip().lower() == "vision_timeout":
                fallback_result = {
                    "error": "vision_timeout",
                    "message": "Image analysis exceeded time limit",
                }
        _patch_analysis_job(
            job_id,
            {
                "status": "done",
                "result_json": fallback_result,
                "error": err_text,
            },
        )
    finally:
        try:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass


def _analysis_job_worker_loop() -> None:
    while True:
        job = _ANALYSIS_JOB_QUEUE.get()
        try:
            _process_analysis_job(job if isinstance(job, dict) else {})
        except Exception as e:
            logger.error("analysis_job worker loop error: %s", str(e)[:240])
        finally:
            _ANALYSIS_JOB_QUEUE.task_done()


def _ensure_analysis_worker_started() -> None:
    global _ANALYSIS_JOB_WORKER_STARTED
    if _ANALYSIS_JOB_WORKER_STARTED:
        return
    with _ANALYSIS_JOB_WORKER_LOCK:
        if _ANALYSIS_JOB_WORKER_STARTED:
            return
        _ensure_dir(ANALYZE_JOB_DIR)
        t = threading.Thread(target=_analysis_job_worker_loop, daemon=True, name="analysis-job-worker")
        t.start()
        _ANALYSIS_JOB_WORKER_STARTED = True
        logger.info("analysis job worker started dir=%s", ANALYZE_JOB_DIR)


def _enqueue_analysis_job(job: Dict[str, Any]) -> None:
    _ensure_analysis_worker_started()
    _ANALYSIS_JOB_QUEUE.put(dict(job or {}), timeout=2.0)


def _store_meal_analysis(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = dict(row or {})
    analysis_id = str(raw.get("analysis_id") or raw.get("scan_id") or "").strip()
    if analysis_id:
        raw["analysis_id"] = analysis_id
    scan_id = analysis_id
    try:
        if analysis_id:
            scan_id = str(uuid.UUID(analysis_id))
    except Exception:
        scan_id = ""
    core = {
        "scan_id": scan_id or str(uuid.uuid4()),
        "analysis_id": analysis_id or str(raw.get("scan_id") or ""),
        "user_id": str(raw.get("user_id") or "").strip(),
        "day": str(raw.get("day") or "").strip() or None,
        "created_at": raw.get("created_at") or _now_utc_naive().isoformat(),
        "updated_at": raw.get("updated_at") or _now_utc_naive().isoformat(),
    }
    payload_json = dict(raw)
    for k in ("scan_id", "analysis_id", "user_id", "day", "created_at", "updated_at"):
        payload_json.pop(k, None)
    core["payload"] = payload_json
    payload = _expand_row_from_json_fallback(TBL_MEAL_ANALYSES, core)
    _analysis_cache_set(payload)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return payload
    try:
        stored = _sb_insert_with_column_fallback(
            TBL_MEAL_ANALYSES,
            core,
            locked_cols={"scan_id", "analysis_id", "user_id"},
        )
        expanded = _expand_row_from_json_fallback(TBL_MEAL_ANALYSES, stored)
        _analysis_cache_set(expanded)
        return expanded
    except Exception as e:
        if not _mark_table_unavailable(TBL_MEAL_ANALYSES, e):
            logger.info(f"meal analysis write skipped: {e}")
        return payload


def _store_analysis_memory(row: Dict[str, Any]) -> None:
    payload = dict(row or {})
    if not payload:
        return
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    try:
        existing = sb_get_one(
            TBL_ANALYSIS_MEMORY,
            params={
                "select": "*",
                "analysis_id": f"eq.{str(payload.get('analysis_id') or '')}",
                "user_id": f"eq.{str(payload.get('user_id') or '')}",
                "limit": "1",
            },
        )
        if existing:
            patch = {k: v for k, v in payload.items() if k not in {"analysis_id", "user_id", "created_at"}}
            _sb_patch_with_column_fallback(
                TBL_ANALYSIS_MEMORY,
                {
                    "analysis_id": f"eq.{str(payload.get('analysis_id') or '')}",
                    "user_id": f"eq.{str(payload.get('user_id') or '')}",
                },
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_ANALYSIS_MEMORY,
                payload,
                locked_cols={"analysis_id", "user_id"},
            )
    except Exception as e:
        logger.info(f"analysis memory write skipped: {e}")


def _get_meal_analysis(user_id: str, analysis_id: str) -> Optional[Dict[str, Any]]:
    aid = str(analysis_id or "").strip()
    if not aid:
        return None

    mem = _analysis_cache_get(aid)
    if isinstance(mem, dict) and str(mem.get("user_id") or "").strip() == str(user_id or "").strip():
        return dict(mem)

    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return mem
    try:
        row = sb_get_one(
            TBL_MEAL_ANALYSES,
            params={
                "select": "*",
                "analysis_id": f"eq.{aid}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
        if row:
            _analysis_cache_set(row)
            return row
    except Exception as e:
        if not _mark_table_unavailable(TBL_MEAL_ANALYSES, e):
            logger.info(f"meal analysis read skipped: {e}")
    return mem


def _patch_meal_analysis(analysis_id: str, user_id: str, patch: Dict[str, Any]) -> None:
    aid = str(analysis_id or "").strip()
    if not aid:
        return
    merged = dict(_analysis_cache_get(aid) or {})
    merged.update(dict(patch or {}))
    _analysis_cache_set(merged)

    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    try:
        patch_src = dict(patch or {})
        core_patch = {
            "updated_at": patch_src.get("updated_at") or _now_utc_naive().isoformat(),
        }
        payload_patch = dict(patch_src)
        payload_patch.pop("updated_at", None)
        core_patch["payload"] = payload_patch
        _sb_patch_with_column_fallback(
            TBL_MEAL_ANALYSES,
            {"analysis_id": f"eq.{aid}", "user_id": f"eq.{user_id}"},
            core_patch,
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_MEAL_ANALYSES, e):
            logger.info(f"meal analysis patch skipped: {e}")


def _store_meal_edit(row: Dict[str, Any]) -> None:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    try:
        raw = dict(row or {})
        analysis_id = str(raw.get("analysis_id") or raw.get("scan_id") or "").strip()
        scan_id = ""
        try:
            if analysis_id:
                scan_id = str(uuid.UUID(analysis_id))
        except Exception:
            scan_id = ""
        edit_payload = raw.get("edit")
        if not isinstance(edit_payload, dict):
            edit_payload = raw.get("edit_patch_json")
        if not isinstance(edit_payload, dict):
            edit_payload = {k: v for k, v in raw.items() if k not in {"id", "edit_id", "analysis_id", "scan_id", "user_id", "created_at"}}
        payload = {
            "id": str(raw.get("id") or raw.get("edit_id") or uuid.uuid4()),
            "scan_id": scan_id or None,
            "analysis_id": analysis_id or None,
            "user_id": str(raw.get("user_id") or "").strip(),
            "edit": edit_payload,
            "created_at": raw.get("created_at") or _now_utc_naive().isoformat(),
        }
        _sb_insert_with_column_fallback(
            TBL_MEAL_EDITS,
            payload,
            locked_cols={"id", "scan_id", "analysis_id", "user_id"},
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_MEAL_EDITS, e):
            logger.info(f"meal edit write skipped: {e}")



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
        except Exception as e:
            raw = _http_exc_raw(e)
            bad_col = _extract_unknown_column(raw)
            if bad_col and bad_col in payload and bad_col not in {"user_id"}:
                moved = _merge_unknown_column_into_json_payload(table, payload, bad_col)
                if not moved:
                    payload.pop(bad_col, None)
                _log_unknown_column_once(table, "upsert", bad_col, moved)
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


def _timezone_label(tz: Optional[str] = None, tz_offset_min: Optional[Any] = None) -> str:
    tz_name = str(tz or "").strip()
    if tz_name:
        return tz_name
    off = _parse_tz_offset_min(tz_offset_min)
    if off is None:
        return "UTC"
    sign = "+" if off >= 0 else "-"
    mins = abs(int(off))
    hh = mins // 60
    mm = mins % 60
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def _select_week_timezone(
    existing_payload: Optional[Dict[str, Any]],
    tz: Optional[str] = None,
    tz_offset_min: Optional[Any] = None,
) -> str:
    if isinstance(existing_payload, dict):
        existing_tz = str(existing_payload.get("tz_used") or "").strip()
        if existing_tz:
            return existing_tz
    return _timezone_label(tz=tz, tz_offset_min=tz_offset_min)


def _is_payload_stale(payload: Optional[Dict[str, Any]], anchor_day_iso: str, max_age_hours: int = 30) -> bool:
    if not isinstance(payload, dict):
        return True
    source_days = payload.get("source_days")
    if isinstance(source_days, list):
        day_set = {str(d)[:10] for d in source_days if str(d).strip()}
        if anchor_day_iso and anchor_day_iso[:10] not in day_set:
            return True
    ts_raw = str(payload.get("generated_at") or payload.get("updated_at") or "").strip()
    if not ts_raw:
        return True
    try:
        ts = dt.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        age_sec = (dt.datetime.now(dt.timezone.utc) - ts.astimezone(dt.timezone.utc)).total_seconds()
        return age_sec > (max_age_hours * 3600)
    except Exception:
        return True


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
DAILY_VALUE_EPS = 1e-9
COACH_CACHE_TTL_HOURS = 48


def _utc_from_iso(raw: Any) -> Optional[dt.datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _daily_totals_version_from_row(row: Optional[Dict[str, Any]]) -> int:
    src = row if isinstance(row, dict) else {}
    raw_version = src.get("daily_totals_version")
    if raw_version is not None:
        try:
            return max(0, int(float(raw_version)))
        except Exception:
            pass
    updated = _utc_from_iso(src.get("updated_at"))
    if updated:
        return max(0, int(updated.timestamp() * 1_000_000))
    return 0


def _daily_totals_changed_fields(current_vals: Dict[str, float], next_vals: Dict[str, float]) -> List[str]:
    changed: List[str] = []
    for key in DAILY_VALUE_ALIASES.keys():
        cur = float(current_vals.get(key, 0.0) or 0.0)
        nxt = float(next_vals.get(key, 0.0) or 0.0)
        if abs(nxt - cur) > DAILY_VALUE_EPS:
            changed.append(key)
    return changed


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
        "daily_totals_version": _daily_totals_version_from_row(src),
    }
    out.update(vals)
    # App compatibility alias
    out["kcal"] = out.get("total_kcal", 0.0)
    return out


def _daily_payload_for_storage(
    user_id: str,
    day_iso: str,
    values: Dict[str, float],
    mapping: Dict[str, str],
    *,
    daily_totals_version: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"user_id": user_id, "day": day_iso, "updated_at": dt.datetime.utcnow().isoformat()}
    if daily_totals_version is not None:
        payload["daily_totals_version"] = int(max(0, int(daily_totals_version)))
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
    request_id = uuid.uuid4().hex[:12]
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
    old_version = _daily_totals_version_from_row(raw_current)

    next_vals: Dict[str, float] = {}
    for k in DAILY_VALUE_ALIASES.keys():
        next_vals[k] = float(current_vals.get(k, 0.0)) + float(increment_vals.get(k, 0.0))
    changed_fields = _daily_totals_changed_fields(current_vals, next_vals)
    if not changed_fields:
        logger.info(
            "daily_totals_version_no_change user=%s day_key=%s old_version=%s new_version=%s changed_fields=%s request_id=%s",
            user_id,
            day_iso,
            old_version,
            old_version,
            "[]",
            request_id,
        )
        return _normalize_daily_totals_record(
            user_id,
            day_iso,
            raw_current if raw_current else {"user_id": user_id, "day": day_iso, **current_vals},
        )

    next_version = max(old_version + 1, int(time.time() * 1_000_000))

    has_legacy_kcal = bool(raw_current and "kcal" in raw_current and "total_kcal" not in raw_current)
    mapping_order = (
        (DAILY_STORAGE_LEGACY, DAILY_STORAGE_MODERN)
        if has_legacy_kcal
        else (DAILY_STORAGE_MODERN, DAILY_STORAGE_LEGACY)
    )

    last_err: Optional[Exception] = None
    for mapping in mapping_order:
        payload = _daily_payload_for_storage(
            user_id,
            day_iso,
            next_vals,
            mapping,
            daily_totals_version=next_version,
        )
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
            normalized = _normalize_daily_totals_record(user_id, day_iso, stored)
            logger.info(
                "daily_totals_version_update user=%s day_key=%s old_version=%s new_version=%s changed_fields=%s request_id=%s",
                user_id,
                day_iso,
                old_version,
                int(_safe_float(normalized.get("daily_totals_version"), next_version) or next_version),
                json.dumps(changed_fields, separators=(",", ":")),
                request_id,
            )
            return normalized
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
        "sugar_g": _safe_float(totals.get("sugar_g"), 0.0) or 0.0,
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

    day_iso = str(day or totals.get("day") or _today_date(tz=tz, tz_offset_min=tz_offset_min).isoformat())
    meals_count_today = 0
    last_meal_ts = ""
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            events = get_meal_events_for_day(user_id, day_iso)
            photo_events = [
                e for e in (events or [])
                if _event_text(e, "source", "event_source").lower() in {"photo", "scan", "meal", ""}
                or _event_text(e, "event_type").lower() in {"photo_analyze", "analyze", "scan"}
            ]
            meals_count_today = len(photo_events)
            if photo_events:
                last_meal_ts = str((photo_events[-1] or {}).get("created_at") or "")
        except Exception as e:
            logger.info(f"daily summary meal-event read skipped: {e}")

    return {
        "day": totals.get("day"),
        "day_key": day_iso,
        "totals": totals,
        "goals": goals,
        "remaining": remaining,
        "daily_totals_version": str(int(_safe_float(totals.get("daily_totals_version"), 0) or 0)),
        "meals_count_today": meals_count_today,
        "last_meal_ts": last_meal_ts,
    }


# -------------------- PHASE 3.1: BEHAVIOR MEMORY --------------------
def _safe_avg(vals: List[float]) -> float:
    arr = [float(v) for v in vals if v is not None]
    if not arr:
        return 0.0
    return sum(arr) / max(1, len(arr))


def _safe_std(vals: List[float]) -> float:
    arr = [float(v) for v in vals if v is not None]
    n = len(arr)
    if n <= 1:
        return 0.0
    mean = _safe_avg(arr)
    var = sum((v - mean) ** 2 for v in arr) / float(n)
    return math.sqrt(max(0.0, var))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _norm_score_from_range(value: float, lo: float, hi: float) -> float:
    """Maps value in [lo,hi] to 0..100."""
    if hi <= lo:
        return 0.0
    return _clamp(((float(value) - float(lo)) / (float(hi) - float(lo))) * 100.0, 0.0, 100.0)


def _consistency_score_from_hits(hit_vals: List[float]) -> float:
    """
    0..100 where higher means "consistently near target across days".
    Balances closeness-to-target and day-to-day stability.
    """
    vals = [max(0.0, float(v)) for v in (hit_vals or [])]
    if not vals:
        return 0.0
    closeness = _safe_avg([max(0.0, 100.0 - abs(v - 100.0)) for v in vals])
    stability = max(0.0, 100.0 - (_safe_std(vals) * 1.8))
    return round((closeness * 0.65) + (stability * 0.35), 1)


def _volatility_index_from_series(vals: List[float], scale: float) -> float:
    """0..100 where higher means more unstable."""
    arr = [float(v) for v in (vals or [])]
    if not arr:
        return 0.0
    vol = _safe_std(arr) * float(scale or 1.0)
    return round(_clamp(vol, 0.0, 100.0), 1)


def _band_from_score(score_0_100: float, low_cut: float = 35.0, high_cut: float = 65.0) -> str:
    s = float(score_0_100 or 0.0)
    if s >= high_cut:
        return "high"
    if s <= low_cut:
        return "low"
    return "medium"


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


def build_weekly_insight_payload(
    user_id: str,
    week_start_iso: str,
    metric_rows: List[Dict[str, Any]],
    tz_used: Optional[str] = None,
) -> Dict[str, Any]:
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
        "tz_used": str(tz_used or "UTC"),
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


def build_weekly_prediction_payload(
    user_id: str,
    week_start_iso: str,
    metric_rows: List[Dict[str, Any]],
    tz_used: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministic Phase 3.2 engine.
    Computes consistency, volatility, and 7-day projection metrics.
    """
    week_end_iso = _week_end_from_start(week_start_iso)
    rows = sorted(metric_rows or [], key=lambda r: str((r or {}).get("day") or ""))
    days = len(rows)

    protein_hit_vals = [_extract_metric_val(r, "protein_hit_pct") for r in rows]
    fiber_hit_vals = [_extract_metric_val(r, "fiber_hit_pct") for r in rows]
    late_vals = [_extract_metric_val(r, "late_calories_pct") for r in rows]
    gl_vals = [_extract_metric_val(r, "avg_glycemic_load") for r in rows]
    upf_vals = [_extract_metric_val(r, "ultra_processed_avg") for r in rows]
    kcal_delta_vals = [_extract_metric_val(r, "kcal_delta_pct") for r in rows]
    day_scores = [_day_score_from_metric_row(r) for r in rows]

    leucine_hit_rate_vals: List[float] = []
    biggest_meals: List[str] = []
    kcal_balances: List[float] = []
    scans_by_day: List[float] = []
    for r in rows:
        tgt = _extract_metric_val(r, "leucine_triggers_target")
        hit = _extract_metric_val(r, "leucine_triggers_hit")
        if tgt > 0:
            leucine_hit_rate_vals.append(_clamp(hit / tgt, 0.0, 1.0))
        else:
            leucine_hit_rate_vals.append(1.0)
        biggest_meals.append(_extract_metric_text(r, "biggest_meal", ""))
        kcal_goal = _extract_metric_val(r, "kcal_goal")
        kcal_consumed = _extract_metric_val(r, "kcal_consumed")
        kcal_balances.append(kcal_consumed - kcal_goal)
        scans_by_day.append(max(0.0, _extract_metric_val(r, "meals_count")))

    protein_avg = round(_safe_avg(protein_hit_vals), 1)
    fiber_avg = round(_safe_avg(fiber_hit_vals), 1)
    glycemic_avg = round(_safe_avg(gl_vals), 1)
    upf_avg = round(_safe_avg(upf_vals), 1)
    timing_balance_avg = round(max(0.0, 100.0 - _safe_avg(late_vals)), 1)

    protein_consistency = _consistency_score_from_hits(protein_hit_vals)
    fiber_consistency = _consistency_score_from_hits(fiber_hit_vals)

    glycemic_volatility = _volatility_index_from_series(gl_vals, scale=3.0)
    upf_volatility = _volatility_index_from_series(upf_vals, scale=12.0)
    kcal_delta_volatility = _volatility_index_from_series(kcal_delta_vals, scale=1.6)
    diet_volatility_index = round(_clamp((glycemic_volatility * 0.45) + (upf_volatility * 0.35) + (kcal_delta_volatility * 0.20), 0.0, 100.0), 1)

    meal_counts: Dict[str, int] = {}
    for b in biggest_meals:
        key = (b or "").strip().lower()
        if not key:
            continue
        meal_counts[key] = meal_counts.get(key, 0) + 1
    dominant_ratio = ((max(meal_counts.values()) / days) * 100.0) if (days > 0 and meal_counts) else 0.0
    late_stability = max(0.0, 100.0 - (_safe_std(late_vals) * 2.0))
    timing_stability_index = round(_clamp((late_stability * 0.7) + (dominant_ratio * 0.3), 0.0, 100.0), 1)
    timing_volatility = round(max(0.0, 100.0 - timing_stability_index), 1)

    readiness_score = round(_safe_avg(day_scores), 1)
    if days >= 2:
        split = max(1, days // 2)
        readiness_trend = round(_safe_avg(day_scores[-split:]) - _safe_avg(day_scores[:split]), 1)
    else:
        readiness_trend = 0.0

    fat_loss_velocity_score = round(
        _clamp(
            (readiness_score * 0.45)
            + (protein_consistency * 0.20)
            + (fiber_consistency * 0.15)
            + ((100.0 - diet_volatility_index) * 0.12)
            + ((100.0 - timing_volatility) * 0.08),
            0.0,
            100.0,
        ),
        1,
    )

    avg_daily_kcal_balance = _safe_avg(kcal_balances)
    projected_weight_change_kg_7d = round(_clamp((avg_daily_kcal_balance * 7.0) / 7700.0, -1.2, 1.2), 3)  # internal only
    deficit_component = _norm_score_from_range(-avg_daily_kcal_balance, 0.0, 500.0)
    days_confidence_pct = round(_clamp((days / 7.0) * 100.0, 0.0, 100.0), 1)
    probability_pct = round(
        _clamp(
            (fat_loss_velocity_score * 0.55)
            + (deficit_component * 0.30)
            + (days_confidence_pct * 0.15)
            - 8.0,
            3.0,
            97.0,
        ),
        1,
    )
    fat_loss_probability_7d = round(_clamp(probability_pct / 100.0, 0.0, 1.0), 3)

    hunger_volatility_score = round(
        _clamp(
            ((100.0 - fiber_consistency) * 0.35)
            + (_norm_score_from_range(glycemic_avg, 12.0, 38.0) * 0.25)
            + (_norm_score_from_range(_safe_avg(late_vals), 20.0, 75.0) * 0.25)
            + (diet_volatility_index * 0.15),
            0.0,
            100.0,
        ),
        1,
    )
    leucine_hit_rate_pct = round(_safe_avg([v * 100.0 for v in leucine_hit_rate_vals]), 1)
    muscle_retention_risk_score = round(
        _clamp(
            ((100.0 - min(100.0, protein_avg)) * 0.55)
            + ((100.0 - protein_consistency) * 0.25)
            + ((100.0 - leucine_hit_rate_pct) * 0.20),
            0.0,
            100.0,
        ),
        1,
    )

    projection_7d_score = round(
        _clamp(
            (probability_pct * 0.50)
            + ((100.0 - hunger_volatility_score) * 0.20)
            + ((100.0 - muscle_retention_risk_score) * 0.30),
            0.0,
            100.0,
        ),
        1,
    )

    days_with_data_7d = int(days)
    scans_7d = int(round(sum(scans_by_day)))
    scan_stability = _safe_std(scans_by_day)
    if days_with_data_7d < 4:
        projection_confidence_band = "low"
        missing_data_reason = "Not enough tracked days this week."
    elif days_with_data_7d < 6:
        projection_confidence_band = "medium"
        missing_data_reason = "Need 1-2 more tracked days for stronger confidence."
    else:
        stable_scan_signal = scans_7d >= days_with_data_7d and scan_stability <= 1.5
        if stable_scan_signal:
            projection_confidence_band = "high"
            missing_data_reason = ""
        else:
            projection_confidence_band = "medium"
            missing_data_reason = "Scan frequency is uneven across the week."

    if avg_daily_kcal_balance <= -120:
        energy_trend = "deficit_trend"
    elif avg_daily_kcal_balance >= 120:
        energy_trend = "surplus_trend"
    else:
        energy_trend = "near_balance"

    if days == 0:
        fat_loss_velocity_score = 0.0
        probability_pct = 0.0
        fat_loss_probability_7d = 0.0
        projection_7d_score = 0.0
        projected_weight_change_kg_7d = 0.0
        projection_confidence_band = "low"
        missing_data_reason = "No tracked days in this week."
        scans_7d = 0
        days_with_data_7d = 0
        energy_trend = "unknown"

    if projected_weight_change_kg_7d <= -0.05:
        weight_direction = "loss"
    elif projected_weight_change_kg_7d >= 0.05:
        weight_direction = "gain"
    else:
        weight_direction = "maintenance"

    payload = {
        "week_start": week_start_iso,
        "week_end": week_end_iso,
        "tz_used": str(tz_used or "UTC"),
        "days_tracked": int(days),
        "days_with_data_7d": int(days_with_data_7d),
        "scans_7d": int(scans_7d),
        "projection_confidence_band": projection_confidence_band,
        "missing_data_reason": str(missing_data_reason or ""),
        "protein_avg": protein_avg,
        "protein_consistency": protein_consistency,
        "fiber_avg": fiber_avg,
        "fiber_consistency": fiber_consistency,
        "timing_balance_avg": timing_balance_avg,
        "timing_stability_index": timing_stability_index,
        "timing_volatility": timing_volatility,
        "diet_volatility_index": diet_volatility_index,
        "upf_avg": upf_avg,
        "upf_volatility": upf_volatility,
        "glycemic_avg": glycemic_avg,
        "glycemic_volatility": glycemic_volatility,
        "readiness_score": readiness_score,
        "readiness_trend": readiness_trend,
        "fat_loss_velocity_score": fat_loss_velocity_score,
        "fat_loss_probability_7d": fat_loss_probability_7d,
        "fat_loss_probability_pct": probability_pct,
        "projection_7d_score": projection_7d_score,
        "energy_balance_trend_7d": {
            "trend": energy_trend,
            "daily_kcal_balance": round(avg_daily_kcal_balance, 1),
            "score": round(_norm_score_from_range(-avg_daily_kcal_balance, -250.0, 350.0), 1),
        },
        "weight_change_projection_7d": {
            "kg_change": projected_weight_change_kg_7d,
            "direction": weight_direction,
            "daily_kcal_balance": round(avg_daily_kcal_balance, 1),
            "confidence_pct": days_confidence_pct,
        },
        "hunger_volatility_projection": {
            "score": hunger_volatility_score,
            "level": _band_from_score(hunger_volatility_score),
            "summary": "Higher score means more unstable appetite/hunger pattern risk over the next 7 days.",
        },
        "muscle_retention_risk": {
            "score": muscle_retention_risk_score,
            "level": _band_from_score(muscle_retention_risk_score),
            "summary": "Higher score means higher risk of under-supporting recovery if the weekly pattern repeats.",
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
        "tz_used": str(payload.get("tz_used") or ""),
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


def upsert_user_weekly_metrics(user_id: str, week_start_iso: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _require_supabase()
    row = {
        "user_id": user_id,
        "week_start": week_start_iso,
        "week_end": str(payload.get("week_end") or _week_end_from_start(week_start_iso)),
        "tz_used": str(payload.get("tz_used") or ""),
        "days_tracked": int(_safe_float(payload.get("days_tracked"), 0) or 0),
        "days_with_data_7d": int(_safe_float(payload.get("days_with_data_7d"), 0) or 0),
        "scans_7d": int(_safe_float(payload.get("scans_7d"), 0) or 0),
        "projection_confidence_band": str(payload.get("projection_confidence_band") or ""),
        "protein_avg": float(_safe_float(payload.get("protein_avg"), 0.0) or 0.0),
        "protein_consistency": float(_safe_float(payload.get("protein_consistency"), 0.0) or 0.0),
        "fiber_avg": float(_safe_float(payload.get("fiber_avg"), 0.0) or 0.0),
        "fiber_consistency": float(_safe_float(payload.get("fiber_consistency"), 0.0) or 0.0),
        "timing_balance_avg": float(_safe_float(payload.get("timing_balance_avg"), 0.0) or 0.0),
        "timing_volatility": float(_safe_float(payload.get("timing_volatility"), 0.0) or 0.0),
        "upf_avg": float(_safe_float(payload.get("upf_avg"), 0.0) or 0.0),
        "upf_volatility": float(_safe_float(payload.get("upf_volatility"), 0.0) or 0.0),
        "glycemic_avg": float(_safe_float(payload.get("glycemic_avg"), 0.0) or 0.0),
        "glycemic_volatility": float(_safe_float(payload.get("glycemic_volatility"), 0.0) or 0.0),
        "readiness_score": float(_safe_float(payload.get("readiness_score"), 0.0) or 0.0),
        "readiness_trend": float(_safe_float(payload.get("readiness_trend"), 0.0) or 0.0),
        "fat_loss_velocity_score": float(_safe_float(payload.get("fat_loss_velocity_score"), 0.0) or 0.0),
        "fat_loss_probability_7d": float(_safe_float(payload.get("fat_loss_probability_7d"), 0.0) or 0.0),
        "projection_7d_score": float(_safe_float(payload.get("projection_7d_score"), 0.0) or 0.0),
        "payload_hash": str(payload.get("payload_hash") or ""),
        "metrics_json": payload,
        "engine_version": str(payload.get("engine_version") or BEHAVIOR_ENGINE_VERSION),
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    existing = sb_get_one(
        TBL_USER_WEEKLY_METRICS,
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
            TBL_USER_WEEKLY_METRICS,
            {"user_id": f"eq.{user_id}", "week_start": f"eq.{week_start_iso}"},
            patch,
        )
        refreshed = sb_get_one(
            TBL_USER_WEEKLY_METRICS,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "week_start": f"eq.{week_start_iso}",
                "limit": "1",
            },
        )
        return refreshed or row
    return _sb_insert_with_column_fallback(TBL_USER_WEEKLY_METRICS, row, locked_cols={"user_id", "week_start"})


def get_user_weekly_metrics_payload(user_id: str, week_start_iso: str) -> Optional[Dict[str, Any]]:
    _require_supabase()
    row = sb_get_one(
        TBL_USER_WEEKLY_METRICS,
        params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "week_start": f"eq.{week_start_iso}",
            "limit": "1",
        },
    )
    if not row:
        return None
    for k in ("metrics_json", "weekly_metrics_json", "payload_json", "payload"):
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
    existing_weekly = None
    try:
        existing_weekly = get_weekly_insight_payload(user_id, week_start_iso)
    except Exception:
        existing_weekly = None
    existing_weekly_metrics = None
    try:
        existing_weekly_metrics = get_user_weekly_metrics_payload(user_id, week_start_iso)
    except Exception:
        existing_weekly_metrics = None
    week_tz = _select_week_timezone(
        existing_weekly if isinstance(existing_weekly, dict) else existing_weekly_metrics,
        tz=tz,
        tz_offset_min=tz_offset_min,
    )

    weekly_payload = build_weekly_insight_payload(user_id, week_start_iso, week_rows, tz_used=week_tz)
    upsert_weekly_insight(user_id, week_start_iso, weekly_payload)
    weekly_metrics_payload = build_weekly_prediction_payload(user_id, week_start_iso, week_rows, tz_used=week_tz)
    try:
        upsert_user_weekly_metrics(user_id, week_start_iso, weekly_metrics_payload)
    except Exception as e:
        logger.info(f"user_weekly_metrics upsert skipped: {e}")

    return {
        "day": target_day,
        "week_start": week_start_iso,
        "daily_metrics": daily_payload,
        "weekly_insights": weekly_payload,
        "weekly_metrics": weekly_metrics_payload,
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

def _uid_input_text(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if val is None:
        return ""
    mod = str(getattr(type(val), "__module__", "") or "")
    if mod.startswith("fastapi.params"):
        return ""
    return str(val).strip()


def require_user_id(x_user_id: Optional[str], user_id: Optional[str]) -> str:
    h = _uid_input_text(x_user_id)
    q = _uid_input_text(user_id)
    if h and q and h != q:
        raise HTTPException(status_code=401, detail="Conflicting user ids in header and query.")
    uid = h or q
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id. Pass X-User-Id header or ?user_id=...")
    return uid


def _to_bool_flag(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _read_ai_consent_row(user_id: str) -> Optional[Dict[str, Any]]:
    uid = str(user_id or "").strip()
    if not uid:
        return None
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_USER_AI_CONSENT):
        return None
    try:
        return sb_get_one(
            TBL_USER_AI_CONSENT,
            params={"select": "*", "user_id": f"eq.{uid}", "limit": "1"},
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_USER_AI_CONSENT, e):
            logger.info(f"ai consent read skipped: {e}")
        return None


def has_ai_consent(user_id: str) -> bool:
    uid = str(user_id or "").strip()
    if not uid:
        return False
    now_ts = time.time()
    cached = _AI_CONSENT_CACHE.get(uid)
    if isinstance(cached, dict):
        cached_at = float(cached.get("cached_at") or 0.0)
        if (now_ts - cached_at) <= 60.0:
            return bool(cached.get("consent_given"))
    row = _read_ai_consent_row(uid)
    consent = bool(row and _to_bool_flag(row.get("consent_given"), False))
    _AI_CONSENT_CACHE[uid] = {"consent_given": consent, "cached_at": now_ts}
    return consent


def require_ai_consent(user_id: str) -> None:
    if not has_ai_consent(user_id):
        raise HTTPException(
            status_code=403,
            detail="AI processing consent required before analysis.",
        )


def _set_ai_consent(user_id: str, consent_given: bool) -> Dict[str, Any]:
    uid = str(user_id or "").strip()
    now_iso = _now_utc_naive().isoformat()
    row = {
        "user_id": uid,
        "consent_given": bool(consent_given),
        "consent_timestamp": now_iso if bool(consent_given) else None,
        "updated_at": now_iso,
    }
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_USER_AI_CONSENT):
        _AI_CONSENT_CACHE[uid] = {"consent_given": bool(consent_given), "cached_at": time.time()}
        return row
    try:
        stored = sb_upsert(TBL_USER_AI_CONSENT, row, on_conflict="user_id")
        out = dict(stored or row)
    except Exception as e:
        if _mark_table_unavailable(TBL_USER_AI_CONSENT, e):
            out = dict(row)
        else:
            raise
    _AI_CONSENT_CACHE[uid] = {"consent_given": bool(out.get("consent_given")), "cached_at": time.time()}
    return out


@app.get("/ai/consent")
def get_ai_consent(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    row = _read_ai_consent_row(uid)
    consent_given = bool(row and _to_bool_flag(row.get("consent_given"), False))
    _AI_CONSENT_CACHE[uid] = {"consent_given": consent_given, "cached_at": time.time()}
    return {
        "user_id": uid,
        "consent_given": consent_given,
        "consent_timestamp": (row or {}).get("consent_timestamp") if isinstance(row, dict) else None,
        "updated_at": (row or {}).get("updated_at") if isinstance(row, dict) else None,
        "record_exists": bool(row),
    }


@app.post("/ai/consent")
def upsert_ai_consent(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    body = payload if isinstance(payload, dict) else {}
    uid = require_user_id(x_user_id, user_id or body.get("user_id"))
    consent_given = _to_bool_flag(body.get("consent_given", body.get("consent")), False)
    stored = _set_ai_consent(uid, consent_given)
    return {
        "ok": True,
        "user_id": uid,
        "consent_given": bool(stored.get("consent_given")),
        "consent_timestamp": stored.get("consent_timestamp"),
        "updated_at": stored.get("updated_at"),
    }


def _delete_supabase_auth_user(user_id: str) -> bool:
    uid = str(user_id or "").strip()
    if not uid:
        return False
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return False
    url = f"{SUPABASE_URL}/auth/v1/admin/users/{uid}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.delete(url, headers=headers, timeout=20)
    if r.status_code in (200, 204, 404):
        return True
    raise HTTPException(
        status_code=502,
        detail={"error": "supabase_auth_delete_failed", "raw": str(r.text or "")[:320]},
    )


@app.delete("/account/delete")
def delete_account(
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    tables = [
        TBL_ANALYSIS_MEMORY,
        TBL_MEAL_ANALYSES,
        TBL_MEAL_EDITS,
        TBL_COACH_MEMORY,
        TBL_COACH_FEEDBACK,
        TBL_COACH_VOICE_CACHE,
        TBL_COACH_EVENTS,
        TBL_DAILY_METRICS,
        TBL_DAILY_SUMMARY,
        TBL_DAILY_TOTALS,
        TBL_MEAL_EVENTS,
        TBL_USER_WEEKLY_METRICS,
        TBL_WEEKLY_INSIGHTS,
        TBL_WEEKLY_REPORTS,
        TBL_PROGRAM_STATUS,
        TBL_USER_CALIBRATION,
        TBL_CONFIDENCE_AUDIT,
        TBL_CONFIDENCE_CALIBRATION_SETTINGS,
        TBL_USER_FOOD_PRIORS,
        TBL_USER_GOALS,
        TBL_USER_USAGE,
        TBL_ANALYSIS_JOBS,
        TBL_USER_AI_CONSENT,
    ]
    deleted_tables: List[str] = []
    skipped_tables: List[str] = []
    failed_tables: List[Dict[str, str]] = []

    for table in tables:
        tkey = _table_key(table)
        if not tkey:
            continue
        if _is_table_disabled(tkey):
            skipped_tables.append(tkey)
            continue
        if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
            skipped_tables.append(tkey)
            continue
        try:
            sb_delete(tkey, {"user_id": f"eq.{uid}"})
            deleted_tables.append(tkey)
        except Exception as e:
            if _mark_table_unavailable(tkey, e):
                skipped_tables.append(tkey)
                continue
            failed_tables.append({"table": tkey, "error": str(_http_exc_raw(e))[:220]})

    auth_deleted = False
    auth_error = ""
    try:
        auth_deleted = _delete_supabase_auth_user(uid)
    except Exception as e:
        auth_error = str(_http_exc_raw(e))[:220]
        logger.warning(f"auth delete failed for user={uid}: {auth_error}")

    _AI_CONSENT_CACHE.pop(uid, None)
    _COACH_EVENT_RING.pop(uid, None)
    for key in list(_COACH_MEM_CACHE.keys()):
        if str(key).startswith(f"{uid}:"):
            _COACH_MEM_CACHE.pop(key, None)

    if failed_tables:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "account_delete_partial_failure",
                "failed_tables": failed_tables,
                "auth_deleted": auth_deleted,
                "auth_error": auth_error,
            },
        )

    resp = {
        "status": "deleted",
        "user_id": uid,
        "deleted_tables": deleted_tables,
        "skipped_tables": skipped_tables,
        "auth_deleted": auth_deleted,
    }
    if auth_error:
        resp["auth_error"] = auth_error
    return _attach_debug_schema(resp, bool(debug))


def _supplement_text(value: Any) -> str:
    return str(value or "").strip()


def _supplement_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _supplement_brand_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _extract_supplement_panel_number(panel: Dict[str, Any], keys: List[str]) -> float:
    if not isinstance(panel, dict):
        return 0.0
    for key in keys:
        if key in panel:
            return float(_safe_float(panel.get(key), 0.0) or 0.0)
    for key, value in panel.items():
        k = str(key or "").strip().lower()
        if any(target in k for target in keys):
            return float(_safe_float(value, 0.0) or 0.0)
    return 0.0


def _supplement_fallback_structured(
    barcode_hint: str = "",
    batch_hint: str = "",
) -> Dict[str, Any]:
    return {
        "brand": "",
        "variant": "",
        "barcode": _supplement_digits(barcode_hint),
        "batch_number": _supplement_text(batch_hint),
        "mfg_date": "",
        "expiry_date": "",
        "ingredients": [],
        "nutrition_panel": {},
    }


def extract_supplement_data(
    front_image_bytes: bytes,
    back_image_bytes: bytes,
    barcode_hint: str = "",
    batch_hint: str = "",
    request_id: str = "",
) -> Dict[str, Any]:
    fallback = _supplement_fallback_structured(barcode_hint=barcode_hint, batch_hint=batch_hint)
    if not GEMINI_API_KEY:
        return fallback
    try:
        _require_gemini_key()
        front_img = Image.open(io.BytesIO(front_image_bytes)).convert("RGB")
        back_img = Image.open(io.BytesIO(back_image_bytes)).convert("RGB")
        prompt = (
            "You are a supplement label extraction assistant for whey protein verification.\n"
            "Return ONLY valid JSON (no markdown, no extra keys) with this exact shape:\n"
            "{\n"
            '  "brand": "",\n'
            '  "variant": "",\n'
            '  "barcode": "",\n'
            '  "batch_number": "",\n'
            '  "mfg_date": "",\n'
            '  "expiry_date": "",\n'
            '  "ingredients": [],\n'
            '  "nutrition_panel": {}\n'
            "}\n"
            "Rules:\n"
            "- Read both front and back label.\n"
            "- Keep dates as seen on label.\n"
            "- Keep nutrition_panel numeric fields when available.\n"
            "- If a field is not visible, return empty string/list/object.\n"
            f"- Barcode hint from app: {_supplement_digits(barcode_hint)}\n"
            f"- Batch hint from app: {_supplement_text(batch_hint)}\n"
        )
        text = _generate_scan_content(
            [prompt, front_img, back_img],
            purpose="vision_scan",
            request_id=request_id,
        )
        parsed = coach_logic.extract_json_object(text)
        if not isinstance(parsed, dict):
            return fallback
        out = {
            "brand": _supplement_text(parsed.get("brand")),
            "variant": _supplement_text(parsed.get("variant")),
            "barcode": _supplement_digits(parsed.get("barcode") or barcode_hint),
            "batch_number": _supplement_text(parsed.get("batch_number") or batch_hint),
            "mfg_date": _supplement_text(parsed.get("mfg_date")),
            "expiry_date": _supplement_text(parsed.get("expiry_date")),
            "ingredients": [str(x).strip() for x in (parsed.get("ingredients") or []) if str(x).strip()],
            "nutrition_panel": parsed.get("nutrition_panel") if isinstance(parsed.get("nutrition_panel"), dict) else {},
        }
        for key in SUPPLEMENT_REQUIRED_STRUCTURED_KEYS:
            out.setdefault(key, fallback.get(key))
        if not out.get("barcode"):
            out["barcode"] = _supplement_digits(barcode_hint)
        if not out.get("batch_number"):
            out["batch_number"] = _supplement_text(batch_hint)
        return out
    except Exception as e:
        logger.warning(f"supplement extraction fallback used: {str(e)[:220]}")
        return fallback


def normalize_supplement_data(
    structured: Dict[str, Any],
    *,
    product_type: str = "whey_protein",
    region: str = "",
    brand_override: str = "",
    variant_override: str = "",
    barcode_override: str = "",
    batch_override: str = "",
    mfg_date_override: str = "",
    expiry_date_override: str = "",
) -> Dict[str, Any]:
    src = structured if isinstance(structured, dict) else {}
    ptype = str(product_type or "whey_protein").strip().lower()
    if ptype not in SUPPLEMENT_SUPPORTED_PRODUCT_TYPES:
        ptype = "whey_protein"

    brand = _supplement_text(brand_override) or _supplement_text(src.get("brand"))
    variant = _supplement_text(variant_override) or _supplement_text(src.get("variant"))
    barcode = _supplement_digits(barcode_override) or _supplement_digits(src.get("barcode"))
    batch_number = _supplement_text(batch_override) or _supplement_text(src.get("batch_number"))
    mfg_date = _supplement_text(mfg_date_override) or _supplement_text(src.get("mfg_date"))
    expiry_date = _supplement_text(expiry_date_override) or _supplement_text(src.get("expiry_date"))
    ingredients = [str(x).strip() for x in (src.get("ingredients") or []) if str(x).strip()]
    nutrition_panel = src.get("nutrition_panel") if isinstance(src.get("nutrition_panel"), dict) else {}

    out = {
        "product_type": ptype,
        "brand": brand,
        "variant": variant,
        "barcode": barcode,
        "batch_number": batch_number,
        "mfg_date": mfg_date,
        "expiry_date": expiry_date,
        "region": _supplement_text(region),
        "ingredients": ingredients[:100],
        "nutrition_panel": nutrition_panel,
    }
    out["structured_data"] = {
        "brand": out["brand"],
        "variant": out["variant"],
        "barcode": out["barcode"],
        "batch_number": out["batch_number"],
        "mfg_date": out["mfg_date"],
        "expiry_date": out["expiry_date"],
        "ingredients": out["ingredients"],
        "nutrition_panel": out["nutrition_panel"],
    }
    return out


def _supplement_brand_profile(brand: str) -> Dict[str, Any]:
    brand_txt = _supplement_text(brand)
    if not brand_txt:
        return {}
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_BRAND_PROFILES):
        return {}
    try:
        row = sb_get_one(
            TBL_SUPPLEMENT_BRAND_PROFILES,
            params={"select": "*", "brand": f"eq.{brand_txt}", "limit": "1"},
        )
        return row if isinstance(row, dict) else {}
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_BRAND_PROFILES, e):
            logger.info(f"supplement brand profile read skipped: {e}")
        return {}


def barcode_exists_in_db(barcode: str) -> bool:
    code = _supplement_digits(barcode)
    if not code:
        return False
    try:
        if supabase_get_barcode(code):
            return True
    except Exception:
        pass
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_SCANS):
        return False
    try:
        row = sb_get_one(
            TBL_SUPPLEMENT_SCANS,
            params={"select": "id", "barcode": f"eq.{code}", "limit": "1"},
        )
        return isinstance(row, dict) and bool(row.get("id"))
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_SCANS, e):
            logger.info(f"supplement barcode existence check skipped: {e}")
        return False


def barcode_matches_brand(barcode: str, brand: str) -> bool:
    code = _supplement_digits(barcode)
    brand_txt = _supplement_text(brand)
    if not code or not brand_txt:
        return True
    profile = _supplement_brand_profile(brand_txt)
    prefix = _supplement_digits(profile.get("official_barcode_prefix"))
    if not prefix:
        return True
    return code.startswith(prefix)


def batch_matches_regex(brand: str, batch_number: str) -> bool:
    batch = _supplement_text(batch_number)
    if not batch:
        return False
    profile = _supplement_brand_profile(brand)
    regex = _supplement_text(profile.get("expected_batch_regex"))
    if not regex:
        return True
    try:
        return re.match(regex, batch) is not None
    except re.error:
        return True


def get_suspicious_batch_count(brand: str, batch_number: str) -> int:
    brand_txt = _supplement_text(brand)
    batch = _supplement_text(batch_number)
    if not brand_txt or not batch:
        return 0
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_SCANS):
        return 0
    try:
        scans = sb_get_many(
            TBL_SUPPLEMENT_SCANS,
            params={
                "select": "id",
                "brand": f"eq.{brand_txt}",
                "batch_number": f"eq.{batch}",
                "limit": "200",
            },
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_SCANS, e):
            logger.info(f"supplement suspicious batch scan read skipped: {e}")
        return 0
    scan_ids = [str((x or {}).get("id") or "").strip() for x in scans if str((x or {}).get("id") or "").strip()]
    if not scan_ids:
        return 0
    if _is_table_disabled(TBL_SUPPLEMENT_USER_FLAGS):
        return 0
    try:
        ids_clause = f"in.({','.join(scan_ids)})"
        flags = sb_get_many(
            TBL_SUPPLEMENT_USER_FLAGS,
            params={"select": "id,issue_type", "scan_id": ids_clause, "limit": "500"},
        )
        risk_count = 0
        for row in flags:
            issue = str((row or {}).get("issue_type") or "").strip().lower()
            if issue in {
                "counterfeit_risk",
                "authenticity_concern",
                "suspicious_packaging",
                "community_flagged_batch",
                "fake_suspected",
            }:
                risk_count += 1
        return int(risk_count)
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_USER_FLAGS, e):
            logger.info(f"supplement suspicious batch flag read skipped: {e}")
        return 0


def detect_protein_spiking(structured_data: Dict[str, Any]) -> bool:
    data = structured_data if isinstance(structured_data, dict) else {}
    panel = data.get("nutrition_panel") if isinstance(data.get("nutrition_panel"), dict) else {}
    ingredients = [str(x).strip().lower() for x in (data.get("ingredients") or []) if str(x).strip()]
    protein_100g = _extract_supplement_panel_number(
        panel,
        ["protein_per_100g", "protein_g_per_100g", "protein_per100g", "protein"],
    )
    carbs_100g = _extract_supplement_panel_number(
        panel,
        ["carbs_per_100g", "carbohydrate_per_100g", "carbohydrates_per_100g", "carbs"],
    )
    suspicious_ingredient_hits = sum(
        1
        for token in ("glycine", "taurine", "maltodextrin", "creatine", "amino blend", "nitrogen")
        if any(token in ing for ing in ingredients)
    )
    if protein_100g >= 95.0:
        return True
    if protein_100g > 0 and protein_100g < 55.0 and suspicious_ingredient_hits >= 1:
        return True
    if protein_100g > 0 and carbs_100g > 0 and (protein_100g + carbs_100g) > 120.0:
        return True
    return False


def calculate_authenticity_score(data: Dict[str, Any]) -> Tuple[float, List[str]]:
    payload = data if isinstance(data, dict) else {}
    score = 100.0
    risk_flags: List[str] = []
    barcode = _supplement_digits(payload.get("barcode"))
    brand = _supplement_text(payload.get("brand"))
    batch_number = _supplement_text(payload.get("batch_number"))
    structured_data = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else payload

    if not barcode_exists_in_db(barcode):
        score -= 25.0
        risk_flags.append("barcode_not_found")

    if not barcode_matches_brand(barcode, brand):
        score -= 20.0
        risk_flags.append("brand_barcode_mismatch")

    if not batch_matches_regex(brand, batch_number):
        score -= 15.0
        risk_flags.append("batch_format_mismatch")

    suspicious_count = get_suspicious_batch_count(brand, batch_number)
    if suspicious_count > 3:
        score -= 20.0
        risk_flags.append("community_flagged_batch")

    if detect_protein_spiking(structured_data):
        score -= 15.0
        risk_flags.append("possible_protein_spiking")

    score = max(0.0, min(100.0, round(score, 1)))
    deduped: List[str] = []
    for flag in risk_flags:
        f = str(flag or "").strip()
        if f and f not in deduped:
            deduped.append(f)
    return score, deduped


def interpret_supplement_score(score: Any) -> str:
    s = float(_safe_float(score, 0.0) or 0.0)
    if s >= 80:
        return "High Authenticity Confidence"
    if s >= 60:
        return "Moderate Confidence"
    if s >= 40:
        return "Low Confidence - Review Recommended"
    return "High Risk - Verification Strongly Recommended"


def _supplement_explanation(score: Any, risk_flags: List[str]) -> str:
    s = float(_safe_float(score, 0.0) or 0.0)
    flags = [str(x or "").strip() for x in (risk_flags or []) if str(x or "").strip()]
    if not flags:
        return (
            f"No major anomaly patterns were detected from barcode, batch formatting, and nutrition consistency checks. "
            f"Current confidence score: {round(s, 1)}/100."
        )
    return (
        f"Detected {len(flags)} risk signal(s): {', '.join(flags[:4])}. "
        f"These indicators lowered confidence to {round(s, 1)}/100. "
        "Consider manual verification with the manufacturer."
    )


def _infer_supplement_region(
    region_hint: Any = "",
    *,
    request: Optional[Request] = None,
    header_values: Optional[List[Any]] = None,
) -> str:
    alias_map = {
        "AUS": "AU",
        "USA": "US",
        "GBR": "GB",
        "IND": "IN",
        "CAN": "CA",
        "NZL": "NZ",
    }

    def _norm(v: Any) -> str:
        token = re.sub(r"[^A-Za-z]", "", str(v or "")).upper()
        if not token:
            return ""
        if len(token) == 2:
            return token
        return alias_map.get(token, "")

    primary = _norm(region_hint)
    if primary:
        return primary

    for raw in (header_values or []):
        maybe = _norm(raw)
        if maybe:
            return maybe

    if request is not None:
        for key in ("x-country-code", "cf-ipcountry", "x-vercel-ip-country", "x-country", "x-geo-country"):
            maybe = _norm(request.headers.get(key))
            if maybe:
                return maybe
    return ""


def _supplement_macro_snapshot(structured_data: Dict[str, Any]) -> Dict[str, float]:
    payload = structured_data if isinstance(structured_data, dict) else {}
    panel = payload.get("nutrition_panel") if isinstance(payload.get("nutrition_panel"), dict) else {}
    return {
        "kcal_per_100g": _extract_supplement_panel_number(
            panel,
            ["kcal_per_100g", "calories_per_100g", "energy_kcal_per_100g", "kcal", "calories"],
        ),
        "protein_per_100g": _extract_supplement_panel_number(
            panel,
            ["protein_per_100g", "protein_g_per_100g", "protein_per100g", "protein"],
        ),
        "carbs_per_100g": _extract_supplement_panel_number(
            panel,
            ["carbs_per_100g", "carbohydrate_per_100g", "carbohydrates_per_100g", "carbs"],
        ),
        "fat_per_100g": _extract_supplement_panel_number(
            panel,
            ["fat_per_100g", "fat_g_per_100g", "fats_per_100g", "fat"],
        ),
    }


def _supplement_macro_variance_score_from_scan_rows(scan_rows: List[Dict[str, Any]]) -> float:
    buckets: Dict[str, List[float]] = {
        "kcal_per_100g": [],
        "protein_per_100g": [],
        "carbs_per_100g": [],
        "fat_per_100g": [],
    }
    for row in scan_rows or []:
        raw_structured = row.get("structured_data")
        structured = raw_structured if isinstance(raw_structured, dict) else _parse_jsonish(raw_structured, {})
        macros = _supplement_macro_snapshot(structured if isinstance(structured, dict) else {})
        for key in buckets.keys():
            val = float(_safe_float(macros.get(key), 0.0) or 0.0)
            if val > 0:
                buckets[key].append(val)

    cv_scores: List[float] = []
    for values in buckets.values():
        if len(values) < 2:
            continue
        mean = sum(values) / float(len(values))
        if mean <= 0:
            continue
        variance = sum((v - mean) ** 2 for v in values) / float(len(values))
        std_dev = math.sqrt(max(0.0, variance))
        cv_scores.append(std_dev / mean)

    if not cv_scores:
        return 0.0
    return round(max(0.0, min(100.0, (sum(cv_scores) / float(len(cv_scores))) * 100.0)), 2)


def _supplement_region_map_from_scan_rows(scan_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in scan_rows or []:
        region_code = _infer_supplement_region((row or {}).get("region"))
        if not region_code:
            continue
        counts[region_code] = int(counts.get(region_code, 0) or 0) + 1
    return counts


def _supplement_batch_pattern_query_match(brand_txt: str, batch: str, variant_txt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    base_match = {
        "brand": f"eq.{brand_txt}",
        "batch_number": f"eq.{batch}",
    }
    variant_match = dict(base_match)
    if variant_txt:
        variant_match["variant"] = f"eq.{variant_txt}"

    if variant_txt:
        try:
            row = sb_get_one(
                TBL_SUPPLEMENT_BATCH_PATTERNS,
                params={"select": "*", "limit": "1", **variant_match},
            )
            return (row if isinstance(row, dict) else None), variant_match
        except Exception as e:
            raw = _http_exc_raw(e).lower()
            if "variant" not in raw:
                if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e):
                    logger.info(f"supplement batch pattern read skipped: {e}")
                return None, variant_match

    try:
        row = sb_get_one(
            TBL_SUPPLEMENT_BATCH_PATTERNS,
            params={"select": "*", "limit": "1", **base_match},
        )
        return (row if isinstance(row, dict) else None), base_match
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e):
            logger.info(f"supplement batch pattern read skipped: {e}")
        return None, base_match


def _supplement_batch_scan_rows(brand_txt: str, batch: str, variant_txt: str) -> List[Dict[str, Any]]:
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_SCANS):
        return []
    base_params = {
        "select": "id,region,authenticity_score,structured_data",
        "brand": f"eq.{brand_txt}",
        "batch_number": f"eq.{batch}",
        "limit": "500",
    }
    if variant_txt:
        variant_params = dict(base_params)
        variant_params["variant"] = f"eq.{variant_txt}"
        try:
            return sb_get_many(TBL_SUPPLEMENT_SCANS, params=variant_params)
        except Exception as e:
            raw = _http_exc_raw(e).lower()
            if "variant" not in raw:
                if not _mark_table_unavailable(TBL_SUPPLEMENT_SCANS, e):
                    logger.info(f"supplement scan aggregate read skipped: {e}")
                return []
    try:
        return sb_get_many(TBL_SUPPLEMENT_SCANS, params=base_params)
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_SCANS, e):
            logger.info(f"supplement scan aggregate read skipped: {e}")
        return []


def _upsert_supplement_batch_pattern(
    brand: str,
    batch_number: str,
    *,
    variant: str = "",
    region: str = "",
    auth_score: Optional[float] = None,
    structured_data: Optional[Dict[str, Any]] = None,
) -> None:
    brand_txt = _supplement_text(brand)
    batch = _supplement_text(batch_number)
    if not brand_txt or not batch:
        return
    variant_txt = _supplement_text(variant)
    region_txt = _infer_supplement_region(region)
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_BATCH_PATTERNS):
        return
    now_iso = _now_utc_naive().isoformat()
    existing, match_params = _supplement_batch_pattern_query_match(brand_txt, batch, variant_txt)
    scan_rows = _supplement_batch_scan_rows(brand_txt, batch, variant_txt)
    existing_count = int(_safe_float((existing or {}).get("scan_count"), 0) or 0) if isinstance(existing, dict) else 0
    if len(scan_rows) <= existing_count:
        scan_rows = list(scan_rows)
        scan_rows.append(
            {
                "region": region_txt,
                "authenticity_score": float(_safe_float(auth_score, 0.0) or 0.0),
                "structured_data": structured_data if isinstance(structured_data, dict) else {},
            }
        )
    if not scan_rows:
        fallback_row = {
            "region": region_txt,
            "authenticity_score": float(_safe_float(auth_score, 0.0) or 0.0),
            "structured_data": structured_data if isinstance(structured_data, dict) else {},
        }
        scan_rows = [fallback_row]

    region_scan_map = _supplement_region_map_from_scan_rows(scan_rows)
    scan_count = int(len(scan_rows or []))
    if existing_count > 0:
        scan_count = max(scan_count, existing_count + 1)
    else:
        scan_count = max(1, scan_count)

    auth_values = [
        float(_safe_float((row or {}).get("authenticity_score"), 0.0) or 0.0)
        for row in (scan_rows or [])
        if float(_safe_float((row or {}).get("authenticity_score"), 0.0) or 0.0) > 0
    ]
    if auth_values:
        avg_auth_score = round(sum(auth_values) / float(len(auth_values)), 2)
    else:
        avg_auth_score = float(_safe_float(auth_score, 0.0) or 0.0)
    macro_variance_score = _supplement_macro_variance_score_from_scan_rows(scan_rows)
    regions = sorted([k for k in region_scan_map.keys() if str(k or "").strip()])

    if isinstance(existing, dict):
        patch = {
            "variant": variant_txt,
            "scan_count": scan_count or int(_safe_float(existing.get("scan_count"), 0) or 0),
            "last_seen": now_iso,
            "last_updated_at": now_iso,
            "regions": regions,
            "region_scan_map": region_scan_map,
            "macro_variance_score": macro_variance_score,
            "avg_auth_score": avg_auth_score,
        }
        try:
            _sb_patch_with_column_fallback(TBL_SUPPLEMENT_BATCH_PATTERNS, match_params, patch)
        except Exception as e:
            if "variant" in match_params and "variant" in _http_exc_raw(e).lower():
                fallback_match = {
                    "brand": f"eq.{brand_txt}",
                    "batch_number": f"eq.{batch}",
                }
                try:
                    _sb_patch_with_column_fallback(TBL_SUPPLEMENT_BATCH_PATTERNS, fallback_match, patch)
                    return
                except Exception as e2:
                    if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e2):
                        logger.info(f"supplement batch pattern patch skipped: {e2}")
                    return
            if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e):
                logger.info(f"supplement batch pattern patch skipped: {e}")
        return

    row = {
        "brand": brand_txt,
        "variant": variant_txt,
        "batch_number": batch,
        "scan_count": max(1, scan_count),
        "first_seen": now_iso,
        "last_seen": now_iso,
        "last_updated_at": now_iso,
        "regions": regions,
        "region_scan_map": region_scan_map,
        "macro_variance_score": macro_variance_score,
        "avg_auth_score": avg_auth_score,
    }
    try:
        _sb_insert_with_column_fallback(TBL_SUPPLEMENT_BATCH_PATTERNS, row)
    except Exception as e:
        if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e):
            logger.info(f"supplement batch pattern insert skipped: {e}")


def _store_supplement_scan(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row or {})
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_SCANS):
        return payload
    try:
        stored = _sb_insert_with_column_fallback(TBL_SUPPLEMENT_SCANS, payload)
        return dict(stored or payload)
    except Exception as e:
        if _mark_table_unavailable(TBL_SUPPLEMENT_SCANS, e):
            return payload
        raise


async def _read_valid_image_bytes(upload: UploadFile, field_name: str) -> bytes:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail={"error": f"{field_name}_empty"})
    try:
        Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail={"error": f"{field_name}_invalid_image"})
    return data


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
      - rebuilds user_weekly_metrics (prediction + consistency engine)
    """
    uid = require_user_id(x_user_id, user_id)
    out = recompute_behavior_memory(uid, day_iso=day, tz=tz, tz_offset_min=tz_offset_min)
    week_start_iso = str(out.get("week_start") or _week_start_monday(_day_iso(day, tz=tz, tz_offset_min=tz_offset_min)))
    public_metrics = _public_predictive_signals(out.get("weekly_metrics"), week_start_iso)
    if isinstance(public_metrics, dict):
        out = dict(out)
        out["weekly_metrics"] = public_metrics
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
    weekly_metrics = None
    try:
        if not refresh:
            weekly_metrics = get_user_weekly_metrics_payload(uid, week_start_iso)
    except Exception as e:
        logger.info(f"weekly metrics read skipped in /weekly/insights: {e}")

    week_tz = _select_week_timezone(
        payload if isinstance(payload, dict) else weekly_metrics,
        tz=tz,
        tz_offset_min=tz_offset_min,
    )
    if _is_payload_stale(payload, anchor_day):
        rows = get_daily_metrics_window(uid, week_start_iso)
        payload = build_weekly_insight_payload(uid, week_start_iso, rows, tz_used=week_tz)
        upsert_weekly_insight(uid, week_start_iso, payload)
    if _is_payload_stale(weekly_metrics, anchor_day):
        rows = get_daily_metrics_window(uid, week_start_iso)
        weekly_metrics = build_weekly_prediction_payload(uid, week_start_iso, rows, tz_used=week_tz)
        try:
            upsert_user_weekly_metrics(uid, week_start_iso, weekly_metrics)
        except Exception as e:
            logger.info(f"weekly metrics write skipped in /weekly/insights: {e}")

    public_metrics = _public_predictive_signals(weekly_metrics, week_start_iso)
    return {
        "ok": True,
        "week_start": week_start_iso,
        "week_end": _week_end_from_start(week_start_iso),
        "insights": payload,
        "metrics": public_metrics or {},
    }


# -------------------- DAILY COACH (LLM INTERPRETER ONLY) --------------------
_COACH_MEM_CACHE: Dict[str, Dict[str, Any]] = {}
_COACH_VOICE_CACHE_MEM: Dict[str, Dict[str, Any]] = {}
_WEEKLY_REPORT_CACHE_MEM: Dict[str, Dict[str, Any]] = {}
_DAILY_TOTALS_VERSION_MEM: Dict[str, Dict[str, Any]] = {}
_USER_COACH_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}

_COACH_SYSTEM_PROMPT = (
    "You are a nutrition coaching assistant. "
    "Provide behavior-focused suggestions only. "
    "Do not provide medical advice, diagnosis, treatment, drug, or supplement recommendations. "
    "Use ONLY the provided numbers and context. "
    "Do not invent metrics. "
    "Output strict JSON only."
)

_DAILY_TONE_ALIASES = {
    "supportive": "supportive",
    "strict": "strict",
    "firm": "strict",
    "funny": "funny",
    "fun": "funny",
    "indian_coach": "indian_coach",
    "indian": "indian_coach",
    "neutral": "supportive",
}

_DAILY_TONE_PROMPTS = {
    "supportive": (
        "Tone supportive: warm and encouraging, acknowledge effort, no guilt language, "
        "practical next step phrasing, zero shame language."
    ),
    "strict": (
        "Tone strict: direct and accountable, command-style short phrasing, no emoji, "
        "must include one concise consequence line without medical claims."
    ),
    "funny": (
        "Tone funny: playful coach voice with one hook phrase like 'Plot twist' or 'Cheat code', "
        "max 2 emoji total, keep facts unchanged and practical."
    ),
    "indian_coach": (
        "Tone indian_coach: Hinglish-light, include 1-2 Hinglish phrases only (e.g. 'chalo', 'boss', 'scene'), "
        "keep guidance practical and respectful, no slang abuse."
    ),
}

_DAILY_TONE_TAG_MAP = {
    "supportive": "supportive",
    "strict": "firm",
    "funny": "celebratory",
    "indian_coach": "supportive",
}

_DAILY_TONE_PACK = {
    "supportive": {
        "emoji_max": 1,
        "signature_phrases": ["Small win", "Let's make it easy", "You're building momentum"],
        "banned_words": ["lazy", "failure", "punishment", "worthless"],
        "must_include_any": ["small win", "let's", "momentum", "try", "aim for"],
    },
    "strict": {
        "emoji_max": 0,
        "signature_phrases": ["Minimum standard", "Do this today", "Non-negotiable"],
        "banned_words": ["lol", "maybe", "kinda", "sort of"],
        "must_include_any": ["do this today", "minimum standard", "fix", "target"],
    },
    "funny": {
        "emoji_max": 2,
        "signature_phrases": ["Plot twist", "Cheat code", "Boss move", "Side quest"],
        "banned_words": ["stupid", "idiot", "pathetic"],
        "must_include_any": ["plot twist", "cheat code", "boss move", "side quest"],
    },
    "indian_coach": {
        "emoji_max": 1,
        "signature_phrases": ["Scene simple hai", "Chalo", "Boss", "Bhai", "Sorted"],
        "hinglish_phrases": ["bhai", "boss", "chalo", "scene", "sorted", "pakka", "thoda", "done hai"],
        "banned_words": ["hopeless", "bakwaas", "useless"],
        "must_include_any": ["scene", "chalo", "boss", "bhai", "sorted"],
        "hinglish_min": 1,
        "hinglish_max": 2,
    },
}

_COACH_SUMMARY_STYLE_BANK = {
    "supportive": [
        "Good momentum today. {summary_fact}",
        "Nice effort so far. {summary_fact}",
        "You are building consistency. {summary_fact}",
        "Small win focus: {summary_fact}",
        "You are on track. Main lever now: {summary_fact}",
        "Progress looks steady. Key shift: {summary_fact}",
        "Strong check-in. Highest-impact change: {summary_fact}",
        "Today’s direction improves if you fix this: {summary_fact}",
        "Good base today. Priority lever: {summary_fact}",
        "Simple focus for today: {summary_fact}",
    ],
    "strict": [
        "Current bottleneck: {bottleneck_label}. {summary_fact} Fix this today.",
        "Non-negotiable lever is {bottleneck_label}. {summary_fact}",
        "Results are limited by {bottleneck_label}. {summary_fact} Act now.",
        "{summary_fact} Do this today.",
        "Main limiter: {bottleneck_label}. {summary_fact} Execute now.",
        "This must be corrected today: {summary_fact}",
        "No drift today. {summary_fact}",
        "Priority is {bottleneck_label}. {summary_fact} Keep it tight.",
        "Direct fix required: {summary_fact}",
        "If unchanged, progress slows. {summary_fact}",
    ],
    "funny": [
        "Plot twist: {summary_fact}",
        "Cheat code moment: {summary_fact}",
        "Boss move alert: {summary_fact}",
        "Side quest check: {summary_fact}",
        "Quick plot update: {summary_fact}",
        "Today’s cheat code is simple: {summary_fact}",
        "Boss move for this meal cycle: {summary_fact}",
        "Tiny side quest, big payoff: {summary_fact}",
        "Game plan update: {summary_fact}",
        "Level-up lever today: {summary_fact}",
    ],
    "indian_coach": [
        "Scene simple hai: {summary_fact}",
        "Boss, aaj ka lever {bottleneck_label} hai. {summary_fact}",
        "Chalo, seedha point: {summary_fact}",
        "Yeh day ka main scene: {summary_fact}",
        "Aaj ka focus clear hai: {summary_fact}",
        "Seedha bolun: {summary_fact}",
        "Boss, yahi main fix hai: {summary_fact}",
        "Chalo practical rakhte hain: {summary_fact}",
        "Aaj ka ROI move: {summary_fact}",
        "Simple scene, strong result: {summary_fact}",
    ],
}

_COACH_WHY_STYLE_BANK = {
    "supportive": [
        "{impact}",
        "Why this matters: {impact}",
        "This matters because {impact}",
    ],
    "strict": [
        "{impact}",
        "Reason: {impact}",
        "If unchanged, this will keep progress unstable. {impact}",
    ],
    "funny": [
        "{impact}",
        "Why it matters: {impact}",
        "Translation: {impact}",
    ],
    "indian_coach": [
        "{impact}",
        "Why matter karta hai: {impact}",
        "Simple reason: {impact}",
    ],
}

_COACH_ACTION_STYLE_BANK = {
    "supportive": [
        "{one_change}",
        "Next easy step: {one_change}",
        "Do this next meal: {one_change}",
        "Highest-ROI step now: {one_change}",
        "Simple action right now: {one_change}",
        "One practical move: {one_change}",
    ],
    "strict": [
        "Do this today: {one_change}",
        "Immediate fix: {one_change}",
        "Non-negotiable action: {one_change}",
        "Execute now: {one_change}",
        "Priority action: {one_change}",
        "Fix this in your next meal: {one_change}",
    ],
    "funny": [
        "Cheat code: {one_change}",
        "Boss move: {one_change}",
        "Quick win: {one_change}",
        "Level-up move: {one_change}",
        "Tiny hack, big impact: {one_change}",
        "Main quest action: {one_change}",
    ],
    "indian_coach": [
        "Chalo, next meal fix: {one_change}",
        "Bas itna kar: {one_change}",
        "Boss move: {one_change}",
        "Aaj ka direct action: {one_change}",
        "Seedha next step: {one_change}",
        "Simple fix abhi: {one_change}",
    ],
}

_COACH_TONE_REWRITE_SYSTEM_PROMPT = (
    "You are a coaching tone rewriter. "
    "Rewrite coaching content into the requested tone while preserving factual meaning and numbers. "
    "Output valid JSON only, no markdown, no extra keys. "
    "Do not add medical claims, diagnosis, treatment advice, shame, or insults. "
    "Preserve all numeric values exactly."
)

_COACH_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
_COACH_PERSONA_PROMPTS = {
    "supportive": (
        "Persona: supportive. "
        "Warm, encouraging, calm. "
        "Acknowledge effort, avoid guilt language, keep tone reassuring."
    ),
    "direct": (
        "Persona: direct. "
        "Short, blunt, no fluff. "
        "State the issue and exact fix in plain language."
    ),
    "performance": (
        "Persona: performance. "
        "Athletic framing: recovery, training readiness, adherence. "
        "Action-first with performance intent."
    ),
    "data": (
        "Persona: data-driven. "
        "Analytical and concise. Mention one key metric anchor without overload."
    ),
}
_COACH_VOICE_SYSTEM_PROMPT = (
    "You are a nutrition coaching assistant for a consumer app. "
    "Output strict JSON only, no markdown, no extra keys. "
    "Never provide medical diagnosis, treatment, or disease claims. "
    "Never guarantee body-weight outcomes. "
    "Always keep empathy_line effort-acknowledging and practical."
)
_UNCERTAINTY_HINTS = ("likely", "might", "looks like", "appears", "could")


def _normalize_persona_mode(mode: Any) -> str:
    m = str(mode or "supportive").strip().lower()
    if m not in _COACH_PERSONA_PROMPTS:
        return "supportive"
    return m


def _normalize_semantic_key(key: Any) -> str:
    text = str(key or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64]


def _normalize_semantic_key_list(values: Any, limit: int = 12) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in (values or []):
        k = _normalize_semantic_key(v)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
        if len(out) >= limit:
            break
    return out


def _normalize_short_text_list(values: Any, limit: int = 3, max_chars: int = 180) -> List[str]:
    out: List[str] = []
    for v in (values or []):
        s = str(v or "").strip()
        if not s:
            continue
        out.append(s[:max_chars])
        if len(out) >= limit:
            break
    return out


def _safe_day_iso(day_iso: Any) -> str:
    raw = str(day_iso or "").strip()
    if not raw:
        return _today_date().isoformat()
    try:
        return dt.date.fromisoformat(raw[:10]).isoformat()
    except Exception:
        return _today_date().isoformat()


def _coach_day_memory_key(user_id: str, day_iso: str) -> str:
    return f"{str(user_id or '').strip()}:{_safe_day_iso(day_iso)}"


def _blank_coach_memory(day_iso: str) -> Dict[str, Any]:
    return {
        "day": _safe_day_iso(day_iso),
        "recent_advice_keys": [],
        "recent_user_friction": [],
        "last_3_coach_messages": [],
        "updated_at": dt.datetime.utcnow().isoformat(),
    }


def _coach_memory_field(row: Dict[str, Any], key: str, default: Any = None) -> Any:
    src = row if isinstance(row, dict) else {}
    if key in src and src.get(key) is not None:
        return src.get(key)
    payload = _parse_jsonish(src.get("payload"), {})
    if isinstance(payload, dict) and payload.get(key) is not None:
        return payload.get(key)
    return default


def _read_coach_memory_day(user_id: str, day_iso: str) -> Dict[str, Any]:
    key = _coach_day_memory_key(user_id, day_iso)
    cached = _COACH_MEMORY_CACHE.get(key)
    if isinstance(cached, dict):
        return dict(cached)

    out = _blank_coach_memory(day_iso)
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_MEMORY):
        _COACH_MEMORY_CACHE[key] = out
        return out
    try:
        row = sb_get_one(
            TBL_COACH_MEMORY,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{_safe_day_iso(day_iso)}",
                "limit": "1",
            },
        )
        if isinstance(row, dict):
            out = {
                "day": _safe_day_iso(row.get("day") or day_iso),
                "recent_advice_keys": _normalize_semantic_key_list(
                    _coach_memory_field(row, "recent_advice_keys")
                    or _coach_memory_field(row, "advice_keys")
                    or []
                ),
                "recent_user_friction": _normalize_short_text_list(
                    _coach_memory_field(row, "recent_user_friction")
                    or _coach_memory_field(row, "user_friction")
                    or [],
                    limit=6,
                    max_chars=90,
                ),
                "last_3_coach_messages": _normalize_short_text_list(
                    _coach_memory_field(row, "last_3_coach_messages")
                    or _coach_memory_field(row, "last_messages")
                    or [],
                    limit=3,
                    max_chars=180,
                ),
                "updated_at": str(row.get("updated_at") or dt.datetime.utcnow().isoformat()),
            }
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_MEMORY, e):
            logger.info(f"coach memory day read skipped: {e}")
    _COACH_MEMORY_CACHE[key] = out
    return dict(out)


def _read_coach_memory_window(user_id: str, day_iso: str) -> Dict[str, Any]:
    day_key = _safe_day_iso(day_iso)
    day_mem = _read_coach_memory_day(user_id, day_key)
    out = {
        "day": day_key,
        "recent_advice_keys": _normalize_semantic_key_list(day_mem.get("recent_advice_keys"), limit=24),
        "recent_user_friction": _normalize_short_text_list(day_mem.get("recent_user_friction"), limit=8, max_chars=90),
        "last_3_coach_messages": _normalize_short_text_list(day_mem.get("last_3_coach_messages"), limit=3, max_chars=180),
    }
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_MEMORY):
        return out
    try:
        start_day = (dt.date.fromisoformat(day_key) - dt.timedelta(days=6)).isoformat()
        rows = sb_get_many(
            TBL_COACH_MEMORY,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"gte.{start_day}",
                "order": "day.desc",
                "limit": "7",
            },
        )
        recent_keys: List[str] = list(out["recent_advice_keys"])
        seen = set(recent_keys)
        last_messages: List[str] = list(out["last_3_coach_messages"])
        for row in (rows or []):
            for k in _normalize_semantic_key_list(_coach_memory_field(row, "recent_advice_keys") or [], limit=12):
                if k in seen:
                    continue
                seen.add(k)
                recent_keys.append(k)
                if len(recent_keys) >= 24:
                    break
            for msg in _normalize_short_text_list(
                _coach_memory_field(row, "last_3_coach_messages") or [],
                limit=3,
                max_chars=180,
            ):
                if msg not in last_messages:
                    last_messages.append(msg)
                if len(last_messages) >= 3:
                    break
        out["recent_advice_keys"] = recent_keys[:24]
        out["last_3_coach_messages"] = last_messages[:3]
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_MEMORY, e):
            logger.info(f"coach memory 7-day read skipped: {e}")
    return out


def _write_coach_memory_day(user_id: str, day_iso: str, memory: Dict[str, Any]) -> Dict[str, Any]:
    day_key = _safe_day_iso(day_iso)
    payload_json = {
        "recent_advice_keys": _normalize_semantic_key_list((memory or {}).get("recent_advice_keys"), limit=24),
        "recent_user_friction": _normalize_short_text_list((memory or {}).get("recent_user_friction"), limit=8, max_chars=90),
        "last_3_coach_messages": _normalize_short_text_list((memory or {}).get("last_3_coach_messages"), limit=3, max_chars=180),
    }
    payload = {
        "user_id": str(user_id or "").strip(),
        "day": day_key,
        "recent_advice_keys": payload_json["recent_advice_keys"],
        "recent_user_friction": payload_json["recent_user_friction"],
        "last_3_coach_messages": payload_json["last_3_coach_messages"],
        "payload": payload_json,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    _COACH_MEMORY_CACHE[_coach_day_memory_key(user_id, day_key)] = dict(payload)
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_MEMORY):
        return payload
    try:
        existing = sb_get_one(
            TBL_COACH_MEMORY,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{day_key}",
                "limit": "1",
            },
        )
        if existing:
            patch = {k: v for k, v in payload.items() if k not in {"user_id", "day"}}
            _sb_patch_with_column_fallback(
                TBL_COACH_MEMORY,
                {"user_id": f"eq.{user_id}", "day": f"eq.{day_key}"},
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_COACH_MEMORY,
                payload,
                locked_cols={"user_id", "day"},
            )
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_MEMORY, e):
            logger.info(f"coach memory write skipped: {e}")
    return payload


def _infer_semantic_key_from_action(title: Any, how: Any) -> str:
    text = f"{str(title or '')} {str(how or '')}".lower()
    mapping = [
        ("protein_at_breakfast", ("protein", "breakfast")),
        ("add_fiber_veg", ("fiber", "veg")),
        ("reduce_upf_snack", ("ultra", "processed")),
        ("flatten_glycemic_spike", ("glycemic", "load")),
        ("add_oil_tracking", ("oil", "track")),
        ("portion_down_0_8", ("portion", "smaller")),
        ("hit_leucine_trigger", ("leucine", "mps")),
        ("scan_more_days", ("scan", "days")),
        ("confirm_cooking_oil", ("cooking", "oil")),
    ]
    for key, clues in mapping:
        if all(c in text for c in clues):
            return key
    if "protein" in text:
        return "protein_anchor"
    if "fiber" in text:
        return "fiber_boost"
    if "oil" in text or "fried" in text:
        return "add_oil_tracking"
    return "consistency_focus"


def _context_gap(context: Dict[str, Any], macro_key: str) -> float:
    goals = (context or {}).get("goals") if isinstance((context or {}).get("goals"), dict) else {}
    consumed = (context or {}).get("consumed_today") if isinstance((context or {}).get("consumed_today"), dict) else {}
    g = float(_safe_float(goals.get(macro_key), 0.0) or 0.0)
    c = float(_safe_float(consumed.get(macro_key), 0.0) or 0.0)
    return max(0.0, round(g - c, 1))


def _resolve_diet_style_from_context(context: Dict[str, Any]) -> str:
    profile = (context or {}).get("profile") if isinstance((context or {}).get("profile"), dict) else {}
    constraints = (context or {}).get("constraints") if isinstance((context or {}).get("constraints"), dict) else {}
    raw = str(profile.get("diet_style") or constraints.get("diet") or "non-veg").strip().lower()
    aliases = {
        "nonveg": "non_veg",
        "non-veg": "non_veg",
        "non_veg": "non_veg",
        "omnivore": "non_veg",
        "veg": "veg",
        "vegetarian": "veg",
        "eggetarian": "eggetarian",
        "egg_veg": "eggetarian",
        "vegan": "vegan",
    }
    return aliases.get(raw, "non_veg")


def _join_human_list(items: List[str]) -> str:
    vals = [str(x or "").strip() for x in (items or []) if str(x or "").strip()]
    if not vals:
        return "high-quality protein sources"
    if len(vals) == 1:
        return vals[0]
    if len(vals) == 2:
        return f"{vals[0]} and {vals[1]}"
    return f"{', '.join(vals[:-1])}, and {vals[-1]}"


def _diet_safe_protein_sources_text(context: Dict[str, Any], limit: int = 5) -> str:
    diet = _resolve_diet_style_from_context(context)
    sources = coach_logic.allowed_protein_sources(diet)
    trimmed = sources[: max(1, int(limit or 5))]
    return _join_human_list(trimmed)


def _is_low_confidence_context(context: Dict[str, Any]) -> bool:
    conf = (context or {}).get("confidence") if isinstance((context or {}).get("confidence"), dict) else {}
    vision_conf = float(_safe_float(conf.get("vision_confidence"), 1.0) or 1.0)
    band = str(conf.get("projection_confidence_band") or "medium").strip().lower()
    return vision_conf < 0.55 or band == "low"


def _repeat_allowed_for_key(context: Dict[str, Any], semantic_key: str) -> bool:
    key = _normalize_semantic_key(semantic_key)
    if not key:
        return False
    protein_gap = _context_gap(context, "protein_g")
    profile = (context or {}).get("profile") if isinstance((context or {}).get("profile"), dict) else {}
    training_days = int(_safe_float(profile.get("training_days_per_week"), 0) or 0)
    if "protein" in key and protein_gap > 60 and training_days >= 4:
        return True
    return False


def _voice_action_candidates(context: Dict[str, Any]) -> List[Dict[str, str]]:
    gaps = {
        "protein": _context_gap(context, "protein_g"),
        "fiber": _context_gap(context, "fiber_g"),
    }
    signals = (context or {}).get("signals") if isinstance((context or {}).get("signals"), dict) else {}
    conf = (context or {}).get("confidence") if isinstance((context or {}).get("confidence"), dict) else {}
    protein_sources_text = _diet_safe_protein_sources_text(context, limit=5)
    candidates: List[Dict[str, str]] = []

    if _is_low_confidence_context(context):
        candidates.append(
            {
                "semantic_key": "confirm_cooking_oil",
                "title": "Confirm cooking style + oil",
                "how": "Tap edit and set fried/air-fried + oil so macros recalculate correctly.",
            }
        )
        days_with_data = int(_safe_float(conf.get("days_with_data_7d"), 0) or 0)
        if days_with_data < 4:
            candidates.append(
                {
                    "semantic_key": "scan_more_days",
                    "title": "Improve data confidence",
                    "how": "Scan 2 more days this week to make coaching more reliable.",
                }
            )
        return candidates

    if gaps["protein"] >= 25:
        candidates.append(
            {
                "semantic_key": "protein_at_breakfast",
                "title": "Add early protein anchor",
                "how": "Add 25-35g protein at breakfast to close today’s protein gap faster.",
            }
        )
    if gaps["fiber"] >= 8:
        candidates.append(
            {
                "semantic_key": "add_fiber_veg",
                "title": "Add fiber booster now",
                "how": "Add one veg + legume side at the next meal to reduce your fiber gap.",
            }
        )
    if float(_safe_float(signals.get("ultra_processed_score"), 0.0) or 0.0) >= 7:
        candidates.append(
            {
                "semantic_key": "reduce_upf_snack",
                "title": "Swap one ultra-processed item",
                "how": "Replace one packaged snack with fruit + yogurt or nuts today.",
            }
        )
    if float(_safe_float(signals.get("glycemic_load"), 0.0) or 0.0) >= 20:
        candidates.append(
            {
                "semantic_key": "flatten_glycemic_spike",
                "title": "Flatten next glucose spike",
                "how": "Pair carbs with protein + veg at your next meal.",
            }
        )
    if not bool(signals.get("mps_triggered")) and gaps["protein"] > 0:
        candidates.append(
            {
                "semantic_key": "hit_leucine_trigger",
                "title": "Hit one leucine trigger",
                "how": f"Add one high-quality protein hit using {protein_sources_text}.",
            }
        )
    if not candidates:
        candidates.append(
            {
                "semantic_key": "consistency_focus",
                "title": "Hold consistency tonight",
                "how": "Keep the next meal simple: lean protein + veg + controlled carbs.",
            }
        )
    return candidates


def _pick_non_repeating_action(context: Dict[str, Any], recent_keys: List[str]) -> Dict[str, str]:
    seen = set(_normalize_semantic_key_list(recent_keys, limit=24))
    candidates = _voice_action_candidates(context)
    for cand in candidates:
        key = _normalize_semantic_key(cand.get("semantic_key"))
        if not key:
            continue
        if key not in seen or _repeat_allowed_for_key(context, key):
            return cand
    return candidates[0] if candidates else {
        "semantic_key": "consistency_focus",
        "title": "Keep consistency",
        "how": "Keep meals simple and balanced for the rest of the day.",
    }


def _limit_text(s: Any, max_chars: int) -> str:
    text = str(s or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _ensure_uncertainty_language(line: str) -> str:
    text = str(line or "").strip()
    lower = text.lower()
    if any(h in lower for h in _UNCERTAINTY_HINTS):
        return text
    if not text:
        return "This likely needs a quick confirmation before we lock coaching."
    return f"It looks like {text[0].lower() + text[1:]}" if len(text) > 1 else "Likely needs confirmation."


def _build_voice_fallback(mode: str, context: Dict[str, Any], recent_keys: List[str]) -> Dict[str, Any]:
    persona = _normalize_persona_mode(mode)
    action = _pick_non_repeating_action(context, recent_keys)
    low_conf = _is_low_confidence_context(context)
    protein_gap = _context_gap(context, "protein_g")
    fiber_gap = _context_gap(context, "fiber_g")

    empathy = "Nice work logging this meal. Small consistent tweaks will compound."
    if persona == "direct":
        empathy = "Good logging. Now execute one fix."
    elif persona == "performance":
        empathy = "Good check-in. Let’s protect recovery and adherence."
    elif persona == "data":
        empathy = "Good data point. One targeted change will move today’s trend."

    if low_conf:
        coach = "This scan likely needs one quick confirmation before we finalize coaching."
    elif protein_gap >= fiber_gap and protein_gap > 0:
        coach = f"Protein is still the main limiter today; closing ~{round(protein_gap, 1)}g changes the day."
    elif fiber_gap > 0:
        coach = f"Fiber remains low by ~{round(fiber_gap, 1)}g, which can hurt satiety later."
    else:
        coach = "You’re close to targets; one precise action can keep momentum strong."

    if low_conf:
        coach = _ensure_uncertainty_language(coach)

    tone_map = {
        "supportive": ["calm", "supportive", "confident"],
        "direct": ["direct", "concise", "clear"],
        "performance": ["focused", "athletic", "intentional"],
        "data": ["analytical", "calm", "precise"],
    }
    out = {
        "coach_line": _limit_text(coach, 160),
        "empathy_line": _limit_text(empathy, 120),
        "one_action": {
            "title": _limit_text(action.get("title") or "One next step", 42),
            "how": _limit_text(action.get("how") or "Apply one practical change in the next meal.", 120),
        },
        "avoid_repeats": _normalize_semantic_key_list([action.get("semantic_key")], limit=2),
        "tone_tags": tone_map.get(persona, tone_map["supportive"]),
    }
    if low_conf:
        out["safety_disclaimer"] = "Informational only. Confidence is currently low; confirm meal details."
    return out


def _coerce_coach_voice_output(
    parsed: Dict[str, Any],
    mode: str,
    context: Dict[str, Any],
    recent_keys: List[str],
) -> Dict[str, Any]:
    persona = _normalize_persona_mode(mode)
    low_conf = _is_low_confidence_context(context)

    coach_line = _limit_text(parsed.get("coach_line"), 160)
    empathy_line = _limit_text(parsed.get("empathy_line"), 120)
    one_action_src = parsed.get("one_action") if isinstance(parsed.get("one_action"), dict) else {}
    title = _limit_text(one_action_src.get("title"), 42)
    how = _limit_text(one_action_src.get("how"), 120)

    if not empathy_line:
        empathy_line = _build_voice_fallback(persona, context, recent_keys).get("empathy_line", "")
    if not coach_line:
        coach_line = _build_voice_fallback(persona, context, recent_keys).get("coach_line", "")
    if low_conf:
        coach_line = _ensure_uncertainty_language(coach_line)

    inferred_key = _infer_semantic_key_from_action(title, how)
    provided_keys = _normalize_semantic_key_list(parsed.get("avoid_repeats"), limit=4)
    key = provided_keys[0] if provided_keys else inferred_key
    if (key in set(_normalize_semantic_key_list(recent_keys, limit=24))) and not _repeat_allowed_for_key(context, key):
        alt = _pick_non_repeating_action(context, recent_keys)
        title = _limit_text(alt.get("title"), 42)
        how = _limit_text(alt.get("how"), 120)
        key = _normalize_semantic_key(alt.get("semantic_key"))

    if low_conf and key not in {"confirm_cooking_oil", "scan_more_days"}:
        alt = _pick_non_repeating_action({**context, "confidence": {"vision_confidence": 0.5, "projection_confidence_band": "low"}}, recent_keys)
        title = _limit_text(alt.get("title"), 42)
        how = _limit_text(alt.get("how"), 120)
        key = _normalize_semantic_key(alt.get("semantic_key"))

    if not title or not how:
        alt = _pick_non_repeating_action(context, recent_keys)
        title = _limit_text(alt.get("title"), 42)
        how = _limit_text(alt.get("how"), 120)
        key = _normalize_semantic_key(alt.get("semantic_key"))

    tone_tags = parsed.get("tone_tags") if isinstance(parsed.get("tone_tags"), list) else []
    tone_tags = [str(t).strip().lower() for t in tone_tags if str(t).strip()][:3]
    if not tone_tags:
        tone_tags = _build_voice_fallback(persona, context, recent_keys).get("tone_tags", ["calm", "supportive"])

    out = {
        "coach_line": coach_line,
        "empathy_line": empathy_line,
        "one_action": {"title": title, "how": how},
        "avoid_repeats": _normalize_semantic_key_list([key] + provided_keys, limit=2),
        "tone_tags": tone_tags,
    }
    disclaimer = str(parsed.get("safety_disclaimer") or "").strip()
    if low_conf:
        out["safety_disclaimer"] = disclaimer or "Informational only. Confidence is currently low; confirm meal details."
    elif disclaimer:
        out["safety_disclaimer"] = _limit_text(disclaimer, 140)
    return out


def _build_coach_voice_prompt(
    mode: str,
    compact_context: Dict[str, Any],
    recent_advice_keys: List[str],
    last_messages: List[str],
) -> str:
    template = {
        "coach_line": "string <=160 chars (1-2 sentences)",
        "empathy_line": "string <=120 chars (must acknowledge effort)",
        "one_action": {"title": "string <=42 chars", "how": "string <=120 chars"},
        "avoid_repeats": ["semantic_key_1", "semantic_key_2"],
        "tone_tags": ["calm", "supportive", "confident"],
        "safety_disclaimer": "optional string",
    }
    low_conf = _is_low_confidence_context(compact_context)
    low_conf_rule = (
        "LOW_CONFIDENCE_MODE=true. coach_line must include uncertainty words "
        "('likely', 'might', 'looks like'). one_action must be confirmation/data-quality focused."
        if low_conf
        else "LOW_CONFIDENCE_MODE=false."
    )
    return (
        f"{_COACH_PERSONA_PROMPTS.get(_normalize_persona_mode(mode), _COACH_PERSONA_PROMPTS['supportive'])}\n"
        "Contract:\n"
        "- JSON only, no markdown.\n"
        "- No extra keys.\n"
        "- No medical claims.\n"
        "- coach_line 1-2 sentences max.\n"
        "- Exactly one action.\n"
        "- Use recent_advice_keys to avoid repeats unless urgency is clearly high.\n"
        f"- {low_conf_rule}\n\n"
        f"recent_advice_keys: {json.dumps(_normalize_semantic_key_list(recent_advice_keys, limit=12), ensure_ascii=True)}\n"
        f"last_3_coach_messages: {json.dumps(_normalize_short_text_list(last_messages, limit=3), ensure_ascii=True)}\n"
        f"context: {json.dumps(compact_context, ensure_ascii=True)}\n"
        f"Output schema: {json.dumps(template, ensure_ascii=True)}"
    )


def _generate_coach_voice_llm(
    mode: str,
    compact_context: Dict[str, Any],
    recent_advice_keys: List[str],
    last_messages: List[str],
) -> Dict[str, Any]:
    _require_gemini_key()
    prompt = _build_coach_voice_prompt(mode, compact_context, recent_advice_keys, last_messages)
    txt, _, tried_models = _call_llm_with_timeout(
        [_COACH_VOICE_SYSTEM_PROMPT, prompt],
        model_name=COACH_VOICE_LLM_MODEL,
        timeout_sec=float(COACH_VOICE_TIMEOUT_SEC),
        retries=1,
        purpose="coach_voice",
    )
    parsed = coach_logic.extract_json_object(str(txt or "").strip())
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "coach_voice_llm_failed", "raw": "Coach voice response is not valid JSON.", "tried_models": tried_models},
        )
    return parsed


def _merge_memory_payload(
    persisted: Dict[str, Any],
    incoming: Dict[str, Any],
) -> Dict[str, Any]:
    out = {
        "recent_advice_keys": _normalize_semantic_key_list((persisted or {}).get("recent_advice_keys"), limit=24),
        "recent_user_friction": _normalize_short_text_list((persisted or {}).get("recent_user_friction"), limit=8, max_chars=90),
        "last_3_coach_messages": _normalize_short_text_list((persisted or {}).get("last_3_coach_messages"), limit=3, max_chars=180),
    }
    in_mem = incoming if isinstance(incoming, dict) else {}
    for k in _normalize_semantic_key_list(in_mem.get("recent_advice_keys"), limit=12):
        if k not in out["recent_advice_keys"]:
            out["recent_advice_keys"].append(k)
    out["recent_advice_keys"] = out["recent_advice_keys"][:24]
    for msg in _normalize_short_text_list(in_mem.get("last_3_coach_messages"), limit=3, max_chars=180):
        if msg not in out["last_3_coach_messages"]:
            out["last_3_coach_messages"].insert(0, msg)
    out["last_3_coach_messages"] = out["last_3_coach_messages"][:3]
    for fx in _normalize_short_text_list(in_mem.get("recent_user_friction"), limit=6, max_chars=90):
        if fx not in out["recent_user_friction"]:
            out["recent_user_friction"].append(fx)
    out["recent_user_friction"] = out["recent_user_friction"][:8]
    return out


def _compact_voice_context(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    ctx = raw_context if isinstance(raw_context, dict) else {}
    goals = ctx.get("goals") if isinstance(ctx.get("goals"), dict) else {}
    consumed = ctx.get("consumed_today") if isinstance(ctx.get("consumed_today"), dict) else {}
    meal = ctx.get("meal_totals") if isinstance(ctx.get("meal_totals"), dict) else {}
    signals = ctx.get("signals") if isinstance(ctx.get("signals"), dict) else {}
    conf = ctx.get("confidence") if isinstance(ctx.get("confidence"), dict) else {}
    profile = ctx.get("profile") if isinstance(ctx.get("profile"), dict) else {}
    return {
        "meal_id": str(ctx.get("meal_id") or ""),
        "date": _safe_day_iso(ctx.get("date")),
        "timezone": str(ctx.get("timezone") or ""),
        "goals": {
            "kcal": round(_safe_float(goals.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(goals.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(goals.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(goals.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(goals.get("fiber_g"), 0.0), 1),
        },
        "consumed_today": {
            "kcal": round(_safe_float(consumed.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(consumed.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(consumed.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(consumed.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(consumed.get("fiber_g"), 0.0), 1),
        },
        "meal_totals": {
            "kcal": round(_safe_float(meal.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(meal.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(meal.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(meal.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(meal.get("fiber_g"), 0.0), 1),
        },
        "signals": {
            "ultra_processed_score": round(_safe_float(signals.get("ultra_processed_score"), 0.0), 1),
            "glycemic_load": round(_safe_float(signals.get("glycemic_load"), 0.0), 1),
            "satiety_score": round(_safe_float(signals.get("satiety_score"), 0.0), 1),
            "protein_bv_score": round(_safe_float(signals.get("protein_bv_score"), 0.0), 1),
            "mps_triggered": bool(signals.get("mps_triggered")),
        },
        "confidence": {
            "vision_confidence": round(_safe_float(conf.get("vision_confidence"), 1.0), 3),
            "projection_confidence_band": str(conf.get("projection_confidence_band") or "medium").strip().lower(),
            "days_with_data_7d": int(_safe_float(conf.get("days_with_data_7d"), 0) or 0),
            "scans_7d": int(_safe_float(conf.get("scans_7d"), 0) or 0),
        },
        "profile": {
            "goal_type": str(profile.get("goal_type") or ""),
            "training_days_per_week": int(_safe_float(profile.get("training_days_per_week"), 0) or 0),
            "training_time": str(profile.get("training_time") or ""),
            "coach_persona": _normalize_persona_mode(profile.get("coach_persona")),
        },
    }


def _append_coach_memory_entry(
    user_id: str,
    day_iso: str,
    semantic_key: str,
    coach_line: str,
    friction: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cur = _read_coach_memory_day(user_id, day_iso)
    keys = _normalize_semantic_key_list([semantic_key] + list(cur.get("recent_advice_keys") or []), limit=24)
    msgs = _normalize_short_text_list([coach_line] + list(cur.get("last_3_coach_messages") or []), limit=3, max_chars=180)
    fx = _normalize_short_text_list(list(cur.get("recent_user_friction") or []) + list(friction or []), limit=8, max_chars=90)
    return _write_coach_memory_day(
        user_id,
        day_iso,
        {
            "recent_advice_keys": keys,
            "last_3_coach_messages": msgs,
            "recent_user_friction": fx,
        },
    )


def _now_utc_naive() -> dt.datetime:
    return dt.datetime.utcnow()


def _parse_iso_dt_naive(value: Any) -> Optional[dt.datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _cache_user_coach_profile(user_id: str, profile: Dict[str, Any], tone_preference: str = "") -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    src = profile if isinstance(profile, dict) else {}
    diet_style = coach_logic.normalize_diet_style(src.get("diet_style") or src.get("diet") or "non-veg")
    entry = {
        "goal_type": str(src.get("goal_type") or "fat_loss").strip().lower() or "fat_loss",
        "diet_style": diet_style,
        "training_days_per_week": max(0, int(_safe_float(src.get("training_days_per_week"), 0) or 0)),
        "training_time": str(src.get("training_time") or "evening").strip().lower() or "evening",
        "tone_preference": _normalize_daily_tone_id(tone_preference or src.get("tone_preference") or "supportive"),
        "updated_at": _now_utc_naive().isoformat(),
    }
    _USER_COACH_PROFILE_CACHE[uid] = entry


def _get_cached_user_coach_profile(user_id: str) -> Dict[str, Any]:
    uid = str(user_id or "").strip()
    if not uid:
        return {}
    src = _USER_COACH_PROFILE_CACHE.get(uid)
    return dict(src) if isinstance(src, dict) else {}


def _normalize_tone_preference(v: Any) -> str:
    tone = str(v or "supportive").strip().lower()
    aliases = {
        "supportive": "supportive",
        "strict": "strict",
        "firm": "strict",
        "funny": "funny",
        "fun": "funny",
        "indian_coach": "indian_coach",
        "indian": "indian_coach",
        "neutral": "supportive",
    }
    return aliases.get(tone, "supportive")


def _normalize_daily_tone_id(v: Any) -> str:
    tone = str(v or "supportive").strip().lower()
    return _DAILY_TONE_ALIASES.get(tone, "supportive")


def _normalize_tone_tag(v: Any, fallback: str = "neutral") -> str:
    tone = str(v or "").strip().lower()
    if tone not in {"supportive", "firm", "celebratory", "neutral"}:
        return fallback if fallback in {"supportive", "firm", "celebratory", "neutral"} else "neutral"
    return tone


def _daily_tone_prompt_text(tone_preference: str) -> str:
    tone = _normalize_daily_tone_id(tone_preference)
    return _DAILY_TONE_PROMPTS.get(tone, _DAILY_TONE_PROMPTS["supportive"])


def _clip_line(text: Any, max_words: int = 28) -> str:
    words = [w for w in str(text or "").strip().split() if w]
    if not words:
        return ""
    return " ".join(words[:max_words]).strip()


def _normalize_similarity_text(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").strip().lower()).strip()


def _line_similarity(a: Any, b: Any) -> float:
    ta = set(_normalize_similarity_text(a).split())
    tb = set(_normalize_similarity_text(b).split())
    if not ta or not tb:
        return 0.0
    inter = len(ta.intersection(tb))
    union = len(ta.union(tb))
    return float(inter / union) if union else 0.0


def _is_repetitive_line(candidate: Any, recent_lines: List[str], threshold: float = 0.78) -> bool:
    c = _normalize_similarity_text(candidate)
    if not c:
        return False
    for line in (recent_lines or []):
        r = _normalize_similarity_text(line)
        if not r:
            continue
        if c == r:
            return True
        if _line_similarity(c, r) >= float(threshold):
            return True
    return False


def _pick_style_line(
    templates: List[str],
    seed: str,
    fmt: Dict[str, str],
    recent_lines: List[str],
    fallback_line: str,
    *,
    max_words: int,
) -> str:
    bank = [str(t or "").strip() for t in (templates or []) if str(t or "").strip()]
    if not bank:
        return _clip_line(fallback_line, max_words=max_words)
    idx = int(hashlib.sha256(str(seed or "seed").encode("utf-8")).hexdigest(), 16) % len(bank)
    for step in range(min(len(bank), 4)):
        tmpl = bank[(idx + step) % len(bank)]
        try:
            candidate = tmpl.format(**fmt)
        except Exception:
            candidate = tmpl
        candidate = _clip_line(candidate, max_words=max_words)
        if not _is_repetitive_line(candidate, recent_lines):
            return candidate
    try:
        fallback_candidate = bank[idx].format(**fmt)
    except Exception:
        fallback_candidate = bank[idx]
    return _clip_line(fallback_candidate or fallback_line, max_words=max_words)


def _coach_variation_seed(user_id: str, day_iso: str, scan_id: str, scan_count: int) -> str:
    uid = str(user_id or "").strip()[-12:] or "anon"
    sid = str(scan_id or "").strip()
    sid_tail = sid[-6:] if sid else f"scan{max(0, int(_safe_float(scan_count, 0) or 0))}"
    return f"{_safe_day_iso(day_iso)}|{uid}|{sid_tail}"


def _apply_dynamic_coach_copy(
    coach_resp: Dict[str, Any],
    norm_payload: Dict[str, Any],
    *,
    user_id: str,
    day_iso: str,
    scan_id: str,
    scan_count: int,
    recent_messages: List[str],
) -> Dict[str, Any]:
    out = dict(coach_resp or {})
    recent_for_pick = _normalize_short_text_list(recent_messages, limit=6, max_chars=220)
    prev_summary = str(out.get("one_sentence_summary") or "").strip()
    prev_one_thing = str(out.get("if_you_do_one_thing") or "").strip()
    if prev_summary:
        recent_for_pick.insert(0, prev_summary[:220])
    if prev_one_thing:
        recent_for_pick.insert(0, prev_one_thing[:220])
    recent_for_pick = _normalize_short_text_list(recent_for_pick, limit=8, max_chars=220)

    tone = _normalize_daily_tone_id(
        out.get("tone_used")
        or out.get("tone_requested")
        or (norm_payload.get("tone_preference") if isinstance(norm_payload, dict) else "")
        or "supportive"
    )
    classifier = _classify_coach_bottleneck(norm_payload if isinstance(norm_payload, dict) else {})
    bottleneck_label = str(classifier.get("bottleneck") or "consistency").replace("_", " ")
    summary_fact = str(classifier.get("summary") or "").strip() or "Consistency is the top lever for today."
    impact = str(classifier.get("impact") or "").strip() or "This pattern can slow progress if repeated."
    one_change = str(classifier.get("one_change") or "").strip() or "Keep the next meal protein + fiber focused."

    seed = _coach_variation_seed(user_id, day_iso, scan_id, scan_count)
    fmt = {
        "summary_fact": summary_fact,
        "impact": impact,
        "one_change": one_change,
        "bottleneck_label": bottleneck_label,
    }
    summary_line = _pick_style_line(
        _COACH_SUMMARY_STYLE_BANK.get(tone, _COACH_SUMMARY_STYLE_BANK["supportive"]),
        f"{seed}:summary:{tone}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        summary_fact,
        max_words=28,
    )
    why_line = _pick_style_line(
        _COACH_WHY_STYLE_BANK.get(tone, _COACH_WHY_STYLE_BANK["supportive"]),
        f"{seed}:why:{tone}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        impact,
        max_words=30,
    )
    one_action_line = _pick_style_line(
        _COACH_ACTION_STYLE_BANK.get(tone, _COACH_ACTION_STYLE_BANK["supportive"]),
        f"{seed}:action:{tone}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        one_change,
        max_words=24,
    )
    if prev_summary and _is_repetitive_line(summary_line, [prev_summary], threshold=0.86):
        summary_line = _pick_style_line(
            _COACH_SUMMARY_STYLE_BANK.get(tone, _COACH_SUMMARY_STYLE_BANK["supportive"]),
            f"{seed}:summary:reroll:{tone}:{bottleneck_label}",
            fmt,
            [prev_summary],
            summary_fact,
            max_words=28,
        )
    if prev_one_thing and _is_repetitive_line(one_action_line, [prev_one_thing], threshold=0.86):
        one_action_line = _pick_style_line(
            _COACH_ACTION_STYLE_BANK.get(tone, _COACH_ACTION_STYLE_BANK["supportive"]),
            f"{seed}:action:reroll:{tone}:{bottleneck_label}",
            fmt,
            [prev_one_thing],
            one_change,
            max_words=24,
        )

    out["one_sentence_summary"] = summary_line
    out["if_you_do_one_thing"] = one_action_line

    out["coach_summary"] = out["one_sentence_summary"]
    out["why_it_matters"] = why_line
    out["one_action"] = out["if_you_do_one_thing"]
    out["variation_seed"] = seed
    out["summary_signature"] = hashlib.sha256(
        f"{str(out.get('coach_summary') or '')}|{seed}|{tone}".encode("utf-8")
    ).hexdigest()[:20]
    return out


def _apply_daily_coach_tone(resp: Dict[str, Any], tone_preference: str) -> Dict[str, Any]:
    out = dict(resp or {})
    tone = _normalize_daily_tone_id(tone_preference)
    out["tone_requested"] = tone
    out["tone_used"] = tone
    out["tone_tag"] = _normalize_tone_tag(out.get("tone_tag"), fallback=_DAILY_TONE_TAG_MAP.get(tone, "neutral"))

    summary = str(out.get("one_sentence_summary") or "").strip()
    pattern = str(out.get("pattern_detected") or "").strip()
    one_thing = str(out.get("if_you_do_one_thing") or "").strip()
    roi = out.get("highest_roi_change") if isinstance(out.get("highest_roi_change"), dict) else {}
    actions = out.get("actions") if isinstance(out.get("actions"), list) else []

    if tone == "strict":
        if summary:
            if "fix this today" not in summary.lower():
                summary = f"{summary.rstrip('.')} Fix this today."
        else:
            summary = "Fix the top bottleneck today to stabilize hunger and recovery."
        if pattern and "if unchanged" not in pattern.lower():
            pattern = f"{pattern.rstrip('.')} If unchanged, recovery and appetite control will stall."
        if one_thing and not one_thing.lower().startswith("do this today"):
            one_thing = f"Do this today: {one_thing.rstrip('.')}"
        elif not one_thing:
            one_thing = "Do this today: front-load protein and fiber before dinner."
        if isinstance(roi, dict):
            title = str(roi.get("title") or "").strip()
            if title and not title.lower().startswith("non-negotiable"):
                roi["title"] = f"Non-negotiable: {title}"
        toned_actions = []
        for a in actions[:3]:
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip() or "Do this"
            if not title.lower().startswith(("do this", "non-negotiable")):
                title = f"Do this today: {title}"
            why = str(a.get("why") or "").strip()
            if why and "if unchanged" not in why.lower():
                why = f"{why.rstrip('.')} If unchanged, progress slows."
            toned_actions.append({"title": title, "why": why, "how": str(a.get("how") or "").strip()})
        if toned_actions:
            out["actions"] = toned_actions

    elif tone == "funny":
        if summary:
            if "plot twist" not in summary.lower():
                summary = f"Plot twist: {summary.rstrip('.')} 😄"
        else:
            summary = "Plot twist: one small food swap can boost your score today 😄"
        if pattern and "side quest" not in pattern.lower():
            pattern = f"{pattern.rstrip('.')} Cravings are on a side quest right now."
        if one_thing and "cheat code" not in one_thing.lower():
            one_thing = f"Cheat code: {one_thing.rstrip('.')}"
        elif not one_thing:
            one_thing = "Cheat code: add one protein anchor plus one fiber booster before dinner."
        if isinstance(roi, dict):
            title = str(roi.get("title") or "").strip()
            if title and not title.lower().startswith(("cheat code", "boss move")):
                roi["title"] = f"Boss move: {title}"
        toned_actions = []
        for idx, a in enumerate(actions[:3]):
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip() or "Quick upgrade"
            if idx == 0 and not title.lower().startswith(("cheat code", "boss move")):
                title = f"Cheat code: {title}"
            toned_actions.append(
                {
                    "title": title,
                    "why": str(a.get("why") or "").strip(),
                    "how": str(a.get("how") or "").strip(),
                }
            )
        if toned_actions:
            out["actions"] = toned_actions

    elif tone == "indian_coach":
        if summary and not any(k in summary.lower() for k in ("scene", "chalo", "boss", "bhai")):
            summary = f"Scene simple hai: {summary.rstrip('.')} Boss, yeh fix karte hain."
        elif not summary:
            summary = "Scene simple hai: protein + fiber ko anchor karo, progress sorted rahega."
        if one_thing and "chalo" not in one_thing.lower():
            one_thing = f"Chalo, next meal fix: {one_thing.rstrip('.')}"
        elif not one_thing:
            one_thing = "Chalo, next meal fix: dal/curd/paneer/tofu ke saath fiber add karo."
        if isinstance(roi, dict):
            title = str(roi.get("title") or "").strip()
            if title and not any(k in title.lower() for k in ("scene", "boss", "anchor")):
                roi["title"] = f"Boss move: {title}"
        toned_actions = []
        for a in actions[:3]:
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip() or "Anchor meal move"
            why = str(a.get("why") or "").strip()
            how = str(a.get("how") or "").strip()
            if "chalo" not in how.lower():
                how = f"Chalo: {how}".strip()
            toned_actions.append({"title": title, "why": why, "how": how})
        if toned_actions:
            out["actions"] = toned_actions

    elif tone == "supportive":
        if summary and not summary.lower().startswith(("good effort", "you are doing")):
            summary = f"Good effort today. {summary}"
        elif not summary:
            summary = "Good effort today. A small protein and fiber shift can improve your direction."
        if one_thing and not one_thing.lower().startswith(("small win", "next easy step")):
            one_thing = f"Small win: {one_thing.rstrip('.')}"
        elif not one_thing:
            one_thing = "Small win: add one protein anchor and one fiber source before dinner."
        if isinstance(roi, dict):
            title = str(roi.get("title") or "").strip()
            if title and not title.lower().startswith(("easy win", "small win")):
                roi["title"] = f"Easy win: {title}"
        toned_actions = []
        for a in actions[:3]:
            if not isinstance(a, dict):
                continue
            title = str(a.get("title") or "").strip() or "Easy upgrade"
            if not title.lower().startswith(("easy", "small")):
                title = f"Easy upgrade: {title}"
            toned_actions.append({"title": title, "why": str(a.get("why") or "").strip(), "how": str(a.get("how") or "").strip()})
        if toned_actions:
            out["actions"] = toned_actions

    if isinstance(roi, dict):
        out["highest_roi_change"] = roi
    out["one_sentence_summary"] = _clip_line(summary, max_words=24)
    out["pattern_detected"] = _clip_line(pattern, max_words=30)
    out["if_you_do_one_thing"] = _clip_line(one_thing, max_words=24)
    return out


_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF]")


def _count_emoji(text: str) -> int:
    try:
        return len(_EMOJI_RE.findall(str(text or "")))
    except Exception:
        return 0


def _tone_copy_checks(rewrite_out: Dict[str, Any], tone_id: str) -> Dict[str, Any]:
    tone = _normalize_daily_tone_id(tone_id)
    rules = _DAILY_TONE_PACK.get(tone, _DAILY_TONE_PACK["supportive"])
    summary = str(rewrite_out.get("coach_summary") or "")
    diag = rewrite_out.get("diagnosis") if isinstance(rewrite_out.get("diagnosis"), dict) else {}
    actions = rewrite_out.get("actions") if isinstance(rewrite_out.get("actions"), list) else []
    body_blob = " ".join(
        [
            summary,
            str(diag.get("pattern") or ""),
            str(diag.get("impact") or ""),
            " ".join(
                [
                    f"{str(a.get('title') or '')} {str(a.get('why') or '')} {str(a.get('how') or '')}"
                    for a in actions
                    if isinstance(a, dict)
                ]
            ),
        ]
    ).strip()
    lowered = body_blob.lower()
    banned = [w for w in (rules.get("banned_words") or []) if str(w).strip() and str(w).lower() in lowered][:10]
    signature = any(str(x).lower() in lowered for x in (rules.get("signature_phrases") or []))
    must_include = rules.get("must_include_any") or []
    must_hit = True if not must_include else any(str(x).lower() in lowered for x in must_include)
    emoji_count = _count_emoji(body_blob)
    emoji_max = int(_safe_float(rules.get("emoji_max"), 1) or 1)
    hinglish_terms = [str(x).lower() for x in (rules.get("hinglish_phrases") or []) if str(x).strip()]
    hinglish_hits = sum(1 for x in hinglish_terms if x in lowered)
    hinglish_min = int(_safe_float(rules.get("hinglish_min"), 0) or 0)
    hinglish_max = int(_safe_float(rules.get("hinglish_max"), 5) or 5)

    constraints_passed = (
        len(banned) == 0
        and emoji_count <= emoji_max
        and must_hit
        and hinglish_hits >= hinglish_min
        and hinglish_hits <= hinglish_max
    )
    notes = []
    if banned:
        notes.append("banned_word")
    if emoji_count > emoji_max:
        notes.append("emoji_limit")
    if not must_hit:
        notes.append("signature_missing")
    if hinglish_hits < hinglish_min or hinglish_hits > hinglish_max:
        notes.append("hinglish_limit")

    return {
        "emoji_count": int(emoji_count),
        "hinglish_phrase_count": int(hinglish_hits),
        "signature_phrase_used": bool(signature),
        "banned_words_found": banned,
        "constraints_passed": bool(constraints_passed),
        "notes": ",".join(notes)[:250],
    }


def _tone_rewrite_fallback(
    input_payload: Dict[str, Any],
    tone_id: str,
    freshness: str,
    max_actions: int,
) -> Dict[str, Any]:
    tone = _normalize_daily_tone_id(tone_id)
    base_actions = input_payload.get("actions") if isinstance(input_payload.get("actions"), list) else []
    fallback_resp = {
        "one_sentence_summary": str(input_payload.get("coach_summary") or ""),
        "pattern_detected": str((input_payload.get("diagnosis") or {}).get("pattern") or ""),
        "if_you_do_one_thing": str(input_payload.get("one_change") or ""),
        "highest_roi_change": (
            base_actions[0]
            if base_actions and isinstance(base_actions[0], dict)
            else {"title": "Top action", "why": str(input_payload.get("impact") or ""), "how": str(input_payload.get("one_change") or "")}
        ),
        "actions": base_actions[: max(1, min(5, int(_safe_float(max_actions, 3) or 3)))],
    }
    toned = _apply_daily_coach_tone(fallback_resp, tone)
    diag = input_payload.get("diagnosis") if isinstance(input_payload.get("diagnosis"), dict) else {}
    rewrite_out = {
        "tone_id": tone,
        "source": "rules_fallback_rewrite",
        "freshness": freshness if freshness in {"updated_now", "updating", "stale_cache"} else "updated_now",
        "coach_summary": _clip_line(toned.get("one_sentence_summary"), max_words=32),
        "diagnosis": {
            "pattern": _clip_line(diag.get("pattern") or toned.get("pattern_detected") or "Pattern needs confirmation.", max_words=36),
            "impact": _clip_line(diag.get("impact") or input_payload.get("impact") or "This pattern can reduce consistency.", max_words=36),
        },
        "actions": [
            {
                "title": _clip_line(a.get("title"), max_words=10) or "Next step",
                "why": _clip_line(a.get("why"), max_words=26) or "Helps consistency.",
                "how": _clip_line(a.get("how"), max_words=26) or _clip_line(toned.get("if_you_do_one_thing"), max_words=26),
            }
            for a in (toned.get("actions") if isinstance(toned.get("actions"), list) else [])[: max(1, min(5, int(_safe_float(max_actions, 3) or 3)))]
            if isinstance(a, dict)
        ],
        "clarifying_question": input_payload.get("clarifying_question")
        if isinstance(input_payload.get("clarifying_question"), dict)
        else None,
        "microcopy": {
            "updating_text": "Updating insights..." if tone != "indian_coach" else "Insights update ho rahe hain...",
            "updated_text": "Updated just now" if tone != "indian_coach" else "Abhi abhi update hua",
        },
        "copy_checks": {},
    }
    rewrite_out["copy_checks"] = _tone_copy_checks(rewrite_out, tone)
    return rewrite_out


def rewrite_coach_tone(
    input_payload: Dict[str, Any],
    tone_id: str,
    *,
    locale: str = "en-AU",
    user_goal: str = "fat_loss",
    coach_mode: str = "daily_summary",
    freshness: str = "updated_now",
    max_chars: int = 650,
    max_actions: int = 3,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    tone = _normalize_daily_tone_id(tone_id)
    fallback = _tone_rewrite_fallback(input_payload, tone, freshness, max_actions)
    if (not allow_llm) or (not GEMINI_API_KEY):
        return fallback

    schema_hint = {
        "tone_id": "supportive|strict|funny|indian_coach",
        "source": "llm_rewrite|rules_fallback_rewrite",
        "freshness": "updated_now|updating|stale_cache",
        "coach_summary": "string",
        "diagnosis": {"pattern": "string", "impact": "string"},
        "actions": [{"title": "string", "why": "string", "how": "string"}],
        "clarifying_question": {"ask": "string", "options": ["string"]} or None,
        "microcopy": {"updating_text": "string", "updated_text": "string"},
        "copy_checks": {
            "emoji_count": 0,
            "hinglish_phrase_count": 0,
            "signature_phrase_used": True,
            "banned_words_found": [],
            "constraints_passed": True,
            "notes": "",
        },
    }
    user_prompt = (
        f"TONE_PACK (JSON):\n{json.dumps(_DAILY_TONE_PACK.get(tone, {}), ensure_ascii=True)}\n\n"
        "REQUEST:\n"
        f'tone_id: "{tone}"\n'
        f'locale: "{str(locale or "en-AU").strip() or "en-AU"}"\n'
        f'user_goal: "{str(user_goal or "fat_loss").strip() or "fat_loss"}"\n'
        f'coach_mode: "{str(coach_mode or "daily_summary").strip() or "daily_summary"}"\n'
        f'freshness: "{str(freshness or "updated_now").strip() or "updated_now"}"\n'
        f"constraints:\n  max_chars: {int(max(220, min(1800, _safe_float(max_chars, 650) or 650)))}\n"
        f"  max_actions: {int(max(1, min(5, _safe_float(max_actions, 3) or 3)))}\n\n"
        f"INPUT_PAYLOAD (JSON):\n{json.dumps(input_payload, ensure_ascii=True)}\n\n"
        f"OUTPUT_SCHEMA (JSON Schema):\n{json.dumps(schema_hint, ensure_ascii=True)}\n"
        "Rewrite content into requested tone. Return ONLY JSON."
    )
    try:
        txt, model_name, tried_models = _call_llm_with_timeout(
            [_COACH_TONE_REWRITE_SYSTEM_PROMPT, user_prompt],
            model_name=COACH_LLM_MODEL,
            timeout_sec=min(_llm_timeout(limit=10.0), 8.0),
            retries=1,
            purpose="tone_rewrite",
        )
        parsed = coach_logic.extract_json_object(txt)
        if not isinstance(parsed, dict):
            raise ValueError("tone rewrite non-json")
        parsed["tone_id"] = _normalize_daily_tone_id(parsed.get("tone_id") or tone)
        parsed["source"] = "llm_rewrite"
        parsed["freshness"] = str(parsed.get("freshness") or freshness).strip().lower()
        if parsed["freshness"] not in {"updated_now", "updating", "stale_cache"}:
            parsed["freshness"] = freshness if freshness in {"updated_now", "updating", "stale_cache"} else "updated_now"
        if not isinstance(parsed.get("microcopy"), dict):
            parsed["microcopy"] = fallback["microcopy"]
        if not isinstance(parsed.get("actions"), list):
            parsed["actions"] = fallback["actions"]
        parsed["actions"] = [a for a in parsed.get("actions", []) if isinstance(a, dict)][: max(1, min(5, int(max_actions or 3)))]
        if not parsed["actions"]:
            parsed["actions"] = fallback["actions"][:1]
        parsed["copy_checks"] = _tone_copy_checks(parsed, parsed["tone_id"])
        obj = _model_validate(CoachToneRewriteV1Model, parsed)
        out = _model_dump(obj)
        checks = _tone_copy_checks(out, out.get("tone_id"))
        out["copy_checks"] = checks
        if not checks.get("constraints_passed"):
            raise ValueError(f"tone rewrite constraints failed: {checks.get('notes')}")
        out["_llm_model_used"] = model_name
        return out
    except Exception as e:
        logger.info("tone rewrite fallback used: %s", str(e)[:200])
        return fallback


def _classify_coach_bottleneck(norm_payload: Dict[str, Any]) -> Dict[str, str]:
    goals = (norm_payload.get("goals") or {}) if isinstance(norm_payload.get("goals"), dict) else {}
    consumed = (norm_payload.get("consumed") or {}) if isinstance(norm_payload.get("consumed"), dict) else {}
    signals = (norm_payload.get("signals") or {}) if isinstance(norm_payload.get("signals"), dict) else {}
    timing = (norm_payload.get("meal_timing") or {}) if isinstance(norm_payload.get("meal_timing"), dict) else {}

    pg = max(0.0, _safe_float(goals.get("protein_g"), 0.0) - _safe_float(consumed.get("protein_g"), 0.0))
    fg = max(0.0, _safe_float(goals.get("fiber_g"), 0.0) - _safe_float(consumed.get("fiber_g"), 0.0))
    gl = max(0.0, _safe_float(signals.get("avg_glycemic_load"), 0.0))
    upf = max(0.0, _safe_float(signals.get("ultra_processed_avg"), 0.0))
    late = max(0.0, _safe_float(timing.get("late_calories_pct"), 0.0))

    scores = [
        ("protein", pg / max(1.0, _safe_float(goals.get("protein_g"), 1.0))),
        ("fiber", fg / max(1.0, _safe_float(goals.get("fiber_g"), 1.0))),
        ("glycemic", gl / 35.0),
        ("upf", upf / 10.0),
        ("timing", late / 100.0),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    bottleneck = scores[0][0] if scores else "protein"

    if bottleneck == "protein":
        return {
            "bottleneck": "protein",
            "pattern": f"Protein remains short by about {round(pg, 1)}g versus target.",
            "impact": "Lower protein consistency can weaken recovery and satiety control later in the day.",
            "one_change": "Add one protein anchor at your next meal and repeat at lunch/dinner.",
            "summary": f"Protein gap is about {round(pg, 1)}g, which is currently the main limiter.",
        }
    if bottleneck == "fiber":
        return {
            "bottleneck": "fiber",
            "pattern": f"Fiber remains short by about {round(fg, 1)}g versus target.",
            "impact": "Low fiber can increase hunger volatility and reduce meal satisfaction.",
            "one_change": "Add one fiber booster (vegetables, beans, fruit) with your next main meal.",
            "summary": f"Fiber gap is about {round(fg, 1)}g, which is limiting satiety quality today.",
        }
    if bottleneck == "upf":
        return {
            "bottleneck": "ultra_processed",
            "pattern": f"Ultra-processed load is elevated at about {round(upf, 1)}/10.",
            "impact": "Higher UPF exposure can reduce satiety stability and increase snacking risk.",
            "one_change": "Replace one packaged snack or refined meal with a whole-food alternative today.",
            "summary": f"Whole-food quality is the top lever now (UPF ~{round(upf, 1)}/10).",
        }
    if bottleneck == "glycemic":
        return {
            "bottleneck": "glycemic_load",
            "pattern": f"Average glycemic load is elevated around {round(gl, 1)}.",
            "impact": "High glycemic swings can drive rebound hunger and inconsistent energy.",
            "one_change": "Pair fast carbs with protein and fiber to flatten glucose swings in the next meal.",
            "summary": f"Glycemic control is the main friction point (GL ~{round(gl, 1)}).",
        }
    return {
        "bottleneck": "timing",
        "pattern": f"Late calories remain high at about {round(late, 1)}% of daily intake.",
        "impact": "Back-loaded calories can worsen appetite control the following morning.",
        "one_change": "Shift 200-300 kcal earlier with a protein-forward snack before evening.",
        "summary": f"Timing balance is the main lever right now (late calories ~{round(late, 1)}%).",
    }


def _coach_rewrite_freshness_from_payload(coach_resp: Dict[str, Any], default: str = "updated_now") -> str:
    f = str(coach_resp.get("tone_rewrite_freshness") or coach_resp.get("fli_status") or "").strip().lower()
    if f in {"updated_now", "updating", "stale_cache"}:
        return f
    if str(coach_resp.get("reasoning_source") or "").strip().lower() == "cached_llm":
        return "stale_cache"
    stale_sec = int(_safe_float(coach_resp.get("fli_stale_seconds"), 0) or 0)
    if stale_sec >= 60:
        return "stale_cache"
    if str(coach_resp.get("fli_status") or "").strip().lower() in {"pending", "updating"}:
        return "updating"
    return default if default in {"updated_now", "updating", "stale_cache"} else "updated_now"


def _build_tone_rewrite_input_payload(
    coach_resp: Dict[str, Any],
    norm_payload: Dict[str, Any],
    *,
    freshness: str,
) -> Dict[str, Any]:
    out = dict(coach_resp or {})
    goals = (norm_payload.get("goals") or {}) if isinstance(norm_payload.get("goals"), dict) else {}
    consumed = (norm_payload.get("consumed") or {}) if isinstance(norm_payload.get("consumed"), dict) else {}
    profile = (norm_payload.get("profile") or {}) if isinstance(norm_payload.get("profile"), dict) else {}
    classifier = _classify_coach_bottleneck(norm_payload)

    diag = {
        "pattern": str(out.get("pattern_detected") or classifier["pattern"]).strip() or classifier["pattern"],
        "impact": str((out.get("biggest_risk_lever") or {}).get("reason") or out.get("projection_explained") or classifier["impact"]).strip()
        or classifier["impact"],
    }
    summary_raw = str(out.get("one_sentence_summary") or "").strip()
    if (not summary_raw) or ("key levers for your 7-day direction" in summary_raw.lower()):
        summary_raw = classifier["summary"]
    one_change = str(out.get("if_you_do_one_thing") or "").strip() or classifier["one_change"]
    actions = out.get("actions") if isinstance(out.get("actions"), list) else []
    if not actions:
        actions = [
            {
                "title": "Top action",
                "why": classifier["impact"],
                "how": one_change,
            }
        ]

    return {
        "bottleneck": classifier["bottleneck"],
        "goal_type": str(profile.get("goal_type") or "fat_loss"),
        "goals": {
            "kcal": round(_safe_float(goals.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(goals.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(goals.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(goals.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(goals.get("fiber_g"), 0.0), 1),
        },
        "consumed": {
            "kcal": round(_safe_float(consumed.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(consumed.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(consumed.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(consumed.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(consumed.get("fiber_g"), 0.0), 1),
        },
        "pattern": diag["pattern"],
        "impact": diag["impact"],
        "one_change": one_change,
        "actions": actions,
        "uncertainty": {
            "needs_clarification": bool(str(freshness) == "updating"),
            "reason": "New scan detected; reconciling latest signals." if str(freshness) == "updating" else "",
        },
        "clarifying_question": out.get("clarifying_question") if isinstance(out.get("clarifying_question"), dict) else None,
        "coach_summary": summary_raw,
        "diagnosis": diag,
    }


def _apply_tone_rewrite_to_coach_response(
    coach_resp: Dict[str, Any],
    norm_payload: Dict[str, Any],
    *,
    tone_id: str,
    freshness: str,
    max_actions: int,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    out = dict(coach_resp or {})
    rewrite_in = _build_tone_rewrite_input_payload(out, norm_payload, freshness=freshness)
    rewritten = rewrite_coach_tone(
        rewrite_in,
        tone_id=tone_id,
        locale="en-AU",
        user_goal=str((norm_payload.get("profile") or {}).get("goal_type") or "fat_loss"),
        coach_mode="daily_summary",
        freshness=freshness,
        max_chars=650,
        max_actions=max_actions,
        allow_llm=allow_llm,
    )
    out["one_sentence_summary"] = _clip_line(rewritten.get("coach_summary"), max_words=28)
    diagnosis = rewritten.get("diagnosis") if isinstance(rewritten.get("diagnosis"), dict) else {}
    out["pattern_detected"] = _clip_line(diagnosis.get("pattern") or out.get("pattern_detected"), max_words=32)
    actions = rewritten.get("actions") if isinstance(rewritten.get("actions"), list) else []
    actions = [a for a in actions if isinstance(a, dict)][: max(1, min(5, int(max_actions or 3)))]
    if actions:
        out["actions"] = [
            {
                "title": str(a.get("title") or "").strip(),
                "why": str(a.get("why") or "").strip(),
                "how": str(a.get("how") or "").strip(),
            }
            for a in actions
            if str(a.get("title") or "").strip() and str(a.get("how") or "").strip()
        ]
    if out.get("actions"):
        first = out["actions"][0]
        out["highest_roi_change"] = {
            "title": str(first.get("title") or "").strip(),
            "why": str(first.get("why") or "").strip(),
            "how": str(first.get("how") or "").strip(),
        }
        out["if_you_do_one_thing"] = _clip_line(first.get("how"), max_words=24)
    if isinstance(rewritten.get("clarifying_question"), dict):
        out["clarifying_question"] = rewritten["clarifying_question"]
    out["tone_requested"] = _normalize_daily_tone_id(tone_id)
    out["tone_used"] = _normalize_daily_tone_id(rewritten.get("tone_id") or tone_id)
    out["tone_tag"] = _normalize_tone_tag(out.get("tone_tag"), fallback=_DAILY_TONE_TAG_MAP.get(out["tone_used"], "neutral"))
    out["microcopy"] = rewritten.get("microcopy") if isinstance(rewritten.get("microcopy"), dict) else {
        "updating_text": "Updating insights...",
        "updated_text": "Updated just now",
    }
    out["copy_checks"] = rewritten.get("copy_checks") if isinstance(rewritten.get("copy_checks"), dict) else _tone_copy_checks(rewritten, out["tone_used"])
    out["tone_rewrite_source"] = str(rewritten.get("source") or "rules_fallback_rewrite")
    out["tone_rewrite_freshness"] = str(rewritten.get("freshness") or freshness)
    return out


def _voice_cache_key(user_id: str, day_iso: str, payload_hash: str, tone_preference: str) -> str:
    return f"{str(user_id or '').strip()}:{_safe_day_iso(day_iso)}:{str(payload_hash or '').strip()}:{_normalize_tone_preference(tone_preference)}"


def _coach_voice_cache_get(user_id: str, day_iso: str, payload_hash: str, tone_preference: str) -> Optional[Dict[str, Any]]:
    key = _voice_cache_key(user_id, day_iso, payload_hash, tone_preference)
    now = _now_utc_naive()

    mem = _COACH_VOICE_CACHE_MEM.get(key)
    if isinstance(mem, dict):
        exp = _parse_iso_dt_naive(mem.get("expires_at"))
        if exp and exp > now and isinstance(mem.get("response"), dict):
            return dict(mem.get("response"))

    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_VOICE_CACHE):
        return None
    try:
        row = sb_get_one(
            TBL_COACH_VOICE_CACHE,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{_safe_day_iso(day_iso)}",
                "payload_hash": f"eq.{str(payload_hash or '').strip()}",
                "tone_preference": f"eq.{_normalize_tone_preference(tone_preference)}",
                "order": "updated_at.desc",
                "limit": "1",
            },
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_VOICE_CACHE, e):
            logger.info(f"coach voice cache read skipped: {e}")
        return None
    if not row:
        return None
    exp = _parse_iso_dt_naive(row.get("expires_at"))
    if not exp or exp <= now:
        return None

    resp = _parse_jsonish(row.get("response_json"), None)
    if not isinstance(resp, dict):
        return None
    _COACH_VOICE_CACHE_MEM[key] = {
        "expires_at": str(row.get("expires_at") or ""),
        "response": dict(resp),
    }
    return dict(resp)


def _coach_voice_cache_set(
    user_id: str,
    day_iso: str,
    payload_hash: str,
    tone_preference: str,
    response_payload: Dict[str, Any],
) -> None:
    key = _voice_cache_key(user_id, day_iso, payload_hash, tone_preference)
    now_iso = _now_utc_naive().isoformat()
    expires_at = (_now_utc_naive() + dt.timedelta(minutes=COACH_VOICE_CACHE_TTL_MIN)).isoformat()
    resp = dict(response_payload or {})
    _COACH_VOICE_CACHE_MEM[key] = {
        "expires_at": expires_at,
        "response": resp,
    }

    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_VOICE_CACHE):
        return
    row = {
        "user_id": str(user_id or "").strip(),
        "day": _safe_day_iso(day_iso),
        "payload_hash": str(payload_hash or "").strip(),
        "tone_preference": _normalize_tone_preference(tone_preference),
        "response_json": resp,
        "coach_generated_ts": str(resp.get("coach_generated_ts") or now_iso),
        "advice_key": str(resp.get("advice_key") or ""),
        "expires_at": expires_at,
        "updated_at": now_iso,
    }
    try:
        existing = sb_get_one(
            TBL_COACH_VOICE_CACHE,
            params={
                "select": "*",
                "user_id": f"eq.{row['user_id']}",
                "day": f"eq.{row['day']}",
                "payload_hash": f"eq.{row['payload_hash']}",
                "tone_preference": f"eq.{row['tone_preference']}",
                "limit": "1",
            },
        )
        if existing:
            patch = {k: v for k, v in row.items() if k not in {"user_id", "day", "payload_hash", "tone_preference"}}
            _sb_patch_with_column_fallback(
                TBL_COACH_VOICE_CACHE,
                {
                    "user_id": f"eq.{row['user_id']}",
                    "day": f"eq.{row['day']}",
                    "payload_hash": f"eq.{row['payload_hash']}",
                    "tone_preference": f"eq.{row['tone_preference']}",
                },
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_COACH_VOICE_CACHE,
                row,
                locked_cols={"user_id", "day", "payload_hash", "tone_preference"},
            )
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_VOICE_CACHE, e):
            logger.info(f"coach voice cache write skipped: {e}")


def _weekly_report_cache_key(user_id: str, week_start_iso: str, payload_hash: str) -> str:
    return f"{str(user_id or '').strip()}:{str(week_start_iso or '').strip()}:{str(payload_hash or '').strip()}"


def _weekly_report_cache_get(user_id: str, week_start_iso: str, payload_hash: str) -> Optional[Dict[str, Any]]:
    key = _weekly_report_cache_key(user_id, week_start_iso, payload_hash)
    mem = _WEEKLY_REPORT_CACHE_MEM.get(key)
    if isinstance(mem, dict):
        return dict(mem)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        row = sb_get_one(
            TBL_WEEKLY_REPORTS,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "week_start": f"eq.{week_start_iso}",
                "payload_hash": f"eq.{payload_hash}",
                "limit": "1",
            },
        )
    except Exception as e:
        logger.info(f"weekly report cache read skipped: {e}")
        return None
    if not row:
        return None
    payload = _parse_jsonish(row.get("report_json"), None)
    if not isinstance(payload, dict):
        return None
    _WEEKLY_REPORT_CACHE_MEM[key] = dict(payload)
    return dict(payload)


def _weekly_report_cache_set(user_id: str, week_start_iso: str, payload_hash: str, report: Dict[str, Any]) -> None:
    key = _weekly_report_cache_key(user_id, week_start_iso, payload_hash)
    payload = dict(report or {})
    _WEEKLY_REPORT_CACHE_MEM[key] = payload
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    row = {
        "user_id": str(user_id or "").strip(),
        "week_start": str(week_start_iso or "").strip(),
        "payload_hash": str(payload_hash or "").strip(),
        "report_json": payload,
        "updated_at": _now_utc_naive().isoformat(),
    }
    try:
        existing = sb_get_one(
            TBL_WEEKLY_REPORTS,
            params={
                "select": "*",
                "user_id": f"eq.{row['user_id']}",
                "week_start": f"eq.{row['week_start']}",
                "payload_hash": f"eq.{row['payload_hash']}",
                "limit": "1",
            },
        )
        if existing:
            patch = {k: v for k, v in row.items() if k not in {"user_id", "week_start", "payload_hash"}}
            _sb_patch_with_column_fallback(
                TBL_WEEKLY_REPORTS,
                {
                    "user_id": f"eq.{row['user_id']}",
                    "week_start": f"eq.{row['week_start']}",
                    "payload_hash": f"eq.{row['payload_hash']}",
                },
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_WEEKLY_REPORTS,
                row,
                locked_cols={"user_id", "week_start", "payload_hash"},
            )
    except Exception as e:
        raw = _http_exc_raw(e)
        if _is_duplicate_key_error(raw):
            # Handle race: two concurrent inserts for same PK.
            try:
                patch = {k: v for k, v in row.items() if k not in {"user_id", "week_start", "payload_hash"}}
                _sb_patch_with_column_fallback(
                    TBL_WEEKLY_REPORTS,
                    {
                        "user_id": f"eq.{row['user_id']}",
                        "week_start": f"eq.{row['week_start']}",
                        "payload_hash": f"eq.{row['payload_hash']}",
                    },
                    patch,
                )
                return
            except Exception as e2:
                logger.info(f"weekly report cache duplicate insert recovery failed: {e2}")
                return
        logger.info(f"weekly report cache write skipped: {e}")


def _feedback_type_normalize(v: Any) -> str:
    t = str(v or "overall").strip().lower()
    if t not in {"accuracy", "portion", "cooking", "oil", "ingredients", "overall"}:
        return "overall"
    return t


def _food_token(name: Any) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64]


def _blend_avg(old_avg: float, old_n: int, new_val: float) -> float:
    if old_n <= 0:
        return float(new_val)
    return ((old_avg * old_n) + new_val) / float(old_n + 1)


def _method_norm(v: Any) -> str:
    return _food_token(v).replace("_", " ")


def _extract_prior_count(row: Dict[str, Any], *keys: str) -> int:
    for k in keys:
        if k in (row or {}) and row.get(k) is not None:
            return int(_safe_float(row.get(k), 0) or 0)
    return 0


def _extract_prior_float(row: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in (row or {}) and row.get(k) is not None:
            return float(_safe_float(row.get(k), default) or default)
    return float(default)


def _extract_oil_by_method(row: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    src = _parse_jsonish((row or {}).get("oil_by_method"), {})
    if not isinstance(src, dict):
        src = {}
    out: Dict[str, Dict[str, float]] = {}
    for mk, mv in src.items():
        key = _food_token(mk).replace("_", " ")
        if not key:
            continue
        if isinstance(mv, dict):
            out[key] = {
                "mean": round(float(_safe_float(mv.get("mean"), 0.0) or 0.0), 4),
                "n": int(_safe_float(mv.get("n"), 0) or 0),
            }
    return out


def _extract_always_ask_methods(row: Dict[str, Any]) -> List[str]:
    arr = _parse_jsonish((row or {}).get("always_ask_oil_for_methods"), [])
    out: List[str] = []
    seen = set()
    if isinstance(arr, list):
        for x in arr:
            m = _food_token(x).replace("_", " ")
            if m and m not in seen:
                seen.add(m)
                out.append(m)
    if bool((row or {}).get("always_ask_clarifying")) and "pan fried" not in seen:
        out.append("pan fried")
    return out


def _row_food_key(row: Dict[str, Any]) -> str:
    return _food_token((row or {}).get("food_key") or (row or {}).get("food_token"))


def _read_user_food_prior(user_id: str, food_token: str) -> Optional[Dict[str, Any]]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    token = _food_token(food_token)
    if not token:
        return None
    try:
        return sb_get_one(
            TBL_USER_FOOD_PRIORS,
            params={"select": "*", "user_id": f"eq.{user_id}", "food_key": f"eq.{token}", "limit": "1"},
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_USER_FOOD_PRIORS, e):
            logger.info(f"user food prior read skipped: {e}")
        return None


def _list_user_food_priors(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return []
    try:
        rows = sb_get_many(
            TBL_USER_FOOD_PRIORS,
            params={"select": "*", "user_id": f"eq.{user_id}", "order": "updated_at.desc", "limit": str(max(1, min(200, limit)))},
        )
        return rows if isinstance(rows, list) else []
    except Exception as e:
        if not _mark_table_unavailable(TBL_USER_FOOD_PRIORS, e):
            logger.info(f"user priors list skipped: {e}")
        return []


def _recent_oil_corrections_for_method(user_id: str, method: str, food_key: str) -> int:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return 0
    rows: List[Dict[str, Any]] = []
    try:
        rows = sb_get_many(
            TBL_COACH_FEEDBACK,
            params={
                "select": "corrections_json,corrections,feedback_type,created_at",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": "30",
            },
        )
    except Exception as e:
        logger.info(f"feedback history read skipped: {e}")
        return 0
    method_norm = _method_norm(method)
    key_norm = _food_token(food_key)
    checked = 0
    matched = 0
    for row in (rows or []):
        if checked >= 10:
            break
        checked += 1
        corr = _parse_jsonish(row.get("corrections_json"), None)
        if not isinstance(corr, dict):
            corr = _parse_jsonish(row.get("corrections"), {})
        if not isinstance(corr, dict):
            continue
        corr_key = _food_token(corr.get("food_key") or corr.get("item_name") or corr.get("food_token"))
        if key_norm and corr_key and corr_key != key_norm:
            continue
        corr_method = _method_norm(corr.get("cooking_method"))
        oil = _safe_float(corr.get("oil_added_tsp"), None)
        if corr_method == method_norm and oil is not None:
            matched += 1
    return matched


def _build_food_prior_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    oil_by_method = _extract_oil_by_method(row)
    return {
        "portion_multiplier_mean": round(_extract_prior_float(row, "portion_multiplier_mean", "portion_multiplier_avg", default=1.0), 4),
        "portion_multiplier_n": int(_extract_prior_count(row, "portion_multiplier_n", "portion_feedback_count")),
        "oil_tsp_mean": round(_extract_prior_float(row, "oil_tsp_mean", "oil_added_tsp_avg", default=0.0), 4),
        "oil_tsp_n": int(_extract_prior_count(row, "oil_tsp_n", "oil_feedback_count")),
        "oil_by_method": oil_by_method,
        "always_ask_oil_for_methods": _extract_always_ask_methods(row),
    }


def _calibration_setting_value(
    settings: Dict[str, Any],
    prediction_type: str,
    key: str,
    fallback: float,
) -> float:
    p = str(prediction_type or "").strip().lower()
    row = (settings or {}).get(p) if isinstance((settings or {}).get(p), dict) else {}
    return float(_safe_float(row.get(key), fallback) or fallback)


def load_confidence_calibration_settings() -> Dict[str, Dict[str, float]]:
    merged: Dict[str, Dict[str, float]] = {
        k: {
            "confidence_threshold": float(v["confidence_threshold"]),
            "range_expansion_factor": float(v["range_expansion_factor"]),
        }
        for k, v in DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS.items()
    }
    if not ENABLE_DYNAMIC_CONFIDENCE_THRESHOLDS:
        return merged
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return merged
    try:
        rows = sb_get_many(
            TBL_CONFIDENCE_CALIBRATION_SETTINGS,
            params={"select": "*", "limit": "32"},
        )
    except Exception as e:
        if not _mark_table_unavailable(TBL_CONFIDENCE_CALIBRATION_SETTINGS, e):
            logger.info(f"confidence calibration settings read skipped: {e}")
        return merged
    # Preferred schema: one row with JSON settings
    for row in (rows or []):
        settings_obj = _parse_jsonish((row or {}).get("settings"), {})
        if isinstance(settings_obj, dict) and settings_obj:
            for p in DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS.keys():
                src = settings_obj.get(p) if isinstance(settings_obj.get(p), dict) else {}
                merged[p] = {
                    "confidence_threshold": float(
                        _safe_float(src.get("confidence_threshold"), merged[p]["confidence_threshold"])
                        or merged[p]["confidence_threshold"]
                    ),
                    "range_expansion_factor": float(
                        _safe_float(src.get("range_expansion_factor"), merged[p]["range_expansion_factor"])
                        or merged[p]["range_expansion_factor"]
                    ),
                }
            return merged
    # Backward compatibility: row-per-prediction_type layout.
    for row in (rows or []):
        p = str((row or {}).get("prediction_type") or "").strip().lower()
        if p not in merged:
            continue
        merged[p] = {
            "confidence_threshold": float(
                _safe_float((row or {}).get("confidence_threshold"), merged[p]["confidence_threshold"])
                or merged[p]["confidence_threshold"]
            ),
            "range_expansion_factor": float(
                _safe_float((row or {}).get("range_expansion_factor"), merged[p]["range_expansion_factor"])
                or merged[p]["range_expansion_factor"]
            ),
        }
    return merged


def _upsert_confidence_calibration_setting(prediction_type: str, confidence_threshold: float, range_expansion_factor: float) -> None:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    p = str(prediction_type or "").strip().lower()
    if p not in DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS:
        return
    row_settings = load_confidence_calibration_settings()
    row_settings[p] = {
        "confidence_threshold": round(float(max(0.5, min(0.98, confidence_threshold))), 4),
        "range_expansion_factor": round(float(max(0.8, min(2.5, range_expansion_factor))), 4),
    }
    row = {
        "user_id": SYSTEM_CALIBRATION_USER_ID,
        "settings": row_settings,
        "updated_at": _now_utc_naive().isoformat(),
    }
    try:
        existing = sb_get_one(
            TBL_CONFIDENCE_CALIBRATION_SETTINGS,
            params={"select": "id,user_id", "user_id": f"eq.{SYSTEM_CALIBRATION_USER_ID}", "order": "updated_at.desc", "limit": "1"},
        )
        if existing:
            _sb_patch_with_column_fallback(
                TBL_CONFIDENCE_CALIBRATION_SETTINGS,
                {"id": f"eq.{existing.get('id')}"},
                {"settings": row["settings"], "updated_at": row["updated_at"]},
                locked_cols={"id"},
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_CONFIDENCE_CALIBRATION_SETTINGS,
                row,
                locked_cols={"user_id"},
            )
    except Exception as e:
        if not _mark_table_unavailable(TBL_CONFIDENCE_CALIBRATION_SETTINGS, e):
            logger.info(f"confidence calibration setting write skipped: {e}")


def _prediction_range(
    prediction_type: str,
    predicted_value: Optional[float],
    settings: Dict[str, Any],
) -> Optional[Dict[str, float]]:
    pv = _safe_float(predicted_value, None)
    if pv is None:
        return None
    p = str(prediction_type or "").strip().lower()
    expand = _calibration_setting_value(settings, p, "range_expansion_factor", 1.0)
    if p == "oil":
        base_half = max(0.5, abs(float(pv)) * 0.30)
    elif p == "portion":
        base_half = max(20.0, abs(float(pv)) * 0.15)
    else:
        base_half = max(0.10, abs(float(pv)) * 0.12)
    half = base_half * max(0.8, min(2.5, expand))
    low = float(pv) - half
    high = float(pv) + half
    if p in {"oil", "portion"}:
        low = max(0.0, low)
        high = max(0.0, high)
    return {"low": round(low, 4), "high": round(high, 4)}


def _within_numeric_range(actual_value: Optional[float], rng: Optional[Dict[str, Any]]) -> Optional[bool]:
    av = _safe_float(actual_value, None)
    if av is None or not isinstance(rng, dict):
        return None
    low = _safe_float(rng.get("low"), None)
    high = _safe_float(rng.get("high"), None)
    if low is None or high is None:
        return None
    return bool(float(low) <= float(av) <= float(high))


def log_confidence_event(
    *,
    user_id: str,
    analysis_id: str,
    meal_id: str,
    prediction_type: str,
    predicted_value: Optional[float],
    predicted_range: Optional[Dict[str, Any]],
    predicted_confidence: Optional[float],
    actual_value: Optional[float],
    actual_range: Optional[Dict[str, Any]] = None,
) -> None:
    if not ENABLE_CONFIDENCE_AUDIT_LOGGING:
        return
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    p = str(prediction_type or "").strip().lower()
    if p not in {"portion", "oil", "vision"}:
        return
    pv = _safe_float(predicted_value, None)
    av = _safe_float(actual_value, None)
    err = None
    if pv is not None and av is not None:
        err = abs(float(pv) - float(av))
    within = _within_numeric_range(av, predicted_range)
    row = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id or "").strip(),
        "analysis_id": str(analysis_id or "").strip() or None,
        "meal_id": str(meal_id or "").strip() or None,
        "prediction_type": p,
        "predicted_value": pv,
        "predicted_range": predicted_range if isinstance(predicted_range, dict) else None,
        "predicted_confidence": None if predicted_confidence is None else round(_clamp01(predicted_confidence, 0.0), 4),
        "actual_value": av,
        "actual_range": actual_range if isinstance(actual_range, dict) else None,
        "error_abs": None if err is None else round(float(err), 6),
        "within_range": within,
        "created_at": _now_utc_naive().isoformat(),
    }
    try:
        _sb_insert_with_column_fallback(TBL_CONFIDENCE_AUDIT, row)
    except Exception as e:
        logger.info(f"confidence audit write skipped: {e}")


def _safe_item_lookup(items: List[Dict[str, Any]], item_id: str) -> Optional[Dict[str, Any]]:
    iid = str(item_id or "").strip()
    if not iid:
        return None
    for it in (items or []):
        if str((it or {}).get("item_id") or "").strip() == iid:
            return dict(it or {})
    return None


def _build_confidence_events_for_rerun(
    *,
    user_id: str,
    analysis_id: str,
    meal_id: str,
    old_items: List[Dict[str, Any]],
    edited_items_pre_priors: List[Dict[str, Any]],
    edits: AnalyzeRerunEditsModel,
    calibration_settings: Dict[str, Any],
    vision_confidence: float,
) -> None:
    if not ENABLE_CONFIDENCE_AUDIT_LOGGING:
        return
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return

    if edits.portion_multiplier is not None:
        pred_grams = sum(float(_safe_float((x or {}).get("grams"), 0.0) or 0.0) for x in (old_items or []))
        act_grams = sum(float(_safe_float((x or {}).get("grams"), 0.0) or 0.0) for x in (edited_items_pre_priors or []))
        log_confidence_event(
            user_id=user_id,
            analysis_id=analysis_id,
            meal_id=meal_id,
            prediction_type="portion",
            predicted_value=pred_grams,
            predicted_range=_prediction_range("portion", pred_grams, calibration_settings),
            predicted_confidence=float(_clamp01(vision_confidence, 0.0)),
            actual_value=act_grams,
        )

    if edits.set_oil_added_tsp is not None:
        target = _safe_item_lookup(old_items, edits.set_oil_added_tsp.item_id)
        pred_oil = float(_safe_float((target or {}).get("oil_added_tsp"), 0.0) or 0.0)
        pred_conf = float(_clamp01((target or {}).get("confidence"), vision_confidence))
        act_oil = float(max(0.0, _safe_float(edits.set_oil_added_tsp.tsp, 0.0) or 0.0))
        log_confidence_event(
            user_id=user_id,
            analysis_id=analysis_id,
            meal_id=meal_id,
            prediction_type="oil",
            predicted_value=pred_oil,
            predicted_range=_prediction_range("oil", pred_oil, calibration_settings),
            predicted_confidence=pred_conf,
            actual_value=act_oil,
        )

    if edits.clarifying_answer:
        old_first = dict((old_items or [{}])[0] or {})
        new_first = dict((edited_items_pre_priors or [{}])[0] or {})
        pred_oil = float(_safe_float(old_first.get("oil_added_tsp"), 0.0) or 0.0)
        act_oil = float(_safe_float(new_first.get("oil_added_tsp"), pred_oil) or pred_oil)
        if abs(act_oil - pred_oil) >= 0.01:
            log_confidence_event(
                user_id=user_id,
                analysis_id=analysis_id,
                meal_id=meal_id,
                prediction_type="oil",
                predicted_value=pred_oil,
                predicted_range=_prediction_range("oil", pred_oil, calibration_settings),
                predicted_confidence=float(_clamp01(old_first.get("confidence"), vision_confidence)),
                actual_value=act_oil,
            )

    if edits.set_cooking_method is not None:
        target_old = _safe_item_lookup(old_items, edits.set_cooking_method.item_id)
        old_method = _method_norm((target_old or {}).get("cooking_method"))
        new_method = _method_norm(edits.set_cooking_method.method)
        match_score = 1.0 if (old_method and new_method and old_method == new_method) else 0.0
        log_confidence_event(
            user_id=user_id,
            analysis_id=analysis_id,
            meal_id=meal_id,
            prediction_type="vision",
            predicted_value=match_score,
            predicted_range={"low": 1.0, "high": 1.0},
            predicted_confidence=float(_clamp01((target_old or {}).get("confidence"), vision_confidence)),
            actual_value=1.0,
            actual_range={"low": 1.0, "high": 1.0},
        )


def _fetch_confidence_audit_rows(prediction_type: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return []
    since = (_now_utc_naive() - dt.timedelta(days=max(1, min(90, int(days))))).isoformat()
    params = {
        "select": "prediction_type,predicted_confidence,error_abs,within_range,predicted_value,actual_value,predicted_range,created_at",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": "5000",
    }
    p = str(prediction_type or "").strip().lower()
    if p:
        params["prediction_type"] = f"eq.{p}"
    try:
        rows = sb_get_many(TBL_CONFIDENCE_AUDIT, params=params)
        return rows if isinstance(rows, list) else []
    except Exception as e:
        logger.info(f"confidence audit read skipped: {e}")
        return []


def _aggregate_confidence_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows or [])
    if total <= 0:
        return {
            "total": 0,
            "avg_confidence": 0.0,
            "avg_error": 0.0,
            "avg_error_pct": 0.0,
            "pct_within_range": 0.0,
            "actual_above_upper_pct": 0.0,
            "actual_below_lower_pct": 0.0,
        }

    conf_sum = 0.0
    conf_n = 0
    err_sum = 0.0
    err_n = 0
    err_pct_sum = 0.0
    err_pct_n = 0
    within_n = 0
    above_n = 0
    below_n = 0
    for r in (rows or []):
        c = _safe_float((r or {}).get("predicted_confidence"), None)
        if c is not None:
            conf_sum += float(c)
            conf_n += 1
        e = _safe_float((r or {}).get("error_abs"), None)
        if e is not None:
            err_sum += float(e)
            err_n += 1
        pv = _safe_float((r or {}).get("predicted_value"), None)
        av = _safe_float((r or {}).get("actual_value"), None)
        if pv is not None and av is not None:
            denom = max(1e-6, abs(float(pv)))
            err_pct_sum += abs(float(av) - float(pv)) / denom
            err_pct_n += 1
        within = (r or {}).get("within_range")
        if within is True:
            within_n += 1
        rng = _parse_jsonish((r or {}).get("predicted_range"), {})
        low = _safe_float((rng or {}).get("low"), None)
        high = _safe_float((rng or {}).get("high"), None)
        if av is not None and low is not None and high is not None:
            if float(av) > float(high):
                above_n += 1
            elif float(av) < float(low):
                below_n += 1

    return {
        "total": total,
        "avg_confidence": round(conf_sum / max(1, conf_n), 4),
        "avg_error": round(err_sum / max(1, err_n), 6),
        "avg_error_pct": round(err_pct_sum / max(1, err_pct_n), 6),
        "pct_within_range": round(within_n / max(1, total), 6),
        "actual_above_upper_pct": round(above_n / max(1, total), 6),
        "actual_below_lower_pct": round(below_n / max(1, total), 6),
    }


def compute_confidence_calibration(days: int = 7) -> Dict[str, Any]:
    settings = load_confidence_calibration_settings()
    if not ENABLE_DYNAMIC_CONFIDENCE_THRESHOLDS:
        return {
            "ok": True,
            "days": int(days),
            "metrics": {},
            "settings": settings,
            "updated_at": _now_utc_naive().isoformat(),
            "dynamic_thresholds_enabled": False,
        }
    metrics: Dict[str, Any] = {}
    updated_settings = json.loads(json.dumps(settings))
    for p in ("portion", "oil", "vision"):
        rows = _fetch_confidence_audit_rows(prediction_type=p, days=days)
        m = _aggregate_confidence_rows(rows)
        metrics[p] = m
        threshold = _calibration_setting_value(updated_settings, p, "confidence_threshold", DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS[p]["confidence_threshold"])
        expand = _calibration_setting_value(updated_settings, p, "range_expansion_factor", DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS[p]["range_expansion_factor"])
        if m["total"] >= 8 and m["pct_within_range"] < 0.60 and m["avg_error_pct"] > 0.15:
            threshold = max(0.50, threshold - 0.03)
            expand = min(2.50, expand * 1.15)
        elif m["total"] >= 8 and m["pct_within_range"] > 0.80 and m["avg_error_pct"] < 0.10:
            threshold = min(0.98, threshold + 0.03)
            expand = max(0.80, expand * 0.95)
        if p == "oil" and m["total"] >= 8:
            if m["actual_above_upper_pct"] > 0.35:
                threshold = max(0.50, threshold - 0.04)
                expand = min(2.50, expand * 1.20)
            elif m["actual_below_lower_pct"] > 0.35:
                threshold = min(0.98, threshold + 0.02)
                expand = max(0.80, expand * 0.90)
        updated_settings[p] = {
            "confidence_threshold": round(threshold, 4),
            "range_expansion_factor": round(expand, 4),
        }

    for p in ("portion", "oil", "vision"):
        _upsert_confidence_calibration_setting(
            p,
            updated_settings[p]["confidence_threshold"],
            updated_settings[p]["range_expansion_factor"],
        )

    return {
        "ok": True,
        "days": int(days),
        "metrics": metrics,
        "settings": updated_settings,
        "updated_at": _now_utc_naive().isoformat(),
    }


def _derive_feedback_food_key(req: CoachFeedbackRequestModel) -> str:
    corr = req.corrections or CoachFeedbackCorrectionsModel()
    candidates: List[Any] = [
        corr.food_key,
        corr.item_name,
        corr.item_id,
        req.meal_id,
    ]
    for item in (corr.confirmed_items or []):
        if isinstance(item, CoachFeedbackConfirmedItemModel):
            candidates.append(item.name)
        elif isinstance(item, dict):
            candidates.append(item.get("name"))
    for raw in candidates:
        token = _food_token(raw)
        if token:
            return token
    return ""


def _upsert_user_food_prior(
    user_id: str,
    food_token: str,
    *,
    rating: Optional[int] = None,
    portion_multiplier: Optional[float] = None,
    oil_added_tsp: Optional[float] = None,
    cooking_method: Optional[str] = None,
) -> Dict[str, Any]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return {}
    token = _food_token(food_token)
    if not token:
        return {}

    existing = _read_user_food_prior(user_id, token) or {}
    feedback_count = int(_safe_float(existing.get("feedback_count"), 0) or 0)
    avg_rating = float(_safe_float(existing.get("avg_rating"), 0.0) or 0.0)
    portion_count = int(_extract_prior_count(existing, "portion_multiplier_n", "portion_feedback_count"))
    portion_avg = float(_extract_prior_float(existing, "portion_multiplier_mean", "portion_multiplier_avg", default=1.0))
    oil_count = int(_extract_prior_count(existing, "oil_tsp_n", "oil_feedback_count"))
    oil_avg = float(_extract_prior_float(existing, "oil_tsp_mean", "oil_added_tsp_avg", default=0.0))
    oil_by_method = _extract_oil_by_method(existing)
    always_ask_methods = _extract_always_ask_methods(existing)
    always_ask_set = set(always_ask_methods)

    if rating is not None:
        safe_rating = max(1, min(5, int(rating)))
        avg_rating = _blend_avg(avg_rating, feedback_count, float(safe_rating))
        feedback_count += 1
    if portion_multiplier is not None and portion_multiplier > 0:
        safe_portion = float(max(0.4, min(2.2, portion_multiplier)))
        portion_avg = _blend_avg(portion_avg, portion_count, safe_portion)
        portion_count += 1
    if oil_added_tsp is not None and oil_added_tsp >= 0:
        safe_oil = float(max(0.0, min(8.0, oil_added_tsp)))
        oil_avg = _blend_avg(oil_avg, oil_count, safe_oil)
        oil_count += 1
    method = _method_norm(cooking_method)
    if method and oil_added_tsp is not None and oil_added_tsp >= 0:
        current_method = oil_by_method.get(method) if isinstance(oil_by_method.get(method), dict) else {"mean": 0.0, "n": 0}
        m_n = int(_safe_float(current_method.get("n"), 0) or 0)
        m_mean = float(_safe_float(current_method.get("mean"), 0.0) or 0.0)
        m_mean = _blend_avg(m_mean, m_n, float(max(0.0, min(8.0, oil_added_tsp))))
        oil_by_method[method] = {"mean": round(m_mean, 4), "n": m_n + 1}

    if method and _recent_oil_corrections_for_method(user_id, method, token) >= 2:
        always_ask_set.add(method)
    always_ask_methods = sorted(always_ask_set)
    always_ask = bool(always_ask_methods)
    row = {
        "id": str(existing.get("id") or uuid.uuid4()),
        "user_id": str(user_id or "").strip(),
        "food_key": token,
        "feedback_count": feedback_count,
        "avg_rating": round(avg_rating, 3),
        "portion_multiplier_mean": round(portion_avg, 4),
        "portion_multiplier_n": portion_count,
        "oil_tsp_mean": round(oil_avg, 4),
        "oil_tsp_n": oil_count,
        "oil_by_method": oil_by_method,
        "always_ask_oil_for_methods": always_ask_methods,
        "portion_feedback_count": portion_count,
        "portion_multiplier_avg": round(portion_avg, 4),
        "oil_feedback_count": oil_count,
        "oil_added_tsp_avg": round(oil_avg, 4),
        "cooking_methods_json": oil_by_method,
        "always_ask_clarifying": always_ask,
        "updated_at": _now_utc_naive().isoformat(),
    }
    try:
        match = {"user_id": f"eq.{row['user_id']}"}
        existing_key = _row_food_key(existing)
        if existing_key:
            match["food_key"] = f"eq.{existing_key}"
        else:
            match["food_key"] = f"eq.{row['food_key']}"
        if existing:
            patch = {k: v for k, v in row.items() if k not in {"user_id", "food_key"}}
            _sb_patch_with_column_fallback(
                TBL_USER_FOOD_PRIORS,
                match,
                patch,
            )
        else:
            _sb_insert_with_column_fallback(
                TBL_USER_FOOD_PRIORS,
                row,
                locked_cols={"user_id", "food_key"},
            )
    except Exception as e:
        logger.info(f"user food prior write skipped: {e}")
    return {
        "food_key": token,
        "portion_multiplier_mean": round(portion_avg, 4),
        "portion_multiplier_n": int(portion_count),
        "oil_tsp_mean": round(oil_avg, 4),
        "oil_tsp_n": int(oil_count),
        "oil_by_method": oil_by_method,
        "always_ask_oil_for_methods": always_ask_methods,
    }


def _build_user_priors_context(user_id: str, limit: int = 12) -> Dict[str, Any]:
    rows = _list_user_food_priors(user_id, limit=max(8, min(50, limit)))
    priors: Dict[str, Any] = {}
    always_methods: List[str] = []
    seen_methods = set()
    for row in rows:
        key = _row_food_key(row)
        if not key:
            continue
        prior_payload = _build_food_prior_payload(row)
        priors[key] = {
            "portion_multiplier_mean": prior_payload.get("portion_multiplier_mean"),
            "portion_multiplier_n": prior_payload.get("portion_multiplier_n"),
            "oil_tsp_mean": prior_payload.get("oil_tsp_mean"),
            "oil_tsp_n": prior_payload.get("oil_tsp_n"),
            "oil_by_method": prior_payload.get("oil_by_method"),
        }
        for m in (prior_payload.get("always_ask_oil_for_methods") or []):
            mk = _method_norm(m)
            if mk and mk not in seen_methods:
                seen_methods.add(mk)
                always_methods.append(mk)
    return {
        "user_priors": priors,
        "always_ask_oil_for_methods": always_methods[:10],
        "defaults_policy": "Use priors only as soft defaults. Ask clarifying question if confidence<0.75 or method in always_ask_oil_for_methods.",
    }


def _build_user_priors_context_for_candidates(
    user_id: str,
    candidate_food_keys: Optional[List[str]] = None,
    limit: int = 12,
) -> Dict[str, Any]:
    base = _build_user_priors_context(user_id, limit=limit)
    priors = dict(base.get("user_priors") or {})
    always_methods = [_method_norm(m) for m in (base.get("always_ask_oil_for_methods") or []) if _method_norm(m)]
    seen_methods = set(always_methods)
    for raw in (candidate_food_keys or []):
        token = _food_token(raw)
        if not token or token in priors:
            continue
        row = _read_user_food_prior(user_id, token) or {}
        if not row:
            continue
        payload = _build_food_prior_payload(row)
        priors[token] = {
            "portion_multiplier_mean": payload.get("portion_multiplier_mean"),
            "portion_multiplier_n": payload.get("portion_multiplier_n"),
            "oil_tsp_mean": payload.get("oil_tsp_mean"),
            "oil_tsp_n": payload.get("oil_tsp_n"),
            "oil_by_method": payload.get("oil_by_method"),
        }
        for m in (payload.get("always_ask_oil_for_methods") or []):
            mk = _method_norm(m)
            if mk and mk not in seen_methods:
                seen_methods.add(mk)
                always_methods.append(mk)
    return {
        "user_priors": priors,
        "always_ask_oil_for_methods": always_methods[:12],
        "defaults_policy": str(base.get("defaults_policy") or ""),
    }


def _needs_user_prior_oil_question(items: List[Dict[str, Any]], always_ask_methods: List[str]) -> bool:
    methods = {_method_norm(m) for m in (always_ask_methods or []) if _method_norm(m)}
    if not methods:
        return False
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        method = _method_norm(it.get("cooking_method"))
        if not method:
            continue
        if method in methods:
            return True
    return False


def _apply_scan_user_priors(
    user_id: str,
    items: List[Dict[str, Any]],
    always_ask_methods: List[str],
    *,
    portion_threshold: float = 0.75,
    oil_threshold: float = 0.70,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    out = [dict(x or {}) for x in (items or [])]
    used = {
        "portion_prior_used": False,
        "oil_prior_used": False,
        "asked_clarifying_question": False,
        "asked_clarifying_question_reason": "",
    }
    if not out:
        return out, used

    for it in out:
        token = _food_token(it.get("name"))
        if not token:
            continue
        prior = _read_user_food_prior(user_id, token) or {}
        if not prior:
            continue
        p_mean = _extract_prior_float(prior, "portion_multiplier_mean", "portion_multiplier_avg", default=1.0)
        p_n = _extract_prior_count(prior, "portion_multiplier_n", "portion_feedback_count")
        prior_conf_portion = min(0.98, 0.45 + (0.08 * float(max(0, p_n))))
        if p_n >= 3 and prior_conf_portion >= portion_threshold and 0.7 <= p_mean <= 1.3 and abs(p_mean - 1.0) >= 0.08:
            grams = float(_safe_float(it.get("grams"), 0.0) or 0.0)
            if grams > 0:
                it["grams"] = round(max(1.0, grams * p_mean), 1)
                used["portion_prior_used"] = True

        method = _method_norm(it.get("cooking_method"))
        if method and method not in {_method_norm(x) for x in (always_ask_methods or [])}:
            oil_by_method = _extract_oil_by_method(prior)
            method_prior = oil_by_method.get(method) if isinstance(oil_by_method.get(method), dict) else {}
            m_n = int(_safe_float(method_prior.get("n"), 0) or 0)
            m_mean = float(_safe_float(method_prior.get("mean"), 0.0) or 0.0)
            prior_conf_oil = min(0.98, 0.40 + (0.10 * float(max(0, m_n))))
            if m_n >= 2 and prior_conf_oil >= oil_threshold and m_mean > 0:
                cur_oil = float(_safe_float(it.get("oil_added_tsp"), 0.0) or 0.0)
                if m_mean > cur_oil:
                    it["oil_added_tsp"] = round(m_mean, 1)
                    used["oil_prior_used"] = True

    if _needs_user_prior_oil_question(out, always_ask_methods):
        used["asked_clarifying_question"] = True
        used["asked_clarifying_question_reason"] = "user_prior_requires_oil_question"
    return out, used


def _apply_user_priors_to_items(
    user_id: str,
    items: List[Dict[str, Any]],
    edits: AnalyzeRerunEditsModel,
    *,
    portion_threshold: float = 0.75,
    oil_threshold: float = 0.70,
) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    out = [dict(x or {}) for x in (items or [])]
    used = {
        "portion_prior_used": False,
        "oil_prior_used": False,
        "asked_clarifying_question": False,
        "asked_clarifying_question_reason": "",
    }
    if not out:
        return out, used

    explicit_portion = edits is not None and edits.portion_multiplier is not None
    explicit_oil = edits is not None and edits.set_oil_added_tsp is not None

    for it in out:
        token = _food_token(it.get("name"))
        if not token:
            continue
        prior = _read_user_food_prior(user_id, token) or {}
        if not prior:
            continue

        if not explicit_portion:
            prior_mul = _extract_prior_float(prior, "portion_multiplier_mean", "portion_multiplier_avg", default=1.0)
            prior_n = _extract_prior_count(prior, "portion_multiplier_n", "portion_feedback_count")
            prior_conf_portion = min(0.98, 0.45 + (0.08 * float(max(0, prior_n))))
            if prior_n >= 3 and prior_conf_portion >= portion_threshold and 0.7 <= prior_mul <= 1.3 and abs(prior_mul - 1.0) >= 0.08:
                grams = float(_safe_float(it.get("grams"), 0.0) or 0.0)
                if grams > 0:
                    it["grams"] = round(max(1.0, grams * prior_mul), 1)
                    used["portion_prior_used"] = True

        if not explicit_oil:
            method = str(it.get("cooking_method") or "").strip().lower()
            prior_oil = _extract_prior_float(prior, "oil_tsp_mean", "oil_added_tsp_avg", default=0.0)
            oil_n = _extract_prior_count(prior, "oil_tsp_n", "oil_feedback_count")
            prior_conf_oil = min(0.98, 0.40 + (0.10 * float(max(0, oil_n))))
            if oil_n >= 2 and prior_conf_oil >= oil_threshold and prior_oil > 0 and ("fried" in method or method in {"pan_fried", "shallow_fried", "deep_fried", "air_fried"}):
                cur_oil = float(_safe_float(it.get("oil_added_tsp"), 0.0) or 0.0)
                if prior_oil > cur_oil:
                    it["oil_added_tsp"] = round(prior_oil, 1)
                    used["oil_prior_used"] = True

    if not used["asked_clarifying_question"]:
        merged_methods = []
        for it in out:
            token = _food_token(it.get("name"))
            if not token:
                continue
            prior = _read_user_food_prior(user_id, token) or {}
            for m in _extract_always_ask_methods(prior):
                if m not in merged_methods:
                    merged_methods.append(m)
        if _needs_user_prior_oil_question(out, merged_methods):
            used["asked_clarifying_question"] = True
            used["asked_clarifying_question_reason"] = "user_prior_requires_oil_question"

    return out, used


def _coach_mem_key(user_id: str, day_iso: str, payload_hash: str) -> str:
    return f"{user_id}:{day_iso}:{payload_hash}"


def _cache_entry_is_expired(entry: Optional[Dict[str, Any]], *, max_age_hours: int = 48) -> bool:
    src = entry if isinstance(entry, dict) else {}
    ts = (
        _utc_from_iso(src.get("updatedAt"))
        or _utc_from_iso(src.get("coach_generated_ts"))
        or _utc_from_iso(src.get("updated_at"))
        or _utc_from_iso(src.get("created_at"))
    )
    if not ts:
        return False
    age_seconds = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds()
    return bool(age_seconds > max(1, int(max_age_hours)) * 3600)


def _coach_cache_get(user_id: str, day_iso: str, payload_hash: str) -> Optional[Dict[str, Any]]:
    # 1) Fast in-memory cache
    mem_key = _coach_mem_key(user_id, day_iso, payload_hash)
    hit = _COACH_MEM_CACHE.get(mem_key)
    if isinstance(hit, dict):
        if _cache_entry_is_expired(hit, max_age_hours=COACH_CACHE_TTL_HOURS):
            _COACH_MEM_CACHE.pop(mem_key, None)
        else:
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
    if _cache_entry_is_expired(row, max_age_hours=COACH_CACHE_TTL_HOURS):
        return None

    stored_hash = str(
        row.get("payload_hash")
        or row.get("insight_signature")
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


def _classify_fli_reason_code(raw: str) -> str:
    msg = str(raw or "").lower()
    if not msg:
        return ""
    if "timeout" in msg:
        return "LLM_TIMEOUT"
    if "rate limit" in msg or "429" in msg:
        return "LLM_RATE_LIMIT"
    if "json" in msg or "parse" in msg or "validation" in msg:
        return "LLM_BAD_JSON"
    if "empty" in msg or "no text returned" in msg:
        return "LLM_EMPTY"
    if "500" in msg or "502" in msg or "503" in msg or "upstream" in msg:
        return "UPSTREAM_500"
    return "LLM_EXCEPTION"


def _extract_llm_failure_debug(err: Exception) -> Tuple[str, List[str], str]:
    raw = _http_exc_raw(err)
    reason = _classify_fli_reason_code(raw)
    tried_models: List[str] = []
    if isinstance(err, HTTPException) and isinstance(err.detail, dict):
        arr = err.detail.get("tried_models")
        if isinstance(arr, list):
            for m in arr:
                _append_tried_model_once(tried_models, m)
        if not raw:
            raw = str(err.detail.get("raw") or err.detail.get("error") or "")
    return reason, tried_models[:8], str(raw or "")[:300]


def _compute_fli_stale_seconds(ts_iso: Any) -> int:
    parsed = _parse_iso_dt_naive(ts_iso)
    if not parsed:
        return 0
    delta = (_now_utc_naive() - parsed).total_seconds()
    return int(max(0, round(delta)))


def _normalize_fli_source(resp: Dict[str, Any]) -> str:
    source = str((resp or {}).get("fli_source") or "").strip().lower()
    if source in {"llm", "cached_llm", "rules"}:
        return source
    if source in {"fallback", "heuristic"}:
        return "rules"
    rs = str((resp or {}).get("reasoning_source") or "").strip().lower()
    if rs in {"llm", "cached_llm"}:
        return rs
    if rs in {"rules", "heuristic", "fallback"}:
        return "rules"
    return "rules"


def _public_source_from_fli(raw_source: Any) -> str:
    src = str(raw_source or "").strip().lower()
    if src in {"llm"}:
        return "llm"
    if src in {"cached_llm", "cache"}:
        return "cache"
    if src in {"rules", "fallback", "heuristic"}:
        return "rules"
    return "rules"


def _attach_coach_response_debug(
    resp: Dict[str, Any],
    *,
    request_id: str,
    started_at: float,
    meal_id: str = "",
    analysis_id: str = "",
    input_scan_id: str = "",
    source_hint: str = "",
    model_used: str = "",
    error_code: str = "",
    tried_models: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out = dict(resp or {})
    internal_source = _normalize_fli_source(out)
    public_source = _public_source_from_fli(source_hint or internal_source)
    merged_model = str(model_used or out.get("llm_model_used") or "").strip()
    merged_error = str(error_code or out.get("llm_error_code") or out.get("fli_reason_code") or "").strip()
    merged_tried: List[str] = []
    for name in list(tried_models or []) + list(out.get("llm_tried_models") or []):
        val = str(name or "").strip()
        if val and val not in merged_tried:
            merged_tried.append(val)
    if not merged_tried and merged_model:
        merged_tried = [merged_model]

    out["request_id"] = str(request_id or _new_request_id())
    out["source"] = public_source
    out["coach_summary_source"] = "llm" if public_source in {"llm", "cache"} else "fallback"
    out["fli_source_internal"] = str(out.get("fli_source") or out.get("reasoning_source") or internal_source)
    out["fli_source"] = internal_source
    out["model_used"] = merged_model
    out["llm_model_used"] = merged_model
    out["error_code"] = merged_error if public_source != "llm" else ""
    out["llm_error_code"] = merged_error if public_source != "llm" else ""
    out["tried_models"] = merged_tried if public_source != "llm" else ([] if not merged_model else [merged_model])
    out["llm_tried_models"] = out["tried_models"]
    tone_requested = _normalize_daily_tone_id(
        out.get("tone_requested")
        or out.get("tone_used")
        or ""
    )
    tone_used = _normalize_daily_tone_id(
        out.get("tone_used")
        or out.get("tone_mode")
        or tone_requested
        or "supportive"
    )
    if not tone_requested:
        tone_requested = tone_used or "supportive"
    if not tone_used:
        tone_used = tone_requested
    out["tone_requested"] = tone_requested
    out["tone_used"] = tone_used
    out["tone_mode"] = _tone_mode_from_source(public_source)
    out["latency_ms"] = int(max(0, round((time.time() - float(started_at or time.time())) * 1000)))

    effective_scan = str(
        input_scan_id
        or out.get("input_scan_id")
        or out.get("last_processed_scan_id")
        or analysis_id
        or meal_id
        or ""
    ).strip()
    effective_analysis = str(analysis_id or out.get("analysis_id") or effective_scan or "").strip()
    effective_meal = str(meal_id or out.get("meal_id") or effective_analysis or effective_scan or "").strip()
    out["input_scan_id"] = effective_scan
    out["analysis_id"] = effective_analysis
    out["meal_id"] = effective_meal
    return out


def _record_coach_event(user_id: str, event: Dict[str, Any]) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    ring = _COACH_EVENT_RING.get(uid)
    if ring is None:
        ring = deque(maxlen=20)
        _COACH_EVENT_RING[uid] = ring
    ring.appendleft(dict(event or {}))

    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_COACH_EVENTS):
        return
    row = {
        "event_id": str(uuid.uuid4()),
        "user_id": uid,
        "event_type": str((event or {}).get("type") or "coach_daily").strip() or "coach_daily",
        "event_json": dict(event or {}),
        "created_at": _now_utc_naive().isoformat(),
    }
    try:
        _sb_insert_with_column_fallback(TBL_COACH_EVENTS, row)
    except Exception as e:
        if not _mark_table_unavailable(TBL_COACH_EVENTS, e):
            logger.info(f"coach event write skipped: {e}")


def _best_cached_coach_llm(user_id: str, day_iso: str) -> Optional[Dict[str, Any]]:
    best_obj: Optional[Dict[str, Any]] = None
    best_ts: Optional[dt.datetime] = None
    prefix = f"{str(user_id or '').strip()}:{str(day_iso or '').strip()}:"
    for key, value in list(_COACH_MEM_CACHE.items()):
        if not key.startswith(prefix) or not isinstance(value, dict):
            continue
        if _cache_entry_is_expired(value, max_age_hours=COACH_CACHE_TTL_HOURS):
            _COACH_MEM_CACHE.pop(key, None)
            continue
        src = _normalize_fli_source(value)
        if src not in {"llm", "cached_llm"}:
            continue
        ts = _parse_iso_dt_naive(value.get("coach_generated_ts") or value.get("updatedAt")) or _now_utc_naive()
        if best_ts is None or ts > best_ts:
            best_obj = dict(value)
            best_ts = ts
    if isinstance(best_obj, dict):
        return best_obj
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
    except Exception:
        row = None
    if not isinstance(row, dict):
        return None
    if _cache_entry_is_expired(row, max_age_hours=COACH_CACHE_TTL_HOURS):
        return None
    for k in ("coach_json", "coach_daily", "coach_response", "response_json", "response"):
        val = row.get(k)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = None
        if isinstance(val, dict) and _normalize_fli_source(val) in {"llm", "cached_llm"}:
            return dict(val)
    return None


def _coach_user_prompt(
    norm_payload: Dict[str, Any],
    fat_loss_score: int,
    rule_alerts: List[Dict[str, str]],
    weekly_behavior: Optional[Dict[str, Any]] = None,
    weekly_predictive: Optional[Dict[str, Any]] = None,
    fast_mode: bool = False,
    tone_preference: str = "supportive",
) -> str:
    tone_pref = _normalize_tone_preference(tone_preference)
    tone_prompt = _daily_tone_prompt_text(tone_pref)
    allowed_palette = coach_logic.allowed_suggestion_palette(norm_payload)
    goals = (norm_payload.get("goals") or {}) if isinstance(norm_payload.get("goals"), dict) else {}
    consumed = (norm_payload.get("consumed") or {}) if isinstance(norm_payload.get("consumed"), dict) else {}
    deltas = {
        "kcal_delta": round(_safe_float(consumed.get("kcal"), 0.0) - _safe_float(goals.get("kcal"), 0.0), 1),
        "protein_gap_g": round(max(0.0, _safe_float(goals.get("protein_g"), 0.0) - _safe_float(consumed.get("protein_g"), 0.0)), 1),
        "fiber_gap_g": round(max(0.0, _safe_float(goals.get("fiber_g"), 0.0) - _safe_float(consumed.get("fiber_g"), 0.0)), 1),
        "carbs_delta_g": round(_safe_float(consumed.get("carbs_g"), 0.0) - _safe_float(goals.get("carbs_g"), 0.0), 1),
        "fat_delta_g": round(_safe_float(consumed.get("fat_g"), 0.0) - _safe_float(goals.get("fat_g"), 0.0), 1),
    }
    wb_patterns = (weekly_behavior or {}).get("patterns") if isinstance(weekly_behavior, dict) else {}
    wb_insights = (weekly_behavior or {}).get("insights") if isinstance(weekly_behavior, dict) else []
    predictive = weekly_predictive if isinstance(weekly_predictive, dict) else {}
    compact = {
        "date": norm_payload.get("date"),
        "goals": norm_payload.get("goals"),
        "consumed": norm_payload.get("consumed"),
        "deltas": deltas,
        "signals": norm_payload.get("signals"),
        "meal_timing": norm_payload.get("meal_timing"),
        "constraints": norm_payload.get("constraints"),
        "profile": norm_payload.get("profile"),
        "fat_loss_score": fat_loss_score,
        "rule_risk_alerts": rule_alerts,
        "behavior_memory_weekly": {
            "patterns": wb_patterns or {},
            "insights": wb_insights[:4] if isinstance(wb_insights, list) else [],
            "days_tracked": int(_safe_float((weekly_behavior or {}).get("days_tracked"), 0) or 0)
            if isinstance(weekly_behavior, dict)
            else 0,
        },
        "predictive_engine_weekly": {
            "days_tracked": int(_safe_float(predictive.get("days_tracked"), 0) or 0),
            "days_with_data_7d": int(_safe_float(predictive.get("days_with_data_7d"), 0) or 0),
            "scans_7d": int(_safe_float(predictive.get("scans_7d"), 0) or 0),
            "projection_confidence_band": str(predictive.get("projection_confidence_band") or ""),
            "missing_data_reason": str(predictive.get("missing_data_reason") or ""),
            "protein_consistency": _safe_float(predictive.get("protein_consistency"), 0.0),
            "fiber_consistency": _safe_float(predictive.get("fiber_consistency"), 0.0),
            "timing_volatility": _safe_float(predictive.get("timing_volatility"), 0.0),
            "diet_volatility_index": _safe_float(predictive.get("diet_volatility_index"), 0.0),
            "fat_loss_velocity_score": _safe_float(predictive.get("fat_loss_velocity_score"), 0.0),
            "fat_loss_probability_7d": _safe_float(predictive.get("fat_loss_probability_7d"), 0.0),
            "projection_7d_score": _safe_float(predictive.get("projection_7d_score"), 0.0),
            "energy_balance_trend_7d": predictive.get("energy_balance_trend_7d")
            if isinstance(predictive.get("energy_balance_trend_7d"), dict)
            else {},
            "hunger_volatility_projection": predictive.get("hunger_volatility_projection")
            if isinstance(predictive.get("hunger_volatility_projection"), dict)
            else {},
            "muscle_retention_risk": predictive.get("muscle_retention_risk")
            if isinstance(predictive.get("muscle_retention_risk"), dict)
            else {},
        },
    }
    template = {
        "one_sentence_summary": "string",
        "pattern_detected": "string",
        "projection_explained": "string",
        "biggest_risk_lever": {"title": "string", "reason": "string"},
        "highest_roi_change": {"title": "string", "why": "string", "how": "string"},
        "if_you_do_one_thing": "string",
        "projection_7d": {"if_unchanged": "string", "if_improved": "string"},
        "diagnosis": ["string", "string"],
        "tomorrow_focus": ["string", "string"],
        "actions": [{"title": "string", "why": "string", "how": "string"}],
        "risk_alerts": [{"type": "string", "level": "low|medium|high", "reason": "string"}],
    }
    if fast_mode:
        fast_payload = {
            "date": compact.get("date"),
            "today_totals": compact.get("consumed"),
            "goal_gaps": {
                "protein_gap_g": deltas.get("protein_gap_g"),
                "fiber_gap_g": deltas.get("fiber_gap_g"),
                "kcal_delta": deltas.get("kcal_delta"),
                "carbs_delta_g": deltas.get("carbs_delta_g"),
                "fat_delta_g": deltas.get("fat_delta_g"),
            },
            "signals": {
                "avg_glycemic_load": _safe_float((compact.get("signals") or {}).get("avg_glycemic_load"), 0.0),
                "glycemic_bucket": "high"
                if _safe_float((compact.get("signals") or {}).get("avg_glycemic_load"), 0.0) >= 25
                else "moderate"
                if _safe_float((compact.get("signals") or {}).get("avg_glycemic_load"), 0.0) >= 15
                else "low",
                "ultra_processed_avg": _safe_float((compact.get("signals") or {}).get("ultra_processed_avg"), 0.0),
                "upf_bucket": "high"
                if _safe_float((compact.get("signals") or {}).get("ultra_processed_avg"), 0.0) >= 6.5
                else "moderate"
                if _safe_float((compact.get("signals") or {}).get("ultra_processed_avg"), 0.0) >= 4
                else "low",
                "leucine_triggers": (compact.get("signals") or {}).get("leucine_triggers"),
                "avg_satiety": _safe_float((compact.get("signals") or {}).get("avg_satiety"), 0.0),
                "late_calories_pct": _safe_float((compact.get("meal_timing") or {}).get("late_calories_pct"), 0.0),
            },
            "meta": {
                "fat_loss_score": fat_loss_score,
                "scans_7d": int(_safe_float((predictive or {}).get("scans_7d"), 0) or 0),
                "days_with_data_7d": int(_safe_float((predictive or {}).get("days_with_data_7d"), 0) or 0),
                "projection_confidence_band": str((predictive or {}).get("projection_confidence_band") or "medium"),
                "goal_type": str((compact.get("profile") or {}).get("goal_type") or "fat_loss"),
                "training_time": str((compact.get("profile") or {}).get("training_time") or "evening"),
            },
            "rule_risk_alerts": rule_alerts[:3],
        }
        return (
            "FAST_MODE: produce concise high-signal coaching from compact metrics only.\n"
            "Rules:\n"
            "- Strict JSON only.\n"
            f"- Tone mode: {tone_pref}. {tone_prompt}\n"
            "- No medical advice, no disease/supplement/treatment claims.\n"
            "- No exact body-weight promises.\n"
            "- Max 2 actions.\n"
            "- one_sentence_summary <= 18 words.\n"
            "- Avoid repeating the same point across sections.\n\n"
            f"Allowed suggestion palette:\n{json.dumps(allowed_palette, ensure_ascii=True)}\n\n"
            f"Compact payload:\n{json.dumps(fast_payload, ensure_ascii=True)}\n\n"
            f"Output JSON shape:\n{json.dumps(template, ensure_ascii=True)}"
        )
    return (
        "Use this daily nutrition summary and produce coaching insight, not a stat report.\n"
        "Rules:\n"
        f"- Tone mode: {tone_pref}. {tone_prompt}\n"
        "- Keep deterministic numbers as truth; do not invent any number.\n"
        "- Prioritize behavior pattern + cause/effect language.\n"
        "- Avoid line-by-line metric repetition. Mention at most 4 numeric anchors in the whole output.\n"
        "- If weekly memory exists, use it for pattern_detected or projection_7d.\n"
        "- Use predictive_engine_weekly to explain likely 7-day direction in plain language.\n"
        "- Never claim exact body-weight outcomes. Do not say 'you will lose X kg/lbs'.\n"
        "- one_sentence_summary must be <= 18 words.\n"
        "- projection_explained must explicitly mention the confidence band (low/medium/high).\n"
        "- If confidence is low, phrase conclusions as early directional signals.\n"
        "- If confidence is high, you may use stronger pattern language (still non-medical).\n"
        "- if_you_do_one_thing must be one short actionable sentence.\n"
        "- pattern_detected must be one concise sentence explaining behavior pattern.\n"
        "- biggest_risk_lever must name the highest-impact bottleneck and why it matters.\n"
        "- highest_roi_change must be one practical lever with why/how.\n"
        "- projection_7d must include if_unchanged and if_improved in plain language.\n"
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


def _coerce_coach_response_shape(
    parsed: Dict[str, Any],
    rule_alerts: List[Dict[str, str]],
    weekly_predictive: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    def _trim_words(s: str, max_words: int) -> str:
        words = [w for w in str(s or "").strip().split() if w]
        if len(words) <= max_words:
            return " ".join(words)
        return " ".join(words[:max_words]).strip()

    confidence_band = str((weekly_predictive or {}).get("projection_confidence_band") or "medium").strip().lower()
    if confidence_band not in {"low", "medium", "high"}:
        confidence_band = "medium"

    one_sentence_summary = _trim_words(str(parsed.get("one_sentence_summary") or "").strip(), 18)
    pattern_detected = str(parsed.get("pattern_detected") or "").strip()
    projection_explained = str(parsed.get("projection_explained") or "").strip()
    if_you_do_one_thing = str(parsed.get("if_you_do_one_thing") or "").strip()

    biggest_risk_src = parsed.get("biggest_risk_lever") if isinstance(parsed.get("biggest_risk_lever"), dict) else {}
    highest_roi_src = parsed.get("highest_roi_change") if isinstance(parsed.get("highest_roi_change"), dict) else {}
    projection_src = parsed.get("projection_7d") if isinstance(parsed.get("projection_7d"), dict) else {}

    biggest_risk = {
        "title": str(biggest_risk_src.get("title") or "").strip(),
        "reason": str(biggest_risk_src.get("reason") or "").strip(),
    }
    highest_roi = {
        "title": str(highest_roi_src.get("title") or "").strip(),
        "why": str(highest_roi_src.get("why") or "").strip(),
        "how": str(highest_roi_src.get("how") or "").strip(),
    }
    projection = {
        "if_unchanged": str(projection_src.get("if_unchanged") or "").strip(),
        "if_improved": str(projection_src.get("if_improved") or "").strip(),
    }

    diagnosis = parsed.get("diagnosis") if isinstance(parsed.get("diagnosis"), list) else []
    tomorrow_focus = parsed.get("tomorrow_focus") if isinstance(parsed.get("tomorrow_focus"), list) else []
    actions = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
    risk_alerts = parsed.get("risk_alerts") if isinstance(parsed.get("risk_alerts"), list) else []

    merged_risks = coach_logic.merge_risk_alerts(rule_alerts, risk_alerts, limit=4)
    primary_alert = merged_risks[0] if merged_risks else {}

    if not pattern_detected:
        if diagnosis:
            pattern_detected = str(diagnosis[0]).strip()
        elif primary_alert:
            pattern_detected = str(primary_alert.get("reason") or "").strip()
        else:
            pattern_detected = "Daily pattern shows room to improve protein, fiber, and meal timing consistency."

    if not biggest_risk["title"] or not biggest_risk["reason"]:
        alert_type = str(primary_alert.get("type") or "").replace("_", " ").strip()
        biggest_risk = {
            "title": (alert_type or "Primary behavior risk").capitalize(),
            "reason": str(primary_alert.get("reason") or "").strip()
            or "Current behavior pattern can slow progress if repeated through the week.",
        }

    if highest_roi["why"] and not coach_logic.action_references_metrics(highest_roi):
        highest_roi["why"] = f"{highest_roi['why']} This change targets protein/fiber/glycemic load behavior."
    if not highest_roi["title"] or not highest_roi["why"] or not highest_roi["how"]:
        highest_roi = {
            "title": "Front-load protein and fiber before dinner",
            "why": "Protein and fiber gaps are reducing satiety and driving late-calorie risk.",
            "how": "Add one protein anchor plus one fiber booster at breakfast and lunch.",
        }

    if not projection["if_unchanged"] or not projection["if_improved"]:
        projection = {
            "if_unchanged": "If this pattern repeats for 7 days, adherence risk will likely stay elevated.",
            "if_improved": "If the highest-ROI change is repeated for 7 days, satiety and score consistency should improve.",
        }

    if not one_sentence_summary:
        one_sentence_summary = _trim_words(f"{biggest_risk['title']}: {highest_roi['title']}.", 18)
    if not if_you_do_one_thing:
        if_you_do_one_thing = f"{highest_roi['title']}: {highest_roi['how']}"
    if not projection_explained:
        projection_explained = f"7-day direction is {confidence_band} confidence based on weekly consistency and scan coverage."
    elif confidence_band not in projection_explained.lower():
        projection_explained = f"{projection_explained} Confidence: {confidence_band}."

    clean_diagnosis = [str(x).strip() for x in diagnosis if str(x).strip()][:4]
    if not clean_diagnosis:
        clean_diagnosis = [pattern_detected, biggest_risk["reason"]]

    clean_focus = [str(x).strip() for x in tomorrow_focus if str(x).strip()][:3]
    if not clean_focus:
        clean_focus = [highest_roi["title"], highest_roi["how"], projection["if_improved"]][:3]

    cleaned = {
        "one_sentence_summary": one_sentence_summary,
        "pattern_detected": pattern_detected,
        "projection_explained": projection_explained,
        "biggest_risk_lever": biggest_risk,
        "highest_roi_change": highest_roi,
        "if_you_do_one_thing": if_you_do_one_thing,
        "projection_7d": projection,
        "diagnosis": clean_diagnosis,
        "tomorrow_focus": clean_focus,
        "actions": [],
        "risk_alerts": merged_risks,
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

    if not cleaned["actions"]:
        cleaned["actions"].append(highest_roi)

    return cleaned


def _generate_daily_coach_llm(
    norm_payload: Dict[str, Any],
    fat_loss_score: int,
    rule_alerts: List[Dict[str, str]],
    weekly_behavior: Optional[Dict[str, Any]] = None,
    weekly_predictive: Optional[Dict[str, Any]] = None,
    fast_mode: bool = False,
    tone_preference: str = "supportive",
) -> Dict[str, Any]:
    _require_gemini_key()
    user_prompt = _coach_user_prompt(
        norm_payload,
        fat_loss_score,
        rule_alerts,
        weekly_behavior=weekly_behavior,
        weekly_predictive=weekly_predictive,
        fast_mode=fast_mode,
        tone_preference=tone_preference,
    )
    timeout_sec = min(_llm_timeout(limit=10.0), 8.0) if fast_mode else _llm_timeout(limit=10.0)
    text, model_name, tried_models = _call_llm_with_timeout(
        [_COACH_SYSTEM_PROMPT, user_prompt],
        model_name=COACH_LLM_MODEL,
        timeout_sec=timeout_sec,
        retries=1,
        purpose="coach_daily",
    )
    parsed = coach_logic.extract_json_object(text)
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "coach_llm_failed", "raw": "LLM did not return valid JSON object.", "tried_models": tried_models},
        )

    cleaned = _coerce_coach_response_shape(parsed, rule_alerts, weekly_predictive=weekly_predictive)
    ok, reason = coach_logic.validate_llm_response_shape(cleaned)
    if not ok:
        raise HTTPException(
            status_code=502,
            detail={"error": "coach_llm_failed", "raw": f"LLM JSON failed validation: {reason}", "tried_models": tried_models},
        )
    cleaned["_llm_model_used"] = model_name
    return cleaned


def _public_predictive_signals(weekly_predictive: Optional[Dict[str, Any]], week_start_iso: str) -> Optional[Dict[str, Any]]:
    if not isinstance(weekly_predictive, dict):
        return None
    conf = str(weekly_predictive.get("projection_confidence_band") or "medium").strip().lower()
    if conf not in {"low", "medium", "high"}:
        conf = "medium"
    return {
        "week_start": str(weekly_predictive.get("week_start") or week_start_iso),
        "tz_used": str(weekly_predictive.get("tz_used") or ""),
        "days_tracked": int(_safe_float(weekly_predictive.get("days_tracked"), 0) or 0),
        "days_with_data_7d": int(_safe_float(weekly_predictive.get("days_with_data_7d"), 0) or 0),
        "scans_7d": int(_safe_float(weekly_predictive.get("scans_7d"), 0) or 0),
        "projection_confidence_band": conf,
        "missing_data_reason": str(weekly_predictive.get("missing_data_reason") or ""),
        "protein_consistency": _safe_float(weekly_predictive.get("protein_consistency"), 0.0),
        "fiber_consistency": _safe_float(weekly_predictive.get("fiber_consistency"), 0.0),
        "timing_volatility": _safe_float(weekly_predictive.get("timing_volatility"), 0.0),
        "diet_volatility_index": _safe_float(weekly_predictive.get("diet_volatility_index"), 0.0),
        "fat_loss_velocity_score": _safe_float(weekly_predictive.get("fat_loss_velocity_score"), 0.0),
        "fat_loss_probability_7d": _safe_float(weekly_predictive.get("fat_loss_probability_7d"), 0.0),
        "projection_7d_score": _safe_float(weekly_predictive.get("projection_7d_score"), 0.0),
        "energy_balance_trend_7d": weekly_predictive.get("energy_balance_trend_7d")
        if isinstance(weekly_predictive.get("energy_balance_trend_7d"), dict)
        else {},
        "hunger_volatility_projection": weekly_predictive.get("hunger_volatility_projection")
        if isinstance(weekly_predictive.get("hunger_volatility_projection"), dict)
        else {},
        "muscle_retention_risk": weekly_predictive.get("muscle_retention_risk")
        if isinstance(weekly_predictive.get("muscle_retention_risk"), dict)
        else {},
    }


def _ensure_coach_voice_defaults(resp: Dict[str, Any], weekly_predictive: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = dict(resp or {})
    conf = str((weekly_predictive or {}).get("projection_confidence_band") or "medium").strip().lower()
    if conf not in {"low", "medium", "high"}:
        conf = "medium"

    pattern = str(out.get("pattern_detected") or "").strip()
    roi = out.get("highest_roi_change") if isinstance(out.get("highest_roi_change"), dict) else {}
    roi_title = str(roi.get("title") or "").strip()
    roi_how = str(roi.get("how") or "").strip()

    one_liner = str(out.get("one_sentence_summary") or "").strip()
    if not one_liner:
        one_liner = f"{roi_title or 'Focus shift needed'} to improve weekly fat-loss direction."
    out["one_sentence_summary"] = " ".join(one_liner.split()[:18]).strip()

    proj_exp = str(out.get("projection_explained") or "").strip()
    if not proj_exp:
        proj_exp = f"Current 7-day direction has {conf} confidence based on recent consistency and scan coverage."
    elif conf not in proj_exp.lower():
        proj_exp = f"{proj_exp} Confidence: {conf}."
    out["projection_explained"] = proj_exp

    one_thing = str(out.get("if_you_do_one_thing") or "").strip()
    if not one_thing:
        one_thing = roi_how or "Front-load protein and fiber before dinner for better satiety control."
    out["if_you_do_one_thing"] = one_thing

    if not pattern:
        out["pattern_detected"] = "Daily pattern shows room to improve protein, fiber, and meal timing consistency."
    return out


def _latest_scan_meta(user_id: str, day_iso: str) -> Dict[str, str]:
    scan_id = ""
    scan_ts = ""
    meals_count_today = 0
    try:
        events = get_meal_events_for_day(user_id, day_iso)
    except Exception:
        events = []
    eligible_events: List[Dict[str, Any]] = []
    for e in (events or []):
        source = _event_text(e, "source", "event_source").lower()
        etype = _event_text(e, "event_type").lower()
        if source not in {"photo", "scan", "meal", ""} and etype not in {"photo_analyze", "analyze", "scan"}:
            continue
        eligible_events.append(e)
    meals_count_today = len(eligible_events)

    for e in reversed(eligible_events):
        event_json = _parse_jsonish(e.get("event_json"), {})
        extra = event_json.get("extra") if isinstance(event_json, dict) and isinstance(event_json.get("extra"), dict) else {}
        sid = str(extra.get("analysis_id") or "").strip()
        sts = str(e.get("created_at") or e.get("updated_at") or "").strip()
        if sid:
            scan_id = sid
            scan_ts = sts
            break

    if scan_id:
        return {"scan_id": scan_id, "scan_ts": scan_ts, "meals_count_today": str(meals_count_today)}

    # Fallback to meal_analyses table if available.
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            rows = sb_get_many(
                TBL_MEAL_ANALYSES,
                params={
                    "select": "analysis_id,created_at,day",
                    "user_id": f"eq.{user_id}",
                    "day": f"eq.{day_iso}",
                    "order": "created_at.desc",
                    "limit": "1",
                },
            )
            if rows:
                row = rows[0] or {}
                return {
                    "scan_id": str(row.get("analysis_id") or "").strip(),
                    "scan_ts": str(row.get("created_at") or "").strip(),
                    "meals_count_today": str(meals_count_today),
                }
        except Exception:
            pass
    return {"scan_id": "", "scan_ts": "", "meals_count_today": str(meals_count_today)}


def _build_server_daily_coach_payload(
    user_id: str,
    day_iso: str,
    *,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
) -> Dict[str, Any]:
    summary = build_daily_summary(user_id, day=day_iso, tz=tz, tz_offset_min=tz_offset_min)
    events = get_meal_events_for_day(user_id, day_iso)
    metrics = compute_daily_metrics_payload(user_id, day_iso, summary, events)
    mj = (metrics or {}).get("metrics_json") if isinstance((metrics or {}).get("metrics_json"), dict) else {}
    consumed = (mj.get("consumed") or {}) if isinstance(mj.get("consumed"), dict) else {}
    goals = (mj.get("goals") or {}) if isinstance(mj.get("goals"), dict) else {}
    sig = (mj.get("signals") or {}) if isinstance(mj.get("signals"), dict) else {}
    daily_totals_version = int(
        _safe_float(
            summary.get("daily_totals_version"),
            _safe_float((summary.get("totals") or {}).get("daily_totals_version"), 0.0),
        )
        or 0
    )
    profile_hint = _get_cached_user_coach_profile(user_id)
    hint_diet = coach_logic.normalize_diet_style(profile_hint.get("diet_style") or "non-veg")
    hint_goal = str(profile_hint.get("goal_type") or "fat_loss").strip().lower() or "fat_loss"
    hint_training_days = max(0, int(_safe_float(profile_hint.get("training_days_per_week"), 0) or 0))
    hint_training_time = str(profile_hint.get("training_time") or "evening").strip().lower() or "evening"
    hint_tone = _normalize_daily_tone_id(profile_hint.get("tone_preference") or "supportive")

    payload = {
        "date": day_iso,
        "goals": {
            "kcal": round(_safe_float(goals.get("kcal"), DEFAULT_DAILY_GOALS["kcal"]), 1),
            "protein_g": round(_safe_float(goals.get("protein_g"), DEFAULT_DAILY_GOALS["protein_g"]), 1),
            "carbs_g": round(_safe_float(goals.get("carbs_g"), DEFAULT_DAILY_GOALS["carbs_g"]), 1),
            "fat_g": round(_safe_float(goals.get("fat_g"), DEFAULT_DAILY_GOALS["fat_g"]), 1),
            "fiber_g": round(_safe_float(goals.get("fiber_g"), DEFAULT_DAILY_GOALS["fiber_g"]), 1),
        },
        "consumed": {
            "kcal": round(_safe_float(consumed.get("kcal"), 0.0), 1),
            "protein_g": round(_safe_float(consumed.get("protein_g"), 0.0), 1),
            "carbs_g": round(_safe_float(consumed.get("carbs_g"), 0.0), 1),
            "fat_g": round(_safe_float(consumed.get("fat_g"), 0.0), 1),
            "fiber_g": round(_safe_float(consumed.get("fiber_g"), 0.0), 1),
        },
        "signals": {
            "leucine_triggers": {
                "target": max(0.0, _safe_float(sig.get("leucine_triggers_target"), 3.0)),
                "hit": max(0.0, _safe_float(sig.get("leucine_triggers_hit"), 0.0)),
            },
            "avg_satiety": round(_safe_float(sig.get("avg_satiety"), 0.0), 1),
            "avg_glycemic_load": round(_safe_float(sig.get("avg_glycemic_load"), 0.0), 1),
            "ultra_processed_avg": round(_safe_float(sig.get("ultra_processed_avg"), 0.0), 1),
        },
        "meal_timing": {
            "late_calories_pct": round(_safe_float(sig.get("late_calories_pct"), 0.0), 1),
            "biggest_meal": str(sig.get("biggest_meal") or "dinner"),
        },
        "constraints": {"diet": hint_diet, "allergies": [], "region": "US"},
        "profile": {
            "goal_type": hint_goal,
            "diet_style": hint_diet,
            "training_days_per_week": hint_training_days,
            "training_time": hint_training_time,
            "tone_preference": hint_tone,
        },
        "tone_preference": hint_tone,
        "_state": {
            "scan_count": int(_safe_float(sig.get("meals_count"), 0) or 0),
            "day": day_iso,
            "daily_totals_version": daily_totals_version,
        },
        "daily_totals_version": str(daily_totals_version),
    }
    sig_seed = {
        "day": day_iso,
        "daily_totals_version": daily_totals_version,
        "scan_count": payload["_state"]["scan_count"],
        "totals": payload["consumed"],
        "upf": payload["signals"]["ultra_processed_avg"],
        "gl": payload["signals"]["avg_glycemic_load"],
    }
    payload["_state_signature"] = hashlib.sha256(
        json.dumps(sig_seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def _build_quick_fli_response(
    payload: Dict[str, Any],
    *,
    weekly_predictive: Optional[Dict[str, Any]] = None,
    latest_scan_id: str = "",
    latest_scan_ts: str = "",
    tone_preference: str = "supportive",
    user_id: str = "",
) -> Dict[str, Any]:
    norm = coach_logic.normalize_daily_payload(payload or {})
    tone_pref = _normalize_daily_tone_id(
        tone_preference
        or (payload.get("tone_preference") if isinstance(payload, dict) else "")
        or (((payload.get("profile") or {}) if isinstance(payload, dict) else {}).get("tone_preference"))
    )
    fat_loss_score = coach_logic.compute_fat_loss_score(norm)
    rule_alerts = coach_logic.build_rule_risk_alerts(norm)
    fb = coach_logic.build_fallback_coach_response(norm, fat_loss_score, rule_alerts)
    generated_ts = dt.datetime.utcnow().isoformat()
    out = {
        "date": str(norm.get("date") or _today_date().isoformat()),
        "fat_loss_score": int(fat_loss_score),
        "one_sentence_summary": str(fb.get("one_sentence_summary") or ""),
        "pattern_detected": str(fb.get("pattern_detected") or ""),
        "projection_explained": str(fb.get("projection_explained") or ""),
        "biggest_risk_lever": fb.get("biggest_risk_lever")
        if isinstance(fb.get("biggest_risk_lever"), dict)
        else {"title": "", "reason": ""},
        "highest_roi_change": fb.get("highest_roi_change")
        if isinstance(fb.get("highest_roi_change"), dict)
        else {"title": "", "why": "", "how": ""},
        "if_you_do_one_thing": str(fb.get("if_you_do_one_thing") or ""),
        "projection_7d": fb.get("projection_7d")
        if isinstance(fb.get("projection_7d"), dict)
        else {"if_unchanged": "", "if_improved": ""},
        "diagnosis": fb.get("diagnosis", []),
        "tomorrow_focus": fb.get("tomorrow_focus", []),
        "actions": (fb.get("actions") or [])[:2],
        "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, fb.get("risk_alerts", []), limit=4),
        "disclaimer": coach_logic.COACH_DISCLAIMER,
        "reasoning_source": "rules",
        "fli_source": "rules",
        "fli_reason_code": "",
        "fli_stale_seconds": 0,
        "fli_status": "ready",
        "source_display": "Coach",
        "source": "rules",
        "last_processed_scan_id": str(latest_scan_id or ""),
        "last_processed_scan_ts": str(latest_scan_ts or ""),
        "updatedAt": generated_ts,
        "coach_generated_ts": generated_ts,
        "payload_hash_used": coach_logic.payload_hash(norm),
        "insight_signature": coach_logic.payload_hash(norm),
        "daily_totals_version": str(
            payload.get("daily_totals_version")
            or ((payload.get("_state") or {}).get("daily_totals_version"))
            or (payload.get("_state_signature") or coach_logic.payload_hash(norm))
        ),
        "meals_count_today": int(_safe_float(((norm.get("signals") or {}).get("meals_count")), 0) or 0),
    }
    public_pred = _public_predictive_signals(weekly_predictive, _week_start_monday(out["date"]))
    if isinstance(public_pred, dict):
        out["predictive_signals"] = public_pred
    out = _ensure_coach_voice_defaults(out, weekly_predictive=weekly_predictive)
    out = _apply_tone_rewrite_to_coach_response(
        out,
        norm,
        tone_id=tone_pref,
        freshness="updated_now",
        max_actions=2,
        allow_llm=False,
    )
    recent_msgs: List[str] = []
    if str(user_id or "").strip():
        mem_day = _read_coach_memory_day(str(user_id or "").strip(), str(out.get("date") or norm.get("date") or _today_date().isoformat()))
        recent_msgs = _normalize_short_text_list(mem_day.get("last_3_coach_messages"), limit=3, max_chars=180)
    out = _apply_dynamic_coach_copy(
        out,
        norm,
        user_id=str(user_id or "").strip(),
        day_iso=str(out.get("date") or norm.get("date") or _today_date().isoformat()),
        scan_id=str(latest_scan_id or ""),
        scan_count=int(_safe_float(((norm.get("signals") or {}).get("meals_count")), 0) or 0),
        recent_messages=recent_msgs,
    )
    return out


def _warm_daily_coach_async(
    user_id: str,
    day_iso: str,
    *,
    latest_scan_id: str = "",
    latest_scan_ts: str = "",
    tone_preference: str = "supportive",
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
) -> None:
    def _job():
        try:
            payload = _build_server_daily_coach_payload(user_id, day_iso, tz=tz, tz_offset_min=tz_offset_min)
            coach_daily(
                payload=payload,
                user_id=user_id,
                refresh=True,
                tz=tz,
                tz_offset_min=tz_offset_min,
                fast=True,
                latest_scan_id=latest_scan_id or None,
                latest_scan_ts=latest_scan_ts or None,
                state_signature=str(payload.get("_state_signature") or ""),
                tone=tone_preference or None,
            )
        except Exception as e:
            logger.warning(f"FLI warm async failed: {e}")

    try:
        threading.Thread(target=_job, daemon=True).start()
    except Exception as e:
        logger.warning(f"FLI warm async thread start failed: {e}")


def _voice_metrics_from_request(req: CoachVoiceRequestModel) -> Dict[str, Any]:
    goals = req.goals or {}
    consumed = req.consumed or {}
    meals_raw = list(req.meals or [])
    meals: List[Dict[str, Any]] = []
    for m in meals_raw:
        if isinstance(m, dict):
            meals.append(dict(m))
            continue
        if hasattr(m, "model_dump"):
            try:
                meals.append(dict(m.model_dump()))
                continue
            except Exception:
                pass
        meals.append(
            {
                "meal_id": str(getattr(m, "meal_id", "") or ""),
                "ts": str(getattr(m, "ts", "") or ""),
                "label": str(getattr(m, "label", "") or ""),
                "kcal": _safe_float(getattr(m, "kcal", 0.0), 0.0),
                "protein_g": _safe_float(getattr(m, "protein_g", 0.0), 0.0),
                "carbs_g": _safe_float(getattr(m, "carbs_g", 0.0), 0.0),
                "fat_g": _safe_float(getattr(m, "fat_g", 0.0), 0.0),
                "confidence": _safe_float(getattr(m, "confidence", 0.0), 0.0),
                "notes": str(getattr(m, "notes", "") or ""),
            }
        )

    protein_gap = max(0.0, round(_safe_float(goals.get("protein_g"), 0.0) - _safe_float(consumed.get("protein_g"), 0.0), 1))
    fiber_gap = max(0.0, round(_safe_float(goals.get("fiber_g"), 0.0) - _safe_float(consumed.get("fiber_g"), 0.0), 1))
    kcal_delta = round(_safe_float(consumed.get("kcal"), 0.0) - _safe_float(goals.get("kcal"), 0.0), 1)
    avg_conf = round(
        _safe_avg(
            [
                _safe_float(m.get("confidence"), 0.0)
                for m in meals
            ]
        ),
        3,
    )

    late_kcal = 0.0
    total_meal_kcal = 0.0
    upf_hints = 0
    for m in meals:
        kcal = float(_safe_float(m.get("kcal"), 0.0) or 0.0)
        total_meal_kcal += kcal
        ts = _parse_iso_dt_naive(m.get("ts"))
        if ts and (ts.hour >= 19 or ts.hour <= 1):
            late_kcal += kcal
        notes = str(m.get("notes") or "").lower()
        label = str(m.get("label") or "").lower()
        if any(x in notes or x in label for x in ("fried", "packaged", "processed", "sugary", "dessert")):
            upf_hints += 1
    late_calories_pct = round(((late_kcal / total_meal_kcal) * 100.0), 1) if total_meal_kcal > 0 else 0.0

    return {
        "protein_gap": protein_gap,
        "fiber_gap": fiber_gap,
        "kcal_delta": kcal_delta,
        "avg_confidence": avg_conf,
        "late_calories_pct": late_calories_pct,
        "upf_hints": upf_hints,
        "meals_count": len(meals),
    }


def _voice_requested_tone(req: CoachVoiceRequestModel) -> str:
    raw = str(getattr(req, "tone_id", "") or getattr(req, "tone_preference", "") or "supportive")
    return _normalize_tone_preference(raw)


def _voice_action_templates(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    protein_gap = float(_safe_float((metrics or {}).get("protein_gap"), 0.0) or 0.0)
    fiber_gap = float(_safe_float((metrics or {}).get("fiber_gap"), 0.0) or 0.0)
    kcal_delta = float(_safe_float((metrics or {}).get("kcal_delta"), 0.0) or 0.0)
    late_pct = float(_safe_float((metrics or {}).get("late_calories_pct"), 0.0) or 0.0)
    avg_conf = float(_safe_float((metrics or {}).get("avg_confidence"), 1.0) or 1.0)
    upf_hints = int(_safe_float((metrics or {}).get("upf_hints"), 0) or 0)

    if avg_conf < 0.55:
        out.append(
            {
                "advice_key": "confirm_cooking_oil_and_portion",
                "title": "Confirm cooking + portion",
                "steps": [
                    "Open Edit on this meal",
                    "Set cooking method and oil",
                    "Confirm portion size once",
                ],
                "why": "This improves scan accuracy before we optimize your next action.",
            }
        )
        out.append(
            {
                "advice_key": "scan_two_more_days",
                "title": "Build stronger data confidence",
                "steps": [
                    "Log your next 2 days",
                    "Keep portions consistent",
                    "Recheck Fat Loss Intelligence",
                ],
                "why": "More data makes coaching more accurate and less repetitive.",
            }
        )
    if protein_gap >= 25:
        out.append(
            {
                "advice_key": "protein_anchor_next_meal",
                "title": "Anchor next meal with protein",
                "steps": [
                    "Pick one main protein source",
                    "Target 30-40g protein",
                    "Pair with vegetables or salad",
                ],
                "why": "Closing the protein shortfall improves satiety and recovery quality.",
            }
        )
    if fiber_gap >= 8:
        out.append(
            {
                "advice_key": "fiber_boost_next_meal",
                "title": "Add one fiber booster",
                "steps": [
                    "Add a vegetable side",
                    "Include beans or whole grain",
                    "Keep refined carbs smaller",
                ],
                "why": "Higher fiber helps reduce hunger swings later in the day.",
            }
        )
    if late_pct >= 45:
        out.append(
            {
                "advice_key": "front_load_day_calories",
                "title": "Shift calories earlier",
                "steps": [
                    "Add protein at breakfast",
                    "Eat a structured lunch",
                    "Keep dinner lighter",
                ],
                "why": "Lower late-calorie load usually improves appetite control.",
            }
        )
    if upf_hints >= 1:
        out.append(
            {
                "advice_key": "swap_one_upf_item",
                "title": "Swap one processed item",
                "steps": [
                    "Identify one packaged food",
                    "Replace with whole-food option",
                    "Keep same calories",
                ],
                "why": "This can improve satiety quality without increasing calories.",
            }
        )
    if kcal_delta > 250:
        out.append(
            {
                "advice_key": "tighten_evening_portion",
                "title": "Tighten evening portion",
                "steps": [
                    "Reduce dinner carbs by 20%",
                    "Keep protein unchanged",
                    "Add water before meal",
                ],
                "why": "Small evening control reduces overshoot without aggressive restriction.",
            }
        )
    if not out:
        out.append(
            {
                "advice_key": "hold_consistency_tonight",
                "title": "Hold consistency tonight",
                "steps": [
                    "Repeat your balanced pattern",
                    "Keep portion stable",
                    "Log the next meal",
                ],
                "why": "Consistency compounds more than perfect one-off meals.",
            }
        )
    return out


def _pick_non_repeating_advice_key(candidates: List[Dict[str, Any]], recent_keys: List[str]) -> Dict[str, Any]:
    seen = set(_normalize_semantic_key_list(recent_keys, limit=32))
    for c in (candidates or []):
        key = _normalize_semantic_key(c.get("advice_key"))
        if key and key not in seen:
            return c
    return (candidates or [{}])[0]


def _voice_fallback_response(
    req: CoachVoiceRequestModel,
    recent_keys: List[str],
    *,
    timeout_mode: bool = False,
) -> Dict[str, Any]:
    metrics = _voice_metrics_from_request(req)
    candidate = _pick_non_repeating_advice_key(_voice_action_templates(metrics), recent_keys)
    tone_pref = _voice_requested_tone(req)
    tone_map = {
        "supportive": "supportive",
        "strict": "firm",
        "funny": "celebratory",
        "indian_coach": "supportive",
    }
    tone_tag = tone_map.get(tone_pref, "neutral")

    empathy = "Good job logging this meal. Small changes now will compound."
    if tone_pref == "strict":
        empathy = "Logged. Now execute one correction."
    elif tone_pref == "funny":
        empathy = "Nice check-in. Let’s win this next meal."
    elif tone_pref == "indian_coach":
        empathy = "Boss, meal logged. Chalo ek strong next step set karte hain."

    protein_gap = float(_safe_float(metrics.get("protein_gap"), 0.0) or 0.0)
    fiber_gap = float(_safe_float(metrics.get("fiber_gap"), 0.0) or 0.0)
    late_pct = float(_safe_float(metrics.get("late_calories_pct"), 0.0) or 0.0)
    avg_conf = float(_safe_float(metrics.get("avg_confidence"), 1.0) or 1.0)
    if timeout_mode:
        insight = "I’m still refining details. Use one practical step now while your full coaching updates."
    elif avg_conf < 0.55:
        insight = "This scan likely needs one quick confirmation before precision coaching."
    elif protein_gap >= fiber_gap and protein_gap > 0:
        insight = f"Protein shortfall is still about {round(protein_gap, 1)}g, which is the main limiter today."
    elif fiber_gap > 0:
        insight = f"Fiber is short by about {round(fiber_gap, 1)}g, which may increase evening hunger."
    elif late_pct >= 45:
        insight = f"Calories are back-loaded ({round(late_pct, 1)}% late), so timing is the main lever."
    else:
        insight = "Your day is close to target; consistency is now the highest-ROI lever."

    out = {
        "coach_generated_ts": _now_utc_naive().isoformat(),
        "tone_tag": tone_tag,
        "empathy_line": _limit_text(empathy, 120),
        "insight_line": _limit_text(insight, 200),
        "one_action": {
            "title": _limit_text(str(candidate.get("title") or "One next step"), 64),
            "steps": [str(x)[:120] for x in (candidate.get("steps") or []) if str(x).strip()][:3] or ["Log your next meal."],
        },
        "why_this_action": _limit_text(str(candidate.get("why") or "It addresses today’s main nutrition limiter."), 220),
        "advice_key": _normalize_semantic_key(candidate.get("advice_key") or "consistency_focus"),
        "safety_disclaimer": "Informational only. Not medical advice.",
    }
    return out


def _coerce_voice_output(
    raw: Dict[str, Any],
    req: CoachVoiceRequestModel,
    recent_keys: List[str],
) -> Dict[str, Any]:
    fallback = _voice_fallback_response(req, recent_keys, timeout_mode=False)
    metrics = _voice_metrics_from_request(req)

    tone_pref = _voice_requested_tone(req)
    default_tone = {
        "supportive": "supportive",
        "strict": "firm",
        "funny": "celebratory",
        "indian_coach": "supportive",
    }.get(tone_pref, "neutral")
    tone_tag = _normalize_tone_tag(raw.get("tone_tag"), fallback=default_tone)
    empathy_line = _limit_text(raw.get("empathy_line"), 120) or fallback["empathy_line"]
    insight_line = _limit_text(raw.get("insight_line"), 200) or fallback["insight_line"]

    action_obj = raw.get("one_action") if isinstance(raw.get("one_action"), dict) else {}
    title = _limit_text(action_obj.get("title"), 64) or fallback["one_action"]["title"]
    steps = action_obj.get("steps") if isinstance(action_obj.get("steps"), list) else []
    steps = [str(s).strip()[:120] for s in steps if str(s).strip()][:3]
    if not steps:
        steps = list(fallback["one_action"]["steps"])

    why = _limit_text(raw.get("why_this_action"), 220) or fallback["why_this_action"]
    advice_key = _normalize_semantic_key(raw.get("advice_key"))
    if not advice_key:
        advice_key = fallback["advice_key"]
    if advice_key in set(_normalize_semantic_key_list(recent_keys, limit=32)):
        advice_key = fallback["advice_key"]
        title = fallback["one_action"]["title"]
        steps = list(fallback["one_action"]["steps"])
        why = fallback["why_this_action"]

    grounded_words = ("protein", "fiber", "calorie", "upf", "glycemic", "late")
    if not any(w in insight_line.lower() for w in grounded_words):
        protein_gap = float(_safe_float(metrics.get("protein_gap"), 0.0) or 0.0)
        fiber_gap = float(_safe_float(metrics.get("fiber_gap"), 0.0) or 0.0)
        if protein_gap > 0:
            insight_line = _limit_text(f"{insight_line} Protein shortfall remains around {round(protein_gap, 1)}g.", 200)
        elif fiber_gap > 0:
            insight_line = _limit_text(f"{insight_line} Fiber shortfall remains around {round(fiber_gap, 1)}g.", 200)

    disclaimer = _limit_text(raw.get("safety_disclaimer"), 140) or "Informational only. Not medical advice."
    return {
        "coach_generated_ts": str(raw.get("coach_generated_ts") or _now_utc_naive().isoformat()),
        "tone_tag": tone_tag,
        "empathy_line": empathy_line,
        "insight_line": insight_line,
        "one_action": {"title": title, "steps": steps},
        "why_this_action": why,
        "advice_key": advice_key,
        "safety_disclaimer": disclaimer,
    }


def _generate_human_coach_voice_llm(
    req: CoachVoiceRequestModel,
    recent_keys: List[str],
) -> Dict[str, Any]:
    _require_gemini_key()
    metrics = _voice_metrics_from_request(req)
    tone_pref = _voice_requested_tone(req)
    candidate_actions = _voice_action_templates(metrics)
    allowed_keys = [_normalize_semantic_key(a.get("advice_key")) for a in candidate_actions if _normalize_semantic_key(a.get("advice_key"))]
    recent_norm = _normalize_semantic_key_list(recent_keys, limit=24)
    payload = {
        "day": _safe_day_iso(req.day),
        "goals": req.goals,
        "consumed": req.consumed,
        "metrics": metrics,
        "user_profile": _model_dump(req.user_profile),
        "tone_preference": tone_pref,
        "allowed_actions": candidate_actions,
        "recent_advice_keys": recent_norm,
    }
    schema = {
        "coach_generated_ts": "ISO",
        "tone_tag": "supportive|firm|celebratory|neutral",
        "empathy_line": "string <=120 chars",
        "insight_line": "string <=200 chars",
        "one_action": {"title": "string", "steps": ["string", "string", "string"]},
        "why_this_action": "string",
        "advice_key": "string",
        "safety_disclaimer": "string",
    }
    prompt = (
        "Return strict JSON only, no markdown, no extra keys.\n"
        "No medical claims or diagnosis.\n"
        "Keep empathy_line short and human.\n"
        "insight_line must reference measurable context.\n"
        "Choose exactly one action from allowed_actions and use its advice_key.\n"
        "Avoid advice keys that appear in recent_advice_keys unless no other option exists.\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}\n"
        f"Output schema:\n{json.dumps(schema, ensure_ascii=True)}"
    )
    text, model_name, tried_models = _call_llm_with_timeout(
        [_COACH_VOICE_SYSTEM_PROMPT, prompt],
        model_name=COACH_VOICE_LLM_MODEL,
        timeout_sec=min(float(COACH_VOICE_TIMEOUT_SEC), 8.0),
        retries=1,
        purpose="coach_voice_human",
    )
    parsed = coach_logic.extract_json_object(str(text or "").strip())
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "coach_voice_llm_failed", "raw": "Coach voice output is not valid JSON.", "tried_models": tried_models},
        )
    parsed["_llm_model_used"] = model_name
    return parsed


@app.post("/coach/voice")
def coach_voice(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(CoachVoiceRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_coach_voice_payload", "raw": str(e)[:300]})

    uid = require_user_id(x_user_id, user_id or req.user_id)
    require_ai_consent(uid)
    day_iso = _safe_day_iso(req.day)
    tone_pref = _voice_requested_tone(req)
    _cache_user_coach_profile(uid, _model_dump(req.user_profile), tone_pref)
    payload_hash = str(req.payload_hash or "").strip()
    if not payload_hash:
        payload_hash = hashlib.sha256(
            json.dumps(
                {
                    "day": day_iso,
                    "goals": req.goals,
                    "consumed": req.consumed,
                    "meals": [_model_dump(m) for m in (req.meals or [])],
                    "tone_preference": tone_pref,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    cached = _coach_voice_cache_get(uid, day_iso, payload_hash, tone_pref)
    if isinstance(cached, dict):
        cached_out = dict(cached)
        cached_out["tone_requested"] = _normalize_daily_tone_id(cached_out.get("tone_requested") or tone_pref)
        cached_out["tone_used"] = cached_out["tone_requested"]
        cached_out["source"] = "cache"
        cached_out["tone_mode"] = _tone_mode_from_source(cached_out.get("source"))
        return _attach_debug_schema(cached_out, bool(debug))

    mem_window = _read_coach_memory_window(uid, day_iso)
    recent_keys = _normalize_semantic_key_list(
        [m.advice_key for m in (req.recent_messages or [])] + list(mem_window.get("recent_advice_keys") or []),
        limit=32,
    )

    output: Dict[str, Any]
    voice_source = "rules"
    voice_model_used = ""
    voice_reason_code = ""
    voice_tried_models: List[str] = []
    if GEMINI_API_KEY:
        try:
            llm_raw = _generate_human_coach_voice_llm(req, recent_keys)
            output = _coerce_voice_output(llm_raw, req, recent_keys)
            voice_source = "llm"
            voice_model_used = str((llm_raw or {}).get("_llm_model_used") or "").strip()
        except Exception as e:
            voice_reason_code, voice_tried_models, _ = _extract_llm_failure_debug(e)
            logger.warning(f"coach voice llm failed, using fallback: {e}")
            output = _voice_fallback_response(req, recent_keys, timeout_mode=True)
    else:
        output = _voice_fallback_response(req, recent_keys, timeout_mode=False)
        voice_reason_code = "NO_GEMINI_KEY"

    output["source"] = voice_source
    output["llm_model_used"] = voice_model_used
    output["llm_error_code"] = voice_reason_code if voice_source != "llm" else ""
    output["llm_tried_models"] = voice_tried_models if voice_source != "llm" else ([] if not voice_model_used else [voice_model_used])
    output["tone_requested"] = tone_pref
    output["tone_used"] = tone_pref
    output["tone_mode"] = _tone_mode_from_source(voice_source)

    _append_coach_memory_entry(
        uid,
        day_iso,
        output.get("advice_key"),
        f"{output.get('empathy_line', '')} {output.get('insight_line', '')}".strip(),
    )
    _coach_voice_cache_set(uid, day_iso, payload_hash, tone_pref, output)
    return _attach_debug_schema(output, bool(debug))


@app.post("/coach/memory/feedback")
def coach_memory_feedback(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(CoachFeedbackRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_feedback_payload", "raw": str(e)[:280]})

    uid = require_user_id(x_user_id, user_id or req.user_id)
    feedback_type = _feedback_type_normalize(req.feedback_type)
    rating = None if req.rating is None else max(1, min(5, int(_safe_float(req.rating, 3) or 3)))
    corr = req.corrections or CoachFeedbackCorrectionsModel()
    food_key = _derive_feedback_food_key(req)
    correction_method = str(corr.cooking_method or "").strip().lower()
    correction_oil = corr.oil_added_tsp
    correction_portion = corr.portion_multiplier
    confirmed_items = [
        {"name": str(ci.name or "").strip(), "grams": float(_safe_float(ci.grams, 0.0) or 0.0)}
        for ci in (corr.confirmed_items or [])
        if str(ci.name or "").strip()
    ]

    row = {
        "id": str(uuid.uuid4()),
        "feedback_id": str(uuid.uuid4()),
        "user_id": uid,
        "analysis_id": str(req.analysis_id or "").strip(),
        "meal_id": str(req.meal_id or "").strip(),
        "feedback_type": feedback_type,
        "rating": rating,
        "free_text": str(req.free_text or "").strip()[:500],
        "corrections_json": _model_dump(corr),
        "corrections": _model_dump(corr),
        "item_name": str(corr.item_name or "").strip(),
        "item_id": str(corr.item_id or "").strip(),
        "cooking_method": correction_method,
        "oil_added_tsp": correction_oil,
        "portion_multiplier": correction_portion,
        "confirmed_items": confirmed_items,
        "created_at": _now_utc_naive().isoformat(),
    }
    try:
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            _sb_insert_with_column_fallback(TBL_COACH_FEEDBACK, row)
    except Exception as e:
        logger.info(f"coach feedback write skipped: {e}")

    updated_prior: Dict[str, Any] = {}
    if food_key:
        updated_prior = _upsert_user_food_prior(
            uid,
            food_key,
            rating=rating,
            portion_multiplier=correction_portion,
            oil_added_tsp=correction_oil,
            cooking_method=correction_method,
        )

    return {
        "ok": True,
        "priors_updated": bool(updated_prior),
        "updated_food_key": str(updated_prior.get("food_key") or food_key or ""),
        "new_priors": {
            "portion_multiplier_mean": float(_safe_float(updated_prior.get("portion_multiplier_mean"), 1.0) or 1.0),
            "oil_tsp_mean": float(_safe_float(updated_prior.get("oil_tsp_mean"), 0.0) or 0.0),
            "always_ask_oil_for_methods": updated_prior.get("always_ask_oil_for_methods") or [],
        },
    }


@app.post("/confidence/calibration/recompute")
def confidence_calibration_recompute(days: int = 7):
    return compute_confidence_calibration(days=days)


@app.get("/confidence/calibration/report")
def confidence_calibration_report(
    prediction_type: Optional[str] = None,
    days: int = 7,
):
    settings = load_confidence_calibration_settings()
    p = str(prediction_type or "").strip().lower()
    if p:
        rows = _fetch_confidence_audit_rows(prediction_type=p, days=days)
        metrics = _aggregate_confidence_rows(rows)
        return {
            "prediction_type": p,
            "last_7d": {
                "total": int(metrics.get("total") or 0),
                "avg_confidence": float(metrics.get("avg_confidence") or 0.0),
                "avg_error": float(metrics.get("avg_error") or 0.0),
                "pct_within_range": float(metrics.get("pct_within_range") or 0.0),
            },
            "calibrated_threshold": _calibration_setting_value(
                settings,
                p,
                "confidence_threshold",
                DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS.get(p, {}).get("confidence_threshold", 0.75),
            ),
            "range_expansion_factor": _calibration_setting_value(
                settings,
                p,
                "range_expansion_factor",
                DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS.get(p, {}).get("range_expansion_factor", 1.0),
            ),
        }

    out: Dict[str, Any] = {}
    for key in ("portion", "oil", "vision"):
        rows = _fetch_confidence_audit_rows(prediction_type=key, days=days)
        metrics = _aggregate_confidence_rows(rows)
        out[key] = {
            "prediction_type": key,
            "last_7d": {
                "total": int(metrics.get("total") or 0),
                "avg_confidence": float(metrics.get("avg_confidence") or 0.0),
                "avg_error": float(metrics.get("avg_error") or 0.0),
                "pct_within_range": float(metrics.get("pct_within_range") or 0.0),
            },
            "calibrated_threshold": _calibration_setting_value(
                settings,
                key,
                "confidence_threshold",
                DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS[key]["confidence_threshold"],
            ),
            "range_expansion_factor": _calibration_setting_value(
                settings,
                key,
                "range_expansion_factor",
                DEFAULT_CONFIDENCE_CALIBRATION_SETTINGS[key]["range_expansion_factor"],
            ),
        }
    return {"prediction_types": out, "updated_at": _now_utc_naive().isoformat()}


def _weekly_report_fallback(
    week_start_iso: str,
    rows: List[Dict[str, Any]],
    weekly_predictive: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    week_end_iso = _week_end_from_start(week_start_iso)
    days_logged = len(rows or [])
    avg_protein_g = round(_safe_avg([_extract_metric_val(r, "protein_consumed_g") for r in rows]), 1)
    avg_upf = round(_safe_avg([_extract_metric_val(r, "ultra_processed_avg") for r in rows]), 1)
    late_pct = round(_safe_avg([_extract_metric_val(r, "late_calories_pct") for r in rows]), 1)
    day_scores = [_day_score_from_metric_row(r) for r in rows]
    resilience = int(round(_safe_avg(day_scores), 0)) if day_scores else 45
    resilience = max(0, min(100, resilience))
    risk = max(0, min(100, int(round(100 - resilience, 0))))

    scans_7d = int(_safe_float((weekly_predictive or {}).get("scans_7d"), 0) or 0)
    conf = str((weekly_predictive or {}).get("projection_confidence_band") or "").strip().lower()
    if conf not in {"low", "medium", "high"}:
        if days_logged >= 6 and scans_7d >= 6:
            conf = "high"
        elif days_logged >= 4:
            conf = "medium"
        else:
            conf = "low"

    top_risks: List[Dict[str, str]] = []
    top_wins: List[Dict[str, str]] = []
    next_plan: List[Dict[str, Any]] = []

    if avg_protein_g > 0 and avg_protein_g < 100:
        top_risks.append(
            {
                "title": "Protein consistency risk",
                "reason": f"Average protein is {avg_protein_g}g, which may limit satiety and recovery.",
                "signal": "avg_protein_g",
            }
        )
    if avg_upf >= 6:
        top_risks.append(
            {
                "title": "Ultra-processed load high",
                "reason": f"Average UPF score is {avg_upf}/10, increasing appetite volatility risk.",
                "signal": "avg_upf_score",
            }
        )
    if late_pct >= 45:
        top_risks.append(
            {
                "title": "Late-calorie clustering",
                "reason": f"{late_pct}% of calories are late, which can destabilize appetite patterns.",
                "signal": "late_calories_pct",
            }
        )
    if not top_risks:
        top_risks.append(
            {
                "title": "Data confidence risk",
                "reason": "Low tracked days limits precision of pattern detection.",
                "signal": "days_logged",
            }
        )

    if days_logged >= 5:
        top_wins.append(
            {
                "title": "Strong logging adherence",
                "why_it_matters": "Consistent logging improves coaching precision and behavior momentum.",
            }
        )
    if avg_upf < 5:
        top_wins.append(
            {
                "title": "Whole-food quality trend",
                "why_it_matters": "Lower processed-food load supports better satiety control.",
            }
        )
    if resilience >= 60:
        top_wins.append(
            {
                "title": "Readiness trend is stable",
                "why_it_matters": "Stable readiness indicates improved consistency across the week.",
            }
        )
    if not top_wins:
        top_wins.append(
            {
                "title": "Baseline established",
                "why_it_matters": "You now have enough data to improve week-over-week decisions.",
            }
        )

    next_plan.append(
        {
            "title": "Protein-first planning",
            "steps": ["Anchor breakfast protein", "Hit one high-protein lunch option"],
        }
    )
    next_plan.append(
        {
            "title": "Timing cleanup",
            "steps": ["Shift part of dinner earlier", "Keep late snacks controlled"],
        }
    )

    data_quality_reasons = []
    if days_logged < 4:
        data_quality_reasons.append("Low tracked days this week.")
    if scans_7d < 4:
        data_quality_reasons.append("Low scan frequency reduces confidence.")
    quality_score = int(round(min(100.0, (days_logged / 7.0) * 70.0 + min(scans_7d, 7) * 4.0), 0))

    return {
        "week_start": week_start_iso,
        "week_end": week_end_iso,
        "resilience_score": resilience,
        "risk_score": risk,
        "confidence_band": conf,
        "top_risks": top_risks[:3],
        "top_wins": top_wins[:3],
        "next_week_plan": next_plan[:3],
        "report_card_facts": {
            "avg_protein_g": avg_protein_g,
            "avg_upf_score": avg_upf,
            "late_calories_pct": late_pct,
            "days_logged": days_logged,
        },
        "data_quality": {
            "score": quality_score,
            "reasons": data_quality_reasons[:3],
        },
        "disclaimer": "Informational only. Not medical advice.",
    }


def _coerce_weekly_report_shape(raw: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "week_start": str(raw.get("week_start") or fallback["week_start"]),
        "week_end": str(raw.get("week_end") or fallback["week_end"]),
        "resilience_score": int(max(0, min(100, _safe_float(raw.get("resilience_score"), fallback["resilience_score"]) or fallback["resilience_score"]))),
        "risk_score": int(max(0, min(100, _safe_float(raw.get("risk_score"), fallback["risk_score"]) or fallback["risk_score"]))),
        "confidence_band": str(raw.get("confidence_band") or fallback["confidence_band"]).strip().lower(),
        "top_risks": raw.get("top_risks") if isinstance(raw.get("top_risks"), list) else fallback["top_risks"],
        "top_wins": raw.get("top_wins") if isinstance(raw.get("top_wins"), list) else fallback["top_wins"],
        "next_week_plan": raw.get("next_week_plan") if isinstance(raw.get("next_week_plan"), list) else fallback["next_week_plan"],
        "report_card_facts": fallback["report_card_facts"],
        "data_quality": fallback["data_quality"],
        "disclaimer": str(raw.get("disclaimer") or fallback["disclaimer"]),
    }
    if out["confidence_band"] not in {"low", "medium", "high"}:
        out["confidence_band"] = fallback["confidence_band"]
    out["top_risks"] = [x for x in out["top_risks"] if isinstance(x, dict)][:3] or list(fallback["top_risks"])
    out["top_wins"] = [x for x in out["top_wins"] if isinstance(x, dict)][:3] or list(fallback["top_wins"])
    out["next_week_plan"] = [x for x in out["next_week_plan"] if isinstance(x, dict)][:3] or list(fallback["next_week_plan"])
    return out


def _generate_weekly_report_llm(base_payload: Dict[str, Any], tone_preference: str) -> Dict[str, Any]:
    _require_gemini_key()
    schema = {
        "week_start": "YYYY-MM-DD",
        "week_end": "YYYY-MM-DD",
        "resilience_score": 0,
        "risk_score": 0,
        "confidence_band": "low|medium|high",
        "top_risks": [{"title": "string", "reason": "string", "signal": "string"}],
        "top_wins": [{"title": "string", "why_it_matters": "string"}],
        "next_week_plan": [{"title": "string", "steps": ["string", "string"]}],
        "report_card_facts": {"avg_protein_g": 0, "avg_upf_score": 0, "late_calories_pct": 0, "days_logged": 0},
        "disclaimer": "Informational only. Not medical advice.",
    }
    prompt = (
        "Return strict JSON only, no markdown, no extra keys.\n"
        "No medical diagnosis or treatment claims.\n"
        "Use only the provided deterministic metrics.\n"
        f"Tone preference: {_normalize_tone_preference(tone_preference)}\n"
        f"Input:\n{json.dumps(base_payload, ensure_ascii=True)}\n"
        f"Output schema:\n{json.dumps(schema, ensure_ascii=True)}"
    )
    text, model_name, tried_models = _call_llm_with_timeout(
        [_COACH_SYSTEM_PROMPT, prompt],
        model_name=COACH_LLM_MODEL,
        timeout_sec=_llm_timeout(limit=10.0),
        retries=1,
        purpose="weekly_report",
    )
    parsed = coach_logic.extract_json_object(str((text or "")).strip())
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "weekly_report_llm_failed", "raw": "weekly report output invalid JSON", "tried_models": tried_models},
        )
    parsed["_llm_model_used"] = model_name
    return parsed


@app.post("/coach/weekly_report")
def coach_weekly_report(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(WeeklyReportRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_weekly_report_payload", "raw": str(e)[:280]})

    uid = require_user_id(x_user_id, user_id or req.user_id)
    require_ai_consent(uid)
    anchor_day = _safe_day_iso(req.week_start or _today_date(tz=req.tz or None, tz_offset_min=req.tz_offset_min).isoformat())
    week_start_iso = _week_start_monday(anchor_day)

    rows = [r for r in (req.daily_rows or []) if isinstance(r, dict)]
    if not rows:
        try:
            rows = get_daily_metrics_window(uid, week_start_iso)
        except Exception:
            rows = []
    weekly_predictive = get_user_weekly_metrics_payload(uid, week_start_iso) if (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY) else None
    fallback = _weekly_report_fallback(week_start_iso, rows, weekly_predictive)
    cache_hash = hashlib.sha256(
        json.dumps(
            {
                "uid": uid,
                "week_start": week_start_iso,
                "rows": rows,
                "predictive": weekly_predictive or {},
                "tone": _normalize_tone_preference(req.tone_preference),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    cached = _weekly_report_cache_get(uid, week_start_iso, cache_hash)
    if isinstance(cached, dict):
        return cached

    out = dict(fallback)
    if GEMINI_API_KEY:
        try:
            llm_raw = _generate_weekly_report_llm(
                {
                    "fallback": fallback,
                    "weekly_predictive": weekly_predictive or {},
                    "training_days_per_week": int(_safe_float(req.training_days_per_week, 0) or 0),
                },
                req.tone_preference,
            )
            out = _coerce_weekly_report_shape(llm_raw, fallback)
        except Exception as e:
            logger.warning(f"weekly report llm failed, using fallback: {e}")
    _weekly_report_cache_set(uid, week_start_iso, cache_hash, out)
    return out


def _generate_program_plan_fallback(req: ProgramCreateRequestModel) -> Dict[str, Any]:
    goal = str(req.program_goal or "fat_loss").strip().lower()
    weeks = int(max(4, min(24, req.duration_weeks)))
    return {
        "program_goal": goal,
        "duration_weeks": weeks,
        "weekly_targets": [
            {"week": 1, "focus": "logging_consistency", "target": "Log at least 5 days"},
            {"week": 2, "focus": "protein_anchor", "target": "Hit protein anchor in first 2 meals"},
            {"week": 3, "focus": "fiber_and_timing", "target": "Add fiber and reduce late-calorie load"},
        ],
        "daily_checkin_prompt": "How consistent were your meals today, and what is one correction for tonight?",
    }


@app.post("/program/create")
def program_create(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(ProgramCreateRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_program_create_payload", "raw": str(e)[:280]})
    uid = require_user_id(x_user_id, user_id or req.user_id)
    now = _now_utc_naive().isoformat()
    plan = _generate_program_plan_fallback(req)
    row = {
        "program_id": str(uuid.uuid4()),
        "user_id": uid,
        "program_goal": str(plan.get("program_goal") or "fat_loss"),
        "duration_weeks": int(_safe_float(plan.get("duration_weeks"), 12) or 12),
        "status": "active",
        "plan_json": plan,
        "created_at": now,
        "updated_at": now,
    }
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            existing = sb_get_one(
                TBL_PROGRAM_STATUS,
                params={"select": "*", "user_id": f"eq.{uid}", "status": "eq.active", "limit": "1"},
            )
            if existing:
                _sb_patch_with_column_fallback(
                    TBL_PROGRAM_STATUS,
                    {"user_id": f"eq.{uid}", "status": "eq.active"},
                    {
                        "program_goal": row["program_goal"],
                        "duration_weeks": row["duration_weeks"],
                        "plan_json": row["plan_json"],
                        "updated_at": now,
                    },
                )
            else:
                _sb_insert_with_column_fallback(TBL_PROGRAM_STATUS, row)
        except Exception as e:
            logger.info(f"program create write skipped: {e}")
    return {"ok": True, "program": row}


@app.post("/program/daily_checkin")
def program_daily_checkin(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(ProgramDailyCheckinRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_program_checkin_payload", "raw": str(e)[:280]})
    uid = require_user_id(x_user_id, user_id or req.user_id)
    checkin = {
        "date": _safe_day_iso(req.date),
        "adherence_score": _safe_float(req.adherence_score, None),
        "notes": str(req.notes or "")[:300],
        "signals": req.signals if isinstance(req.signals, dict) else {},
        "ts": _now_utc_naive().isoformat(),
    }
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            existing = sb_get_one(
                TBL_PROGRAM_STATUS,
                params={"select": "*", "user_id": f"eq.{uid}", "status": "eq.active", "limit": "1"},
            )
            if existing:
                history = _parse_jsonish(existing.get("checkins_json"), [])
                if not isinstance(history, list):
                    history = []
                history.append(checkin)
                history = history[-30:]
                _sb_patch_with_column_fallback(
                    TBL_PROGRAM_STATUS,
                    {"user_id": f"eq.{uid}", "status": "eq.active"},
                    {"checkins_json": history, "updated_at": _now_utc_naive().isoformat()},
                )
        except Exception as e:
            logger.info(f"program checkin write skipped: {e}")
    return {"ok": True, "checkin": checkin}


@app.get("/program/status")
def program_status(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return {"ok": True, "program": None}
    try:
        row = sb_get_one(
            TBL_PROGRAM_STATUS,
            params={"select": "*", "user_id": f"eq.{uid}", "status": "eq.active", "order": "updated_at.desc", "limit": "1"},
        )
        return {"ok": True, "program": row or None}
    except Exception as e:
        logger.info(f"program status read skipped: {e}")
        return {"ok": True, "program": None}


@app.post("/coach/daily")
def coach_daily(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    refresh: Optional[bool] = False,
    fast: Optional[bool] = False,
    debug: Optional[bool] = False,
    tone: Optional[str] = None,
    tone_id: Optional[str] = None,
    latest_scan_id: Optional[str] = None,
    latest_scan_ts: Optional[str] = None,
    meal_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
    state_signature: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """
    Deterministic score + LLM reasoning layer.
    Numbers are always computed by Python rules; LLM only interprets.
    """
    uid = require_user_id(x_user_id, user_id)
    require_ai_consent(uid)
    request_id = _new_request_id()
    started = time.time()
    norm = coach_logic.normalize_daily_payload(payload or {})
    incoming_profile = payload.get("profile") if isinstance(payload, dict) and isinstance(payload.get("profile"), dict) else {}
    tone_pref = _normalize_daily_tone_id(
        tone_id
        or tone
        or (payload.get("tone_preference") if isinstance(payload, dict) else "")
        or incoming_profile.get("tone_preference")
        or "supportive"
    )
    norm["tone_preference"] = tone_pref
    if not isinstance(norm.get("profile"), dict):
        norm["profile"] = {}
    norm["profile"]["tone_preference"] = tone_pref
    _cache_user_coach_profile(uid, norm.get("profile") if isinstance(norm.get("profile"), dict) else {}, tone_pref)
    if not norm.get("date"):
        norm["date"] = _today_date().isoformat()

    fat_loss_score = coach_logic.compute_fat_loss_score(norm)
    rule_alerts = coach_logic.build_rule_risk_alerts(norm)
    p_hash = hashlib.sha256(f"{coach_logic.payload_hash(norm)}:tone:{tone_pref}".encode("utf-8")).hexdigest()
    day_iso = str(norm.get("date") or _today_date().isoformat())
    requested_meal_id = str(
        meal_id
        or (payload.get("meal_id") if isinstance(payload, dict) else "")
        or ""
    ).strip()
    requested_analysis_id = str(
        analysis_id
        or (payload.get("analysis_id") if isinstance(payload, dict) else "")
        or requested_meal_id
        or ""
    ).strip()
    requested_input_scan_id = str(
        latest_scan_id
        or (payload.get("input_scan_id") if isinstance(payload, dict) else "")
        or requested_analysis_id
        or requested_meal_id
        or ""
    ).strip()
    week_start_iso = _week_start_monday(day_iso)
    scan_meta = _latest_scan_meta(uid, day_iso)
    processed_scan_id = str(requested_input_scan_id or scan_meta.get("scan_id") or "").strip()
    processed_scan_ts = str(latest_scan_ts or scan_meta.get("scan_ts") or "").strip()
    incoming_state = payload.get("_state") if isinstance(payload, dict) and isinstance(payload.get("_state"), dict) else {}
    meals_count_today = int(_safe_float(incoming_state.get("scan_count"), 0) or 0)
    if meals_count_today <= 0:
        meals_count_today = int(_safe_float(scan_meta.get("meals_count_today"), 0) or 0)

    week_rows: Optional[List[Dict[str, Any]]] = None
    weekly_behavior: Optional[Dict[str, Any]] = None
    try:
        weekly_behavior = get_weekly_insight_payload(uid, week_start_iso)
    except Exception as e:
        logger.info(f"weekly insight read skipped in /coach/daily: {e}")
    if _is_payload_stale(weekly_behavior, day_iso):
        weekly_behavior = None

    weekly_predictive: Optional[Dict[str, Any]] = None
    try:
        weekly_predictive = get_user_weekly_metrics_payload(uid, week_start_iso)
    except Exception as e:
        logger.info(f"weekly metrics read skipped in /coach/daily: {e}")
    if _is_payload_stale(weekly_predictive, day_iso):
        weekly_predictive = None

    week_tz = _select_week_timezone(
        weekly_behavior if isinstance(weekly_behavior, dict) else weekly_predictive,
        tz=tz,
        tz_offset_min=tz_offset_min,
    )

    if not weekly_behavior:
        try:
            week_rows = get_daily_metrics_window(uid, week_start_iso)
            if week_rows:
                weekly_behavior = build_weekly_insight_payload(uid, week_start_iso, week_rows, tz_used=week_tz)
                upsert_weekly_insight(uid, week_start_iso, weekly_behavior)
        except Exception as e:
            logger.info(f"weekly insight recompute skipped in /coach/daily: {e}")

    if not weekly_predictive:
        try:
            if week_rows is None:
                week_rows = get_daily_metrics_window(uid, week_start_iso)
            if week_rows:
                weekly_predictive = build_weekly_prediction_payload(uid, week_start_iso, week_rows, tz_used=week_tz)
                try:
                    upsert_user_weekly_metrics(uid, week_start_iso, weekly_predictive)
                except Exception as e:
                    logger.info(f"weekly metrics write skipped in /coach/daily: {e}")
        except Exception as e:
            logger.info(f"weekly metrics recompute skipped in /coach/daily: {e}")

    weekly_hash = str((weekly_behavior or {}).get("payload_hash") or "").strip()
    if weekly_hash:
        p_hash = hashlib.sha256(f"{p_hash}:{weekly_hash}".encode("utf-8")).hexdigest()
    weekly_metrics_hash = str((weekly_predictive or {}).get("payload_hash") or "").strip()
    if weekly_metrics_hash:
        p_hash = hashlib.sha256(f"{p_hash}:{weekly_metrics_hash}".encode("utf-8")).hexdigest()
    incoming_daily_version = str(
        (
            (payload.get("_state") or {}).get("daily_totals_version")
            if isinstance(payload, dict) and isinstance(payload.get("_state"), dict)
            else ""
        )
        or (payload.get("daily_totals_version") if isinstance(payload, dict) else "")
        or ""
    ).strip()
    if state_signature:
        p_hash = hashlib.sha256(f"{p_hash}:{state_signature}".encode("utf-8")).hexdigest()
    elif incoming_daily_version:
        p_hash = hashlib.sha256(f"{p_hash}:{incoming_daily_version}".encode("utf-8")).hexdigest()
    if requested_meal_id:
        p_hash = hashlib.sha256(f"{p_hash}:meal:{requested_meal_id}".encode("utf-8")).hexdigest()
    if requested_analysis_id:
        p_hash = hashlib.sha256(f"{p_hash}:analysis:{requested_analysis_id}".encode("utf-8")).hexdigest()
    if processed_scan_id:
        p_hash = hashlib.sha256(f"{p_hash}:{processed_scan_id}".encode("utf-8")).hexdigest()
    daily_totals_version = str(incoming_daily_version or state_signature or p_hash)
    memory_window = _read_coach_memory_window(uid, day_iso)
    recent_coach_messages = _normalize_short_text_list(memory_window.get("last_3_coach_messages"), limit=3, max_chars=180)

    cached = _coach_cache_get(uid, day_iso, p_hash) if not refresh else None
    if isinstance(cached, dict):
        out = dict(cached)
        if processed_scan_id:
            cached_scan_id = str(out.get("last_processed_scan_id") or "").strip()
            if cached_scan_id and cached_scan_id != processed_scan_id:
                logger.info(
                    f"fli_stale_detected user={uid} latest_scan_id={processed_scan_id} last_processed_scan_id={cached_scan_id}"
                )
                out = {}
        if not out:
            cached = None
    if isinstance(cached, dict):
        out = dict(cached)
        out["fat_loss_score"] = int(fat_loss_score)
        out["disclaimer"] = coach_logic.COACH_DISCLAIMER
        out["date"] = day_iso
        inferred_source = _normalize_fli_source(out)
        out["reasoning_source"] = str(
            out.get("reasoning_source") or ("cached_llm" if inferred_source in {"llm", "cached_llm"} else "rules")
        )
        out["last_processed_scan_id"] = str(out.get("last_processed_scan_id") or processed_scan_id)
        out["last_processed_scan_ts"] = str(out.get("last_processed_scan_ts") or processed_scan_ts)
        out["updatedAt"] = str(out.get("updatedAt") or dt.datetime.utcnow().isoformat())
        out["payload_hash_used"] = str(out.get("payload_hash_used") or p_hash)
        out["insight_signature"] = str(out.get("insight_signature") or out.get("payload_hash_used") or p_hash)
        out["coach_generated_ts"] = str(out.get("coach_generated_ts") or out.get("updatedAt") or dt.datetime.utcnow().isoformat())
        out["meals_count_today"] = int(_safe_float(out.get("meals_count_today"), meals_count_today) or 0)
        out["fli_source"] = _normalize_fli_source(out)
        out["fli_reason_code"] = str(out.get("fli_reason_code") or "CACHE_HIT")
        out["fli_stale_seconds"] = int(out.get("fli_stale_seconds") or _compute_fli_stale_seconds(out.get("coach_generated_ts")))
        out["fli_status"] = str(out.get("fli_status") or "ready")
        out["source_display"] = "Coach"
        normalized_src = _normalize_fli_source(out)
        out["source"] = "cache" if normalized_src == "cached_llm" else ("llm" if normalized_src == "llm" else "rules")
        out["llm_model_used"] = str(out.get("llm_model_used") or "")
        out["llm_error_code"] = str(out.get("llm_error_code") or ("" if out["source"] == "llm" else out.get("fli_reason_code") or ""))
        out["llm_tried_models"] = list(out.get("llm_tried_models") or [])
        out["daily_totals_version"] = str(out.get("daily_totals_version") or daily_totals_version)
        out = _ensure_coach_voice_defaults(out, weekly_predictive=weekly_predictive)
        needs_rewrite = (str(out.get("tone_used") or "").strip().lower() != tone_pref) or (
            not str(out.get("tone_rewrite_source") or "").strip()
        )
        if needs_rewrite:
            out = _apply_tone_rewrite_to_coach_response(
                out,
                norm,
                tone_id=tone_pref,
                freshness=_coach_rewrite_freshness_from_payload(out, default="updated_now"),
                max_actions=(2 if fast else 3),
                allow_llm=False,
            )
        else:
            out["tone_requested"] = tone_pref
            out["tone_used"] = tone_pref
            out["tone_tag"] = _normalize_tone_tag(out.get("tone_tag"), fallback=_DAILY_TONE_TAG_MAP.get(tone_pref, "neutral"))
        out["pattern_detected"] = str(out.get("pattern_detected") or "")
        if not isinstance(out.get("biggest_risk_lever"), dict):
            out["biggest_risk_lever"] = {"title": "", "reason": ""}
        if not isinstance(out.get("highest_roi_change"), dict):
            out["highest_roi_change"] = {"title": "", "why": "", "how": ""}
        if not isinstance(out.get("projection_7d"), dict):
            out["projection_7d"] = {"if_unchanged": "", "if_improved": ""}
        if isinstance(weekly_behavior, dict):
            out["behavior_memory"] = {
                "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
                "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
                "patterns": weekly_behavior.get("patterns") or {},
                "insights": (weekly_behavior.get("insights") or [])[:4],
            }
        public_pred = _public_predictive_signals(weekly_predictive, week_start_iso)
        if isinstance(public_pred, dict):
            out["predictive_signals"] = public_pred
        else:
            out.pop("predictive_signals", None)
        out = _apply_dynamic_coach_copy(
            out,
            norm,
            user_id=uid,
            day_iso=day_iso,
            scan_id=processed_scan_id,
            scan_count=meals_count_today,
            recent_messages=recent_coach_messages,
        )
        logger.info(
            f"fli_fetch source=cache user={uid} updatedAt={out.get('updatedAt')} "
            f"last_processed_scan_id={out.get('last_processed_scan_id')} "
            f"payload_hash_used={out.get('payload_hash_used')} meals_count_today={out.get('meals_count_today')} "
            f"duration_ms={int((time.time()-started)*1000)}"
        )
        out = _attach_coach_response_debug(
            out,
            request_id=request_id,
            started_at=started,
            meal_id=requested_meal_id,
            analysis_id=requested_analysis_id,
            input_scan_id=processed_scan_id,
            source_hint=(
                "cache"
                if _normalize_fli_source(out) == "cached_llm"
                else ("llm" if _normalize_fli_source(out) == "llm" else "rules")
            ),
            model_used=str(out.get("llm_model_used") or ""),
            error_code=str(out.get("llm_error_code") or out.get("fli_reason_code") or ""),
            tried_models=list(out.get("llm_tried_models") or []),
        )
        _record_coach_event(
            uid,
            {
                "request_id": out.get("request_id"),
                "type": "coach_daily",
                "source": out.get("source"),
                "model_used": out.get("model_used"),
                "error_code": out.get("error_code"),
                "latency_ms": out.get("latency_ms"),
                "meal_id": out.get("meal_id"),
                "analysis_id": out.get("analysis_id"),
                "input_scan_id": out.get("input_scan_id"),
                "day": day_iso,
            },
        )
        return _attach_debug_schema(out, bool(debug))

    llm_resp: Optional[Dict[str, Any]] = None
    reasoning_source = "rules"
    llm_reason_code = ""
    llm_model_used = ""
    llm_tried_models: List[str] = []
    llm_error_raw = ""
    if GEMINI_API_KEY:
        try:
            llm_resp = _generate_daily_coach_llm(
                norm,
                fat_loss_score,
                rule_alerts,
                weekly_behavior=weekly_behavior,
                weekly_predictive=weekly_predictive,
                fast_mode=bool(fast),
                tone_preference=tone_pref,
            )
            reasoning_source = "llm"
            llm_reason_code = ""
            llm_model_used = str((llm_resp or {}).get("_llm_model_used") or "").strip()
        except Exception as e:
            llm_reason_code, llm_tried_models, llm_error_raw = _extract_llm_failure_debug(e)
            logger.warning(f"Daily coach LLM failed, using fallback: {e}")

    if not llm_resp:
        cached_llm = _best_cached_coach_llm(uid, day_iso)
        if isinstance(cached_llm, dict):
            generated_ts = dt.datetime.utcnow().isoformat()
            final_resp = dict(cached_llm)
            final_resp["date"] = day_iso
            final_resp["fat_loss_score"] = int(fat_loss_score)
            final_resp["disclaimer"] = coach_logic.COACH_DISCLAIMER
            final_resp["reasoning_source"] = "cached_llm"
            final_resp["fli_source"] = "cached_llm"
            final_resp["fli_reason_code"] = llm_reason_code or "LLM_UNAVAILABLE_CACHED"
            final_resp["fli_stale_seconds"] = _compute_fli_stale_seconds(final_resp.get("coach_generated_ts"))
            final_resp["fli_status"] = "ready"
            final_resp["source_display"] = "Coach"
            final_resp["source"] = "cache"
            final_resp["llm_model_used"] = str(final_resp.get("llm_model_used") or llm_model_used or "")
            final_resp["llm_error_code"] = str(final_resp.get("llm_error_code") or llm_reason_code or "")
            final_resp["llm_tried_models"] = list(final_resp.get("llm_tried_models") or llm_tried_models or [])
            final_resp["payload_hash_used"] = p_hash
            final_resp["insight_signature"] = p_hash
            final_resp["daily_totals_version"] = daily_totals_version
            final_resp["last_processed_scan_id"] = processed_scan_id
            final_resp["last_processed_scan_ts"] = processed_scan_ts
            final_resp["updatedAt"] = generated_ts
            final_resp["meals_count_today"] = meals_count_today
            final_resp = _ensure_coach_voice_defaults(final_resp, weekly_predictive=weekly_predictive)
            final_resp = _apply_tone_rewrite_to_coach_response(
                final_resp,
                norm,
                tone_id=tone_pref,
                freshness=_coach_rewrite_freshness_from_payload(final_resp, default="stale_cache"),
                max_actions=(2 if fast else 3),
                allow_llm=False,
            )
            if isinstance(weekly_behavior, dict):
                final_resp["behavior_memory"] = {
                    "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
                    "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
                    "patterns": weekly_behavior.get("patterns") or {},
                    "insights": (weekly_behavior.get("insights") or [])[:4],
                }
            public_pred = _public_predictive_signals(weekly_predictive, week_start_iso)
            if isinstance(public_pred, dict):
                final_resp["predictive_signals"] = public_pred
            final_resp = _apply_dynamic_coach_copy(
                final_resp,
                norm,
                user_id=uid,
                day_iso=day_iso,
                scan_id=processed_scan_id,
                scan_count=meals_count_today,
                recent_messages=recent_coach_messages,
            )
            try:
                roi_cached = final_resp.get("highest_roi_change") if isinstance(final_resp.get("highest_roi_change"), dict) else {}
                sem_key_cached = _infer_semantic_key_from_action(roi_cached.get("title"), roi_cached.get("how"))
                _append_coach_memory_entry(
                    uid,
                    day_iso,
                    sem_key_cached,
                    str(final_resp.get("one_sentence_summary") or final_resp.get("coach_summary") or ""),
                )
            except Exception as e:
                logger.info(f"coach memory append skipped in /coach/daily (cached_llm): {e}")
            _coach_cache_set(uid, day_iso, p_hash, final_resp)
            logger.info(
                f"fli_fetch source={final_resp.get('reasoning_source')} user={uid} updatedAt={final_resp.get('updatedAt')} "
                f"last_processed_scan_id={final_resp.get('last_processed_scan_id')} "
                f"payload_hash_used={final_resp.get('payload_hash_used')} meals_count_today={final_resp.get('meals_count_today')} "
                f"duration_ms={int((time.time()-started)*1000)}"
            )
            final_resp = _attach_coach_response_debug(
                final_resp,
                request_id=request_id,
                started_at=started,
                meal_id=requested_meal_id,
                analysis_id=requested_analysis_id,
                input_scan_id=processed_scan_id,
                source_hint="cache",
                model_used=str(final_resp.get("llm_model_used") or llm_model_used or ""),
                error_code=str(final_resp.get("llm_error_code") or llm_reason_code or ""),
                tried_models=list(final_resp.get("llm_tried_models") or llm_tried_models or []),
            )
            _record_coach_event(
                uid,
                {
                    "request_id": final_resp.get("request_id"),
                    "type": "coach_daily",
                    "source": final_resp.get("source"),
                    "model_used": final_resp.get("model_used"),
                    "error_code": final_resp.get("error_code"),
                    "latency_ms": final_resp.get("latency_ms"),
                    "meal_id": final_resp.get("meal_id"),
                    "analysis_id": final_resp.get("analysis_id"),
                    "input_scan_id": final_resp.get("input_scan_id"),
                    "day": day_iso,
                },
            )
            return _attach_debug_schema(final_resp, bool(debug))

        llm_resp = coach_logic.build_fallback_coach_response(norm, fat_loss_score, rule_alerts)

    generated_ts = dt.datetime.utcnow().isoformat()
    final_resp = {
        "date": day_iso,
        "fat_loss_score": int(fat_loss_score),
        "one_sentence_summary": str(llm_resp.get("one_sentence_summary") or ""),
        "pattern_detected": str(llm_resp.get("pattern_detected") or ""),
        "projection_explained": str(llm_resp.get("projection_explained") or ""),
        "biggest_risk_lever": llm_resp.get("biggest_risk_lever")
        if isinstance(llm_resp.get("biggest_risk_lever"), dict)
        else {"title": "", "reason": ""},
        "highest_roi_change": llm_resp.get("highest_roi_change")
        if isinstance(llm_resp.get("highest_roi_change"), dict)
        else {"title": "", "why": "", "how": ""},
        "if_you_do_one_thing": str(llm_resp.get("if_you_do_one_thing") or ""),
        "projection_7d": llm_resp.get("projection_7d")
        if isinstance(llm_resp.get("projection_7d"), dict)
        else {"if_unchanged": "", "if_improved": ""},
        "diagnosis": llm_resp.get("diagnosis", []),
        "tomorrow_focus": llm_resp.get("tomorrow_focus", []),
        "actions": llm_resp.get("actions", [])[: (2 if fast else 3)],
        "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, llm_resp.get("risk_alerts", []), limit=4),
        "disclaimer": coach_logic.COACH_DISCLAIMER,
        "reasoning_source": reasoning_source,
        "fli_source": "llm" if reasoning_source == "llm" else "rules",
        "fli_reason_code": llm_reason_code if reasoning_source != "llm" else "",
        "fli_stale_seconds": 0,
        "fli_status": "ready",
        "source_display": "Coach",
        "source": "llm" if reasoning_source == "llm" else "rules",
        "llm_model_used": llm_model_used if reasoning_source == "llm" else "",
        "llm_error_code": llm_reason_code if reasoning_source != "llm" else "",
        "llm_tried_models": llm_tried_models if reasoning_source != "llm" else ([] if not llm_model_used else [llm_model_used]),
        "llm_error_raw": llm_error_raw if reasoning_source != "llm" else "",
        "week_start": week_start_iso,
        "last_processed_scan_id": processed_scan_id,
        "last_processed_scan_ts": processed_scan_ts,
        "updatedAt": generated_ts,
        "coach_generated_ts": generated_ts,
        "payload_hash_used": p_hash,
        "insight_signature": p_hash,
        "daily_totals_version": daily_totals_version,
        "meals_count_today": meals_count_today,
    }
    final_resp = _ensure_coach_voice_defaults(final_resp, weekly_predictive=weekly_predictive)
    if isinstance(weekly_behavior, dict):
        final_resp["behavior_memory"] = {
            "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
            "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
            "patterns": weekly_behavior.get("patterns") or {},
            "insights": (weekly_behavior.get("insights") or [])[:4],
        }
    public_pred = _public_predictive_signals(weekly_predictive, week_start_iso)
    if isinstance(public_pred, dict):
        final_resp["predictive_signals"] = public_pred

    # Final safety gate. If anything violates guardrails, return deterministic fallback.
    ok, reason = coach_logic.validate_llm_response_shape(final_resp)
    if not ok:
        logger.warning(f"Daily coach response failed safety gate: {reason}")
        fb = coach_logic.build_fallback_coach_response(norm, fat_loss_score, rule_alerts)
        generated_ts = dt.datetime.utcnow().isoformat()
        final_resp = {
            "date": day_iso,
            "fat_loss_score": int(fat_loss_score),
            "one_sentence_summary": str(fb.get("one_sentence_summary") or ""),
            "pattern_detected": str(fb.get("pattern_detected") or ""),
            "projection_explained": str(fb.get("projection_explained") or ""),
            "biggest_risk_lever": fb.get("biggest_risk_lever")
            if isinstance(fb.get("biggest_risk_lever"), dict)
            else {"title": "", "reason": ""},
            "highest_roi_change": fb.get("highest_roi_change")
            if isinstance(fb.get("highest_roi_change"), dict)
            else {"title": "", "why": "", "how": ""},
            "if_you_do_one_thing": str(fb.get("if_you_do_one_thing") or ""),
            "projection_7d": fb.get("projection_7d")
            if isinstance(fb.get("projection_7d"), dict)
            else {"if_unchanged": "", "if_improved": ""},
            "diagnosis": fb.get("diagnosis", []),
            "tomorrow_focus": fb.get("tomorrow_focus", []),
            "actions": fb.get("actions", [])[: (2 if fast else 3)],
            "risk_alerts": coach_logic.merge_risk_alerts(rule_alerts, fb.get("risk_alerts", []), limit=4),
            "disclaimer": coach_logic.COACH_DISCLAIMER,
            "reasoning_source": "rules",
            "fli_source": "rules",
            "fli_reason_code": "SAFETY_GATE_FAILED",
            "fli_stale_seconds": 0,
            "fli_status": "ready",
            "source_display": "Coach",
            "source": "rules",
            "llm_model_used": "",
            "llm_error_code": "SAFETY_GATE_FAILED",
            "llm_tried_models": llm_tried_models,
            "llm_error_raw": llm_error_raw,
            "week_start": week_start_iso,
            "last_processed_scan_id": processed_scan_id,
            "last_processed_scan_ts": processed_scan_ts,
            "updatedAt": generated_ts,
            "coach_generated_ts": generated_ts,
            "payload_hash_used": p_hash,
            "insight_signature": p_hash,
            "daily_totals_version": daily_totals_version,
            "meals_count_today": meals_count_today,
        }
        final_resp = _ensure_coach_voice_defaults(final_resp, weekly_predictive=weekly_predictive)
        if isinstance(weekly_behavior, dict):
            final_resp["behavior_memory"] = {
                "week_start": str(weekly_behavior.get("week_start") or week_start_iso),
                "days_tracked": int(_safe_float(weekly_behavior.get("days_tracked"), 0) or 0),
                "patterns": weekly_behavior.get("patterns") or {},
                "insights": (weekly_behavior.get("insights") or [])[:4],
            }
        public_pred = _public_predictive_signals(weekly_predictive, week_start_iso)
        if isinstance(public_pred, dict):
            final_resp["predictive_signals"] = public_pred

    final_resp = _apply_tone_rewrite_to_coach_response(
        final_resp,
        norm,
        tone_id=tone_pref,
        freshness=_coach_rewrite_freshness_from_payload(final_resp, default="updated_now"),
        max_actions=(2 if fast else 3),
        allow_llm=False,
    )
    final_resp = _apply_dynamic_coach_copy(
        final_resp,
        norm,
        user_id=uid,
        day_iso=day_iso,
        scan_id=processed_scan_id,
        scan_count=meals_count_today,
        recent_messages=recent_coach_messages,
    )
    try:
        roi_main = final_resp.get("highest_roi_change") if isinstance(final_resp.get("highest_roi_change"), dict) else {}
        sem_key_main = _infer_semantic_key_from_action(roi_main.get("title"), roi_main.get("how"))
        _append_coach_memory_entry(
            uid,
            day_iso,
            sem_key_main,
            str(final_resp.get("one_sentence_summary") or final_resp.get("coach_summary") or ""),
        )
    except Exception as e:
        logger.info(f"coach memory append skipped in /coach/daily: {e}")
    _coach_cache_set(uid, day_iso, p_hash, final_resp)
    logger.info(
        f"fli_fetch source={final_resp.get('reasoning_source')} user={uid} updatedAt={final_resp.get('updatedAt')} "
        f"last_processed_scan_id={final_resp.get('last_processed_scan_id')} "
        f"payload_hash_used={final_resp.get('payload_hash_used')} meals_count_today={final_resp.get('meals_count_today')} "
        f"duration_ms={int((time.time()-started)*1000)}"
    )
    final_resp = _attach_coach_response_debug(
        final_resp,
        request_id=request_id,
        started_at=started,
        meal_id=requested_meal_id,
        analysis_id=requested_analysis_id,
        input_scan_id=processed_scan_id,
        source_hint=("llm" if reasoning_source == "llm" else "rules"),
        model_used=llm_model_used,
        error_code=llm_reason_code,
        tried_models=llm_tried_models,
    )
    _record_coach_event(
        uid,
        {
            "request_id": final_resp.get("request_id"),
            "type": "coach_daily",
            "source": final_resp.get("source"),
            "model_used": final_resp.get("model_used"),
            "error_code": final_resp.get("error_code"),
            "latency_ms": final_resp.get("latency_ms"),
            "meal_id": final_resp.get("meal_id"),
            "analysis_id": final_resp.get("analysis_id"),
            "input_scan_id": final_resp.get("input_scan_id"),
            "day": day_iso,
        },
    )
    return _attach_debug_schema(final_resp, bool(debug))


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

# -------------------- GEMINI FOOD DETECTION (Confidence-first V1) --------------------
def _coerce_vision_scan_payload(raw: Dict[str, Any], vision_threshold: float = 0.72) -> VisionScanV1Model:
    src = raw if isinstance(raw, dict) else {}
    items_in = src.get("items") if isinstance(src.get("items"), list) else []
    cleaned_items: List[Dict[str, Any]] = []
    for idx, it in enumerate(items_in):
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        grams = max(0.0, float(_safe_float(it.get("grams"), 0.0) or 0.0))
        if not name or grams <= 0:
            continue
        cleaned_items.append(
            {
                "item_id": str(it.get("item_id") or f"i{idx + 1}"),
                "name": name,
                "grams": round(grams, 1),
                "cooking_method": str(it.get("cooking_method") or "unknown").strip().lower() or "unknown",
                "oil_added_tsp": max(0.0, float(_safe_float(it.get("oil_added_tsp"), 0.0) or 0.0)),
                "confidence": round(_clamp01(it.get("confidence"), 0.65), 3),
                "candidate_alternatives": [
                    str(x).strip()
                    for x in (it.get("candidate_alternatives") or [])
                    if str(x).strip()
                ][:4],
            }
        )

    if not cleaned_items:
        raise ValueError("No usable items from scan payload.")

    top_in = src.get("top_candidates") if isinstance(src.get("top_candidates"), list) else []
    cleaned_top: List[Dict[str, Any]] = []
    for idx, c in enumerate(top_in[:5]):
        if not isinstance(c, dict):
            continue
        label = str(c.get("label") or "").strip()
        if not label:
            continue
        cleaned_top.append(
            {
                "candidate_id": str(c.get("candidate_id") or f"c{idx + 1}"),
                "label": label,
                "confidence": round(_clamp01(c.get("confidence"), 0.5), 3),
                "evidence": [str(x).strip() for x in (c.get("evidence") or []) if str(x).strip()][:4],
                "assumptions": [str(x).strip() for x in (c.get("assumptions") or []) if str(x).strip()][:4],
                "portion_guess_g": max(0.0, float(_safe_float(c.get("portion_guess_g"), 0.0) or 0.0)),
            }
        )

    if not cleaned_top:
        cleaned_top = [
            {
                "candidate_id": f"c{idx + 1}",
                "label": item["name"],
                "confidence": item["confidence"],
                "evidence": [],
                "assumptions": [],
                "portion_guess_g": item["grams"],
            }
            for idx, item in enumerate(cleaned_items[:3])
        ]

    vis_conf = _clamp01(src.get("vision_confidence"), default=_safe_float(src.get("confidence"), 0.65) or 0.65)
    # Deterministic trigger rules (non-random):
    # 1) Any fried/air-fried style item with zero explicit oil -> always ask oil-method clarification.
    # 2) Otherwise, low confidence scans ask generic clarification.
    # 3) High confidence + non-fried pattern -> no clarification.
    v_threshold = max(0.50, min(0.98, float(_safe_float(vision_threshold, 0.72) or 0.72)))
    if _needs_fried_oil_question(cleaned_items):
        clarifying = dict(_FRIED_CLARIFY_QUESTION)
    elif vis_conf < v_threshold:
        clarifying = dict(_LOW_CONF_CLARIFY_QUESTION)
    else:
        clarifying = None

    payload = {
        "vision_confidence": round(vis_conf, 3),
        "top_candidates": cleaned_top,
        "clarifying_question": clarifying,
        "editable_context": {"items": cleaned_items},
        "items": cleaned_items,
    }
    return _model_validate(VisionScanV1Model, payload)


def _fallback_vision_scan_from_items(items: List[Dict[str, Any]], vision_threshold: float = 0.72) -> VisionScanV1Model:
    cleaned_items = []
    for idx, it in enumerate(items or []):
        name = str((it or {}).get("name") or "").strip()
        grams = max(0.0, float(_safe_float((it or {}).get("grams"), 0.0) or 0.0))
        if not name or grams <= 0:
            continue
        cleaned_items.append(
            {
                "item_id": str((it or {}).get("item_id") or f"i{idx + 1}"),
                "name": name,
                "grams": round(grams, 1),
                "cooking_method": str((it or {}).get("cooking_method") or "unknown"),
                "oil_added_tsp": max(0.0, float(_safe_float((it or {}).get("oil_added_tsp"), 0.0) or 0.0)),
                "confidence": round(_clamp01((it or {}).get("confidence"), 0.62), 3),
                "candidate_alternatives": [
                    str(x).strip()
                    for x in ((it or {}).get("candidate_alternatives") or [])
                    if str(x).strip()
                ][:4],
            }
        )
    if not cleaned_items:
        raise HTTPException(status_code=502, detail={"error": "scan_failed", "raw": "No recognizable items."})

    avg_conf = sum(i["confidence"] for i in cleaned_items) / max(1, len(cleaned_items))
    vis_conf = round(_clamp01(avg_conf, 0.62), 3)
    top = [
        {
            "candidate_id": f"c{idx + 1}",
            "label": item["name"],
            "confidence": item["confidence"],
            "evidence": [],
            "assumptions": [],
            "portion_guess_g": item["grams"],
        }
        for idx, item in enumerate(cleaned_items[:3])
    ]
    v_threshold = max(0.50, min(0.98, float(_safe_float(vision_threshold, 0.72) or 0.72)))
    if _needs_fried_oil_question(cleaned_items):
        clarifying = dict(_FRIED_CLARIFY_QUESTION)
    elif vis_conf < v_threshold:
        clarifying = {
            "ask": "Is this portion size accurate and was extra oil used?",
            "options": ["Looks right", "Portion is larger", "Portion is smaller", "Extra oil used"],
        }
    else:
        clarifying = None
    return _model_validate(
        VisionScanV1Model,
        {
            "vision_confidence": vis_conf,
            "top_candidates": top,
            "clarifying_question": clarifying,
            "editable_context": {"items": cleaned_items},
            "items": cleaned_items,
        },
    )


def gemini_vision_scan_v1(
    image_bytes: bytes,
    personalization_context: Optional[Dict[str, Any]] = None,
    vision_threshold: float = 0.72,
    request_id: str = "",
    job_id: str = "",
) -> VisionScanV1Model:
    _require_gemini_key()
    priors_ctx = personalization_context if isinstance(personalization_context, dict) else {}
    priors_json = json.dumps(
        {
            "user_priors": priors_ctx.get("user_priors") if isinstance(priors_ctx.get("user_priors"), dict) else {},
            "always_ask_oil_for_methods": priors_ctx.get("always_ask_oil_for_methods")
            if isinstance(priors_ctx.get("always_ask_oil_for_methods"), list)
            else [],
            "defaults_policy": str(priors_ctx.get("defaults_policy") or ""),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    v_threshold = max(0.50, min(0.98, float(_safe_float(vision_threshold, 0.72) or 0.72)))
    prompt = """
You are a food-vision assistant for a nutrition app.
Return ONLY valid JSON (no markdown) with this exact shape:
{
  "vision_confidence": 0.0,
  "top_candidates": [
    {
      "candidate_id": "c1",
      "label": "grilled chicken salad",
      "confidence": 0.0,
      "evidence": ["leafy greens", "grilled chicken pieces"],
      "assumptions": ["dressing included"],
      "portion_guess_g": 0.0
    }
  ],
  "clarifying_question": {
    "ask": "Is there dressing/oil added? If yes, how much?",
    "options": ["No", "Yes - light", "Yes - normal", "Yes - heavy"]
  },
  "items": [
    {
      "item_id": "i1",
      "name": "grilled chicken",
      "grams": 180,
      "cooking_method": "grilled",
      "oil_added_tsp": 0,
      "confidence": 0.0,
      "candidate_alternatives": ["chicken thigh", "chicken breast"]
    }
  ]
}

Rules:
- Use simple USDA-friendly item names.
- items must not be empty.
- grams > 0 for each item.
- confidence fields must be 0..1.
- Use personalization context only as soft defaults, never as guaranteed truth.
- If an item's cooking method is in always_ask_oil_for_methods, include clarifying_question even when confidence is high.
- If confidence >= VISION_THRESHOLD, set clarifying_question to null.
- If confidence < VISION_THRESHOLD, include exactly one clarifying_question.
- VISION_THRESHOLD: """ + f"{v_threshold:.2f}" + """
- Personalization context JSON:
""" + priors_json
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = _generate_scan_content(
        [prompt, img],
        purpose="vision_scan",
        request_id=request_id,
        job_id=job_id,
    )
    parsed = coach_logic.extract_json_object(text)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail={"error": "vision_scan_failed", "raw": "No JSON object returned by model."})
    return _coerce_vision_scan_payload(parsed, vision_threshold=v_threshold)


def gemini_detect_foods(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Backward-compatible shim used by older callers.
    """
    scan = gemini_vision_scan_v1(image_bytes)
    return [
        {
            "item_id": it.item_id,
            "name": it.name,
            "grams": it.grams,
            "confidence": it.confidence,
            "cooking_method": it.cooking_method,
            "oil_added_tsp": it.oil_added_tsp,
            "candidate_alternatives": it.candidate_alternatives,
        }
        for it in (scan.items or [])
    ]


def _compute_scan_nutrition(detected_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float], List[Dict[str, Any]]]:
    results: List[Dict[str, Any]] = []
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0
    total_micros = {
        "vitamin_d_ug": 0.0,
        "vitamin_b12_ug": 0.0,
        "iron_mg": 0.0,
        "magnesium_mg": 0.0,
        "calcium_mg": 0.0,
        "potassium_mg": 0.0,
        "sodium_mg": 0.0,
        "fiber_g": 0.0,
        "sugar_g": 0.0,
    }
    item_warnings: List[Dict[str, Any]] = []

    for idx, d in enumerate(detected_items or []):
        name = str((d or {}).get("name") or "").strip()
        if not name:
            continue
        grams = max(0.0, float(_safe_float((d or {}).get("grams"), 0.0) or 0.0))
        if grams <= 0:
            continue
        conf = _clamp01((d or {}).get("confidence"), 0.6)
        item_id = str((d or {}).get("item_id") or f"i{idx + 1}")
        cooking_method = str((d or {}).get("cooking_method") or "unknown").strip().lower() or "unknown"
        oil_added_tsp = max(0.0, float(_safe_float((d or {}).get("oil_added_tsp"), 0.0) or 0.0))
        if oil_added_tsp <= 0 and "fried" in cooking_method:
            oil_added_tsp = 1.0
        candidate_alternatives = [
            str(x).strip() for x in ((d or {}).get("candidate_alternatives") or []) if str(x).strip()
        ][:4]

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
                    "item_id": item_id,
                    "name": name,
                    "warning": "nutrition_lookup_failed",
                    "detail": (last_item_err or "No usable USDA match found")[:220],
                }
            )
            results.append(
                {
                    "item_id": item_id,
                    "name": name,
                    "grams": round(grams, 1),
                    "confidence": round(conf, 2),
                    "cooking_method": cooking_method,
                    "oil_added_tsp": round(oil_added_tsp, 2),
                    "candidate_alternatives": candidate_alternatives,
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

        # Minimal deterministic correction for user-specified cooking/oil edits.
        if oil_added_tsp > 0:
            kcal += oil_added_tsp * 40.5
            f += oil_added_tsp * 4.5

        micros = {}
        for k, v in (micros100 or {}).items():
            if k == "_units":
                continue
            micros[k] = round(float(v) * factor, 3)

        results.append(
            {
                "item_id": item_id,
                "name": name,
                "grams": round(grams, 1),
                "confidence": round(conf, 2),
                "cooking_method": cooking_method,
                "oil_added_tsp": round(oil_added_tsp, 2),
                "candidate_alternatives": candidate_alternatives,
                "kcal": round(kcal, 1),
                "macros": {
                    "protein_g": round(p, 1),
                    "carbs_g": round(c, 1),
                    "fat_g": round(f, 1),
                },
                "micros": micros,
                "micros_units": (micros100 or {}).get("_units"),
                "usda": {
                    "fdcId": fdc_id,
                    "description": (details or {}).get("description"),
                    "dataType": (details or {}).get("dataType"),
                },
            }
        )

        total_kcal += kcal
        total_p += p
        total_c += c
        total_f += f
        for mk, mv in micros.items():
            if mk in total_micros:
                total_micros[mk] += float(mv)

    totals = {
        "kcal": round(total_kcal, 1),
        "protein_g": round(total_p, 1),
        "carbs_g": round(total_c, 1),
        "fat_g": round(total_f, 1),
    }
    return results, totals, total_micros, item_warnings


def _build_micros_payload(total_micros: Dict[str, float]) -> Dict[str, Any]:
    tm = total_micros or {}
    return {
        "vitamin_d_ug": round(float(_safe_float(tm.get("vitamin_d_ug"), 0.0) or 0.0), 3),
        "vitamin_b12_ug": round(float(_safe_float(tm.get("vitamin_b12_ug"), 0.0) or 0.0), 3),
        "iron_mg": round(float(_safe_float(tm.get("iron_mg"), 0.0) or 0.0), 3),
        "magnesium_mg": round(float(_safe_float(tm.get("magnesium_mg"), 0.0) or 0.0), 3),
        "calcium_mg": round(float(_safe_float(tm.get("calcium_mg"), 0.0) or 0.0), 3),
        "potassium_mg": round(float(_safe_float(tm.get("potassium_mg"), 0.0) or 0.0), 3),
        "sodium_mg": round(float(_safe_float(tm.get("sodium_mg"), 0.0) or 0.0), 3),
        "fiber_g": round(float(_safe_float(tm.get("fiber_g"), 0.0) or 0.0), 3),
        "sugar_g": round(float(_safe_float(tm.get("sugar_g"), 0.0) or 0.0), 3),
        "_units": {
            "vitamin_d_ug": "µg",
            "vitamin_b12_ug": "µg",
            "iron_mg": "mg",
            "magnesium_mg": "mg",
            "calcium_mg": "mg",
            "potassium_mg": "mg",
            "sodium_mg": "mg",
            "fiber_g": "g",
            "sugar_g": "g",
        },
    }


def _build_rerun_daily_delta(
    old_totals: Dict[str, Any],
    old_micros: Dict[str, Any],
    new_totals: Dict[str, Any],
    new_micros: Dict[str, Any],
) -> Dict[str, float]:
    old_totals = old_totals if isinstance(old_totals, dict) else {}
    old_micros = old_micros if isinstance(old_micros, dict) else {}
    new_totals = new_totals if isinstance(new_totals, dict) else {}
    new_micros = new_micros if isinstance(new_micros, dict) else {}
    return {
        "total_kcal": float(_safe_float(new_totals.get("kcal"), 0.0) or 0.0)
        - float(_safe_float(old_totals.get("kcal"), 0.0) or 0.0),
        "protein_g": float(_safe_float(new_totals.get("protein_g"), 0.0) or 0.0)
        - float(_safe_float(old_totals.get("protein_g"), 0.0) or 0.0),
        "carbs_g": float(_safe_float(new_totals.get("carbs_g"), 0.0) or 0.0)
        - float(_safe_float(old_totals.get("carbs_g"), 0.0) or 0.0),
        "fat_g": float(_safe_float(new_totals.get("fat_g"), 0.0) or 0.0)
        - float(_safe_float(old_totals.get("fat_g"), 0.0) or 0.0),
        "fiber_g": float(_safe_float(new_micros.get("fiber_g"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("fiber_g"), 0.0) or 0.0),
        "sugar_g": float(_safe_float(new_micros.get("sugar_g"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("sugar_g"), 0.0) or 0.0),
        "sodium_mg": float(_safe_float(new_micros.get("sodium_mg"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("sodium_mg"), 0.0) or 0.0),
        "vitamin_d_ug": float(_safe_float(new_micros.get("vitamin_d_ug"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("vitamin_d_ug"), 0.0) or 0.0),
        "vitamin_b12_ug": float(_safe_float(new_micros.get("vitamin_b12_ug"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("vitamin_b12_ug"), 0.0) or 0.0),
        "iron_mg": float(_safe_float(new_micros.get("iron_mg"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("iron_mg"), 0.0) or 0.0),
        "magnesium_mg": float(_safe_float(new_micros.get("magnesium_mg"), 0.0) or 0.0)
        - float(_safe_float(old_micros.get("magnesium_mg"), 0.0) or 0.0),
    }


def _coerce_meal_qa_payload(raw: Dict[str, Any], vision: VisionScanV1Model) -> MealQAModel:
    src = raw if isinstance(raw, dict) else {}
    issues_in = src.get("issues") if isinstance(src.get("issues"), list) else []
    fixes_in = src.get("one_tap_fixes") if isinstance(src.get("one_tap_fixes"), list) else []

    issues = []
    for issue in issues_in[:4]:
        if not isinstance(issue, dict):
            continue
        msg = str(issue.get("message") or "").strip()
        if not msg:
            continue
        sev = str(issue.get("severity") or "medium").strip().lower()
        if sev not in {"low", "medium", "high"}:
            sev = "medium"
        issues.append(
            {
                "issue_type": str(issue.get("issue_type") or "quality_check").strip().lower() or "quality_check",
                "severity": sev,
                "message": msg,
            }
        )

    fixes = []
    for f in fixes_in[:4]:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or "").strip()
        if not label:
            continue
        patch = f.get("patch") if isinstance(f.get("patch"), dict) else {}
        fixes.append({"label": label, "patch": patch})

    qa_score = max(0.0, min(100.0, float(_safe_float(src.get("qa_score"), 0.0) or 0.0)))
    ask_to_confirm = str(src.get("ask_to_confirm") or "").strip() or None

    if not issues:
        if _clamp01(vision.vision_confidence, 0.65) < 0.72:
            issues.append(
                {
                    "issue_type": "low_visual_confidence",
                    "severity": "medium",
                    "message": "Low visual confidence - confirm portion/cooking/oil to improve accuracy.",
                }
            )
        else:
            issues.append(
                {
                    "issue_type": "quality_check",
                    "severity": "low",
                    "message": "Scan quality is acceptable.",
                }
            )

    if not fixes:
        fixes = [
            {"label": "Portion +20%", "patch": {"portion_multiplier": 1.2}},
            {"label": "Portion -20%", "patch": {"portion_multiplier": 0.8}},
            {"label": "Add oil 1 tsp", "patch": {"set_oil_added_tsp": {"item_id": "i1", "tsp": 1.0}}},
        ]

    if qa_score <= 0:
        qa_score = round(_clamp01(vision.vision_confidence, 0.65) * 100.0, 1)
    return _model_validate(
        MealQAModel,
        {"qa_score": qa_score, "issues": issues, "one_tap_fixes": fixes, "ask_to_confirm": ask_to_confirm},
    )


def gemini_meal_qa_v1(
    image_bytes: bytes,
    vision: VisionScanV1Model,
    nutrition_summary: Dict[str, Any],
    request_id: str = "",
    job_id: str = "",
) -> MealQAModel:
    _require_gemini_key()
    prompt = (
        "You are Meal QA for a nutrition app. "
        "Given the image and parsed meal summary, detect inconsistencies and provide one-tap correction patches. "
        "Return ONLY strict JSON in this shape: "
        '{"qa_score": 0, "issues":[{"issue_type":"string","severity":"low|medium|high","message":"string"}],'
        '"one_tap_fixes":[{"label":"string","patch":{"portion_multiplier":1.2}}],"ask_to_confirm":"string or null"}. '
        "Use only these patch keys: portion_multiplier, set_cooking_method, set_oil_added_tsp, swap_item, clarifying_answer."
    )
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    compact = {
        "vision_confidence": vision.vision_confidence,
        "top_candidates": [_model_dump(x) for x in vision.top_candidates[:3]],
        "clarifying_question": _model_dump(vision.clarifying_question) if vision.clarifying_question else None,
        "items": [_model_dump(x) for x in vision.items],
        "nutrition_summary": nutrition_summary,
    }
    try:
        text = _generate_scan_content(
            [prompt, json.dumps(compact, ensure_ascii=True, separators=(",", ":")), img],
            purpose="meal_qa",
            request_id=request_id,
            job_id=job_id,
        )
        parsed = coach_logic.extract_json_object(text)
        if isinstance(parsed, dict):
            return _coerce_meal_qa_payload(parsed, vision)
        raise ValueError("No JSON object returned by model.")
    except Exception as e:
        logger.info(f"meal QA LLM fallback: {str(e)[:220]}")
    return _coerce_meal_qa_payload({}, vision)


def gemini_meal_qa_rerun_v1(
    vision: VisionScanV1Model,
    nutrition_summary: Dict[str, Any],
    request_id: str = "",
    job_id: str = "",
) -> MealQAModel:
    """
    Rerun path without re-uploading image. Uses stored scan context + edited nutrition summary.
    """
    _require_gemini_key()
    prompt = (
        "You are Meal QA for a nutrition app. "
        "Given scan context and edited meal summary, detect likely inconsistencies and suggest one-tap fixes. "
        "Return ONLY strict JSON in this shape: "
        '{"qa_score": 0, "issues":[{"issue_type":"string","severity":"low|medium|high","message":"string"}],'
        '"one_tap_fixes":[{"label":"string","patch":{"portion_multiplier":1.2}}],"ask_to_confirm":"string or null"}. '
        "Use only these patch keys: portion_multiplier, set_cooking_method, set_oil_added_tsp, swap_item, clarifying_answer."
    )
    compact = {
        "vision_confidence": vision.vision_confidence,
        "top_candidates": [_model_dump(x) for x in vision.top_candidates[:3]],
        "clarifying_question": _model_dump(vision.clarifying_question) if vision.clarifying_question else None,
        "items": [_model_dump(x) for x in vision.items],
        "nutrition_summary": nutrition_summary,
    }
    try:
        text = _generate_scan_content(
            [prompt, json.dumps(compact, ensure_ascii=True, separators=(",", ":"))],
            purpose="meal_qa_rerun",
            request_id=request_id,
            job_id=job_id,
        )
        parsed = coach_logic.extract_json_object(text)
        if isinstance(parsed, dict):
            return _coerce_meal_qa_payload(parsed, vision)
        raise ValueError("No JSON object returned by model.")
    except Exception as e:
        logger.info(f"meal QA rerun LLM fallback: {str(e)[:220]}")
    return _coerce_meal_qa_payload({}, vision)


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


@app.post("/supplement/scan")
async def supplement_scan(
    request: Request,
    front_image: UploadFile = File(...),
    back_image: UploadFile = File(...),
    product_type: str = Form("whey_protein"),
    brand: str = Form(""),
    variant: str = Form(""),
    barcode: str = Form(""),
    batch_number: str = Form(""),
    mfg_date: str = Form(""),
    expiry_date: str = Form(""),
    region: str = Form(""),
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_country_code: Optional[str] = Header(default=None, alias="X-Country-Code"),
    cf_ipcountry: Optional[str] = Header(default=None, alias="CF-IPCountry"),
    x_vercel_ip_country: Optional[str] = Header(default=None, alias="X-Vercel-IP-Country"),
):
    uid = require_user_id(x_user_id, user_id)
    require_ai_consent(uid)
    request_id = _new_request_id()

    product = str(product_type or "whey_protein").strip().lower()
    if product not in SUPPLEMENT_SUPPORTED_PRODUCT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_product_type",
                "supported": sorted(list(SUPPLEMENT_SUPPORTED_PRODUCT_TYPES)),
            },
        )

    front_bytes = await _read_valid_image_bytes(front_image, "front_image")
    back_bytes = await _read_valid_image_bytes(back_image, "back_image")
    image_hash = hashlib.sha256(front_bytes + b"::" + back_bytes).hexdigest()

    extracted = extract_supplement_data(
        front_bytes,
        back_bytes,
        barcode_hint=barcode,
        batch_hint=batch_number,
        request_id=request_id,
    )
    region_code = _infer_supplement_region(
        region,
        request=request,
        header_values=[x_country_code, cf_ipcountry, x_vercel_ip_country],
    )

    normalized = normalize_supplement_data(
        extracted,
        product_type=product,
        region=region_code,
        brand_override=brand,
        variant_override=variant,
        barcode_override=barcode,
        batch_override=batch_number,
        mfg_date_override=mfg_date,
        expiry_date_override=expiry_date,
    )
    score, flags = calculate_authenticity_score(normalized)
    level = interpret_supplement_score(score)
    explanation = _supplement_explanation(score, flags)

    row = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "product_type": product,
        "brand": normalized.get("brand"),
        "variant": normalized.get("variant"),
        "barcode": normalized.get("barcode"),
        "batch_number": normalized.get("batch_number"),
        "mfg_date": normalized.get("mfg_date"),
        "expiry_date": normalized.get("expiry_date"),
        "region": normalized.get("region"),
        "authenticity_score": score,
        "risk_flags": flags,
        "structured_data": normalized.get("structured_data"),
        "image_hash": image_hash,
        "created_at": _now_utc_naive().isoformat(),
    }
    stored = _store_supplement_scan(row)
    _upsert_supplement_batch_pattern(
        str(normalized.get("brand") or ""),
        str(normalized.get("batch_number") or ""),
        variant=str(normalized.get("variant") or ""),
        region=str(normalized.get("region") or ""),
        auth_score=float(_safe_float(score, 0.0) or 0.0),
        structured_data=normalized.get("structured_data") if isinstance(normalized.get("structured_data"), dict) else {},
    )

    out = {
        "scan_id": str(stored.get("id") or row["id"]),
        "product_type": product,
        "brand": normalized.get("brand"),
        "variant": normalized.get("variant"),
        "barcode": normalized.get("barcode"),
        "batch_number": normalized.get("batch_number"),
        "authenticity_score": score,
        "risk_flags": flags,
        "confidence_level": level,
        "explanation": explanation,
        "legal_note": SUPPLEMENT_LEGAL_DISCLAIMER,
        "source": "pattern_engine",
        "llm_used": bool(GEMINI_API_KEY),
        "structured_data": normalized.get("structured_data"),
        "request_id": request_id,
    }
    return _attach_debug_schema(out, bool(debug))


@app.post("/supplement/report_issue")
def supplement_report_issue(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(SupplementIssueReportRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_supplement_issue_payload", "raw": str(e)[:260]})

    uid = require_user_id(x_user_id, user_id or req.user_id)
    scan_id = str(req.scan_id or "").strip()
    if not scan_id:
        raise HTTPException(status_code=400, detail={"error": "scan_id_required"})
    row = {
        "id": str(uuid.uuid4()),
        "scan_id": scan_id,
        "issue_type": str(req.issue_type or "suspicious_packaging").strip().lower()[:64],
        "description": str(req.description or "").strip()[:500],
        "created_at": _now_utc_naive().isoformat(),
    }

    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_USER_FLAGS):
        return _attach_debug_schema({"ok": True, "reported": False, "scan_id": scan_id}, bool(debug))

    try:
        _sb_insert_with_column_fallback(TBL_SUPPLEMENT_USER_FLAGS, row)
    except Exception as e:
        if _mark_table_unavailable(TBL_SUPPLEMENT_USER_FLAGS, e):
            return _attach_debug_schema({"ok": True, "reported": False, "scan_id": scan_id}, bool(debug))
        raise

    resp = {"ok": True, "reported": True, "scan_id": scan_id, "issue_type": row["issue_type"]}
    return _attach_debug_schema(resp, bool(debug))



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
            "Easy add-ons: Greek yogurt, milk, paneer, tofu, lentils, or whey."
        ]
    if leucine_gap_g <= 1.0:
        return [
            "You're close — add a moderate protein boost.",
            "Good options: tofu/tempeh, paneer, Greek yogurt, lentils, or a protein shake."
        ]
    return [
        "You're quite short — this meal needs more protein to trigger muscle-building.",
        "Add a strong protein portion (e.g., tofu/paneer/lentils/Greek yogurt) or a protein shake."
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


def _scan_confidence_band(conf: float) -> str:
    c = _clamp01(conf, 0.0)
    if c >= 0.82:
        return "high"
    if c >= 0.72:
        return "medium"
    return "low"


_FRIED_METHOD_HINTS = {
    "fried",
    "deep fried",
    "deep-fried",
    "deep_fried",
    "pan fried",
    "pan-fried",
    "pan_fried",
    "stir fried",
    "stir-fried",
    "stir_fried",
    "air fried",
    "air-fried",
    "air_fried",
    "saute",
    "sauteed",
    "tempura",
    "crispy",
}
_FRIED_NAME_HINTS = {
    "fried",
    "fries",
    "tempura",
    "pakora",
    "bhaji",
    "cutlet",
    "fritter",
    "crispy",
}
_FRIED_CLARIFY_QUESTION = {
    "ask": "How was this cooked for oil estimate?",
    "options": [
        "Not fried / no added oil",
        "Air-fried (little/no oil)",
        "Pan/Shallow fried (~1 tsp oil)",
        "Deep fried (~2+ tsp oil)",
    ],
}
_LOW_CONF_CLARIFY_QUESTION = {
    "ask": "Is there visible added oil, sauce, or dressing?",
    "options": ["No", "Yes - light", "Yes - normal", "Yes - heavy"],
}


def _norm_phrase(text: Any) -> str:
    return str(text or "").strip().lower().replace("_", " ").replace("-", " ")


def _contains_hint(text: Any, hints: set) -> bool:
    phrase = _norm_phrase(text)
    if not phrase:
        return False
    return any(h in phrase for h in hints)


def _needs_fried_oil_question(items: List[Dict[str, Any]]) -> bool:
    for it in items or []:
        if not isinstance(it, dict):
            continue
        oil_tsp = max(0.0, float(_safe_float(it.get("oil_added_tsp"), 0.0) or 0.0))
        if oil_tsp > 0:
            continue
        method = it.get("cooking_method")
        name = it.get("name")
        if _contains_hint(method, _FRIED_METHOD_HINTS) or _contains_hint(name, _FRIED_NAME_HINTS):
            return True
    return False


def _build_scan_data_quality(vision: VisionScanV1Model, vision_threshold: float = 0.72) -> Dict[str, Any]:
    conf = _clamp01(vision.vision_confidence, 0.65)
    v_threshold = max(0.50, min(0.98, float(_safe_float(vision_threshold, 0.72) or 0.72)))
    band = _scan_confidence_band(conf)
    reason = ""
    if conf < v_threshold:
        reason = "Low image confidence; confirm portion/cooking/oil for more reliable totals."
    return {
        "confidence_band": band,
        "vision_confidence": round(conf, 3),
        "vision_threshold": round(v_threshold, 3),
        "missing_data_reason": reason,
    }


def _portion_multiplier_value(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("multiplier")
    if isinstance(raw, PortionMultiplierEdit):
        raw = raw.multiplier
    val = _safe_float(raw, None)
    if val is None:
        return None
    return max(0.3, min(3.0, float(val)))


def _apply_rerun_edits(base_items: List[Dict[str, Any]], edits: AnalyzeRerunEditsModel) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = [dict(x or {}) for x in (base_items or [])]
    if not out:
        return out

    mul = _portion_multiplier_value(edits.portion_multiplier)
    if mul is not None:
        for it in out:
            grams = max(0.0, float(_safe_float(it.get("grams"), 0.0) or 0.0))
            it["grams"] = round(grams * mul, 1)

    if edits.set_cooking_method:
        target = str(edits.set_cooking_method.item_id or "").strip()
        if target:
            for it in out:
                if str(it.get("item_id") or "") == target:
                    it["cooking_method"] = str(edits.set_cooking_method.method or "unknown").strip().lower() or "unknown"
                    break

    if edits.set_oil_added_tsp:
        target = str(edits.set_oil_added_tsp.item_id or "").strip()
        tsp = max(0.0, float(_safe_float(edits.set_oil_added_tsp.tsp, 0.0) or 0.0))
        if target:
            for it in out:
                if str(it.get("item_id") or "") == target:
                    it["oil_added_tsp"] = round(tsp, 2)
                    break

    if edits.swap_item:
        target = str(edits.swap_item.item_id or "").strip()
        new_name = str(edits.swap_item.new_name or "").strip()
        if target and new_name:
            for it in out:
                if str(it.get("item_id") or "") == target:
                    it["name"] = new_name
                    break

    answer = str(edits.clarifying_answer or "").strip().lower()
    if answer:
        if "deep" in answer:
            out[0]["oil_added_tsp"] = 2.5
        elif "pan" in answer or "shallow" in answer:
            out[0]["oil_added_tsp"] = 1.0
        elif "air" in answer and "fried" in answer:
            out[0]["oil_added_tsp"] = 0.5
        elif "heavy" in answer:
            out[0]["oil_added_tsp"] = 2.0
        elif "normal" in answer:
            out[0]["oil_added_tsp"] = 1.0
        elif "light" in answer:
            out[0]["oil_added_tsp"] = 0.5
        elif answer in {"no", "none", "no oil", "no added oil", "not fried / no added oil", "looks right"}:
            out[0]["oil_added_tsp"] = 0.0
    return out


def _build_scan_response(
    *,
    source: str,
    analysis_id: str,
    usage_row: Dict[str, Any],
    vision: VisionScanV1Model,
    results: List[Dict[str, Any]],
    totals: Dict[str, float],
    micros_payload: Dict[str, Any],
    meal_qa: MealQAModel,
    plan: str,
    coaching: Dict[str, Any],
    item_warnings: List[Dict[str, Any]],
    data_quality: Dict[str, Any],
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "analysis_id": analysis_id,
        "source": source,
        "total_kcal": round(float(_safe_float(totals.get("kcal"), 0.0) or 0.0), 1),
        "totals": {
            "kcal": round(float(_safe_float(totals.get("kcal"), 0.0) or 0.0), 1),
            "total_kcal": round(float(_safe_float(totals.get("kcal"), 0.0) or 0.0), 1),
            "protein_g": round(float(_safe_float(totals.get("protein_g"), 0.0) or 0.0), 1),
            "carbs_g": round(float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0), 1),
            "fat_g": round(float(_safe_float(totals.get("fat_g"), 0.0) or 0.0), 1),
            "micros": micros_payload,
        },
        "micros": micros_payload,
        "micronutrients": micros_payload,
        "items": results,
        "vision_confidence": round(_clamp01(vision.vision_confidence, 0.65), 3),
        "top_candidates": [_model_dump(x) for x in (vision.top_candidates or [])[:5]],
        "clarifying_question": _model_dump(vision.clarifying_question) if vision.clarifying_question else None,
        "editable_context": {"items": [_model_dump(x) for x in (vision.items or [])]},
        "meal_qa": _model_dump(meal_qa),
        "data_quality": data_quality,
        "usage": {
            "plan": usage_row.get("plan"),
            "remaining_day": int(usage_row.get("remaining_day") or 0),
            "remaining_month": int(usage_row.get("remaining_month") or 0),
        },
    }
    if item_warnings:
        response["warnings"] = item_warnings[:8]
    if plan_at_least(plan, "pro"):
        response["coaching"] = coaching
    else:
        response["locked"] = {"feature": "coaching", "required_plan": "pro"}
    return response


# -------------------- ANALYZE (PHOTO) --------------------
def _run_analyze_pipeline(
    *,
    user_id: str,
    image_bytes: bytes,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    debug: bool = False,
    request_id: str = "",
    job_id: str = "",
) -> Dict[str, Any]:
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user_id")
    started = time.time()
    calibration_settings = load_confidence_calibration_settings()
    vision_threshold = _calibration_setting_value(calibration_settings, "vision", "confidence_threshold", 0.72)
    portion_threshold = _calibration_setting_value(calibration_settings, "portion", "confidence_threshold", 0.75)
    oil_threshold = _calibration_setting_value(calibration_settings, "oil", "confidence_threshold", 0.70)
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    day_local_iso = today_local.isoformat()

    usage_row = consume_one_scan(uid, today=today_local)
    contents = image_bytes or b""
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    priors_context = _build_user_priors_context_for_candidates(uid, candidate_food_keys=[], limit=14)
    vision_scan = gemini_vision_scan_v1(
        contents,
        personalization_context=priors_context,
        vision_threshold=vision_threshold,
        request_id=request_id,
        job_id=job_id,
    )
    detected_items = [_model_dump(x) for x in (vision_scan.items or [])]
    detected_items, personalization_used = _apply_scan_user_priors(
        uid,
        detected_items,
        priors_context.get("always_ask_oil_for_methods") if isinstance(priors_context, dict) else [],
        portion_threshold=portion_threshold,
        oil_threshold=oil_threshold,
    )
    if detected_items:
        vision_payload = _model_dump(vision_scan)
        vision_payload["items"] = detected_items
        if personalization_used.get("asked_clarifying_question") and not vision_payload.get("clarifying_question"):
            vision_payload["clarifying_question"] = dict(_FRIED_CLARIFY_QUESTION)
        vision_scan = _coerce_vision_scan_payload(vision_payload, vision_threshold=vision_threshold)
    if vision_scan.clarifying_question and not personalization_used.get("asked_clarifying_question"):
        personalization_used["asked_clarifying_question"] = True
    if personalization_used.get("asked_clarifying_question") and not str(
        personalization_used.get("asked_clarifying_question_reason") or ""
    ).strip():
        if float(_safe_float(vision_scan.vision_confidence, 0.65) or 0.65) < vision_threshold:
            personalization_used["asked_clarifying_question_reason"] = "low_confidence"
    logger.info("Detected items: %s job_id=%s request_id=%s", detected_items, job_id, request_id)

    results, totals, total_micros, item_warnings = _compute_scan_nutrition(detected_items)
    micros_payload = _build_micros_payload(total_micros)
    total_kcal = float(_safe_float(totals.get("kcal"), 0.0) or 0.0)
    total_p = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
    total_c = float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0)
    total_f = float(_safe_float(totals.get("fat_g"), 0.0) or 0.0)

    scan_coaching = build_coaching_payload(
        total_kcal=total_kcal,
        protein_g=total_p,
        carbs_g=total_c,
        fat_g=total_f,
        mps_threshold_g=2.5,
    )
    meal_qa = gemini_meal_qa_v1(
        contents,
        vision_scan,
        {
            "totals": totals,
            "micros": micros_payload,
            "items": results,
        },
        request_id=request_id,
        job_id=job_id,
    )
    data_quality = _build_scan_data_quality(vision_scan, vision_threshold=vision_threshold)
    analysis_id = str(uuid.uuid4())
    image_hash = _sha256_bytes(contents)
    plan = str(usage_row.get("plan") or DEFAULT_PLAN).lower()

    response = _build_scan_response(
        source="photo",
        analysis_id=analysis_id,
        usage_row=usage_row,
        vision=vision_scan,
        results=results,
        totals=totals,
        micros_payload=micros_payload,
        meal_qa=meal_qa,
        plan=plan,
        coaching=scan_coaching,
        item_warnings=item_warnings,
        data_quality=data_quality,
    )
    response["personalization_used"] = personalization_used
    response["learning_applied"] = bool(
        personalization_used.get("portion_prior_used")
        or personalization_used.get("oil_prior_used")
        or personalization_used.get("asked_clarifying_question")
    )
    response["request_id"] = request_id
    response["job_id"] = job_id
    response["input_scan_id"] = analysis_id
    response["analysis_id"] = analysis_id
    response["meal_id"] = analysis_id
    response["coach_summary_source"] = "fallback"
    response["fli_source"] = "rules"
    response["source"] = "rules"
    resolved_scan_model = _choose_single_llm_model(SCAN_LLM_MODEL, None)
    response["model_used"] = resolved_scan_model
    response["error_code"] = ""
    response["tried_models"] = [resolved_scan_model]

    analysis_row = {
        "analysis_id": analysis_id,
        "user_id": uid,
        "day": day_local_iso,
        "created_at": dt.datetime.utcnow().isoformat(),
        "updated_at": dt.datetime.utcnow().isoformat(),
        "image_hash": image_hash,
        "vision_confidence": round(_clamp01(vision_scan.vision_confidence, 0.65), 3),
        "top_candidates_json": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
        "items_json": [_model_dump(x) for x in (vision_scan.items or [])],
        "nutrition_totals_json": {"totals": totals, "micros": micros_payload},
        "llm_outputs_json": {
            "vision": _model_dump(vision_scan),
            "meal_qa": _model_dump(meal_qa),
            "clarifying_question": _model_dump(vision_scan.clarifying_question) if vision_scan.clarifying_question else None,
        },
        "qa_json": _model_dump(meal_qa),
        "data_quality_json": data_quality,
        "tz_used": _timezone_label(tz=tz, tz_offset_min=tz_offset_min),
    }
    _store_meal_analysis(analysis_row)
    _store_analysis_memory(
        {
            "analysis_id": analysis_id,
            "user_id": uid,
            "created_at": analysis_row.get("created_at") or dt.datetime.utcnow().isoformat(),
            "image_hash": image_hash,
            "items_json": [_model_dump(x) for x in (vision_scan.items or [])],
            "top_candidates": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
            "vision_confidence": round(_clamp01(vision_scan.vision_confidence, 0.65), 3),
            "payload_hash": hashlib.sha256(
                json.dumps(
                    {
                        "items": [_model_dump(x) for x in (vision_scan.items or [])],
                        "top_candidates": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest(),
        }
    )

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
            extra={
                "plan": plan,
                "analysis_id": analysis_id,
                "warnings": item_warnings[:8],
                "vision_confidence": response.get("vision_confidence"),
                "job_id": job_id,
            },
        )
    except Exception as e:
        logger.warning(f"Meal events write skipped: {e}")

    try:
        inc = {
            "total_kcal": total_kcal,
            "protein_g": total_p,
            "carbs_g": total_c,
            "fat_g": total_f,
            "fiber_g": float(total_micros.get("fiber_g") or 0.0),
            "sodium_mg": float(total_micros.get("sodium_mg") or 0.0),
            "vitamin_d_ug": float(total_micros.get("vitamin_d_ug") or 0.0),
            "vitamin_b12_ug": float(total_micros.get("vitamin_b12_ug") or 0.0),
            "iron_mg": float(total_micros.get("iron_mg") or 0.0),
            "magnesium_mg": float(total_micros.get("magnesium_mg") or 0.0),
        }
        daily_totals_row = add_to_daily_totals(uid, inc, day=day_local_iso)
        response["daily_totals_version"] = str(int(_safe_float(daily_totals_row.get("daily_totals_version"), 0) or 0))
        response["daily"] = build_daily_summary(uid, day=day_local_iso)
    except Exception as e:
        logger.warning(f"Daily totals update skipped: {e}")

    try:
        weekly_predictive_internal = None
        memory = recompute_behavior_memory(uid, day_iso=day_local_iso, tz=tz, tz_offset_min=tz_offset_min)
        if isinstance(memory, dict):
            weekly_predictive_internal = memory.get("weekly_metrics")
            response["weekly_insights"] = memory.get("weekly_insights")
            response["weekly_metrics"] = _public_predictive_signals(
                memory.get("weekly_metrics"),
                memory.get("week_start") or _week_start_monday(day_local_iso),
            )
    except Exception as e:
        weekly_predictive_internal = None
        logger.warning(f"Behavior memory recompute skipped: {e}")

    scan_ts = dt.datetime.utcnow().isoformat()
    response["scan_id"] = analysis_id
    response["latest_scan_id"] = analysis_id
    response["latest_scan_ts"] = scan_ts
    try:
        coach_payload = _build_server_daily_coach_payload(uid, day_local_iso, tz=tz, tz_offset_min=tz_offset_min)
        state_obj = coach_payload.get("_state") if isinstance(coach_payload.get("_state"), dict) else {}
        daily_signals = dict(coach_payload.get("signals", {}) if isinstance(coach_payload.get("signals"), dict) else {})
        daily_signals["scan_count"] = int(_safe_float(state_obj.get("scan_count"), 0) or 0)
        response["today_totals"] = coach_payload.get("consumed", {})
        response["daily_signals"] = daily_signals
        response["state_signature"] = str(coach_payload.get("_state_signature") or "")
        response["daily_totals_version"] = str(
            coach_payload.get("daily_totals_version")
            or ((state_obj or {}).get("daily_totals_version"))
            or response.get("daily_totals_version")
            or response["state_signature"]
        )
        coach_tone_pref = _normalize_daily_tone_id(
            ((coach_payload.get("profile") or {}).get("tone_preference") if isinstance(coach_payload.get("profile"), dict) else "")
            or "supportive"
        )
        quick_fli = _build_quick_fli_response(
            coach_payload,
            weekly_predictive=weekly_predictive_internal,
            latest_scan_id=analysis_id,
            latest_scan_ts=scan_ts,
            tone_preference=coach_tone_pref,
            user_id=uid,
        )
        response["fat_loss_intelligence"] = quick_fli
        response["fat_loss_intelligence_status"] = "pending" if GEMINI_API_KEY else "ready"
        response["fat_loss_intelligence_updated_at"] = quick_fli.get("updatedAt")
        response["coach_summary_source"] = str(quick_fli.get("source") or "fallback")
        response["fli_source"] = str(quick_fli.get("source") or "fallback")
        response["model_used"] = str(quick_fli.get("model_used") or quick_fli.get("llm_model_used") or SCAN_LLM_MODEL)
        response["error_code"] = str(quick_fli.get("error_code") or quick_fli.get("llm_error_code") or "")
        response["tried_models"] = list(quick_fli.get("tried_models") or quick_fli.get("llm_tried_models") or [SCAN_LLM_MODEL])
        if GEMINI_API_KEY:
            _warm_daily_coach_async(
                uid,
                day_local_iso,
                latest_scan_id=analysis_id,
                latest_scan_ts=scan_ts,
                tone_preference=coach_tone_pref,
                tz=tz,
                tz_offset_min=tz_offset_min,
            )
    except Exception as e:
        logger.warning(f"Analyze FLI payload build skipped: {e}")

    totals_hash = hashlib.sha256(
        json.dumps(
            {
                "kcal": round(float(_safe_float(totals.get("kcal"), 0.0) or 0.0), 1),
                "protein": round(float(_safe_float(totals.get("protein_g"), 0.0) or 0.0), 1),
                "carbs": round(float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0), 1),
                "fat": round(float(_safe_float(totals.get("fat_g"), 0.0) or 0.0), 1),
                "fiber": round(float(_safe_float(micros_payload.get("fiber_g"), 0.0) or 0.0), 1),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    logger.info(
        "analyze_success user=%s scan_id=%s job_id=%s scan_count=%s totals_hash=%s",
        uid,
        analysis_id,
        job_id,
        int(_safe_float((response.get("daily_signals") or {}).get("scan_count"), 0) or 0),
        totals_hash,
    )
    response["latency_ms"] = int(max(0, round((time.time() - started) * 1000)))
    return _attach_debug_schema(response, bool(debug))


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    require_ai_consent(uid)
    request_id = _new_request_id()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    job_id = str(uuid.uuid4())
    input_path = _analysis_job_file_path(job_id)
    with open(input_path, "wb") as f:
        f.write(contents)

    row = _store_analysis_job(
        {
            "id": job_id,
            "user_id": uid,
            "status": "queued",
            "created_at": _now_utc_naive().isoformat(),
            "updated_at": _now_utc_naive().isoformat(),
            "input_path": input_path,
            "result_json": None,
            "error": "",
            "request_id": request_id,
        }
    )
    try:
        _enqueue_analysis_job(
            {
                "job_id": job_id,
                "id": job_id,
                "user_id": uid,
                "input_path": input_path,
                "tz": tz,
                "tz_offset_min": tz_offset_min,
                "request_id": request_id,
            }
        )
    except Exception as e:
        err_text = f"job_enqueue_failed: {str(e)[:220]}"
        _patch_analysis_job(
            job_id,
            {
                "status": "done",
                "error": err_text,
                "result_json": _minimal_analysis_fallback_result(job_id, request_id, err_text),
            },
        )
        raise HTTPException(status_code=503, detail="Analyze queue is temporarily busy. Please retry.")

    logger.info("analysis_job queued job_id=%s user=%s request_id=%s", job_id, uid, request_id)
    out = {
        "job_id": job_id,
        "status": str(row.get("status") or "queued"),
        "request_id": request_id,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "poll_url": f"/jobs/{job_id}",
    }
    out = _attach_debug_schema(out, bool(debug))
    return JSONResponse(status_code=202, content=out)


@app.get("/jobs/{job_id}")
def get_analysis_job(
    job_id: str,
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    row = _get_analysis_job(job_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "job_id": job_id})
    owner = str(row.get("user_id") or "").strip()
    if owner and owner != uid:
        raise HTTPException(status_code=403, detail="Job does not belong to this user.")
    status = str(row.get("status") or "queued").strip().lower() or "queued"
    out = {
        "job_id": str(row.get("id") or job_id),
        "status": status,
        "progress": _analysis_job_progress(status),
        "request_id": str(row.get("request_id") or ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "error": str(row.get("error") or "") if status in {"failed", "done"} else "",
    }
    if status == "done":
        result_obj = row.get("result_json")
        if isinstance(result_obj, str):
            result_obj = _parse_jsonish(result_obj, {})
        out["result"] = result_obj if isinstance(result_obj, dict) else {}
    return _attach_debug_schema(out, bool(debug))


@app.get("/jobs/{job_id}/result")
def get_analysis_job_result(
    job_id: str,
    user_id: Optional[str] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    row = _get_analysis_job(job_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "job_id": job_id})
    owner = str(row.get("user_id") or "").strip()
    if owner and owner != uid:
        raise HTTPException(status_code=403, detail="Job does not belong to this user.")
    status = str(row.get("status") or "queued").strip().lower() or "queued"
    if status == "failed":
        raise HTTPException(status_code=409, detail={"error": "job_failed", "message": str(row.get("error") or "Analyze job failed")})
    if status != "done":
        raise HTTPException(status_code=409, detail={"error": "job_not_ready", "status": status})
    result_obj = row.get("result_json")
    if isinstance(result_obj, str):
        result_obj = _parse_jsonish(result_obj, {})
    out = result_obj if isinstance(result_obj, dict) else {}
    out.setdefault("job_id", str(row.get("id") or job_id))
    out.setdefault("request_id", str(row.get("request_id") or ""))
    return _attach_debug_schema(out, bool(debug))


@app.post("/analyze/rerun")
def analyze_rerun(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    debug: Optional[bool] = False,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    request_id = _new_request_id()
    started = time.time()
    calibration_settings = load_confidence_calibration_settings()
    vision_threshold = _calibration_setting_value(calibration_settings, "vision", "confidence_threshold", 0.72)
    portion_threshold = _calibration_setting_value(calibration_settings, "portion", "confidence_threshold", 0.75)
    oil_threshold = _calibration_setting_value(calibration_settings, "oil", "confidence_threshold", 0.70)
    raw_payload = payload if isinstance(payload, dict) else {}
    try:
        logger.info(
            "analyze_rerun incoming request_id=%s user=%s payload=%s",
            request_id,
            uid,
            json.dumps(raw_payload, ensure_ascii=True)[:1800],
        )
    except Exception:
        logger.info("analyze_rerun incoming request_id=%s user=%s payload_unserializable=1", request_id, uid)
    raw_analysis_id = str(raw_payload.get("analysis_id") or raw_payload.get("scan_id") or "").strip()
    if not raw_analysis_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_rerun_payload",
                "message": "Missing analysis_id or scan_id.",
                "field": "analysis_id",
                "expected_schema": {"analysis_id": "string (or scan_id)", "edits": "object|array", "edit": "object"},
            },
        )
    raw_payload = dict(raw_payload)
    raw_payload["analysis_id"] = raw_analysis_id

    existing = _get_meal_analysis(uid, raw_analysis_id)
    if not existing:
        raise HTTPException(status_code=404, detail={"error": "analysis_not_found", "analysis_id": raw_analysis_id})

    coerced_payload = _coerce_rerun_payload(raw_payload, existing)
    coercion_errors = coerced_payload.pop("_coercion_errors", None)
    if isinstance(coercion_errors, list) and coercion_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "invalid_rerun_payload",
                "message": str(coercion_errors[0]),
                "field": "edits.swap_candidate",
                "expected_schema": {
                    "swap_candidate": {"item_id": "string", "candidate_index": "number >= 0"},
                    "swap_item": {"item_id": "string", "new_name": "string"},
                },
            },
        )
    try:
        req = _model_validate(AnalyzeRerunRequestModel, coerced_payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_friendly_rerun_validation_error(e))

    day_iso = _day_iso(existing.get("day"), tz=tz, tz_offset_min=tz_offset_min)
    items_raw = _parse_jsonish(existing.get("items_json"), [])
    if not isinstance(items_raw, list) or not items_raw:
        llm_raw = _parse_jsonish(existing.get("llm_outputs_json"), {})
        if isinstance(llm_raw, dict):
            vision_raw = llm_raw.get("vision") if isinstance(llm_raw.get("vision"), dict) else {}
            items_raw = vision_raw.get("items") if isinstance(vision_raw.get("items"), list) else []
    if not isinstance(items_raw, list) or not items_raw:
        raise HTTPException(status_code=400, detail={"error": "analysis_has_no_editable_items"})

    edited_items = _apply_rerun_edits(items_raw, req.edits)
    edited_items_pre_priors = [dict(x or {}) for x in edited_items]
    edited_items, personalization_used = _apply_user_priors_to_items(
        uid,
        edited_items,
        req.edits,
        portion_threshold=portion_threshold,
        oil_threshold=oil_threshold,
    )
    top_candidates = _parse_jsonish(existing.get("top_candidates_json"), [])
    clarifying_q = None
    llm_raw = _parse_jsonish(existing.get("llm_outputs_json"), {})
    if isinstance(llm_raw, dict):
        clarifying_q = llm_raw.get("clarifying_question")

    base_conf = _clamp01(existing.get("vision_confidence"), 0.65)
    if str(req.edits.clarifying_answer or "").strip():
        base_conf = min(1.0, base_conf + 0.07)
        clarifying_q = None

    vision_scan = _coerce_vision_scan_payload(
        {
            "vision_confidence": base_conf,
            "top_candidates": top_candidates,
            "clarifying_question": clarifying_q,
            "items": edited_items,
        },
        vision_threshold=vision_threshold,
    )
    if vision_scan.clarifying_question and not personalization_used.get("asked_clarifying_question"):
        personalization_used["asked_clarifying_question"] = True
    if personalization_used.get("asked_clarifying_question") and not str(
        personalization_used.get("asked_clarifying_question_reason") or ""
    ).strip():
        if float(_safe_float(vision_scan.vision_confidence, 0.65) or 0.65) < vision_threshold:
            personalization_used["asked_clarifying_question_reason"] = "low_confidence"

    results, totals, total_micros, item_warnings = _compute_scan_nutrition([_model_dump(x) for x in vision_scan.items])
    micros_payload = _build_micros_payload(total_micros)
    total_kcal = float(_safe_float(totals.get("kcal"), 0.0) or 0.0)
    total_p = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
    total_c = float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0)
    total_f = float(_safe_float(totals.get("fat_g"), 0.0) or 0.0)

    scan_coaching = build_coaching_payload(
        total_kcal=total_kcal,
        protein_g=total_p,
        carbs_g=total_c,
        fat_g=total_f,
        mps_threshold_g=2.5,
    )
    meal_qa = gemini_meal_qa_rerun_v1(
        vision_scan,
        {
            "totals": totals,
            "micros": micros_payload,
            "items": results,
        },
    )
    data_quality = _build_scan_data_quality(vision_scan, vision_threshold=vision_threshold)

    usage_row = get_or_init_usage(uid, today=_today_date(tz=tz, tz_offset_min=tz_offset_min))
    usage_row = normalize_resets(usage_row, today=_today_date(tz=tz, tz_offset_min=tz_offset_min))
    plan = str(usage_row.get("plan") or DEFAULT_PLAN).lower()

    response = _build_scan_response(
        source="photo_rerun",
        analysis_id=req.analysis_id,
        usage_row=usage_row,
        vision=vision_scan,
        results=results,
        totals=totals,
        micros_payload=micros_payload,
        meal_qa=meal_qa,
        plan=plan,
        coaching=scan_coaching,
        item_warnings=item_warnings,
        data_quality=data_quality,
    )
    response["rerun"] = {"ok": True, "analysis_id": req.analysis_id}
    response["request_id"] = request_id
    response["input_scan_id"] = str(req.analysis_id)
    response["analysis_id"] = str(req.analysis_id)
    response["meal_id"] = str(req.analysis_id)
    response["coach_summary_source"] = "fallback"
    response["fli_source"] = "rules"
    response["source"] = "rules"
    response["model_used"] = ""
    response["error_code"] = ""
    response["tried_models"] = []
    response["personalization_used"] = personalization_used
    response["learning_applied"] = bool(
        personalization_used.get("portion_prior_used")
        or personalization_used.get("oil_prior_used")
        or personalization_used.get("asked_clarifying_question")
    )

    try:
        _build_confidence_events_for_rerun(
            user_id=uid,
            analysis_id=str(req.analysis_id),
            meal_id=str(req.analysis_id),
            old_items=[dict(x or {}) for x in (items_raw or [])],
            edited_items_pre_priors=edited_items_pre_priors,
            edits=req.edits,
            calibration_settings=calibration_settings,
            vision_confidence=float(_safe_float(existing.get("vision_confidence"), base_conf) or base_conf),
        )
    except Exception as e:
        logger.info(f"confidence audit logging skipped: {e}")

    # Adjust daily totals by delta so rerun updates current day instead of double-counting.
    old_nt = _parse_jsonish(existing.get("nutrition_totals_json"), {})
    old_totals = old_nt.get("totals") if isinstance(old_nt.get("totals"), dict) else old_nt
    old_micros = old_nt.get("micros") if isinstance(old_nt.get("micros"), dict) else {}
    delta = _build_rerun_daily_delta(old_totals, old_micros, totals, micros_payload)
    try:
        daily_totals_row = add_to_daily_totals(uid, delta, day=day_iso)
        response["daily_totals_version"] = str(int(_safe_float(daily_totals_row.get("daily_totals_version"), 0) or 0))
        response["daily"] = build_daily_summary(uid, day=day_iso)
    except Exception as e:
        logger.warning(f"Daily totals rerun delta update skipped: {e}")

    rerun_scan_ts = dt.datetime.utcnow().isoformat()
    response["scan_id"] = str(req.analysis_id)
    response["latest_scan_id"] = str(req.analysis_id)
    response["latest_scan_ts"] = rerun_scan_ts
    try:
        coach_payload = _build_server_daily_coach_payload(uid, day_iso, tz=tz, tz_offset_min=tz_offset_min)
        state_obj = coach_payload.get("_state") if isinstance(coach_payload.get("_state"), dict) else {}
        daily_signals = dict(coach_payload.get("signals", {}) if isinstance(coach_payload.get("signals"), dict) else {})
        daily_signals["scan_count"] = int(_safe_float(state_obj.get("scan_count"), 0) or 0)
        response["today_totals"] = coach_payload.get("consumed", {})
        response["daily_signals"] = daily_signals
        response["state_signature"] = str(coach_payload.get("_state_signature") or "")
        response["daily_totals_version"] = str(
            coach_payload.get("daily_totals_version")
            or ((state_obj or {}).get("daily_totals_version"))
            or response.get("daily_totals_version")
            or response["state_signature"]
        )
        coach_tone_pref = _normalize_daily_tone_id(
            ((coach_payload.get("profile") or {}).get("tone_preference") if isinstance(coach_payload.get("profile"), dict) else "")
            or "supportive"
        )
        quick_fli = _build_quick_fli_response(
            coach_payload,
            latest_scan_id=str(req.analysis_id),
            latest_scan_ts=rerun_scan_ts,
            tone_preference=coach_tone_pref,
            user_id=uid,
        )
        response["fat_loss_intelligence"] = quick_fli
        response["fat_loss_intelligence_status"] = "pending" if GEMINI_API_KEY else "ready"
        response["fat_loss_intelligence_updated_at"] = quick_fli.get("updatedAt")
        response["coach_summary_source"] = str(quick_fli.get("source") or "fallback")
        response["fli_source"] = str(quick_fli.get("source") or "fallback")
        response["model_used"] = str(quick_fli.get("model_used") or quick_fli.get("llm_model_used") or "")
        response["error_code"] = str(quick_fli.get("error_code") or quick_fli.get("llm_error_code") or "")
        response["tried_models"] = list(quick_fli.get("tried_models") or quick_fli.get("llm_tried_models") or [])
        if GEMINI_API_KEY:
            _warm_daily_coach_async(
                uid,
                day_iso,
                latest_scan_id=str(req.analysis_id),
                latest_scan_ts=rerun_scan_ts,
                tone_preference=coach_tone_pref,
                tz=tz,
                tz_offset_min=tz_offset_min,
            )
    except Exception as e:
        logger.warning(f"Rerun FLI payload build skipped: {e}")

    _patch_meal_analysis(
        req.analysis_id,
        uid,
        {
            "updated_at": dt.datetime.utcnow().isoformat(),
            "vision_confidence": response.get("vision_confidence"),
            "items_json": [_model_dump(x) for x in (vision_scan.items or [])],
            "nutrition_totals_json": {"totals": totals, "micros": micros_payload},
            "qa_json": _model_dump(meal_qa),
            "data_quality_json": data_quality,
            "llm_outputs_json": {
                "vision": _model_dump(vision_scan),
                "meal_qa": _model_dump(meal_qa),
                "clarifying_question": _model_dump(vision_scan.clarifying_question) if vision_scan.clarifying_question else None,
            },
        },
    )
    _store_analysis_memory(
        {
            "analysis_id": str(req.analysis_id),
            "user_id": uid,
            "created_at": existing.get("created_at") or dt.datetime.utcnow().isoformat(),
            "image_hash": str(existing.get("image_hash") or ""),
            "items_json": [_model_dump(x) for x in (vision_scan.items or [])],
            "top_candidates": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
            "vision_confidence": round(_clamp01(vision_scan.vision_confidence, 0.65), 3),
            "payload_hash": hashlib.sha256(
                json.dumps(
                    {
                        "items": [_model_dump(x) for x in (vision_scan.items or [])],
                        "top_candidates": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest(),
        }
    )

    _store_meal_edit(
        {
            "edit_id": str(uuid.uuid4()),
            "analysis_id": req.analysis_id,
            "user_id": uid,
            "created_at": dt.datetime.utcnow().isoformat(),
            "edit_patch_json": _model_dump(req.edits),
        }
    )
    response["latency_ms"] = int(max(0, round((time.time() - started) * 1000)))
    return _attach_debug_schema(response, bool(debug))

