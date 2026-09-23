"""Shadow logging: off by default, isolated from the student's turn when on.

The invariants worth guarding are the ones that fail silently in production: the
live config must not pick up the shadow model, the shadow must see the prompt as
it was sent rather than as the caller later mutated it, and the prompt variant
must be recorded so a mid-week change cannot quietly poison the comparison.
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


def _msgs():
    # build_messages() puts the system prompt and retrieved context first.
    return [{"role": "system", "content": "SYS PROMPT"},
            {"role": "user", "content": "hi"}]


def _setup(monkeypatch, tmp_path, reply="SHADOW REPLY"):
    """Point the db and shadow at a scratch database; capture the shadow call."""
    cfg = _Cfg(data_dir=str(tmp_path))
    monkeypatch.setattr(db, "get_config", lambda: cfg)
    monkeypatch.setattr(db, "_initialized", False)
    monkeypatch.setattr(shadow, "get_config", lambda: cfg)
    monkeypatch.delenv("AITA_SHADOW_PROMPT", raising=False)
    monkeypatch.delenv("AITA_SHADOW_PROMPT_SUFFIX", raising=False)

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
    assert shadow.fire(_msgs(), 1, "live") is None
    assert seen == {}  # no model was called at all


def test_logs_the_pair(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire(_msgs(), 42, "live answer", 2200).join(5)

    (row,) = _rows(tmp_path)
    assert row["interaction_id"] == 42
    assert row["model"] == "gpt-6-luna"
    assert row["baseline_response"] == "live answer"
    assert row["shadow_response"] == "SHADOW REPLY"
    assert row["baseline_latency_ms"] == 2200
    assert row["error"] is None
    assert row["latency_ms"] >= 0
    # Routed over the OpenAI protocol with reasoning off, so temperature=0 holds.
    assert seen["cfg"].llm_provider == "openai"
    assert seen["cfg"].llm_model == "gpt-6-luna"
    assert seen["cfg"].llm_extra_params == {"reasoning_effort": "none"}


def test_tuned_prompt_is_appended_and_tagged(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire(_msgs(), 1, "live").join(5)

    system = seen["messages"][0]["content"]
    assert system.startswith("SYS PROMPT")          # course prompt survives intact
    assert "END WITH ONE GUIDING QUESTION" in system
    assert seen["messages"][1] == {"role": "user", "content": "hi"}
    (row,) = _rows(tmp_path)
    assert row["prompt_variant"].startswith("tuned:")


def test_base_prompt_opt_out(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    monkeypatch.setenv("AITA_SHADOW_PROMPT", "base")
    shadow.fire(_msgs(), 1, "live").join(5)

    assert seen["messages"][0]["content"] == "SYS PROMPT"
    (row,) = _rows(tmp_path)
    assert row["prompt_variant"] == "base"


def test_suffix_override_changes_the_tag(monkeypatch, tmp_path):
    """Two different suffixes must not be recorded under the same variant tag."""
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    monkeypatch.setenv("AITA_SHADOW_PROMPT_SUFFIX", "\n\nBE TERSE.")
    shadow.fire(_msgs(), 1, "live").join(5)

    assert seen["messages"][0]["content"] == "SYS PROMPT\n\nBE TERSE."
    (row,) = _rows(tmp_path)
    assert row["prompt_variant"].startswith("tuned:")
    monkeypatch.delenv("AITA_SHADOW_PROMPT_SUFFIX")
    assert row["prompt_variant"] != shadow._prompt_suffix()[1]   # tag tracks the text


def test_live_config_is_not_rewritten(monkeypatch, tmp_path):
    """A leaked override here would serve the shadow model to students."""
    cfg, _seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire(_msgs(), 1, "live").join(5)

    assert cfg.llm_provider == "gemini"
    assert cfg.llm_model == "gemini-3.5-flash-lite"
    assert cfg.llm_extra_params == {}


def test_prompt_is_snapshotted(monkeypatch, tmp_path):
    """app.py keeps appending to the chat history after the shadow is fired."""
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    messages = _msgs()
    thread = shadow.fire(messages, 1, "live")
    messages.append({"role": "assistant", "content": "added later"})
    messages[1]["content"] = "mutated"
    thread.join(5)

    assert len(seen["messages"]) == 2
    assert seen["messages"][1] == {"role": "user", "content": "hi"}


def test_failure_is_recorded_not_raised(monkeypatch, tmp_path):
    _cfg, _seen = _setup(monkeypatch, tmp_path, reply=RuntimeError("gateway down"))
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire(_msgs(), 7, "live").join(5)

    (row,) = _rows(tmp_path)
    assert row["shadow_response"] is None
    assert "RuntimeError: gateway down" in row["error"]


def test_extra_params_override(monkeypatch, tmp_path):
    _cfg, seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    monkeypatch.setenv("AITA_SHADOW_EXTRA_PARAMS", '{"reasoning_effort": "low"}')
    shadow.fire(_msgs(), 1, "live").join(5)

    assert seen["cfg"].llm_extra_params == {"reasoning_effort": "low"}


def test_migration_adds_columns_to_an_existing_table(monkeypatch, tmp_path):
    """3101 and 3102 already have the pre-0.7.3 table on their volumes."""
    path = tmp_path / "aita.db"
    old = sqlite3.connect(path)
    old.execute("""CREATE TABLE shadow_interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, interaction_id INTEGER,
        timestamp TEXT NOT NULL, model TEXT NOT NULL, baseline_response TEXT,
        shadow_response TEXT, latency_ms INTEGER, error TEXT)""")
    old.execute("INSERT INTO shadow_interactions (timestamp, model) VALUES ('t','m')")
    old.commit()
    old.close()

    _cfg, _seen = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("AITA_SHADOW_MODEL", "gpt-6-luna")
    shadow.fire(_msgs(), 1, "live", 900).join(5)

    rows = _rows(tmp_path)
    assert len(rows) == 2                       # the pre-existing row survived
    assert rows[0]["prompt_variant"] is None    # backfilled as NULL
    assert rows[1]["baseline_latency_ms"] == 900
