"""Check retrieval source balancing: keep conceptual material in the context.

An embedding model can rank homework problem statements above the handout that
explains the method, leaving the assistant with the question restated and nothing
to teach from. These rules are what prevent that.
"""
from aita_core.rag import _balance_sources


class _Cfg:
    def __init__(self, rule="", max_hw=2):
        self.retrieval_source_balance = rule
        self.retrieval_max_homework = max_hw


def mk(*flags):  # True = homework chunk
    return [(f, {"source": ("Homework: HW%d.pdf" % i) if f else ("Handout: %d.pdf" % i)})
            for i, f in enumerate(flags)]


def labels(sel):
    return [("HW" if is_hw else "CONCEPT") for is_hw, _ in sel]


def test_no_rule_is_pure_score_order():
    e = mk(True, True, True, True, True, False)
    assert labels(_balance_sources(e, 5, _Cfg())) == ["HW"] * 5


def test_guarantee_swaps_weakest_when_all_homework():
    e = mk(True, True, True, True, True, False)   # conceptual sits at rank 6
    out = _balance_sources(e, 5, _Cfg("guarantee"))
    assert labels(out) == ["HW", "HW", "HW", "HW", "CONCEPT"]
    assert len(out) == 5  # still k chunks, not k+1


def test_guarantee_is_a_no_op_when_already_mixed():
    e = mk(True, True, False, True, True, False)
    assert labels(_balance_sources(e, 5, _Cfg("guarantee"))) == labels(e[:5])


def test_guarantee_leaves_it_alone_when_nothing_conceptual_exists():
    e = mk(True, True, True)          # homework is genuinely all there is
    assert labels(_balance_sources(e, 5, _Cfg("guarantee"))) == ["HW"] * 3


def test_cap_limits_homework_and_backfills():
    e = mk(True, True, True, True, False, False, False)
    out = _balance_sources(e, 5, _Cfg("cap", max_hw=2))
    assert labels(out) == ["HW", "HW", "CONCEPT", "CONCEPT", "CONCEPT"]


def test_cap_falls_short_rather_than_inventing_chunks():
    e = mk(True, True, True, True)    # only 2 homework allowed, nothing to backfill
    out = _balance_sources(e, 5, _Cfg("cap", max_hw=2))
    assert labels(out) == ["HW", "HW"]


def test_fewer_eligible_than_k():
    e = mk(False, True)
    for rule in ("", "guarantee", "cap"):
        assert len(_balance_sources(e, 5, _Cfg(rule))) == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok: score order preserved, guarantee swaps only when starved, cap backfills")
