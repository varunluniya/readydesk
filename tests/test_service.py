from datetime import date

import pytest

from gen4 import KnowledgeBase, LLMClient, Memory
from hard_cases import FOUR, OK_FIELDS, TODAY
from service import ReadyDeskService


@pytest.fixture
def svc():
    return ReadyDeskService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_checklist_is_cited_for_the_right_product(svc):
    r = svc.check({"product": "home_loan", "documents": FOUR, "fields": OK_FIELDS}, today=TODAY)
    assert "property_documents" in r["missing_documents"]
    assert any(c["heading"] == "Home loan" for c in r["trace"]["retrieval"])


def test_missing_document_never_goes_direct(svc):
    r = svc.check({"documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
    assert r["confidence"] == 0.85 and r["route"] == "flag_for_review"


def test_applicant_message_lists_exact_fixes(svc):
    r = svc.check({"documents": ["id_proof"], "fields": {**OK_FIELDS, "pan_number": "12"}}, today=TODAY)
    assert r["route"] == "return_to_applicant"
    assert "income proof" in r["applicant_message"] and "pan_number" in r["applicant_message"]


def test_unknown_product_rejected(svc):
    with pytest.raises(ValueError):
        svc.check({"product": "yacht", "documents": [], "fields": {}}, today=TODAY)


def test_needless_flags_loosen_threshold_within_bounds(svc):
    for k in range(40):
        r = svc.check({"application_id": f"n{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)
    assert 0.75 <= svc.thresholds()["high"] < 0.85


def test_common_issues_are_remembered(svc):
    for k in range(3):
        svc.check({"documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
    assert svc.common_issues()[0] == ("address_proof", 3)


def test_freshness_uses_today(svc):
    app = {"documents": ["id_proof", "income_proof", "address_proof",
                         {"type": "bank_statement", "period_end": "2026-08-15"}], "fields": OK_FIELDS}
    assert svc.check(app, today=date(2026, 9, 1))["field_issues"] == []
    assert svc.check(app, today=date(2027, 1, 1))["field_issues"]
