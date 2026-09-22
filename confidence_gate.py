"""
ReadyDesk — a confidence-gated completeness checker for loan application
intake.

Screens an application for missing documents and missing/invalid fields,
then routes it based on how confident the system is that the application
is actually ready for an underwriter's desk. A single binary "complete?
yes/no" check hides its own error rate; a confidence score plus a
three-band route makes that error rate visible and actionable instead.

Routing bands:
    high   (>= HIGH_THRESH) -> direct_to_underwriter
    medium (LOW_THRESH .. HIGH_THRESH) -> flag_for_review (with the
             specific concern named, not a generic "needs review" flag)
    low    (< LOW_THRESH) -> return_to_applicant

The underwriter still substantively reviews every loan this gate lets
through -- it only screens intake completeness -- so the cost of an
occasional false "complete" is low (it gets caught downstream). That is
why HIGH_THRESH can sit at a confident-but-not-paranoid 0.85 rather than
something more conservative.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List

HIGH_THRESH = 0.85
LOW_THRESH = 0.55

REQUIRED_DOCUMENTS = ["id_proof", "income_proof", "bank_statement", "address_proof"]

# Deduction weight per missing document / per field issue. Tuned so a
# single missing document plus a single field issue lands squarely in
# the medium band, and several of each pushes an application into the
# low band -- see README for a worked example.
MISSING_DOC_PENALTY = 0.15
FIELD_ISSUE_PENALTY = 0.06

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PHONE_RE = re.compile(r"^[0-9]{10}$")


@dataclass
class GateResult:
    route: str
    confidence: float
    missing_documents: List[str] = field(default_factory=list)
    field_issues: List[str] = field(default_factory=list)


def call_llm_analysis(application: Dict) -> Dict:
    """
    Analyze an application for missing documents and field issues.

    Honest disclosure: no external LLM API key was available when this
    was built, so this is a deterministic rule-based analyzer standing in
    for a real LLM call -- disclosed honestly rather than faked. It's
    written exactly like the real call would be (structured input in,
    structured JSON-shaped output out) and is the single swap point for a
    live API integration; nothing else in this file needs to change.
    """
    documents = set(application.get("documents", []))
    fields = application.get("fields", {})

    missing_documents = [d for d in REQUIRED_DOCUMENTS if d not in documents]

    field_issues = []

    if not str(fields.get("applicant_name", "")).strip():
        field_issues.append("applicant_name: missing")

    pan = str(fields.get("pan_number", ""))
    if not PAN_RE.match(pan):
        field_issues.append(f"pan_number: invalid format ('{pan}')")

    phone = str(fields.get("phone_number", ""))
    if not PHONE_RE.match(phone):
        field_issues.append(f"phone_number: invalid format ('{phone}')")

    loan_amount = fields.get("loan_amount")
    try:
        if float(loan_amount) <= 0:
            field_issues.append("loan_amount: must be greater than zero")
    except (TypeError, ValueError):
        field_issues.append(f"loan_amount: not numeric ('{loan_amount}')")

    monthly_income = fields.get("monthly_income")
    try:
        float(monthly_income)
    except (TypeError, ValueError):
        field_issues.append(f"monthly_income: not numeric ('{monthly_income}')")

    confidence = max(
        0.0,
        1.0
        - MISSING_DOC_PENALTY * len(missing_documents)
        - FIELD_ISSUE_PENALTY * len(field_issues),
    )

    return {
        "missing_documents": missing_documents,
        "field_issues": field_issues,
        "confidence": round(confidence, 2),
    }


def confidence_gated_response(application: Dict) -> GateResult:
    analysis = call_llm_analysis(application)
    confidence = analysis["confidence"]

    if confidence >= HIGH_THRESH:
        route = "direct_to_underwriter"
    elif confidence >= LOW_THRESH:
        route = "flag_for_review"
    else:
        route = "return_to_applicant"

    return GateResult(
        route=route,
        confidence=confidence,
        missing_documents=analysis["missing_documents"],
        field_issues=analysis["field_issues"],
    )


def format_result(name: str, application: Dict, result: GateResult) -> str:
    lines = [f"--- Application: {name} ---"]
    lines.append(f"Route:      {result.route}")
    lines.append(f"Confidence: {result.confidence:.2f}")
    lines.append(
        "Missing documents: "
        + (", ".join(result.missing_documents) if result.missing_documents else "none")
    )
    if result.field_issues:
        lines.append("Field issues:")
        for issue in result.field_issues:
            lines.append(f"  - {issue}")
    else:
        lines.append("Field issues: none")
    return "\n".join(lines)


TEST_APPLICATIONS = {
    "clean": {
        "documents": ["id_proof", "income_proof", "bank_statement", "address_proof"],
        "fields": {
            "applicant_name": "Asha Rao",
            "loan_amount": 350000,
            "monthly_income": 62000,
            "pan_number": "ABCDE1234F",
            "phone_number": "9876543210",
        },
    },
    "minor_issues": {
        "documents": ["id_proof", "income_proof", "bank_statement"],
        "fields": {
            "applicant_name": "Rahul Mehta",
            "loan_amount": 275000,
            "monthly_income": 48000,
            "pan_number": "abcde1234f",
            "phone_number": "9812345678",
        },
    },
    "serious_issues": {
        "documents": ["id_proof"],
        "fields": {
            "applicant_name": "",
            "loan_amount": -5000,
            "monthly_income": "N/A",
            "pan_number": "12345",
            "phone_number": "12345",
        },
    },
}
