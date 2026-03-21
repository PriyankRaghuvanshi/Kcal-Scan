from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chain_baseline_snapshots import load_chain_baseline_snapshot, write_chain_baseline_snapshot
from chain_rollout_registry import get_chain_runtime_config, load_chain_rollout_registry
from local_venue_enrichment import enrich_place_with_local_profile


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _normalize_chain_key(v: Any) -> str:
    return _safe_text(v).lower().replace(" ", "_")


def _normalize_market(v: Any) -> str:
    out = _safe_text(v).upper()
    return out if out in {"AU", "IN", "US"} else ""


def _fixtures_file() -> Path:
    return Path(__file__).resolve().parent / "data" / "chain_baseline_fixtures.json"


def load_baseline_fixtures() -> Dict[str, Any]:
    path = _fixtures_file()
    if not path.exists():
        return {"version": "v1", "fixtures": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": "v1", "fixtures": []}
    if not isinstance(data, dict):
        return {"version": "v1", "fixtures": []}
    fixtures = data.get("fixtures") if isinstance(data.get("fixtures"), list) else []
    return {"version": _safe_text(data.get("version") or "v1"), "fixtures": fixtures}


def _place_from_fixture(chain_key: str, market: str, fixture: Dict[str, Any]) -> Dict[str, Any]:
    place_name = _safe_text(fixture.get("place_name") or chain_key.replace("_", " ").title())
    place_id = _safe_text(fixture.get("place_id") or f"baseline::{chain_key}::{market}".lower())
    vicinity = _safe_text(fixture.get("vicinity") or ("India" if market == "IN" else ("Australia" if market == "AU" else "USA")))
    return {
        "place_id": place_id,
        "place_name": place_name,
        "name": place_name,
        "vicinity": vicinity,
        "country_code": market,
    }


def _pick_fixtures_for_chain(chain_key: str, market: str) -> List[Dict[str, Any]]:
    loaded = load_baseline_fixtures().get("fixtures") or []
    out: List[Dict[str, Any]] = []
    for raw in loaded:
        if not isinstance(raw, dict):
            continue
        ck = _normalize_chain_key(raw.get("chain_key"))
        mk = _normalize_market(raw.get("market"))
        if ck == chain_key and mk == market:
            out.append(raw)
    return out


def _extract_top_item_names(enriched: Dict[str, Any], limit: int = 3) -> List[str]:
    names: List[str] = []
    items = enriched.get("top_menu_items") if isinstance(enriched.get("top_menu_items"), list) else []
    for item in items[: max(1, min(10, limit))]:
        if not isinstance(item, dict):
            continue
        n = _safe_text(item.get("item_name"))
        if n:
            names.append(n)
    return names


def _extract_top_item_scores(enriched: Dict[str, Any], limit: int = 3) -> List[float]:
    scores: List[float] = []
    items = enriched.get("top_menu_items") if isinstance(enriched.get("top_menu_items"), list) else []
    for item in items[: max(1, min(10, limit))]:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        if score is None:
            score = item.get("fat_loss_fit_score")
        scores.append(round(_safe_float(score, 0.0), 4))
    return scores


def _extract_totals_proxy(enriched: Dict[str, Any]) -> Dict[str, float]:
    top = enriched.get("top_menu_item") if isinstance(enriched.get("top_menu_item"), dict) else {}
    kcal = _safe_float(top.get("estimated_calories"), 0.0)
    if kcal <= 0:
        kcal = _safe_float(top.get("calories"), 0.0)
    protein = _safe_float(top.get("estimated_protein_g"), 0.0)
    if protein <= 0:
        protein = _safe_float(top.get("protein_g"), 0.0)
    return {
        "kcal": round(kcal, 2),
        "protein_g": round(protein, 2),
        "carbs_g": 0.0,
        "fat_g": 0.0,
    }


def _build_case_output(enriched: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = enriched if isinstance(enriched, dict) else {}
    return {
        "matched_chain_key": _safe_text(payload.get("matched_chain_key")),
        "chain_menu_store": _safe_text(payload.get("chain_menu_store")),
        "top_item_names": _extract_top_item_names(payload, limit=3),
        "top_item_scores": _extract_top_item_scores(payload, limit=3),
        "trust_tiers": {},
        "fallback_mode_used": _safe_text(payload.get("chain_fallback_mode") or "unknown"),
        "totals": _extract_totals_proxy(payload),
        "no_result": not bool(payload),
    }


def list_stable_registry_chains() -> List[Dict[str, Any]]:
    reg = load_chain_rollout_registry(force_reload=False)
    rows = reg.get("chains") if isinstance(reg.get("chains"), list) else []
    stable: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _safe_text(row.get("status")).lower() != "stable":
            continue
        chain_key = _normalize_chain_key(row.get("chain_key"))
        market = _normalize_market(row.get("market"))
        if chain_key and market:
            stable.append({"chain_key": chain_key, "market": market, "registry_version": int(row.get("registry_version") or 1)})
    return stable


def generate_baseline_for_chain(chain_key: str, market: str, registry_version: int) -> Dict[str, Any]:
    fixtures = _pick_fixtures_for_chain(chain_key, market)
    if not fixtures:
        fixtures = [{"chain_key": chain_key, "market": market, "case_id": f"default_{chain_key}_{market}", "place_name": chain_key.replace("_", " ").title()}]

    runtime = get_chain_runtime_config(chain_key, market)
    cases: List[Dict[str, Any]] = []
    for idx, fixture in enumerate(fixtures):
        place = _place_from_fixture(chain_key, market, fixture)
        enriched = enrich_place_with_local_profile(place, market_tag=market)
        case_id = _safe_text(fixture.get("case_id") or f"{chain_key}_{market}_{idx + 1}")
        cases.append(
            {
                "case_id": case_id,
                "input_signature": {
                    "restaurant_name": _safe_text(place.get("name")),
                    "market": market,
                },
                "outputs": _build_case_output(enriched),
            }
        )

    payload = {
        "snapshot_id": _safe_text(runtime.get("baseline_snapshot_id") or f"snap_{chain_key}_{market.lower()}_v{registry_version}"),
        "chain_key": chain_key,
        "market": market,
        "registry_version": int(registry_version),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fixture_version": _safe_text(load_baseline_fixtures().get("version") or "v1"),
        "generator": {
            "module": "chain_baseline_runner",
            "schema_version": "v1",
        },
        "cases": cases,
    }
    write_chain_baseline_snapshot(chain_key, market, registry_version, payload)
    return payload


def _kcal_macro_drift(baseline_totals: Dict[str, Any], current_totals: Dict[str, Any]) -> Tuple[float, float]:
    b_kcal = _safe_float((baseline_totals or {}).get("kcal"), 0.0)
    c_kcal = _safe_float((current_totals or {}).get("kcal"), 0.0)
    b_protein = _safe_float((baseline_totals or {}).get("protein_g"), 0.0)
    c_protein = _safe_float((current_totals or {}).get("protein_g"), 0.0)
    return abs(c_kcal - b_kcal), abs(c_protein - b_protein)


def diff_chain_against_baseline(chain_key: str, market: str, registry_version: int) -> Dict[str, Any]:
    baseline = load_chain_baseline_snapshot(chain_key, market, registry_version)
    if not baseline:
        return {
            "chain_key": chain_key,
            "market": market,
            "registry_version": registry_version,
            "has_baseline": False,
            "metrics": {},
            "failed_guardrails": ["missing_baseline"],
            "ok": False,
        }

    baseline_cases = baseline.get("cases") if isinstance(baseline.get("cases"), list) else []
    fixtures = _pick_fixtures_for_chain(chain_key, market)
    fixture_by_case = { _safe_text(f.get("case_id")): f for f in fixtures if isinstance(f, dict) and _safe_text(f.get("case_id")) }

    total_cases = 0
    top1_name_changed = 0
    top3_overlap_fail = 0
    no_result_rate_baseline = 0
    no_result_rate_current = 0
    fallback_mode_changed = 0
    kcal_drift_max = 0.0
    protein_drift_max = 0.0

    for case in baseline_cases:
        if not isinstance(case, dict):
            continue
        total_cases += 1
        case_id = _safe_text(case.get("case_id"))
        fixture = fixture_by_case.get(case_id) or {
            "place_name": ((case.get("input_signature") or {}).get("restaurant_name") if isinstance(case.get("input_signature"), dict) else ""),
            "case_id": case_id,
        }
        place = _place_from_fixture(chain_key, market, fixture)
        current = _build_case_output(enrich_place_with_local_profile(place, market_tag=market))
        base_outputs = case.get("outputs") if isinstance(case.get("outputs"), dict) else {}

        base_top = (base_outputs.get("top_item_names") or [""])[:1]
        curr_top = (current.get("top_item_names") or [""])[:1]
        if _safe_text(base_top[0] if base_top else "") != _safe_text(curr_top[0] if curr_top else ""):
            top1_name_changed += 1

        base_top3 = set([_safe_text(x) for x in (base_outputs.get("top_item_names") or [])[:3] if _safe_text(x)])
        curr_top3 = set([_safe_text(x) for x in (current.get("top_item_names") or [])[:3] if _safe_text(x)])
        if base_top3 and not (base_top3 & curr_top3):
            top3_overlap_fail += 1

        if bool(base_outputs.get("no_result")):
            no_result_rate_baseline += 1
        if bool(current.get("no_result")):
            no_result_rate_current += 1

        if _safe_text(base_outputs.get("fallback_mode_used")) != _safe_text(current.get("fallback_mode_used")):
            fallback_mode_changed += 1

        kcal_drift, protein_drift = _kcal_macro_drift(base_outputs.get("totals") or {}, current.get("totals") or {})
        kcal_drift_max = max(kcal_drift_max, kcal_drift)
        protein_drift_max = max(protein_drift_max, protein_drift)

    denom = max(1, total_cases)
    metrics = {
        "cases_total": total_cases,
        "top1_name_change_rate": round(top1_name_changed / denom, 4),
        "top3_overlap_fail_rate": round(top3_overlap_fail / denom, 4),
        "fallback_mode_change_rate": round(fallback_mode_changed / denom, 4),
        "no_result_rate_baseline": round(no_result_rate_baseline / denom, 4),
        "no_result_rate_current": round(no_result_rate_current / denom, 4),
        "no_result_rate_delta": round((no_result_rate_current - no_result_rate_baseline) / denom, 4),
        "kcal_drift_max_abs": round(kcal_drift_max, 2),
        "protein_drift_max_abs": round(protein_drift_max, 2),
    }

    failed_guardrails: List[str] = []
    if metrics["top1_name_change_rate"] > 0.2:
        failed_guardrails.append("top1_name_change_rate")
    if metrics["top3_overlap_fail_rate"] > 0.1:
        failed_guardrails.append("top3_overlap_fail_rate")
    if metrics["fallback_mode_change_rate"] > 0.05:
        failed_guardrails.append("fallback_mode_change_rate")
    if metrics["no_result_rate_delta"] > 0.02:
        failed_guardrails.append("no_result_rate_delta")
    if metrics["kcal_drift_max_abs"] > 80.0:
        failed_guardrails.append("kcal_drift_max_abs")
    if metrics["protein_drift_max_abs"] > 8.0:
        failed_guardrails.append("protein_drift_max_abs")

    return {
        "chain_key": chain_key,
        "market": market,
        "registry_version": registry_version,
        "has_baseline": True,
        "metrics": metrics,
        "failed_guardrails": failed_guardrails,
        "ok": not bool(failed_guardrails),
    }

