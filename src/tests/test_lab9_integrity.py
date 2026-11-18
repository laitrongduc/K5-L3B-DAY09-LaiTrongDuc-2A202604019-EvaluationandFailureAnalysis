"""Additional M7 integrity checks for traps not covered by the starter vectors."""

import copy

import pytest

pytestmark = pytest.mark.student

SPEC = {
    "eval_set_version": "v2",
    "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                 "threshold": {"min": 0.8}}],
}
ROWS = [{"item_id": f"E-{item:03d}", "seed": seed, "pass_rate": True, "slices": ["money_movement"]}
        for item in range(1, 3) for seed in (11, 22)]


def report(rows=None, failures=None):
    return {"run_id": "test", "manifest": {"eval_set_sha": "abc", "items": 2, "seeds": [11, 22]},
            "rows": copy.deepcopy(ROWS if rows is None else rows),
            "metrics": {"pass_rate": 1.0}, "evaluator_failures": failures or []}


def test_integrity_rejects_duplicate_pair_even_when_row_count_matches():
    from lab9.gate import integrity_check

    rows = copy.deepcopy(ROWS)
    rows[-1] = copy.deepcopy(rows[0])
    assert any("duplicate (item_id, seed)" in problem
               for problem in integrity_check(report(rows), report(), SPEC))


def test_integrity_rejects_evaluator_failure_on_green_report():
    from lab9.gate import integrity_check

    assert any("evaluator_failures" in problem
               for problem in integrity_check(report(failures=["pass_rate: crashed"]), report(), SPEC))


def test_integrity_rejects_missing_row_grader_value():
    from lab9.gate import integrity_check

    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = None
    assert any("has missing pass_rate" in problem
               for problem in integrity_check(report(rows), report(), SPEC))


def test_integrity_rejects_slice_relabeling():
    from lab9.gate import integrity_check

    rows = copy.deepcopy(ROWS)
    rows[0]["slices"] = []
    problems = integrity_check(report(rows), report(), SPEC)
    assert any("slice tags" in problem for problem in problems)


def test_slice_ratchet_rejects_lowering_floor_or_dropping_slice():
    from lab9.gate import integrity_check

    old = {**SPEC, "slices": [{"name": "money_movement", "metric": "pass_rate",
                                "min": 0.9, "no_significant_drop": True, "blocking": True}]}
    looser = {**SPEC, "slices": [{"name": "money_movement", "metric": "pass_rate",
                                  "min": 0.8, "blocking": True}]}
    problems = integrity_check(report(), report(), looser, old)
    assert any("slice money_movement/pass_rate.min may not fall" in problem for problem in problems)
    assert any("removed slice money_movement/pass_rate.no_significant_drop" in problem for problem in problems)
