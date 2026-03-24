"""
Post-scan recipe suggestions: Spoonacular (real recipes + nutrition) when API key is set;
otherwise Gemini structured suggestions (clearly labeled as estimates).
File-backed user prefs for personalization (saved / dismissed / cuisine affinity).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import random
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

SPOONACULAR_BASE = "https://api.spoonacular.com/recipes/complexSearch"
# Free public recipe index (no API key). https://www.themealdb.com/api.php
THEMEALDB_API_BASE = "https://www.themealdb.com/api/json/v1/1"


def _store_path() -> Path:
    override = (os.getenv("USER_RECIPE_PREFS_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "user_recipe_prefs.json"


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": "1", "users": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", "1")
            data.setdefault("users", {})
            if isinstance(data.get("users"), dict):
                return data
    except Exception:
        pass
    return {"version": "1", "users": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def get_user_recipe_prefs(user_id: str) -> Dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {}
    with _LOCK:
        store = _load_store()
    u = (store.get("users") or {}).get(uid)
    if isinstance(u, dict):
        return dict(u)
    return {
        "saved_recipe_keys": [],
        "dismissed_keys": [],
        "cuisine_affinity": {},
        "meal_tags": {},
        "saved_recipe_snapshots": {},
        "recipe_suggest_usage": {"day": "", "count": 0},
    }


def _utc_day_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _default_user_bucket() -> Dict[str, Any]:
    return {
        "saved_recipe_keys": [],
        "dismissed_keys": [],
        "cuisine_affinity": {},
        "meal_tags": {},
        "saved_recipe_snapshots": {},
        "recipe_suggest_usage": {"day": "", "count": 0},
    }


def _recipe_plan_unlimited(plan: str) -> bool:
    p = (plan or "free").strip().lower()
    return p in ("pro", "infinite")


def _free_daily_suggest_limit() -> int:
    try:
        return max(1, int(os.getenv("RECIPE_SUGGEST_FREE_DAILY_LIMIT", "5")))
    except Exception:
        return 5


def _recipe_rate_limit_read(user_id: str) -> Tuple[int, int, int]:
    """Returns (used_today, limit, remaining)."""
    limit = _free_daily_suggest_limit()
    with _LOCK:
        store = _load_store()
        users = store.setdefault("users", {})
        u = users.setdefault(user_id, _default_user_bucket())
        usage = u.get("recipe_suggest_usage")
        if not isinstance(usage, dict):
            usage = {"day": "", "count": 0}
        day = _utc_day_iso()
        if str(usage.get("day") or "") != day:
            used = 0
        else:
            used = int(usage.get("count") or 0)
        rem = max(0, limit - used)
        return used, limit, rem


def _recipe_rate_limit_commit(user_id: str) -> None:
    """Increment successful suggest count for free-tier users (call after generating suggestions)."""
    day = _utc_day_iso()
    with _LOCK:
        store = _load_store()
        users = store.setdefault("users", {})
        u = users.setdefault(user_id, _default_user_bucket())
        usage = u.get("recipe_suggest_usage")
        if not isinstance(usage, dict):
            usage = {"day": "", "count": 0}
        if str(usage.get("day") or "") != day:
            usage = {"day": day, "count": 0}
        usage["count"] = int(usage.get("count") or 0) + 1
        usage["day"] = day
        u["recipe_suggest_usage"] = usage
        users[user_id] = u
        _save_store(store)


def list_saved_recipes(user_id: str) -> Dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {"recipes": [], "count": 0}
    prefs = get_user_recipe_prefs(uid)
    keys: List[str] = [str(x) for x in (prefs.get("saved_recipe_keys") or []) if x]
    snaps = prefs.get("saved_recipe_snapshots")
    if not isinstance(snaps, dict):
        snaps = {}
    out: List[Dict[str, Any]] = []
    for k in keys:
        snap = snaps.get(k)
        if isinstance(snap, dict) and str(snap.get("title") or "").strip():
            row = dict(snap)
            row["recipe_key"] = k
            out.append(row)
        else:
            out.append({"recipe_key": k, "title": str(k), "missing_detail": True})
    return {"recipes": out, "count": len(out)}


def record_recipe_feedback(
    user_id: str,
    recipe_key: str,
    action: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    uid = (user_id or "").strip()
    key = (recipe_key or "").strip()
    act = (action or "").strip().lower()
    if not uid or not key:
        return {"ok": False, "error": "missing_user_or_recipe_key"}
    allowed = {"save", "unsave", "dismiss", "open", "more_like"}
    if act not in allowed:
        return {"ok": False, "error": "invalid_action"}

    meta = meta if isinstance(meta, dict) else {}
    with _LOCK:
        store = _load_store()
        users = store.setdefault("users", {})
        u = users.setdefault(uid, _default_user_bucket())
        saved: List[str] = list(u.get("saved_recipe_keys") or [])
        dismissed: List[str] = list(u.get("dismissed_keys") or [])
        cuisines: Dict[str, int] = dict(u.get("cuisine_affinity") or {})
        tags: Dict[str, int] = dict(u.get("meal_tags") or {})
        snaps: Dict[str, Any] = dict(u.get("saved_recipe_snapshots") or {}) if isinstance(u.get("saved_recipe_snapshots"), dict) else {}

        if act == "dismiss":
            if key not in dismissed:
                dismissed.append(key)
            u["dismissed_keys"] = dismissed[-300:]
        elif act == "save":
            if key not in saved:
                saved.insert(0, key)
            u["saved_recipe_keys"] = saved[:120]
            rs = meta.get("recipe_snapshot")
            if isinstance(rs, dict):
                title = str(rs.get("title") or "").strip()
                if title:
                    snaps[key] = {
                        "title": title[:200],
                        "source_url": str(rs.get("source_url") or "")[:900],
                        "image_url": str(rs.get("image_url") or "")[:900],
                        "est_kcal_per_serving": rs.get("est_kcal_per_serving"),
                        "est_protein_g_per_serving": rs.get("est_protein_g_per_serving"),
                        "source": str(rs.get("source") or "")[:40],
                        "cuisines": rs.get("cuisines") if isinstance(rs.get("cuisines"), list) else [],
                        "why_similar": str(rs.get("why_similar") or "")[:320],
                        "saved_at": str(rs.get("saved_at") or "").strip() or _utc_now_iso(),
                    }
            u["saved_recipe_snapshots"] = snaps
            c = str(meta.get("cuisine") or "").strip().lower()
            if c:
                cuisines[c] = int(cuisines.get(c, 0)) + 2
        elif act == "unsave":
            u["saved_recipe_keys"] = [x for x in saved if x != key]
            if key in snaps:
                del snaps[key]
            u["saved_recipe_snapshots"] = snaps
        elif act == "open":
            c = str(meta.get("cuisine") or "").strip().lower()
            if c:
                cuisines[c] = int(cuisines.get(c, 0)) + 1
        elif act == "more_like":
            c = str(meta.get("cuisine") or "").strip().lower()
            t = str(meta.get("meal_tag") or "").strip().lower()
            if c:
                cuisines[c] = int(cuisines.get(c, 0)) + 3
            if t:
                tags[t] = int(tags.get(t, 0)) + 2

        u["cuisine_affinity"] = cuisines
        u["meal_tags"] = tags
        users[uid] = u
        _save_store(store)
    return {"ok": True}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _meal_totals(meal: Dict[str, Any]) -> Tuple[float, float]:
    tot = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
    kcal = _safe_float(meal.get("total_kcal") or tot.get("kcal") or tot.get("total_kcal"), 0.0)
    p = _safe_float(tot.get("protein_g"), 0.0)
    return kcal, p


def _extract_search_query(meal: Dict[str, Any]) -> str:
    parts: List[str] = []
    for c in (meal.get("top_candidates") or [])[:2]:
        if isinstance(c, dict) and c.get("label"):
            parts.append(str(c["label"]))
    for it in (meal.get("items") or [])[:5]:
        if isinstance(it, dict) and it.get("name"):
            parts.append(str(it["name"]))
    q = " ".join(parts).strip()
    q = re.sub(r"\s+", " ", q)[:140]
    if len(q) < 3:
        return "high protein dinner"
    return q


def _recipe_key_spoonacular(rid: int) -> str:
    return f"spoon:{rid}"


def _themealdb_enabled() -> bool:
    v = (os.getenv("THEMEALDB_DISABLED") or "").strip().lower()
    return v not in ("1", "true", "yes", "on")


def _themealdb_normalize_query(query: str) -> str:
    raw = re.sub(r"\s+", " ", (query or "").strip())
    if len(raw) < 2:
        return "chicken"
    if len(raw) > 48:
        raw = " ".join(raw.split()[:4])
    return raw


def _themealdb_meal_page_url(id_meal: str) -> str:
    mid = (id_meal or "").strip()
    if not mid:
        return "https://www.themealdb.com/"
    return f"https://www.themealdb.com/meal/{mid}"


def _themealdb_search(query: str) -> List[Dict[str, Any]]:
    """Free catalog: TheMealDB (no key). No per-serving macros in API — links + images only."""
    q = _themealdb_normalize_query(query)
    meals_raw: List[Dict[str, Any]] = []

    attempts: List[Dict[str, str]] = [{"s": q}]
    parts = q.split()
    if len(parts) > 1:
        attempts.append({"s": parts[0]})

    for params in attempts:
        try:
            r = requests.get(f"{THEMEALDB_API_BASE}/search.php", params=params, timeout=12)
            if not r.ok:
                continue
            data = r.json()
            m = data.get("meals")
            if isinstance(m, list) and m:
                meals_raw = m
                break
        except Exception as e:
            logger.warning("themealdb search failed: %s", e)

    if not meals_raw and parts:
        ing = re.sub(r"[^a-zA-Z ]+", "", parts[0]).strip().lower() or "chicken"
        try:
            r = requests.get(f"{THEMEALDB_API_BASE}/filter.php", params={"i": ing}, timeout=12)
            if r.ok:
                data = r.json()
                m = data.get("meals")
                if isinstance(m, list) and m:
                    meals_raw = m[:18]
        except Exception as e:
            logger.warning("themealdb filter failed: %s", e)

    out: List[Dict[str, Any]] = []
    for rec in meals_raw[:18]:
        if not isinstance(rec, dict):
            continue
        mid = str(rec.get("idMeal") or "").strip()
        title = str(rec.get("strMeal") or "").strip()
        if not mid or not title:
            continue
        img = str(rec.get("strMealThumb") or "").strip()
        src = str(rec.get("strSource") or "").strip()
        yt = str(rec.get("strYoutube") or "").strip()
        area = str(rec.get("strArea") or "").strip()
        url = src or yt or _themealdb_meal_page_url(mid)
        cuisines = [area] if area else []
        out.append(
            {
                "recipe_key": f"meal:{mid}",
                "title": title,
                "image_url": img,
                "source_url": url,
                "est_protein_g_per_serving": None,
                "est_kcal_per_serving": None,
                "cuisines": cuisines,
                "why_similar": "From TheMealDB’s free recipe index — similar ingredients or regional style.",
                "source": "themealdb",
            }
        )
    return out


def _parse_spoonacular_nutrients(recipe: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    nut = recipe.get("nutrition")
    if not isinstance(nut, dict):
        return None, None
    nutrients = nut.get("nutrients")
    if not isinstance(nutrients, list):
        return None, None
    protein = None
    kcal = None
    for n in nutrients:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name") or "").lower()
        amt = _safe_float(n.get("amount"), 0.0)
        if name == "protein":
            protein = amt
        if name in ("calories", "calorie"):
            kcal = amt
    return protein, kcal


def _spoonacular_diet_param(diet_style: str) -> Optional[str]:
    d = (diet_style or "").strip().lower()
    if d == "vegan":
        return "vegan"
    if d == "veg":
        return "vegetarian"
    return None


def _spoonacular_search(
    query: str,
    diet_style: str,
    meal_kcal: float,
    meal_protein: float,
    api_key: str,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "apiKey": api_key,
        "query": query or "high protein",
        "number": 15,
        "addRecipeInformation": True,
        "sort": "protein",
        "sortDirection": "desc",
    }
    dp = _spoonacular_diet_param(diet_style)
    if dp:
        params["diet"] = dp
    # Per-serving macro bands loosely aligned to the scanned meal (variety, not clones).
    if meal_protein > 5:
        params["minProtein"] = max(12.0, min(55.0, round(meal_protein * 0.45)))
    else:
        params["minProtein"] = 18.0
    if meal_kcal > 120:
        params["maxCalories"] = int(min(1200, max(380, round(meal_kcal * 1.35))))
    else:
        params["maxCalories"] = 750

    try:
        r = requests.get(SPOONACULAR_BASE, params=params, timeout=14)
        if not r.ok:
            logger.warning("spoonacular complexSearch http %s", r.status_code)
            return []
        data = r.json()
    except Exception as e:
        logger.warning("spoonacular request failed: %s", e)
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    out: List[Dict[str, Any]] = []
    for rec in results:
        if not isinstance(rec, dict):
            continue
        rid = rec.get("id")
        if rid is None:
            continue
        title = str(rec.get("title") or "").strip()
        if not title:
            continue
        img = str(rec.get("image") or "").strip()
        src = str(rec.get("sourceUrl") or rec.get("spoonacularSourceUrl") or "").strip()
        p_g, kcal = _parse_spoonacular_nutrients(rec)
        cuisines = rec.get("cuisines")
        cuisine_list = [str(x).strip() for x in cuisines if str(x).strip()] if isinstance(cuisines, list) else []
        out.append(
            {
                "recipe_key": _recipe_key_spoonacular(int(rid)),
                "title": title,
                "image_url": img,
                "source_url": src or f"https://spoonacular.com/recipes/{title.replace(' ', '-').lower()}-{rid}",
                "est_protein_g_per_serving": round(p_g, 1) if p_g is not None else None,
                "est_kcal_per_serving": int(round(kcal)) if kcal is not None else None,
                "cuisines": cuisine_list[:4],
                "why_similar": "Picked for high protein in a similar calorie band to your meal.",
                "source": "spoonacular",
            }
        )
    return out


def _rank_recipes(
    recipes: List[Dict[str, Any]],
    prefs: Dict[str, Any],
    dismissed: set,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    aff = prefs.get("cuisine_affinity") if isinstance(prefs.get("cuisine_affinity"), dict) else {}
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for rec in recipes:
        rk = str(rec.get("recipe_key") or "")
        if rk in dismissed:
            continue
        c_list = rec.get("cuisines") if isinstance(rec.get("cuisines"), list) else []
        boost = 0.0
        for c in c_list:
            cl = str(c).strip().lower()
            boost += 0.12 * float(aff.get(cl, 0))
        scored.append((boost + random.random() * 0.08, rec))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored[:limit]]


def _llm_recipe_suggestions(
    meal: Dict[str, Any],
    prefs: Dict[str, Any],
    model_name: str,
) -> Tuple[List[Dict[str, Any]], str]:
    import google.generativeai as genai
    import coach_daily_logic as coach_logic

    q = _extract_search_query(meal)
    kcal, prot = _meal_totals(meal)
    aff = prefs.get("cuisine_affinity") if isinstance(prefs.get("cuisine_affinity"), dict) else {}
    top_cuis = sorted(aff.items(), key=lambda x: -x[1])[:6]
    aff_s = ", ".join(f"{k} ({v})" for k, v in top_cuis) or "none yet"

    prompt = f"""You are a nutrition coach. The user logged a meal (photo scan). Suggest 4 DISTINCT home-cooked recipe ideas that feel like a similar *style* but add variety (not the same dish).

Meal search context: {q}
Approx meal totals: {round(kcal)} kcal, {round(prot, 1)}g protein.
User cuisine affinity (from past saves/opens): {aff_s}

Rules:
- Respect common diet patterns if implied by ingredients (e.g. vegetarian if no meat in items); still be creative.
- Each recipe must include realistic estimated per-serving protein and calories (rough estimates).
- "why_similar" is one short sentence tying to their logged meal.
- No brand names. No medical claims.

Return ONLY valid JSON:
{{"recipes":[{{"title":"","cuisine":"","est_kcal_per_serving":0,"est_protein_g_per_serving":0,"why_similar":"","short_idea":""}}]}}
"""
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": 0.55, "max_output_tokens": 1200},
    )
    text = str(resp.text or "").strip()
    parsed = coach_logic.extract_json_object(text)
    if not isinstance(parsed, dict):
        return [], "parse_failed"
    arr = parsed.get("recipes")
    if not isinstance(arr, list):
        return [], "no_recipes_array"
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(arr[:6]):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        h = hashlib.sha256(title.lower().encode("utf-8")).hexdigest()[:14]
        cuisine = str(raw.get("cuisine") or "").strip()
        out.append(
            {
                "recipe_key": f"llm:{h}:{i}",
                "title": title,
                "image_url": "",
                "source_url": "",
                "est_protein_g_per_serving": round(_safe_float(raw.get("est_protein_g_per_serving"), 0.0), 1),
                "est_kcal_per_serving": int(round(_safe_float(raw.get("est_kcal_per_serving"), 0.0))),
                "cuisines": [cuisine] if cuisine else [],
                "why_similar": str(raw.get("why_similar") or "").strip()[:220],
                "short_idea": str(raw.get("short_idea") or "").strip()[:180],
                "source": "llm",
            }
        )
    return out, "ok"


def build_recipe_suggest_response(
    user_id: str,
    meal: Dict[str, Any],
    diet_style: str,
    goal_type: str,
    gemini_api_key: str,
    gemini_model: str,
    spoonacular_key: str,
    plan: str = "free",
) -> Dict[str, Any]:
    uid = (user_id or "").strip()
    used, limit, remaining = _recipe_rate_limit_read(uid)
    if not _recipe_plan_unlimited(plan):
        if remaining <= 0:
            return {
                "source": "rate_limited",
                "goal_type": goal_type,
                "query_used": "",
                "recipes": [],
                "disclaimer": (
                    f"You've used your {limit} free recipe suggestion runs today. "
                    "Upgrade to Pro for unlimited ideas, or try again tomorrow."
                ),
                "rate_limited": True,
                "used_today": used,
                "free_daily_limit": limit,
                "personalization": {},
            }

    prefs = get_user_recipe_prefs(uid)
    dismissed = set(str(x) for x in (prefs.get("dismissed_keys") or []) if x)
    meal_kcal, meal_p = _meal_totals(meal if isinstance(meal, dict) else {})
    query = _extract_search_query(meal if isinstance(meal, dict) else {})

    recipes: List[Dict[str, Any]] = []
    source = "none"
    if spoonacular_key:
        recipes = _spoonacular_search(query, diet_style, meal_kcal, meal_p, spoonacular_key)
        if recipes:
            source = "spoonacular"
    if not recipes and _themealdb_enabled():
        recipes = _themealdb_search(query)
        if recipes:
            source = "themealdb"
    if not recipes and gemini_api_key:
        try:
            llm_list, _reason = _llm_recipe_suggestions(meal if isinstance(meal, dict) else {}, prefs, gemini_model)
            recipes = llm_list
            if recipes:
                source = "llm"
        except Exception as e:
            logger.warning("recipe llm fallback failed: %s", e)

    recipes = _rank_recipes(recipes, prefs, dismissed, limit=5)

    if recipes and not _recipe_plan_unlimited(plan):
        _recipe_rate_limit_commit(uid)

    disclaimer = ""
    if source == "llm":
        disclaimer = "These ideas are AI-generated; macros are estimates—verify before logging."
    elif source == "spoonacular":
        disclaimer = "Nutrition comes from Spoonacular; verify portions before logging."
    elif source == "themealdb":
        disclaimer = "Recipes from TheMealDB (free catalog, no paid API). Per-serving macros aren’t provided—verify before logging."
    else:
        disclaimer = "Recipe suggestions unavailable right now."

    return {
        "source": source,
        "goal_type": goal_type,
        "query_used": query[:160],
        "recipes": recipes,
        "disclaimer": disclaimer,
        "rate_limited": False,
        "used_today": used,
        "free_daily_limit": limit,
        "personalization": {
            "cuisine_affinity_top": sorted(
                (prefs.get("cuisine_affinity") or {}).items(), key=lambda x: -x[1]
            )[:8],
        },
    }
