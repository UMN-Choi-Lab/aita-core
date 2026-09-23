"""Check transient-error backoff: retry 429/5xx, re-raise the rest fast.

Covers both provider error shapes, since the backoff helper is shared: google-genai
reports HTTP status on ``.code``, the OpenAI SDK (and the UMN AI Gateway behind it)
on ``.status_code``.
"""
from google.genai import errors
from aita_core.providers import (
    _call_with_backoff, _openai_chat, _status_code, _is_transient, _is_content_filtered,
    _HIGH_DEMAND_MSG, _NO_RESPONSE_MSG, _FILTERED_MSG,
)

# base_delay=0 -> time.sleep(0), so the tests run instantly.


def _api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": "test"}})


def test_retries_then_succeeds():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _api_error(429)
        return "ok"
    assert _call_with_backoff(fn, tries=4, base_delay=0) == "ok"
    assert calls["n"] == 3  # failed twice, succeeded on the third


def test_exhausts_then_reraises():
    def fn():
        raise _api_error(429)
    try:
        _call_with_backoff(fn, tries=3, base_delay=0)
        assert False, "should have raised after exhausting retries"
    except errors.APIError as e:
        assert e.code == 429


def test_non_retryable_reraises_immediately():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        raise _api_error(400)  # bad request -> a real bug, not transient
    try:
        _call_with_backoff(fn, tries=4, base_delay=0)
        assert False, "should have raised"
    except errors.APIError as e:
        assert e.code == 400
    assert calls["n"] == 1  # no retries on a non-transient error


# --- OpenAI / gateway error shape (status on .status_code, not .code) --------

class _OpenAIStyleError(Exception):
    """Stands in for openai.APIStatusError without importing the SDK's shape."""
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_status_code_reads_both_shapes():
    assert _status_code(_api_error(429)) == 429          # google-genai .code
    assert _status_code(_OpenAIStyleError(503)) == 503   # openai .status_code
    assert _status_code(ValueError("not an API error")) is None


def test_openai_style_429_is_retried():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _OpenAIStyleError(429)
        return "ok"
    assert _call_with_backoff(fn, tries=4, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_plain_exception_is_not_retried():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        raise ValueError("bug, not a transient API error")
    try:
        _call_with_backoff(fn, tries=4, base_delay=0)
        assert False, "should have raised"
    except ValueError:
        pass
    assert calls["n"] == 1


# --- _openai_chat fallbacks --------------------------------------------------

class _OpenAIStyleError2(Exception):
    """API error with a body message, as the SDK surfaces it."""
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class _Cfg:
    llm_model = "gemini-3.5-flash-lite"
    llm_temperature = 0
    llm_max_output_tokens = 2048


class _FakeClient:
    """Minimal stand-in for openai.OpenAI: client.chat.completions.create(...)."""
    def __init__(self, behaviour):
        self.calls = 0
        self.behaviour = behaviour
        outer = self
        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                return outer.behaviour(outer.calls)
        class _Chat:
            completions = _Completions()
        self.chat = _Chat()


def _resp(content, finish_reason="stop"):
    choice = type("C", (), {})()
    choice.message = type("M", (), {"content": content})()
    choice.finish_reason = finish_reason
    return type("R", (), {"choices": [choice]})()


def _with_client(client, fn):
    """Swap the module-level cached client for the duration of one call."""
    import aita_core.providers as prov
    saved = prov._openai_client
    prov._openai_client = client
    try:
        return fn()
    finally:
        prov._openai_client = saved


def test_openai_chat_returns_text():
    client = _FakeClient(lambda n: _resp("hello"))
    assert _with_client(client, lambda: _openai_chat(_Cfg(), [])) == "hello"
    assert client.calls == 1


def test_openai_chat_retries_empty_then_gives_up():
    client = _FakeClient(lambda n: _resp(""))
    out = _with_client(client, lambda: _openai_chat(_Cfg(), []))
    assert out == _NO_RESPONSE_MSG
    assert client.calls == 3  # first call + 2 empty-retries


def test_openai_chat_recovers_on_empty_retry():
    client = _FakeClient(lambda n: _resp("" if n == 1 else "recovered"))
    assert _with_client(client, lambda: _openai_chat(_Cfg(), [])) == "recovered"
    assert client.calls == 2


def test_openai_chat_429_returns_friendly_message():
    def boom(n):
        raise _OpenAIStyleError(429)
    client = _FakeClient(boom)
    import aita_core.providers as prov
    saved_delay = prov._call_with_backoff.__defaults__
    out = _with_client(client, lambda: _openai_chat(_Cfg(), []))
    assert out == _HIGH_DEMAND_MSG
    assert client.calls == 4  # tries=4, all exhausted
    assert prov._call_with_backoff.__defaults__ == saved_delay


# --- timeouts: no status code, but the thread must not block forever ----------

class _ReadTimeout(Exception):
    """Stands in for httpx.ReadTimeout / google-genai's timeout wrapper."""


def test_timeouts_count_as_transient():
    assert _is_transient(_ReadTimeout("read timed out"))
    assert _is_transient(TimeoutError())
    assert not _is_transient(ValueError("a real bug"))


def test_timeout_is_retried_then_succeeds():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _ReadTimeout("read timed out")
        return "ok"
    assert _call_with_backoff(fn, tries=4, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_openai_chat_timeout_returns_friendly_message():
    def boom(n):
        raise _ReadTimeout("read timed out")
    assert _with_client(_FakeClient(boom), lambda: _openai_chat(_Cfg(), [])) == _HIGH_DEMAND_MSG


def test_openai_chat_400_still_raises():
    def boom(n):
        raise _OpenAIStyleError(400)
    client = _FakeClient(boom)
    try:
        _with_client(client, lambda: _openai_chat(_Cfg(), []))
        assert False, "a 400 is a real bug and must not be swallowed"
    except _OpenAIStyleError as e:
        assert e.status_code == 400


# --- content filtering: the safety layer refuses before the model sees it -----

_AZURE_400 = ("litellm.BadRequestError: Azure_aiException - The response was filtered due to "
              "the prompt triggering Azure OpenAI's content management policy. Please modify "
              "your prompt and retry.")


def test_recognises_azure_and_openai_filters():
    assert _is_content_filtered(_OpenAIStyleError2(400, _AZURE_400))
    assert _is_content_filtered(_OpenAIStyleError2(400, "error: content_filter triggered"))
    assert not _is_content_filtered(_OpenAIStyleError2(400, "invalid model name"))
    assert not _is_content_filtered(_OpenAIStyleError2(429, _AZURE_400))  # rate limit, not a filter


def test_filtered_prompt_declines_instead_of_raising():
    def boom(n):
        raise _OpenAIStyleError2(400, _AZURE_400)
    out = _with_client(_FakeClient(boom), lambda: _openai_chat(_Cfg(), []))
    assert out == _FILTERED_MSG


def test_filtered_prompt_is_not_retried():
    calls = {"n": 0}
    def boom(n):
        calls["n"] = n
        raise _OpenAIStyleError2(400, _AZURE_400)
    _with_client(_FakeClient(boom), lambda: _openai_chat(_Cfg(), []))
    assert calls["n"] == 1  # a filter verdict will not change on retry


def test_filtered_response_short_circuits_the_empty_retry():
    """finish_reason=content_filter must not burn two empty-retries first."""
    def resp(n):
        r = _resp("")
        r.choices[0].finish_reason = "content_filter"
        return r
    client = _FakeClient(resp)
    assert _with_client(client, lambda: _openai_chat(_Cfg(), [])) == _FILTERED_MSG
    assert client.calls == 1


if __name__ == "__main__":
    test_retries_then_succeeds()
    test_exhausts_then_reraises()
    test_non_retryable_reraises_immediately()
    test_status_code_reads_both_shapes()
    test_openai_style_429_is_retried()
    test_plain_exception_is_not_retried()
    test_openai_chat_returns_text()
    test_openai_chat_retries_empty_then_gives_up()
    test_openai_chat_recovers_on_empty_retry()
    test_openai_chat_429_returns_friendly_message()
    test_openai_chat_400_still_raises()
    test_timeouts_count_as_transient()
    test_timeout_is_retried_then_succeeds()
    test_openai_chat_timeout_returns_friendly_message()
    test_recognises_azure_and_openai_filters()
    test_filtered_prompt_declines_instead_of_raising()
    test_filtered_prompt_is_not_retried()
    test_filtered_response_short_circuits_the_empty_retry()
    print("ok: both error shapes retried, empty retried, 429 friendly, 400 fast-failed")
