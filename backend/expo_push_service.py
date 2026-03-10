"""
Expo Push Service: build messages, send to Expo API, fetch receipts.
Direct HTTP integration; batches messages; supports dry-run.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

logger = logging.getLogger("kcal")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
BATCH_SIZE = 50
DEVICE_NOT_REGISTERED = "DeviceNotRegistered"


def build_expo_push_message(
    alert_candidate: Dict[str, Any],
    expo_push_token: str,
) -> Dict[str, Any]:
    """
    Build a single Expo push message from an alert candidate.
    """
    title = str(alert_candidate.get("title") or "Smart Food Alert").strip()
    body = str(alert_candidate.get("body") or "").strip()
    place_id = str(alert_candidate.get("place_id") or "").strip()
    place_name = str(alert_candidate.get("place_name") or "").strip()
    best_item_name = str(alert_candidate.get("best_item_name") or "").strip()
    alert_type = str(alert_candidate.get("alert_type") or "").strip()
    display_score = alert_candidate.get("display_rank_score_100")
    context_mode = str(alert_candidate.get("context_mode") or "").strip()
    alert_id = f"{alert_type}::{place_id}::{best_item_name}"

    data: Dict[str, Any] = {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "place_id": place_id,
        "place_name": place_name,
        "best_item_name": best_item_name,
        "context_mode": context_mode,
    }
    if display_score is not None:
        data["display_rank_score_100"] = display_score

    msg: Dict[str, Any] = {
        "to": expo_push_token,
        "title": title or "Smart Food Alert",
        "body": body or "A nearby option fits your goals.",
        "sound": "default",
        "data": data,
    }
    return msg


def send_expo_push_messages(
    messages: List[Dict[str, Any]],
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Send push messages to Expo API. Batches into chunks of BATCH_SIZE.
    Returns: {
        "ok": bool,
        "dry_run": bool,
        "tickets": [...],  # list of {status, id?, message?, details?}
        "errors": [...],   # request-level errors
        "sent_count": int,
        "error_count": int,
    }
    """
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "tickets": [{"status": "ok", "id": f"dry-run-{i}"} for i in range(len(messages))],
            "errors": [],
            "sent_count": len(messages),
            "error_count": 0,
        }

    if not messages:
        return {"ok": True, "dry_run": False, "tickets": [], "errors": [], "sent_count": 0, "error_count": 0}

    all_tickets: List[Dict[str, Any]] = []
    request_errors: List[Dict[str, Any]] = []

    chunks: List[List[Dict[str, Any]]] = []
    for i in range(0, len(messages), BATCH_SIZE):
        chunks.append(messages[i : i + BATCH_SIZE])

    if not _HAS_REQUESTS:
        request_errors.append({"message": "requests module not installed"})
        for _ in messages:
            all_tickets.append({"status": "error", "message": "requests not installed"})
        return {
            "ok": False,
            "dry_run": False,
            "tickets": all_tickets,
            "errors": request_errors,
            "sent_count": 0,
            "error_count": len(messages),
        }

    for chunk in chunks:
        try:
            r = requests.post(
                EXPO_PUSH_URL,
                json=chunk,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except Exception as e:
            logger.warning("expo_push_send: network error %s", str(e))
            request_errors.append({"message": str(e), "chunk_size": len(chunk)})
            for _ in chunk:
                all_tickets.append({"status": "error", "message": str(e)})
            continue

        if r.status_code >= 400:
            err_text = (r.text or "")[:500]
            logger.warning("expo_push_send: HTTP %d %s", r.status_code, err_text)
            try:
                body = r.json()
                errs = body.get("errors") or [{"message": err_text}]
            except Exception:
                errs = [{"message": err_text}]
            request_errors.extend(errs)
            for _ in chunk:
                all_tickets.append({"status": "error", "message": err_text})
            continue

        try:
            body = r.json()
        except Exception:
            request_errors.append({"message": "invalid json response"})
            for _ in chunk:
                all_tickets.append({"status": "error", "message": "invalid response"})
            continue

        tickets = body.get("data")
        if isinstance(tickets, list):
            all_tickets.extend(tickets)
        elif isinstance(tickets, dict):
            all_tickets.append(tickets)
        else:
            for _ in chunk:
                all_tickets.append({"status": "error", "message": "missing tickets"})

    sent = sum(1 for t in all_tickets if t.get("status") == "ok")
    err_count = len(all_tickets) - sent
    return {
        "ok": len(request_errors) == 0,
        "dry_run": False,
        "tickets": all_tickets,
        "errors": request_errors,
        "sent_count": sent,
        "error_count": err_count,
    }


def fetch_expo_push_receipts(receipt_ids: List[str]) -> Dict[str, Any]:
    """
    Fetch push receipts from Expo. receipt_ids are ticket IDs from send response.
    Returns: {
        "ok": bool,
        "receipts": {ticket_id: {status, message?, details?}},
        "errors": [...],
    }
    """
    if not receipt_ids:
        return {"ok": True, "receipts": {}, "errors": []}

    ids = [str(i).strip() for i in receipt_ids if str(i).strip()][:1000]
    if not ids:
        return {"ok": True, "receipts": {}, "errors": []}

    if not _HAS_REQUESTS:
        return {"ok": False, "receipts": {}, "errors": [{"message": "requests module not installed"}]}

    try:
        r = requests.post(
            EXPO_RECEIPTS_URL,
            json={"ids": ids},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    except Exception as e:
        logger.warning("expo_push_receipts: network error %s", str(e))
        return {"ok": False, "receipts": {}, "errors": [{"message": str(e)}]}

    if r.status_code >= 400:
        err_text = (r.text or "")[:500]
        logger.warning("expo_push_receipts: HTTP %d %s", r.status_code, err_text)
        try:
            body = r.json()
            errs = body.get("errors") or [{"message": err_text}]
        except Exception:
            errs = [{"message": err_text}]
        return {"ok": False, "receipts": {}, "errors": errs}

    try:
        body = r.json()
    except Exception:
        return {"ok": False, "receipts": {}, "errors": [{"message": "invalid json response"}]}

    receipts = body.get("data")
    if not isinstance(receipts, dict):
        receipts = {}
    return {"ok": True, "receipts": receipts, "errors": body.get("errors") or []}


def is_device_not_registered(ticket_or_receipt: Dict[str, Any]) -> bool:
    """Check if ticket/receipt indicates DeviceNotRegistered."""
    details = ticket_or_receipt.get("details") or {}
    err = details.get("error") if isinstance(details, dict) else None
    return str(err) == DEVICE_NOT_REGISTERED
