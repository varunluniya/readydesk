"""
ReadyDesk intelligent service — loan intake completeness with Gen-4 layers.

    Retrieval  the checklist for this product x applicant type, freshness and
               consistency rules; every requirement is cited
    Context    product, applicant type, loan amount (high-value rules), today's
               date (document freshness), cross-document facts
    Memory     every submission per application -> resubmission diffs
               ("fixed: X; still missing: Y") and recurring-issue stats
    Feedback   underwriter verdicts (was it actually complete?) move the
               routing threshold in bounded, logged steps

v1 checked one fixed list of four documents and five field formats. v2
knows the checklist differs by product and applicant type, reads document
metadata (expired ID, stale bank statement, name mismatch, income gap),
remembers earlier submissions, and learns from underwriters.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from checklists import FRESH_DAYS, HEADINGS, HIGH_VALUE_ABOVE, INCOME_TOLERANCE, required_documents
from confidence_gate import FIELD_ISSUE_PENALTY, HIGH_THRESH, LOW_THRESH, MISSING_DOC_PENALTY, call_llm_analysis
from gen4 import Context, KnowledgeBase, LLMClient, Memory, Trace
from gen4 import feedback as fb

SYSTEM = "readydesk"
HERE = Path(__file__).parent
STEP = 0.02
HIGH_BOUNDS = (0.75, 0.95)
COOLDOWN = 10


# v1 weighted every field issue equally (0.06). A name that doesn't match the
# ID or a 60% income gap is not the same as a lowercase PAN, so v2 weights by
# severity. Format issues keep v1's weight, so v1's sample routes are unchanged.
SEVERITY = {"does not match ID": 0.16, "gap)": 0.16, "older than": 0.10, "expired on": 0.0}


def _severity(issue: str) -> float:
    for marker, w in SEVERITY.items():
        if marker in issue:
            return w
    return FIELD_ISSUE_PENALTY


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


class ReadyDeskService:
    def __init__(self, memory: Memory | None = None, kb: KnowledgeBase | None = None,
                 llm: LLMClient | None = None):
        self.memory = memory or Memory(os.environ.get("GEN4_DB", HERE / "data" / f"{SYSTEM}.db"))
        self.kb = kb or KnowledgeBase.from_dir(HERE / "knowledge")
        self.llm = llm or LLMClient()

    def thresholds(self) -> dict:
        return {"high": self.memory.get_param("high_threshold", HIGH_THRESH),
                "low": self.memory.get_param("low_threshold", LOW_THRESH)}

    # -- analysis -------------------------------------------------------------------------
    def analyse(self, app: dict, today: date) -> dict:
        product = app.get("product", "personal_loan")
        atype = app.get("applicant_type", "salaried")
        fields = app.get("fields", {})
        docs = [d if isinstance(d, dict) else {"type": d} for d in app.get("documents", [])]
        by_type = {d["type"]: d for d in docs}
        amount = fields.get("loan_amount")
        try:
            amount_f = float(amount)
        except (TypeError, ValueError):
            amount_f = None
        required = required_documents(product, atype, amount_f)
        rules = [HEADINGS[(product, atype)]]
        if amount_f and amount_f > HIGH_VALUE_ABOVE:
            rules.append("High-value applications")

        missing, issues = [], []
        for r in required:
            d = by_type.get(r)
            if d is None:
                missing.append(r)
            elif d.get("valid_until") and date.fromisoformat(d["valid_until"]) < today:
                missing.append(r)
                issues.append(f"{r}: expired on {d['valid_until']}")
                rules.append("Document freshness")

        # v1 field-format checks, unchanged (PAN, phone, name, amounts)
        v1 = call_llm_analysis({"documents": required, "fields": fields})
        issues += v1["field_issues"]

        stale_cut = today - timedelta(days=FRESH_DAYS)
        for t, key in (("bank_statement", "period_end"), ("income_proof", "issued_on")):
            d = by_type.get(t)
            if d and d.get(key) and date.fromisoformat(d[key]) < stale_cut:
                issues.append(f"{t}: dated {d[key]}, older than {FRESH_DAYS} days")
                rules.append("Document freshness")
        idp = by_type.get("id_proof")
        if idp and idp.get("name_on_doc") and fields.get("applicant_name") and \
                _norm_name(idp["name_on_doc"]) != _norm_name(fields["applicant_name"]):
            issues.append(f"applicant_name: '{fields['applicant_name']}' does not match ID ('{idp['name_on_doc']}')")
            rules.append("Cross-document consistency")
        inc = by_type.get("income_proof")
        try:
            stated = float(fields.get("monthly_income"))
            slip = float(inc["monthly_income"]) if inc and inc.get("monthly_income") is not None else None
        except (TypeError, ValueError):
            stated, slip = None, None
        if stated and slip and abs(stated - slip) / slip > INCOME_TOLERANCE:
            issues.append(f"monthly_income: stated {stated:,.0f} vs salary slip {slip:,.0f} (>20% gap)")
            rules.append("Cross-document consistency")

        missing = list(dict.fromkeys(missing))
        issues = list(dict.fromkeys(issues))
        penalty = MISSING_DOC_PENALTY * len(missing) + sum(_severity(i) for i in issues)
        conf = round(max(0.0, 1.0 - penalty), 2)
        return {"required_documents": required, "missing_documents": missing, "field_issues": issues,
                "confidence": conf, "rules": list(dict.fromkeys(rules)), "product": product,
                "applicant_type": atype}

    # -- decision -----------------------------------------------------------------------------
    def check(self, app: dict, today: date | None = None) -> dict:
        today = today or date.today()
        trace = Trace()
        a = self.analyse(app, today)
        t = self.thresholds()
        trace.params = t
        c = a["confidence"]
        route = ("direct_to_underwriter" if c >= t["high"] else
                 "flag_for_review" if c >= t["low"] else "return_to_applicant")
        if route == "direct_to_underwriter" and a["missing_documents"]:
            # v1 let one missing document through at exactly 0.85; a required
            # document can't be "confidently complete" while absent.
            route = "flag_for_review"
        rules = a["rules"] + ["Routing bands"]

        app_id = app.get("application_id")
        prev = self.memory.history(f"application:{app_id}", limit=1) if app_id else []
        diff = None
        if prev:
            p = prev[0]["output"]
            fixed = [x for x in p["missing_documents"] + p["field_issues"]
                     if x not in a["missing_documents"] + a["field_issues"]]
            diff = {"submission": len(self.memory.history(f"application:{app_id}")) + 1, "fixed": fixed,
                    "still_open": a["missing_documents"] + a["field_issues"]}
            rules.append("Resubmissions")
        common = self.common_issues()
        trace.context = (Context().add("product", a["product"]).add("applicant_type", a["applicant_type"])
                         .add("today", today.isoformat(), "document freshness").add(
                             "required_documents", a["required_documents"])).as_dict()
        trace.memory = {"previous_submissions": len(prev), "resubmission": diff,
                        "most_common_issues": common[:3]}
        passages = []
        for r in dict.fromkeys(rules):
            passages += self.kb.search(r, k=1)
        trace.cite({(p.source, p.heading): p for p in passages}.values())
        msg = self._message(route, a, diff) if route != "direct_to_underwriter" else ""
        trace.model = {"provider": self.llm.last_provider}

        out = {"application_id": app_id, "route": route, "confidence": c,
               "missing_documents": a["missing_documents"], "field_issues": a["field_issues"],
               "required_documents": a["required_documents"], "resubmission": diff, "applicant_message": msg}
        did = self.memory.record_decision(SYSTEM, f"application:{app_id or 'unidentified'}", {"product": a["product"],
                                          "applicant_type": a["applicant_type"]}, out)
        return {"decision_id": did, **out, "trace": trace.as_dict()}

    def _message(self, route: str, a: dict, diff: dict | None) -> str:
        def offline():
            parts = []
            if diff and diff["fixed"]:
                parts.append("Thanks, these are now sorted: " + "; ".join(diff["fixed"]) + ".")
            if a["missing_documents"]:
                parts.append("Please upload: " + ", ".join(d.replace("_", " ") for d in a["missing_documents"]) + ".")
            if a["field_issues"]:
                parts.append("Please correct: " + "; ".join(a["field_issues"]) + ".")
            if route == "flag_for_review":
                parts.append("Your application is with our team meanwhile; fixing these speeds it up.")
            return " ".join(parts)
        return self.llm.complete(f"Write a short, polite message to a loan applicant. Route: {route}. "
                                 f"Missing: {a['missing_documents']}. Issues: {a['field_issues']}. "
                                 f"Fixed since last time: {diff and diff['fixed']}.", offline=offline, max_tokens=200)

    def common_issues(self) -> list[tuple[str, int]]:
        cnt = Counter()
        for d in self.memory.decisions(system=SYSTEM, limit=500):
            cnt.update(d["output"]["missing_documents"])
            cnt.update(i.split(":")[0] for i in d["output"]["field_issues"])
        return cnt.most_common(5)

    # -- feedback -------------------------------------------------------------------------------
    def underwriter_verdict(self, decision_id: str, actually_complete: bool) -> dict:
        if not self.memory.record_outcome(decision_id, {"actually_complete": actually_complete}):
            raise KeyError(decision_id)
        return self.learn()

    def learn(self, window: int = 200, min_n: int = 20) -> dict:
        done = self.memory.decisions(system=SYSTEM, with_outcome=True, limit=window)
        direct = [d for d in done if d["output"]["route"] == "direct_to_underwriter"]
        flagged = [d for d in done if d["output"]["route"] == "flag_for_review"]
        false_complete = fb.Guardrail("false_complete_rate", 0.10, min_n).check(
            sum(1 for d in direct if not d["outcome"]["actually_complete"]), len(direct))
        needless_flag = fb.Guardrail("needless_flag_rate", 0.60, min_n).check(
            sum(1 for d in flagged if d["outcome"]["actually_complete"]), len(flagged))
        high = self.thresholds()["high"]
        action = None
        last = self.memory.get_param("high_threshold_n", 0)
        if len(done) - last >= COOLDOWN:  # at most one step per 10 new verdicts
            if false_complete["tripped"] and high < HIGH_BOUNDS[1]:
                new = round(min(HIGH_BOUNDS[1], high + STEP), 3)
                self.memory.set_param("high_threshold", new, "false-complete rate above 10% (lower bound)")
                action = f"high threshold {high} -> {new}"
            elif needless_flag["tripped"] and high > HIGH_BOUNDS[0]:
                new = round(max(HIGH_BOUNDS[0], high - STEP), 3)
                self.memory.set_param("high_threshold", new, "most flagged applications were complete")
                action = f"high threshold {high} -> {new}"
            self.memory.set_param("high_threshold_n", len(done))
        return {"false_complete": false_complete, "needless_flag": needless_flag, "action": action,
                "thresholds": self.thresholds()}
