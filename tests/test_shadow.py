"""Shadow logging: off by default, isolated from the student's turn when on.

The two invariants worth guarding are the ones that fail silently in production:
the live config must not pick up the shadow model, and the shadow must see the
prompt as it was sent, not as the caller later mutated it.
"""
import dataclasses
import sqlite3

from aita_core import db, providers, shadow


@dataclasses.dataclass
class _Cfg:
    data_dir: str
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_temperature: float = 0
    llm_max_output_tokens: int = 0
    llm_extra_params: dict = dataclasses.field(default_factory=dict)


def _setup(monkeypatch, tmp_path, reply="SHADOW REPLY"):
    """Point the db and shadow at a scratch database; capture the shadow call."""
    cfg = _Cfg(data_dir=str(tmp_path))
    monkeypatch.setattr(db, "get_config", lambda: cfg)
    monkeypatch.setattr(db, "_initialized", False)
    monkeypatch.setattr(shadow, "get_config", lambda: cfg)

    seen = {}

    def fake_complete(call_cfg, messages):
        seen["cfg"] = call_cfg
        seen["messages"] = messages
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(providers, "chat_complete", fake_complete)
    return cfg, seen


def _rows(tmp_path):
    conn = sqlite3.connect(tmp_path / "aita.db")
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM shadow_interactions")]
    conn.close()
    return rows


def test_off_unless_configured(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.delenv("AITA_SHADOW_MODEL", raising=False)
    assert shadow.fire([{"role": "user", "content": "hi"}], 1, "live") is None
    assert seen == {}  # no model was called at all


def test_logs_the_pair(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire([{"role": "user", "content": "hi"}], 42, "live answer").join(5)

    (row,) = _rows(tmp_path)
    assert row["interaction_id"] == 42
    assert row["model"] == "gpt-6-luna"
    assert row["baseline_response"] == "live answer"
    assert row["shadow_response"] == "SHADOW REPLY"
    assert row["error"] is None
    assert row["latency_ms"] >= 0
    # Routed over the OpenAI protocol with reasoning off, so temperature=0 holds.
    assert seen["cfg"].llm_provider == "openai"
    assert seen["cfg"].llm_model == "gpt-6-luna"
    assert seen["cfg"].llm_extra_params == {"reasoning_effort": "none"}


def test_live_config_is_not_rewritten(monkeypatch, tmp_path):
    """A leaked override here would serve the shadow model to students."""
    cfg, _seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire([{"role": "user", "content": "hi"}], 1, "live").join(5)

    assert cfg.llm_provider == "gemini"
    assert cfg.llm_model == "gemini-3.5-flash-lite"
    assert cfg.llm_extra_params == {}


def test_prompt_is_snapshotted(monkeypatch, tmp_path):
    """app.py keeps appending to the chat history after the shadow is fired."""
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    messages = [{"role": "user", "content": "original"}]
    thread = shadow.fire(messages, 1, "live")
    messages.append({"role": "assistant", "content": "added later"})
    messages[0]["content"] = "mutated"
    thread.join(5)

    assert seen["messages"] == [{"role": "user", "content": "original"}]


def test_failure_is_recorded_not_raised(monkeypatch, tmp_path):
    _cfg, _seen = _setup(monkeypatch, tmp_path, reply=RuntimeError("gateway down"))
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire([{"role": "user", "content": "hi"}], 7, "live").join(5)

    (row,) = _rows(tmp_path)
    assert row["shadow_response"] is None
    assert "RuntimeError: gateway down" in row["error"]


def test_extra_params_override(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    monkeypatch.setenv("AITA_SHADOW_EXTRA_PARAMS", '{"reasoning_effort": "low"}')
    shadow.fire([{"role": "user", "content": "hi"}], 1, "live").join(5)

    assert seen["cfg"].llm_extra_params == {"reasoning_effort": "low"}
