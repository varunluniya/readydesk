import os
import tempfile

os.environ["GEN4_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["GEN4_LLM_PROVIDER"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

c = TestClient(app)
FIELDS = {"applicant_name": "Asha Rao", "loan_amount": 90000, "monthly_income": 40000,
          "pan_number": "ABCDE1234F", "phone_number": "9876543210"}


def test_check_resubmit_feedback():
    r = c.post("/check", json={"application_id": "A9", "product": "two_wheeler",
                               "documents": [{"type": "id_proof", "name_on_doc": "asha  rao"}],
                               "fields": FIELDS}).json()
    assert r["route"] == "flag_for_review" and r["missing_documents"] == ["address_proof"]
    r2 = c.post("/check", json={"application_id": "A9", "product": "two_wheeler",
                                "documents": ["id_proof", "address_proof"], "fields": FIELDS}).json()
    assert r2["route"] == "direct_to_underwriter" and r2["resubmission"]["fixed"] == ["address_proof"]
    assert c.post("/feedback", json={"decision_id": r2["decision_id"], "actually_complete": True}).status_code == 200
    assert c.get("/insights").json()["thresholds"]["high"] == 0.85


def test_errors():
    assert c.post("/check", json={"product": "yacht"}).status_code == 422
    assert c.post("/feedback", json={"decision_id": "x", "actually_complete": True}).status_code == 404
