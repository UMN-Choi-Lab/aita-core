"""Homework injection: matched by number, the named HW wins, other homework is dropped."""
from types import SimpleNamespace

try:
    import numpy as np
    import faiss
    from aita_core import rag
except ImportError as e:  # faiss/deps not present in this env
    import sys
    print(f"skip: {e}")
    sys.exit(0)

LABELS = ["Homework: hw00.pdf", "Homework: hw02.pdf", "Homework: hw02_starter.ipynb",
          "Homework: HW10.pdf", "Handout: newtons_method.pdf"]


def _fake_index():
    """Five one-hot chunks; the query leans hw02.pdf > starter, and HW10 above both."""
    index = faiss.IndexFlatIP(5)
    index.add(np.eye(5, dtype="float32"))
    rag._index = index
    rag._chunks = [{"text": l, "metadata": {"source_label": l, "source": l}} for l in LABELS]
    rag._embed_query = lambda q: np.array([[0.1, 0.5, 0.3, 0.9, 0.2]], dtype="float32")
    rag.get_config = lambda: SimpleNamespace(week_to_hw={5: "HW2"})


def _chunk(label):
    return {"text": label, "source": label, "file_path": label, "score": 0.7}


def test_number_from_label():
    assert rag._hw_number("Homework: hw02.pdf") == 2       # 3101's file names
    assert rag._hw_number("Homework: HW2.pdf") == 2        # 3102 / 3201's
    assert rag._hw_number("Homework: hw00_starter.ipynb") == 0
    assert rag._hw_number("Homework: HW10.pdf") == 10      # "HW1" in it, but not HW1
    assert rag._hw_number("Handout: newtons_method.pdf") is None


def test_named_hw_replaces_the_wrong_one():
    _fake_index()
    got = [c["source"] for c in rag._inject_hw(
        "HW02 task 2: can you help me get started",
        [_chunk(LABELS[0]), _chunk(LABELS[4])], current_week=5)]
    assert got == ["Homework: hw02.pdf", "Homework: hw02_starter.ipynb",
                   "Handout: newtons_method.pdf"], got


def test_hw1_never_pulls_hw10():
    _fake_index()
    got = [c["source"] for c in rag._inject_hw("hw1 question", [_chunk(LABELS[3])], 5)]
    assert got == [], got


def test_bare_homework_means_the_current_one():
    _fake_index()
    got = [c["source"] for c in rag._inject_hw("how do I start the homework",
                                               [_chunk(LABELS[0])], current_week=5)]
    assert got == ["Homework: hw02.pdf", "Homework: hw02_starter.ipynb",
                   "Homework: hw00.pdf"], got


def test_no_homework_words_leaves_context_alone():
    _fake_index()
    ctx = [_chunk(LABELS[4])]
    assert rag._inject_hw("what is a jacobian", ctx, 5) == ctx


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
