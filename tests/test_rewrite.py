"""Follow-up rewrite: only with history, and any failure falls back to the student's words."""
from types import SimpleNamespace

try:
    from aita_core import rag, providers
except ImportError as e:  # faiss/deps not present in this env
    import sys
    print(f"skip: {e}")
    sys.exit(0)

HISTORY = [{"role": "user", "content": "how do I pick x0 for HW02"},
           {"role": "assistant", "content": "Two ways: from daily demand, or from the "
                                            "pump curves. Which one do you want to try?"}]
rag.get_config = lambda: SimpleNamespace()
seen = []


def _llm(reply):
    def fake(cfg, messages):
        seen.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply
    providers.chat_complete = fake


def test_no_history_no_call():
    seen.clear()
    _llm("should not be used")
    assert rag._standalone_query("the second", []) == "the second"
    assert not seen


def test_rewrite_sees_the_assistant_question():
    seen.clear()
    _llm('"HW02 choose x0 from the pump curves"\n')
    assert rag._standalone_query("the second", HISTORY) == "HW02 choose x0 from the pump curves"
    prompt = seen[0][1]["content"]
    assert "Which one do you want to try?" in prompt and "Latest message: the second" in prompt


def test_failures_fall_back():
    for reply in (RuntimeError("vertex down"), "", providers._NO_RESPONSE_MSG,
                  providers._HIGH_DEMAND_MSG, providers._FILTERED_MSG, "x" * 301):
        _llm(reply)
        assert rag._standalone_query("the second", HISTORY) == "the second", reply


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
