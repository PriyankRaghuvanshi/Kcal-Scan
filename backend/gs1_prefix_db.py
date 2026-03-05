import re
from typing import Any, Dict, Optional

# Minimal GS1 allocation ranges for Phase 2b. This is plausibility-only, not authoritative verification.
# Prefix is derived from first 3 digits of normalized GTIN where possible.
_GS1_PREFIX_RANGES = [
    # US / Canada (common UPC/EAN allocations)
    (0, 19, "US", "GS1 US", 0.82),
    (30, 39, "US", "GS1 US", 0.82),
    (60, 139, "US", "GS1 US", 0.82),
    (754, 755, "CA", "GS1 Canada", 0.82),
    # India
    (890, 890, "IN", "GS1 India", 0.9),
    # Australia
    (930, 939, "AU", "GS1 Australia", 0.88),
    # EU (selected ranges grouped as EU for region-level plausibility)
    (300, 379, "EU", "GS1 Europe", 0.68),
    (400, 440, "EU", "GS1 Europe", 0.68),
    (500, 509, "EU", "GS1 Europe", 0.68),
    (520, 529, "EU", "GS1 Europe", 0.68),
    (540, 560, "EU", "GS1 Europe", 0.68),
    (570, 579, "EU", "GS1 Europe", 0.68),
    (590, 599, "EU", "GS1 Europe", 0.68),
    (800, 839, "EU", "GS1 Europe", 0.68),
    (840, 849, "EU", "GS1 Europe", 0.68),
]


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _prefix3(gtin: str) -> Optional[int]:
    code = _digits(gtin)
    if len(code) < 12:
        return None
    # UPC-A / EAN-13 / GTIN-14 are all handled with first three digits as plausibility prefix.
    try:
        return int(code[:3])
    except Exception:
        return None


def lookup_gs1_prefix_country(gtin: Any) -> Dict[str, Any]:
    code = _digits(gtin)
    p3 = _prefix3(code)
    out: Dict[str, Any] = {
        "country_code": "",
        "org_hint": "Unknown GS1 allocation",
        "confidence": 0.0,
        "prefix": code[:3] if len(code) >= 3 else "",
    }
    if p3 is None:
        return out

    for start, end, country_code, org_hint, conf in _GS1_PREFIX_RANGES:
        if start <= p3 <= end:
            out["country_code"] = country_code
            out["org_hint"] = org_hint
            out["confidence"] = float(conf)
            return out
    return out

