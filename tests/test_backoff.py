"""Check transient-error backoff: retry 429/5xx, re-raise the rest fast."""
from google.genai import errors
from aita_core.providers import _call_with_backoff

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


if __name__ == "__main__":
    test_retries_then_succeeds()
    test_exhausts_then_reraises()
    test_non_retryable_reraises_immediately()
    print("ok: 429 retried, exhaustion re-raised, 400 fast-failed")
