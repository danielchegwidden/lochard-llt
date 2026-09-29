"""Leadership Portal API tests (local; uses the developer's CLI profile). Run against a throwaway Lakebase branch –
the tests write data:

  cd src/app && source ../../scripts/localdev.env.sh && DATABRICKS_PROFILE=fevm-dc-demo-workspace-02 .venv/bin/python -m pytest ../../tests/app -q

Personas are simulated with the x-forwarded-email header (as the Databricks Apps proxy sets it); roles for the
seeded directors / LLT come from scorecard.app_user_role.
"""
import os
import sys

import pytest

APP = os.path.join(os.path.dirname(__file__), "..", "..", "src", "app")
sys.path.insert(0, os.path.abspath(APP))
os.chdir(os.path.abspath(APP))

from fastapi.testclient import TestClient  # noqa: E402

import app as portal  # noqa: E402
from server import db  # noqa: E402

CHAIR = {"x-forwarded-email": "chair@board.example-lochard.com.au"}
LLT = {"x-forwarded-email": "da@example-lochard.com.au"}
MARK = "pytest-marker"


@pytest.fixture(scope="module")
def client():
    with TestClient(portal.app) as c:
        yield c
        with db.pool.connection() as conn:   # clean up test comments (pool closes with the app lifespan)
            conn.execute("DELETE FROM scorecard.comment WHERE body LIKE %s", (f"%{MARK}%",))


def test_fy27_scorecard_matches_board_slide(client):
    d = client.get("/api/scorecard/FY27?period=FY27-M02").json()
    kpis = {k["code"]: k for p in d["pillars"] for k in p["kpis"]}
    assert len(kpis) == 8 and d["weights_total"] == 100
    assert [p["name"] for p in d["pillars"]] == ["HSE & Iona Operations", "Growth Delivery", "Financial"]
    assert {c: k["weight_pct"] for c, k in kpis.items()} == {"1.1": 20, "1.2": 10, "1.3": 5, "2.1": 5, "2.2": 20,
                                                              "2.3": 10, "3.1": 20, "3.2": 10}
    assert kpis["1.1"]["status"] == "AT_RISK" and kpis["2.1"]["status"] == "AT_RISK"
    assert all(kpis[c]["status"] == "ON_TRACK" for c in ["1.2", "1.3", "2.2", "2.3", "3.1", "3.2"])
    assert kpis["1.1"]["owner_initials"] == "DA" and kpis["2.2"]["owner_initials"] == "DS/DG"
    assert len(kpis["2.2"]["deliverables"]) == 6
    assert d["summary"]["status_index_pct"] == pytest.approx(87.5)


def test_illegal_transition_is_409(client):
    r = client.post("/api/period/FY27-M02/advance", json={"to_state": "OWNER_SUBMITTED"})
    assert r.status_code == 409


def test_role_checked_transition_is_403(client):
    r = client.post("/api/period/FY27-M02/advance", json={"to_state": "LOCKED"}, headers=LLT)
    assert r.status_code == 403


def test_locked_period_rejects_status_update(client):
    r = client.post("/api/kpi/FY27-1.1/status", json={"period": "FY27-M01", "status": "AT_RISK"}, headers=LLT)
    assert r.status_code == 409


def test_board_only_comment_visibility(client):
    r = client.post("/api/kpi/FY27-3.1/comments", headers=CHAIR,
                    json={"period": "FY27-M02", "body": f"board only {MARK}", "visibility": "BOARD_ONLY"})
    assert r.status_code == 200, r.text
    chair_view = client.get("/api/kpi/FY27-3.1?period=FY27-M02", headers=CHAIR).json()["comments"]
    llt_view = client.get("/api/kpi/FY27-3.1?period=FY27-M02", headers=LLT).json()["comments"]
    assert any(MARK in c["body"] for c in chair_view)
    assert not any(MARK in c["body"] for c in llt_view)
    r = client.post("/api/kpi/FY27-3.1/comments", headers=LLT,
                    json={"period": "FY27-M02", "body": f"x {MARK}", "visibility": "BOARD_ONLY"})
    assert r.status_code == 403


def test_individual_scores_hidden_from_llt(client):
    llt = client.get("/api/kpi/FY27-2.1?period=FY27-M02", headers=LLT).json()["board_scores"]
    assert llt and all(s["director_name"] == "Director" and "director_email" not in s for s in llt)


def test_export_pptx(client):
    r = client.get("/api/export/FY27/FY27-M02.pptx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_dashboards_have_embed_urls(client):
    rows = client.get("/api/dashboards").json()
    assert len(rows) == 5 and all(r["embed_url"] and "/embed/dashboardsv3/" in r["embed_url"] for r in rows)
