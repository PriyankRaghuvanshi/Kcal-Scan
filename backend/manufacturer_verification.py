import re
import time
from typing import Any, Dict, Optional

import requests


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


class ManufacturerVerifier:
    def verify_gtin(self, gtin: str, region: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError


class UnavailableManufacturerVerifier(ManufacturerVerifier):
    def __init__(self, provider: str = "none"):
        self.provider = str(provider or "none").strip().lower()

    def verify_gtin(self, gtin: str, region: Optional[str] = None) -> Dict[str, Any]:
        return {
            "status": "unavailable",
            "company_name": "",
            "source": self.provider or "none",
            "latency_ms": 0,
            "raw": {"reason": "provider_disabled"},
        }


class GS1LicensedManufacturerVerifier(ManufacturerVerifier):
    """
    Placeholder adapter for a future licensed GS1/commercial integration.
    """

    def __init__(self, timeout_sec: float = 5.0):
        self.timeout_sec = float(timeout_sec)

    def verify_gtin(self, gtin: str, region: Optional[str] = None) -> Dict[str, Any]:
        return {
            "status": "unavailable",
            "company_name": "",
            "source": "gs1_licensed",
            "latency_ms": 0,
            "raw": {"reason": "provider_not_configured"},
        }


class OpenFoodFactsManufacturerVerifier(ManufacturerVerifier):
    def __init__(
        self,
        *,
        timeout_sec: float = 5.0,
        base_url: str = "https://world.openfoodfacts.net/api/v2",
        prefetched: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self.timeout_sec = max(1.0, float(timeout_sec))
        self.base_url = str(base_url or "https://world.openfoodfacts.net/api/v2").rstrip("/")
        self.prefetched = prefetched if isinstance(prefetched, dict) else {}

    def verify_gtin(self, gtin: str, region: Optional[str] = None) -> Dict[str, Any]:
        code = _digits(gtin)
        if len(code) < 12:
            return {
                "status": "not_found",
                "company_name": "",
                "source": "openfoodfacts",
                "latency_ms": 0,
                "raw": {"reason": "invalid_gtin"},
            }

        started = time.perf_counter()
        try:
            payload = self.prefetched.get(code)
            if not isinstance(payload, dict):
                url = f"{self.base_url}/product/{code}"
                resp = requests.get(url, timeout=self.timeout_sec)
                if resp.status_code != 200:
                    return {
                        "status": "error",
                        "company_name": "",
                        "source": "openfoodfacts",
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "raw": {"http_status": int(resp.status_code)},
                    }
                body = resp.json()
                payload = body if isinstance(body, dict) else {}

            off_status = int(payload.get("status") or 0)
            if off_status != 1:
                return {
                    "status": "not_found",
                    "company_name": "",
                    "source": "openfoodfacts",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "raw": {"off_status": off_status},
                }

            product = payload.get("product") if isinstance(payload.get("product"), dict) else {}
            company_name = _clean_text(product.get("brands") or product.get("brand_owner") or product.get("manufacturer"))
            if not company_name:
                return {
                    "status": "not_found",
                    "company_name": "",
                    "source": "openfoodfacts",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "raw": {"off_status": off_status, "reason": "company_missing"},
                }

            return {
                "status": "verified",
                "company_name": company_name,
                "source": "openfoodfacts",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "raw": {"off_status": off_status},
            }
        except Exception as e:
            return {
                "status": "error",
                "company_name": "",
                "source": "openfoodfacts",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "raw": {"error": str(e)[:220]},
            }


def create_manufacturer_verifier(
    provider: str,
    *,
    enabled: bool,
    timeout_sec: float = 5.0,
    prefetched: Optional[Dict[str, Dict[str, Any]]] = None,
    off_base_url: str = "https://world.openfoodfacts.net/api/v2",
) -> ManufacturerVerifier:
    token = str(provider or "none").strip().lower()
    if not enabled:
        return UnavailableManufacturerVerifier(provider="none")
    if token in {"none", ""}:
        return UnavailableManufacturerVerifier(provider="none")
    if token == "gs1_licensed":
        return GS1LicensedManufacturerVerifier(timeout_sec=timeout_sec)
    if token in {"off", "openfoodfacts", "open_food_facts"}:
        # Phase 1 provider uses OFF until a licensed provider is integrated.
        return OpenFoodFactsManufacturerVerifier(
            timeout_sec=timeout_sec,
            base_url=off_base_url,
            prefetched=prefetched,
        )
    return UnavailableManufacturerVerifier(provider=token)

