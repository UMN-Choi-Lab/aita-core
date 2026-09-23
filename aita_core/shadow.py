"""Fire-and-forget shadow logging of a candidate model.

Sends the exact messages a student's turn produced to a second model and records
the reply. Students never see shadow output; it exists so a candidate can be
judged against the live model on real traffic instead of synthetic scenarios.

Off unless ``AITA_SHADOW_MODEL`` is set. The call runs on a daemon thread and
swallows every error: a broken shadow must never cost a student their answer.
The shadow speaks the OpenAI protocol, so ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL``
select the backend (the UMN AI Gateway) independently of the live provider.
"""

import copy
import dataclasses
import json
import os
import threading
import time
from datetime import datetime

from aita_core import providers
from aita_core.config import get_config
from aita_core.db import get_conn


def _extra_params():
    raw = os.getenv("AITA_SHADOW_EXTRA_PARAMS")
    if raw:
        return json.loads(raw)
    # Reasoning models on the gateway reject temperature=0 unless reasoning is off.
    return {"reasoning_effort": "none"}


def fire(messages, interaction_id, baseline_response):
    """Start the shadow call if one is configured. Returns immediately."""
    model = os.getenv("AITA_SHADOW_MODEL")
    if not model:
        return None
    thread = threading.Thread(
        target=_run,
        # deepcopy: the caller goes on mutating its chat history after we return.
        args=(model, copy.deepcopy(messages), interaction_id, baseline_response),
        daemon=True,
    )
    thread.start()
    return thread


def _run(model, messages, interaction_id, baseline_response):
    started = time.monotonic()
    reply, err = None, None
    try:
        cfg = dataclasses.replace(
            get_config(),
            llm_provider="openai",
            llm_model=model,
            llm_extra_params=_extra_params(),
        )
        reply = providers.chat_complete(cfg, messages)
    except Exception as e:                                  # noqa: BLE001 - never propagate
        err = f"{type(e).__name__}: {e}"[:2000]
    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        _record(interaction_id, model, baseline_response, reply, latency_ms, err)
    except Exception:                                       # noqa: BLE001
        pass


def _record(interaction_id, model, baseline_response, reply, latency_ms, err):
    conn = get_conn()
    conn.execute(
        "INSERT INTO shadow_interactions "
        "(interaction_id, timestamp, model, baseline_response, shadow_response, "
        " latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (interaction_id, datetime.now().isoformat(), model,
         baseline_response, reply, latency_ms, err),
    )
    conn.commit()
    conn.close()
