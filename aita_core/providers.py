"""Provider-agnostic LLM + embedding access.

Two backends are supported, selected by ``cfg.llm_provider``:

- ``"openai"`` (default): the OpenAI SDK (``OPENAI_API_KEY`` from env).
- ``"gemini"``: Google Gemini via the ``google-genai`` SDK. When ``cfg.gcp_project``
  is set the client targets Vertex AI using Application Default Credentials (ADC) —
  no API key to manage. Otherwise it falls back to the SDK's own env-based config
  (e.g. ``GEMINI_API_KEY`` for the Gemini Developer API).

Both backends return data in the same shape so ``rag`` and ``ingest`` stay
provider-agnostic: ``chat_complete`` returns a string, ``embed_texts`` returns a
float32 ``numpy`` array of shape ``(len(texts), dim)``.
"""

import time

import numpy as np

# Transient statuses worth retrying: 429 rate-limit/quota, 503 unavailable, 500.
# Vertex quota (esp. on a free-trial project shared across courses) can 429 under
# a class-launch burst; a short backoff rides out the spike instead of erroring
# the student. Non-transient errors (400/403/404) are re-raised unchanged.
_RETRYABLE_STATUS = (429, 500, 503)


def _call_with_backoff(fn, *, tries=4, base_delay=0.5):
    """Call ``fn`` with exponential backoff on transient API errors (429/5xx)."""
    from google.genai import errors as _genai_errors
    for attempt in range(tries):
        try:
            return fn()
        except _genai_errors.APIError as e:
            if getattr(e, "code", None) in _RETRYABLE_STATUS and attempt < tries - 1:
                time.sleep(base_delay * (2 ** attempt))  # 0.5s, 1s, 2s
                continue
            raise


# Vertex AI's embedding endpoint accepts far fewer instances per request than the
# OpenAI embeddings API, so Gemini batches are kept small.
_OPENAI_EMBED_BATCH = 100
_GEMINI_EMBED_BATCH = 50

_openai_client = None
_gemini_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


def _get_gemini_client(cfg):
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        if cfg.gcp_project:
            _gemini_client = genai.Client(
                vertexai=True,
                project=cfg.gcp_project,
                location=cfg.gcp_location or "us-central1",
            )
        else:
            # Honours GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT / GEMINI_API_KEY.
            _gemini_client = genai.Client()
    return _gemini_client


# ---------------------------------------------------------------------------
# Chat completion
# ---------------------------------------------------------------------------

def chat_complete(cfg, messages):
    """Return the assistant's reply text for OpenAI-style ``messages``."""
    if cfg.llm_provider == "gemini":
        return _gemini_chat(cfg, messages)
    return _openai_chat(cfg, messages)


def _openai_chat(cfg, messages):
    client = _get_openai_client()
    kwargs = {
        "model": cfg.llm_model,
        "messages": messages,
        "temperature": cfg.llm_temperature,
    }
    if cfg.llm_max_output_tokens:
        kwargs["max_tokens"] = cfg.llm_max_output_tokens
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def _gemini_chat(cfg, messages):
    from google.genai import types
    client = _get_gemini_client(cfg)

    # OpenAI 'system' messages -> Gemini system_instruction;
    # 'assistant' role -> 'model'; everything else -> 'user'.
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
        )

    def _call(temperature):
        config = types.GenerateContentConfig(
            system_instruction="\n\n".join(system_parts) or None,
            temperature=temperature,
            max_output_tokens=cfg.llm_max_output_tokens or None,
        )
        return client.models.generate_content(
            model=cfg.llm_model, contents=contents, config=config,
        )

    from google.genai import errors as _genai_errors
    try:
        resp = _call_with_backoff(lambda: _call(cfg.llm_temperature))
        text = resp.text
        # Retry on an empty candidate (a rare transient/deterministic empty return
        # that otherwise surfaces the user-facing fallback below). Nudge the
        # temperature up to break a deterministic empty; a genuine safety block will
        # still return empty and fall through to the fallback.
        tries = 0
        while not text and tries < 2:
            tries += 1
            resp = _call_with_backoff(
                lambda t=tries: _call(min(1.0, max(cfg.llm_temperature, 0.3) + 0.1 * t))
            )
            text = resp.text
    except _genai_errors.APIError as e:
        # Backoff exhausted on a transient error (usually 429 quota under load):
        # give the student a clear "try again" instead of a stack trace.
        if getattr(e, "code", None) in _RETRYABLE_STATUS:
            return ("The assistant is experiencing high demand right now. "
                    "Please wait a few seconds and send your message again.")
        raise
    if not text:
        # Safety block, empty candidate, or truncation with no text.
        return ("I'm sorry — I couldn't generate a response to that. "
                "Could you rephrase your question?")
    return text


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def embed_texts(cfg, texts):
    """Embed ``texts`` (a list of strings). Returns float32 array (n, dim)."""
    if cfg.llm_provider == "gemini":
        return _gemini_embed(cfg, texts)
    return _openai_embed(cfg, texts)


def _openai_embed(cfg, texts):
    client = _get_openai_client()
    out = []
    n_batches = (len(texts) - 1) // _OPENAI_EMBED_BATCH + 1
    for i in range(0, len(texts), _OPENAI_EMBED_BATCH):
        batch = texts[i:i + _OPENAI_EMBED_BATCH]
        print(f"  Embedding batch {i // _OPENAI_EMBED_BATCH + 1}/{n_batches} "
              f"({len(batch)} chunks)")
        resp = client.embeddings.create(model=cfg.embedding_model, input=batch)
        out.extend(item.embedding for item in resp.data)
    return np.array(out, dtype="float32")


def _gemini_embed(cfg, texts):
    from google.genai import types
    client = _get_gemini_client(cfg)
    dims = cfg.embedding_dimensions or None
    embed_cfg = types.EmbedContentConfig(output_dimensionality=dims) if dims else None

    out = []
    n_batches = (len(texts) - 1) // _GEMINI_EMBED_BATCH + 1
    for i in range(0, len(texts), _GEMINI_EMBED_BATCH):
        batch = texts[i:i + _GEMINI_EMBED_BATCH]
        print(f"  Embedding batch {i // _GEMINI_EMBED_BATCH + 1}/{n_batches} "
              f"({len(batch)} chunks)")
        resp = client.models.embed_content(
            model=cfg.embedding_model, contents=batch, config=embed_cfg,
        )
        out.extend(e.values for e in resp.embeddings)
    return np.array(out, dtype="float32")
