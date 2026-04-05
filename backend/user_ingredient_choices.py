"""
User ingredient/clarification choices: remember answers per user and food so we ask less next time.

- Local JSON file (always): fast, works offline.
- Supabase table user_ingredient_choices when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
  are set (disable with USER_INGREDIENT_CHOICES_SUPABASE=0).

Read merge: {**file_choices, **remote_choices} (remote wins on conflict).
Write: merge into file then upsert full merged map to Supabase.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, cast

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

TBL_USER_INGREDIENT_CHOICES = "user_ingredient_choices"


def _store_path() -> Path:
    override = (os.getenv("USER_INGREDIENT_CHOICES_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "user_ingredient_choices.json"


def _normalize_token(t: str) -> str:
    return " ".join((t or "").strip().lower().split())[:128]


def component_memory_key(phrase: str) -> str:
    """
    Secondary memory bucket for a decomposed ingredient phrase (e.g. 'oatmeal', 'almond milk').
    Prefix isolates component keys from full-meal keys in storage.
    """
    tok = _normalize_token(phrase or "")
    if not tok:
        return ""
    return f"cmp::{tok[:80]}"


def _user_key(user_id: str, food_token: str) -> str:
    uid = (user_id or "").strip()
    token = _normalize_token(food_token or "")
    if not uid or not token:
        return ""
    return f"{uid}::{token}"


def _food_key_for_db(food_token: str) -> str:
    return _normalize_token(food_token or "")


def _supabase_enabled() -> bool:
    if str(os.getenv("USER_INGREDIENT_CHOICES_SUPABASE", "1") or "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    url = str(os.getenv("SUPABASE_URL") or "").strip()
    key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    return bool(url and key and requests is not None)


def _sb_headers(*, prefer: Optional[str] = None) -> Dict[str, str]:
    key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    h: Dict[str, str] = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _sb_base(table: str) -> str:
    base = str(os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_fetch_choices(user_id: str, food_key: str) -> Optional[Dict[str, str]]:
    uid = (user_id or "").strip()
    fk = (food_key or "").strip()
    if not uid or not fk:
        return None
    try:
        url = _sb_base(TBL_USER_INGREDIENT_CHOICES)
        params = {
            "user_id": f"eq.{uid}",
            "food_key": f"eq.{fk}",
            "select": "choices",
            "limit": "1",
        }
        r = cast(Any, requests).get(url, headers=_sb_headers(), params=params, timeout=15)
        if r.status_code != 200:
            logger.info(
                "user_ingredient_choices read failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:200],
            )
            return None
        rows = r.json() or []
        if not rows or not isinstance(rows[0], dict):
            return None
        raw = rows[0].get("choices")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None
        if not isinstance(raw, dict):
            return None
        return {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}
    except Exception as e:
        logger.info("user_ingredient_choices read skipped: %s", str(e)[:200])
        return None


def _sb_upsert_choices(user_id: str, food_key: str, choices: Dict[str, str]) -> None:
    uid = (user_id or "").strip()
    fk = (food_key or "").strip()
    if not uid or not fk or not choices:
        return
    row = {
        "user_id": uid,
        "food_key": fk,
        "choices": choices,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    url = _sb_base(TBL_USER_INGREDIENT_CHOICES)
    headers = _sb_headers(prefer="resolution=merge-duplicates,return=minimal")
    params = {"on_conflict": "user_id,food_key"}
    r = cast(Any, requests).post(url, headers=headers, params=params, data=json.dumps(row), timeout=20)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"upsert failed {r.status_code}: {(r.text or '')[:300]}")


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": "1", "choices": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", "1")
            data.setdefault("choices", {})
            if isinstance(data.get("choices"), dict):
                return data
    except Exception:
        pass
    return {"version": "1", "choices": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def get_food_token_from_item(item: Dict[str, Any]) -> str:
    """Derive a stable food token from an item (e.g. for coffee, smoothie)."""
    name = str((item or {}).get("name") or "").strip().lower()
    if not name:
        return ""
    return _normalize_token(name)[:80]


def get_user_ingredient_choices(user_id: str, food_token: str) -> Dict[str, str]:
    """Return stored choices for (user_id, food_token). Remote overrides file on key collision."""
    key = _user_key(user_id, food_token)
    if not key:
        return {}
    fk = _food_key_for_db(food_token)
    local: Dict[str, str] = {}
    with _LOCK:
        store = _load_store()
        choices = (store.get("choices") or {}).get(key)
        if isinstance(choices, dict):
            local = {str(k): str(v) for k, v in choices.items() if v is not None}

    if not _supabase_enabled():
        return local

    remote = _sb_fetch_choices(user_id, fk)
    if not remote:
        return local
    return {**local, **remote}


def save_user_ingredient_choices(
    user_id: str,
    food_token: str,
    choices: Dict[str, str],
) -> None:
    """Merge and save choices for (user_id, food_token); dual-write file + Supabase when configured."""
    key = _user_key(user_id, food_token)
    if not key or not isinstance(choices, dict):
        return
    fk = _food_key_for_db(food_token)
    merged = {str(k): str(v).strip() for k, v in choices.items() if v is not None and str(v).strip()}
    if not merged:
        return

    final_merged: Dict[str, str] = {}
    with _LOCK:
        store = _load_store()
        by_key = store.setdefault("choices", {})
        existing = by_key.get(key)
        if isinstance(existing, dict):
            base = {str(k): str(v) for k, v in existing.items() if v is not None}
            final_merged = {**base, **merged}
        else:
            final_merged = dict(merged)
        by_key[key] = final_merged
        _save_store(store)

    if _supabase_enabled() and fk:
        try:
            remote_existing = _sb_fetch_choices(user_id, fk) or {}
            sup_merged = {**remote_existing, **final_merged}
            _sb_upsert_choices(user_id, fk, sup_merged)
        except Exception as e:
            logger.warning("user_ingredient_choices supabase write failed: %s", str(e)[:220])


# Snapshot saved after the user applies ingredient clarifications (“we’ll remember”).
MEAL_MEMORY_LABEL = "__meal_memory_label"
MEAL_MEMORY_KCAL = "__meal_memory_kcal"
MEAL_MEMORY_PROTEIN_G = "__meal_memory_protein_g"
MEAL_MEMORY_CARBS_G = "__meal_memory_carbs_g"
MEAL_MEMORY_FAT_G = "__meal_memory_fat_g"

_MEAL_MEMORY_KEYS = frozenset(
    {
        MEAL_MEMORY_LABEL,
        MEAL_MEMORY_KCAL,
        MEAL_MEMORY_PROTEIN_G,
        MEAL_MEMORY_CARBS_G,
        MEAL_MEMORY_FAT_G,
    }
)


def is_meal_memory_key(key: str) -> bool:
    return str(key or "").strip() in _MEAL_MEMORY_KEYS


def _floatish(v: Any) -> float:
    try:
        return float(_safe_num(v))
    except Exception:
        return 0.0


def _safe_num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    return float(s)


def _trim_usual_title(name: str) -> str:
    n = " ".join(str(name or "").split()).strip()
    if len(n) > 72:
        n = n[:69] + "…"
    return n


def _meal_memory_payload_from_totals(label: str, totals: Dict[str, Any]) -> Dict[str, str]:
    lab = _trim_usual_title(label)
    if not lab:
        return {}
    kcal = _floatish((totals or {}).get("kcal"))
    if kcal <= 0:
        return {}
    return {
        MEAL_MEMORY_LABEL: lab,
        MEAL_MEMORY_KCAL: str(int(round(kcal))),
        MEAL_MEMORY_PROTEIN_G: str(round(_floatish((totals or {}).get("protein_g")), 1)),
        MEAL_MEMORY_CARBS_G: str(round(_floatish((totals or {}).get("carbs_g")), 1)),
        MEAL_MEMORY_FAT_G: str(round(_floatish((totals or {}).get("fat_g")), 1)),
    }


def _totals_close_to_memory(stored: Dict[str, str], totals: Dict[str, Any]) -> bool:
    """Loose match: same ballpark kcal (+/- ~25%) and protein when both meaningful."""
    try:
        sk = _floatish(stored.get(MEAL_MEMORY_KCAL))
        ck = _floatish((totals or {}).get("kcal"))
    except Exception:
        return False
    if sk <= 30 or ck <= 30:
        return False
    if abs(ck - sk) / max(sk, 1.0) > 0.26:
        return False
    sp = _floatish(stored.get(MEAL_MEMORY_PROTEIN_G))
    cp = _floatish((totals or {}).get("protein_g"))
    if sp >= 8.0 and cp >= 8.0:
        if abs(cp - sp) / max(sp, 1.0) > 0.34:
            return False
    return True


def usual_meal_anchor_tokens(name: str) -> List[str]:
    """Longest phrases first so we prefer specific keys over short roots."""
    try:
        from meal_accuracy_decompose import clarification_phrases_for_item_name
    except ImportError:
        phrases: List[str] = []
    else:
        phrases = clarification_phrases_for_item_name(name)
    out: List[str] = []
    seen: set[str] = set()
    for p in phrases:
        t = _normalize_token(p)[:80]
        if len(t) < 4:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    out.sort(key=len, reverse=True)
    return out[:10]


def save_usual_meal_memory_for_label(user_id: str, meal_item_label: str, totals: Dict[str, Any]) -> None:
    """
    Persist usual-meal snapshot under several normalized phrase keys so wording variants still match.
    Merges only meal-memory keys; clarification dimensions on the same row stay intact.
    """
    uid = (user_id or "").strip()
    raw_name = str(meal_item_label or "").strip()
    if not uid or not raw_name:
        return
    mem = _meal_memory_payload_from_totals(raw_name, totals)
    if not mem:
        return
    for tok in usual_meal_anchor_tokens(raw_name):
        save_user_ingredient_choices(uid, tok, dict(mem))


def find_usual_meal_hint(user_id: str, first_item_name: str, totals: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    If stored usual snapshot matches current totals, return a short line for the client.
    """
    uid = (user_id or "").strip()
    name = str(first_item_name or "").strip()
    if not uid or not name:
        return None
    for tok in usual_meal_anchor_tokens(name):
        stored = get_user_ingredient_choices(uid, tok) or {}
        if not isinstance(stored, dict):
            continue
        label = str(stored.get(MEAL_MEMORY_LABEL) or "").strip()
        if not label:
            continue
        if not _totals_close_to_memory(stored, totals):
            continue
        line = (
            f"This looks like your usual {label} — similar kcal and macros to what you confirmed before."
        )
        return {"label": label, "line": line, "matched_food_key": tok}
    return None
