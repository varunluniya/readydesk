# ReadyDesk

A confidence-gated completeness checker for loan application intake. Before
an application reaches an underwriter, ReadyDesk screens it for missing
documents, missing or invalid fields, and formatting errors — then routes
it based on how confident the system is that the application is actually
ready for the underwriter's desk.

## Why confidence gating

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

## Demo

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

## Honest disclosure on the model backend

No external LLM API key was available when this was built, so
`call_llm_analysis()` is a deterministic rule-based analyzer standing in
for a real LLM call — disclosed honestly in the code rather than faked. The
function is written exactly like the real call would be (structured prompt
in, structured JSON out) and is the single swap point for a live API
integration; nothing else in the file needs to change.

## Project layout

```
cli.py                    Entry point — runs the 3 sample applications
confidence_gate.py         Core gating logic, thresholds, and rationale
test_confidence_gate.py    pytest suite (8/8 passing)
run_output.txt             Captured real output from `python cli.py`
```

## Tests

```
$ python -m pytest test_confidence_gate.py -v
8 passed
```
