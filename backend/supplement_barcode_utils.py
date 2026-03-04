import re
from typing import Optional, Dict


def normalize_barcode(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"\D", "", raw)
    return cleaned if cleaned else None


def detect_gtin_type(barcode: str) -> Optional[str]:
    if len(barcode) == 12:
        return "UPC-A"
    if len(barcode) == 13:
        return "EAN-13"
    if len(barcode) == 14:
        return "GTIN-14"
    return None


def validate_ean13_checksum(barcode: str) -> bool:
    if len(barcode) != 13 or not barcode.isdigit():
        return False
    digits = [int(x) for x in barcode]
    checksum = digits[-1]
    total = sum(digits[i] if i % 2 == 0 else digits[i] * 3 for i in range(12))
    calc = (10 - (total % 10)) % 10
    return checksum == calc


def validate_upca_checksum(barcode: str) -> bool:
    if len(barcode) != 12 or not barcode.isdigit():
        return False
    digits = [int(x) for x in barcode]
    checksum = digits[-1]
    total = sum(digits[i] * 3 if i % 2 == 0 else digits[i] for i in range(11))
    calc = (10 - (total % 10)) % 10
    return checksum == calc


def validate_checksum(barcode: str) -> bool:
    t = detect_gtin_type(barcode)
    if t == "EAN-13":
        return validate_ean13_checksum(barcode)
    if t == "UPC-A":
        return validate_upca_checksum(barcode)
    return False


def extract_company_prefix(barcode: str) -> Optional[str]:
    # Simplified prefix extraction (first 6 digits for now)
    if not barcode or len(barcode) < 6:
        return None
    return barcode[:6]

