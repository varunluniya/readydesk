"""
Incremental-loading fix: learn()'s `decisions(..., limit=window)` call looked bounded
because of the LIMIT, but without a watermark SQLite still scanned every
decision this system had ever logged and sorted it by ts to produce that
window (confirmed with EXPLAIN QUERY PLAN) -- the same shape as the classic full-rescan
mistake, just with a capped result size instead of an uncapped one.

The fix keeps the "last `window` verdicts" guardrail sample as a persisted
sliding window that only absorbs NEW outcomes since the last watermark,
instead of re-deriving the whole window from scratch every call. These
tests prove it still slides correctly, stays idempotent across repeated
calls with nothing new, and ages old verdicts out once the window fills.
"""
from datetime import date

from gen4 import KnowledgeBase, LLMClient, Memory
from hard_cases import FOUR, OK_FIELDS, TODAY
from service import ReadyDeskService


def _svc():
    return ReadyDeskService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_learn_is_idempotent_no_double_counting():
    svc = _svc()
    for k in range(15):
        r = svc.check({"application_id": f"a{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)

    first = svc.learn()
    second = svc.learn()
    third = svc.learn()
    assert first["false_complete"]["n"] == second["false_complete"]["n"] == third["false_complete"]["n"]
    assert first["needless_flag"]["n"] == second["needless_flag"]["n"] == third["needless_flag"]["n"]


def test_learn_picks_up_new_verdicts_after_more_are_recorded():
    svc = _svc()
    for k in range(5):
        r = svc.check({"application_id": f"b{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)
    first = svc.learn()

    for k in range(5, 12):
        r = svc.check({"application_id": f"b{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)
    second = svc.learn()

    assert second["needless_flag"]["n"] > first["needless_flag"]["n"]
    assert second["needless_flag"]["n"] == 12


def test_sliding_window_ages_out_old_verdicts_once_full():
    """The guardrail's sample is a bounded, most-recent-`window` window by
    design (not an all-time cumulative count) -- verify the incremental
    ring buffer actually ages old entries out instead of growing forever."""
    svc = _svc()
    window = 20
    for k in range(window):
        r = svc.check({"application_id": f"c{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)
    full = svc.learn(window=window)
    assert full["needless_flag"]["n"] == window

    for k in range(window, window + 5):
        r = svc.check({"application_id": f"c{k}", "documents": FOUR[:3], "fields": OK_FIELDS}, today=TODAY)
        svc.underwriter_verdict(r["decision_id"], actually_complete=True)
    after = svc.learn(window=window)
    # still capped at `window`, not window + 5 -- the oldest 5 verdicts aged out
    assert after["needless_flag"]["n"] == window
