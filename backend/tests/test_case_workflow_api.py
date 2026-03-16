"""
API tests for YieldPilot case workflow: endpoints, auth, filtering, memo export, empty state.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Ensure backend is on path
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_BACKEND))

try:
    from fastapi.testclient import TestClient
    from main import app
except ImportError:
    pytest.skip("FastAPI or main.app not available", allow_module_level=True)


@pytest.fixture(autouse=True)
def _temp_db():
    d = tempfile.mkdtemp(prefix="yp_api_test_")
    path = Path(d) / "cases.sqlite"
    os.environ["YIELDPILOT_CASE_DB_PATH"] = str(path)
    from yieldpilot_case_workflow import init_schema
    init_schema()
    yield
    os.environ.pop("YIELDPILOT_CASE_DB_PATH", None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def uid():
    return "test-user-api-1"


def test_cases_require_user(client):
    r = client.get("/yieldpilot/cases")
    assert r.status_code == 401


def test_post_case(client, uid):
    r = client.post(
        "/yieldpilot/cases",
        json={"symbol": "AAPL", "title": "API case", "scenario_type": "covered_call"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "case" in data
    assert data["case"]["symbol"] == "AAPL"
    assert data["case"]["user_id"] == uid


def test_post_case_from_recommendation(client, uid):
    r = client.post(
        "/yieldpilot/cases/from-recommendation",
        json={
            "recommendation": {
                "symbol": "SPY",
                "scenario_type": "wheel",
                "model_score": 75,
                "capital_required": 50000,
            },
            "title": "SPY wheel",
        },
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["case"]["symbol"] == "SPY"
    assert data["case"]["scenario_type"] == "wheel"


def test_get_cases_empty(client, uid):
    r = client.get("/yieldpilot/cases", headers={"X-User-Id": uid})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["cases"] == []


def test_get_cases_with_filter(client, uid):
    client.post("/yieldpilot/cases", json={"symbol": "AAPL", "title": "A"}, headers={"X-User-Id": uid})
    client.post("/yieldpilot/cases", json={"symbol": "MSFT", "title": "B"}, headers={"X-User-Id": uid})
    r = client.get("/yieldpilot/cases", params={"symbol": "AAPL"}, headers={"X-User-Id": uid})
    assert r.status_code == 200
    cases = r.json()["cases"]
    assert len(cases) == 1
    assert cases[0]["symbol"] == "AAPL"


def test_get_case_by_id(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "GOOG", "title": "One"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.get(f"/yieldpilot/cases/{cid}", headers={"X-User-Id": uid})
    assert r.status_code == 200
    assert r.json()["case"]["symbol"] == "GOOG"


def test_get_case_404(client, uid):
    r = client.get("/yieldpilot/cases/99999", headers={"X-User-Id": uid})
    assert r.status_code == 404


def test_patch_case(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "QQQ", "title": "Original"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.patch(
        f"/yieldpilot/cases/{cid}",
        json={"title": "Updated", "rationale": "Reason"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["case"]["title"] == "Updated"
    assert r.json()["case"]["rationale"] == "Reason"


def test_post_comment(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "X", "title": "Comment case"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.post(
        f"/yieldpilot/cases/{cid}/comment",
        json={"body": "Hello comment"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["comment"]["body"] == "Hello comment"
    r2 = client.get(f"/yieldpilot/cases/{cid}/comments", headers={"X-User-Id": uid})
    assert len(r2.json()["comments"]) == 1


def test_post_status(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "Y", "title": "Status case"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.post(
        f"/yieldpilot/cases/{cid}/status",
        json={"new_status": "under_review", "note": "Sending for review"},
        headers={"X-User-Id": uid},
    )
    assert r.status_code == 200
    assert r.json()["case"]["status"] == "under_review"
    r2 = client.get(f"/yieldpilot/cases/{cid}/status-history", headers={"X-User-Id": uid})
    assert len(r2.json()["status_history"]) >= 2


def test_memo_json(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "M", "title": "Memo", "rationale": "For export"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.get(f"/yieldpilot/cases/{cid}/memo.json", headers={"X-User-Id": uid})
    assert r.status_code == 200
    assert "Memo" in r.text
    assert "M" in r.text


def test_memo_csv(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "C", "title": "CSV case"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.get(f"/yieldpilot/cases/{cid}/memo.csv", headers={"X-User-Id": uid})
    assert r.status_code == 200
    assert "case_title" in r.text


def test_memo_txt(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "T", "title": "TXT case"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.get(f"/yieldpilot/cases/{cid}/memo.txt", headers={"X-User-Id": uid})
    assert r.status_code == 200
    assert "TXT case" in r.text


def test_delete_case(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "D", "title": "To delete"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.delete(f"/yieldpilot/cases/{cid}", headers={"X-User-Id": uid})
    assert r.status_code == 200
    r2 = client.get(f"/yieldpilot/cases/{cid}", headers={"X-User-Id": uid})
    assert r2.status_code == 404


def test_user_isolation(client, uid):
    create = client.post(
        "/yieldpilot/cases",
        json={"symbol": "I", "title": "Isolation"},
        headers={"X-User-Id": uid},
    )
    cid = create.json()["case"]["id"]
    r = client.get(f"/yieldpilot/cases/{cid}", headers={"X-User-Id": "other-user"})
    assert r.status_code == 404
