"""One-shot runner for a hand-built list of (chain, market, url) targets.

Reads /tmp/missing_markets_targets.json (list of {chain, market, url} dicts)
and runs tools/ingest_chain_from_url.py in --stage-only mode against each,
writing results to data/remediation_run_log.json under the existing keys so
resume-from-log works.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INGEST = os.path.join(REPO, "tools", "ingest_chain_from_url.py")
RUN_LOG = os.path.join(REPO, "data", "remediation_run_log.json")
TARGETS_JSON = "/tmp/missing_markets_targets.json"


def load_run_log():
    if not os.path.exists(RUN_LOG):
        return {}
    with open(RUN_LOG) as f:
        return json.load(f)


def save_run_log(log):
    with open(RUN_LOG, "w") as f:
        json.dump(log, f, indent=2)


def main():
    with open(TARGETS_JSON) as f:
        targets = json.load(f)
    print(f"Targets: {len(targets)}")
    log = load_run_log()
    done = 0
    skipped = 0
    for t in targets:
        ck = t["chain"]
        m = t["market"]
        url = t["url"]
        ck_m = f"{ck}::{m}"
        # Skip if already ok in log
        if log.get(ck_m, {}).get("status") == "ok":
            print(f"SKIP {ck_m} — already ok")
            skipped += 1
            continue
        cmd = [sys.executable, INGEST, "--chain", ck, "--market", m,
               "--url", url, "--stage-only"]
        print(f"\n{'='*70}\n{ck_m}  url={url}")
        t0 = dt.datetime.utcnow()
        try:
            r = subprocess.run(cmd, cwd=REPO, capture_output=False, timeout=600)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -1
        el = (dt.datetime.utcnow() - t0).total_seconds()
        status = "ok" if rc == 0 else ("needs_review" if rc == 2 else "failed")
        log[ck_m] = {
            "status": status,
            "rc": rc,
            "elapsed_s": round(el, 1),
            "completed_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        save_run_log(log)
        done += 1

    print(f"\n=== DONE ===")
    print(f"Processed: {done}  Skipped (already ok): {skipped}")


if __name__ == "__main__":
    main()
