"""Current-homework resolver: exact week, else next upcoming, else most recent past."""
from types import SimpleNamespace

try:
    from aita_core.rag import _resolve_current_hw
except ImportError as e:  # faiss/deps not present in this env
    import sys
    print(f"skip: {e}")
    sys.exit(0)

# week_to_hw is DUE-week -> label; HW1 is due week 2, so week 1 has no exact match.
W2H = {2: "HW1", 3: "HW2", 4: "HW3", 5: "HW4", 6: "HW5", 7: "HW6",
       9: "HW7", 10: "HW8", 11: "HW9", 12: "HW10", 13: "HW11", 14: "HW12"}
cfg = SimpleNamespace(week_to_hw=W2H)


def test_forward_when_no_exact_match():
    assert _resolve_current_hw(cfg, 1) == "HW1"   # week 1 -> upcoming HW1 (due wk2)
    assert _resolve_current_hw(cfg, 8) == "HW7"   # gap week -> upcoming HW7 (due wk9)


def test_exact_week_match():
    assert _resolve_current_hw(cfg, 2) == "HW1"
    assert _resolve_current_hw(cfg, 9) == "HW7"


def test_past_fallback_after_last_hw():
    assert _resolve_current_hw(cfg, 20) == "HW12"


def test_no_schedule_returns_none():
    assert _resolve_current_hw(SimpleNamespace(week_to_hw={}), 1) is None


if __name__ == "__main__":
    test_forward_when_no_exact_match()
    test_exact_week_match()
    test_past_fallback_after_last_hw()
    test_no_schedule_returns_none()
    print("ok: week1 ->", _resolve_current_hw(cfg, 1))
