"""
Supabase keep-alive.

Free-plan Supabase projects hibernate when the database sees no activity, and
while hibernating the REST and auth APIs return 503 until the next request
wakes them. That broke CalorieClick on 2026-11-09 (most API calls 503'd for
the hour before it woke).

The Railway backend runs 24/7 (Serverless is off), so it runs a tiny real
database read on a fixed interval to keep the project awake. The read goes
through PostgREST, so it is genuine database activity, not just a gateway hit.

Config (Railway variables):
  SUPABASE_KEEPALIVE_INTERVAL_SECONDS  default 600 (10 min); 0 disables.
  SUPABASE_KEEPALIVE_TABLE             default "plan_limits".

Failures are logged and never raised: a missed ping must not affect the API.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 600
MIN_INTERVAL_SECONDS = 60
DEFAULT_TABLE = "plan_limits"
REQUEST_TIMEOUT_SECONDS = 20

_started_lock = threading.Lock()
_started = False


def keepalive_interval_seconds() -> int:
    """Interval from env. 0 (or negative) disables; values below 60s are raised to 60s."""
    raw = os.getenv("SUPABASE_KEEPALIVE_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    try:
        value = int(float(raw))
    except ValueError:
        logger.warning(
            "Invalid SUPABASE_KEEPALIVE_INTERVAL_SECONDS=%r; using default %ss",
            raw,
            DEFAULT_INTERVAL_SECONDS,
        )
        return DEFAULT_INTERVAL_SECONDS
    if value <= 0:
        return 0
    return max(value, MIN_INTERVAL_SECONDS)


def keepalive_table() -> str:
    return os.getenv("SUPABASE_KEEPALIVE_TABLE", "").strip() or DEFAULT_TABLE


def ping_once(
    supabase_url: str,
    service_role_key: str,
    table: Optional[str] = None,
    http_get: Callable[..., requests.Response] = requests.get,
) -> bool:
    """Run one minimal database read. Returns True on HTTP 200, False otherwise. Never raises."""
    if not supabase_url or not service_role_key:
        return False
    table = table or keepalive_table()
    url = f"{supabase_url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    try:
        resp = http_get(
            url,
            headers=headers,
            params={"select": "*", "limit": "1"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as e:  # network errors, timeouts
        logger.warning("Supabase keep-alive ping failed: %s", e)
        return False
    if resp.status_code == 200:
        logger.debug("Supabase keep-alive ping ok (%s)", table)
        return True
    logger.warning(
        "Supabase keep-alive ping returned HTTP %s for table %s",
        resp.status_code,
        table,
    )
    return False


def _loop(supabase_url: str, service_role_key: str, interval: int, sleep: Callable[[float], None]) -> None:
    while True:
        ping_once(supabase_url, service_role_key)
        sleep(interval)


def start_keepalive_thread(
    supabase_url: str,
    service_role_key: str,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[threading.Thread]:
    """Start the daemon keep-alive thread once per process. Returns the thread, or None if not started."""
    global _started
    if not supabase_url or not service_role_key:
        logger.info("Supabase keep-alive not started: SUPABASE_URL or service role key missing")
        return None
    interval = keepalive_interval_seconds()
    if interval == 0:
        logger.info("Supabase keep-alive disabled (SUPABASE_KEEPALIVE_INTERVAL_SECONDS=0)")
        return None
    with _started_lock:
        if _started:
            return None
        _started = True
    t = threading.Thread(
        target=_loop,
        args=(supabase_url, service_role_key, interval, sleep),
        daemon=True,
        name="supabase-keepalive",
    )
    t.start()
    logger.info("Supabase keep-alive started: table=%s, every %ss", keepalive_table(), interval)
    return t
