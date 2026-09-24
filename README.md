# ReadyDesk

_Confidence-gated loan intake that knows the checklist for each product and applicant type, reads document metadata (expiry, freshness, name, income), remembers resubmissions, and tunes its threshold from underwriter verdicts._

[![ci](https://github.com/varunluniya/readydesk/actions/workflows/ci.yml/badge.svg)](https://github.com/varunluniya/readydesk/actions/workflows/ci.yml)

## What's new in v2: an intelligent, deployable service

| Layer | In ReadyDesk |
|---|---|
| **Retrieval** | Product × applicant-type checklists, freshness and consistency rules, cited per decision |
| **Context** | Product, applicant type, loan amount (two-wheeler above 1.5L, any loan above 10L), today's date |
| **Memory** | Every submission per application → "fixed: X, still open: Y". Issue frequency across applicants |
| **Feedback** | Underwriter "was it actually complete?" → threshold moves ±0.02 (bounded 0.75–0.95, cooldown) |

| 9 applications (3 originals + 6 hard cases) | v1 | v2 |
|---|---|---|
| Correctly routed | 3/9 | **9/9** |
| Expired ID / stale statement / name mismatch / 38k-vs-62k income | sent straight to underwriter | flagged, with the exact concern |
| Two-wheeler buyer with ID + address | asked for 4 documents | straight through (product checklist) |
| Self-employed without ITR | sent straight to underwriter | flagged: needs `itr_2y`, `business_proof` |

Full framework write-up: [FRAMEWORK.md](FRAMEWORK.md).

## Run it

```bash
pip install -r requirements-dev.txt
uvicorn app:app --reload        # http://127.0.0.1:8000/docs
python -m pytest -q             # original 8 tests + service/API tests
python run_evals.py
python compare_v1_v2.py
python cli.py                   # v1 CLI still works
```

Docker: `docker build -t readydesk . && docker run -p 8000:8000 -v readydesk-data:/data readydesk` · Render: `render.yaml`.

```bash
curl -X POST localhost:8000/check -H 'content-type: application/json' -d '{"application_id":"A1","product":"personal_loan","applicant_type":"self_employed","documents":["id_proof","address_proof","bank_statement"],"fields":{"applicant_name":"Asha Rao","loan_amount":350000,"monthly_income":62000,"pan_number":"ABCDE1234F","phone_number":"9876543210"}}'
```

| Endpoint | Purpose |
|---|---|
| `POST /check` | Route, confidence, missing documents, issues, resubmission diff, applicant message, trace |
| `POST /feedback` | Underwriter verdict → threshold learning |
| `GET /insights` | Most common issues, guardrails, current thresholds |

---

## The original engine (v1)

The v1 demo still runs unchanged; the service wraps it.

A confidence-gated completeness checker for loan application intake. Before
an application reaches an underwriter, ReadyDesk screens it for missing
documents, missing or invalid fields, and formatting errors — then routes
it based on how confident the system is that the application is actually
ready for the underwriter's desk.

### Why confidence gating

A single "is this complete? yes/no" check hides its own error rate. Instead
of one binary answer, ReadyDesk reports a confidence score and routes on
three bands:

| Band | Confidence | Route |
|---|---|---|
| High | ≥ 0.85 | Straight to the underwriter |
| Medium | 0.55–0.85 | Flagged for review, with the *specific* concern named |
| Low | < 0.55 | Returned to the applicant with an explanation |

The underwriter still substantively reviews every loan — this gate only
screens intake completeness — so the cost of an occasional false "complete"
is low (it gets caught downstream), which is why the high band can sit at a
confident-but-not-paranoid 0.85 rather than something more conservative.
Full rationale for each threshold is in the code comments.

### Demo

```
$ python cli.py

--- Application: clean ---
Route:      direct_to_underwriter
Confidence: 1.00
Missing documents: none
Field issues: none

--- Application: minor_issues ---
Route:      flag_for_review
Confidence: 0.79
Missing documents: address_proof
Field issues:
  - pan_number: invalid format ('abcde1234f')

--- Application: serious_issues ---
Route:      return_to_applicant
Confidence: 0.25
Missing documents: income_proof, bank_statement, address_proof
Field issues:
  - applicant_name: missing
  - pan_number: invalid format ('12345')
  - phone_number: invalid format ('12345')
  - loan_amount: must be greater than zero
  - monthly_income: not numeric ('N/A')
```

All three routing outcomes land exactly where the confidence bands predict,
and the medium/low bands produce a specific, actionable concern list rather
than a generic "needs review" flag.

### Honest disclosure on the model backend

No external LLM API key was available when this was built, so
`call_llm_analysis()` is a deterministic rule-based analyzer standing in
for a real LLM call — disclosed honestly in the code rather than faked. The
function is written exactly like the real call would be (structured prompt
in, structured JSON out) and is the single swap point for a live API
integration; nothing else in the file needs to change.

### Project layout

```
cli.py                    Entry point — runs the 3 sample applications
confidence_gate.py         Core gating logic, thresholds, and rationale
test_confidence_gate.py    pytest suite (8/8 passing)
run_output.txt             Captured real output from `python cli.py`
```

### Tests

```
$ python -m pytest test_confidence_gate.py -v
8 passed
```
