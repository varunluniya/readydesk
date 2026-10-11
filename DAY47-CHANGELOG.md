# Day 47 changelog — ReadyDesk

## Finding

`learn()` calls `self.memory.decisions(system=SYSTEM, with_outcome=True,
limit=window)` — this *looks* bounded because of the `limit`, and
ReadyDesk already had a deliberate, sensible design the other repos
lacked: a bounded recent-window guardrail sample (last `window=200`
verdicts) plus a count-based cooldown (`high_threshold_n`) so the routing
threshold doesn't thrash on every single verdict.

But `EXPLAIN QUERY PLAN` showed the `LIMIT` doesn't protect the query from
Guide 5's Mistake 5: without an index, SQLite still ran a full table
`SCAN` of every decision this system had ever logged, plus a temp B-tree
sort, to produce the `ORDER BY ts DESC` before it could take the top
`window` rows. Cost grows with total decision count regardless of how
small the window or the result size is.

## Changes

- `gen4/memory.py` — added a `(system, ts DESC)` index on `decisions`,
  confirmed via `EXPLAIN QUERY PLAN` to turn the full `SCAN` + temp-sort
  into a direct index `SEARCH` in ts-descending order. Plus the shared
  kernel fixes from LendFair's changelog (`fact_history`,
  `decisions(outcome_since=...)`, the `outcome_ts` fix).

- `service.py`
  - `learn()` rewritten. Because the "last `window` verdicts" sample is
    real business logic (a deliberately bounded, recent-only guardrail
    sample, not an all-time cumulative count), this doesn't switch to pure
    cumulative accumulation like the other repos — instead it keeps a
    persisted sliding window (`ring:{LEARN_KEY}`): only outcomes newer than
    the watermark are appended to it, and it's trimmed back down to
    `window` every call, so a call with nothing new touches zero old rows,
    and old verdicts still age out exactly as before.
    `LEARN_KEY = "readydesk_learn"`, `LEARN_GRACE_DAYS = 1`.
  - The ring is always re-trimmed to `window` (even when nothing new
    arrived), so a caller is never left with a stale size from an earlier
    call that used a different `window` value. The existing cooldown
    (`high_threshold_n`) logic is otherwise untouched, including its
    pre-existing quirk where it stops firing once the window saturates
    (verified to be the exact same behavior before and after the fix, not
    something introduced by it).

- `tests/test_incremental_learning.py` — new, 3 tests: idempotency,
  picking up new verdicts after more are recorded, and the sliding window
  actually aging old verdicts out once full (not growing unbounded).

## Verification

- `pytest -q` → 23/23 passed (20 original + 3 new).
- `run_evals.py` → GATE PASS, 100%/100%, unchanged.
- `seed.py --reset` → identical to pre-fix baseline (360 applications, 432
  submissions, thresholds `{high: 0.95, low: 0.55}`, identical most-common-
  issues breakdown).
- `compare_v1_v2.py` → identical to pre-fix baseline (v2 9/9 correct vs v1
  3/9).

No behavioral change in any observable output.
