"""Structured mirror of knowledge/document_checklists.md (the knowledge file is what gets cited)."""

CHECKLISTS = {
    ("personal_loan", "salaried"): ["id_proof", "income_proof", "bank_statement", "address_proof"],
    ("personal_loan", "self_employed"): ["id_proof", "address_proof", "bank_statement", "itr_2y", "business_proof"],
    ("two_wheeler", "salaried"): ["id_proof", "address_proof"],
    ("two_wheeler", "self_employed"): ["id_proof", "address_proof"],
    ("home_loan", "salaried"): ["id_proof", "address_proof", "income_proof", "bank_statement", "itr_2y",
                                "property_documents"],
    ("home_loan", "self_employed"): ["id_proof", "address_proof", "bank_statement", "itr_2y", "business_proof",
                                     "property_documents"],
}
HEADINGS = {
    ("personal_loan", "salaried"): "Personal loan, salaried",
    ("personal_loan", "self_employed"): "Personal loan, self-employed",
    ("two_wheeler", "salaried"): "Two-wheeler loan", ("two_wheeler", "self_employed"): "Two-wheeler loan",
    ("home_loan", "salaried"): "Home loan", ("home_loan", "self_employed"): "Home loan",
}
TWO_WHEELER_INCOME_ABOVE = 150_000
HIGH_VALUE_ABOVE = 1_000_000
FRESH_DAYS = 90
INCOME_TOLERANCE = 0.20


def required_documents(product: str, applicant_type: str, loan_amount: float | None) -> list[str]:
    key = (product, applicant_type)
    if key not in CHECKLISTS:
        raise ValueError(f"unknown product/applicant_type {key}")
    docs = list(CHECKLISTS[key])
    amt = loan_amount if isinstance(loan_amount, (int, float)) else 0
    if product == "two_wheeler" and amt > TWO_WHEELER_INCOME_ABOVE and "income_proof" not in docs:
        docs.append("income_proof")
    if amt > HIGH_VALUE_ABOVE and "itr_2y" not in docs:
        docs.append("itr_2y")
    return docs
