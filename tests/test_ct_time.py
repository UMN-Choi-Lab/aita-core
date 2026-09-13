"""Admin timestamps render in US Central (DST-aware). Needs streamlit+tzdata."""
try:
    from aita_core.admin import _fmt_ct
except ImportError as e:  # streamlit/pandas not installed in this env
    import sys
    print(f"skip: {e}")
    sys.exit(0)


def test_summer_is_cdt():
    # 16:39 UTC in September -> Central Daylight Time (UTC-5)
    assert _fmt_ct("2026-09-09T16:39:01.123") == "2026-09-09 11:39 CDT"


def test_winter_is_cst():
    # 16:39 UTC in December -> Central Standard Time (UTC-6)
    assert _fmt_ct("2026-12-15T16:39:00") == "2026-12-15 10:39 CST"


def test_edge_cases():
    assert _fmt_ct("") == ""
    assert _fmt_ct("garbage-string-here") == "garbage-string-h"  # malformed -> first 16 chars


if __name__ == "__main__":
    test_summer_is_cdt(); test_winter_is_cst(); test_edge_cases()
    print("ok:", _fmt_ct("2026-09-09T16:39:01.123"))
