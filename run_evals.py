#!/usr/bin/env python3
"""
ReadyDesk eval gate. Segments:
  v1_samples     the 3 original applications route exactly as in v1
  hard_cases     product checklists, expiry, freshness, name/income consistency
  resubmission   a second submission names what was fixed and what is still open
  feedback       false-complete verdicts raise the threshold; bounded; logged
"""

from confidence_gate import TEST_APPLICATIONS
from gen4 import KnowledgeBase, LLMClient, Memory
from gen4.evals import EvalCase, gate, print_and_exit, run_eval
from hard_cases import FOUR, HARD_CASES, OK_FIELDS, TODAY
from service import ReadyDeskService


def fresh():
    return ReadyDeskService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def system(inp):
    svc = fresh()
    if inp[0] == "route":
        return svc.check(inp[1], today=TODAY)["route"]
    if inp[0] == "resubmit":
        first = {"application_id": "A1", "documents": ["id_proof"], "fields": OK_FIELDS}
        svc.check(first, today=TODAY)
        second = svc.check({**first, "documents": FOUR[:3]}, today=TODAY)
        return (sorted(second["resubmission"]["fixed"]), second["resubmission"]["still_open"])
    if inp[0] == "feedback":
        for k in range(30):
            r = svc.check({"application_id": f"x{k}", "documents": FOUR, "fields": OK_FIELDS}, today=TODAY)
            svc.underwriter_verdict(r["decision_id"], actually_complete=(k % 3 != 0))
        hist = svc.memory.param_history("high_threshold")
        return (svc.thresholds()["high"] > 0.85, svc.thresholds()["high"] <= 0.95, bool(hist))
    raise ValueError(inp)


V1 = {"clean": "direct_to_underwriter", "minor_issues": "flag_for_review", "serious_issues": "return_to_applicant"}
cases = [EvalCase(n, ("route", a), V1[n], "v1_samples") for n, a in TEST_APPLICATIONS.items()]
cases += [EvalCase(i, ("route", a), exp, "hard_cases", why) for i, a, exp, why in HARD_CASES]
cases.append(EvalCase("resubmission-diff", ("resubmit",),
                      (["bank_statement", "income_proof"], ["address_proof"]), "resubmission"))
cases.append(EvalCase("false-complete-tightens", ("feedback",), (True, True, True), "feedback"))

if __name__ == "__main__":
    report = run_eval(cases, system, runs=3)
    ok, why = gate(report, min_accuracy=1.0, min_consistency=1.0)
    print_and_exit("ReadyDesk", report, ok, why)
