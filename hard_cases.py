"""
Applications v1 routes wrongly because it only knows one checklist and never
reads document metadata. Each: (id, application, route v2 should give, why).
TODAY is fixed so freshness checks are reproducible.
"""
from datetime import date

TODAY = date(2026, 9, 1)
OK_FIELDS = {"applicant_name": "Asha Rao", "loan_amount": 350000, "monthly_income": 62000,
             "pan_number": "ABCDE1234F", "phone_number": "9876543210"}
FOUR = ["id_proof", "income_proof", "bank_statement", "address_proof"]

HARD_CASES = [
    ("self-employed-missing-itr",
     {"product": "personal_loan", "applicant_type": "self_employed", "documents": FOUR, "fields": OK_FIELDS},
     "flag_for_review", "self-employed checklist needs ITR (2y) and business proof; v1 only knows the salaried list"),
    ("expired-id",
     {"documents": [{"type": "id_proof", "valid_until": "2025-12-31", "name_on_doc": "Asha Rao"},
                    "income_proof", "bank_statement", "address_proof"], "fields": OK_FIELDS},
     "flag_for_review", "ID expired 2025-12-31 counts as missing"),
    ("stale-statement-and-name-mismatch",
     {"documents": [{"type": "id_proof", "name_on_doc": "Asha R. Menon"},
                    {"type": "bank_statement", "period_end": "2026-02-28"}, "income_proof", "address_proof"],
      "fields": OK_FIELDS},
     "flag_for_review", "bank statement 6 months old + ID name differs"),
    ("income-gap",
     {"documents": ["id_proof", {"type": "income_proof", "monthly_income": 38000, "issued_on": "2026-08-01"},
                    "bank_statement", "address_proof"], "fields": OK_FIELDS},
     "flag_for_review", "stated 62,000 vs slip 38,000"),
    ("two-wheeler-light-checklist",
     {"product": "two_wheeler", "documents": ["id_proof", "address_proof"],
      "fields": {**OK_FIELDS, "loan_amount": 95000}},
     "direct_to_underwriter", "two-wheeler under 1.5L needs only ID + address; v1 would demand 4 documents"),
    ("high-value-needs-itr",
     {"documents": FOUR, "fields": {**OK_FIELDS, "loan_amount": 1500000}},
     "flag_for_review", "above 10L requires ITR regardless of product"),
]
