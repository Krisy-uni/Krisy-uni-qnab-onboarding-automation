import os
os.environ["INTEGRATION_API_KEY"] = "testing-key"

from app import app


def test_health():
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_contract_rejects_missing_key():
    response = app.test_client().post("/api/contracts/register", json={"case_id": 1})
    assert response.status_code == 401


def test_contract_rejects_bad_case_id():
    response = app.test_client().post(
        "/api/contracts/register", json={"case_id": "wrong"},
        headers={"X-Integration-Key": "testing-key"})
    assert response.status_code == 400


def test_finance_invite_rejects_missing_email():
    response = app.test_client().post(
        "/api/finance/invite", json={"case_id": 1},
        headers={"X-Integration-Key": "testing-key"})
    assert response.status_code == 400
