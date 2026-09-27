"""
Guide 4 Assignment 2 ("RAG with Guardrails") applied to ReadyDesk's own
applicant-message generator: one query that passes cleanly, one that fires
the guardrail, and one genuine edge case.
"""
import pytest

from gen4 import KnowledgeBase, LLMClient, Memory
from service import ReadyDeskService


@pytest.fixture
def svc():
    return ReadyDeskService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_passing_query_message_names_the_open_items(svc):
    a = {"missing_documents": ["address_proof"], "field_issues": []}
    draft = "Please upload: address proof."
    out = svc._guarded(draft, "flag_for_review", a, draft, passages=[])
    assert out == draft
    assert "guardrail replaced" not in out


def test_guardrail_fires_on_approval_language_with_open_items(svc):
    """The Air Canada failure shape: a fluent, reassuring line that contradicts
    the applicant's real status -- documents are still missing, but the draft
    implies everything is fine."""
    a = {"missing_documents": ["income_proof"], "field_issues": []}
    bad_draft = "You're all set, thanks for applying!"
    fallback = "Please upload: income proof."
    out = svc._guarded(bad_draft, "flag_for_review", a, fallback, passages=[])
    assert out != bad_draft
    assert "guardrail replaced" in out
    assert "income proof" in out


def test_edge_case_draft_lists_one_missing_item_but_drops_another(svc):
    """Genuine edge case: the draft never claims approval and does mention one
    real missing item, but silently drops a second one the applicant also
    needs to act on -- a partial truth is still an actionable gap here."""
    a = {"missing_documents": ["income_proof", "bank_statement"], "field_issues": []}
    partial_draft = "Please upload: income proof."
    fallback = "Please upload: income proof, bank statement."
    out = svc._guarded(partial_draft, "flag_for_review", a, fallback, passages=[])
    assert out != partial_draft
    assert "bank statement" in out.lower()
