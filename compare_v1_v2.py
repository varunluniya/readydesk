#!/usr/bin/env python3
"""Prove-It: v1 vs v2 routing on the 3 original applications + 6 hard cases."""
from confidence_gate import TEST_APPLICATIONS, confidence_gated_response
from gen4 import KnowledgeBase, LLMClient, Memory
from hard_cases import HARD_CASES, TODAY
from service import ReadyDeskService

V1_EXPECTED = {"clean": "direct_to_underwriter", "minor_issues": "flag_for_review",
               "serious_issues": "return_to_applicant"}


def v1_route(app):
    flat = {**app, "documents": [d["type"] if isinstance(d, dict) else d for d in app.get("documents", [])]}
    return confidence_gated_response(flat).route


svc = ReadyDeskService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))
rows = [(n, a, V1_EXPECTED[n], "original sample") for n, a in TEST_APPLICATIONS.items()] + HARD_CASES
ok1 = ok2 = 0
print(f"{'case':<36}{'correct':<24}{'v1':<24}{'v2':<24}")
for name, app, exp, why in rows:
    r1, r2 = v1_route(app), svc.check(app, today=TODAY)["route"]
    ok1 += r1 == exp
    ok2 += r2 == exp
    print(f"{name:<36}{exp:<24}{r1 + ('' if r1 == exp else ' ✗'):<24}{r2 + ('' if r2 == exp else ' ✗'):<24}")
print(f"\nv1 correct: {ok1}/{len(rows)}   v2 correct: {ok2}/{len(rows)}")
