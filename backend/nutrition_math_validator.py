import re
from typing import Any, Dict, Iterable, Optional


def _to_num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    txt = str(value).strip()
    if not txt:
        return 0.0
    m = re.search(r"[-+]?\d*\.?\d+", txt)
    if not m:
        return 0.0
    try:
        return float(m.group(0))
    except Exception:
        return 0.0


def _pick(panel: Dict[str, Any], keys: Iterable[str]) -> float:
    if not isinstance(panel, dict):
        return 0.0
    for key in keys:
        if key in panel:
            val = _to_num(panel.get(key))
            if val > 0:
                return val
    return 0.0


def _extract_serving_size_g(panel: Dict[str, Any]) -> float:
    if not isinstance(panel, dict):
        return 0.0
    for key in ("serving_size_g", "serving_size", "serve_size", "serving"):
        if key in panel:
            val = _to_num(panel.get(key))
            if val > 0:
                return val
    return 0.0


def validate_nutrition_math(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    data = structured_data if isinstance(structured_data, dict) else {}
    panel = data.get("nutrition_panel") if isinstance(data.get("nutrition_panel"), dict) else {}

    serving_size_g = _extract_serving_size_g(panel)

    p_100 = _pick(panel, ["protein_per_100g", "protein_g_per_100g", "protein_per100g"])
    c_100 = _pick(panel, ["carbs_per_100g", "carbohydrate_per_100g", "carbohydrates_per_100g"])
    f_100 = _pick(panel, ["fat_per_100g", "fat_g_per_100g", "fats_per_100g"])
    kcal_100 = _pick(panel, ["kcal_per_100g", "calories_per_100g", "energy_kcal_per_100g"])

    p_srv = _pick(panel, ["protein_per_serving", "protein_g_per_serving", "protein_per_serve", "protein_g"])
    c_srv = _pick(panel, ["carbs_per_serving", "carbohydrates_per_serving", "carbs_g", "carbs"])
    f_srv = _pick(panel, ["fat_per_serving", "fat_g_per_serving", "fat_g", "fat"])
    kcal_srv = _pick(panel, ["kcal_per_serving", "calories_per_serving", "energy_kcal_per_serving", "kcal", "calories"])

    flags = []
    reasons = []

    # Prefer per-serving validation when all values are present, fallback to per-100g.
    use_serving = all(v > 0 for v in (p_srv, c_srv, f_srv, kcal_srv))
    use_100 = all(v > 0 for v in (p_100, c_100, f_100, kcal_100))

    kcal_est = 0.0
    kcal_declared = 0.0
    if use_serving:
        kcal_est = 4.0 * p_srv + 4.0 * c_srv + 9.0 * f_srv
        kcal_declared = kcal_srv
    elif use_100:
        kcal_est = 4.0 * p_100 + 4.0 * c_100 + 9.0 * f_100
        kcal_declared = kcal_100

    mismatch_pct = 0.0
    if kcal_est > 0 and kcal_declared > 0:
        mismatch_pct = abs(kcal_est - kcal_declared) / max(kcal_declared, 1.0) * 100.0
        if mismatch_pct > 15.0:
            flags.append("nutrition_kcal_mismatch")
            reasons.append("Declared calories are not consistent with macro-derived calories.")

    # Soft plausibility band for whey products.
    protein_for_plausibility = p_100
    if protein_for_plausibility <= 0 and serving_size_g > 0 and p_srv > 0:
        protein_for_plausibility = (p_srv / serving_size_g) * 100.0

    if protein_for_plausibility > 0 and (protein_for_plausibility < 35.0 or protein_for_plausibility > 95.0):
        flags.append("nutrition_protein_implausible")
        reasons.append("Protein concentration is outside common whey plausibility range.")

    serving_present = serving_size_g > 0
    if not serving_present:
        reasons.append("Serving size is missing or unclear on the panel.")

    return {
        "flags": flags,
        "kcal_estimated": round(kcal_est, 2) if kcal_est > 0 else 0.0,
        "kcal_declared": round(kcal_declared, 2) if kcal_declared > 0 else 0.0,
        "kcal_mismatch_pct": round(mismatch_pct, 2) if mismatch_pct > 0 else 0.0,
        "protein_per_100g": round(protein_for_plausibility, 2) if protein_for_plausibility > 0 else 0.0,
        "serving_size_present": bool(serving_present),
        "reasons": reasons[:4],
    }

