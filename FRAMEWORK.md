# ReadyDesk — FDE Framework Build Notes

## Part 1 — Problem Reframing

| Step | Output |
|---|---|
| Ordinary problem | "Check that loan applications are complete before underwriting." |
| Lever 1: Data liquidity | Document metadata (expiry dates, statement periods, the name printed on the ID, the income on the salary slip) is captured at upload and never compared with the form. Underwriters' "this wasn't actually complete" judgements are never fed back. |
| Lever 2: Network effect | Every underwriter verdict tunes the routing threshold. Recurring issues across applicants show which form fields need better guidance. |
| Lever 3: Algorithmic leverage | Product- and applicant-type checklists, freshness and cross-document consistency checks, severity-weighted confidence, and a resubmission diff. |
| Lever 4: First principles × JTBD | The underwriter's job is "only see files I can decide on". The applicant's job is "know exactly what to fix, once". Both are served by precision about *which* requirement failed. |
| Extraordinary problem | **Route each application on whether it is complete for its product and applicant type, today**, catch the inconsistencies a format check can't see, tell the applicant exactly what to fix (and what they already fixed), and let underwriters' verdicts tune the gate. |
| Rating | 4 / 5 |

## Part 2 — Design the Eval

**Outcome of intelligence**
- v1's three sample applications route exactly as before.
- Six hard cases route correctly: self-employed checklist, expired ID, stale statement plus name mismatch, income gap, the lighter two-wheeler checklist, and the high-value ITR rule.
- A resubmission names what was fixed and what is still open. False-complete verdicts raise the threshold (bounded to 0.75–0.95, cooldown of 10 verdicts).

**EQ(PRE)**
| Angle | Hypothesis |
|---|---|
| Causal | "All four documents present" is taken to mean ready. It isn't, if one is expired, stale or contradicts the form. |
| Context | One checklist is used for every product, so it over-asks two-wheeler buyers and under-asks the self-employed. |
| Consistency | Equal weights for every issue let a material income gap route straight to the underwriter. |

**EQ(POST), cheapest first**
1. Prompt: the applicant message lists exact fixes and acknowledges resubmission progress. The offline template is the floor.
2. Context/retrieval: product checklists, freshness, consistency, severity weights, and "a missing document never goes direct".
3. Feedback: underwriter verdicts drive a false-complete guardrail and a needless-flag guardrail, which move the threshold in bounded steps.

**Executable:** `python run_evals.py` runs 11 cases × 3 runs. The hard-case expectations were written with the severity weights in view, so they are a regression gate, not a held-out test.

## Part 3 — Gen-4 Architecture

| Layer | What ReadyDesk does |
|---|---|
| Retrieval | `knowledge/document_checklists.md`. The checklist, freshness, consistency, routing and resubmission sections are cited per decision. |
| Context | Product, applicant type, loan amount (two-wheeler above 1.5L, any loan above 10L), today's date. |
| Memory | Every submission per application id (resubmission diff) and issue frequency across all applications. |
| Feedback | `POST /feedback` with the underwriter's verdict. The high threshold moves ±0.02 with a cooldown, and every change is logged in `/params`. |

The model writes the applicant message. A live model can also be used to extract fields from free-text notes (future). The offline template is used without a key.

## Part 4 — Implementation Plan

| Component | Priority | Estimate | Status |
|---|---|---|---|
| Product × applicant-type checklists + high-value rule | MVP | 0.5 day | done |
| Document metadata checks (expiry, freshness, name, income) | MVP | 0.5 day | done |
| Severity-weighted confidence + missing-doc floor | MVP | 0.25 day | done |
| Resubmission diff + issue frequency | MVP | 0.25 day | done |
| Underwriter feedback → bounded threshold learning | MVP | 0.25 day | done |
| API, Docker, CI | MVP | 0.5 day | done |
| OCR / DigiLocker ingestion to fill document metadata automatically | future | 3+ days | future |
| LLM extraction from free-text applicant notes | nice-to-have | 0.5 day | future |

## Part 5 — Prove It

**Visible change** (`python compare_v1_v2.py`, output in `run_output_v1_vs_v2.txt`):

| Case | Correct route | v1 | v2 |
|---|---|---|---|
| 3 original samples | as before | ✓ | ✓ |
| Self-employed, no ITR or business proof | flag | direct ✗ | flag ✓ |
| ID expired | flag | direct ✗ | flag ✓ |
| Bank statement 6 months old + ID name differs | flag | direct ✗ | flag ✓ |
| Stated income 62k vs slip 38k | flag | direct ✗ | flag ✓ |
| Two-wheeler under 1.5L with ID + address only | direct | flag ✗ (asked for 4 documents) | direct ✓ |
| ₹15L loan without ITR | flag | direct ✗ | flag ✓ |
| **Total** | | **3 / 9** | **9 / 9** |

An outside observer would see underwriters no longer receiving files with expired IDs or contradictory incomes, two-wheeler buyers no longer being asked for documents their product doesn't need, and applicants who resubmit being told what they fixed.
