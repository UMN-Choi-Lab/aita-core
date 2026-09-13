"""build_schedule_block: the model's only source of date/week truth."""
from datetime import date
from types import SimpleNamespace

from aita_core.rag import build_schedule_block


def _cfg(**kw):
    base = dict(
        semester_start="2026-09-07",  # Monday of week 1
        week_topics={1: ["Orientation"], 2: ["Python 101"], 3: ["Root-finding"]},
        meeting_pattern="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_marks_current_week_and_date():
    out = build_schedule_block(_cfg(), 2, today=date(2026, 9, 16))
    assert "Week 2" in out and "Wednesday, September 16, 2026" in out
    assert "<-- CURRENT WEEK" in out
    # the marker lands on week 2's row, not another week's
    row = next(l for l in out.splitlines() if "<-- CURRENT WEEK" in l)
    assert "Week  2" in row


def test_lists_every_week():
    out = build_schedule_block(_cfg(), 1, today=date(2026, 9, 7))
    for wk in (1, 2, 3):
        assert f"Week {wk:>2}" in out


def test_meeting_pattern_optional():
    assert "labs are Wednesday" not in build_schedule_block(_cfg(), 1, today=date(2026, 9, 7))
    out = build_schedule_block(_cfg(meeting_pattern="Labs are Wednesday."), 1,
                               today=date(2026, 9, 7))
    assert "Labs are Wednesday." in out


def test_empty_when_unconfigured():
    assert build_schedule_block(_cfg(semester_start=""), 1) == ""
    assert build_schedule_block(_cfg(week_topics={}), 1) == ""


def test_next_class_rolls_forward_past_end_of_week():
    # Sunday after week 1 -> next meeting is in the following week, not in the past
    out = build_schedule_block(_cfg(), 1, today=date(2026, 9, 13))
    assert "Next class meeting:" in out
    line = next(l for l in out.splitlines() if "Next class meeting" in l)
    assert "September 1" in line or "September 2" in line  # forward, not Sep 07
