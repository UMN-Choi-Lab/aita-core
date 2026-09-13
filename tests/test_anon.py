"""Check the log de-identification: students hashed, teaching team kept."""
import os
from types import SimpleNamespace

os.environ["AITA_ANON_SALT"] = "test-salt"
from aita_core.app import _anon_student_id  # noqa: E402

cfg = SimpleNamespace(admin_emails=["chois@umn.edu", "mlevin@umn.edu"])


def test_teaching_team_kept_plain():
    assert _anon_student_id(cfg, "chois@umn.edu") == "chois"
    assert _anon_student_id(cfg, "mlevin@umn.edu") == "mlevin"


def test_student_is_anonymized_and_not_the_id():
    tok = _anon_student_id(cfg, "smit1234@umn.edu")
    assert tok.startswith("anon_")
    assert "smit1234" not in tok


def test_stable_across_email_and_bare_id():
    # same person via full email vs bare internet id -> same token
    assert _anon_student_id(cfg, "smit1234@umn.edu") == _anon_student_id(cfg, "smit1234")


def test_salt_changes_token():
    a = _anon_student_id(cfg, "smit1234")
    os.environ["AITA_ANON_SALT"] = "other-salt"
    b = _anon_student_id(cfg, "smit1234")
    os.environ["AITA_ANON_SALT"] = "test-salt"
    assert a != b


if __name__ == "__main__":
    test_teaching_team_kept_plain()
    test_student_is_anonymized_and_not_the_id()
    test_stable_across_email_and_bare_id()
    test_salt_changes_token()
    print("ok:", _anon_student_id(cfg, "smit1234@umn.edu"), "| admin:", _anon_student_id(cfg, "chois@umn.edu"))
