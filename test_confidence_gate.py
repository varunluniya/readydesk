import pytest
from confidence_gate import (
    confidence_gated_response,
    call_llm_analysis,
    TEST_APPLICATIONS,
    HIGH_THRESH,
    LOW_THRESH,
)


def test_clean_application_routes_direct():
    result = confidence_gated_response(TEST_APPLICATIONS["clean"])
    assert result.route == "direct_to_underwriter"
    assert result.confidence >= HIGH_THRESH
    assert result.missing_documents == []
    assert result.field_issues == []


def test_minor_issues_routes_to_review_with_specific_concern():
    result = confidence_gated_response(TEST_APPLICATIONS["minor_issues"])
    assert result.route == "flag_for_review"
    assert LOW_THRESH <= result.confidence < HIGH_THRESH
    # the whole point of the medium band is a SPECIFIC concern, not a blank flag
    assert "address_proof" in result.missing_documents
    assert any("pan_number" in issue for issue in result.field_issues)


def test_serious_issues_routes_to_applicant():
    result = confidence_gated_response(TEST_APPLICATIONS["serious_issues"])
    assert result.route == "return_to_applicant"
    assert result.confidence < LOW_THRESH
    assert len(result.missing_documents) >= 2
    assert len(result.field_issues) >= 2


def test_missing_document_detected_by_name():
    analysis = call_llm_analysis(
        {
            "documents": ["id_proof", "income_proof", "bank_statement"],
            "fields": {
                "applicant_name": "Test User",
                "loan_amount": 100000,
                "monthly_income": 50000,
                "pan_number": "ABCDE1234F",
                "phone_number": "9876543210",
            },
        }
    )
    assert analysis["missing_documents"] == ["address_proof"]
    assert analysis["field_issues"] == []
    assert analysis["confidence"] > LOW_THRESH


def test_invalid_pan_format_flagged():
    analysis = call_llm_analysis(
        {
            "documents": ["id_proof", "income_proof", "bank_statement", "address_proof"],
            "fields": {
                "applicant_name": "Test User",
                "loan_amount": 100000,
                "monthly_income": 50000,
                "pan_number": "NOTAPAN",
                "phone_number": "9876543210",
            },
        }
    )
    assert any("pan_number" in issue for issue in analysis["field_issues"])


def test_invalid_phone_format_flagged():
    analysis = call_llm_analysis(
        {
            "documents": ["id_proof", "income_proof", "bank_statement", "address_proof"],
            "fields": {
                "applicant_name": "Test User",
                "loan_amount": 100000,
                "monthly_income": 50000,
                "pan_number": "ABCDE1234F",
                "phone_number": "12345",
            },
        }
    )
    assert any("phone_number" in issue for issue in analysis["field_issues"])


def test_negative_loan_amount_flagged():
    analysis = call_llm_analysis(
        {
            "documents": ["id_proof", "income_proof", "bank_statement", "address_proof"],
            "fields": {
                "applicant_name": "Test User",
                "loan_amount": -100,
                "monthly_income": 50000,
                "pan_number": "ABCDE1234F",
                "phone_number": "9876543210",
            },
        }
    )
    assert any("loan_amount" in issue for issue in analysis["field_issues"])


def test_confidence_bounds():
    for name, app in TEST_APPLICATIONS.items():
        result = confidence_gated_response(app)
        assert 0.0 <= result.confidence <= 1.0, f"{name} confidence out of bounds"
