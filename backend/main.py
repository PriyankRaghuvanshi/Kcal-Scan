import asyncio
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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, List, Tuple, Union, Literal
from zoneinfo import ZoneInfo

import requests
try:
    import httpx
except Exception:  # pragma: no cover - optional runtime dependency fallback
    httpx = None
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Header, Body, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

import google.generativeai as genai
import coach_daily_logic as coach_logic
from supplement_barcode_utils import (
    normalize_barcode,
    detect_gtin_type,
    validate_checksum,
    extract_company_prefix,
)
from supplement_fssai_utils import (
    extract_fssai_license,
    extract_fssai_from_structured,
)
from nutrition_math_validator import validate_nutrition_math
from manufacturer_verification import get_manufacturer_verifier
from healthy_place_scoring import (
    HEALTHY_PLACE_SCORING_VERSION,
    best_options_for_place,
    score_healthy_place,
)
from healthy_order_recommender import suggest_best_order_for_place
from healthy_food_map import (
    build_healthy_food_map_response,
    build_sections,
    enrich_places_for_healthy_map,
)
from menu_item_scoring import recommend_menu_items_for_place
from menu_scan import build_menu_scan_response
from menu_intelligence_store import get_place_menu_intelligence, ingest_menu_intelligence
from recommendation_feedback_store import (
    ALLOWED_FEEDBACK_EVENTS,
    get_feedback_summary,
    get_place_item_feedback_signal,
    log_recommendation_feedback_event,
)
from user_venue_contributions import create_contribution
from contribution_review_flow import (
    list_pending_contributions,
    get_contribution_review_bundle,
    approve_contribution,
    reject_contribution,
)
from contribution_auto_promotion import (
    run_auto_promotion_for_place,
    run_auto_promotion_all,
    get_auto_promotion_status,
)
from meal_feedback_store import upsert_meal_feedback_event, list_meal_feedback_events
from meal_decision_event_store import log_meal_decision_event, list_meal_decision_events
from goal_coach_action_tracking import log_goal_coach_event
from yieldpilot_case_routes import router as yieldpilot_case_router
from push_token_store import (
    register_push_token,
    unregister_push_token,
    list_tokens_for_user,
    deactivate_token_by_value,
)
from push_delivery_store import (
    create_delivery_record,
    update_delivery_status,
    list_pending_receipt_ids,
    list_recent_deliveries,
    get_delivery_by_ticket_id,
    mark_token_deactivated_for_delivery,
    was_recently_sent,
)
from expo_push_service import (
    build_expo_push_message,
    send_expo_push_messages,
    fetch_expo_push_receipts,
    is_device_not_registered,
)
from push_rollout import (
    can_send_real_push,
    get_push_rollout_mode,
    get_push_test_user_ids,
    get_user_push_eligibility,
    get_rollout_status,
)
from user_last_location_store import upsert_user_location, get_user_location
from recipe_suggestions import build_recipe_suggest_response, record_recipe_feedback, list_saved_recipes
from push_send_flow import send_smart_alert_for_user as _send_smart_alert_for_user
from personal_response_summary import get_personal_meal_memory
from nutrition_mode import NutritionMode
from better_choice_nearby import build_better_choice_nearby_response
from daily_fatloss_coach import build_daily_fatloss_coach_response
from daily_food_decision import build_daily_decision_response
from lunch_decision import build_lunch_decision_response
from nearby_feed import build_healthy_nearby_feed
from ranked_place_builder import build_ranked_place_profile
from context_modes import infer_context_mode
from place_today_decision import evaluate_place_for_today
from smart_food_alerts import build_smart_food_alert_candidates, build_alert_audit_one_liner
from healthy_places_audit import (
    build_audit_one_liner,
    build_audit_result_row,
    build_filtered_out_entry,
)
from place_trace_debug import build_place_trace
from google_nearby_cache import get as google_nearby_cache_get, set as google_nearby_cache_set
from healthy_nearby_fastpath import shortlist_places
from healthy_nearby_rank_one import build_rank_context_from_request, rank_one_healthy_nearby_place
from local_venue_enrichment import summarize_launch_area_coverage
from launch_readiness_report import build_launch_readiness_report, build_all_areas_report
from suburb_remediation import generate_prioritized_remediation
from post_sync_remediation_report import (
    run_post_sync_launch_report,
    run_post_sync_reports_for_priority_areas,
    build_next_enrichment_targets_from_fetch,
)
from apply_enrichment_targets import apply_next_enrichment_targets, apply_enrichment_targets
from goal_coach import (
    build_starter_plan,
    build_daily_coach_state,
    build_daily_suggested_actions,
    build_weekly_review,
    build_weekly_next_step_action,
    compute_kickoff_status,
)
from goal_plan_store import (
    create_goal_plan,
    get_active_goal_plan,
    update_goal_plan_status,
)
from journey_store import (
    add_weight_entry,
    add_check_in,
    add_photo_entry,
    get_weight_entries,
    get_check_ins,
    get_photo_entries,
    get_journey_summary,
)
from admin_ops_dashboard import (
    build_ops_dashboard_summary,
    run_apply_next_targets,
    run_push_batch_dry_run,
    run_check_receipts,
    run_auto_promote,
)
from local_launch_enrichment_pack import (
    list_priority_launch_areas,
    seed_launch_area_enrichment,
    seed_all_priority_launch_areas,
    get_launch_enrichment_status,
)
from local_profile_supabase_sync import (
    sync_launch_pack_profiles_to_supabase,
    sync_auto_promoted_profiles_to_supabase,
    sync_all_trusted_local_profiles,
    get_sync_status,
)
from venue_intelligence_cache import get as venue_cache_get, cache_to_menu_payload, has as venue_cache_has
from background_enrichment_queue import enqueue as enrichment_enqueue, should_enqueue_for_low_specificity
from recommendation_safety import has_strong_menu_evidence, sanitize_recommended_item
from restaurant_reality_check import build_restaurant_reality_check
from share_card_formatter import build_best_order_share_card
from swap_intelligence import build_swap_suggestions
from weekly_coach import build_weekly_coach_payload
from nutrition_resolution_cache import (
    normalize_food_lookup_key,
    get_cached_nutrition_resolution,
    set_cached_nutrition_resolution,
    resolve_nutrition_with_cache,
)
from scan_performance_analytics import (
    record_scan_performance_event,
    build_scan_performance_summary,
    list_recent_events,
)
from vision_result_cache import (
    compute_image_fingerprint,
    get_cached_vision_result,
    set_cached_vision_result,
    should_reuse_cached_vision_result,
    vision_cache_skipped_reason as _vision_cache_skipped_reason,
)
from personalization_profiles import (
    get_personalized_reason,
    normalize_personalization_goal,
    personalization_goal_value,
)
from google_places_new_client import (
    PLACES_NEARBY_FIELD_MASK,
    build_nearby_search_payload,
    map_places_new_response,
    resolve_nearby_base,
)
try:
    from gs1_prefix_db import lookup_gs1_prefix_country
    _GS1_IMPORT_ERROR = ""
except Exception as _gs1_exc:  # pragma: no cover - deployment safety fallback
    _GS1_IMPORT_ERROR = str(_gs1_exc)

    def lookup_gs1_prefix_country(gtin: Any) -> Dict[str, Any]:
        return {"country_code": "", "org_hint": "", "confidence": 0.0}

# -------------------- LOGGING --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")
if _GS1_IMPORT_ERROR:
    logger.warning(
        "gs1_prefix_db import unavailable (%s); GS1 prefix checks disabled until module is deployed.",
        _GS1_IMPORT_ERROR[:220],
    )

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
app.include_router(yieldpilot_case_router, prefix="/yieldpilot")

# -------------------- ENV --------------------
USDA_API_KEY = os.getenv("USDA_API_KEY", "").strip()
USDA_BASE = "https://api.nal.usda.gov/fdc/v1"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

OPENFOODFACTS_BASE = os.getenv("OPENFOODFACTS_BASE", "https://world.openfoodfacts.org/api/v2").strip()
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
# Reuse existing env var names but enforce Places API (New) Nearby Search endpoint.
_GOOGLE_PLACES_BASE_RAW = os.getenv("GOOGLE_PLACES_NEARBY_BASE", os.getenv("GOOGLE_PLACES_BASE", "")).strip()
GOOGLE_PLACES_NEARBY_BASE = resolve_nearby_base(_GOOGLE_PLACES_BASE_RAW)
if _GOOGLE_PLACES_BASE_RAW and GOOGLE_PLACES_NEARBY_BASE != _GOOGLE_PLACES_BASE_RAW:
    logger.warning(
        "Ignoring legacy GOOGLE_PLACES_BASE value; Healthy Nearby now requires Places API (New) searchNearby endpoint."
    )
OFF_CACHE: Dict[str, Dict[str, Any]] = {}
OFF_CACHE_TTL = 60 * 60 * 24  # 24 hours
_mfr_enabled_raw = str(os.getenv("MFR_VERIFY_ENABLED", "0") or "").strip().lower()
MFR_VERIFY_ENABLED = _mfr_enabled_raw in {"1", "true", "yes", "on", "y"}
MFR_VERIFY_PROVIDER = str(os.getenv("MFR_VERIFY_PROVIDER", "off") or "off").strip().lower()
try:
    _mfr_cache_days = int(float(os.getenv("MFR_VERIFY_CACHE_TTL_DAYS", "14").strip() or "14"))
except Exception:
    _mfr_cache_days = 14
MFR_VERIFY_CACHE_TTL_SEC = max(7 * 86400, min(30 * 86400, _mfr_cache_days * 86400))
try:
    MFR_VERIFY_TIMEOUT_SEC = max(1.0, min(8.0, float(os.getenv("MFR_VERIFY_TIMEOUT_SEC", "5").strip() or "5")))
except Exception:
    MFR_VERIFY_TIMEOUT_SEC = 5.0
try:
    MFR_VERIFY_DAILY_LIMIT = max(1, min(500, int(float(os.getenv("MFR_VERIFY_DAILY_LIMIT", "30").strip() or "30"))))
except Exception:
    MFR_VERIFY_DAILY_LIMIT = 30

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
    # Coach voice LLM: allow a bit more wall time than scan LLM; configurable (default 12s, cap 20s).
    COACH_VOICE_TIMEOUT_SEC = max(3.0, min(20.0, float(os.getenv("COACH_VOICE_TIMEOUT_SEC", "12").strip() or "12")))
except Exception:
    COACH_VOICE_TIMEOUT_SEC = 12.0
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
_MFR_VERIFY_CACHE: Dict[str, Dict[str, Any]] = {}
_MFR_VERIFY_RATE_DAY = ""
_MFR_VERIFY_RATE_COUNTER: Dict[str, int] = {}
_MFR_VERIFY_LOCK = threading.Lock()
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


@app.get("/scan-performance/summary")
def scan_performance_summary(window_days: Optional[int] = 7):
    """Returns median/p90 time-to-first-result, time-to-final-result, and latency breakdown."""
    return build_scan_performance_summary(window_days=window_days or 7)


@app.get("/scan-performance/recent")
def scan_performance_recent(limit: Optional[int] = 50):
    """Returns recent scan performance events (newest first)."""
    return {"events": list_recent_events(limit=limit or 50)}


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
    caller_timeout = float(timeout_sec if timeout_sec is not None else 8.0)
    # Vision scan needs headroom; other callers (e.g. coach_voice_human) must honor their timeout_sec.
    if purpose_key.startswith("scan:vision_scan"):
        effective_timeout = max(25.0, min(90.0, caller_timeout))
    else:
        effective_timeout = max(3.0, min(120.0, caller_timeout))
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
    ingredient_hints: Optional[Dict[str, str]] = None


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


class SetItemGramsEdit(BaseModel):
    item_id: str
    grams: float


class PortionMultiplierEdit(BaseModel):
    item_id: str = ""
    multiplier: float


class ItemMacroOverrideEdit(BaseModel):
    """Manual correction for one line item after USDA resolution (rerun only)."""

    item_id: str = ""
    kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None


class AnalyzeRerunEditsModel(BaseModel):
    portion_multiplier: Optional[Union[float, PortionMultiplierEdit]] = None
    set_cooking_method: Optional[SetCookingMethodEdit] = None
    set_oil_added_tsp: Optional[SetOilAddedEdit] = None
    swap_item: Optional[SwapItemEdit] = None
    set_item_grams: Optional[SetItemGramsEdit] = None
    macro_override: Optional[ItemMacroOverrideEdit] = None
    clarifying_answer: Optional[str] = None
    clarifying_answers: Optional[List[Dict[str, str]]] = None


class AnalyzeRerunRequestModel(BaseModel):
    analysis_id: str
    edits: AnalyzeRerunEditsModel = Field(default_factory=AnalyzeRerunEditsModel)


class DailyFatLossCoachRequestModel(BaseModel):
    lat: float
    lng: float
    radius: int = 2000
    target_calories: float = 2000.0
    consumed_calories: float = 0.0
    target_protein_g: float = 150.0
    consumed_protein_g: float = 0.0
    limit: int = 5


class WeeklyCoachDayRowModel(BaseModel):
    date: str = ""
    consumed_calories: Optional[float] = None
    target_calories: Optional[float] = None
    consumed_protein_g: Optional[float] = None
    target_protein_g: Optional[float] = None
    lunch_calories: Optional[float] = None
    dinner_calories: Optional[float] = None
    lunch_protein_g: Optional[float] = None
    dinner_protein_g: Optional[float] = None


class WeeklyCoachChoiceRowModel(BaseModel):
    ts: str = ""
    place_name: str = ""
    recommended_order: str = ""
    fit_for_today: Optional[bool] = None
    health_score: Optional[float] = None
    why_it_helped: str = ""


class WeeklyCoachRequestModel(BaseModel):
    user_id: str = ""
    week_start: str = ""
    goal: str = ""
    cut_mode: bool = False
    daily_rows: List[WeeklyCoachDayRowModel] = Field(default_factory=list)
    choices: List[WeeklyCoachChoiceRowModel] = Field(default_factory=list)


class MenuIntelligenceItemModel(BaseModel):
    item_name: str
    estimated_calories: Optional[float] = None
    estimated_protein_g: Optional[float] = None
    estimated_carbs_g: Optional[float] = None
    estimated_fat_g: Optional[float] = None
    estimated_satiety: Optional[str] = None
    confidence: Optional[float] = None


class MenuIntelligenceIngestRequestModel(BaseModel):
    place_id: str
    restaurant_name: Optional[str] = ""
    cuisine: Optional[str] = ""
    source: str = "user_scan"
    menu_items: List[MenuIntelligenceItemModel] = Field(default_factory=list)


class RecommendationFeedbackEventRequestModel(BaseModel):
    event: str
    place_id: str
    item: Optional[str] = ""
    user_id: Optional[str] = ""
    session_id: Optional[str] = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)



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
                "type": "set_oil_added_tsp|set_cooking_method|swap_candidate|swap_item|set_portion_multiplier|macro_override|set_item_grams",
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
    if action_type in {"set_item_grams", "set_grams"}:
        grams = _safe_float(act.get("grams", act.get("value")), None)
        if grams is not None and float(grams) > 0:
            edits["set_item_grams"] = {"item_id": item_id, "grams": max(0.0, float(grams))}
        return
    if action_type in {"macro_override", "set_macro_override"}:
        mo: Dict[str, Any] = {"item_id": item_id}
        for k in ("kcal", "protein_g", "carbs_g", "fat_g"):
            v = _safe_float(act.get(k), None)
            if v is not None:
                mo[k] = max(0.0, float(v))
        if len(mo) > 1:
            edits["macro_override"] = mo
        return
    if action_type in {"clarifying_answer", "set_clarifying_answer"}:
        answer = str(act.get("value") or act.get("clarifying_answer") or "").strip()
        if answer:
            edits["clarifying_answer"] = answer
        return
    if action_type in {"clarifying_answers", "set_clarifying_answers"}:
        raw = act.get("answers") if isinstance(act.get("answers"), list) else act.get("clarifying_answers")
        if isinstance(raw, list):
            merged: List[Dict[str, str]] = []
            for x in raw:
                if isinstance(x, dict):
                    k = str(x.get("key") or "").strip()
                    v = str(x.get("value") or "").strip()
                    if k and v:
                        merged.append({"key": k, "value": v})
            if merged:
                edits["clarifying_answers"] = merged
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

    clarifying_answers_raw = src.get("clarifying_answers") or edits.get("clarifying_answers")
    if isinstance(clarifying_answers_raw, list):
        edits["clarifying_answers"] = [
            {"key": str(x.get("key") or "").strip(), "value": str(x.get("value") or "").strip()}
            for x in clarifying_answers_raw
            if isinstance(x, dict) and (str(x.get("key") or "").strip() or str(x.get("value") or "").strip())
        ]

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
    health_context: Dict[str, Any] = Field(default_factory=dict)


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


class RecipeSuggestRequestModel(BaseModel):
    user_id: str
    analysis_id: str = ""
    meal: Dict[str, Any] = Field(default_factory=dict)
    diet_style: str = "non-veg"
    goal_type: str = "fat_loss"
    plan: str = "free"


class RecipeFeedbackRequestModel(BaseModel):
    user_id: str
    recipe_key: str = ""
    action: str = ""
    cuisine: str = ""
    meal_tag: str = ""
    recipe_snapshot: Dict[str, Any] = Field(default_factory=dict)


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
            "stage": str(updated.get("stage") or "").strip() or None,
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

        def _on_fast_result(partial: Dict[str, Any]) -> None:
            _patch_analysis_job(
                job_id,
                {
                    "result_json": partial,
                    "stage": "enriching",
                    "updated_at": _now_utc_naive().isoformat(),
                },
            )
            logger.info("analysis_job fast_result written job_id=%s", job_id)

        result = _run_analyze_pipeline(
            user_id=user_id,
            image_bytes=contents,
            tz=tz,
            tz_offset_min=tz_offset_min,
            debug=False,
            request_id=request_id,
            job_id=job_id,
            on_fast_result=_on_fast_result,
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
        try:
            lb = result.get("latency_breakdown_ms") or {}
            record_scan_performance_event({
                "request_id": request_id,
                "analysis_id": str(result.get("analysis_id") or result.get("scan_id") or ""),
                "user_id": user_id,
                "job_id": job_id,
                "time_to_first_result_ms": int(result.get("time_to_first_result_ms") or 0),
                "time_to_final_result_ms": int(result.get("latency_ms") or result.get("time_to_final_result_ms") or 0),
                "resize_ms": int(lb.get("resize_ms") or 0),
                "priors_ms": int(lb.get("priors_ms") or 0),
                "vision_ms": int(lb.get("vision_ms") or 0),
                "nutrition_ms": int(lb.get("nutrition_ms") or 0),
                "meal_qa_ms": int(lb.get("meal_qa_ms") or 0),
                "enrichment_ms": int(lb.get("enrichment_ms") or 0),
                "nutrition_cache_hit_count": int(result.get("nutrition_cache_hit_count") or 0),
                "nutrition_cache_miss_count": int(result.get("nutrition_cache_miss_count") or 0),
                "vision_cache_reuse_used": bool(result.get("vision_cache_reuse_used")),
                "vision_cache_skipped_reason": str(result.get("vision_cache_skipped_reason") or ""),
                "vision_cache_hit_count": int(result.get("vision_cache_hit_count") or 0),
                "vision_cache_miss_count": int(result.get("vision_cache_miss_count") or 0),
                "image_was_resized": bool(result.get("image_was_resized")),
                "image_bytes_before": int(result.get("image_bytes_before") or 0),
                "image_bytes_after": int(result.get("image_bytes_after") or 0),
            })
        except Exception:
            pass
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


def _build_meal_snapshot_for_coach(
    meal_events: List[Dict[str, Any]],
    consumed_kcal: float,
    consumed_protein_g: float,
    goal_protein_g: float,
) -> str:
    """Build a short human-readable snapshot so the coach can reference actual meals and numbers."""
    photo_events = [
        e for e in (meal_events or [])
        if _event_text(e, "source", "event_source").lower() in {"photo", "scan", "meal", ""}
        or _event_text(e, "event_type").lower() in {"photo_analyze", "analyze", "scan"}
    ]
    n = len(photo_events)
    protein_gap = max(0.0, (goal_protein_g or 0) - (consumed_protein_g or 0))
    parts = [f"Today so far: {n} meal(s) logged, {int(round(consumed_protein_g or 0))} g protein, {int(round(consumed_kcal or 0))} kcal."]
    if protein_gap > 0:
        parts.append(f"Protein gap to target: {int(round(protein_gap))} g.")
    if photo_events:
        last_ev = photo_events[-1]
        ej = last_ev.get("event_json") if isinstance(last_ev.get("event_json"), dict) else {}
        items = ej.get("items") if isinstance(ej.get("items"), list) else []
        names = []
        for it in items[:5]:
            if isinstance(it, dict) and str(it.get("name") or "").strip():
                names.append(str(it.get("name") or "").strip())
        if names:
            parts.append(f"Latest meal: {', '.join(names[:4])}.")
    return " ".join(parts)


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


def _get_goal_coach_daily_consumed(user_id: str, day_iso: str) -> Optional[Dict[str, Any]]:
    """Return consumed_calories and consumed_protein_g for one day.
    Prefer daily_metrics (synced after scans); fallback to daily_totals so Goal Coach
    reflects scanned meals even when daily_metrics has not been written yet.
    """
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        row = sb_get_one(
            TBL_DAILY_METRICS,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "day": f"eq.{day_iso}",
                "limit": "1",
            },
        )
        if row:
            mj = row.get("metrics_json") if isinstance(row.get("metrics_json"), dict) else {}
            consumed = mj.get("consumed") if isinstance(mj.get("consumed"), dict) else {}
            kcal = float(_safe_float(consumed.get("kcal"), 0.0) or 0.0)
            protein_g = float(_safe_float(consumed.get("protein_g"), 0.0) or 0.0)
            if kcal > 0 or protein_g > 0:
                return {"consumed_calories": round(kcal, 1), "consumed_protein_g": round(protein_g, 1)}
        # Fallback: use daily_totals (source of truth from scans) so Goal Coach shows real meal data
        totals = get_daily_totals(user_id, day_iso)
        if totals:
            kcal = float(_safe_float(totals.get("total_kcal") or totals.get("kcal"), 0.0) or 0.0)
            protein_g = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
            return {"consumed_calories": round(kcal, 1), "consumed_protein_g": round(protein_g, 1)}
    except Exception:
        pass
    return None


def _goal_coach_metrics_rows_to_days(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map daily_metrics rows to weekly_coach day shape: date, consumed_calories, target_calories, consumed_protein_g, target_protein_g."""
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        day = str((r.get("day") or ""))[:10]
        if not day:
            continue
        mj = r.get("metrics_json") if isinstance(r.get("metrics_json"), dict) else {}
        consumed = mj.get("consumed") if isinstance(mj.get("consumed"), dict) else {}
        goals = mj.get("goals") if isinstance(mj.get("goals"), dict) else {}
        out.append({
            "date": day,
            "day": day,
            "consumed_calories": float(_safe_float(consumed.get("kcal"), 0.0) or 0.0),
            "target_calories": float(_safe_float(goals.get("kcal"), 0.0) or 0.0),
            "consumed_protein_g": float(_safe_float(consumed.get("protein_g"), 0.0) or 0.0),
            "target_protein_g": float(_safe_float(goals.get("protein_g"), 0.0) or 0.0),
        })
    return out


def _goal_coach_plan_merged(plan_row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge starter_plan into plan so target_calories, target_protein_g etc. are top-level for goal_coach helpers."""
    out = dict(plan_row)
    starter = plan_row.get("starter_plan") if isinstance(plan_row.get("starter_plan"), dict) else {}
    for k, v in (starter or {}).items():
        if out.get(k) is None and v is not None:
            out[k] = v
    return out


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
            return {"daily_limit": 5, "monthly_limit": 50}
        if plan == "elite":
            return {"daily_limit": 10, "monthly_limit": 300}
        if plan == "advanced":
            return {"daily_limit": 20, "monthly_limit": 600}
        if plan == "pro":
            return {"daily_limit": 40, "monthly_limit": 1200}
        if plan == "infinite":
            return {"daily_limit": 200, "monthly_limit": 100000}
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


def extract_packaging_fingerprint(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = structured_data if isinstance(structured_data, dict) else {}
    raw_text = str(payload.get("raw_text") or "").strip()
    if not raw_text:
        text_parts: List[str] = []
        for key in (
            "brand",
            "variant",
            "batch_number",
            "mfg_date",
            "expiry_date",
            "manufacturer",
            "distributed_by",
            "serving_size",
            "net_weight",
        ):
            val = str(payload.get(key) or "").strip()
            if val:
                text_parts.append(val)
        ingredients = payload.get("ingredients") if isinstance(payload.get("ingredients"), list) else []
        for token in ingredients[:80]:
            t = str(token or "").strip()
            if t:
                text_parts.append(t)
        nutrition_panel = payload.get("nutrition_panel") if isinstance(payload.get("nutrition_panel"), dict) else {}
        if nutrition_panel:
            text_parts.append(json.dumps(nutrition_panel, ensure_ascii=False))
        text_parts.append(json.dumps(payload, ensure_ascii=False))
        raw_text = "\n".join([x for x in text_parts if x])

    text = raw_text.lower()
    key_phrases = [
        "whey protein isolate",
        "instantized",
        "amino acid profile",
        "manufactured for",
        "distributed by",
        "net weight",
        "serving size",
    ]
    detected = [p for p in key_phrases if p in text]
    return {
        "phrase_count": len(detected),
        "phrases": detected[:10],
    }


def infer_batch_pattern(batch_number: str) -> Optional[str]:
    raw = _supplement_text(batch_number).upper()
    if not raw:
        return None
    pattern = re.sub(r"[A-Z]", "A", raw)
    pattern = re.sub(r"[0-9]", "9", pattern)
    pattern = re.sub(r"\s+", "", pattern)
    return pattern[:64] if pattern else None


def detect_seal_presence(image_bytes: Optional[bytes]) -> Dict[str, Any]:
    if not image_bytes:
        return {"seal_detected": None}
    return {"seal_detected": True}


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
            "- If FSSAI license is visible, include it inside nutrition_panel as key fssai_license_number.\n"
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


async def lookup_openfoodfacts(barcode: str) -> Dict[str, Any]:
    now = time.time()
    code = str(barcode or "").strip()
    if not code:
        return {"status": 0}

    cached = OFF_CACHE.get(code)
    if isinstance(cached, dict):
        ts = float(_safe_float(cached.get("ts"), 0.0) or 0.0)
        if now - ts < OFF_CACHE_TTL:
            data = cached.get("data")
            return data if isinstance(data, dict) else {"status": 0}

    url = f"https://world.openfoodfacts.net/api/v2/product/{code}"
    data: Dict[str, Any]
    try:
        if httpx is not None:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    body = r.json()
                    data = body if isinstance(body, dict) else {"status": 0}
                else:
                    data = {"status": 0}
        else:
            r = requests.get(url, timeout=5.0)
            if r.status_code == 200:
                body = r.json()
                data = body if isinstance(body, dict) else {"status": 0}
            else:
                data = {"status": 0}
    except Exception:
        data = {"status": 0}

    OFF_CACHE[code] = {"data": data, "ts": now}
    return data


def _mfr_cache_key(provider: str, gtin: str) -> str:
    return f"{str(provider or 'none').strip().lower()}:{_supplement_digits(gtin)}"


def _mfr_cache_get(provider: str, gtin: str) -> Optional[Dict[str, Any]]:
    key = _mfr_cache_key(provider, gtin)
    now = time.time()
    with _MFR_VERIFY_LOCK:
        entry = _MFR_VERIFY_CACHE.get(key)
        if not isinstance(entry, dict):
            return None
        ts = float(_safe_float(entry.get("ts"), 0.0) or 0.0)
        if now - ts > float(MFR_VERIFY_CACHE_TTL_SEC):
            _MFR_VERIFY_CACHE.pop(key, None)
            return None
        data = entry.get("data")
        return dict(data) if isinstance(data, dict) else None


def _mfr_cache_set(provider: str, gtin: str, payload: Dict[str, Any]) -> None:
    key = _mfr_cache_key(provider, gtin)
    with _MFR_VERIFY_LOCK:
        _MFR_VERIFY_CACHE[key] = {"ts": time.time(), "data": dict(payload or {})}


def _mfr_rate_allow(user_or_ip: str) -> bool:
    token = str(user_or_ip or "anon").strip() or "anon"
    day = _today_date().isoformat()
    with _MFR_VERIFY_LOCK:
        global _MFR_VERIFY_RATE_DAY
        if _MFR_VERIFY_RATE_DAY != day:
            _MFR_VERIFY_RATE_DAY = day
            _MFR_VERIFY_RATE_COUNTER.clear()
        used = int(_safe_float(_MFR_VERIFY_RATE_COUNTER.get(token), 0) or 0)
        if used >= int(_safe_float(MFR_VERIFY_DAILY_LIMIT, 30) or 30):
            return False
        _MFR_VERIFY_RATE_COUNTER[token] = used + 1
    return True


def _mfr_company_matches_brand(company_name: Any, brand_name: Any) -> bool:
    company = re.sub(r"[^a-z0-9]+", " ", str(company_name or "").lower()).strip()
    brand = re.sub(r"[^a-z0-9]+", " ", str(brand_name or "").lower()).strip()
    if not company or not brand:
        return False
    if brand in company or company in brand:
        return True
    company_tokens = {x for x in company.split() if len(x) >= 3}
    brand_tokens = {x for x in brand.split() if len(x) >= 3}
    if not company_tokens or not brand_tokens:
        return False
    overlap = company_tokens.intersection(brand_tokens)
    return len(overlap) >= 1


def _manufacturer_verification_signal(
    *,
    gtin: str,
    region: str,
    inferred_brand: str,
    user_or_ip: str,
    prefetched_off: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns internal verification signal with conservative status mapping.
    """
    out = {
        "status": "unavailable",
        "company_name": "",
        "source": "none",
        "latency_ms": 0,
        "raw": {"reason": "disabled"},
    }
    code = _supplement_digits(gtin)
    if not MFR_VERIFY_ENABLED:
        return out
    if not code:
        out["raw"] = {"reason": "missing_gtin"}
        return out
    if not _mfr_rate_allow(user_or_ip):
        out["raw"] = {"reason": "rate_limited"}
        return out

    cached = _mfr_cache_get(MFR_VERIFY_PROVIDER, code)
    if isinstance(cached, dict):
        return cached

    prefetched = {}
    if isinstance(prefetched_off, dict):
        prefetched[code] = prefetched_off

    verifier = get_manufacturer_verifier(
        enabled=MFR_VERIFY_ENABLED,
        provider=MFR_VERIFY_PROVIDER,
        timeout_sec=MFR_VERIFY_TIMEOUT_SEC,
        prefetched=prefetched,
        off_base_url=str(OPENFOODFACTS_BASE or "https://world.openfoodfacts.net/api/v2"),
    )
    result = verifier.verify_gtin(code, region=region)
    if not isinstance(result, dict):
        result = {
            "status": "error",
            "company_name": "",
            "source": str(MFR_VERIFY_PROVIDER or "none"),
            "latency_ms": 0,
            "raw": {"reason": "invalid_verifier_response"},
        }
    result["status"] = str(result.get("status") or "error").strip().lower()
    result["company_name"] = str(result.get("company_name") or "").strip()
    result["source"] = str(result.get("source") or MFR_VERIFY_PROVIDER or "none").strip().lower()
    result["latency_ms"] = int(_safe_float(result.get("latency_ms"), 0) or 0)
    if not isinstance(result.get("raw"), dict):
        result["raw"] = {"raw": str(result.get("raw") or "")[:220]}

    _mfr_cache_set(MFR_VERIFY_PROVIDER, code, result)
    return result


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


def calculate_authenticity_score(
    data: Dict[str, Any],
    precomputed_barcode_flags: Optional[List[str]] = None,
) -> Tuple[float, List[str]]:
    payload = data if isinstance(data, dict) else {}
    score = 100.0
    risk_flags: List[str] = []
    barcode = _supplement_digits(payload.get("barcode"))
    brand = _supplement_text(payload.get("brand"))
    batch_number = _supplement_text(payload.get("batch_number"))
    structured_data = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else payload

    if precomputed_barcode_flags is None:
        if not barcode_exists_in_db(barcode):
            score -= 25.0
            risk_flags.append("barcode_not_found")

        if not barcode_matches_brand(barcode, brand):
            score -= 20.0
            risk_flags.append("brand_barcode_mismatch")
    else:
        for flag in precomputed_barcode_flags or []:
            f = str(flag or "").strip()
            if not f:
                continue
            risk_flags.append(f)
        if "barcode_checksum_invalid" in risk_flags:
            score -= 25.0
        if "barcode_not_found_public_db" in risk_flags:
            score -= 10.0
        if "barcode_brand_mismatch" in risk_flags:
            score -= 20.0
        if "gs1_prefix_unknown" in risk_flags:
            score -= 5.0
        if "gs1_prefix_mismatch_region" in risk_flags:
            score -= 10.0
        if "batch_anomaly_macro_outlier" in risk_flags:
            score -= 15.0
        if "batch_anomaly_region_outlier" in risk_flags:
            score -= 10.0
        if "nutrition_kcal_mismatch" in risk_flags:
            score -= 15.0
        if "nutrition_protein_implausible" in risk_flags:
            score -= 10.0
        if "packaging_phrase_missing" in risk_flags:
            score -= 10.0
        if "batch_pattern_unseen" in risk_flags:
            score -= 10.0
        if "seal_missing" in risk_flags:
            score -= 15.0
        if "mfr_verified_company_match" in risk_flags:
            score += 5.0
        if "mfr_verified_company_mismatch" in risk_flags:
            score -= 15.0

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

    fssai_meta = extract_fssai_from_structured(structured_data if isinstance(structured_data, dict) else {})
    fssai_number = _supplement_digits((fssai_meta or {}).get("fssai_license_number"))
    fssai_label_present = bool((fssai_meta or {}).get("fssai_label_present"))
    if fssai_number and len(fssai_number) == 14:
        score += 2.0
    elif fssai_label_present:
        score -= 5.0
        risk_flags.append("fssai_number_invalid")

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


def _apply_supplement_score_cap(
    score: Any,
    *,
    barcode_verified: bool,
    same_region_scan_count: int,
) -> float:
    s = float(_safe_float(score, 0.0) or 0.0)
    if s > 95.0 and not (bool(barcode_verified) or int(_safe_float(same_region_scan_count, 0) or 0) >= 8):
        s = 95.0
    return round(max(0.0, min(100.0, s)), 1)


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


def _build_supplement_trust_payload(
    *,
    score: float,
    flags: List[str],
    normalized_barcode: str,
    off_status: int,
    off_brand: str,
    inferred_brand: str,
    gs1_info: Dict[str, Any],
    mfr_result: Dict[str, Any],
    mfr_status: str,
    fssai_license: str,
    proof_mode_enabled: bool,
    seal_detected: Any,
    batch_scan_count: int,
) -> Dict[str, Any]:
    """Human-readable trust signals for the supplement scanner UI (not a legal certification)."""
    fs = {str(x or "").strip().lower() for x in (flags or []) if str(x or "").strip()}
    has_barcode = bool(str(normalized_barcode or "").strip())
    gs1_cc = str((gs1_info or {}).get("country_code") or "").strip().upper()
    gs1_hint = str((gs1_info or {}).get("org_hint") or "").strip()
    off_brand_s = str(off_brand or "").strip()
    brand_s = str(inferred_brand or "").strip()
    mfr_src = str((mfr_result or {}).get("source") or "").strip().lower() or "registry"
    mfr_src_label = {
        "openfoodfacts": "Open Food Facts product record",
        "gs1_licensed": "GS1 licensed data (if configured)",
    }.get(mfr_src, "Manufacturer / GTIN registry signal")

    sources: List[Dict[str, str]] = []

    sources.append(
        {
            "id": "label_ocr",
            "name": "Label photos & OCR",
            "detail": "Front/back images analyzed to read barcode, batch, and nutrition panel text.",
            "status": "info",
        }
    )

    if not has_barcode:
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": "Public product database — skipped (no barcode to look up).",
                "status": "warn",
            }
        )
    elif "barcode_checksum_invalid" in fs or "barcode_invalid_format" in fs:
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": "Barcode failed format or checksum; database lookup not reliable.",
                "status": "bad",
            }
        )
    elif "barcode_not_found_public_db" in fs:
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": "No matching product found for this barcode in the public database.",
                "status": "warn",
            }
        )
    elif "barcode_brand_mismatch" in fs:
        detail = "Product found, but listed brand differs from the label we read."
        if off_brand_s:
            detail += f" DB: {off_brand_s[:72]}{'…' if len(off_brand_s) > 72 else ''}."
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": detail,
                "status": "warn",
            }
        )
    elif off_status == 1:
        detail = "Barcode matched a public product record."
        if off_brand_s:
            detail += f" Listed brand: {off_brand_s[:72]}{'…' if len(off_brand_s) > 72 else ''}."
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": detail,
                "status": "ok",
            }
        )
    else:
        sources.append(
            {
                "id": "open_food_facts",
                "name": "Open Food Facts",
                "detail": "Product database check did not return a confident match.",
                "status": "warn",
            }
        )

    if not has_barcode:
        sources.append(
            {
                "id": "gs1_prefix",
                "name": "GS1 company prefix",
                "detail": "Not evaluated without a valid barcode.",
                "status": "info",
            }
        )
    elif "gs1_prefix_mismatch_region" in fs:
        sources.append(
            {
                "id": "gs1_prefix",
                "name": "GS1 company prefix",
                "detail": "Prefix country does not align with your scan region (plausibility check).",
                "status": "bad",
            }
        )
    elif "gs1_prefix_unknown" in fs or not gs1_cc:
        sources.append(
            {
                "id": "gs1_prefix",
                "name": "GS1 company prefix",
                "detail": "Prefix could not be mapped to a country (reference data may be incomplete).",
                "status": "warn",
            }
        )
    else:
        extra = f" {gs1_hint}" if gs1_hint else ""
        sources.append(
            {
                "id": "gs1_prefix",
                "name": "GS1 company prefix",
                "detail": f"Prefix maps to region {gs1_cc}.{extra}".strip(),
                "status": "ok",
            }
        )

    if "mfr_verified_company_match" in fs:
        sources.append(
            {
                "id": "manufacturer",
                "name": "Brand / manufacturer link",
                "detail": f"GTIN owner aligns with label brand ({mfr_src_label}).",
                "status": "ok",
            }
        )
    elif "mfr_verified_company_mismatch" in fs:
        sources.append(
            {
                "id": "manufacturer",
                "name": "Brand / manufacturer link",
                "detail": f"Registered GTIN owner does not match the label brand ({mfr_src_label}).",
                "status": "bad",
            }
        )
    elif "mfr_verification_not_found" in fs:
        sources.append(
            {
                "id": "manufacturer",
                "name": "Brand / manufacturer link",
                "detail": f"No owner record found for this GTIN ({mfr_src_label}).",
                "status": "warn",
            }
        )
    elif "mfr_verification_unavailable" in fs:
        sources.append(
            {
                "id": "manufacturer",
                "name": "Brand / manufacturer link",
                "detail": "Registry lookup unavailable for this scan.",
                "status": "info",
            }
        )
    elif has_barcode:
        sources.append(
            {
                "id": "manufacturer",
                "name": "Brand / manufacturer link",
                "detail": f"No strong manufacturer signal ({mfr_src_label}).",
                "status": "info",
            }
        )

    fssai_digits = _supplement_digits(fssai_license)
    if fssai_digits:
        sources.append(
            {
                "id": "fssai",
                "name": "FSSAI license (label text)",
                "detail": f"Read from packaging: {fssai_digits}. Confirm on the official FSSAI portal.",
                "status": "info",
            }
        )

    n_scans = max(1, int(_safe_float(batch_scan_count, 0) or 0) + 1)
    sources.append(
        {
            "id": "community",
            "name": "Community batch signals",
            "detail": f"Anonymous scan patterns for this batch in your region (n≈{n_scans}). More scans improve stability.",
            "status": "ok" if n_scans >= 8 else "info",
        }
    )

    if proof_mode_enabled:
        if seal_detected is True:
            sources.append(
                {
                    "id": "seal",
                    "name": "Seal photo (high confidence mode)",
                    "detail": "Seal/cap evidence provided.",
                    "status": "ok",
                }
            )
        elif "seal_missing" in fs:
            sources.append(
                {
                    "id": "seal",
                    "name": "Seal photo (high confidence mode)",
                    "detail": "Expected seal evidence — photo missing or inconclusive.",
                    "status": "warn",
                }
            )
        else:
            sources.append(
                {
                    "id": "seal",
                    "name": "Seal photo (high confidence mode)",
                    "detail": "Optional seal check — no penalty applied.",
                    "status": "info",
                }
            )

    barcode_verified = (
        off_status == 1
        and "barcode_brand_mismatch" not in fs
        and "barcode_checksum_invalid" not in fs
        and "barcode_not_found_public_db" not in fs
    )
    s_val = float(_safe_float(score, 0.0) or 0.0)
    if barcode_verified and s_val >= 68.0 and "mfr_verified_company_mismatch" not in fs:
        tier = "strong"
        badge_label = "Cross-checked with Open Food Facts + label analysis"
    elif not has_barcode or "barcode_not_found_public_db" in fs or "barcode_checksum_invalid" in fs or s_val < 42.0:
        tier = "limited"
        badge_label = "Limited external confirmation — rely on breakdown below"
    else:
        tier = "moderate"
        badge_label = "Partial external match — review sources below"

    return {
        "badge": {"tier": tier, "label": badge_label},
        "sources": sources,
        "reference_urls": {
            "open_food_facts": "https://world.openfoodfacts.org/",
            "open_food_facts_product": f"https://world.openfoodfacts.org/product/{_supplement_digits(normalized_barcode)}"
            if has_barcode and _supplement_digits(normalized_barcode)
            else "",
        },
    }


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


def _supplement_region_confidence(
    region_form_value: Any,
    *,
    x_country_code: Any = "",
    cf_ipcountry: Any = "",
    x_vercel_ip_country: Any = "",
) -> float:
    """Rough confidence for region inference used in GS1 mismatch penalties."""
    if _infer_supplement_region(region_form_value):
        return 0.95
    for raw in (x_country_code, cf_ipcountry, x_vercel_ip_country):
        if _infer_supplement_region(raw):
            return 0.8
    return 0.35


def _supplement_prefix_region_matches(prefix_country_code: Any, user_region_code: Any) -> bool:
    pref = str(prefix_country_code or "").strip().upper()
    user = str(user_region_code or "").strip().upper()
    if not pref or not user:
        return True
    if pref == user:
        return True
    if pref == "EU":
        # Minimal coverage for current region-based plausibility checks.
        eu_codes = {
            "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
            "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
            "SI", "ES", "SE",
        }
        return user in eu_codes
    if pref == "US" and user in {"US", "CA"}:
        return True
    if pref == "CA" and user in {"CA", "US"}:
        return True
    return False


def _parse_region_scan_map(raw: Any) -> Dict[str, int]:
    payload = raw if isinstance(raw, dict) else _parse_jsonish(raw, {})
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, int] = {}
    for k, v in payload.items():
        region = _infer_supplement_region(k)
        if not region:
            continue
        out[region] = int(_safe_float(v, 0) or 0)
    return out


def compute_batch_anomaly(scan: Dict[str, Any], batch_pattern_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns anomaly_score 0..1 and reasons based on community pattern drift.
    Signals stay weak when scan_count is low.
    """
    row = batch_pattern_row if isinstance(batch_pattern_row, dict) else {}
    scan_count = int(_safe_float(row.get("scan_count"), 0) or 0)
    macro_variance_score = float(_safe_float(row.get("macro_variance_score"), 0.0) or 0.0)
    region_scan_map = _parse_region_scan_map(row.get("region_scan_map"))
    region_code = _infer_supplement_region((scan or {}).get("region"))

    anomaly = 0.0
    reasons: List[str] = []

    if macro_variance_score >= 35.0:
        anomaly += 0.72
        reasons.append("batch_anomaly_macro_outlier")
    elif macro_variance_score >= 25.0:
        anomaly += 0.52
        reasons.append("batch_anomaly_macro_outlier")

    if region_code and scan_count >= 8:
        region_hits = int(_safe_float(region_scan_map.get(region_code), 0) or 0)
        share = (float(region_hits) / float(max(scan_count, 1))) if scan_count > 0 else 0.0
        if region_hits == 0:
            anomaly += 0.55
            reasons.append("batch_anomaly_region_outlier")
        elif share < 0.08:
            anomaly += 0.35
            reasons.append("batch_anomaly_region_outlier")

    if scan_count < 8:
        anomaly *= 0.4

    anomaly = max(0.0, min(1.0, anomaly))
    return {
        "anomaly_score": round(anomaly, 3),
        "reasons": reasons,
        "scan_count": scan_count,
        "macro_variance_score": round(macro_variance_score, 2),
        "region_scan_map": region_scan_map,
    }


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


def _supplement_brand_pattern_stats(brand_txt: str, variant_txt: str) -> Dict[str, Any]:
    if not brand_txt:
        return {}
    if (not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)) or _is_table_disabled(TBL_SUPPLEMENT_BATCH_PATTERNS):
        return {}

    params: Dict[str, str] = {
        "select": "batch_pattern,batch_number,scan_count",
        "brand": f"eq.{brand_txt}",
        "limit": "500",
    }
    if variant_txt:
        params["variant"] = f"eq.{variant_txt}"

    rows: List[Dict[str, Any]] = []
    try:
        rows = sb_get_many(TBL_SUPPLEMENT_BATCH_PATTERNS, params=params)
    except Exception as e:
        raw = _http_exc_raw(e).lower()
        if "batch_pattern" in raw:
            fallback_params = dict(params)
            fallback_params["select"] = "batch_number,scan_count"
            try:
                rows = sb_get_many(TBL_SUPPLEMENT_BATCH_PATTERNS, params=fallback_params)
            except Exception as e2:
                if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e2):
                    logger.info(f"supplement batch pattern stats read skipped: {e2}")
                return {}
        else:
            if not _mark_table_unavailable(TBL_SUPPLEMENT_BATCH_PATTERNS, e):
                logger.info(f"supplement batch pattern stats read skipped: {e}")
            return {}

    pattern_counts: Dict[str, int] = {}
    total = 0
    for row in rows or []:
        pattern = _supplement_text((row or {}).get("batch_pattern")) or infer_batch_pattern((row or {}).get("batch_number"))
        if not pattern:
            continue
        weight = max(1, int(_safe_float((row or {}).get("scan_count"), 1) or 1))
        pattern_counts[pattern] = int(pattern_counts.get(pattern, 0) or 0) + weight
        total += weight

    if not pattern_counts:
        return {}
    dominant_pattern = max(pattern_counts.items(), key=lambda kv: kv[1])[0]
    return {
        "pattern_counts": pattern_counts,
        "dominant_pattern": dominant_pattern,
        "total_observations": int(total),
    }


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
    batch_pattern = infer_batch_pattern(batch)
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
            "batch_pattern": batch_pattern,
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
        "batch_pattern": batch_pattern,
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
    "You are a real human nutrition coach talking to a client. "
    "You have seen their meal scans, today's totals, protein/fiber gaps, fat loss stats, and weekly patterns. "
    "Talk like a coach who actually looked at their data: reference their numbers and meals in natural language. "
    "Use different words and sentence structures every time—never repeat the same phrases. Sound like a person, not a template. "
    "If RELATIONSHIP_STANCE is warm_reset: treat off-plan meals as normal human moments—reassure, then one specific compensating action. "
    "If RELATIONSHIP_STANCE is accountability: the pattern is repeating; be calm, direct, and caring, ask for a simple plan, mention timeline pressure qualitatively (no exact weight promises). No insults, no shouting. "
    "Provide behavior-focused suggestions only. No medical advice, diagnosis, treatment, or supplement recommendations. "
    "Use ONLY the provided numbers and context; do not invent metrics. Output strict JSON only. "
    "Your voice must feel distinctly different by the requested tone (supportive/strict/funny/indian_coach): each tone has its own energy and way of speaking so the user can tell which coach they chose. Keep language caring, calm, and never shouty."
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
        "Tone supportive: like a real coach who knows them—warm, human, conversational. "
        "If they went off-plan or had a treat, normalize it ('enjoying food sometimes is normal'), never shame them, "
        "then give one concrete next move tied to their numbers (e.g. trim refined carbs at dinner if kcal are high). "
        "If the data shows a repeating junk or overshoot pattern across days, shift firmer: clear expectations, plan the next meals, "
        "mention their goal timeline can slip if it keeps up—still respectful, never cruel. "
        "Vary wording; reference real gaps and scans; avoid corporate wellness filler."
    ),
    "strict": (
        "Tone strict: direct and accountable, like a high-performance coach who is calm and caring. Short, clear phrasing. No emoji. "
        "Show empathy first, then directional action and one concise consequence line (no medical claims). "
        "No harsh or shouting language; keep it respectful and supportive."
    ),
    "funny": (
        "Tone funny: playful, human coach. Use fresh hook phrases (not only 'Plot twist' or 'Cheat code'—vary: 'Here's the thing', "
        "'Real talk', 'Pro move', etc.). Max 2 emoji. Keep facts and advice solid with real direction. "
        "Mix humor + empathy + motivation without becoming generic."
    ),
    "indian_coach": (
        "Tone indian_coach: talk like a real Indian coach—natural Hinglish. Mix Hindi and English the way people actually speak "
        "(e.g. 'bhai', 'dost', 'yaar', 'chalo', 'karo', 'thoda', 'bilkul', 'sahi hai', 'theek hai', 'ab', 'dekho', 'simple', 'pakka', "
        "'mast', 'solid', 'kya baat', 'no tension', 'ho jayega'). Vary your phrases; don't limit to 2–3 words. "
        "Practical, respectful, conversational, and inspiring. Occasionally use a short Bhagavad Gita-inspired action idea "
        "(focus on karm/action and discipline, not religious preaching), while staying grounded in scan data."
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
        "signature_phrases": [
            "Small win", "Let's make it easy", "You're building momentum",
            "Good direction", "Nice progress", "One step at a time", "You've got this",
        ],
        "banned_words": ["lazy", "failure", "punishment", "worthless"],
        "must_include_any": [],  # LLM varies naturally; no fixed phrase required
    },
    "strict": {
        "emoji_max": 0,
        "signature_phrases": [
            "Minimum standard", "Do this today", "Non-negotiable",
            "Fix this", "Lock it in", "No drift", "Execute",
        ],
        "banned_words": ["lol", "maybe", "kinda", "sort of"],
        "must_include_any": [],
    },
    "funny": {
        "emoji_max": 2,
        "signature_phrases": [
            "Plot twist", "Cheat code", "Boss move", "Side quest",
            "Here's the thing", "Real talk", "Pro move", "Unlock", "Level up",
        ],
        "banned_words": ["stupid", "idiot", "pathetic"],
        "must_include_any": [],
    },
    "indian_coach": {
        "emoji_max": 1,
        "signature_phrases": [
            "Chalo", "Boss", "Bhai", "Dost", "Yaar", "Sahi hai", "Theek hai",
            "Scene simple hai", "Ho jayega", "Pakka", "Mast", "Solid", "Kya baat",
            "No tension", "Thoda adjust", "Dekho", "Bilkul", "Simple",
        ],
        "hinglish_phrases": [
            "bhai", "boss", "dost", "yaar", "chalo", "karo", "thoda", "bilkul",
            "sahi hai", "theek hai", "ab", "dekho", "simple", "pakka", "mast",
            "solid", "kya baat", "no tension", "ho jayega", "scene", "sorted",
            "done hai", "accha", "badhiya", "chalo ab",
        ],
        "banned_words": ["hopeless", "bakwaas", "useless"],
        "must_include_any": [],  # LLM uses natural Hinglish; no single phrase required
        "hinglish_min": 1,
        "hinglish_max": 4,
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
        "Today's direction improves if you fix this: {summary_fact}",
        "Good base today. Priority lever: {summary_fact}",
        "Simple focus for today: {summary_fact}",
        "Your log today points to one habit to refine: {summary_fact}",
        "Reading your day like a coach: {summary_fact}",
        "Fat loss loves clarity—here is today's clearest signal: {summary_fact}",
        "Momentum is decent; the upgrade path is: {summary_fact}",
        "You've logged enough for a useful pattern read: {summary_fact}",
        "The gentle upgrade for today is: {summary_fact}",
        "Your habits are teachable—main lesson right now: {summary_fact}",
        "No shame, just navigation: {summary_fact}",
        "Today's highest-ROI habit tweak: {summary_fact}",
        "Keep the wins; tighten this one thread: {summary_fact}",
        "If you change one routine today, make it this: {summary_fact}",
        "This is the lever that most protects your weekly average: {summary_fact}",
        "You are closer than it feels—next hinge is: {summary_fact}",
        "Stack small choices; start with: {summary_fact}",
    ],
    "strict": [
        "Current bottleneck is {bottleneck_label}. {summary_fact} Let's fix this today.",
        "Most important lever is {bottleneck_label}. {summary_fact}",
        "Results are limited by {bottleneck_label}. {summary_fact} Start now.",
        "{summary_fact} Do this today.",
        "Main limiter is {bottleneck_label}. {summary_fact} Let's execute now.",
        "This needs a gentle correction today: {summary_fact}",
        "Let's avoid more drift today. {summary_fact}",
        "Priority is {bottleneck_label}. {summary_fact} Keep it tight.",
        "Clear fix needed: {summary_fact}",
        "If unchanged, progress slows. {summary_fact}",
        "Timeline pressure is real—tighten {bottleneck_label}: {summary_fact}",
        "Your choices today either compound or cost—focus: {summary_fact}",
        "No extra lectures: the fix is {bottleneck_label}. {summary_fact}",
        "We protect fat-loss velocity by fixing: {summary_fact}",
        "One disciplined adjustment beats five vague intentions: {summary_fact}",
        "Standards slip when {bottleneck_label} slips; reset with: {summary_fact}",
        "Hold the line on {bottleneck_label} starting now: {summary_fact}",
        "This is the day-part that moves the needle: {summary_fact}",
        "Let's not negotiate with the log—execute: {summary_fact}",
        "Repeatable wins need a repeatable fix: {summary_fact}",
        "Your next meal is where you vote for the trend you want: {summary_fact}",
        "Quiet the noise; single priority: {summary_fact}",
    ],
    "funny": [
        "Plot twist: {summary_fact}",
        "Cheat code moment: {summary_fact}",
        "Boss move alert: {summary_fact}",
        "Side quest check: {summary_fact}",
        "Quick plot update: {summary_fact}",
        "Today's cheat code is simple: {summary_fact}",
        "Boss move for this meal cycle: {summary_fact}",
        "Tiny side quest, big payoff: {summary_fact}",
        "Game plan update: {summary_fact}",
        "Level-up lever today: {summary_fact}",
        "Patch notes incoming: {summary_fact}",
        "Your build needs one stat buff: {summary_fact}",
        "RNG didn't break; habits did—hotfix: {summary_fact}",
        "Speedrun cancelled; slow-and-steady wins: {summary_fact}",
        "Daily quest reminder: {summary_fact}",
        "Achievement almost unlocked—finish with: {summary_fact}",
        "Inventory check says: {summary_fact}",
        "Tutorial skipped; here's the real lesson: {summary_fact}",
        "Mini-boss named {bottleneck_label} spotted: {summary_fact}",
        "Combo broken—re-chain with: {summary_fact}",
        "Respawn screen avoided if you: {summary_fact}",
        "Loot box closed; grind this instead: {summary_fact}",
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
        "Dekho data kya bol raha hai: {summary_fact}",
        "Thoda discipline, zyada result—yeh line: {summary_fact}",
        "Bhai, fat loss mein clarity king hai; aaj ki clarity: {summary_fact}",
        "Aaj habit ka ek thread pakadna hai: {summary_fact}",
        "Theek hai, no fluff—main point: {summary_fact}",
        "Pakka wala fix aaj yeh hai: {summary_fact}",
        "Dost, next step obvious hai: {summary_fact}",
        "Solid week banane ke liye aaj yeh lock karo: {summary_fact}",
        "Hinglish mein seedhi baat: {summary_fact}",
        "Energy aur hunger dono ke liye best move: {summary_fact}",
        "Scene tab set hota hai jab {bottleneck_label} set ho—{summary_fact}",
        "Chalo compass sahi karte hain: {summary_fact}",
        "Mast effort; ab sharp edge: {summary_fact}",
    ],
    "supportive_warm": [
        "You're a little off plan today—and that's completely human. {summary_fact}",
        "Real talk: you enjoyed something heavier; that doesn't erase your week. {summary_fact}",
        "Today drifted, and that's okay—plenty of strong weeks include one loose meal. {summary_fact}",
        "Totally normal to want a treat; now we just balance the rest of the day. {summary_fact}",
        "You veered from target—no drama, we fix the next meal. {summary_fact}",
        "One richer choice happened; you can still land today softly. {summary_fact}",
        "Your body wanted flavor; your week still wants steadiness—bridge them with: {summary_fact}",
        "Gentle reset beats harsh shame; next hinge: {summary_fact}",
        "Label it a detour, not a disaster—course-correct with: {summary_fact}",
        "Comfort food days happen; learning still counts: {summary_fact}",
        "You did not fail a diet—you lived a day; tighten with: {summary_fact}",
        "Self-compassion plus one smart meal preserves fat-loss momentum: {summary_fact}",
        "Return to basics without punishing yourself: {summary_fact}",
        "Hunger and joy both matter; balance looks like: {summary_fact}",
        "One loose round does not undo your habits unless you let it stack: {summary_fact}",
        "Warm coaching mode: breathe, then execute: {summary_fact}",
        "Treat logged; values unchanged—next move: {summary_fact}",
        "We are protecting the trend, not judging a moment: {summary_fact}",
    ],
    "supportive_accountability": [
        "I'm going to be straight: this ultra-processed / calorie pattern is repeating—not a one-off. {summary_fact}",
        "We've seen several days like this; we need a tighter plan or your fat-loss timeline keeps stretching. {summary_fact}",
        "This isn't about guilt—it's a habit loop showing up in your scans. {summary_fact}",
        "Pattern check: junk-heavy days are stacking; time to reset structure together. {summary_fact}",
        "Your data says this is recurring, not random—let's lock the next 48 hours. {summary_fact}",
        "I care about your outcome, so I'm naming the pattern clearly: {summary_fact}",
        "Your fat-loss graph bends on weeks like this—interrupt the loop: {summary_fact}",
        "The signal is repetition, not a bad day—upgrade the system: {summary_fact}",
        "Cravings are human; predictable loops are fixable—start with: {summary_fact}",
        "Support means honesty: this needs structure before it becomes default: {summary_fact}",
        "We coach the habit, not your character—focus area: {summary_fact}",
        "If this rhythm continues, the goal date shifts—let's stabilize: {summary_fact}",
        "Your logs are asking for a plan, not more willpower: {summary_fact}",
        "Together we tighten the environment that keeps triggering this: {summary_fact}",
        "Pattern familiarity is a cue to change the script: {summary_fact}",
        "Repetition is information—use it: {summary_fact}",
        "Accountability is kindness with boundaries—here is the boundary: {summary_fact}",
    ],
    "strict_warm": [
        "You went over today—once is fine. Recover cleanly at the next meal: {summary_fact}",
        "Slip logged. No drama; execute balance now: {summary_fact}",
        "Treat happened. Tighten the next plate—protein and vegetables first: {summary_fact}",
        "Off-target calories today. Fix it with one disciplined next meal: {summary_fact}",
        "Deviation accepted. Close the day without stacking mistakes: {summary_fact}",
        "One indulgence ends here; next plate returns standards: {summary_fact}",
        "No spiraling—just realign macros and timing: {summary_fact}",
        "Discipline is the recovery tool; apply it now: {summary_fact}",
        "Close the loop today so tomorrow starts clean: {summary_fact}",
        "You enjoyed it; now earn back control in one action: {summary_fact}",
        "Single correction prevents a weekly overshoot: {summary_fact}",
        "Reset calories without self-attack—execute the fix: {summary_fact}",
        "Balance is a skill; practice it at the next sitting: {summary_fact}",
        "Own the slip, then own the comeback meal: {summary_fact}",
    ],
    "strict_accountability": [
        "Pattern check: high junk / calories are repeating across days. {summary_fact} Let's tighten structure.",
        "This habit loop is showing in your scans. {summary_fact} Plan the next 48 hours so your timeline stays on track.",
        "Repeated UPF drift is visible. {summary_fact} Start a steady reset from the next meal.",
        "Same pattern for multiple days. {summary_fact} Try a written two-meal plan.",
        "Data suggests this is recurring, not a one-off. {summary_fact} Let's lock consistency now.",
        "Fat loss doesn't negotiate with repeated shortcuts—interrupt this: {summary_fact}",
        "Your timeline needs protection; the pattern won't self-heal: {summary_fact}",
        "Repetition means rules, not motivation speeches: {summary_fact}",
        "We stop the drift where it starts—next intentional block: {summary_fact}",
        "Habit stacks fast; unwind it with structure today: {summary_fact}",
        "Enough data—time for a written protocol: {summary_fact}",
        "If you want the outcome, match the inputs—fix: {summary_fact}",
        "Process calories are a choice pattern now—change the choice architecture: {summary_fact}",
        "Serious weeks need serious guardrails: {summary_fact}",
    ],
    "funny_warm": [
        "Side quest: you ate the loot. Main quest: balance dinner. {summary_fact}",
        "Plot twist—you had fun. Don't wipe the save; fix the next meal. {summary_fact}",
        "Treat debuff applied; stack protein + veg to cleanse. {summary_fact}",
        "You cashed a cheat code—cool. Re-spec the next plate. {summary_fact}",
        "Boss fight paused for cake; resume with a clean round. {summary_fact}",
        "Snack DLC installed; uninstall with one clean meal plan: {summary_fact}",
        "Plot armor expired briefly—re-equip discipline: {summary_fact}",
        "You farmed joy points; now farm consistency: {summary_fact}",
        "Desync fixed by syncing dinner to target: {summary_fact}",
        "Treat arc ended—speedrun recovery: {summary_fact}",
        "Lag spike from sugar; stabilize with: {summary_fact}",
        "Buff eating happened; re-buff protein: {summary_fact}",
        "Save corruption risk: zero if you patch next meal: {summary_fact}",
    ],
    "funny_accountability": [
        "Speed-running snack mode again? {summary_fact} Patch the build this week.",
        "Same mini-boss every day—boring pattern. {summary_fact} Change the route.",
        "Your log is stuck in junk chapter. {summary_fact} Hard-mode plan required.",
        "Streak of processed pulls—RNG isn't the problem. {summary_fact} Commit to two clean meals.",
        "Achievement unlocked: pattern detected. {summary_fact} Grind consistency next.",
        "Daily quest: stop repeating the snack cutscene: {summary_fact}",
        "Your macro storyline needs a new writer: {summary_fact}",
        "Meta is broken—too many comfort pulls: {summary_fact}",
        "Grindset.exe crashed—reboot with structure: {summary_fact}",
        "World record attempt for same mistake—retire the category: {summary_fact}",
        "Inventory full of excuses; clear slot with a plan: {summary_fact}",
        "Patch Tuesday is now; deploy habits v2: {summary_fact}",
    ],
    "indian_coach_warm": [
        "Arre treat ho gaya—scene bigad nahi gaya. {summary_fact}",
        "Boss, aaj thoda zyada ho gaya, normal hai. Next meal se balance. {summary_fact}",
        "Ek rich meal—koi tension nahi, ab protein + veg se set karte hain. {summary_fact}",
        "Thoda drift hua, theek hai; ab practical fix karo. {summary_fact}",
        "Mast enjoy kiya—ab chalo next meal tight rakho. {summary_fact}",
        "Zindagi mein mithaas chahiye; trend ko bhi chahiye control—{summary_fact}",
        "Thoda comfort khaya, ab comfort zone se nikal ke action: {summary_fact}",
        "Ghar ka ya bahar ka, koi baat nahi—ab balance wala move: {summary_fact}",
        "Fat loss journey mein kabhi kabhi day heavy hota hai; lesson: {summary_fact}",
        "Chill maar, par next plate conscious rakho: {summary_fact}",
        "Boss, guilt ka scene chhodo, execution pakdo: {summary_fact}",
        "Ek meal heavy, next meal smart—yeh rhythm: {summary_fact}",
        "Treat = pause button, not game over—resume with: {summary_fact}",
        "Sahi coach wali baat: dhairya rakho, plan follow karo—{summary_fact}",
    ],
    "indian_coach_accountability": [
        "Bhai, pattern repeat ho raha hai scans mein—ab calm aur serious plan chahiye. {summary_fact}",
        "Dekho, junk days stack ho rahe hain; timeline stretch ho jayega. {summary_fact}",
        "Same scene baar baar—habit dikh rahi hai. {summary_fact} Ab structure lock karo.",
        "Data bol raha hai recurring hai, random nahi. {summary_fact} 48 ghante ka plan banao.",
        "Boss, consistency tut rahi hai—ab clear supportive rules set karte hain. {summary_fact}",
        "Samajh aa raha hai habit set ho gayi hai—ab todo badlo: {summary_fact}",
        "Fat loss tabhi grip karti hai jab pattern break hota hai—start: {summary_fact}",
        "Dost, repetition ko respect do—system change karo: {summary_fact}",
        "Weekly trend alarming nahi, lekin serious hai—intercept: {summary_fact}",
        "Ab sirf motivation nahi, protocol chahiye: {summary_fact}",
        "Aadat ko data se pakdo, phir replace karo: {summary_fact}",
        "Scene yeh hai: comfort eating loop—exit strategy: {summary_fact}",
        "Thoda tough love: yeh tab tak rahega jab tak plan na ho—{summary_fact}",
    ],
}

_COACH_WHY_STYLE_BANK = {
    "supportive": [
        "{impact}",
        "Why this matters: {impact}",
        "This matters because {impact}",
        "For your habits and weekly average: {impact}",
        "This is how the day shapes fat loss: {impact}",
        "Connect the dots: {impact}",
        "Your future week feels this choice: {impact}",
        "Coaching lens—cause and effect: {impact}",
        "Gentle truth for momentum: {impact}",
        "Hunger and calories both learn from this: {impact}",
        "Pattern-wise, here's the cost of ignoring it: {impact}",
        "Understanding beats guilt: {impact}",
        "This is the story your log is telling: {impact}",
    ],
    "strict": [
        "{impact}",
        "Reason: {impact}",
        "If unchanged, progress may stay unstable. {impact}",
        "Reality check: {impact}",
        "Non-negotiable link to results: {impact}",
        "Cause → effect, plainly: {impact}",
        "Timelines follow habits; note this: {impact}",
        "No sugar-coating the mechanism: {impact}",
        "Discipline exists because of facts like this: {impact}",
        "Your deficit math interacts with: {impact}",
        "This is where adherence meets outcome: {impact}",
        "Ignore it and the trend bends: {impact}",
        "Straight mechanism: {impact}",
    ],
    "funny": [
        "{impact}",
        "Why it matters: {impact}",
        "Translation: {impact}",
        "Lore drop: {impact}",
        "Plot relevance: {impact}",
        "Stats screen says: {impact}",
        "If you skip the tutorial: {impact}",
        "Bonus XP reason: {impact}",
        "Speedrun penalty if you ignore: {impact}",
        "Patch rationale: {impact}",
        "Devs notes (your body edition): {impact}",
        "Quest journal entry: {impact}",
    ],
    "indian_coach": [
        "{impact}",
        "Why matter karta hai: {impact}",
        "Simple reason: {impact}",
        "Samajh lo mechanism: {impact}",
        "Practical angle: {impact}",
        "Fat loss angle se: {impact}",
        "Dimaag mein yeh baithao: {impact}",
        "Seedha science-wali baat: {impact}",
        "Habit aur result ka link: {impact}",
        "Aaj ka lesson yeh hai: {impact}",
        "Boss, reason clear karte hain: {impact}",
        "Chalo cause-effect dekho: {impact}",
    ],
    "supportive_warm": [
        "{impact}",
        "Here's the human side: {impact}",
        "No stress—{impact}",
        "Soft landing still needs honesty: {impact}",
        "Warm framing, same physics: {impact}",
        "You're not bad; the day had friction—{impact}",
        "Recovery wisdom: {impact}",
        "One treat doesn't erase this truth: {impact}",
        "Self-kindness includes seeing: {impact}",
        "Balance needs this awareness: {impact}",
        "Gentle guardrail: {impact}",
        "Your nervous system and your goal both care about: {impact}",
    ],
    "supportive_accountability": [
        "{impact}",
        "Holding you accountable with care: {impact}",
        "Straight talk: {impact}",
        "Repeating patterns have repeating outcomes: {impact}",
        "I'm on your side—not the excuse's side: {impact}",
        "This is how loops stay loops: {impact}",
        "Love the person; tighten the habit: {impact}",
        "Your goal deserves this honesty: {impact}",
        "We name it so we can change it: {impact}",
        "Data-backed reality: {impact}",
        "Support sounds like naming the pattern: {impact}",
        "Fat-loss roadmap gets clearer when you see: {impact}",
    ],
    "strict_warm": [
        "{impact}",
        "Bottom line: {impact}",
        "Execute knowing: {impact}",
        "Clear-eyed view: {impact}",
        "Correction without drama needs facts: {impact}",
        "One slip, still true: {impact}",
        "Mechanics don't pause for feelings: {impact}",
        "Know this, then move: {impact}",
        "Reality after indulgence: {impact}",
        "No spiral—just this fact: {impact}",
    ],
    "strict_accountability": [
        "{impact}",
        "If this repeats: {impact}",
        "Impact of drift: {impact}",
        "Compounding risk: {impact}",
        "This is what repetition buys you: {impact}",
        "Your deficit can't outrun this habit: {impact}",
        "Timeline math: {impact}",
        "Habit cost, quantified in behavior: {impact}",
        "Stop the bleed by seeing: {impact}",
        "Accountability means staring at: {impact}",
        "Nothing changes if this stays invisible: {impact}",
    ],
    "funny_warm": [
        "{impact}",
        "Real talk buff: {impact}",
        "Debuff explanation: {impact}",
        "Treat lore—still canon: {impact}",
        "Rewind isn't free; here's why: {impact}",
        "Patch explained like you are five: {impact}",
        "Snack chapter footnote: {impact}",
        "Fun detected; physics unchanged: {impact}",
    ],
    "funny_accountability": [
        "{impact}",
        "Patch notes: {impact}",
        "Meta update: {impact}",
        "Repeat quest penalty: {impact}",
        "Achievement: Groundhog Day—why it stings: {impact}",
        "Speedrun banned until you read: {impact}",
        "Bug report: same input, same output—{impact}",
        "Leaderboard of habits—you slipped here: {impact}",
        "Nerf incoming unless you fix: {impact}",
    ],
    "indian_coach_warm": [
        "{impact}",
        "Dekho simple baat: {impact}",
        "Samjho: {impact}",
        "Arre tension nahi, lekin sach yeh hai: {impact}",
        "Mast, par mechanism bhi sun lo: {impact}",
        "Treat ke baad bhi seedhi baat: {impact}",
        "Dost, yeh samajh lo: {impact}",
        "Thoda pyar se, par clear: {impact}",
    ],
    "indian_coach_accountability": [
        "{impact}",
        "Seedhi baat: {impact}",
        "Dhyaan do: {impact}",
        "Dekho bhai, loop wahi rahega agar: {impact}",
        "Pattern ko serious lo: {impact}",
        "Yeh repeat tab tak jab tak: {impact}",
        "Boss, data friendly nahi—honest hai: {impact}",
        "Timeline tight rakhni hai toh yeh samjho: {impact}",
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
        "Habit anchor for today: {one_change}",
        "When in doubt, default to: {one_change}",
        "Make your future week easier by: {one_change}",
        "Gentle but decisive—{one_change}",
        "This protects satiety and your average: {one_change}",
        "Copy-paste this into your evening: {one_change}",
        "Lock one ritual: {one_change}",
        "Your coaching homework: {one_change}",
        "Start the upward trend with: {one_change}",
        "One choice that signals you're serious: {one_change}",
        "Tiny repeat, big trajectory: {one_change}",
    ],
    "strict": [
        "Try this today: {one_change}",
        "Immediate next step: {one_change}",
        "Priority action: {one_change}",
        "Start now: {one_change}",
        "Fix this in your next meal: {one_change}",
        "Execute without debate: {one_change}",
        "Non-optional if you want the trend: {one_change}",
        "Calories follow behavior—so do: {one_change}",
        "Do this before the day runs away: {one_change}",
        "Standards action: {one_change}",
        "Proof over promises: {one_change}",
        "Tighten the weakest link now: {one_change}",
        "Single decisive move: {one_change}",
        "No second helpings of excuses—{one_change}",
        "Timeline protection looks like: {one_change}",
    ],
    "funny": [
        "Cheat code: {one_change}",
        "Boss move: {one_change}",
        "Quick win: {one_change}",
        "Level-up move: {one_change}",
        "Tiny hack, big impact: {one_change}",
        "Main quest action: {one_change}",
        "Equip this strategy: {one_change}",
        "Stack the combo: {one_change}",
        "Unlock the sane macro path: {one_change}",
        "Press A to adult: {one_change}",
        "OP strat (balanced edition): {one_change}",
        "Speedrun to stability: {one_change}",
        "Equip protein shield—{one_change}",
        "Daily quest objective: {one_change}",
        "Patch your build: {one_change}",
        "Collectible: discipline—route: {one_change}",
    ],
    "indian_coach": [
        "Chalo, next meal fix: {one_change}",
        "Bas itna kar: {one_change}",
        "Boss move: {one_change}",
        "Aaj ka direct action: {one_change}",
        "Seedha next step: {one_change}",
        "Simple fix abhi: {one_change}",
        "Practical rule aaj ke liye: {one_change}",
        "Zada socho mat, yeh execute karo: {one_change}",
        "Pakka plan—{one_change}",
        "Fat loss friendly move: {one_change}",
        "Habit tight karni hai toh: {one_change}",
        "Dekho, easiest win yeh hai: {one_change}",
        "Next meal ko sorted karo: {one_change}",
        "Aaj commitment dikhane ka tareeka: {one_change}",
        "Seedhi discipline yeh hai: {one_change}",
    ],
    "supportive_warm_action": [
        "{one_change}",
        "Next meal, keep it simple: {one_change}",
        "You've got this—{one_change}",
        "Easy win: {one_change}",
        "Soft landing recipe: {one_change}",
        "Come back gently with: {one_change}",
        "No punishment, just: {one_change}",
        "Rebuild trust with your plan via: {one_change}",
        "Nourish without spiraling—{one_change}",
        "One calm corrective: {one_change}",
        "Bounce-back move: {one_change}",
        "Close the day kindly with: {one_change}",
    ],
    "supportive_accountability_action": [
        "{one_change}",
        "We need this locked in: {one_change}",
        "Non-negotiable next step: {one_change}",
        "Plan it like this: {one_change}",
        "Structure beats cravings—start with: {one_change}",
        "Write it down, then do: {one_change}",
        "Break the loop concretely: {one_change}",
        "Your week turns when you commit to: {one_change}",
        "Protective habit to install: {one_change}",
        "Repeat until boring, then repeat: {one_change}",
        "Accountability looks like executing: {one_change}",
        "Two-meal contract: {one_change}",
    ],
    "strict_warm_action": [
        "{one_change}",
        "Next meal—execute: {one_change}",
        "Recovery move: {one_change}",
        "Clean correction: {one_change}",
        "Stop the bleed: {one_change}",
        "Tighten now; relax later: {one_change}",
        "One disciplined plate: {one_change}",
        "Reset calories with: {one_change}",
    ],
    "strict_accountability_action": [
        "{one_change}",
        "48-hour plan: {one_change}",
        "Baseline step: {one_change}",
        "Hard reset protocol: {one_change}",
        "Do this before anything else: {one_change}",
        "Pattern interrupt command: {one_change}",
        "Minimum viable discipline: {one_change}",
        "Non-negotiable baseline: {one_change}",
    ],
    "funny_warm_action": [
        "{one_change}",
        "Respawn move: {one_change}",
        "Next checkpoint: {one_change}",
        "Debuff cleanse: {one_change}",
        "Re-spec breakfast/dinner: {one_change}",
        "Loot responsibly next: {one_change}",
        "Press restart without rage-quitting: {one_change}",
    ],
    "funny_accountability_action": [
        "{one_change}",
        "Hotfix: {one_change}",
        "Required patch: {one_change}",
        "Mandatory update: {one_change}",
        "Critical bugfix: {one_change}",
        "Server maintenance (you): {one_change}",
        "Nerf snack meta via: {one_change}",
    ],
    "indian_coach_warm_action": [
        "{one_change}",
        "Bas ab ye karo: {one_change}",
        "Next meal fix: {one_change}",
        "Abhi simple execution: {one_change}",
        "Thoda sa tight, bahut zyada calm: {one_change}",
        "Balance wala move: {one_change}",
        "Chalo undo nahi, adjust—{one_change}",
    ],
    "indian_coach_accountability_action": [
        "{one_change}",
        "Ab ye pakka karo: {one_change}",
        "Priority step: {one_change}",
        "Pakka commitment: {one_change}",
        "Ab rules follow karne hain: {one_change}",
        "Structure ab non-optional: {one_change}",
        "Yehi week badalne wala step: {one_change}",
    ],
}

_COACH_INSPIRATION_STYLE_BANK = {
    "supportive": [
        "Progress is built one honest meal at a time. You are doing that now.",
        "You don't need perfection today; you need consistency in the next step.",
        "Every corrected meal is a vote for your future self.",
        "Fat loss is mostly habit math—your next choice keeps the math kind.",
        "Understanding your own patterns is the quiet superpower here.",
        "Small repeats beat heroic once-in-a-while efforts.",
        "Your week is a mosaic; one tile still matters.",
        "Gentle pacing still moves the graph in the right direction.",
        "Self-trust grows when you follow through once, then again.",
        "You're learning what triggers hunger and what satisfies it—that's coaching gold.",
        "Coherence beats intensity for lasting change.",
        "Steady is not boring; steady is how goals survive real life.",
    ],
    "strict": [
        "Discipline is a skill, not a mood; train it in this next meal.",
        "Standards create outcomes. Hold the standard now.",
        "Execution beats intention. Prove it with this next action.",
        "Your timeline listens to your habits more than your intentions.",
        "Choose the harder helpful move once; it pays rent all week.",
        "Adherence is the product; everything else is marketing.",
        "Calm rigidity beats chaotic motivation.",
        "Protect the deficit by protecting structure.",
        "One decisive execution closes ten open loops in your head.",
        "The mirror and the scale both follow behavior, not wishes.",
        "Don't negotiate with the plan at the moment of hunger—pre-decide.",
        "Win the next hour and the day follows.",
    ],
    "funny": [
        "Main-character move: recover fast and keep the streak alive.",
        "You dropped one level, not the whole game. Respawn smart.",
        "Tiny correction now, big boss win later.",
        "NPC energy is skipping protein; main-character energy is logging it.",
        "Your macro quest line continues—don't abandon it over one cutscene.",
        "Lag is temporary; clean meals are the FPS boost.",
        "Keep the season pass to consistency rolling.",
        "Boss loot is discipline; grind responsibly.",
        "Save file intact if the next plate is intentional.",
        "You can't speedrun fat loss, but you can speedrun a smart breakfast.",
        "Tutorial tip: hunger is a skill tree; feed it wisely.",
        "Patch notes say: one good meal fixes the vibe meter.",
    ],
    "indian_coach": [
        "Bhagavad Gita style: karm par focus rakho, fal par tension kam.",
        "Gita yaad rakho: action tumhare haath mein hai, outcome follow karega.",
        "Aaj ka karm clear rakho; kal ka result strong hoga.",
        "Niyat sahi + roz ka chhota karm = sustainable fat loss.",
        "Dhairya rakho—body ko samajhna time leta hai, consistency se response aata hai.",
        "Jo aadat repeat hoti hai, wahi result repeat hota hai—simple equation.",
        "Control jo hai woh abhi ka meal hai; usi pe focus karo.",
        "Discipline ego ka fight nahi, future self ka favour hai.",
        "Scene tough ho to bhi agla step simple rakho.",
        "Energy aur focus dono protein-fiber rhythm se stable hote hain.",
        "Fat loss mein guru mantra: chhoti cheezein daily, bada drama nahi.",
        "Karm = aaj ka plate; phal = weeks ka trend—dono alag cheez hai.",
    ],
    "supportive_warm": [
        "One off-plan moment does not define you; your next decision does.",
        "You are not behind, you are adjusting. That's real progress.",
        "Treat happened, journey continues. Next meal is your reset.",
        "Compassion plus clarity moves you faster than shame ever could.",
        "Your habits are still yours; one bite didn't steal them.",
        "Warm nights happen; calm mornings still do too.",
        "Return to baseline without drama—that's advanced skill.",
        "You can enjoy food and still steer the weekly average.",
        "Forgive the slip, fund the comeback meal with intention.",
        "The kindest coaches still tell the truth; you're ready to hear it gently.",
        "Hunger is human; structure is how you meet it kindly.",
        "You're learning boundary, not punishment—that's growth.",
    ],
    "supportive_accountability": [
        "Respect yourself enough to break this loop today.",
        "Habits change when standards are repeated, especially on hard days.",
        "Your goal deserves structure, not random decisions.",
        "Patterns repeat until the environment changes—design yours on purpose.",
        "The story you tell about food should match the life you want.",
        "Accountability is love with edges; edges keep you honest.",
        "Fat loss respects systems more than mood spikes.",
        "When the same trigger fires daily, change the response once.",
        "You're not broken; the habit pathway is just well-worn—lay new tracks.",
        "Your scans are a mirror; adjust the routine, not your worth.",
        "Strong weeks include boring repetitions of good basics.",
        "Choose identity-level consistency: 'I'm someone who plans.'",
    ],
    "strict_warm": [
        "No guilt, no excuses—just a clean correction now.",
        "One slip is noise. Response is the signal.",
        "Reset immediately and momentum returns.",
        "The fastest recovery is a boring, high-protein plate.",
        "Discipline after indulgence is self-respect, not punishment.",
        "Close the loop so your brain stops rumination.",
        "Tight next meal protects blood sugar drama and regret loops.",
        "You ate it; now earn the calm of being back on plan.",
        "Correct hard once instead of negotiating soft for days.",
        "Your future self pays for stacked slips—pay now, cheaply.",
    ],
    "strict_accountability": [
        "This is where commitment is proven, not promised.",
        "Protect the timeline by protecting your next two meals.",
        "Pattern broken today becomes progress tomorrow.",
        "Serious goals need non-optional guardrails—install them now.",
        "Repetition is expensive; pay the discipline bill early.",
        "You can't out-train, out-walk, or out-hope a recurring calorie pattern.",
        "Structure now prevents another regret week.",
        "Your word to yourself should weigh more than a craving.",
        "Interrupt the autopilot with a written plan—that's leverage.",
        "Decide once, repeat mechanically; that's how loops die.",
    ],
    "funny_warm": [
        "Treat tax paid. Now collect your consistency refund.",
        "Patch applied: back to hero mode next meal.",
        "You are one smart plate away from a comeback arc.",
        "Snack villain appeared; protein hero time.",
        "Save corruption avoided—you still control dinner.",
        "Debuff wore off; stack a veggie buff.",
        "Rewind isn't free, but salad is cheaper than regret.",
        "You grabbed epic loot; now balance the inventory.",
        "Plot armor recharges with water, protein, and sleep.",
        "Side quest complete; resume main storyline: habits.",
    ],
    "funny_accountability": [
        "Lore update: discipline arc unlocked, snack arc cancelled.",
        "Patch notes v2: fewer junk pulls, more wins.",
        "Daily boss rule: plan beats cravings.",
        "Meta shift: stop speedrunning the pantry.",
        "Achievement hunting is cool; hunting chips daily is not.",
        "Your build sheet says 'human', not 'vending machine'.",
        "Seasonal event 'Stress Eating' needs a nerf—patch today.",
        "Leaderboards lie; your log doesn't—listen to it.",
        "Hard mode is just two planned meals—unlock it.",
        "RNG won't save a streak of same inputs—change the inputs.",
    ],
    "indian_coach_warm": [
        "Arjun style focus: agla step sahi, baaki sab set ho jayega.",
        "Gita wali clarity: aaj ka karm strong rakho, kal ka phal better hoga.",
        "No tension—seedha next action pe dhyan do.",
        "Treat ho gaya toh guilt ka scene band—ab smart karm shuru.",
        "Thoda zyada khaya = data point, drama nahin.",
        "Next meal se scene control mein lao—simple.",
        "Mann aur pet dono ko respect do—balance se dono khush.",
        "Jo beet gaya so beet gaya; ab jo karna hai woh karo.",
        "Dost, comeback strong Indians karte hain—ab tumhari baari.",
        "Calm rakho, plate set karo, age badho.",
    ],
    "indian_coach_accountability": [
        "Bhai, Gita ka seedha lesson: action repeat karo, result repeat hoga.",
        "Discipline ko daily karm banao; tabhi timeline bachegi.",
        "Scene tab badlega jab habit badlegi—ab se.",
        "Comfort zone mein fat loss nahi milti—thoda structured rehna padega.",
        "Jo pattern baar baar dikhe, wahi system change maangta hai.",
        "Willpower kabhi kabhi; systems har din—choose systems.",
        "Data se argue mat karo—use karo, phir adjust karo.",
        "Thodi strictness ab = zyada freedom baad mein.",
        "Goal serious ho toh routine bhi serious honi chahiye.",
        "Har roz ka chhota karm bada faayda laata hai—promise.",
    ],
}

_COACH_TONE_REWRITE_SYSTEM_PROMPT = (
    "You are a coaching tone rewriter. "
    "Rewrite coaching content into the requested tone while preserving factual meaning and numbers. "
    "Use natural, varied language—change wording so it sounds like a real person in that tone. "
    "For indian_coach: use natural Hinglish (mix of Hindi and English as people actually speak), not just 2–3 canned words; vary phrases (bhai, dost, chalo, sahi hai, theek hai, dekho, pakka, mast, etc.). "
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
    "You are a real human coach who has seen this user's meals and stats. "
    "The user message includes COACH_TONE_RULES—follow that tone closely so supportive vs strict vs funny vs indian_coach feel obviously different. "
    "If RELATIONSHIP_STANCE=warm_reset: sound human—it's okay they enjoyed something off-plan; normalize, no guilt; one concrete next move from their numbers; reassure they can get back on track. "
    "If RELATIONSHIP_STANCE=accountability: pattern is repeating; be direct and caring-firm, insist on a simple plan, mention their goal timeline slips if this keeps up (no exact weight promises). "
    "Talk in natural, varied language—change your wording every time. Reference their actual scans, gaps, and patterns like a coach would. "
    "Avoid generic AI filler (e.g. 'leverage', 'optimize your journey', 'holistic wellness') unless the tone is playful and it fits. "
    "Output strict JSON only, no markdown, no extra keys. "
    "Never provide medical diagnosis, treatment, or disease claims. Never guarantee body-weight outcomes. "
    "empathy_line: warm for supportive/funny/indian_coach; for strict tone use brief, matter-of-fact acknowledgment (not mushy). Include motivational direction, not generic filler. Avoid all-caps emphasis and shouting words."
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
        "Voice: Talk like a real human coach who has seen their meals and stats. Use different words each time; reference their actual data (scans, gaps, timing) naturally. Do not sound like a template.\n"
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


def get_user_tone_for_push(user_id: str) -> str:
    """Return coach tone preference for push notifications. Uses in-memory profile cache (set when user hits coach/voice or daily coach)."""
    profile = _get_cached_user_coach_profile(user_id)
    tone = str(profile.get("tone_preference") or "supportive").strip().lower()
    return _normalize_tone_preference(tone)


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
    for step in range(min(len(bank), 10)):
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
    weekly_predictive: Optional[Dict[str, Any]] = None,
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
    try:
        fs_coach = int(_safe_float(out.get("fat_loss_score"), -1))
        if fs_coach < 0 and isinstance(norm_payload, dict) and norm_payload.get("goals"):
            fs_coach = int(coach_logic.compute_fat_loss_score(norm_payload))
    except Exception:
        fs_coach = -1
    stance = _compute_coach_relationship_stance(
        norm_payload if isinstance(norm_payload, dict) else {},
        weekly_predictive=weekly_predictive,
        fat_loss_score=fs_coach if fs_coach >= 0 else None,
    )
    sk_sum, sk_why, sk_act = _effective_coach_style_keys(tone, stance)

    classifier = _classify_coach_bottleneck(norm_payload if isinstance(norm_payload, dict) else {})
    classifier = _stance_tune_classifier(classifier, stance, norm_payload if isinstance(norm_payload, dict) else {})
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
        _COACH_SUMMARY_STYLE_BANK.get(sk_sum, _COACH_SUMMARY_STYLE_BANK["supportive"]),
        f"{seed}:summary:{sk_sum}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        summary_fact,
        max_words=36,
    )
    why_line = _pick_style_line(
        _COACH_WHY_STYLE_BANK.get(sk_why, _COACH_WHY_STYLE_BANK["supportive"]),
        f"{seed}:why:{sk_why}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        impact,
        max_words=34,
    )
    one_action_line = _pick_style_line(
        _COACH_ACTION_STYLE_BANK.get(sk_act, _COACH_ACTION_STYLE_BANK["supportive"]),
        f"{seed}:action:{sk_act}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        one_change,
        max_words=28,
    )
    motivation_line = _pick_style_line(
        _COACH_INSPIRATION_STYLE_BANK.get(sk_sum, _COACH_INSPIRATION_STYLE_BANK.get(tone, _COACH_INSPIRATION_STYLE_BANK["supportive"])),
        f"{seed}:motivation:{sk_sum}:{bottleneck_label}",
        fmt,
        recent_for_pick,
        "Consistency compounds.",
        max_words=22,
    )
    if prev_summary and _is_repetitive_line(summary_line, [prev_summary], threshold=0.86):
        summary_line = _pick_style_line(
            _COACH_SUMMARY_STYLE_BANK.get(sk_sum, _COACH_SUMMARY_STYLE_BANK["supportive"]),
            f"{seed}:summary:reroll:{sk_sum}:{bottleneck_label}",
            fmt,
            [prev_summary],
            summary_fact,
            max_words=36,
        )
    if prev_one_thing and _is_repetitive_line(one_action_line, [prev_one_thing], threshold=0.86):
        one_action_line = _pick_style_line(
            _COACH_ACTION_STYLE_BANK.get(sk_act, _COACH_ACTION_STYLE_BANK["supportive"]),
            f"{seed}:action:reroll:{sk_act}:{bottleneck_label}",
            fmt,
            [prev_one_thing],
            one_change,
            max_words=28,
        )

    out["one_sentence_summary"] = summary_line
    out["if_you_do_one_thing"] = one_action_line

    out["coach_summary"] = out["one_sentence_summary"]
    out["why_it_matters"] = _clip_line(f"{why_line} {motivation_line}".strip(), max_words=48)
    out["one_action"] = out["if_you_do_one_thing"]
    out["coach_motivation_line"] = motivation_line
    out["variation_seed"] = seed
    out["coach_relationship_stance"] = stance
    out["summary_signature"] = hashlib.sha256(
        f"{str(out.get('coach_summary') or '')}|{seed}|{tone}|{stance}".encode("utf-8")
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


def _projection_trend_from_predictive(predictive: Optional[Dict[str, Any]]) -> str:
    """Derive improving | stable | declining for 7-day projection phrasing variety."""
    if not predictive or not isinstance(predictive, dict):
        return "stable"
    score = float(_safe_float(predictive.get("projection_7d_score"), 50.0) or 50.0)
    velocity = float(_safe_float(predictive.get("fat_loss_velocity_score"), 0.0) or 0.0)
    protein = float(_safe_float(predictive.get("protein_consistency"), 0.0) or 0.0)
    if score >= 58 or velocity > 5 or protein >= 70:
        return "improving"
    if score <= 42 or velocity < -5 or protein <= 40:
        return "declining"
    return "stable"


def _compute_coach_relationship_stance(
    norm_payload: Dict[str, Any],
    *,
    weekly_predictive: Optional[Dict[str, Any]] = None,
    fat_loss_score: Optional[int] = None,
) -> str:
    """
    Layer coaching voice: warm_reset (one-off slip), accountability (repeated pattern), or steady.
    """
    goals = (norm_payload.get("goals") or {}) if isinstance(norm_payload.get("goals"), dict) else {}
    consumed = (norm_payload.get("consumed") or {}) if isinstance(norm_payload.get("consumed"), dict) else {}
    signals = (norm_payload.get("signals") or {}) if isinstance(norm_payload.get("signals"), dict) else {}

    gk = float(_safe_float(goals.get("kcal"), 1.0)) or 1.0
    ck = float(_safe_float(consumed.get("kcal"), 0.0))
    kcal_over_pct = ((ck - gk) / gk) * 100.0 if gk > 0 else 0.0
    upf_day = float(_safe_float(signals.get("ultra_processed_avg"), 0.0))
    sat = float(_safe_float(signals.get("avg_satiety"), 0.0))
    gl = float(_safe_float(signals.get("avg_glycemic_load"), 0.0))

    score = int(_safe_float(fat_loss_score, -1)) if fat_loss_score is not None else -1

    pred = weekly_predictive if isinstance(weekly_predictive, dict) else {}
    upf_week = float(_safe_float(pred.get("upf_avg"), 0.0))
    days_tr = int(_safe_float(pred.get("days_tracked"), 0) or 0)
    diet_vol = float(_safe_float(pred.get("diet_volatility_index"), 0.0))
    protein_cons = float(_safe_float(pred.get("protein_consistency"), 50.0))
    vel = float(_safe_float(pred.get("fat_loss_velocity_score"), 50.0))
    eb = pred.get("energy_balance_trend_7d") if isinstance(pred.get("energy_balance_trend_7d"), dict) else {}
    energy_trend = str(eb.get("trend") or "").strip().lower()

    acc = 0
    if days_tr >= 3 and upf_week >= 5.9:
        acc += 2
    if days_tr >= 4 and upf_week >= 6.2:
        acc += 1
    if diet_vol >= 56 and upf_day >= 5.4:
        acc += 1
    if 0 < protein_cons < 44 and days_tr >= 3 and upf_week >= 5.6:
        acc += 1
    if days_tr >= 3 and "surplus" in energy_trend:
        acc += 1
    if days_tr >= 4 and vel < 40 and upf_week >= 5.5:
        acc += 1
    if upf_day >= 6.8 and kcal_over_pct > 4:
        acc += 1

    slip_today = kcal_over_pct > 5.5 or upf_day >= 5.8 or gl >= 22.5 or (sat > 0 and sat < 52 and upf_day >= 5.1)
    soft_day = score < 0 or score < 63

    if acc >= 3:
        return "accountability"
    if slip_today and soft_day and acc <= 1:
        return "warm_reset"
    return "steady"


def _stance_tune_classifier(
    classifier: Dict[str, str],
    stance: str,
    norm_payload: Dict[str, Any],
) -> Dict[str, str]:
    out = dict(classifier or {})
    goals = (norm_payload.get("goals") or {}) if isinstance(norm_payload.get("goals"), dict) else {}
    consumed = (norm_payload.get("consumed") or {}) if isinstance(norm_payload.get("consumed"), dict) else {}
    gk = float(_safe_float(goals.get("kcal"), 1.0)) or 1.0
    ck = float(_safe_float(consumed.get("kcal"), 0.0))
    kcal_over = max(0.0, ck - gk)
    kcal_over_pct = (kcal_over / gk) * 100.0 if gk > 0 else 0.0

    if stance == "warm_reset":
        out["impact"] = (
            "One richer or treat-style choice doesn't erase your week—what you do for the next meal is what steadies hunger and calories."
        )
        if kcal_over_pct > 4:
            out["one_change"] = (
                f"Tonight bias your plate to protein + vegetables and trim refined carbs a bit—you're roughly {int(round(kcal_over))} kcal over target."
            )
        else:
            out["one_change"] = (
                "Next meal: protein and vegetables first, keep starches smaller so today lands softly without punishing yourself."
            )
        base_s = str(out.get("summary") or "").strip()
        out["summary"] = (f"You're slightly off track today—that's normal. {base_s}" if base_s else out.get("summary", "")).strip()
    elif stance == "accountability":
        out["impact"] = (
            "Your scans show this is becoming a habit—not a random craving—so we need a clearer plan or your fat-loss timeline keeps stretching."
        )
        out["one_change"] = (
            "Pre-plan your next two meals around whole foods and cap ultra-processed snacks; walk me through it by logging those meals."
        )
        base_s = str(out.get("summary") or "").strip()
        out["summary"] = (
            (f"Pattern alert: processed calories are trending high across multiple days. {base_s}" if base_s else base_s)
        ).strip()
    return out


def _effective_coach_style_keys(tone: str, stance: str) -> Tuple[str, str, str]:
    t = _normalize_daily_tone_id(tone)
    if stance == "steady":
        return t, t, t
    if stance == "warm_reset":
        if t == "supportive":
            return "supportive_warm", "supportive_warm", "supportive_warm_action"
        if t == "strict":
            return "strict_warm", "strict_warm", "strict_warm_action"
        if t == "funny":
            return "funny_warm", "funny_warm", "funny_warm_action"
        if t == "indian_coach":
            return "indian_coach_warm", "indian_coach_warm", "indian_coach_warm_action"
    if stance == "accountability":
        if t == "supportive":
            return "supportive_accountability", "supportive_accountability", "supportive_accountability_action"
        if t == "strict":
            return "strict_accountability", "strict_accountability", "strict_accountability_action"
        if t == "funny":
            return "funny_accountability", "funny_accountability", "funny_accountability_action"
        if t == "indian_coach":
            return "indian_coach_accountability", "indian_coach_accountability", "indian_coach_accountability_action"
    return t, t, t


def _normalize_health_context(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    signals = src.get("signals") if isinstance(src.get("signals"), dict) else {}
    out = {
        "source": str(src.get("source") or "").strip().lower(),
        "signals": {
            "steps_avg_7d": _safe_float(signals.get("steps_avg_7d"), 0.0),
            "steps_yesterday": _safe_float(signals.get("steps_yesterday"), 0.0),
            "sleep_hours_avg_7d": _safe_float(signals.get("sleep_hours_avg_7d"), 0.0),
            "sleep_last_night_hours": _safe_float(signals.get("sleep_last_night_hours"), 0.0),
            "resting_hr_avg_7d": _safe_float(signals.get("resting_hr_avg_7d"), 0.0),
            "hrv_ms_avg_7d": _safe_float(signals.get("hrv_ms_avg_7d"), 0.0),
            "weight_kg_latest": _safe_float(signals.get("weight_kg_latest"), 0.0),
        },
    }
    return out


def _build_health_parameter_advice(health_context: Dict[str, Any]) -> Dict[str, Any]:
    hc = _normalize_health_context(health_context)
    s = hc.get("signals") if isinstance(hc.get("signals"), dict) else {}
    steps = float(_safe_float(s.get("steps_avg_7d"), 0.0))
    steps_yday = float(_safe_float(s.get("steps_yesterday"), 0.0))
    sleep_h = float(_safe_float(s.get("sleep_hours_avg_7d"), 0.0))
    sleep_last = float(_safe_float(s.get("sleep_last_night_hours"), 0.0))
    rhr = float(_safe_float(s.get("resting_hr_avg_7d"), 0.0))
    hrv = float(_safe_float(s.get("hrv_ms_avg_7d"), 0.0))

    weak: List[Dict[str, Any]] = []
    if steps > 0 and steps < 7000:
        weak.append(
            {
                "parameter": "activity_steps",
                "severity": "high" if steps < 5000 else "moderate",
                "value": round(steps, 0),
                "target": "7000-9000 avg steps/day",
                "suggestion": "Add two 12-minute brisk walks after meals and one 8-minute walk after dinner.",
            }
        )
    if sleep_h > 0 and sleep_h < 7.0:
        weak.append(
            {
                "parameter": "sleep_duration",
                "severity": "high" if sleep_h < 6.0 else "moderate",
                "value": round(sleep_h, 1),
                "target": "7.0-8.0 hours/night",
                "suggestion": "Set a fixed wind-down alarm and protect a 60-minute no-screen pre-sleep routine.",
            }
        )
    if rhr > 0 and rhr > 72:
        weak.append(
            {
                "parameter": "resting_heart_rate",
                "severity": "high" if rhr >= 78 else "moderate",
                "value": round(rhr, 0),
                "target": "downward trend over 2-4 weeks",
                "suggestion": "Prioritize sleep consistency, hydration, and lower late-night heavy meals this week.",
            }
        )
    if hrv > 0 and hrv < 35:
        weak.append(
            {
                "parameter": "hrv_recovery",
                "severity": "high" if hrv < 28 else "moderate",
                "value": round(hrv, 1),
                "target": "upward trend over 2-4 weeks",
                "suggestion": "Use one lighter recovery day, breathing work for 10 minutes, and regular sleep timing.",
            }
        )

    weak_sorted = sorted(
        weak,
        key=lambda x: (0 if str(x.get("severity")) == "high" else 1, str(x.get("parameter") or "")),
    )
    top = weak_sorted[:2]
    lines = [str(item.get("suggestion") or "").strip() for item in top if str(item.get("suggestion") or "").strip()]
    summary = (
        f"Health signals from {str(hc.get('source') or 'device')} show "
        + ", ".join([str(item.get("parameter") or "").replace("_", " ") for item in top])
        + " as the main weak spots."
    ) if top else ""
    engaging_line = ""
    if steps_yday > 0 and steps_yday < 7000:
        engaging_line = (
            f"Yesterday you did about {int(round(steps_yday))} steps. Let's hit at least 7000 today—quick post-meal walks will get you there."
        )
    elif sleep_last > 0 and sleep_last < 7.0:
        engaging_line = (
            f"Last night sleep was about {round(sleep_last, 1)}h. Let's push for 7+ hours tonight so hunger and recovery improve tomorrow."
        )
    elif top:
        engaging_line = "You are close—lock one health habit today and your fat-loss trend gets easier to sustain."

    def _bar(value: float, target: float, label: str) -> Dict[str, Any]:
        pct = 0.0
        if target > 0:
            pct = max(0.0, min(1.0, float(value) / float(target)))
        return {"label": label, "value": round(value, 1), "target": target, "pct": round(pct, 3)}

    bars: List[Dict[str, Any]] = []
    if steps > 0:
        bars.append(_bar(steps, 7000.0, "Steps avg (7d)"))
    if sleep_h > 0:
        bars.append(_bar(sleep_h, 7.5, "Sleep hrs avg (7d)"))
    if hrv > 0:
        bars.append(_bar(hrv, 45.0, "HRV avg (ms)"))
    if rhr > 0:
        # For resting HR lower is better; represent inverse progress to <=65.
        inv = max(0.0, 80.0 - rhr)
        bars.append(_bar(inv, 15.0, "Resting HR recovery"))

    return {
        "source": str(hc.get("source") or "unknown"),
        "weak_parameters": weak_sorted,
        "coach_summary": summary,
        "coach_steps": lines[:2],
        "engaging_line": engaging_line,
        "chart_bars": bars[:4],
    }


def _apply_health_advice_to_coach_response(resp: Dict[str, Any], health_context: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(resp or {})
    try:
        advice = _build_health_parameter_advice(health_context)
        weak = advice.get("weak_parameters") if isinstance(advice.get("weak_parameters"), list) else []
        out["health_context_used"] = bool(weak)
        out["health_signal_source"] = str(advice.get("source") or "")
        out["health_parameter_advice"] = advice
        out["health_coach_line"] = str(advice.get("engaging_line") or "")
        out["health_chart_bars"] = advice.get("chart_bars") if isinstance(advice.get("chart_bars"), list) else []
        if weak:
            summary = str(advice.get("coach_summary") or "").strip()
            steps = advice.get("coach_steps") if isinstance(advice.get("coach_steps"), list) else []
            if summary:
                existing = str(out.get("why_it_matters") or out.get("insight_line") or "").strip()
                merged = _clip_line(f"{existing} {summary}".strip(), max_words=60)
                if str(out.get("why_it_matters") or "").strip():
                    out["why_it_matters"] = merged
                elif str(out.get("insight_line") or "").strip():
                    out["insight_line"] = merged[:200]
            if steps and isinstance(out.get("one_action"), dict):
                curr_steps = out["one_action"].get("steps") if isinstance(out["one_action"].get("steps"), list) else []
                out["one_action"]["steps"] = (curr_steps + [str(s) for s in steps])[:3]
            if str(out.get("health_coach_line") or "").strip() and str(out.get("insight_line") or "").strip():
                out["insight_line"] = _limit_text(f"{out.get('insight_line')} {out.get('health_coach_line')}", 200)
    except Exception as e:
        # Fail-open: never break coach response if optional health enrichment fails.
        logger.info("health advice enrichment skipped: %s", str(e)[:200])
    return out


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
    meal_snapshot = str((norm_payload.get("meal_snapshot") or "")).strip()
    scans_7d = int(_safe_float((predictive or {}).get("scans_7d"), 0) or 0)
    protein_gap = float(deltas.get("protein_gap_g") or 0.0)
    kcal_delta = float(deltas.get("kcal_delta") or 0.0)
    if protein_gap > 35 and (consumed.get("protein_g") or 0) == 0:
        coach_mode = "first_meal_or_protein_behind"
    elif protein_gap > 30:
        coach_mode = "protein_behind"
    elif scans_7d < 2:
        coach_mode = "logging_needed"
    elif kcal_delta > 300:
        coach_mode = "calories_tight"
    elif protein_gap < 10 and protein_gap >= 0:
        coach_mode = "protein_ahead"
    else:
        coach_mode = "general"
    compact = {
        "date": norm_payload.get("date"),
        "goals": norm_payload.get("goals"),
        "consumed": norm_payload.get("consumed"),
        "deltas": deltas,
        "meal_snapshot": meal_snapshot,
        "coach_mode": coach_mode,
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
        "projection_trend": _projection_trend_from_predictive(predictive),
    }
    rel_stance = _compute_coach_relationship_stance(
        norm_payload,
        weekly_predictive=weekly_predictive,
        fat_loss_score=int(fat_loss_score),
    )
    compact["relationship_stance"] = rel_stance
    relationship_voice_rules = {
        "warm_reset": (
            "RELATIONSHIP_STANCE=warm_reset. User had a treat or heavier meal—normalize it like a real coach, zero shame, "
            "reassure they can get back on track, then one compensating action from their kcal/carb/protein gaps."
        ),
        "accountability": (
            "RELATIONSHIP_STANCE=accountability. Repeating high ultra-processed / calorie overshoot pattern across days—be direct but respectful, "
            "insist on a written-down plan for the next 48h; mention fat-loss timeline stretches if it continues (no exact kg/lb promises)."
        ),
        "steady": "RELATIONSHIP_STANCE=steady. Coach per tone without exaggerated drama.",
    }.get(rel_stance, "RELATIONSHIP_STANCE=steady.")
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
                "projection_trend": compact.get("projection_trend") or "stable",
            },
            "rule_risk_alerts": rule_alerts[:3],
        }
        mode_line = ""
        if coach_mode == "first_meal_or_protein_behind":
            mode_line = "Focus: They have little or no protein logged yet—suggest anchoring protein at the next meal and mention the gap in grams.\n"
        elif coach_mode == "protein_behind":
            mode_line = "Focus: Mention their current protein gap in grams and one concrete way to close it today.\n"
        elif coach_mode == "logging_needed":
            mode_line = "Focus: They have few scans this week—encourage logging the next meal without sounding pushy.\n"
        elif coach_mode == "calories_tight":
            mode_line = "Focus: They are over calorie target—suggest one practical lever (e.g. portion, timing, or quality) without shaming.\n"
        elif coach_mode == "protein_ahead":
            mode_line = "Focus: Protein is on track—acknowledge that and highlight one other lever (fiber, timing, or quality) if relevant.\n"
        snapshot_line = f"Meal snapshot (use this so you sound like you have seen their scans): {meal_snapshot}\n\n" if meal_snapshot else ""
        return (
            "FAST_MODE: produce concise high-signal coaching from compact metrics only.\n"
            + snapshot_line
            + f"{relationship_voice_rules}\n"
            + mode_line
            + "Voice: Write like a real human coach who has seen this user's meal scans and fat loss stats. "
            "Reference their actual numbers (gaps, scans, timing) in natural language. Use different words and sentence structures—never sound like a template or repeat the same phrases.\n"
            "Rules:\n"
            "- Strict JSON only.\n"
            f"- Tone mode: {tone_pref}. {tone_prompt}\n"
            "- No medical advice, no disease/supplement/treatment claims.\n"
            "- No exact body-weight promises.\n"
            "- Max 2 actions.\n"
            "- one_sentence_summary <= 18 words.\n"
            "- Avoid repeating the same point across sections.\n"
            "- Balance levers: do not default to glycemic; weight protein and fiber gaps equally. Vary if_you_do_one_thing angle (protein vs fiber vs timing) when possible.\n"
            "- projection_7d: Vary wording by projection_trend (improving/stable/declining); start with 'Based on your last 7 days (X days with scans).'\n\n"
            f"Allowed suggestion palette:\n{json.dumps(allowed_palette, ensure_ascii=True)}\n\n"
            f"Compact payload:\n{json.dumps(fast_payload, ensure_ascii=True)}\n\n"
            f"Output JSON shape:\n{json.dumps(template, ensure_ascii=True)}"
        )
    mode_line = ""
    if coach_mode == "first_meal_or_protein_behind":
        mode_line = "Focus: They have little or no protein logged yet—suggest anchoring protein at the next meal and mention the gap in grams.\n"
    elif coach_mode == "protein_behind":
        mode_line = "Focus: Mention their current protein gap in grams and one concrete way to close it today.\n"
    elif coach_mode == "logging_needed":
        mode_line = "Focus: They have few scans this week—encourage logging the next meal without sounding pushy.\n"
    elif coach_mode == "calories_tight":
        mode_line = "Focus: They are over calorie target—suggest one practical lever (e.g. portion, timing, or quality) without shaming.\n"
    elif coach_mode == "protein_ahead":
        mode_line = "Focus: Protein is on track—acknowledge that and highlight one other lever (fiber, timing, or quality) if relevant.\n"
    snapshot_line = f"Meal snapshot (use this so you sound like you have seen their scans): {meal_snapshot}\n\n" if meal_snapshot else ""
    return (
        "Use this daily nutrition summary and produce coaching insight, not a stat report.\n"
        + snapshot_line
        + f"{relationship_voice_rules}\n"
        + mode_line
        + "Voice: You are a real human coach who has seen this user's meal scans, today's totals, protein/fiber gaps, and fat loss stats. "
        "Talk like you understand their data: reference their actual numbers and patterns in natural, varied language. "
        "Use different words and sentence structures every time—do not repeat the same phrases or sound like a script. "
        "Coach the client like a real person would.\n"
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
        "- For projection_7d: Start with 'Based on your last 7 days (X days with scans).' Use projection_trend to vary wording: if improving say something like 'If you keep this week's consistency...'; if declining 'If you tighten up the last few days...'; if stable 'If you hold this pattern...'. Use different wording each time—do not repeat the same sentence.\n"
        "- Keep it practical and behavior-focused.\n"
        "- No medical advice, disease claims, supplements, dosages, or treatment language.\n"
        "- Every action must clearly reference at least one metric keyword from this set: "
        "protein, fiber, glycemic load, ultra-processed, leucine, late calories, kcal, carbs, fat.\n"
        "- Max 3 actions.\n"
        "- Keep language concise.\n- Every response should include: empathy, motivation, directional next-step coaching, and an inspiring tone grounded in their data.\n"
        "- Balance levers: do not default to glycemic load every day. Weight protein gap and fiber gap equally with glycemic/UPF/timing; only make glycemic the primary lever when it is clearly the biggest risk from the data.\n"
        "- Vary the primary lever day to day: e.g. protein one day, fiber another, timing or UPF another. Avoid repeating the same main lever two days in a row unless data strongly demands it.\n"
        "- Vary if_you_do_one_thing and tomorrow_focus: do not repeat the same focus or same phrasing three days in a row. Pick a different angle (protein vs fiber vs timing vs quality) when possible.\n\n"
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
        _fallback_variants = (
            (
                "If this pattern repeats for 7 days, adherence risk will likely stay elevated.",
                "If the highest-ROI change is repeated for 7 days, satiety and score consistency should improve.",
            ),
            (
                "Based on your last 7 days, repeating today's pattern would keep progress slow.",
                "Based on your last 7 days, applying the suggested change consistently would improve your trajectory.",
            ),
            (
                "Holding this pattern through the week would maintain current risk levels.",
                "Shifting to the suggested lever for the rest of the week would support better adherence and outcomes.",
            ),
        )
        _seed = f"{confidence_band}:{biggest_risk.get('title', '')}"
        _idx = sum(ord(c) for c in _seed) % 3
        _pair = _fallback_variants[_idx]
        projection = {"if_unchanged": _pair[0], "if_improved": _pair[1]}

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
    consumed_kcal = float(_safe_float(consumed.get("kcal"), 0.0) or 0.0)
    consumed_protein = float(_safe_float(consumed.get("protein_g"), 0.0) or 0.0)
    goal_protein = float(_safe_float(goals.get("protein_g"), 0.0) or 0.0)
    meal_snapshot = _build_meal_snapshot_for_coach(events, consumed_kcal, consumed_protein, goal_protein)
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
        "meal_snapshot": meal_snapshot,
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
    health_context = payload.get("health_context") if isinstance(payload, dict) and isinstance(payload.get("health_context"), dict) else {}
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
        weekly_predictive=weekly_predictive,
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


def _voice_relationship_stance(metrics: Dict[str, Any]) -> str:
    """Match daily coach: one-off slip vs repeating treat/junk pattern from meal list heuristics."""
    kcal_delta = float(_safe_float((metrics or {}).get("kcal_delta"), 0.0))
    upf_hints = int(_safe_float((metrics or {}).get("upf_hints"), 0) or 0)
    meals_count = int(_safe_float((metrics or {}).get("meals_count"), 0) or 0)
    if meals_count >= 4 and upf_hints >= 3 and kcal_delta > 180:
        return "accountability"
    if meals_count >= 3 and upf_hints >= 2 and kcal_delta > 320:
        return "accountability"
    if kcal_delta > 85 or upf_hints >= 1:
        return "warm_reset"
    return "steady"


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
    v_stance = _voice_relationship_stance(metrics)
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
    if v_stance == "warm_reset":
        empathy = "Hey—you're human; one heavier choice doesn't wreck your week. We'll balance the next meal."
    elif v_stance == "accountability":
        empathy = "I'm with you, but your last few logs show the same treat pattern—we need a tighter plan today."
    if tone_pref == "strict":
        empathy = "Logged. Now execute one correction." if v_stance == "steady" else empathy
    elif tone_pref == "funny":
        empathy = "Nice check-in. Let’s win this next meal." if v_stance == "steady" else empathy
    elif tone_pref == "indian_coach":
        empathy = "Boss, meal logged. Chalo ek strong next step set karte hain." if v_stance == "steady" else empathy

    protein_gap = float(_safe_float(metrics.get("protein_gap"), 0.0) or 0.0)
    fiber_gap = float(_safe_float(metrics.get("fiber_gap"), 0.0) or 0.0)
    late_pct = float(_safe_float(metrics.get("late_calories_pct"), 0.0) or 0.0)
    avg_conf = float(_safe_float(metrics.get("avg_confidence"), 1.0) or 1.0)
    kcal_delta = float(_safe_float(metrics.get("kcal_delta"), 0.0) or 0.0)
    if timeout_mode:
        insight = "I’m still refining details. Use one practical step now while your full coaching updates."
    elif avg_conf < 0.55:
        insight = "This scan likely needs one quick confirmation before precision coaching."
    elif v_stance == "warm_reset" and kcal_delta > 50:
        insight = (
            f"You're roughly {int(round(max(0, kcal_delta)))} kcal over target—bias your next meal to protein + veg and trim refined carbs a bit."
        )
    elif v_stance == "accountability":
        insight = (
            "If this snack-heavy pattern keeps up, your fat-loss timeline stretches—pre-plan the next two meals around whole foods."
        )
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
    v_stance = _voice_relationship_stance(metrics)
    candidate_actions = _voice_action_templates(metrics)
    allowed_keys = [_normalize_semantic_key(a.get("advice_key")) for a in candidate_actions if _normalize_semantic_key(a.get("advice_key"))]
    recent_norm = _normalize_semantic_key_list(recent_keys, limit=24)
    payload = {
        "day": _safe_day_iso(req.day),
        "goals": req.goals,
        "consumed": req.consumed,
        "metrics": metrics,
        "relationship_stance": v_stance,
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
    tone_guidance = _daily_tone_prompt_text(tone_pref)
    stance_note = {
        "warm_reset": "RELATIONSHIP_STANCE=warm_reset (post-treat / off-plan meal). empathy_line: normalize, no shame. insight_line: one compensating move from kcal/protein/fiber gaps.",
        "accountability": "RELATIONSHIP_STANCE=accountability (repeating junk pattern in meal list). empathy_line: brief real talk. insight_line: direct plan + timeline pressure, still respectful.",
        "steady": "RELATIONSHIP_STANCE=steady.",
    }.get(v_stance, "RELATIONSHIP_STANCE=steady.")
    prompt = (
        f"COACH_TONE_ID: {tone_pref}\n"
        f"COACH_TONE_RULES: {tone_guidance}\n"
        f"{stance_note}\n\n"
        "empathy_line and insight_line must clearly match COACH_TONE_ID (voice, rhythm, word choice—not the same style for every tone).\n"
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
        timeout_sec=float(COACH_VOICE_TIMEOUT_SEC),
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
                    "health_context": _normalize_health_context(req.health_context),
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
    output = _apply_health_advice_to_coach_response(output, req.health_context)

    _append_coach_memory_entry(
        uid,
        day_iso,
        output.get("advice_key"),
        f"{output.get('empathy_line', '')} {output.get('insight_line', '')}".strip(),
    )
    _coach_voice_cache_set(uid, day_iso, payload_hash, tone_pref, output)
    return _attach_debug_schema(output, bool(debug))


@app.post("/recipes/suggest")
def recipes_suggest(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(RecipeSuggestRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_recipe_suggest_payload", "raw": str(e)[:300]})
    uid = require_user_id(x_user_id, user_id or req.user_id)
    require_ai_consent(uid)
    spoon_key = (os.getenv("SPOONACULAR_API_KEY") or "").strip()
    out = build_recipe_suggest_response(
        uid,
        req.meal or {},
        str(req.diet_style or "non-veg"),
        str(req.goal_type or "fat_loss"),
        GEMINI_API_KEY,
        _SINGLE_SUPPORTED_GEMINI_MODEL,
        spoon_key,
        str(req.plan or "free"),
    )
    return out


@app.get("/recipes/saved")
def recipes_saved(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    require_ai_consent(uid)
    return list_saved_recipes(uid)


@app.post("/recipes/feedback")
def recipes_feedback(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    try:
        req = _model_validate(RecipeFeedbackRequestModel, payload or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_recipe_feedback_payload", "raw": str(e)[:300]})
    uid = require_user_id(x_user_id, user_id or req.user_id)
    require_ai_consent(uid)
    meta = {
        "cuisine": str(req.cuisine or "").strip(),
        "meal_tag": str(req.meal_tag or "").strip(),
        "recipe_snapshot": req.recipe_snapshot if isinstance(req.recipe_snapshot, dict) else {},
    }
    return record_recipe_feedback(uid, str(req.recipe_key or "").strip(), str(req.action or "").strip(), meta)


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
    def _protein_hit_pct(r: Dict[str, Any]) -> float:
        mj = r.get("metrics_json") if isinstance(r.get("metrics_json"), dict) else {}
        hit = mj.get("hit_pct") if isinstance(mj.get("hit_pct"), dict) else {}
        return float(_safe_float(hit.get("protein"), 0.0) or 0.0)

    protein_days_this_week = sum(1 for r in (rows or []) if _protein_hit_pct(r) >= 99.0)
    win_summary = ""
    if days_logged > 0:
        win_summary = f"{protein_days_this_week}/{days_logged} protein days this week."
    if resilience >= 65 and win_summary:
        win_summary = "Strong week: " + win_summary

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
            "protein_days_this_week": protein_days_this_week,
        },
        "win_summary": win_summary,
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
        "win_summary": str(raw.get("win_summary") or fallback.get("win_summary") or ""),
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


# -------------------- GOAL COACH (Let's Go) --------------------


def _compute_goal_coach_wins_and_streaks(
    user_id: str,
    day_iso: str,
    targets: Dict[str, Any],
    consumed: Dict[str, Any],
    week_metric_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute daily win flags and streaks for Goal Coach / FLI reward surface. Premium, factual tone."""
    target_cal = float(_safe_float(targets.get("calories") or targets.get("target_calories"), 0.0) or 0.0)
    target_protein = float(_safe_float(targets.get("protein_g") or targets.get("target_protein_g"), 0.0) or 0.0)
    consumed_cal = float(_safe_float(consumed.get("calories") or consumed.get("consumed_calories"), 0.0) or 0.0)
    consumed_protein = float(_safe_float(consumed.get("protein_g") or consumed.get("consumed_protein_g"), 0.0) or 0.0)

    protein_hit_today = target_protein > 0 and consumed_protein >= max(1.0, 0.9 * target_protein)
    kcal_in_range_today = False
    if target_cal > 0 and consumed_cal > 0:
        ratio = consumed_cal / target_cal
        kcal_in_range_today = 0.85 <= ratio <= 1.15
    daily_win = {
        "protein_hit": protein_hit_today,
        "kcal_in_range": kcal_in_range_today,
    }
    protein_streak_days = 0
    logging_streak_days = 0
    win_line = ""

    if week_metric_rows and day_iso:
        try:
            dt.date.fromisoformat(day_iso[:10])
        except Exception:
            pass
        else:
            day_list = []
            for r in week_metric_rows or []:
                if not isinstance(r, dict):
                    continue
                d = str((r.get("day") or ""))[:10]
                if not d or d > day_iso:
                    continue
                mj = r.get("metrics_json") if isinstance(r.get("metrics_json"), dict) else {}
                c = mj.get("consumed") if isinstance(mj.get("consumed"), dict) else {}
                g = mj.get("goals") if isinstance(mj.get("goals"), dict) else {}
                tp = float(_safe_float(g.get("protein_g"), 0.0) or 0.0)
                cp = float(_safe_float(c.get("protein_g"), 0.0) or 0.0)
                meals = int(_safe_float((mj.get("signals") or {}).get("meals_count"), 0) or 0)
                ph = tp > 0 and cp >= max(1.0, 0.9 * tp)
                day_list.append((d, ph, meals >= 1))
            if day_iso not in [x[0] for x in day_list]:
                day_list.append((day_iso, protein_hit_today, consumed_cal > 0 or consumed_protein > 0))
            day_list.sort(key=lambda x: x[0], reverse=True)
            for d, ph, logged in day_list:
                if ph:
                    protein_streak_days += 1
                else:
                    break
            for d, ph, logged in day_list:
                if logged:
                    logging_streak_days += 1
                else:
                    break

    if protein_hit_today:
        win_line = "Protein target met."
    elif protein_streak_days >= 2:
        win_line = f"{protein_streak_days}-day protein streak."
    elif logging_streak_days >= 2:
        win_line = f"{logging_streak_days}-day logging streak."
    elif kcal_in_range_today:
        win_line = "Day in range."

    return {
        "daily_win": daily_win,
        "protein_streak_days": protein_streak_days,
        "logging_streak_days": logging_streak_days,
        "win_line": win_line,
    }


@app.post("/goal-coach/plan/create")
def goal_coach_plan_create(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Create a new goal plan and return it with kickoff status."""
    uid = require_user_id(x_user_id, user_id or (payload.get("user_id") if isinstance(payload, dict) else None))
    body = payload if isinstance(payload, dict) else {}
    plan_input = {
        "goal_type": body.get("goal_type", "fat_loss"),
        "goal_preset": body.get("goal_preset"),
        "timeframe_weeks": body.get("timeframe_weeks"),
        "target_date": body.get("target_date"),
        "pace_mode": body.get("pace_mode", "balanced"),
        "training_days_per_week": body.get("training_days_per_week"),
        "diet_preference": body.get("diet_preference"),
        "current_weight": body.get("current_weight"),
        "target_weight": body.get("target_weight"),
    }
    starter = build_starter_plan(plan_input)
    plan_row = create_goal_plan(uid, plan_input, starter)
    kickoff = compute_kickoff_status(plan_row)
    plan_str = get_user_plan(uid)
    sub_required = kickoff.get("requires_subscription", False)
    requires_advanced = sub_required and not plan_at_least(plan_str, "advanced")
    return {
        "ok": True,
        "plan": plan_row,
        "kickoff_day": kickoff.get("kickoff_days_used", 1),
        "kickoff_days_total": kickoff.get("free_kickoff_days", 21),
        "kickoff_active": kickoff.get("in_kickoff", True),
        "subscription_required": sub_required,
        "requires_advanced_plan": requires_advanced,
    }


@app.get("/goal-coach/plan")
def goal_coach_plan_get(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Get active goal plan and kickoff status."""
    uid = require_user_id(x_user_id, user_id)
    plan = get_active_goal_plan(uid)
    if not plan:
        return {"has_plan": False, "plan": None, "kickoff_day": 0, "kickoff_days_total": 21, "kickoff_active": False, "subscription_required": False, "requires_advanced_plan": False}
    kickoff = compute_kickoff_status(plan)
    plan_str = get_user_plan(uid)
    sub_required = kickoff.get("requires_subscription", False)
    requires_advanced = sub_required and not plan_at_least(plan_str, "advanced")
    return {
        "has_plan": True,
        "plan": plan,
        "kickoff_day": kickoff.get("kickoff_days_used", 0),
        "kickoff_days_total": kickoff.get("free_kickoff_days", 21),
        "kickoff_active": kickoff.get("in_kickoff", True),
        "subscription_required": sub_required,
        "requires_advanced_plan": requires_advanced,
    }


@app.get("/goal-coach/daily")
def goal_coach_daily_get(
    user_id: Optional[str] = None,
    day: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    current_hour: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Daily coach state: targets, consumed so far, one best action, coach summary, suggested_actions. Gated after kickoff if no subscription."""
    uid = require_user_id(x_user_id, user_id)
    day_iso = _day_iso(day, tz=tz, tz_offset_min=tz_offset_min)
    plan_row = get_active_goal_plan(uid)
    if not plan_row:
        return {"ok": True, "has_plan": False, "today_targets": None, "consumed_so_far": None, "coach_focus": "", "best_action_today": "", "coach_summary": "", "risk_flags": [], "suggested_actions": {}, "subscription_required": False, "requires_advanced_plan": False, "kickoff_days_total": 21}
    plan = _goal_coach_plan_merged(plan_row)
    kickoff = compute_kickoff_status(plan_row)
    consumed = _get_goal_coach_daily_consumed(uid, day_iso) or {}
    daily_metrics = {"date": day_iso, "day": day_iso, **consumed}
    memory_signals: Dict[str, Any] = {}
    state = build_daily_coach_state(plan, daily_metrics, memory_signals)
    hour_local: Optional[int] = None
    if current_hour is not None and 0 <= current_hour <= 23:
        hour_local = int(current_hour)
    suggested_actions = build_daily_suggested_actions(state, hour_local)
    today_targets = {
        "calories": int(state.get("targets", {}).get("calories", 0) or 0),
        "protein_g": int(state.get("targets", {}).get("protein_g", 0) or 0),
        "carbs_g": int((plan.get("starter_plan") or {}).get("target_carbs_g", 0) or 0),
        "fat_g": int((plan.get("starter_plan") or {}).get("target_fat_g", 0) or 0),
    }
    consumed_so_far = {
        "calories": int(state.get("consumed", {}).get("calories", 0) or 0),
        "protein_g": int(state.get("consumed", {}).get("protein_g", 0) or 0),
    }
    week_start_iso = _week_start_monday(day_iso)
    week_rows: List[Dict[str, Any]] = []
    try:
        week_rows = get_daily_metrics_window(uid, week_start_iso)
    except Exception:
        week_rows = []
    wins_streaks = _compute_goal_coach_wins_and_streaks(
        uid,
        day_iso,
        state.get("targets") or today_targets,
        state.get("consumed") or consumed_so_far,
        week_metric_rows=week_rows,
    )
    plan_str = get_user_plan(uid)
    sub_required = kickoff.get("requires_subscription", False)
    requires_advanced = sub_required and not plan_at_least(plan_str, "advanced")
    return {
        "ok": True,
        "has_plan": True,
        "today_targets": today_targets,
        "consumed_so_far": consumed_so_far,
        "coach_focus": str(state.get("coach_focus", "")),
        "best_action_today": str(state.get("one_action_today", "")),
        "coach_summary": str(state.get("headline", "")),
        "risk_flags": list(state.get("risk_flags", [])),
        "suggested_actions": suggested_actions,
        "subscription_required": sub_required,
        "requires_advanced_plan": requires_advanced,
        "kickoff_active": kickoff.get("in_kickoff", True),
        "kickoff_day": kickoff.get("kickoff_days_used", 0),
        "kickoff_days_total": kickoff.get("free_kickoff_days", 21),
        "daily_win": wins_streaks.get("daily_win"),
        "protein_streak_days": wins_streaks.get("protein_streak_days", 0),
        "logging_streak_days": wins_streaks.get("logging_streak_days", 0),
        "win_line": wins_streaks.get("win_line", ""),
    }


@app.get("/goal-coach/weekly")
def goal_coach_weekly_get(
    user_id: Optional[str] = None,
    week_start: Optional[str] = None,
    day: Optional[str] = None,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Weekly review: adherence, resilience, main win, bottleneck, next week focus. Plan remains visible; gated after kickoff."""
    uid = require_user_id(x_user_id, user_id)
    anchor_day = _day_iso(day, tz=tz, tz_offset_min=tz_offset_min)
    week_start_iso = _week_start_monday(week_start or anchor_day)
    plan_row = get_active_goal_plan(uid)
    if not plan_row:
        return {"ok": True, "has_plan": False, "review": None, "subscription_required": False}
    plan = _goal_coach_plan_merged(plan_row)
    kickoff = compute_kickoff_status(plan_row)
    rows: List[Dict[str, Any]] = []
    try:
        rows = get_daily_metrics_window(uid, week_start_iso)
    except Exception:
        pass
    days = _goal_coach_metrics_rows_to_days(rows)
    review = build_weekly_review(plan, days, None)
    next_step_action = build_weekly_next_step_action(review)
    plan_str = get_user_plan(uid)
    sub_required = kickoff.get("requires_subscription", False)
    requires_advanced = sub_required and not plan_at_least(plan_str, "advanced")
    return {
        "ok": True,
        "has_plan": True,
        "week_start": week_start_iso,
        "week_end": _week_end_from_start(week_start_iso),
        "review": review,
        "next_step_action": next_step_action,
        "subscription_required": sub_required,
        "requires_advanced_plan": requires_advanced,
        "kickoff_active": kickoff.get("in_kickoff", True),
    }


@app.post("/goal-coach/plan/pause")
def goal_coach_plan_pause(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    updated = update_goal_plan_status(uid, "paused")
    return {"ok": True, "plan": updated}


@app.post("/goal-coach/plan/resume")
def goal_coach_plan_resume(
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    updated = update_goal_plan_status(uid, "active")
    return {"ok": True, "plan": updated}


def _goal_coach_require_advanced_if_past_kickoff(uid: str) -> None:
    """Raise 402 if user has active plan, past kickoff, and plan < Advanced (for journey writes)."""
    plan_row = get_active_goal_plan(uid)
    if not plan_row:
        return
    kickoff = compute_kickoff_status(plan_row)
    if not kickoff.get("requires_subscription"):
        return
    plan_str = get_user_plan(uid)
    if plan_at_least(plan_str, "advanced"):
        return
    raise HTTPException(
        status_code=402,
        detail={
            "error": "upgrade_required",
            "feature": "lets_go_journey",
            "required_plan": "advanced",
            "message": "Upgrade to Advanced to continue your Let's Go journey after the 3-week trial.",
        },
    )


@app.post("/goal-coach/weight")
def goal_coach_weight_log(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Log a weight measurement (kg). Body: value_kg, day (optional YYYY-MM-DD)."""
    uid = require_user_id(x_user_id, user_id or (payload.get("user_id") if isinstance(payload, dict) else None))
    _goal_coach_require_advanced_if_past_kickoff(uid)
    body = payload if isinstance(payload, dict) else {}
    value_kg = float(_safe_float(body.get("value_kg"), 0.0) or 0.0)
    if value_kg <= 0:
        raise HTTPException(status_code=422, detail={"error": "value_kg_required"})
    day_iso = (body.get("day") or "").strip() or None
    entry = add_weight_entry(uid, value_kg, day_iso)
    return {"ok": True, "entry": entry}


@app.post("/goal-coach/check-in")
def goal_coach_check_in(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Record a check-in (e.g. after a meal). Body: day (optional), analysis_id (optional), meal (optional)."""
    uid = require_user_id(x_user_id, user_id or (payload.get("user_id") if isinstance(payload, dict) else None))
    _goal_coach_require_advanced_if_past_kickoff(uid)
    body = payload if isinstance(payload, dict) else {}
    entry = add_check_in(
        uid,
        day_iso=(body.get("day") or "").strip() or None,
        analysis_id=(body.get("analysis_id") or "").strip() or None,
        meal_label=(body.get("meal") or body.get("meal_label") or "").strip() or None,
    )
    return {"ok": True, "entry": entry}


@app.post("/goal-coach/photo")
def goal_coach_photo_log(
    payload: Dict[str, Any] = Body(...),
    user_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Log a weekly progress photo. Body: week_start (YYYY-MM-DD Monday), uri_or_ref, note (optional)."""
    uid = require_user_id(x_user_id, user_id or (payload.get("user_id") if isinstance(payload, dict) else None))
    _goal_coach_require_advanced_if_past_kickoff(uid)
    body = payload if isinstance(payload, dict) else {}
    week_start = (body.get("week_start") or "").strip()
    uri_or_ref = (body.get("uri_or_ref") or body.get("uri") or "").strip()
    if not week_start or not uri_or_ref:
        raise HTTPException(status_code=422, detail={"error": "week_start_and_uri_required"})
    entry = add_photo_entry(uid, week_start, uri_or_ref, note=(body.get("note") or "").strip() or None)
    return {"ok": True, "entry": entry}


@app.get("/goal-coach/journey")
def goal_coach_journey_get(
    user_id: Optional[str] = None,
    day: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Journey summary: weight entries, check-ins, photos. Optional day for today's check-ins."""
    uid = require_user_id(x_user_id, user_id)
    summary = get_journey_summary(uid, today_iso=day)
    weights = get_weight_entries(uid, limit=90)
    photos = get_photo_entries(uid, limit=24)
    return {
        "ok": True,
        "summary": summary,
        "weight_entries": weights,
        "photo_entries": photos,
    }


@app.post("/goal-coach/events")
def goal_coach_events(payload: Dict[str, Any] = Body(...)):
    """
    Log Goal Coach funnel events: shown, clicked, destination_opened, action_completed.
    Payload must include event_type and user_id; optional metadata (source_surface, action_type, etc.).
    """
    try:
        saved = log_goal_coach_event(payload if isinstance(payload, dict) else {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return {"ok": True, "event": saved}


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
    health_sig_hash = hashlib.sha256(json.dumps(_normalize_health_context(health_context), sort_keys=True).encode("utf-8")).hexdigest()
    p_hash = hashlib.sha256(f"{p_hash}:health:{health_sig_hash}".encode("utf-8")).hexdigest()
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
            weekly_predictive=weekly_predictive,
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
        out = _apply_health_advice_to_coach_response(out, health_context)
        return _attach_debug_schema(out, bool(debug))

    # IMPORTANT: do not block core experience on LLM.
    # Daily coach always returns deterministic rules immediately.
    # (LLM can be layered later via cached_llm or explicit operator tooling.)
    llm_resp: Optional[Dict[str, Any]] = None
    reasoning_source = "rules"
    llm_reason_code = "RULES_FAST_PATH"
    llm_model_used = ""
    llm_tried_models: List[str] = []
    llm_error_raw = ""

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
                weekly_predictive=weekly_predictive,
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
            final_resp = _apply_health_advice_to_coach_response(final_resp, health_context)
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
        weekly_predictive=weekly_predictive,
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
    final_resp = _apply_health_advice_to_coach_response(final_resp, health_context)
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
        entry: Dict[str, Any] = {
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
        hints_in = it.get("ingredient_hints")
        if isinstance(hints_in, dict):
            entry["ingredient_hints"] = {str(k): str(v).strip() for k, v in hints_in.items() if v is not None and str(v).strip()}
        cleaned_items.append(entry)

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
      "candidate_alternatives": ["chicken thigh", "chicken breast"],
      "ingredient_hints": {}
    }
  ]
}

Ingredient hints (optional): When you can clearly see ingredients that affect nutrition, add "ingredient_hints" to that item with keys/values below. Only include what is visible; omit the key if unsure. Use these exact values:
- Coffee/tea/latte/chai: milk_type = None|Whole|Low-fat|Skim|Almond|Oat|Soy|Coconut; sweetener = None|Sugar|Artificial|Honey|Other
- Smoothie/shake: milk_base = Dairy|Almond|Oat|Soy|None / water; sweetener = None|Sugar|Honey|Syrup|Other
- Salad: dressing = None|Light|Normal|Heavy
- Sandwich/wrap/burger/bagel/toast: spread = None|Butter|Mayo|Both|Other
- Yogurt/parfait: toppings = None|Honey|Jam|Granola|Fruit only|Other
- Oatmeal/porridge: milk_type = Water|Whole|Skim|Almond|Oat|Soy; sweetener = None|Sugar|Honey|Maple|Other
If you cannot tell from the image, use empty object {} or omit ingredient_hints.

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


def _menu_scan_ocr_from_image(
    image_bytes: bytes,
    *,
    request_id: str = "",
    job_id: str = "",
) -> Dict[str, Any]:
    """
    Best-effort OCR extraction for menu photos.
    Fails open with low-confidence empty output so menu scan can degrade gracefully.
    """
    if not GEMINI_API_KEY:
        return {"raw_text": "", "menu_lines": [], "ocr_confidence": 0.0}

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return {"raw_text": "", "menu_lines": [], "ocr_confidence": 0.0}

    prompt = """
You are an OCR + parser assistant for restaurant menus.
Return ONLY valid JSON:
{
  "raw_text": "full OCR text",
  "menu_lines": ["line1", "line2"],
  "ocr_confidence": 0.0
}

Rules:
- Extract likely menu item lines only where possible.
- Keep lines short and readable.
- Exclude obvious headers, prices-only lines, and decorative text when possible.
- ocr_confidence must be 0..1.
""".strip()

    try:
        text = _generate_scan_content(
            [prompt, img],
            purpose="menu_scan_ocr",
            request_id=request_id,
            job_id=job_id,
        )
    except Exception as e:
        logger.warning("menu_scan_ocr failed request_id=%s err=%s", request_id, str(e)[:220])
        return {"raw_text": "", "menu_lines": [], "ocr_confidence": 0.0}

    parsed = coach_logic.extract_json_object(text)
    if isinstance(parsed, dict):
        raw_text = str(parsed.get("raw_text") or "").strip()
        raw_lines = parsed.get("menu_lines")
        menu_lines: List[str] = []
        if isinstance(raw_lines, list):
            menu_lines = [str(x or "").strip() for x in raw_lines if str(x or "").strip()][:50]
        if not raw_text and menu_lines:
            raw_text = "\n".join(menu_lines)
        conf = _clamp01(parsed.get("ocr_confidence"), 0.58)
        return {
            "raw_text": raw_text,
            "menu_lines": menu_lines,
            "ocr_confidence": conf,
        }

    # Fallback: treat raw text response as OCR text.
    plain = str(text or "").strip()
    if not plain:
        return {"raw_text": "", "menu_lines": [], "ocr_confidence": 0.0}
    lines = [str(x or "").strip() for x in plain.splitlines() if str(x or "").strip()][:50]
    return {
        "raw_text": plain,
        "menu_lines": lines,
        "ocr_confidence": 0.45,
    }


def _resolve_nutrition_usda(name: str) -> Dict[str, Any]:
    """Resolve nutrition via USDA API. Raises if no usable match. Used as resolver for cache."""
    candidates = usda_search_candidates(name)
    last_item_err = None
    for cand in (candidates or [])[:6]:
        try:
            fdc_id = int(cand["fdcId"])
            details = usda_food_details(fdc_id)
            macros100 = extract_macros_per_100g(details)
            micros100 = extract_micros_per_100g(details)
            return {
                "macros100": macros100,
                "micros100": micros100,
                "fdc_id": fdc_id,
                "description": (details or {}).get("description"),
                "dataType": (details or {}).get("dataType"),
                "source": "usda",
                "resolved_name": (details or {}).get("description", name),
            }
        except Exception as e:
            last_item_err = str(getattr(e, "detail", e))
            continue
    raise HTTPException(
        status_code=502,
        detail={"error": "nutrition_lookup_failed", "message": (last_item_err or "No usable USDA match")[:220]},
    )


def _scan_nutrition_one_item(idx: int, d: Any) -> Dict[str, Any]:
    """Resolve one vision item to a nutrition row. Safe to run concurrently (cache layers use locks)."""
    if not isinstance(d, dict):
        return {"kind": "skip"}
    name = str((d or {}).get("name") or "").strip()
    if not name:
        return {"kind": "skip"}
    grams = max(0.0, float(_safe_float((d or {}).get("grams"), 0.0) or 0.0))
    if grams <= 0:
        return {"kind": "skip"}
    conf = _clamp01((d or {}).get("confidence"), 0.6)
    item_id = str((d or {}).get("item_id") or f"i{idx + 1}")
    cooking_method = str((d or {}).get("cooking_method") or "unknown").strip().lower() or "unknown"
    oil_added_tsp = max(0.0, float(_safe_float((d or {}).get("oil_added_tsp"), 0.0) or 0.0))
    if oil_added_tsp <= 0 and "fried" in cooking_method:
        oil_added_tsp = 1.0
    candidate_alternatives = [
        str(x).strip() for x in ((d or {}).get("candidate_alternatives") or []) if str(x).strip()
    ][:4]

    details = None
    macros100 = None
    micros100 = None
    fdc_id = None
    last_item_err = None
    powder_meta: Optional[Dict[str, Any]] = None
    cache_hit_delta = 0
    cache_miss_delta = 0

    try:
        from scan_food_rules import detect_powder_like, parse_powder_sentinel, resolve_powder_nutrition

        is_powder, powder_guess, needs_confirm = detect_powder_like(name, candidate_alternatives)
        sentinel_type = parse_powder_sentinel(name)
        resolved_type = sentinel_type or powder_guess
        if is_powder and resolved_type:
            resolved_powder = resolve_powder_nutrition(powder_type=resolved_type, grams=grams)
            if resolved_powder.get("macros100"):
                macros100 = resolved_powder.get("macros100")
                micros100 = resolved_powder.get("micros100") or {}
                details = {"description": resolved_powder.get("description"), "dataType": resolved_powder.get("dataType")}
                powder_meta = {
                    "is_powder_like": True,
                    "powder_type_guess": powder_guess,
                    "powder_type_resolved": resolved_type,
                    "needs_powder_confirmation": bool(needs_confirm and not sentinel_type),
                    "powder_confirmation": resolved_powder.get("powder_confirmation"),
                    "nutrition_source": "supplement_table",
                }
    except Exception:
        powder_meta = None

    resolved: Dict[str, Any] = {}
    try:
        if macros100 is None:
            resolved = resolve_nutrition_with_cache({"name": name}, _resolve_nutrition_usda) or {}
        if resolved.get("macros100"):
            macros100 = resolved["macros100"]
            micros100 = resolved.get("micros100")
            fdc_id = resolved.get("fdc_id")
            details = {"description": resolved.get("description"), "dataType": resolved.get("dataType")}
            if resolved.get("_cache_hit"):
                cache_hit_delta += 1
            else:
                cache_miss_delta += 1
    except Exception as e:
        last_item_err = str(getattr(e, "detail", str(e)))[:220]

    if not details and not macros100:
        try:
            candidates = usda_search_candidates(name)
        except Exception as e:
            last_item_err = str(getattr(e, "detail", str(e)))[:220]
            candidates = []
        for cand in (candidates or [])[:6]:
            try:
                fdc_id = int(cand["fdcId"])
                maybe_details = usda_food_details(fdc_id)
                maybe_macros = extract_macros_per_100g(maybe_details)
                maybe_micros = extract_micros_per_100g(maybe_details)
                details = maybe_details
                macros100 = maybe_macros
                micros100 = maybe_micros
                cache_miss_delta += 1
                break
            except Exception as e:
                last_item_err = str(getattr(e, "detail", e))
                continue

    if not details or not macros100:
        warn = {
            "item_id": item_id,
            "name": name,
            "warning": "nutrition_lookup_failed",
            "detail": (last_item_err or "No usable USDA match found")[:220],
        }
        row = {
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
            "_powder_meta": powder_meta,
        }
        return {
            "kind": "row",
            "result": row,
            "warning": warn,
            "cache_hit_delta": cache_hit_delta,
            "cache_miss_delta": cache_miss_delta,
            "kcal": 0.0,
            "p": 0.0,
            "c": 0.0,
            "f": 0.0,
            "micros_delta": {},
        }

    factor = grams / 100.0
    kcal = macros100["kcal_per_100g"] * factor
    p = macros100["protein_g_per_100g"] * factor
    c = macros100["carbs_g_per_100g"] * factor
    f = macros100["fat_g_per_100g"] * factor

    if oil_added_tsp > 0:
        kcal += oil_added_tsp * 40.5
        f += oil_added_tsp * 4.5

    micros: Dict[str, Any] = {}
    for k, v in (micros100 or {}).items():
        if k == "_units":
            continue
        micros[k] = round(float(v) * factor, 3)

    row = {
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
        "_powder_meta": powder_meta,
    }
    return {
        "kind": "row",
        "result": row,
        "warning": None,
        "cache_hit_delta": cache_hit_delta,
        "cache_miss_delta": cache_miss_delta,
        "kcal": float(kcal),
        "p": float(p),
        "c": float(c),
        "f": float(f),
        "micros_delta": micros,
    }


def _compute_scan_nutrition(detected_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float], List[Dict[str, Any]], Dict[str, int]]:
    cache_hit_count = 0
    cache_miss_count = 0
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

    pairs = list(enumerate(detected_items or []))
    parallel = str(os.getenv("SCAN_NUTRITION_PARALLEL", "1")).strip().lower() in ("1", "true", "yes")
    if parallel and len(pairs) > 1:
        max_workers = min(8, len(pairs))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            outcomes = list(pool.map(lambda ij: _scan_nutrition_one_item(ij[0], ij[1]), pairs))
    else:
        outcomes = [_scan_nutrition_one_item(i, d) for i, d in pairs]

    for oc in outcomes:
        if not isinstance(oc, dict) or oc.get("kind") == "skip":
            continue
        w = oc.get("warning")
        if isinstance(w, dict):
            item_warnings.append(w)
        results.append(oc.get("result") or {})
        cache_hit_count += int(oc.get("cache_hit_delta") or 0)
        cache_miss_count += int(oc.get("cache_miss_delta") or 0)
        total_kcal += float(_safe_float(oc.get("kcal"), 0.0) or 0.0)
        total_p += float(_safe_float(oc.get("p"), 0.0) or 0.0)
        total_c += float(_safe_float(oc.get("c"), 0.0) or 0.0)
        total_f += float(_safe_float(oc.get("f"), 0.0) or 0.0)
        md = oc.get("micros_delta") if isinstance(oc.get("micros_delta"), dict) else {}
        for mk, mv in md.items():
            if mk in total_micros:
                total_micros[mk] += float(mv)

    totals = {
        "kcal": round(total_kcal, 1),
        "protein_g": round(total_p, 1),
        "carbs_g": round(total_c, 1),
        "fat_g": round(total_f, 1),
    }
    cache_stats = {"hit_count": cache_hit_count, "miss_count": cache_miss_count}
    return results, totals, total_micros, item_warnings, cache_stats


_SCAN_MICRO_TOTAL_KEYS: Tuple[str, ...] = (
    "vitamin_d_ug",
    "vitamin_b12_ug",
    "iron_mg",
    "magnesium_mg",
    "calcium_mg",
    "potassium_mg",
    "sodium_mg",
    "fiber_g",
    "sugar_g",
)


def _retotal_scan_from_item_results(results: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Re-sum meal totals and micronutrients from per-item scan rows."""
    total_kcal = 0.0
    total_p = total_c = total_f = 0.0
    total_micros: Dict[str, float] = {k: 0.0 for k in _SCAN_MICRO_TOTAL_KEYS}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        total_kcal += float(_safe_float(r.get("kcal"), 0.0) or 0.0)
        m = r.get("macros") if isinstance(r.get("macros"), dict) else {}
        total_p += float(_safe_float(m.get("protein_g"), 0.0) or 0.0)
        total_c += float(_safe_float(m.get("carbs_g"), 0.0) or 0.0)
        total_f += float(_safe_float(m.get("fat_g"), 0.0) or 0.0)
        mic = r.get("micros") if isinstance(r.get("micros"), dict) else {}
        for k in _SCAN_MICRO_TOTAL_KEYS:
            if k in mic:
                total_micros[k] += float(_safe_float(mic.get(k), 0.0) or 0.0)
    totals = {
        "kcal": round(total_kcal, 1),
        "protein_g": round(total_p, 1),
        "carbs_g": round(total_c, 1),
        "fat_g": round(total_f, 1),
    }
    return totals, total_micros


def _macro_override_has_any_field(override: Any) -> bool:
    if override is None:
        return False
    for k in ("kcal", "protein_g", "carbs_g", "fat_g"):
        v = getattr(override, k, None)
        if v is not None:
            return True
    return False


def _apply_macro_override_to_scan(
    results: List[Dict[str, Any]],
    totals: Dict[str, float],
    total_micros: Dict[str, float],
    override: Any,
    default_item_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, float]]:
    """Patch one item's kcal/macros and re-total; scale that item's micros when kcal changes."""
    if not _macro_override_has_any_field(override):
        return results, totals, total_micros
    rows = [dict(x or {}) for x in (results or [])]
    if not rows:
        return results, totals, total_micros
    target_id = str(getattr(override, "item_id", "") or default_item_id or "").strip()
    idx = -1
    for i, it in enumerate(rows):
        if str(it.get("item_id") or "").strip() == target_id:
            idx = i
            break
    if idx < 0:
        idx = 0
    it = dict(rows[idx])
    old_kcal = float(_safe_float(it.get("kcal"), 0.0) or 0.0)
    macros: Dict[str, Any] = dict(it.get("macros") or {}) if isinstance(it.get("macros"), dict) else {}
    if getattr(override, "kcal", None) is not None:
        it["kcal"] = max(0.0, round(float(override.kcal), 1))
    if getattr(override, "protein_g", None) is not None:
        macros["protein_g"] = max(0.0, round(float(override.protein_g), 1))
    if getattr(override, "carbs_g", None) is not None:
        macros["carbs_g"] = max(0.0, round(float(override.carbs_g), 1))
    if getattr(override, "fat_g", None) is not None:
        macros["fat_g"] = max(0.0, round(float(override.fat_g), 1))
    it["macros"] = macros
    # Totals sum item.kcal for energy but macros from item.macros; if the user edits only P/C/F,
    # we must sync kcal from macros (Atwater 4/4/9) or "Total kcal" stays stale while macros update.
    explicit_kcal = getattr(override, "kcal", None) is not None
    macro_touched = any(
        getattr(override, k, None) is not None for k in ("protein_g", "carbs_g", "fat_g")
    )
    if not explicit_kcal and macro_touched:
        pg = float(_safe_float(macros.get("protein_g"), 0.0) or 0.0)
        cg = float(_safe_float(macros.get("carbs_g"), 0.0) or 0.0)
        fg = float(_safe_float(macros.get("fat_g"), 0.0) or 0.0)
        it["kcal"] = round(4.0 * pg + 4.0 * cg + 9.0 * fg, 1)
    new_kcal = float(_safe_float(it.get("kcal"), 0.0) or 0.0)
    kcal_changed = abs(new_kcal - old_kcal) > 0.01
    mic = it.get("micros") if isinstance(it.get("micros"), dict) else {}
    if kcal_changed and mic and old_kcal > 0.001:
        ratio = new_kcal / old_kcal
        it["micros"] = {k: round(float(v) * ratio, 3) for k, v in mic.items() if str(k) != "_units"}
    it["manual_macro_override"] = True
    rows[idx] = it
    new_totals, new_micros = _retotal_scan_from_item_results(rows)
    return rows, new_totals, new_micros


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
    seal_image: Optional[UploadFile] = File(default=None),
    product_type: str = Form("whey_protein"),
    brand: str = Form(""),
    variant: str = Form(""),
    barcode: str = Form(""),
    batch_number: str = Form(""),
    mfg_date: str = Form(""),
    expiry_date: str = Form(""),
    region: str = Form(""),
    proof_mode: Any = Form(False),
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
    seal_bytes: Optional[bytes] = None
    if seal_image is not None and str(getattr(seal_image, "filename", "") or "").strip():
        try:
            seal_bytes = await _read_valid_image_bytes(seal_image, "seal_image")
        except Exception as e:
            logger.info(f"supplement seal image skipped: {e}")
            seal_bytes = None
    image_hash = hashlib.sha256(front_bytes + b"::" + back_bytes + b"::" + (seal_bytes or b"")).hexdigest()

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
    structured_payload = (
        normalized.get("structured_data")
        if isinstance(normalized.get("structured_data"), dict)
        else {}
    )
    if not isinstance(structured_payload, dict):
        structured_payload = {}
    packaging_fingerprint = extract_packaging_fingerprint(structured_payload)

    fssai_result = extract_fssai_from_structured(structured_payload)
    if not fssai_result:
        combined_text_parts = [
            _supplement_text(normalized.get("brand")),
            _supplement_text(normalized.get("variant")),
            _supplement_text(normalized.get("batch_number")),
            _supplement_text(normalized.get("mfg_date")),
            _supplement_text(normalized.get("expiry_date")),
            " ".join([str(x).strip() for x in (structured_payload.get("ingredients") or []) if str(x).strip()]),
            json.dumps(structured_payload, ensure_ascii=False),
        ]
        fssai_result = extract_fssai_license("\n".join([x for x in combined_text_parts if x]))

    if fssai_result:
        regulatory = structured_payload.get("regulatory") if isinstance(structured_payload.get("regulatory"), dict) else {}
        regulatory = dict(regulatory)
        fssai_no = _supplement_digits(fssai_result.get("fssai_license_number"))
        regulatory["fssai_license_number"] = fssai_no
        regulatory["fssai_confidence"] = float(_safe_float(fssai_result.get("confidence"), 0.0) or 0.0)
        regulatory["fssai_method"] = str(fssai_result.get("method") or "").strip() or "regex"
        regulatory["fssai_source_image"] = str(fssai_result.get("source_image") or "back").strip() or "back"
        regulatory["fssai_raw_text_snippet"] = str(fssai_result.get("snippet") or "").strip()[:180]
        structured_payload["regulatory"] = regulatory
        normalized["structured_data"] = structured_payload

    logger.info(
        "supplement_fssai_extract",
        extra={
            "found": bool(fssai_result and _supplement_digits((fssai_result or {}).get("fssai_license_number"))),
            "confidence": float(_safe_float((fssai_result or {}).get("confidence"), 0.0) or 0.0),
            "method": str((fssai_result or {}).get("method") or ""),
        },
    )

    risk_flags: List[str] = []
    barcode_trace: Dict[str, Any] = {}
    off_status = 0
    off_brand = ""
    off_data: Dict[str, Any] = {}
    gs1_info: Dict[str, Any] = {}

    inferred_brand = _supplement_text(normalized.get("brand"))
    inferred_variant = _supplement_text(normalized.get("variant"))
    inferred_batch = _supplement_text(normalized.get("batch_number"))
    inferred_batch_pattern = infer_batch_pattern(inferred_batch)
    region_confidence = _supplement_region_confidence(
        region,
        x_country_code=x_country_code,
        cf_ipcountry=cf_ipcountry,
        x_vercel_ip_country=x_vercel_ip_country,
    )

    batch_pattern_row, _batch_match_params = _supplement_batch_pattern_query_match(
        inferred_brand,
        inferred_batch,
        inferred_variant,
    ) if (
        inferred_brand
        and inferred_batch
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
        and not _is_table_disabled(TBL_SUPPLEMENT_BATCH_PATTERNS)
    ) else (None, {})
    brand_pattern_stats = _supplement_brand_pattern_stats(
        inferred_brand,
        inferred_variant,
    ) if (
        inferred_brand
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
        and not _is_table_disabled(TBL_SUPPLEMENT_BATCH_PATTERNS)
    ) else {}

    normalized_barcode = normalize_barcode(normalized.get("barcode") or barcode)
    barcode_trace["normalized"] = normalized_barcode

    if not normalized_barcode:
        risk_flags.append("barcode_missing")
    else:
        gtin_type = detect_gtin_type(normalized_barcode)
        barcode_trace["gtin_type"] = gtin_type

        if not gtin_type:
            risk_flags.append("barcode_invalid_format")
        else:
            checksum_valid = validate_checksum(normalized_barcode)
            barcode_trace["checksum_valid"] = checksum_valid

            if not checksum_valid:
                risk_flags.append("barcode_checksum_invalid")
            else:
                prefix = extract_company_prefix(normalized_barcode)
                barcode_trace["prefix"] = prefix

                gs1_info = lookup_gs1_prefix_country(normalized_barcode)
                barcode_trace["gs1"] = gs1_info
                gs1_country = str((gs1_info or {}).get("country_code") or "").strip().upper()
                if not gs1_country:
                    risk_flags.append("gs1_prefix_unknown")
                elif region_code and region_confidence >= 0.75 and not _supplement_prefix_region_matches(gs1_country, region_code):
                    risk_flags.append("gs1_prefix_mismatch_region")

                off_data = await lookup_openfoodfacts(normalized_barcode)
                off_status = int(_safe_float(off_data.get("status"), 0) or 0)
                barcode_trace["off_status"] = off_status

                if off_status != 1:
                    risk_flags.append("barcode_not_found_public_db")
                else:
                    product_obj = off_data.get("product", {}) if isinstance(off_data.get("product"), dict) else {}
                    off_brand = str(product_obj.get("brands") or "").strip()
                    barcode_trace["off_brand"] = off_brand
                    if inferred_brand and off_brand:
                        if inferred_brand.lower() not in str(off_brand).lower():
                            risk_flags.append("barcode_brand_mismatch")

    mfr_result = _manufacturer_verification_signal(
        gtin=normalized_barcode,
        region=region_code,
        inferred_brand=inferred_brand,
        user_or_ip=uid or request.client.host if request and request.client else uid,
        prefetched_off=off_data if isinstance(off_data, dict) else None,
    )
    mfr_status = str(mfr_result.get("status") or "").strip().lower()
    mfr_company = _supplement_text(mfr_result.get("company_name"))
    if mfr_status == "verified":
        if mfr_company and inferred_brand and _mfr_company_matches_brand(mfr_company, inferred_brand):
            risk_flags.append("mfr_verified_company_match")
        elif mfr_company and inferred_brand:
            risk_flags.append("mfr_verified_company_mismatch")
    elif mfr_status == "not_found":
        risk_flags.append("mfr_verification_not_found")
    elif mfr_status in {"error", "unavailable"}:
        risk_flags.append("mfr_verification_unavailable")

    logger.info(
        "supplement_manufacturer_verification",
        extra={
            "gtin": _supplement_digits(normalized_barcode),
            "provider": str(MFR_VERIFY_PROVIDER or "none"),
            "status": mfr_status or "unavailable",
            "company_name": mfr_company,
            "latency_ms": int(_safe_float(mfr_result.get("latency_ms"), 0) or 0),
        },
    )

    nutrition_validation = validate_nutrition_math(structured_payload)
    for nflag in (nutrition_validation.get("flags") or []):
        token = str(nflag or "").strip()
        if token:
            risk_flags.append(token)

    batch_scan_context = {
        "brand": inferred_brand,
        "variant": inferred_variant,
        "batch_number": inferred_batch,
        "region": region_code,
        "macro_snapshot": _supplement_macro_snapshot(structured_payload),
    }
    batch_anomaly = compute_batch_anomaly(batch_scan_context, batch_pattern_row)
    batch_scan_count = int(_safe_float(batch_anomaly.get("scan_count"), 0) or 0)
    if batch_scan_count >= 8:
        for reason in (batch_anomaly.get("reasons") or []):
            token = str(reason or "").strip()
            if token:
                risk_flags.append(token)

    phrase_count = int(_safe_float(packaging_fingerprint.get("phrase_count"), 0) or 0)
    if phrase_count < 2:
        risk_flags.append("packaging_phrase_missing")

    total_pattern_obs = int(_safe_float((brand_pattern_stats or {}).get("total_observations"), 0) or 0)
    pattern_counts = (brand_pattern_stats or {}).get("pattern_counts")
    current_pattern_seen = 0
    if isinstance(pattern_counts, dict) and inferred_batch_pattern:
        current_pattern_seen = int(_safe_float(pattern_counts.get(inferred_batch_pattern), 0) or 0)
    if inferred_batch_pattern and total_pattern_obs >= 8 and current_pattern_seen <= 0:
        risk_flags.append("batch_pattern_unseen")

    proof_mode_enabled = _to_bool_flag(proof_mode, False)
    seal_check = detect_seal_presence(seal_bytes)
    seal_detected = seal_check.get("seal_detected")
    if proof_mode_enabled and seal_detected is not True:
        risk_flags.append("seal_missing")

    verification_payload = (
        structured_payload.get("verification")
        if isinstance(structured_payload.get("verification"), dict)
        else {}
    )
    verification_payload = dict(verification_payload or {})
    verification_payload["gs1_prefix"] = {
        "country_code": str((gs1_info or {}).get("country_code") or ""),
        "org_hint": str((gs1_info or {}).get("org_hint") or ""),
        "confidence": float(_safe_float((gs1_info or {}).get("confidence"), 0.0) or 0.0),
        "region_confidence": float(_safe_float(region_confidence, 0.0) or 0.0),
    }
    verification_payload["manufacturer_registry"] = {
        "status": mfr_status or "unavailable",
        "company_name": mfr_company,
        "source": str(mfr_result.get("source") or ""),
        "latency_ms": int(_safe_float(mfr_result.get("latency_ms"), 0) or 0),
    }
    verification_payload["nutrition_math"] = nutrition_validation
    verification_payload["batch_anomaly"] = batch_anomaly
    verification_payload["packaging_fingerprint"] = packaging_fingerprint
    verification_payload["batch_pattern_learning"] = {
        "current_pattern": inferred_batch_pattern or "",
        "dominant_pattern": str((brand_pattern_stats or {}).get("dominant_pattern") or ""),
        "current_pattern_seen": current_pattern_seen,
        "total_observations": total_pattern_obs,
    }
    verification_payload["seal_check"] = {
        "proof_mode": bool(proof_mode_enabled),
        "seal_detected": seal_detected,
    }
    structured_payload["verification"] = verification_payload
    structured_payload["packaging_fingerprint"] = packaging_fingerprint
    normalized["structured_data"] = structured_payload

    score, flags = calculate_authenticity_score(
        normalized,
        precomputed_barcode_flags=risk_flags,
    )
    region_scan_map = (
        batch_anomaly.get("region_scan_map")
        if isinstance(batch_anomaly.get("region_scan_map"), dict)
        else {}
    )
    same_region_scan_count = int(_safe_float(region_scan_map.get(region_code), 0) or 0) + (1 if region_code else 0)
    barcode_verified = (
        off_status == 1
        and "barcode_brand_mismatch" not in flags
        and "barcode_checksum_invalid" not in flags
        and "barcode_not_found_public_db" not in flags
    )
    score = _apply_supplement_score_cap(
        score,
        barcode_verified=barcode_verified,
        same_region_scan_count=same_region_scan_count,
    )
    level = interpret_supplement_score(score)
    explanation = _supplement_explanation(score, flags)

    _reg_trust = structured_payload.get("regulatory") if isinstance(structured_payload.get("regulatory"), dict) else {}
    _fssai_trust = str(_reg_trust.get("fssai_license_number") or "")
    _trust_pkg = _build_supplement_trust_payload(
        score=float(_safe_float(score, 0.0) or 0.0),
        flags=list(flags or []),
        normalized_barcode=str(normalized_barcode or ""),
        off_status=int(_safe_float(off_status, 0) or 0),
        off_brand=str(off_brand or ""),
        inferred_brand=str(inferred_brand or ""),
        gs1_info=gs1_info if isinstance(gs1_info, dict) else {},
        mfr_result=mfr_result if isinstance(mfr_result, dict) else {},
        mfr_status=str(mfr_status or ""),
        fssai_license=_fssai_trust,
        proof_mode_enabled=bool(proof_mode_enabled),
        seal_detected=seal_detected,
        batch_scan_count=int(_safe_float(batch_scan_count, 0) or 0),
    )
    _ref_urls = _trust_pkg.get("reference_urls") if isinstance(_trust_pkg.get("reference_urls"), dict) else {}
    _verification_reference_urls = {k: str(v).strip() for k, v in _ref_urls.items() if str(v or "").strip()}

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
        "structured_data": structured_payload,
        "packaging_fingerprint_json": packaging_fingerprint,
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
        structured_data=structured_payload,
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
        "structured_data": structured_payload,
        "scan_count": max(1, batch_scan_count + 1),
        "community_scan_count": max(1, batch_scan_count + 1),
        "batch_anomaly_score": float(_safe_float(batch_anomaly.get("anomaly_score"), 0.0) or 0.0),
        "request_id": request_id,
        "trust_badge": _trust_pkg.get("badge") if isinstance(_trust_pkg.get("badge"), dict) else {},
        "verification_sources": _trust_pkg.get("sources") if isinstance(_trust_pkg.get("sources"), list) else [],
        "verification_reference_urls": _verification_reference_urls,
    }
    logger.info(
        "supplement_barcode_verification",
        extra={
            "barcode_trace": barcode_trace,
            "risk_flags": risk_flags,
            "batch_anomaly": batch_anomaly,
            "nutrition_math": nutrition_validation,
            "packaging_fingerprint": packaging_fingerprint,
            "batch_pattern": inferred_batch_pattern,
            "proof_mode": bool(proof_mode_enabled),
            "seal_detected": seal_detected,
        },
    )
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


def compute_health_score(place: Dict[str, Any]) -> float:
    """Backward-compatible wrapper for legacy callers expecting only a float score."""
    try:
        scored = score_healthy_place(place)
        return round(float(_safe_float(scored.get("health_score"), 5.0) or 5.0), 1)
    except Exception:
        return 5.0


def _best_options_for_place(place: Dict[str, Any]) -> List[str]:
    """Backward-compatible wrapper for legacy callers expecting option suggestions list."""
    try:
        out = best_options_for_place(place)
        return out if isinstance(out, list) and out else ["Protein-forward meal", "Lower-oil whole-food option"]
    except Exception:
        return ["Protein-forward meal", "Lower-oil whole-food option"]


async def fetch_google_places(
    lat: float, lng: float, radius: int = 3000
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[int]]:
    """Returns (places, error_reason, raw_places_count). raw_places_count is from API body when 200."""
    if not GOOGLE_PLACES_API_KEY:
        logger.info("fetch_google_places: GOOGLE_PLACES_API_KEY not configured, returning empty list")
        return [], "places_api_key_not_configured", None

    cached = google_nearby_cache_get(lat, lng, radius)
    if cached is not None:
        return cached[0], cached[1], cached[2]

    payload = build_nearby_search_payload(
        lat,
        lng,
        radius,
        max_result_count=20,
        rank_preference="DISTANCE",
    )
    headers = {
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": PLACES_NEARBY_FIELD_MASK,
        "Content-Type": "application/json",
    }

    try:
        if httpx is not None:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(GOOGLE_PLACES_NEARBY_BASE, json=payload, headers=headers)
                body = r.json() if 200 <= r.status_code < 300 else {}
                if not body and r.status_code >= 300:
                    err_snippet = (str(r.text)[:400] if getattr(r, "text", None) else str(r))[:400]
                    logger.info(f"healthy places lookup failed: {r.status_code} {err_snippet}")
                    return [], f"api_error_{r.status_code}", None
        else:
            r = requests.post(GOOGLE_PLACES_NEARBY_BASE, json=payload, headers=headers, timeout=8.0)
            body = r.json() if 200 <= r.status_code < 300 else {}
            if not body and r.status_code >= 300:
                err_snippet = str(getattr(r, "text", ""))[:400]
                logger.info(f"healthy places lookup failed: {r.status_code} {err_snippet}")
                return [], f"api_error_{r.status_code}", None
    except Exception as e:
        logger.info(f"healthy places lookup failed: {e}")
        return [], "api_request_failed", None

    raw_places = body.get("places") if isinstance(body, dict) else []
    raw_count = len(raw_places) if isinstance(raw_places, list) else 0
    results = map_places_new_response(body if isinstance(body, dict) else {})

    # Log what Google returned so we can debug zero results (check Railway logs).
    logger.info(
        "fetch_google_places: response lat=%.4f lng=%.4f radius=%d body_keys=%s raw_places_count=%d parsed_count=%d",
        lat, lng, radius,
        list(body.keys()) if isinstance(body, dict) else [],
        raw_count,
        len(results),
    )
    if isinstance(body, dict) and body.get("error"):
        logger.info("fetch_google_places: body.error=%s", str(body.get("error"))[:500])

    if not results and raw_count > 0:
        logger.info(f"fetch_google_places: API returned {raw_count} raw places but parse yielded 0 at ({lat},{lng})")

    # If narrow search returned nothing, try once more with a wider radius before giving up.
    if not results and radius < 5000:
        wider_payload = build_nearby_search_payload(
            lat, lng, 5000, max_result_count=20, rank_preference="DISTANCE"
        )
        try:
            if httpx is not None:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    r2 = await client.post(GOOGLE_PLACES_NEARBY_BASE, json=wider_payload, headers=headers)
                    body2 = r2.json() if 200 <= r2.status_code < 300 else {}
            else:
                r2 = requests.post(GOOGLE_PLACES_NEARBY_BASE, json=wider_payload, headers=headers, timeout=8.0)
                body2 = r2.json() if 200 <= r2.status_code < 300 else {}
            if r2.status_code >= 300:
                return results, f"api_error_{r2.status_code}", raw_count
            results = map_places_new_response(body2 if isinstance(body2, dict) else {})
            if results:
                raw_count = len(body2.get("places") or []) if isinstance(body2, dict) else raw_count
                logger.info(f"fetch_google_places: wider fallback radius=5000 found {len(results)} places at ({lat},{lng})")
        except Exception as e2:
            logger.info(f"fetch_google_places: wider fallback failed: {e2}")

    google_nearby_cache_set(lat, lng, radius, results, None, raw_count)
    return results, None, raw_count



# Allowed sort_mode values for /places/healthy. Default "sectioned" for backward compatibility (existing clients expect sections).
HEALTHY_PLACES_SORT_MODES = ("flat_score", "sectioned")
HEALTHY_PLACES_SORT_MODE_DEFAULT = "sectioned"


# Default and max places to rank for /places/healthy (speeds up initial load).
HEALTHY_PLACES_LIMIT_DEFAULT = 12
HEALTHY_PLACES_LIMIT_MAX = 40


@app.get("/places/healthy")
async def healthy_places(
    lat: float,
    lng: float,
    radius: int = 3000,
    cut_mode: bool = False,
    goal: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    sort_mode: str = HEALTHY_PLACES_SORT_MODE_DEFAULT,
    debug: bool = False,
    user_id: str = "",
    context_mode: str = "",
    post_workout: bool = False,
    late_night: bool = False,
    local_hour: Optional[int] = None,
    poor_sleep_flag: bool = False,
    high_craving_risk_flag: bool = False,
    diet_preference: str = "",
    limit: Optional[int] = None,
):
    sort_mode_val = (sort_mode or "").strip().lower()
    if sort_mode_val not in HEALTHY_PLACES_SORT_MODES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_sort_mode",
                "message": f"sort_mode must be one of: {', '.join(HEALTHY_PLACES_SORT_MODES)}",
                "received": sort_mode,
                "allowed": list(HEALTHY_PLACES_SORT_MODES),
            },
        )
    healthy_sort_mode = sort_mode_val

    uid_for_location = (user_id or "").strip()
    if uid_for_location and math.isfinite(lat) and math.isfinite(lng):
        try:
            upsert_user_location(uid_for_location, lat, lng)
        except Exception:
            pass

    t_start = time.perf_counter()
    places, fetch_error_reason, raw_places_count = await fetch_google_places(lat, lng, radius=radius)
    t_fetch_ms = round((time.perf_counter() - t_start) * 1000, 1)

    use_fast_path = str(os.getenv("USE_FAST_PATH", "1")).strip().lower() in ("1", "true", "yes")
    rank_limit = max(1, min(HEALTHY_PLACES_LIMIT_MAX, int(limit or os.getenv("HEALTHY_PLACES_LIMIT", str(HEALTHY_PLACES_LIMIT_DEFAULT)) or HEALTHY_PLACES_LIMIT_DEFAULT)))
    # Default 8 (was 10): fewer deep-ranked places = faster first paint for Healthy Nearby
    shortlist_size = min(rank_limit, max(6, min(15, int(os.getenv("HEALTHY_SHORTLIST_SIZE", "8") or 8))))
    places_to_rank = list(places)
    shortlist_debug = {"fetched_count": len(places), "shortlisted_count": len(places), "skipped_count": 0}
    if use_fast_path and len(places) > shortlist_size:
        shortlisted, skipped, shortlist_debug = shortlist_places(
            places,
            shortlist_size=shortlist_size,
            origin_lat=float(lat),
            origin_lng=float(lng),
            cache_has=venue_cache_has,
        )
        places_to_rank = shortlisted
    places_to_rank = places_to_rank[:rank_limit]
    shortlist_debug["rank_limit"] = rank_limit
    t_shortlist_ms = round((time.perf_counter() - t_start) * 1000 - t_fetch_ms, 1)

    nutrition_mode = NutritionMode.CUT if bool(cut_mode) else NutritionMode.DEFAULT
    personalization_goal = normalize_personalization_goal(goal)
    personalization_goal_value_str = personalization_goal_value(personalization_goal)
    # One disk read per request (not per place): parallel rank workers used to each reload feedback/decision JSON.
    uid_clean = str(user_id or "").strip()
    feedback_events_prefetch: Optional[List[Dict[str, Any]]] = None
    decision_events_prefetch: Optional[List[Dict[str, Any]]] = None
    if uid_clean:
        try:
            feedback_events_prefetch = list_meal_feedback_events(user_id=uid_clean, limit=2000)
            decision_events_prefetch = list_meal_decision_events(user_id=uid_clean, limit=4000)
        except Exception:
            feedback_events_prefetch = None
            decision_events_prefetch = None
    t_rank_start = time.perf_counter()
    rank_ctx = build_rank_context_from_request(
        lat=float(lat),
        lng=float(lng),
        cut_mode=bool(cut_mode),
        goal=str(goal or "").strip(),
        nutrition_mode=nutrition_mode,
        personalization_goal=personalization_goal,
        personalization_goal_value_str=personalization_goal_value_str,
        diet_preference=diet_preference,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        post_workout=bool(post_workout),
        late_night=bool(late_night),
        poor_sleep_flag=bool(poor_sleep_flag),
        high_craving_risk_flag=bool(high_craving_risk_flag),
        context_mode=str(context_mode or "").strip(),
        local_hour=local_hour,
        user_id=uid_clean,
        feedback_events_prefetch=feedback_events_prefetch,
        decision_events_prefetch=decision_events_prefetch,
    )
    parallel_rank = str(os.getenv("HEALTHY_NEARBY_PARALLEL_RANK", "1")).strip().lower() in ("1", "true", "yes")
    if parallel_rank and len(places_to_rank) > 1:
        scored = await asyncio.gather(
            *[asyncio.to_thread(rank_one_healthy_nearby_place, p, rank_ctx) for p in places_to_rank]
        )
        scored = list(scored)
    else:
        scored = [rank_one_healthy_nearby_place(p, rank_ctx) for p in places_to_rank]

    # Personal memory is merged in rank_one_healthy_nearby_place (mem_dict + ranking_fields).
    # Avoid a second pass that re-fetched the same stores N times.

    t_rank_ms = round((time.perf_counter() - t_rank_start) * 1000, 1)
    t_total_ms = round((time.perf_counter() - t_start) * 1000, 1)

    # Add map-friendly metadata; sort by client-requested sort_mode (flat_score = display_rank_score_100 desc, distance; sectioned = sections then score).
    scored = enrich_places_for_healthy_map(
        scored,
        origin_lat=float(_safe_float(lat, 0.0) or 0.0),
        origin_lng=float(_safe_float(lng, 0.0) or 0.0),
        goal=str(goal or "").strip(),
        cut_mode=bool(cut_mode),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        sort_mode=healthy_sort_mode,
    )
    sections_payload = build_sections(scored) if healthy_sort_mode == "sectioned" else None

    # Enqueue visible places with low specificity for background enrichment
    for p in scored[:10]:
        if should_enqueue_for_low_specificity(p):
            try:
                enrichment_enqueue(
                    str(p.get("place_id") or p.get("id") or ""),
                    place_name=str(p.get("name") or ""),
                    place_types=p.get("types") if isinstance(p.get("types"), list) else None,
                    chain_match_key=p.get("chain_key") or p.get("chain_id"),
                    reason_enqueued="candidate_low_specificity",
                )
            except Exception:
                pass

    radius_used = int(max(200, min(50000, int(_safe_float(radius, 3000) or 3000))))
    response = {
        "sort_mode": healthy_sort_mode,
        "places_count": len(scored),
        "api_available": bool(GOOGLE_PLACES_API_KEY),
        "radius_used": radius_used,
    }
    if healthy_sort_mode == "flat_score":
        response["items"] = scored
    else:
        response["places"] = scored
        if sections_payload is not None:
            response["sections"] = sections_payload
    if fetch_error_reason:
        response["_no_results_reason"] = fetch_error_reason
    elif not scored:
        response["_no_results_reason"] = "no_places_returned_by_api"
    if (not scored or debug) and isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        response["_debug"] = {
            "request_lat": round(float(lat), 4),
            "request_lng": round(float(lng), 4),
            "radius_used": radius_used,
            "raw_places_count": raw_places_count,
            "parsed_count": len(places),
            "scored_count": len(scored),
            "empty_state_reason": response.get("_no_results_reason") or ("ok" if scored else "no_places_returned_by_api"),
        }
        if debug:
            response["_debug"]["timings_ms"] = {
                "nearby_fetch_ms": t_fetch_ms,
                "shortlist_ms": t_shortlist_ms,
                "ranking_ms": t_rank_ms,
                "total_ms": t_total_ms,
            }
            response["_debug"]["fetched_count"] = len(places)
            response["_debug"]["shortlisted_count"] = shortlist_debug.get("shortlisted_count", len(places_to_rank))
            response["_debug"]["deeply_ranked_count"] = len(scored)
            if shortlist_debug:
                response["_debug"]["shortlist_debug"] = shortlist_debug
    if scored and isinstance(scored[0].get("share_card"), dict):
        response["top_share_card"] = scored[0]["share_card"]
    if scored and isinstance(scored[0].get("reality_check_share_card"), dict):
        response["top_reality_check_share_card"] = scored[0]["reality_check_share_card"]
    return response


@app.get("/launch-readiness/report")
async def launch_readiness_report(area_key: str = "", include_examples: bool = True):
    """
    Launch readiness report for a suburb. Measures concrete value beyond Google Places.
    GET /launch-readiness/report?area_key=parramatta
    GET /launch-readiness/report?area_key=parramatta&include_examples=false
    """
    key = area_key.strip() or "parramatta"

    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )

    return await build_launch_readiness_report(
        key, fetch_fn=fetcher, include_examples=include_examples,
    )


@app.get("/launch-readiness/report/all")
async def launch_readiness_report_all(include_examples: bool = False, samples_per_area: int = 1):
    """Summaries for all configured launch areas. samples_per_area=1 for faster run."""
    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )

    return await build_all_areas_report(
        fetch_fn=fetcher, include_examples=include_examples, samples_per_area=samples_per_area,
    )


@app.get("/launch-readiness/remediation")
async def launch_readiness_remediation(top_n_suburbs: int = 2, samples_per_area: int = 2):
    """
    Prioritized remediation for top N worst suburbs. Surfaces missing chains,
    generic fallback venues, cuisines needing enrichment, duplicate clusters.
    GET /launch-readiness/remediation?top_n_suburbs=2&samples_per_area=2
    """
    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await generate_prioritized_remediation(
        fetch_fn=fetcher,
        top_n_suburbs=max(1, min(5, top_n_suburbs)),
        samples_per_area=max(1, min(5, samples_per_area)),
    )


@app.get("/launch-readiness/post-sync-report")
async def launch_readiness_post_sync_report(area_key: str = ""):
    """
    Post-sync launch readiness report for one area. Includes canonical sync metrics.
    GET /launch-readiness/post-sync-report?area_key=parramatta
    """
    key = area_key.strip() or "parramatta"

    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await run_post_sync_launch_report(key, fetch_fn=fetcher, include_examples=True)


@app.get("/launch-readiness/post-sync-report/all")
async def launch_readiness_post_sync_report_all(limit_areas: int = 5):
    """
    Post-sync reports for priority launch areas. Includes canonical metrics.
    GET /launch-readiness/post-sync-report/all?limit_areas=5
    """
    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await run_post_sync_reports_for_priority_areas(
        fetch_fn=fetcher,
        limit_areas=max(1, min(10, limit_areas)),
        include_examples=True,
    )


@app.get("/launch-readiness/next-enrichment-targets")
async def launch_readiness_next_enrichment_targets(limit: int = 20, limit_areas: int = 5):
    """
    Prioritized next-enrichment targets for action planning.
    GET /launch-readiness/next-enrichment-targets?limit=20&limit_areas=5
    """
    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await build_next_enrichment_targets_from_fetch(
        fetch_fn=fetcher,
        limit_total=max(1, min(50, limit)),
        limit_areas=max(1, min(10, limit_areas)),
    )


@app.post("/launch-readiness/apply-next-enrichment-targets")
async def launch_readiness_apply_next_enrichment_targets(payload: Dict[str, Any] = Body(default=None)):
    """
    Bulk apply next-enrichment targets. Fetches targets then applies to canonical store.
    Body: { "limit": 20, "area_keys": ["wentworthville", "parramatta"] } (optional)
    POST /launch-readiness/apply-next-enrichment-targets
    """
    body = payload or {}
    limit = max(1, min(50, int(body.get("limit") or 20)))
    area_keys = body.get("area_keys")
    if isinstance(area_keys, list):
        area_keys = [str(a).strip().lower() for a in area_keys if a]
    else:
        area_keys = None

    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await apply_next_enrichment_targets(
        limit=limit,
        area_keys=area_keys,
        fetch_fn=fetcher,
    )


@app.post("/launch-readiness/apply-enrichment-targets")
async def launch_readiness_apply_enrichment_targets(payload: Dict[str, Any] = Body(default=None)):
    """
    Bulk apply an explicit list of enrichment targets (from next-enrichment-targets output).
    Body: { "targets": [ { area_key, place_name, recommended_enrichment_action, ... } ], "limit": 20 } (optional)
    POST /launch-readiness/apply-enrichment-targets
    """
    body = payload or {}
    targets = body.get("targets")
    if not isinstance(targets, list):
        return {
            "targets_considered": 0,
            "targets_applied": 0,
            "targets_skipped": 0,
            "applied_by_action": {},
            "skipped_by_reason": {},
            "sample_results": [],
            "error": "body.targets must be a list",
        }
    limit = body.get("limit")
    if limit is not None:
        limit = max(1, min(50, int(limit)))
    from apply_enrichment_targets import apply_enrichment_targets
    return apply_enrichment_targets(targets, limit=limit)


@app.get("/admin/ops-dashboard")
async def admin_ops_dashboard(
    limit_targets: int = 20,
    limit_areas: int = 5,
    scan_window_days: int = 7,
    goal_coach_window_days: int = 7,
):
    """
    Compact internal ops dashboard summary.
    GET /admin/ops-dashboard?limit_targets=20&limit_areas=5&scan_window_days=7&goal_coach_window_days=7
    """
    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await build_ops_dashboard_summary(
        limit_targets=max(1, min(50, int(limit_targets))),
        limit_areas=max(1, min(10, int(limit_areas))),
        scan_window_days=max(1, min(30, int(scan_window_days))),
        goal_coach_window_days=max(1, min(30, int(goal_coach_window_days))),
        fetch_fn=fetcher,
    )


@app.post("/admin/ops-dashboard/apply-next-targets")
async def admin_ops_dashboard_apply_next_targets(payload: Dict[str, Any] = Body(default=None)):
    """
    Explicit internal operator action: bulk apply next targets into canonical store.
    Body: { "limit": 20, "area_keys": ["wentworthville", "parramatta"] }
    """
    p = payload if isinstance(payload, dict) else {}
    limit = max(1, min(50, int(p.get("limit") or 20)))
    area_keys = p.get("area_keys")
    if isinstance(area_keys, list):
        area_keys = [str(a).strip().lower() for a in area_keys if a]
    else:
        area_keys = None

    async def fetcher(lat: float, lng: float):
        return await healthy_places(
            lat=lat, lng=lng, radius=3000, cut_mode=True,
            sort_mode="flat_score", debug=True,
        )
    return await run_apply_next_targets(limit=limit, area_keys=area_keys, fetch_fn=fetcher)


@app.post("/admin/ops-dashboard/run-batch-dry-run")
async def admin_ops_dashboard_run_batch_dry_run(payload: Dict[str, Any] = Body(default=None)):
    """
    Explicit internal operator action: run batch push dry-run.
    Body: { "limit_users": 100 }
    """
    p = payload if isinstance(payload, dict) else {}
    limit_users = max(1, min(2000, int(p.get("limit_users") or 100)))
    return await run_push_batch_dry_run(limit_users=limit_users)


@app.post("/admin/ops-dashboard/check-receipts")
async def admin_ops_dashboard_check_receipts(payload: Dict[str, Any] = Body(default=None)):
    """
    Explicit internal operator action: check pending receipts (safe maintenance).
    Body: { "limit": 100 }
    """
    p = payload if isinstance(payload, dict) else {}
    limit = max(1, min(500, int(p.get("limit") or 100)))
    return await run_check_receipts(limit=limit)


@app.post("/admin/ops-dashboard/run-auto-promote")
async def admin_ops_dashboard_run_auto_promote(payload: Dict[str, Any] = Body(default=None)):
    """
    Explicit internal operator action: run contribution auto-promotion (evidence-based).
    Body: { "limit": 100, "area_key": "parramatta" }
    """
    p = payload if isinstance(payload, dict) else {}
    limit = max(1, min(500, int(p.get("limit") or 100)))
    area_key = str(p.get("area_key") or "").strip() or None
    return run_auto_promote(limit=limit, area_key=area_key)


@app.get("/launch-areas/coverage")
def launch_areas_coverage(area_key: str = ""):
    """
    Launch area coverage summary. Helps track launch readiness.
    GET /launch-areas/coverage
    GET /launch-areas/coverage?area_key=wentworthville
    """
    summary = summarize_launch_area_coverage(area_key.strip() or None)
    return summary


@app.post("/launch-enrichment/seed")
def launch_enrichment_seed(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """
    Seed local venue profiles from the launch enrichment pack.
    Body: { area_key?, limit_areas?, limit_per_area? }
    If area_key provided, seeds that area only. Else seeds all priority areas.
    Admin/debug utility.
    """
    p = payload if isinstance(payload, dict) else {}
    area_key = str(p.get("area_key") or "").strip() or None
    limit_areas = max(1, min(10, int(p.get("limit_areas") or 5)))
    limit_per_area = max(1, min(50, int(p.get("limit_per_area") or 20)))
    if area_key:
        return seed_launch_area_enrichment(area_key, limit=limit_per_area)
    return seed_all_priority_launch_areas(limit_areas=limit_areas, limit_per_area=limit_per_area)


@app.get("/launch-enrichment/status")
def launch_enrichment_status(area_key: Optional[str] = None):
    """
    Status of launch enrichment pack: pack definitions vs profiles in store.
    GET /launch-enrichment/status
    GET /launch-enrichment/status?area_key=parramatta
    """
    return get_launch_enrichment_status(area_key=area_key or None)


@app.post("/local-profiles/sync/supabase")
def local_profiles_sync_supabase(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """
    Sync trusted local profiles to Supabase canonical store.
    Body: { sync_launch_pack?, sync_auto_promoted?, area_key?, limit? }
    Admin/debug utility. Idempotent.
    """
    p = payload if isinstance(payload, dict) else {}
    sync_launch = bool(p.get("sync_launch_pack", True))
    sync_auto = bool(p.get("sync_auto_promoted", True))
    area_key = str(p.get("area_key") or "").strip() or None
    limit = max(1, min(500, int(p.get("limit") or 100)))
    if sync_launch and sync_auto:
        return sync_all_trusted_local_profiles(limit=limit)
    if sync_launch:
        return {"launch_pack": sync_launch_pack_profiles_to_supabase(area_key=area_key, limit=limit)}
    if sync_auto:
        return {"auto_promoted": sync_auto_promoted_profiles_to_supabase(area_key=area_key, limit=limit)}
    return {"synced": 0, "message": "No sync type selected"}


@app.get("/local-profiles/sync/status")
def local_profiles_sync_status(area_key: Optional[str] = None):
    """
    Status of canonical Supabase store vs local sources.
    GET /local-profiles/sync/status
    GET /local-profiles/sync/status?area_key=parramatta
    """
    return get_sync_status(area_key=area_key or None)


@app.get("/places/healthy/audit")
async def healthy_places_audit(
    lat: float,
    lng: float,
    radius_m: int = 3000,
    goal: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    sort_mode: str = "flat_score",
    limit: int = 10,
    include_filtered_out: bool = False,
    include_candidate_debug: bool = False,
    include_alert_candidates: bool = False,
    user_id: str = "",
    context_mode: str = "",
    post_workout: bool = False,
    late_night: bool = False,
    local_hour: Optional[int] = None,
    poor_sleep_flag: bool = False,
    high_craving_risk_flag: bool = False,
    diet_preference: str = "",
):
    """
    Developer-only audit: inspect why each place ranked where it did.
    Uses the same retrieval and canonical ranking as /places/healthy.
    No LLM. No ranking logic changes.
    """
    sort_mode_val = (sort_mode or "flat_score").strip().lower()
    if sort_mode_val not in HEALTHY_PLACES_SORT_MODES:
        sort_mode_val = "flat_score"
    radius = int(max(200, min(50000, radius_m)))
    cut_mode = (goal or "").strip().lower() in ("cut", "fat_loss")
    payload = await healthy_places(
        lat=lat,
        lng=lng,
        radius=radius,
        cut_mode=cut_mode,
        goal=goal,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        sort_mode=sort_mode_val,
        user_id=user_id,
        context_mode=context_mode,
        post_workout=post_workout,
        late_night=late_night,
        local_hour=local_hour,
        poor_sleep_flag=poor_sleep_flag,
        high_craving_risk_flag=high_craving_risk_flag,
        diet_preference=diet_preference,
    )
    items = payload.get("items") or payload.get("places") or []
    if not isinstance(items, list):
        items = []
    places_considered = len(items)
    limited = items[: max(1, min(100, limit))]
    places_returned = len(limited)
    results = []
    for i, place in enumerate(limited, 1):
        row = build_audit_result_row(place, i, include_candidate_debug=include_candidate_debug)
        if str(user_id or "").strip():
            try:
                mem = get_personal_meal_memory(
                    user_id=user_id,
                    place_id=row.get("place_id"),
                    place_name=row.get("place_name"),
                    item_name=row.get("best_item_name"),
                    goal=goal,
                    time_of_day="",
                )
                row.update(mem.to_dict())
            except Exception:
                pass
        results.append(row)
    filtered_out: List[Dict[str, Any]] = []
    if include_filtered_out and len(items) > len(limited):
        for place in items[places_returned:]:
            filtered_out.append(build_filtered_out_entry(place, "limit"))
    alert_candidates: List[Dict[str, Any]] = []
    if include_alert_candidates and items:
        context_info_raw = {
            "remaining_calories": remaining_calories,
            "remaining_protein_g": remaining_protein_g,
            "post_workout": bool(post_workout),
            "late_night": bool(late_night),
            "poor_sleep_flag": bool(poor_sleep_flag),
            "high_craving_risk_flag": bool(high_craving_risk_flag),
            "context_mode_override": (context_mode or "").strip() or None,
            "local_hour": int(local_hour) if local_hour is not None else 12,
        }
        ctx_modes = infer_context_mode(context_info_raw)
        user_context_alert = {
            "remaining_protein_g": remaining_protein_g,
            "remaining_calories": remaining_calories,
            "post_workout": bool(post_workout),
            "late_night": bool(late_night),
            "local_hour": int(local_hour) if local_hour is not None else 12,
            "context_mode": ctx_modes.get("context_mode", "default"),
            "context_flags": ctx_modes.get("context_flags", {}),
            "poor_sleep_flag": bool(poor_sleep_flag),
            "high_craving_risk_flag": bool(high_craving_risk_flag),
            "recent_alerts_count_6h": 0,
            "recent_alerts_count_24h": 0,
            "weekly_alert_count": 0,
            "ignored_streak": 0,
        }
        alert_candidates = build_smart_food_alert_candidates(user_context_alert, items, eligible_only=False)
        for ac in alert_candidates:
            ac["audit_one_liner"] = build_alert_audit_one_liner(ac)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    out = {
        "query": {
            "lat": lat,
            "lng": lng,
            "radius_m": radius,
            "goal": goal or None,
            "remaining_calories": remaining_calories,
            "remaining_protein_g": remaining_protein_g,
            "sort_mode": sort_mode_val,
            "limit": limit,
        },
        "summary": {
            "places_considered": places_considered,
            "places_returned": places_returned,
            "sort_mode": sort_mode_val,
            "generated_at": generated_at,
        },
        "results": results,
    }
    if include_filtered_out:
        out["filtered_out"] = filtered_out
    if include_alert_candidates:
        out["alert_candidates"] = alert_candidates
    return out


@app.get("/places/healthy/trace")
async def healthy_places_trace(
    lat: float,
    lng: float,
    radius: int = 3000,
    goal: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    user_id: str = "",
    sort_mode: str = "flat_score",
    query_place_name: str = "",
    query_place_id: str = "",
    include_all_places: bool = False,
    top_n_visible: int = 20,
):
    """
    Debug tool: explain why a place (e.g. Subway) did or did not appear.
    Runs same pipeline as /places/healthy. Builds traces for matching places or all.
    """
    cut_mode = (goal or "").strip().lower() in ("cut", "fat_loss")
    payload = await healthy_places(
        lat=lat,
        lng=lng,
        radius=radius,
        cut_mode=cut_mode,
        goal=goal,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        sort_mode=sort_mode,
        user_id=user_id,
        debug=True,
    )
    items = payload.get("items") or payload.get("places") or []
    if not isinstance(items, list):
        items = []

    user_context = {
        "remaining_calories": remaining_calories,
        "remaining_protein_g": remaining_protein_g,
        "cut_mode": cut_mode,
        "goal": goal,
    }

    query_name = (query_place_name or "").strip().lower()
    query_id = (query_place_id or "").strip()

    if include_all_places:
        places_to_trace = items
    elif query_name or query_id:
        places_to_trace = []
        for p in items:
            name = str(p.get("name") or p.get("place_name") or "").strip().lower()
            pid = str(p.get("place_id") or p.get("id") or "").strip()
            if query_name and query_name in name:
                places_to_trace.append(p)
            elif query_id and pid == query_id:
                places_to_trace.append(p)
    else:
        places_to_trace = items[:5]

    place_to_rank = {}
    for i, p in enumerate(items):
        pid = str(p.get("place_id") or p.get("id") or "").strip()
        if pid:
            place_to_rank[pid] = i + 1
    traces = []
    for place in places_to_trace:
        pid = str(place.get("place_id") or place.get("id") or "").strip()
        rank = place_to_rank.get(pid)
        visible_places = items[: max(1, top_n_visible)]
        trace = build_place_trace(
            place,
            user_context=user_context,
            visible_rank=rank,
            visible_places=visible_places,
        )
        trace["visible_rank"] = rank
        trace["fetched_but_hidden"] = rank is None or rank > top_n_visible
        if trace["fetched_but_hidden"] and not trace.get("hidden_reason"):
            trace["hidden_reason"] = "top_n_cutoff" if rank and rank > top_n_visible else "low_score"
        traces.append(trace)

    fetched_but_hidden = [t for t in traces if t.get("fetched_but_hidden")]
    top_visible = items[: max(1, min(12, top_n_visible))]

    out = {
        "ok": True,
        "query": {
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "goal": goal,
            "query_place_name": query_place_name or None,
            "query_place_id": query_place_id or None,
            "include_all_places": include_all_places,
            "top_n_visible": top_n_visible,
        },
        "fetched_count": len(items),
        "visible_count": min(len(items), top_n_visible),
        "trace_count": len(traces),
        "traces": traces,
        "fetched_but_hidden": [{"place_name": t["place_name"], "place_id": t["place_id"], "hidden_reason": t.get("hidden_reason")} for t in fetched_but_hidden],
        "top_visible": [
            {
                "place_name": p.get("name") or p.get("place_name"),
                "place_id": p.get("place_id") or p.get("id"),
                "display_rank_score_100": p.get("display_rank_score_100"),
                "chosen_candidate_specificity_tier": p.get("chosen_candidate_specificity_tier"),
                "best_item_name": p.get("best_item_name") or p.get("best_order"),
            }
            for p in top_visible
        ],
    }
    debug_block = payload.get("_debug") or {}
    if debug_block:
        out["shortlist_debug"] = debug_block.get("shortlist_debug")
        out["timings_ms"] = debug_block.get("timings_ms")
        out["fetched_count"] = debug_block.get("fetched_count", len(items))
        out["shortlisted_count"] = debug_block.get("shortlisted_count", len(items))
        out["deeply_ranked_count"] = debug_block.get("deeply_ranked_count", len(items))
    return out


@app.get("/smart-food-alerts/candidates")
async def smart_food_alert_candidates(
    lat: float,
    lng: float,
    radius: int = 3000,
    goal: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    user_id: str = "",
    context_mode: str = "",
    post_workout: bool = False,
    late_night: bool = False,
    local_hour: Optional[int] = None,
    poor_sleep_flag: bool = False,
    high_craving_risk_flag: bool = False,
    diet_preference: str = "",
    recent_alerts_count_6h: Optional[int] = None,
    recent_alerts_count_24h: Optional[int] = None,
    weekly_alert_count: Optional[int] = None,
    ignored_streak: Optional[int] = None,
    recently_opened_app: bool = False,
    recently_viewed_nearby: bool = False,
    eligible_only: bool = False,
):
    """
    Dev/internal: build smart food alert candidates.
    Reuses same ranked place pipeline as /places/healthy.
    Returns alert candidates with why_triggered, suppression_reasons, eligible_to_send.
    """
    cut_mode = (goal or "").strip().lower() in ("cut", "fat_loss")
    context_info_raw = {
        "remaining_calories": remaining_calories,
        "remaining_protein_g": remaining_protein_g,
        "post_workout": bool(post_workout),
        "late_night": bool(late_night),
        "poor_sleep_flag": bool(poor_sleep_flag),
        "high_craving_risk_flag": bool(high_craving_risk_flag),
        "context_mode_override": (context_mode or "").strip() or None,
        "local_hour": int(local_hour) if local_hour is not None else 12,
    }
    ctx_modes = infer_context_mode(context_info_raw)
    user_context = {
        "remaining_calories": remaining_calories,
        "remaining_protein_g": remaining_protein_g,
        "post_workout": bool(post_workout),
        "late_night": bool(late_night),
        "local_hour": int(local_hour) if local_hour is not None else 12,
        "context_mode": ctx_modes.get("context_mode", "default"),
        "context_flags": ctx_modes.get("context_flags", {}),
        "poor_sleep_flag": bool(poor_sleep_flag),
        "high_craving_risk_flag": bool(high_craving_risk_flag),
        "recent_alerts_count_6h": recent_alerts_count_6h if recent_alerts_count_6h is not None else 0,
        "recent_alerts_count_24h": recent_alerts_count_24h if recent_alerts_count_24h is not None else 0,
        "weekly_alert_count": weekly_alert_count if weekly_alert_count is not None else 0,
        "ignored_streak": ignored_streak if ignored_streak is not None else 0,
        "recently_opened_app": bool(recently_opened_app),
        "recently_viewed_nearby": bool(recently_viewed_nearby),
    }
    payload = await healthy_places(
        lat=lat,
        lng=lng,
        radius=radius,
        cut_mode=cut_mode,
        goal=goal,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        sort_mode="flat_score",
        user_id=user_id,
        context_mode=context_mode,
        post_workout=post_workout,
        late_night=late_night,
        local_hour=local_hour,
        poor_sleep_flag=poor_sleep_flag,
        high_craving_risk_flag=high_craving_risk_flag,
        diet_preference=diet_preference,
    )
    items = payload.get("items") or payload.get("places") or []
    if not isinstance(items, list):
        items = []
    candidates = build_smart_food_alert_candidates(
        user_context, items, eligible_only=eligible_only
    )
    for c in candidates:
        c["audit_one_liner"] = build_alert_audit_one_liner(c)
    return {
        "candidates": candidates,
        "places_considered": len(items),
        "query": {
            "lat": lat,
            "lng": lng,
            "remaining_protein_g": remaining_protein_g,
            "remaining_calories": remaining_calories,
            "context_mode": user_context.get("context_mode"),
            "local_hour": user_context.get("local_hour"),
        },
    }


@app.get("/places/healthy-map")
async def healthy_places_map(
    lat: float,
    lng: float,
    radius: int = 3000,
    cut_mode: bool = False,
    goal: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    limit: int = 40,
):
    nearby_payload = await healthy_places(
        lat=lat,
        lng=lng,
        radius=radius,
        cut_mode=bool(cut_mode),
        goal=goal,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
    )

    # /places/healthy returns "places" when sort_mode=sectioned, "items" when sort_mode=flat_score
    places = (
        nearby_payload.get("places") or nearby_payload.get("items") or []
    ) if isinstance(nearby_payload, dict) else []

    return build_healthy_food_map_response(
        places=places if isinstance(places, list) else [],
        lat=float(_safe_float(lat, 0.0) or 0.0),
        lng=float(_safe_float(lng, 0.0) or 0.0),
        radius=int(max(200, min(5000, int(_safe_float(radius, 3000) or 3000)))),
        goal=str(goal or "").strip(),
        cut_mode=bool(cut_mode),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        limit=max(1, min(80, int(_safe_float(limit, 40) or 40))),
    )


@app.post("/meal-feedback")
async def meal_feedback(payload: Dict[str, Any] = Body(...)):
    """
    Capture meal feedback events (partial allowed) and allow follow-up updates via feedback_id.
    """
    try:
        saved = upsert_meal_feedback_event(payload if isinstance(payload, dict) else {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return {"ok": True, "feedback": saved}


@app.post("/meal-decision-event")
async def meal_decision_event(payload: Dict[str, Any] = Body(...)):
    """
    Append-only meal decision events (viewed/opened/swap accepted/chosen/ignored).
    """
    try:
        saved = log_meal_decision_event(payload if isinstance(payload, dict) else {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return {"ok": True, "event": saved}


@app.get("/push/rollout/status")
async def push_rollout_status():
    """
    Rollout config and observability. Returns sending_enabled, rollout_mode,
    rollout_percent, active_user_days, max_per_6h, max_per_24h, allowlist_count,
    recent_sent_count, recent_receipt_ok_count, recent_receipt_error_count.
    """
    return get_rollout_status()


@app.post("/push/register")
async def push_register(payload: Dict[str, Any] = Body(...)):
    """
    Register Expo push token for a user. Dedupes by user_id + expo_push_token.
    Payload: user_id, expo_push_token, platform (ios|android), device_name?, app_version?
    """
    try:
        p = payload if isinstance(payload, dict) else {}
        saved = register_push_token(p)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return {"ok": True, "token": saved}


@app.post("/push/unregister")
async def push_unregister(payload: Dict[str, Any] = Body(...)):
    """
    Unregister Expo push token. Mark inactive.
    Payload: user_id, expo_push_token
    """
    try:
        p = payload if isinstance(payload, dict) else {}
        result = unregister_push_token(p)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return {"ok": True, **result}


@app.post("/push/send-smart-alerts")
async def push_send_smart_alerts(payload: Dict[str, Any] = Body(...)):
    """
    Send eligible Smart Food Alerts as Expo push notifications.
    Payload: user_id, lat, lng, eligible_only?, dry_run?, context?, fatigue?, goal?, radius?
    Top 1 candidate per user per run (conservative).
    Respects EXPO_PUSH_SENDING_ENABLED; dry_run works even when disabled.
    """
    p = payload if isinstance(payload, dict) else {}
    user_id = (p.get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=422, detail={"error": "user_id required"})
    lat = _safe_float(p.get("lat"), 0.0)
    lng = _safe_float(p.get("lng"), 0.0)
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise HTTPException(status_code=422, detail={"error": "lat and lng required"})

    try:
        upsert_user_location(user_id, lat, lng)
    except Exception:
        pass

    dry_run = bool(p.get("dry_run", True))
    eligible_only = bool(p.get("eligible_only", True))
    goal = str(p.get("goal") or "").strip()
    radius = max(500, min(5000, int(_safe_float(p.get("radius"), 3000) or 3000)))
    context = dict(p.get("context") or {})
    if "tone_preference" not in context:
        context["tone_preference"] = get_user_tone_for_push(user_id)

    return await _send_smart_alert_for_user(
        healthy_places,
        user_id,
        lat,
        lng,
        context=context,
        fatigue=p.get("fatigue") or {},
        goal=goal,
        radius=radius,
        eligible_only=eligible_only,
        dry_run=dry_run,
    )


@app.post("/push/send-smart-alerts/batch")
async def push_send_smart_alerts_batch(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """
    Batch Smart Alert send for eligible users. Scheduler-friendly.
    Payload: { "limit_users": 200, "dry_run": true }
    Default: dry_run=true (requires explicit dry_run=false for real sends).
    """
    from push_batch_sender import send_smart_alerts_for_eligible_users, _batch_user_limit

    p = payload if isinstance(payload, dict) else {}
    limit_users = max(1, min(2000, int(p.get("limit_users") or _batch_user_limit())))
    dry_run = bool(p.get("dry_run", True))

    result = await send_smart_alerts_for_eligible_users(
        limit_users=limit_users,
        dry_run=dry_run,
    )
    return result


@app.get("/push/send-smart-alerts/batch/status")
async def push_send_smart_alerts_batch_status():
    """
    Lightweight config/health summary for batch Smart Alert sending.
    """
    from push_rollout import get_rollout_status
    from push_batch_sender import (
        _batch_user_limit,
        _sample_results_limit,
        list_users_with_active_push_tokens,
    )
    from user_last_location_store import list_user_ids_with_location

    status = get_rollout_status()
    status["batch_user_limit"] = _batch_user_limit()
    status["batch_sample_results_limit"] = _sample_results_limit()
    users_with_tokens = list_users_with_active_push_tokens(limit=10000)
    users_with_location = set(list_user_ids_with_location(limit=10000))
    batch_eligible_count = sum(1 for u in users_with_tokens if (u.get("user_id") or "").strip() in users_with_location)
    status["users_with_active_tokens"] = len(users_with_tokens)
    status["users_with_stored_location"] = len(users_with_location)
    status["batch_eligible_estimate"] = batch_eligible_count
    return status


@app.post("/push/check-receipts")
async def push_check_receipts(payload: Dict[str, Any] = Body(...)):
    """
    Fetch receipts for given ticket IDs, update delivery records, deactivate invalid tokens.
    Payload: ticket_ids (list), dry_run? (default false)
    """
    p = payload if isinstance(payload, dict) else {}
    ticket_ids = p.get("ticket_ids") or []
    if not isinstance(ticket_ids, list):
        ticket_ids = []
    ticket_ids = [str(t).strip() for t in ticket_ids if str(t).strip()][:1000]
    dry_run = bool(p.get("dry_run", False))

    if dry_run:
        return {"ok": True, "dry_run": True, "processed": 0, "receipt_ok": 0, "receipt_error": 0, "tokens_deactivated": 0}

    if not ticket_ids:
        return {"ok": True, "dry_run": False, "processed": 0, "receipt_ok": 0, "receipt_error": 0, "tokens_deactivated": 0}

    receipts_result = fetch_expo_push_receipts(ticket_ids)
    receipts = receipts_result.get("receipts") or {}
    receipt_ok = 0
    receipt_error = 0
    tokens_deactivated = 0

    for tid, receipt in receipts.items():
        delivery = get_delivery_by_ticket_id(tid)
        if not delivery:
            continue
        if receipt.get("status") == "ok":
            update_delivery_status(delivery["delivery_id"], status="receipt_ok", expo_receipt_id=tid)
            receipt_ok += 1
        else:
            err_details = receipt.get("details") or {}
            err_code = err_details.get("error") if isinstance(err_details, dict) else None
            err_msg = receipt.get("message") or ""
            update_delivery_status(
                delivery["delivery_id"],
                status="receipt_error",
                error_code=str(err_code) if err_code else None,
                error_message=err_msg[:500],
            )
            receipt_error += 1
            if is_device_not_registered(receipt):
                mark_token_deactivated_for_delivery(delivery["delivery_id"])
                deactivate_token_by_value(delivery["user_id"], delivery["expo_push_token"])
                tokens_deactivated += 1

    return {
        "ok": receipts_result.get("ok", True),
        "dry_run": False,
        "processed": len(receipts),
        "receipt_ok": receipt_ok,
        "receipt_error": receipt_error,
        "tokens_deactivated": tokens_deactivated,
    }


@app.post("/push/check-pending-receipts")
async def push_check_pending_receipts(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """
    Check receipts for all pending (sent but not receipt-checked) tickets.
    Optional payload: { "limit": 100 }
    """
    p = payload if isinstance(payload, dict) else {}
    limit = max(1, min(500, int(p.get("limit") or 100)))
    pending = list_pending_receipt_ids(limit=limit)
    if not pending:
        return {"ok": True, "pending_count": 0, "processed": 0, "receipt_ok": 0, "receipt_error": 0, "tokens_deactivated": 0}
    result = await push_check_receipts({"ticket_ids": pending, "dry_run": False})
    result["pending_count"] = len(pending)
    return result


@app.get("/push/analytics/summary")
async def push_analytics_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    dry_run_only: bool = False,
    real_send_only: bool = False,
):
    """
    Push analytics summary. Query params: start_date, end_date, user_id?, alert_type?, dry_run_only?, real_send_only?
    """
    from push_analytics import build_push_analytics_summary

    summary = build_push_analytics_summary(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        alert_type=alert_type,
        dry_run_only=dry_run_only,
        real_send_only=real_send_only,
    )
    return {"ok": True, "summary": summary}


@app.get("/push/analytics/recent-deliveries")
async def push_analytics_recent_deliveries(
    limit: int = 50,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    Recent delivery records. Query params: limit (default 50), user_id?, alert_type?, status?
    """
    deliveries = list_recent_deliveries(
        limit=max(1, min(200, limit or 50)),
        user_id=user_id,
        alert_type=alert_type,
        status=status,
    )
    rows = [
        {
            "delivery_id": d.get("delivery_id"),
            "user_id": d.get("user_id"),
            "alert_type": d.get("alert_type"),
            "place_name": d.get("place_name"),
            "title": d.get("title"),
            "dry_run": d.get("dry_run"),
            "status": d.get("status"),
            "expo_ticket_id": d.get("expo_ticket_id"),
            "error_code": d.get("error_code"),
            "created_at": d.get("created_at"),
        }
        for d in deliveries
    ]
    return {"ok": True, "deliveries": rows, "count": len(rows)}


@app.get("/push/analytics/rollout-status")
async def push_analytics_rollout_status(debug: bool = False):
    """
    Rollout configuration. debug=true shows allowlist size and sample (redacted) IDs.
    """
    import os

    push_enabled = str(os.getenv("EXPO_PUSH_SENDING_ENABLED", "0")).strip().lower() in ("1", "true", "yes")
    mode = get_push_rollout_mode()
    allowlist = get_push_test_user_ids()
    sample_count = 0
    sample_ids = []
    if debug and allowlist:
        sample_count = len(allowlist)
        for uid in sorted(allowlist)[:5]:
            sample_ids.append(uid[:4] + "***" + uid[-4:] if len(uid) > 12 else "***")
    return {
        "ok": True,
        "push_sending_enabled": push_enabled,
        "rollout_mode": mode,
        "allowlist_size": len(allowlist),
        "sample_ids_count": sample_count if debug else None,
        "sample_ids_preview": sample_ids if debug else None,
    }


@app.get("/places/feed")
async def places_feed(lat: float, lng: float, radius: int = 3000, limit_per_section: int = 6):
    nearby_places, _, _ = await fetch_google_places(lat, lng, radius=radius)
    return build_healthy_nearby_feed(
        nearby_places=nearby_places,
        limit_per_section=max(1, min(12, int(_safe_float(limit_per_section, 6) or 6))),
    )

@app.get("/places/lunch-decision")
async def places_lunch_decision(
    lat: float,
    lng: float,
    radius: int = 3000,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    target_calories: Optional[float] = None,
    consumed_calories: Optional[float] = None,
    target_protein_g: Optional[float] = None,
    consumed_protein_g: Optional[float] = None,
    current_hour: Optional[int] = None,
    goal: str = "",
    cut_mode: bool = False,
):
    nearby_places, fetch_err, _ = await fetch_google_places(lat, lng, radius=radius)
    lunch_payload = build_lunch_decision_response(
        nearby_places=nearby_places,
        origin_lat=float(_safe_float(lat, 0.0) or 0.0),
        origin_lng=float(_safe_float(lng, 0.0) or 0.0),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        current_hour=current_hour,
        goal=goal,
        cut_mode=bool(cut_mode),
        use_llm_place_context=False,
    )
    lunch_payload["daily_decision"] = build_daily_decision_response(
        nearby_places=nearby_places,
        origin_lat=float(_safe_float(lat, 0.0) or 0.0),
        origin_lng=float(_safe_float(lng, 0.0) or 0.0),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        current_hour=current_hour,
        goal=goal,
        cut_mode=bool(cut_mode),
        use_llm_place_context=False,
    )
    lunch_payload["api_available"] = bool(GOOGLE_PLACES_API_KEY)
    lunch_payload["nearby_places_count"] = len(nearby_places)
    if fetch_err:
        lunch_payload["_no_results_reason"] = fetch_err
    elif not GOOGLE_PLACES_API_KEY:
        lunch_payload["_no_results_reason"] = "places_api_key_not_configured"
    elif not nearby_places:
        lunch_payload["_no_results_reason"] = "no_places_returned_by_api"
    return lunch_payload


@app.get("/places/daily-decision")
async def places_daily_decision(
    lat: float,
    lng: float,
    radius: int = 3000,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    target_calories: Optional[float] = None,
    consumed_calories: Optional[float] = None,
    target_protein_g: Optional[float] = None,
    consumed_protein_g: Optional[float] = None,
    current_hour: Optional[int] = None,
    goal: str = "",
    cut_mode: bool = False,
):
    nearby_places, _, _ = await fetch_google_places(lat, lng, radius=radius)
    return {
        "daily_decision": build_daily_decision_response(
            nearby_places=nearby_places,
            origin_lat=float(_safe_float(lat, 0.0) or 0.0),
            origin_lng=float(_safe_float(lng, 0.0) or 0.0),
            remaining_calories=remaining_calories,
            remaining_protein_g=remaining_protein_g,
            target_calories=target_calories,
            consumed_calories=consumed_calories,
            target_protein_g=target_protein_g,
            consumed_protein_g=consumed_protein_g,
            current_hour=current_hour,
            goal=goal,
            cut_mode=bool(cut_mode),
            use_llm_place_context=False,
        )
    }


@app.get("/places/better-choice-nearby")
async def better_choice_nearby(
    lat: float,
    lng: float,
    selected_place_name: str = "",
    selected_place_id: str = "",
    radius: int = 3000,
    min_score_delta: float = 1.2,
    limit: int = 5,
):
    if not str(selected_place_name or "").strip() and not str(selected_place_id or "").strip():
        raise HTTPException(status_code=400, detail="selected_place_name or selected_place_id is required")

    nearby_places, _, _ = await fetch_google_places(lat, lng, radius=radius)

    return build_better_choice_nearby_response(
        nearby_places=nearby_places,
        selected_place_name=str(selected_place_name or "").strip(),
        selected_place_id=str(selected_place_id or "").strip(),
        origin_lat=float(_safe_float(lat, 0.0) or 0.0),
        origin_lng=float(_safe_float(lng, 0.0) or 0.0),
        min_score_delta=float(_safe_float(min_score_delta, 1.2) or 1.2),
        limit=max(1, min(10, int(_safe_float(limit, 5) or 5))),
    )


@app.post("/places/daily-fatloss-coach")
async def daily_fatloss_coach(payload: DailyFatLossCoachRequestModel):
    radius = int(max(200, min(5000, int(_safe_float(payload.radius, 2000) or 2000))))
    nearby_places, _, _ = await fetch_google_places(payload.lat, payload.lng, radius=radius)

    return build_daily_fatloss_coach_response(
        nearby_places=nearby_places,
        target_calories=float(_safe_float(payload.target_calories, 2000.0) or 2000.0),
        consumed_calories=float(_safe_float(payload.consumed_calories, 0.0) or 0.0),
        target_protein_g=float(_safe_float(payload.target_protein_g, 150.0) or 150.0),
        consumed_protein_g=float(_safe_float(payload.consumed_protein_g, 0.0) or 0.0),
        limit=max(1, min(10, int(_safe_float(payload.limit, 5) or 5))),
    )



@app.post("/coach/weekly-progress")
def coach_weekly_progress(payload: WeeklyCoachRequestModel):
    rows = [
        row.model_dump(exclude_none=True)
        for row in (payload.daily_rows or [])
        if isinstance(row, WeeklyCoachDayRowModel)
    ]
    choices = [
        row.model_dump(exclude_none=True)
        for row in (payload.choices or [])
        if isinstance(row, WeeklyCoachChoiceRowModel)
    ]

    weekly_payload = build_weekly_coach_payload(
        days=rows,
        choices=choices,
        goal=str(payload.goal or "").strip(),
        cut_mode=bool(payload.cut_mode),
    )

    return {
        "week_start": str(payload.week_start or "").strip(),
        "weekly_coach": weekly_payload,
    }


@app.post("/menu/scan")
async def scan_menu_endpoint(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    restaurant_name: Optional[str] = Form(default=""),
    place_id: Optional[str] = Form(default=""),
    cuisine: Optional[str] = Form(default=""),
    ocr_text: Optional[str] = Form(default=""),
    remaining_calories: Optional[float] = Form(default=None),
    remaining_protein_g: Optional[float] = Form(default=None),
    goal: Optional[str] = Form(default=""),
    cut_mode: Optional[bool] = Form(default=False),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = require_user_id(x_user_id, user_id)
    require_ai_consent(uid)

    image_bytes = await _read_valid_image_bytes(file, "file")
    request_id = _new_request_id()

    ocr_override = str(ocr_text or "").strip()
    if ocr_override:
        ocr_payload = {
            "raw_text": ocr_override,
            "menu_lines": [x.strip() for x in ocr_override.splitlines() if x.strip()][:50],
            "ocr_confidence": 0.72,
        }
    else:
        ocr_payload = _menu_scan_ocr_from_image(image_bytes, request_id=request_id)

    menu_scan = build_menu_scan_response(
        raw_menu_text=str(ocr_payload.get("raw_text") or ""),
        ocr_lines=ocr_payload.get("menu_lines") if isinstance(ocr_payload.get("menu_lines"), list) else None,
        ocr_confidence=float(_safe_float(ocr_payload.get("ocr_confidence"), 0.0) or 0.0),
        restaurant_name=str(restaurant_name or "").strip(),
        place_id=str(place_id or "").strip(),
        cuisine=str(cuisine or "").strip(),
        remaining_calories=float(_safe_float(remaining_calories, 0.0)) if remaining_calories is not None else None,
        remaining_protein_g=float(_safe_float(remaining_protein_g, 0.0)) if remaining_protein_g is not None else None,
        goal=str(goal or "").strip(),
        cut_mode=bool(cut_mode),
    )
    menu_scan["request_id"] = request_id
    menu_scan["ocr_confidence"] = round(float(_safe_float(ocr_payload.get("ocr_confidence"), 0.0) or 0.0), 2)

    return {"menu_scan": menu_scan}


@app.post("/places/menu-intelligence/ingest")
def ingest_menu_intelligence_endpoint(payload: MenuIntelligenceIngestRequestModel):
    place_id = str(payload.place_id or "").strip()
    if not place_id:
        raise HTTPException(status_code=400, detail="place_id is required")

    items = [
        item.model_dump(exclude_none=True)
        for item in payload.menu_items
        if str(item.item_name or "").strip()
    ]
    if not items:
        raise HTTPException(status_code=400, detail="menu_items must include at least one item")

    entry = ingest_menu_intelligence(
        place_id=place_id,
        restaurant_name=str(payload.restaurant_name or "").strip(),
        cuisine=str(payload.cuisine or "").strip(),
        menu_items=items,
        source=str(payload.source or "user_scan").strip(),
    )
    if not isinstance(entry, dict):
        raise HTTPException(status_code=500, detail="Failed to persist menu intelligence")

    return {
        "ok": True,
        "place_id": place_id,
        "restaurant_name": entry.get("restaurant_name", ""),
        "cuisine": entry.get("cuisine", ""),
        "menu_items_count": len(entry.get("menu_items") or []),
        "confidence": entry.get("confidence"),
        "last_updated": entry.get("last_updated"),
        "menu_intelligence_version": entry.get("version", "v1"),
    }


@app.get("/places/menu-intelligence/{place_id}")
def get_menu_intelligence_endpoint(place_id: str):
    pid = str(place_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="place_id is required")

    entry = get_place_menu_intelligence(pid)
    if not isinstance(entry, dict):
        return {"found": False, "place_id": pid, "menu_items": []}

    out = dict(entry)
    out["found"] = True
    return out


@app.post("/places/recommendation-feedback")
def log_recommendation_feedback(payload: RecommendationFeedbackEventRequestModel):
    event_name = " ".join(str(payload.event or "").strip().lower().split())
    place_id = str(payload.place_id or "").strip()
    item_name = " ".join(str(payload.item or "").strip().split())

    if not place_id:
        raise HTTPException(status_code=400, detail="place_id is required")

    if event_name not in ALLOWED_FEEDBACK_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"event must be one of: {', '.join(sorted(ALLOWED_FEEDBACK_EVENTS))}",
        )

    logged = log_recommendation_feedback_event(
        event=event_name,
        place_id=place_id,
        item=item_name,
        user_id=str(payload.user_id or "").strip(),
        session_id=str(payload.session_id or "").strip(),
        metadata=payload.metadata if isinstance(payload.metadata, dict) else {},
    )
    if not isinstance(logged, dict):
        raise HTTPException(status_code=500, detail="Failed to log recommendation feedback")

    return {
        "ok": True,
        "event_id": str(logged.get("event_id") or ""),
        "event": str(logged.get("event") or event_name),
        "place_id": place_id,
        "item": item_name,
        "created_at": logged.get("created_at"),
        "feedback_signal": get_place_item_feedback_signal(place_id, item_name),
    }


@app.get("/places/recommendation-feedback/summary")
def recommendation_feedback_summary(place_id: str = "", item: str = ""):
    pid = str(place_id or "").strip()
    item_name = " ".join(str(item or "").strip().split())
    return get_feedback_summary(place_id=pid, item=item_name)


# -------------------- VENUE CONTRIBUTIONS (REVIEW) --------------------
@app.post("/venue-contributions")
def create_venue_contribution(payload: Dict[str, Any] = Body(...)):
    """
    Create a venue contribution (user suggestion). Payload: place_id, place_name, area_key,
    contribution_type (better_order_suggestion, vegetarian_option_missing, etc.), user_id, payload.
    """
    ctype = str(payload.get("contribution_type") or "better_order_suggestion").strip().lower()
    if ctype not in ("better_order_suggestion", "item_not_on_menu", "vegetarian_option_missing",
                     "vegan_option_missing", "recommendation_accurate", "recommendation_inaccurate", "menu_item_correction"):
        raise HTTPException(status_code=400, detail="invalid_contribution_type")
    place_name = str(payload.get("place_name") or "").strip()
    area_key = str(payload.get("area_key") or "").strip()
    if not place_name or not area_key:
        raise HTTPException(status_code=400, detail="place_name and area_key required")
    rec = create_contribution(
        place_id=str(payload.get("place_id") or "").strip(),
        place_name=place_name,
        area_key=area_key,
        contribution_type=ctype,
        user_id=str(payload.get("user_id") or "").strip(),
        payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else None,
    )
    return {"ok": True, "contribution_id": rec.get("contribution_id"), "created_at": rec.get("created_at")}


@app.get("/venue-contributions/pending")
def venue_contributions_pending(area_key: str = "", limit: int = 50):
    """
    List pending venue contributions for review.
    Optional area_key filter. limit 1-200.
    """
    limit = max(1, min(200, int(limit) if limit else 50))
    ak = str(area_key or "").strip().lower() or None
    return {"contributions": list_pending_contributions(area_key=ak, limit=limit)}


@app.get("/venue-contributions/review-bundle")
def venue_contributions_review_bundle(contribution_id: str = ""):
    """
    Get review bundle for a contribution: contribution + profile + templates + related.
    """
    cid = str(contribution_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="contribution_id required")
    bundle = get_contribution_review_bundle(cid)
    if bundle.get("error"):
        raise HTTPException(status_code=404, detail=bundle.get("error", "not_found"))
    return bundle


@app.post("/venue-contributions/review/approve")
def venue_contributions_review_approve(payload: Dict[str, Any] = Body(...)):
    """
    Approve a contribution. Payload: contribution_id, reviewer_id, action_type,
    template_payload (for accept_as_new_template), swap_payload (for accept_as_swap),
    reviewer_notes.
    """
    cid = str(payload.get("contribution_id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="contribution_id required")
    result = approve_contribution(
        cid,
        reviewer_id=str(payload.get("reviewer_id") or "").strip(),
        action_payload=payload,
    )
    if result.get("outcome") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "approval_failed"))
    return result


@app.post("/venue-contributions/review/reject")
def venue_contributions_review_reject(payload: Dict[str, Any] = Body(...)):
    """
    Reject a contribution. Payload: contribution_id, reviewer_id, reviewer_notes.
    """
    cid = str(payload.get("contribution_id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="contribution_id required")
    result = reject_contribution(
        cid,
        reviewer_id=str(payload.get("reviewer_id") or "").strip(),
        reviewer_notes=str(payload.get("reviewer_notes") or "").strip(),
    )
    if result.get("outcome") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "rejection_failed"))
    return result


@app.post("/venue-contributions/auto-promote/run")
def venue_contributions_auto_promote_run(
    payload: Dict[str, Any] = Body(default={}),
):
    """
    Run evidence-based auto-promotion. Optional place_id, area_key, place_name to scope.
    Body: { place_id?, area_key?, place_name?, limit? }. Admin/debug utility.
    """
    p = payload if isinstance(payload, dict) else {}
    place_id = str(p.get("place_id") or "").strip() or None
    area_key = str(p.get("area_key") or "").strip() or None
    place_name = str(p.get("place_name") or "").strip() or None
    limit = max(1, min(int(p.get("limit") or 100), 500))
    if place_id or area_key or place_name:
        result = run_auto_promotion_for_place(
            place_id=place_id,
            area_key=area_key,
            place_name=place_name,
        )
    else:
        result = run_auto_promotion_all(limit=limit)
    return result


@app.get("/venue-contributions/auto-promote/status")
def venue_contributions_auto_promote_status(
    place_id: Optional[str] = None,
    area_key: Optional[str] = None,
):
    """
    Get auto-promotion status for a place: aggregates, scores, would_promote.
    """
    result = get_auto_promotion_status(
        place_id=place_id or None,
        area_key=area_key or None,
    )
    return result


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

def _joined_item_names_lower(results: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for it in results or []:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name") or "").strip().lower()
        if n:
            parts.append(n)
    return " ".join(parts)


_PROTEIN_PRODUCT_HINTS = (
    "whey",
    "protein",
    "isolate",
    "concentrate",
    "casein",
    "bcaa",
    "protein bar",
    "energy bar",
    "granola bar",
    "supplement",
    "powder",
    "shake",
    "blend",
    "mass gainer",
)
_PACKAGED_SNACK_HINTS = (
    "chips",
    "crisps",
    "cookie",
    "biscuit",
    "candy",
    "chocolate bar",
    "snack bar",
    "cereal bar",
    "cracker",
    "instant ",
    "ready to drink",
    "rtd",
)
_SUGARY_DRINK_HINTS = (
    "cola",
    "soda",
    "soft drink",
    "lemonade",
    "iced tea",
    "energy drink",
    "coke",
    "pepsi",
    "sprite",
    "fanta",
    "mountain dew",
    "ginger ale",
    "root beer",
    "tonic water",
)


def _build_protein_kcal_insight(
    totals: Dict[str, Any],
    results: List[Dict[str, Any]],
    *,
    powder_detected: bool,
) -> Optional[Dict[str, Any]]:
    """Single-serve / supplement scans: protein per calorie density with a simple emoji band."""
    kcal = float(_safe_float(totals.get("kcal"), 0.0) or 0.0)
    protein_g = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
    if kcal < 35:
        return None
    names = _joined_item_names_lower(results)
    n_items = len(
        [x for x in (results or []) if isinstance(x, dict) and str(x.get("name") or "").strip()]
    )
    protein_hint = any(h in names for h in _PROTEIN_PRODUCT_HINTS)
    packaged_hint = any(h in names for h in _PACKAGED_SNACK_HINTS) or " bar" in names or names.endswith(" bar")
    small_portion = n_items <= 2 and kcal <= 550
    relevant = bool(
        powder_detected
        or protein_hint
        or (small_portion and packaged_hint)
        or (small_portion and protein_g >= 12.0 and kcal <= 520)
    )
    if not relevant:
        return None

    protein_per_100_kcal = (protein_g / max(kcal, 1.0)) * 100.0
    pct_cals_from_protein = min(100.0, (protein_g * 4.0 / max(kcal, 1.0)) * 100.0)

    if protein_per_100_kcal >= 9.0 or pct_cals_from_protein >= 30:
        band = "strong"
        emoji = "😊"
        headline = "Strong protein for the calories"
    elif protein_per_100_kcal >= 6.5 or pct_cals_from_protein >= 22:
        band = "good"
        emoji = "🙂"
        headline = "Decent protein density"
    elif protein_per_100_kcal >= 4.5 or pct_cals_from_protein >= 15:
        band = "ok"
        emoji = "😐"
        headline = "Okay — not a protein standout"
    else:
        band = "weak"
        emoji = "⚠️"
        headline = "Low protein for the calories"

    caption = (
        f"About {round1(protein_per_100_kcal)} g protein per 100 kcal "
        f"(~{round1(pct_cals_from_protein)}% of calories from protein)."
    )
    if "isolate" in names and "concentrate" not in names:
        caption += " Label wording suggests isolate — often a higher protein % than concentrate for the same calories."
    elif "concentrate" in names and "isolate" not in names:
        caption += " Label wording suggests concentrate — isolate is often higher protein % per scoop if you are comparing tubs."

    return {
        "relevant": True,
        "band": band,
        "emoji": emoji,
        "headline": headline,
        "caption": caption.strip(),
        "protein_per_100_kcal": round1(protein_per_100_kcal),
        "protein_calorie_pct": round1(pct_cals_from_protein),
        "protein_g": round1(protein_g),
        "kcal": round1(kcal),
    }


def _build_scan_swap_suggestions(
    totals: Dict[str, Any],
    coaching: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Goal-aware nudges when the plate looks calorie-dense or ultra-processed (generic copy, no brand names)."""
    kcal = float(_safe_float(totals.get("kcal"), 0.0) or 0.0)
    protein_g = float(_safe_float(totals.get("protein_g"), 0.0) or 0.0)
    carbs_g = float(_safe_float(totals.get("carbs_g"), 0.0) or 0.0)
    names = _joined_item_names_lower(results)
    up = float(_safe_float(coaching.get("ultra_processed_score"), 0.0) or 0.0)

    swaps: List[Dict[str, Any]] = []
    seen = set()

    def add(title: str, reason: str, kind: str) -> None:
        key = (title, kind)
        if key in seen:
            return
        seen.add(key)
        swaps.append({"title": title, "reason": reason, "kind": kind})

    if up >= 6.0 and kcal >= 120:
        add(
            "Try a less processed choice next time",
            "Refined carb + fat combos are easy to overeat — whole-food swaps often improve fullness for the same goal.",
            "upf",
        )

    if kcal >= 70 and protein_g < 4 and carbs_g >= 12:
        if any(h in names for h in _SUGARY_DRINK_HINTS) or ("juice" in names and kcal >= 80):
            add(
                "Lower-calorie drink swap",
                "If you want flavor with fewer calories, a no-sugar version or sparkling water often fits fat-loss goals better.",
                "beverage",
            )
        elif carbs_g >= 18:
            add(
                "Watch liquid calories",
                "Sweet drinks rarely add fullness — unsweetened tea, coffee, or water can free calories for food.",
                "beverage",
            )

    if kcal >= 180 and protein_g < 8 and up >= 5.5:
        add(
            "Add protein or fiber alongside",
            "Pairing with Greek yogurt, fruit, vegetables, or nuts can steady energy and hunger.",
            "balance",
        )

    return swaps[:4]


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

# Dimension registry (Phase 1 MVP): canonical clarification dimensions.
DIMENSION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "added_fat": {
        "label": "Dressing / added oil?",
        "options": ["None", "Light", "Normal", "Heavy"],
        "impact_kcal": 120,
    },
    "dairy_type": {
        "label": "Milk / yogurt type?",
        "options": ["None", "Whole", "Low-fat", "Skim", "Almond", "Oat", "Soy", "Coconut"],
        "impact_kcal": 60,
    },
    "sweetener": {
        "label": "Sweetener?",
        "options": ["None", "Sugar", "Honey", "Syrup", "Artificial", "Other"],
        "impact_kcal": 60,
    },
    "protein_add_on": {
        "label": "Extra protein added?",
        "options": ["No", "Yes - small", "Yes - medium", "Yes - large"],
        "impact_kcal": 80,
    },
    "sauce_or_spread": {
        "label": "Sauce / spread?",
        "options": ["None", "Butter", "Mayo", "Creamy sauce", "Other"],
        "impact_kcal": 90,
    },
    "portion_size": {
        "label": "Portion size?",
        "options": ["Small", "Medium", "Large"],
        "impact_kcal": 180,
    },
    "frozen_treat_style": {
        "label": "Frozen treat type?",
        "options": [
            "Regular / full-fat",
            "Light / low-fat",
            "High-protein (whey)",
            "Frozen yogurt",
            "Dairy-free / vegan",
        ],
        "impact_kcal": 95,
    },
    "starch_portion": {
        "label": "Starch portion?",
        "options": ["Small", "Medium", "Large"],
        "impact_kcal": 140,
    },
    "cooking_method": {
        "label": "How cooked?",
        "options": ["Boiled", "Poached", "Grilled", "Baked", "Pan fried", "Deep fried", "Other"],
        "impact_kcal": 100,
    },
    "egg_count": {
        "label": "How many eggs?",
        "options": ["1", "2", "3", "4+"],
        "impact_kcal": 80,
    },
}

# Alias mapping: old / non-canonical hint keys -> canonical dimension ID.
DIMENSION_ALIASES: Dict[str, str] = {
    "milk_type": "dairy_type",
    "milk_base": "dairy_type",
    "yogurt_type": "dairy_type",
    "dressing": "added_fat",
    "spread": "sauce_or_spread",
    "how_cooked": "cooking_method",
}


def _normalize_dim_id(key: str) -> str:
    """Return canonical dimension ID; pass-through if already canonical or unknown."""
    k = str(key or "").strip()
    if not k:
        return ""
    return DIMENSION_ALIASES.get(k, k)


def _is_meaningful_stored_value(v: Any) -> bool:
    """True only when stored value is non-empty and usable."""
    if v is None:
        return False
    s = str(v).strip()
    return len(s) > 0


def _stored_has_meaningful_value(stored: Dict[str, Any], dim_id: str) -> bool:
    """True if stored has a meaningful value for this dimension (canonical or alias key)."""
    if not stored or not dim_id:
        return False
    if _is_meaningful_stored_value(stored.get(dim_id)):
        return True
    for alias, canonical in DIMENSION_ALIASES.items():
        if canonical == dim_id and _is_meaningful_stored_value(stored.get(alias)):
            return True
    return False


def _vision_resolves_dimension(hints: Dict[str, Any], dim_id: str) -> bool:
    """True if ingredient_hints has a meaningful value for this dimension (canonical or alias key)."""
    if not hints or not dim_id:
        return False
    if _is_meaningful_stored_value(hints.get(dim_id)):
        return True
    for alias, canonical in DIMENSION_ALIASES.items():
        if canonical == dim_id and _is_meaningful_stored_value(hints.get(alias)):
            return True
    return False


# Helpers for dimension metadata (safe lookups).

def _dim_meta(dim_id: str) -> Dict[str, Any]:
    return DIMENSION_REGISTRY.get(_normalize_dim_id(str(dim_id or "").strip()), {})


def _dim_impact(dim_id: str) -> float:
    meta = _dim_meta(dim_id)
    try:
        return float(_safe_float(meta.get("impact_kcal"), 0) or 0)
    except Exception:
        return 0.0


def _dim_label(dim_id: str, fallback: Optional[str] = None) -> str:
    meta = _dim_meta(dim_id)
    label = str(meta.get("label") or fallback or dim_id or "").strip()
    if not label:
        return ""
    return label


def _dim_options(dim_id: str, fallback: Optional[List[str]] = None) -> List[str]:
    meta = _dim_meta(dim_id)
    opts = meta.get("options")
    if isinstance(opts, list) and opts:
        return [str(o) for o in opts if str(o).strip()]
    if isinstance(fallback, list) and fallback:
        return [str(o) for o in fallback if str(o).strip()]
    return []


# Ingredient clarification (Issues 9/11): infer from name when possible, ask only when unclear.
# Each question can have "name_hints": [(phrase_regex_or_substring, option_value), ...] for inference.
_CLARIFICATION_RULES: List[Dict[str, Any]] = [
    {
        "pattern": re.compile(r"^(coffee|espresso|latte|cappuccino|flat white|mocha|americano|chai|tea)\b", re.I),
        "questions": [
            {
                "key": "dairy_type",
                "label": "Milk?",
                "options": ["None", "Whole", "Low-fat", "Skim", "Almond", "Oat", "Soy", "Coconut"],
                "name_hints": [
                    ("black|no milk|without milk|no dairy", "None"),
                    ("whole milk|full.?cream", "Whole"),
                    ("low.?fat|lowfat|semi.?skim", "Low-fat"),
                    ("skim|skimmed", "Skim"),
                    ("almond|almond milk", "Almond"),
                    ("oat milk|oat.?milk|oat latte", "Oat"),
                    ("soy|soya|soy milk", "Soy"),
                    ("coconut milk|coconut", "Coconut"),
                ],
            },
            {
                "key": "sweetener",
                "label": "Sweetener?",
                "options": ["None", "Sugar", "Artificial", "Honey", "Other"],
                "name_hints": [
                    ("no sugar|unsweetened|no sweetener|without sugar", "None"),
                    ("sugar|sweetened|with sugar", "Sugar"),
                    ("artificial|stevia|sucralose|sweet.?n.?low|equal", "Artificial"),
                    ("honey", "Honey"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(smoothie|shake|milkshake)\b", re.I),
        "questions": [
            {
                "key": "dairy_type",
                "label": "Milk base?",
                "options": ["Dairy", "Almond", "Oat", "Soy", "None / water"],
                "name_hints": [
                    ("dairy|milk base|whole milk|yogurt base", "Dairy"),
                    ("almond|almond milk", "Almond"),
                    ("oat milk|oat.?milk", "Oat"),
                    ("soy|soya", "Soy"),
                    ("water|no milk|water base", "None / water"),
                ],
            },
            {
                "key": "sweetener",
                "label": "Added sweetener?",
                "options": ["None", "Sugar", "Honey", "Syrup", "Other"],
                "name_hints": [
                    ("no sugar|unsweetened", "None"),
                    ("sugar|sweetened", "Sugar"),
                    ("honey", "Honey"),
                    ("syrup|maple|agave", "Syrup"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(salad|green salad|mixed salad|garden salad|caesar|side salad)\b", re.I),
        "questions": [
            {
                "key": "added_fat",
                "label": "Dressing/oil?",
                "options": ["None", "Light", "Normal", "Heavy"],
                "name_hints": [
                    ("no dressing|undressed|dry|naked", "None"),
                    ("light dressing|light oil|drizzle", "Light"),
                    ("heavy|extra dressing|creamy", "Heavy"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(sandwich|wrap|burger|bagel|toast)\b", re.I),
        "questions": [
            {
                "key": "sauce_or_spread",
                "label": "Spread/butter?",
                "options": ["None", "Butter", "Mayo", "Both", "Other"],
                "name_hints": [
                    ("no spread|dry|plain", "None"),
                    ("butter|buttered", "Butter"),
                    ("mayo|mayonnaise", "Mayo"),
                    ("both|butter and mayo", "Both"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(yogurt|yoghurt|parfait)\b", re.I),
        "questions": [
            {
                "key": "dairy_type",
                "label": "Yogurt type?",
                "options": ["Greek high-protein", "Greek regular", "Regular", "Skyr"],
                "name_hints": [
                    ("high.?protein|high protein", "Greek high-protein"),
                    ("greek|greek yogurt", "Greek regular"),
                    ("regular|plain yogurt", "Regular"),
                    ("skyr", "Skyr"),
                ],
            },
            {
                "key": "toppings",
                "label": "Sweet toppings?",
                "options": ["None", "Honey", "Jam", "Granola", "Fruit only", "Other"],
                "name_hints": [
                    ("plain|no toppings|unsweetened", "None"),
                    ("honey", "Honey"),
                    ("jam|preserve", "Jam"),
                    ("granola|muesli", "Granola"),
                    ("fruit|berries", "Fruit only"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(oatmeal|porridge|oats)\b", re.I),
        "questions": [
            {
                "key": "dairy_type",
                "label": "Made with milk?",
                "options": ["Water", "Whole", "Skim", "Almond", "Oat", "Soy"],
                "name_hints": [
                    ("water|just oats", "Water"),
                    ("milk|whole milk", "Whole"),
                    ("skim", "Skim"),
                    ("almond", "Almond"),
                    ("oat milk", "Oat"),
                    ("soy", "Soy"),
                ],
            },
            {
                "key": "sweetener",
                "label": "Sweetener?",
                "options": ["None", "Sugar", "Honey", "Maple", "Other"],
                "name_hints": [
                    ("plain|no sugar|unsweetened", "None"),
                    ("sugar|brown sugar", "Sugar"),
                    ("honey", "Honey"),
                    ("maple|syrup", "Maple"),
                ],
            },
            {
                "key": "protein_add_on",
                "label": "Egg added?",
                "options": ["No", "Yes - 1", "Yes - 2", "Yes - 3+"],
                "name_hints": [
                    ("no egg|without egg", "No"),
                    ("with egg|1 egg|one egg", "Yes - 1"),
                    ("2 egg|two egg", "Yes - 2"),
                    ("3 egg|three egg", "Yes - 3+"),
                ],
            },
            {
                "key": "dairy_type",
                "label": "Yogurt in it?",
                "options": ["None", "Greek high-protein", "Greek regular", "Regular"],
                "name_hints": [
                    ("no yogurt|without yogurt", "None"),
                    ("greek|high.?protein yogurt", "Greek high-protein"),
                    ("greek yogurt", "Greek regular"),
                    ("yogurt", "Regular"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"\b(ice cream|gelato|sundae|soft serve|frozen yogurt|frozen yoghurt|fro yo|froyo|ice pop|popsicle|sorbet)\b", re.I),
        "questions": [
            {
                "key": "frozen_treat_style",
                "label": "What kind of frozen treat?",
                "options": [
                    "Regular / full-fat",
                    "Light / low-fat",
                    "High-protein (whey)",
                    "Frozen yogurt",
                    "Dairy-free / vegan",
                ],
                "name_hints": [
                    (r"protein|whey|halo|enlightened|skinny|low.?cal ice|high.?protein ice", "High-protein (whey)"),
                    (r"low.?fat|light|lite|reduced.?fat|skim", "Light / low-fat"),
                    (r"fro.?yo|frozen yogurt|frozen yoghurt|yogurt ice", "Frozen yogurt"),
                    (r"vegan|dairy.?free|oat ice|almond|cashew|coconut.?based|^sorbet\b", "Dairy-free / vegan"),
                    (r"gelato|premium|full.?fat", "Regular / full-fat"),
                ],
            },
            {
                "key": "sweetener",
                "label": "Sweetener?",
                "name_hints": [
                    (r"no sugar|unsweetened|sugar.?free", "None"),
                    (r"stevia|sucralose|artificial|sweetener", "Artificial"),
                    (r"honey|syrup|maple|agave", "Honey"),
                    (r"sugar|sweetened", "Sugar"),
                ],
            },
        ],
    },
    {
        "pattern": re.compile(r"^(egg|eggs|scrambled egg|boiled egg|omelette|omelet)\b", re.I),
        "questions": [
            {
                "key": "cooking_method",
                "label": "How cooked?",
                "options": ["Boiled", "Poached", "Scrambled", "Fried", "Omelette", "Other"],
                "name_hints": [
                    ("boiled|hard.?boiled|soft.?boiled", "Boiled"),
                    ("poached", "Poached"),
                    ("scrambled", "Scrambled"),
                    ("fried|sunny", "Fried"),
                    ("omelette|omelet", "Omelette"),
                ],
            },
            {
                "key": "egg_count",
                "label": "How many eggs?",
                "options": ["1", "2", "3", "4+"],
                "name_hints": [
                    ("1 egg|one egg|single", "1"),
                    ("2 egg|two egg|double", "2"),
                    ("3 egg|three", "3"),
                    ("4 egg|four|many", "4+"),
                ],
            },
        ],
    },
]


def _infer_ingredient_choices_from_name(name: str, questions: List[Dict[str, Any]]) -> Dict[str, str]:
    """Infer clarification choices from item name when possible (e.g. 'oat milk latte' -> milk_type Oat)."""
    if not name or not questions:
        return {}
    phrase = " ".join(name.strip().lower().split())
    out: Dict[str, str] = {}
    for q in questions:
        key = str(q.get("key") or "").strip()
        if not key or key in out:
            continue
        options = [str(o) for o in (q.get("options") or []) if str(o).strip()]
        name_hints = list(q.get("name_hints") or [])
        for hint_phrase, value in name_hints:
            if not value:
                continue
            try:
                if re.search(hint_phrase, phrase, re.I):
                    out[key] = value
                    break
            except re.error:
                if hint_phrase.lower() in phrase:
                    out[key] = value
                    break
        if key in out:
            continue
        for opt in options:
            if not opt or opt.lower() in ("other", "none / water"):
                continue
            if opt.lower() in phrase or opt.lower().replace("-", " ") in phrase:
                out[key] = opt
                break
    return out


def _get_ingredient_clarification_questions(user_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return clarification_questions only for keys we can't infer from name or from stored choices."""
    try:
        from user_ingredient_choices import get_user_ingredient_choices, get_food_token_from_item
    except ImportError:
        return []
    if not items or not user_id:
        return []
    # 4A. Build raw candidates per item.
    raw_candidates: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str((it or {}).get("name") or "").strip()
        if not name:
            continue
        token = get_food_token_from_item(it)
        if not token:
            continue
        stored = get_user_ingredient_choices(user_id, token) or {}
        if not isinstance(stored, dict):
            stored = {}
        vision_hints = (it or {}).get("ingredient_hints") or {}
        if not isinstance(vision_hints, dict):
            vision_hints = {}

        for rule in _CLARIFICATION_RULES:
            if not rule.get("pattern") or not rule.get("questions"):
                continue
            if not rule["pattern"].search(name):
                continue
            inferred = _infer_ingredient_choices_from_name(name, rule["questions"])
            for q in rule["questions"]:
                key = _normalize_dim_id(str(q.get("key") or "").strip())
                if not key or key not in DIMENSION_REGISTRY:
                    continue
                # 4B. Resolve by memory: skip only when stored value is meaningful.
                if _stored_has_meaningful_value(stored, key):
                    continue
                # 4C. Resolve by name / hint inference.
                if key in inferred:
                    continue
                if _vision_resolves_dimension(vision_hints, key):
                    continue
                label = _dim_label(key, fallback=str(q.get("label") or key))
                options = _dim_options(key, fallback=[str(o) for o in (q.get("options") or []) if str(o).strip()])
                impact = _dim_impact(key)
                raw_candidates.append(
                    {
                        "key": key,
                        "label": label,
                        "options": options,
                        "impact_kcal": impact,
                    }
                )

        # Optionally map known ingredient_hints keys into candidates when hint exists but is empty/unknown.
        for hint_key, hint_val in vision_hints.items():
            dim_id = _normalize_dim_id(str(hint_key or "").strip())
            if not dim_id or dim_id not in DIMENSION_REGISTRY:
                continue
            if _stored_has_meaningful_value(stored, dim_id):
                continue
            if _is_meaningful_stored_value(hint_val):
                # Already resolved by vision hint.
                continue
            label = _dim_label(dim_id, fallback=dim_id)
            options = _dim_options(dim_id)
            impact = _dim_impact(dim_id)
            raw_candidates.append(
                {
                    "key": dim_id,
                    "label": label,
                    "options": options,
                    "impact_kcal": impact,
                }
            )

    # 4D. Dedupe by dimension key, keeping highest impact.
    unique: Dict[str, Dict[str, Any]] = {}
    for c in raw_candidates:
        k = str(c.get("key") or "").strip()
        if not k:
            continue
        prev = unique.get(k)
        if not prev or float(c.get("impact_kcal") or 0) > float(prev.get("impact_kcal") or 0):
            unique[k] = c

    candidates = list(unique.values())
    if not candidates:
        return []

    # 4E. Rank by impact_kcal descending.
    candidates.sort(key=lambda c: float(c.get("impact_kcal") or 0), reverse=True)

    # 4F. Cap: first only if impact_kcal >= 35; second only if impact_kcal >= 45; max 2.
    selected: List[Dict[str, Any]] = []
    if candidates and float(candidates[0].get("impact_kcal") or 0) >= 35:
        selected.append(candidates[0])
    if len(candidates) > 1 and float(candidates[1].get("impact_kcal") or 0) >= 45:
        selected.append(candidates[1])

    # 4G. Public output shape unchanged.
    out: List[Dict[str, Any]] = []
    for c in selected:
        key = str(c.get("key") or "").strip()
        if not key:
            continue
        label = str(c.get("label") or key)
        options = [str(o) for o in (c.get("options") or []) if str(o).strip()]
        if not options:
            continue
        out.append(
            {
                "key": key,
                "label": label,
                "options": options,
            }
        )
    return out


def _get_llm_clarification_questions_safe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Optionally suggest 0-2 clarification questions from LLM for items that matched no rule. Fast timeout."""
    if not items or not GEMINI_API_KEY:
        return []
    names = [str((it or {}).get("name") or "").strip() for it in items[:3] if (it or {}).get("name")]
    if not names:
        return []
    prompt = (
        "Return only a JSON array of 0-2 clarification questions for better nutrition accuracy. "
        "Each element: {\"key\": \"snake_case_key\", \"label\": \"Short question?\", \"options\": [\"A\", \"B\", \"C\"]}. "
        "Only suggest when the answer is not obvious from the food name. Keys must be unique snake_case. "
        f"Detected foods: {json.dumps(names, ensure_ascii=True)}. Output JSON array only, no markdown."
    )
    try:
        text, _, _ = _call_llm_with_timeout(
            [prompt],
            model_name=COACH_LLM_MODEL,
            timeout_sec=min(3.0, _llm_timeout(limit=3.0)),
            retries=0,
            purpose="clarification_questions",
        )
        parsed = coach_logic.extract_json_object(str(text or "").strip())
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict) and x.get("key")]
        if isinstance(parsed, dict) and "questions" in parsed:
            return [x for x in (parsed.get("questions") or []) if isinstance(x, dict) and x.get("key")]
    except Exception as e:
        logger.info("llm clarification questions skipped: %s", e)
    return []


def _apply_stored_ingredient_choices_to_items(user_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich item names from stored + inferred-from-name choices for better nutrition lookup."""
    try:
        from user_ingredient_choices import get_user_ingredient_choices, get_food_token_from_item
    except ImportError:
        return items
    if not items or not user_id:
        return items
    first = items[0] if isinstance(items[0], dict) else None
    if not first:
        return items
    token = get_food_token_from_item(first)
    if not token:
        return items
    stored = get_user_ingredient_choices(user_id, token)
    name = str(first.get("name") or "").strip()
    vision_hints = (first or {}).get("ingredient_hints") or {}
    if not isinstance(vision_hints, dict):
        vision_hints = {}
    inferred: Dict[str, str] = {}
    for rule in _CLARIFICATION_RULES:
        if not rule.get("pattern") or not rule.get("questions"):
            continue
        if rule["pattern"].search(name):
            inferred = _infer_ingredient_choices_from_name(name, rule["questions"])
            break
    merged = dict(inferred)
    for k, v in (vision_hints or {}).items():
        if v is not None and str(v).strip():
            merged[k] = str(v).strip()
    if isinstance(stored, dict):
        for k, v in stored.items():
            if v is not None and str(v).strip():
                merged[k] = str(v).strip()
    if not merged:
        return items
    parts = [name]
    _skip = ("none", "no", "", "water")
    if merged.get("milk_type") and str(merged["milk_type"]).lower() not in _skip:
        parts.append(f"with {merged['milk_type'].lower()} milk")
    if merged.get("sweetener") and str(merged["sweetener"]).lower() not in _skip:
        parts.append(merged["sweetener"].lower())
    if merged.get("milk_base") and str(merged.get("milk_base", "")).lower() not in _skip:
        parts.append(f"({merged['milk_base'].lower()} base)")
    if merged.get("dressing") and str(merged["dressing"]).lower() not in _skip:
        parts.append(f"({merged['dressing'].lower()} dressing)")
    if merged.get("spread") and str(merged["spread"]).lower() not in _skip:
        parts.append(f"with {merged['spread'].lower()}")
    if merged.get("toppings") and str(merged["toppings"]).lower() not in _skip:
        parts.append(f"with {merged['toppings'].lower()}")
    if len(parts) > 1:
        first = dict(first)
        first["name"] = " ".join(parts).strip()
        return [first] + list(items[1:])
    return items


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

    if getattr(edits, "set_item_grams", None):
        target = str(edits.set_item_grams.item_id or "").strip()
        grams = max(0.0, float(_safe_float(edits.set_item_grams.grams, 0.0) or 0.0))
        if target and grams > 0:
            for it in out:
                if str(it.get("item_id") or "") == target:
                    it["grams"] = round(grams, 1)
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
    # Powder-specific top-level metadata for UI.
    powder_items = [
        it for it in (results or [])
        if isinstance(it, dict) and isinstance(it.get("_powder_meta"), dict) and it["_powder_meta"].get("is_powder_like")
    ]
    if powder_items:
        meta = powder_items[0].get("_powder_meta") or {}
        response["powder_detected"] = True
        response["powder_type_guess"] = meta.get("powder_type_guess")
        response["powder_requires_confirmation"] = bool(meta.get("needs_powder_confirmation"))
        response["powder_confirmed_type"] = meta.get("powder_type_resolved")
        response["powder_confirmed_grams"] = (powder_items[0] or {}).get("grams")
        response["nutrition_resolution_mode"] = meta.get("nutrition_source") or "supplement_table"
    else:
        response["powder_detected"] = False
        response["powder_type_guess"] = None
        response["powder_requires_confirmation"] = False
        response["powder_confirmed_type"] = None
        response["powder_confirmed_grams"] = None
        response["nutrition_resolution_mode"] = "usda"
    try:
        pk_insight = _build_protein_kcal_insight(
            totals,
            results,
            powder_detected=bool(powder_items),
        )
        if pk_insight:
            response["protein_kcal_insight"] = pk_insight
        swap_list = _build_scan_swap_suggestions(totals, coaching, results)
        if swap_list:
            response["swap_suggestions"] = swap_list
    except Exception:
        logger.warning("scan insight attachments skipped", exc_info=False)
    if item_warnings:
        response["warnings"] = item_warnings[:8]
    if plan_at_least(plan, "pro"):
        response["coaching"] = coaching
    else:
        response["locked"] = {"feature": "coaching", "required_plan": "pro"}
    return response


# -------------------- ANALYZE (PHOTO) --------------------
# Slightly smaller default to speed up scan (Issue 12); env can override.
_SCAN_MAX_IMAGE_PIXELS = int(os.getenv("SCAN_MAX_IMAGE_PIXELS", str(1024 * 1024)))
_SCAN_MAX_EDGE_PX = int(os.getenv("SCAN_MAX_EDGE_PX", "1024"))
_SCAN_JPEG_QUALITY = max(60, min(95, int(os.getenv("SCAN_JPEG_QUALITY", "85"))))


def _resize_image_for_scan(image_bytes: bytes) -> Tuple[bytes, Optional[Dict[str, int]]]:
    """Resize image to reduce Gemini payload and latency. Returns (resized_bytes, original_size)."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if w * h <= _SCAN_MAX_IMAGE_PIXELS and max(w, h) <= _SCAN_MAX_EDGE_PX:
            return image_bytes, {"w": w, "h": h}
        scale = min(1.0, (_SCAN_MAX_IMAGE_PIXELS / (w * h)) ** 0.5, _SCAN_MAX_EDGE_PX / max(w, h))
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=_SCAN_JPEG_QUALITY, optimize=True)
        return buf.getvalue(), {"w": w, "h": h}
    except Exception as e:
        logger.warning("scan image resize skipped: %s", str(e)[:120])
        return image_bytes, None


def _run_analyze_pipeline(
    *,
    user_id: str,
    image_bytes: bytes,
    tz: Optional[str] = None,
    tz_offset_min: Optional[int] = None,
    debug: bool = False,
    request_id: str = "",
    job_id: str = "",
    on_fast_result: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user_id")
    started = time.time()
    latency_ms: Dict[str, int] = {}
    _t = time.time()

    contents, _resize_info = _resize_image_for_scan(image_bytes)
    latency_ms["resize_ms"] = int(max(0, round((time.time() - _t) * 1000)))
    _t = time.time()

    calibration_settings = load_confidence_calibration_settings()
    vision_threshold = _calibration_setting_value(calibration_settings, "vision", "confidence_threshold", 0.72)
    portion_threshold = _calibration_setting_value(calibration_settings, "portion", "confidence_threshold", 0.75)
    oil_threshold = _calibration_setting_value(calibration_settings, "oil", "confidence_threshold", 0.70)
    today_local = _today_date(tz=tz, tz_offset_min=tz_offset_min)
    day_local_iso = today_local.isoformat()

    usage_row = consume_one_scan(uid, today=today_local)
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        _ = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    priors_context = _build_user_priors_context_for_candidates(uid, candidate_food_keys=[], limit=14)
    latency_ms["priors_ms"] = int(max(0, round((time.time() - _t) * 1000)))
    _t = time.time()

    vision_cache_hit = False
    vision_cache_reuse_used = False
    vision_cache_skipped_reason: Optional[str] = None
    fingerprint = compute_image_fingerprint(contents)
    cached = get_cached_vision_result(fingerprint) if fingerprint else None
    if cached and should_reuse_cached_vision_result(cached, min_confidence=vision_threshold):
        try:
            vision_scan = _coerce_vision_scan_payload(cached, vision_threshold=vision_threshold)
            vision_cache_hit = True
            vision_cache_reuse_used = True
            latency_ms["vision_ms"] = 0
        except Exception:
            vision_cache_skipped_reason = "coerce_failed"
            cached = None
    if not cached or not vision_cache_reuse_used:
        if cached and not vision_cache_reuse_used:
            vision_cache_skipped_reason = vision_cache_skipped_reason or _vision_cache_skipped_reason(
                cached, min_confidence=vision_threshold
            )
        vision_scan = gemini_vision_scan_v1(
            contents,
            personalization_context=priors_context,
            vision_threshold=vision_threshold,
            request_id=request_id,
            job_id=job_id,
        )
        latency_ms["vision_ms"] = int(max(0, round((time.time() - _t) * 1000)))
        if fingerprint:
            try:
                set_cached_vision_result(
                    fingerprint,
                    {
                        "items": [_model_dump(x) for x in (vision_scan.items or [])],
                        "top_candidates": [_model_dump(x) for x in (vision_scan.top_candidates or [])],
                        "vision_confidence": float(vision_scan.vision_confidence or 0),
                    },
                    ttl_hours=72,
                )
            except Exception:
                pass
    _t = time.time()

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
    ingredient_clarification_questions = _get_ingredient_clarification_questions(uid, detected_items)
    detected_items = _apply_stored_ingredient_choices_to_items(uid, detected_items)
    logger.info("Detected items: %s job_id=%s request_id=%s", detected_items, job_id, request_id)
    latency_ms["vision_ms"] = int(max(0, round((time.time() - _t) * 1000)))
    _t = time.time()

    results, totals, total_micros, item_warnings, nutrition_cache_stats = _compute_scan_nutrition(detected_items)
    latency_ms["nutrition_ms"] = int(max(0, round((time.time() - _t) * 1000)))
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
    analysis_id = str(uuid.uuid4())
    meal_qa_fallback = _coerce_meal_qa_payload({}, vision_scan)
    data_quality = _build_scan_data_quality(vision_scan, vision_threshold=vision_threshold)
    fast_result = _build_scan_response(
        source="photo",
        analysis_id=analysis_id,
        usage_row=usage_row,
        vision=vision_scan,
        results=results,
        totals=totals,
        micros_payload=micros_payload,
        meal_qa=meal_qa_fallback,
        plan=str(usage_row.get("plan") or DEFAULT_PLAN).lower(),
        coaching=scan_coaching,
        item_warnings=item_warnings,
        data_quality=data_quality,
    )
    for k in ("meal_id", "input_scan_id"):
        fast_result[k] = analysis_id
    fast_result["request_id"] = request_id
    fast_result["job_id"] = job_id
    fast_result["_fast_result"] = True
    fast_result["latency_breakdown_ms"] = dict(latency_ms)
    fast_result["nutrition_cache_hit_count"] = nutrition_cache_stats.get("hit_count", 0)
    fast_result["nutrition_cache_miss_count"] = nutrition_cache_stats.get("miss_count", 0)
    fast_result["vision_cache_reuse_used"] = vision_cache_reuse_used
    fast_result["vision_cache_skipped_reason"] = vision_cache_skipped_reason
    if ingredient_clarification_questions:
        fast_result["clarification_questions"] = ingredient_clarification_questions
    time_to_first_result_ms = int(max(0, round((time.time() - started) * 1000)))
    fast_result["time_to_first_result_ms"] = time_to_first_result_ms
    if on_fast_result and callable(on_fast_result):
        try:
            on_fast_result(fast_result)
        except Exception as e:
            logger.warning("on_fast_result callback failed: %s", str(e)[:120])

    _t = time.time()
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
    latency_ms["meal_qa_ms"] = int(max(0, round((time.time() - _t) * 1000)))
    _t = time.time()

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
    if ingredient_clarification_questions:
        response["clarification_questions"] = ingredient_clarification_questions
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
    latency_ms["enrichment_ms"] = int(max(0, round((time.time() - _t) * 1000)))
    response["latency_ms"] = int(max(0, round((time.time() - started) * 1000)))
    response["time_to_first_result_ms"] = time_to_first_result_ms
    response["time_to_final_result_ms"] = response["latency_ms"]
    response["latency_breakdown_ms"] = latency_ms
    response["nutrition_cache_hit_count"] = nutrition_cache_stats.get("hit_count", 0)
    response["nutrition_cache_miss_count"] = nutrition_cache_stats.get("miss_count", 0)
    response["vision_cache_reuse_used"] = vision_cache_reuse_used
    response["vision_cache_skipped_reason"] = vision_cache_skipped_reason
    response["vision_cache_hit_count"] = 1 if vision_cache_reuse_used else 0
    response["vision_cache_miss_count"] = 0 if vision_cache_reuse_used else 1
    response["image_bytes_before"] = len(image_bytes)
    response["image_bytes_after"] = len(contents)
    response["image_was_resized"] = len(contents) < len(image_bytes)
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
    progress_stage = str(row.get("stage") or row.get("progress_stage") or "").strip() or None
    out = {
        "job_id": str(row.get("id") or job_id),
        "status": status,
        "progress": _analysis_job_progress(status),
        "progress_stage": progress_stage,
        "request_id": str(row.get("request_id") or ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "error": str(row.get("error") or "") if status in {"failed", "done"} else "",
    }
    result_obj = row.get("result_json")
    if result_obj is not None:
        if isinstance(result_obj, str):
            result_obj = _parse_jsonish(result_obj, {})
        out["result"] = result_obj if isinstance(result_obj, dict) else {}
        out["result_complete"] = status == "done"
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

    items_for_nutrition = [_model_dump(x) for x in vision_scan.items]
    if getattr(req.edits, "clarifying_answers", None) and isinstance(req.edits.clarifying_answers, list):
        try:
            from user_ingredient_choices import save_user_ingredient_choices, get_food_token_from_item
        except ImportError:
            pass
        else:
            first_item = (items_for_nutrition or [{}])[0] if items_for_nutrition else None
            if first_item and isinstance(first_item, dict):
                token = get_food_token_from_item(first_item)
                if token:
                    choices_to_save = {}
                    for a in req.edits.clarifying_answers:
                        if isinstance(a, dict):
                            k = str(a.get("key") or "").strip()
                            v = str(a.get("value") or "").strip()
                            if k and v:
                                choices_to_save[k] = v
                    if choices_to_save:
                        save_user_ingredient_choices(uid, token, choices_to_save)
                        _s = ("none", "no", "", "water")
                        parts = [str(first_item.get("name") or "").strip()]
                        if choices_to_save.get("milk_type") and choices_to_save["milk_type"].lower() not in _s:
                            parts.append(f"with {choices_to_save['milk_type'].lower()} milk")
                        if choices_to_save.get("sweetener") and choices_to_save["sweetener"].lower() not in _s:
                            parts.append(choices_to_save["sweetener"].lower())
                        if choices_to_save.get("milk_base") and choices_to_save.get("milk_base", "").lower() not in _s:
                            parts.append(f"({choices_to_save['milk_base'].lower()} base)")
                        if choices_to_save.get("dressing") and choices_to_save["dressing"].lower() not in _s:
                            parts.append(f"({choices_to_save['dressing'].lower()} dressing)")
                        if choices_to_save.get("spread") and choices_to_save["spread"].lower() not in _s:
                            parts.append(f"with {choices_to_save['spread'].lower()}")
                        if choices_to_save.get("toppings") and choices_to_save["toppings"].lower() not in _s:
                            parts.append(f"with {choices_to_save['toppings'].lower()}")
                        fts = str(choices_to_save.get("frozen_treat_style") or "").strip()
                        if fts and fts.lower() not in ("regular / full-fat", "not sure", ""):
                            parts.append(f"({fts.lower()})")
                        if len(parts) > 1:
                            items_for_nutrition = [dict(first_item, name=" ".join(parts).strip())] + list(items_for_nutrition[1:])

    results, totals, total_micros, item_warnings, _ = _compute_scan_nutrition(items_for_nutrition)
    default_iid = _default_item_id_from_analysis_row(existing)
    results, totals, total_micros = _apply_macro_override_to_scan(
        results, totals, total_micros, req.edits.macro_override, default_iid
    )
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
