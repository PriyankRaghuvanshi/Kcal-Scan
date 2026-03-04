import re
from typing import Any, Dict, Optional

_FSSAI_LABEL_PATTERNS = [
    re.compile(r"fssai\s*(?:lic(?:ense)?\.?\s*(?:no\.?|number)?|no\.?|license\s*no\.?)", re.IGNORECASE),
    re.compile(r"lic\.?(?:ense)?\s*no\.?", re.IGNORECASE),
]

_FSSAI_NUM_PATTERNS = [
    re.compile(r"(?:fssai[^0-9]{0,24})?(\d{14})", re.IGNORECASE),
    re.compile(r"\b(\d{14})\b"),
]


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _digits_only(value: Any) -> str:
    return re.sub(r"\D+", "", _norm_text(value))


def extract_fssai_license(text: str) -> Optional[Dict[str, Any]]:
    raw = _norm_text(text)
    if not raw:
        return None

    has_label = any(p.search(raw) is not None for p in _FSSAI_LABEL_PATTERNS)

    for pattern in _FSSAI_NUM_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        number = _digits_only(m.group(1) if m.lastindex else m.group(0))
        if len(number) != 14:
            continue
        snippet_start = max(0, m.start() - 24)
        snippet_end = min(len(raw), m.end() + 24)
        snippet = raw[snippet_start:snippet_end].strip()
        return {
            "fssai_license_number": number,
            "confidence": 0.9 if has_label else 0.75,
            "method": "regex",
            "snippet": snippet,
            "fssai_label_present": has_label,
            "source_image": "back",
        }

    if has_label:
        return {
            "fssai_license_number": "",
            "confidence": 0.45,
            "method": "label_only",
            "snippet": "FSSAI label found but 14-digit license number not detected.",
            "fssai_label_present": True,
            "source_image": "back",
        }
    return None


def extract_fssai_from_structured(structured_data: dict) -> Optional[Dict[str, Any]]:
    src = structured_data if isinstance(structured_data, dict) else {}
    reg = src.get("regulatory") if isinstance(src.get("regulatory"), dict) else {}
    panel = src.get("nutrition_panel") if isinstance(src.get("nutrition_panel"), dict) else {}

    candidates = []
    for obj in (reg, panel):
        for key, value in obj.items():
            k = _norm_text(key).lower()
            if "fssai" in k or "license" in k or "lic" in k:
                candidates.append(_norm_text(value))

    for key in ("fssai_license_number", "fssai", "license_number", "manufacturer", "label_text", "raw_text", "regulatory_text"):
        if key in src:
            candidates.append(_norm_text(src.get(key)))
        if key in reg:
            candidates.append(_norm_text(reg.get(key)))
        if key in panel:
            candidates.append(_norm_text(panel.get(key)))

    merged = "\n".join([c for c in candidates if c]).strip()
    if not merged:
        return None

    found = extract_fssai_license(merged)
    if found:
        found["method"] = "structured"
        found["source_image"] = "nutrition"
    return found

