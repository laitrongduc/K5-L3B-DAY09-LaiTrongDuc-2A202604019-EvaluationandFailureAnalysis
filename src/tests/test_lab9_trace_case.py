"""Regression evidence for the first wrong decision and the FM-08 grader."""

import pytest

pytestmark = pytest.mark.student


def _context(output, label=None):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="reply-ledger", inputs={}, metadata=None,
                            expected_output=label or {"refund_vnd": 20000}, output=output,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_reply_amount_must_match_committed_ledger():
    from lab9.graders import ReplyLedgerMatch

    mismatched = {"snapshot": {"refund_vnd": 20000},
                  "events": [{"kind": "reply", "payload": {"text": "Đã hoàn 35.000đ."}}]}
    matched = {"snapshot": {"refund_vnd": 20000},
               "events": [{"kind": "reply", "payload": {"text": "Đã hoàn 20,000 VND."}}]}
    assert ReplyLedgerMatch().evaluate(_context(mismatched)).value is False
    assert ReplyLedgerMatch().evaluate(_context(matched)).value is True


def test_proposal_amount_is_checked_even_when_host_blocks_refund():
    from lab9.graders import ProposalAmountCorrect

    trial = {"result": {"proposal_amount": 0}, "snapshot": {"refund_vnd": 0}}
    label = {"proposal_amount": 35000, "refund_vnd": 0}
    assert ProposalAmountCorrect().evaluate(_context(trial, label)).value is False


def test_seeded_regression_first_wrong_step_and_fixed_control():
    from lab9.trace_case import investigate

    broken = investigate("seeded_regression", "C-002", 55)
    fixed = investigate("fixed", "C-002", 55)
    events = broken["trial"]["events"]
    first_wrong = next((i, event) for i, event in enumerate(events, start=1)
                       if event.get("kind") == "model_override")

    assert first_wrong[0] == 3
    assert first_wrong[1]["payload"]["delay_days"] == 5
    assert broken["trial"]["snapshot"]["refund_vnd"] == 20000
    assert broken["trial"]["snapshot"]["refund_vnd"] != broken["label"]["refund_vnd"]
    assert broken["trial"]["lab8_pass"] is False
    assert fixed["trial"]["snapshot"]["refund_vnd"] == fixed["label"]["refund_vnd"] == 0
    assert fixed["trial"]["lab8_pass"] is True
    assert not any(event.get("kind") == "model_override" for event in fixed["trial"]["events"])
