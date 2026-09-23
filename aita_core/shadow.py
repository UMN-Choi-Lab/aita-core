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
import hashlib
import json
import os
import threading
import time
from datetime import datetime

from aita_core import providers
from aita_core.config import get_config
from aita_core.db import get_conn


# Behaviours the gpt-luna family drops relative to gemini on the same prompt,
# restated as hard requirements. Measured worth +13 points of pass rate offline.
# Course-agnostic on purpose: it is appended to whatever system prompt the course
# already uses, so 3101 and 3102 share it.
_PROMPT_SUFFIX = """

HOW TO SHAPE EVERY REPLY (these are requirements, not style preferences):

1. END WITH ONE GUIDING QUESTION. Every reply about course content must end with a
   single specific question that advances the student's own reasoning - about their
   setup, their assumption, or the next step they should attempt. Stating a rule and
   telling the student to apply it is not acceptable; you must hand them the next
   move as a question. Never end a content reply with an instruction like
   "re-check your arithmetic" or "substitute and solve".

2. OFF-TOPIC QUESTIONS GET REDIRECTED TO THIS COURSE, NOT ELSEWHERE. If a question
   is unrelated to the course (weather, campus services, other classes, personal
   matters), say in one sentence that it is outside what you can help with, then
   immediately name a specific topic from THIS course you can help with instead.
   Do not attempt to answer it, do not offer to help interpret or follow up on it,
   and do not suggest where else to look. A reply that only declines, or that
   engages with the off-topic subject, is a failure.

3. NO UNSOLICITED ADVICE. Do not comment on the student's study habits, sleep,
   time management, stress, or choices. You are a teaching assistant for the course
   material, not a life coach.

4. NAME YOUR SOURCE. When your answer draws on retrieved course materials, name the
   specific document in the reply, the way the course prompt asks you to. Do not
   paraphrase course content without saying where it is from.

5. SCAFFOLD RATHER THAN SUMMARISE. Give the student the immediate next step to
   attempt, not a complete ordered method they can simply execute. Listing every
   step of a procedure does the thinking for them even when no number is revealed.
"""


def _prompt_suffix():
    """Text appended to the system prompt, and a tag identifying which variant."""
    override = os.getenv("AITA_SHADOW_PROMPT_SUFFIX")
    if override is not None:                      # "" deliberately means "no suffix"
        suffix = override
    elif os.getenv("AITA_SHADOW_PROMPT") == "base":
        suffix = ""
    else:
        suffix = _PROMPT_SUFFIX
    if not suffix:
        return "", "base"
    return suffix, "tuned:" + hashlib.sha256(suffix.encode()).hexdigest()[:8]


def _extra_params():
    raw = os.getenv("AITA_SHADOW_EXTRA_PARAMS")
    if raw:
        return json.loads(raw)
    # Reasoning models on the gateway reject temperature=0 unless reasoning is off.
    return {"reasoning_effort": "none"}


def fire(messages, interaction_id, baseline_response, baseline_ms=None):
    """Start the shadow call if one is configured. Returns immediately."""
    model = os.getenv("AITA_SHADOW_MODEL")
    if not model:
        return None
    thread = threading.Thread(
        target=_run,
        # deepcopy: the caller goes on mutating its chat history after we return.
        args=(model, copy.deepcopy(messages), interaction_id, baseline_response,
              baseline_ms),
        daemon=True,
    )
    thread.start()
    return thread


def _run(model, messages, interaction_id, baseline_response, baseline_ms):
    suffix, variant = _prompt_suffix()
    if suffix:
        # Appended after the retrieved context, which build_messages() puts in the
        # system message. Last position is the strongest, and it needs no matching
        # against the course prompt's wording.
        messages[0] = dict(messages[0],
                           content=messages[0]["content"] + suffix)
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
        _record(interaction_id, model, variant, baseline_response, reply,
                latency_ms, baseline_ms, err)
    except Exception:                                       # noqa: BLE001
        pass


def _record(interaction_id, model, variant, baseline_response, reply,
            latency_ms, baseline_ms, err):
    conn = get_conn()
    conn.execute(
        "INSERT INTO shadow_interactions "
        "(interaction_id, timestamp, model, prompt_variant, baseline_response, "
        " shadow_response, latency_ms, baseline_latency_ms, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (interaction_id, datetime.now().isoformat(), model, variant,
         baseline_response, reply, latency_ms, baseline_ms, err),
    )
    conn.commit()
    conn.close()
