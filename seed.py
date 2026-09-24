#!/usr/bin/env python3
"""
Seed ReadyDesk with 4 months of synthetic loan-intake history.

    python seed.py [--reset] [--if-empty]

About 450 applications across personal, two-wheeler and home loans
(salaried and self-employed), each with realistic defects: missing
documents, lowercase or short PANs, 9-digit phone numbers, expired IDs,
stale bank statements, name spellings that differ from the ID, and income
figures that don't match the salary slip. A quarter of applicants fix the
problems and resubmit, so resubmission memory has history. Underwriters
give a verdict on 70% of files, so the threshold feedback loop has
evidence. Names and numbers are synthetic.
"""

from datetime import timedelta
from pathlib import Path

from checklists import required_documents
from gen4 import Memory
from gen4.seedkit import NOW, already_seeded, args, iso, mark
from service import ReadyDeskService

N, DAYS = 360, 120
FIRST = ["Asha", "Rahul", "Meera", "Imran", "Priya", "Vikram", "Neha", "Arjun", "Farah", "Sanjay", "Kavya", "Rohan"]
LAST = ["Rao", "Mehta", "Iyer", "Khan", "Sharma", "Patil", "Nair", "Gupta", "Desai", "Kulkarni", "Singh", "Joshi"]
PRODUCTS = [("personal_loan", 0.55, (50_000, 800_000)), ("two_wheeler", 0.30, (60_000, 220_000)),
            ("home_loan", 0.15, (1_500_000, 9_000_000))]


def pan(rng):
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(rng.choice(L) for _ in range(5)) + f"{rng.randint(0, 9999):04d}" + rng.choice(L)


def make(rng, i, today):
    prod = rng.choices([p for p, _, _ in PRODUCTS], [w for _, w, _ in PRODUCTS])[0]
    lo, hi = next(r for p, _, r in PRODUCTS if p == prod)
    atype = "self_employed" if rng.random() < 0.3 else "salaried"
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    amount = round(rng.uniform(lo, hi), -3)
    income = round(rng.uniform(25_000, 250_000), -3)
    fields = {"applicant_name": name, "loan_amount": amount, "monthly_income": income,
              "pan_number": pan(rng), "phone_number": f"9{rng.randint(100000000, 999999999)}"}
    docs = []
    for d in required_documents(prod, atype, amount):
        if rng.random() < 0.12:
            continue                                                   # missing
        doc = {"type": d}
        if d == "id_proof":
            doc["name_on_doc"] = name if rng.random() > 0.06 else name.replace(" ", " K. ")
            doc["valid_until"] = (today + timedelta(days=rng.randint(-200, 3000))).isoformat()
        if d == "bank_statement":
            doc["period_end"] = (today - timedelta(days=rng.choice([10, 20, 35, 60, 150]))).isoformat()
        if d == "income_proof":
            doc["monthly_income"] = income if rng.random() > 0.08 else round(income * rng.uniform(0.5, 0.75), -3)
            doc["issued_on"] = (today - timedelta(days=rng.randint(5, 120))).isoformat()
        docs.append(doc)
    if rng.random() < 0.07:
        fields["pan_number"] = fields["pan_number"].lower()
    if rng.random() < 0.05:
        fields["phone_number"] = fields["phone_number"][:9]
    if rng.random() < 0.03:
        fields["monthly_income"] = "N/A"
    return {"application_id": f"APP-{50000 + i}", "product": prod, "applicant_type": atype,
            "documents": docs, "fields": fields}


def fix(app, result, today):
    """What a diligent applicant does after being told what's wrong."""
    fixed = {**app, "fields": dict(app["fields"]), "documents": [dict(d) for d in app["documents"]]}
    have = {d["type"] for d in fixed["documents"]}
    for d in result["missing_documents"]:
        if d not in have:
            fixed["documents"].append({"type": d})
    for d in fixed["documents"]:
        if d["type"] == "id_proof":
            d["valid_until"] = (today + timedelta(days=1500)).isoformat()
            d["name_on_doc"] = fixed["fields"]["applicant_name"]
        if d["type"] == "bank_statement":
            d["period_end"] = (today - timedelta(days=5)).isoformat()
    fixed["fields"]["pan_number"] = str(fixed["fields"]["pan_number"]).upper()
    return fixed


def main():
    a, rng = args("data/readydesk.db", "Seed ReadyDesk with synthetic intake history")
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    mem = Memory(a.db)
    if a.if_empty and already_seeded(mem):
        print(f"{a.db} already has data -- skipping seed")
        return
    svc = ReadyDeskService(memory=mem)
    s = {"applications": 0, "submissions": 0, "resubmissions": 0, "direct": 0, "flagged": 0, "returned": 0,
         "underwriter_verdicts": 0}
    jobs = sorted(((rng.uniform(3, DAYS), i) for i in range(N)), reverse=True)
    for days_ago, i in jobs:
        today = (NOW - timedelta(days=days_ago)).date()
        app = make(rng, i, today)
        r = svc.check(app, today=today)
        s["applications"] += 1
        s["submissions"] += 1
        mem.backdate(r["decision_id"], iso(days_ago))
        if r["route"] != "direct_to_underwriter" and rng.random() < 0.35:
            later = days_ago - rng.uniform(0.5, 3)
            r = svc.check(fix(app, r, today), today=(NOW - timedelta(days=later)).date())
            s["submissions"] += 1
            s["resubmissions"] += 1
            mem.backdate(r["decision_id"], iso(later))
            days_ago = later
        s[{"direct_to_underwriter": "direct", "flag_for_review": "flagged",
           "return_to_applicant": "returned"}[r["route"]]] += 1
        if r["route"] != "return_to_applicant" and rng.random() < 0.7:
            truly = not r["missing_documents"] and not r["field_issues"]
            truly = truly if rng.random() > 0.06 else not truly    # underwriters find things the gate can't see
            svc.underwriter_verdict(r["decision_id"], truly)
            mem.backdate(r["decision_id"], iso(days_ago), iso(max(0.1, days_ago - 1)))
            s["underwriter_verdicts"] += 1
    mark(mem, "readydesk", a.seed, s)
    learned = svc.learn()
    print(f"seeded {a.db}: {s}")
    print("thresholds:", learned["thresholds"], "| most common issues:", svc.common_issues()[:4])


if __name__ == "__main__":
    main()
