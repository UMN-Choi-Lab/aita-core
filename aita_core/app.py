"""
AITA Streamlit chat application.
Parameterized by CourseConfig — no course-specific strings hardcoded.
"""

import os
import sys
import hashlib
import jwt
import streamlit as st
from streamlit.components.v1 import html as _st_html

from aita_core.config import get_config
from aita_core.rag import chat
from aita_core import shadow
from aita_core.db import log_interaction, rate_interaction, add_feedback, add_feature_request
from aita_core.admin import admin_page, is_admin_user


def _anon_student_id(cfg, ident):
    """Return the id written to the interaction logs.

    Teaching team (emails in cfg.admin_emails) keep their real internet id so
    their own activity stays legible in the admin panel. Every other student is
    stored under a stable, non-identifying token derived from a secret salt
    (AITA_ANON_SALT), so the logs hold no student identity and cannot be traced
    back to a person by anyone holding the database.
    """
    internet_id = ident.split("@")[0] if "@" in ident else ident
    email = ident if "@" in ident else f"{internet_id}@umn.edu"
    if email in (cfg.admin_emails or []):
        return internet_id
    salt = os.environ.get("AITA_ANON_SALT", "")
    return "anon_" + hashlib.sha256(f"{salt}:{internet_id.lower()}".encode()).hexdigest()[:16]


def _set_auth_cookie(user_data: dict):
    cfg = get_config()
    token = jwt.encode(user_data, cfg.cookie_key, algorithm="HS256")
    _st_html(
        f'<script>document.cookie="{cfg.cookie_name}={token}; path=/; max-age={30*24*3600}; SameSite=Lax";</script>',
        height=0,
    )


def _get_auth_cookie():
    cfg = get_config()
    try:
        token = st.context.cookies.get(cfg.cookie_name)
        if token:
            return jwt.decode(token, cfg.cookie_key, algorithms=["HS256"])
    except Exception:
        pass
    return None


def _delete_auth_cookie():
    cfg = get_config()
    _st_html(
        f'<script>document.cookie="{cfg.cookie_name}=; path=/; max-age=0";</script>',
        height=0,
    )


def resolve_file_path(stored_path):
    cfg = get_config()
    if stored_path and os.path.isfile(stored_path):
        return stored_path
    marker = "course_materials/"
    idx = stored_path.find(marker)
    if idx != -1:
        relative = stored_path[idx:]
        candidate = os.path.join(cfg.base_dir, relative)
        if os.path.isfile(candidate):
            return candidate
    return None


def _google_oauth_flow():
    import google_auth_oauthlib.flow
    import requests as _requests
    from aita_core import oauth_store

    cfg = get_config()
    _scopes = ["openid", "https://www.googleapis.com/auth/userinfo.profile",
               "https://www.googleapis.com/auth/userinfo.email"]

    auth_code = st.query_params.get("code")
    print(f"[OAUTH] code={'YES' if auth_code else 'NO'}, verifier={'YES' if oauth_store.code_verifier else 'NO'}", file=sys.stderr, flush=True)

    if auth_code:
        if st.session_state.get("_oauth_exchanging"):
            return
        st.session_state._oauth_exchanging = True

        try:
            flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                cfg.google_client_secret_file, scopes=_scopes,
                redirect_uri=cfg.redirect_uri,
            )
            flow.code_verifier = oauth_store.code_verifier
            flow.fetch_token(code=auth_code)

            creds = flow.credentials
            user_resp = _requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"})
            user_info = user_resp.json()
            print(f"[OAUTH] user_info: {user_info}", file=sys.stderr, flush=True)

            email = user_info.get("email", "")
            print(f"[OAUTH] email={email}", file=sys.stderr, flush=True)
            if not email.endswith("@umn.edu"):
                st.session_state.pop("_oauth_exchanging", None)
                st.query_params.clear()
                st.error("Please sign in with your **@umn.edu** Google account.")
                return

            st.session_state.authenticated = True
            st.session_state.student_id = _anon_student_id(cfg, email)
            st.session_state.student_email = email
            st.session_state.student_name = user_info.get("name", "")
            st.session_state._set_cookie = {
                "name": user_info.get("name", ""),
                "email": email,
            }
            st.session_state.pop("_oauth_exchanging", None)
            oauth_store.code_verifier = None
            print(f"[OAUTH] SUCCESS: {email}", file=sys.stderr, flush=True)
            st.rerun()
        except Exception as e:
            print(f"[OAUTH] Exception: {e}", file=sys.stderr, flush=True)
            st.session_state.pop("_oauth_exchanging", None)
            oauth_store.code_verifier = None
            st.rerun()
    else:
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            cfg.google_client_secret_file, scopes=_scopes,
            redirect_uri=cfg.redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="select_account",
        )
        oauth_store.code_verifier = flow.code_verifier
        print(f"[OAUTH] Auth URL generated, verifier stored: {flow.code_verifier[:10]}..." if flow.code_verifier else "[OAUTH] No verifier", file=sys.stderr, flush=True)

        st.markdown(f"""
<div style="display: flex; justify-content: center;">
    <a href="{auth_url}" target="_self"
       style="background-color: #4285f4; color: #fff; text-decoration: none;
              text-align: center; font-size: 16px; padding: 10px 20px;
              border-radius: 4px; display: inline-flex; align-items: center;
              cursor: pointer;">
        <img src="https://lh3.googleusercontent.com/COxitqgJr1sJnIDe8-jiKhxDx1FrYbtRHKJ9z_hELisAlapwE9LUPh6fcXIfb5vwpbMl4xl9H9TRFPc5NOO8Sb3VSgIBrfRYvW6cUA"
             alt="Google" style="margin-right: 10px; width: 24px; height: 24px;
             background: white; border: 2px solid white; border-radius: 3px;">
        Sign in with Google
    </a>
</div>
""", unsafe_allow_html=True)


_POSITIVE_REASONS = [
    ("concept", "Helped me understand the concept"),
    ("guidance", "Guided me without giving the answer"),
    ("sources", "Pointed me to useful course materials"),
    ("other", "Other"),
]

_NEGATIVE_REASONS = [
    ("incorrect", "Response was incorrect or misleading"),
    ("vague", "Too vague — needed more specific guidance"),
    ("misunderstood", "Didn't understand my question"),
    ("wanted_answer", "I wanted a more direct answer"),
    ("other", "Other"),
]


def _render_inline_feedback(interaction_id, msg_index):
    """Render inline feedback buttons below an assistant message."""
    fb_key = f"fb_{interaction_id}"
    already_rated = st.session_state.feedback_given.get(interaction_id)

    if already_rated:
        st.caption("Thanks for your feedback!")
        return

    # Check if user already clicked thumbs up/down (pending reason selection)
    rating_state_key = f"fb_rating_{interaction_id}"
    current_rating = st.session_state.get(rating_state_key)

    if current_rating is None:
        # Tier 1: Show thumbs up/down
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("👍", key=f"{fb_key}_up", help="Helpful"):
                st.session_state[rating_state_key] = 1
                rate_interaction(interaction_id, 1)
                st.rerun()
        with cols[1]:
            if st.button("👎", key=f"{fb_key}_down", help="Not helpful"):
                st.session_state[rating_state_key] = -1
                rate_interaction(interaction_id, -1)
                st.rerun()
    else:
        # Tier 2: Show reason options
        reasons = _POSITIVE_REASONS if current_rating == 1 else _NEGATIVE_REASONS
        prompt = "What made this helpful?" if current_rating == 1 else "What was the issue?"
        reason_labels = [r[1] for r in reasons]
        reason_keys = [r[0] for r in reasons]

        selected = st.radio(
            prompt,
            reason_labels,
            key=f"{fb_key}_reason",
            horizontal=True,
        )
        reason_idx = reason_labels.index(selected)
        reason_code = reason_keys[reason_idx]

        comment = st.text_input(
            "Anything else? (optional)",
            key=f"{fb_key}_comment",
            label_visibility="collapsed",
            placeholder="Anything else? (optional)",
        )

        if st.button("Submit", key=f"{fb_key}_submit"):
            add_feedback(
                st.session_state.student_id,
                interaction_id,
                current_rating,
                comment.strip() if comment else "",
                reason=reason_code,
            )
            st.session_state.feedback_given[interaction_id] = True
            st.rerun()


def login_page():
    cfg = get_config()
    st.title(cfg.course_name)
    st.markdown(cfg.course_description)
    st.markdown("---")

    if cfg.google_auth_enabled:
        _google_oauth_flow()
    else:
        student_id = st.text_input("Enter your UMN Student ID or Internet ID to get started:")
        if st.button("Sign In"):
            if student_id.strip():
                st.session_state.authenticated = True
                st.session_state.student_id = _anon_student_id(cfg, student_id.strip())
                st.rerun()
            else:
                st.error("Please enter a valid student ID.")

    st.markdown("---")
    st.caption(
        "This is an AI assistant. It will guide your learning but will not give "
        "direct answers to homework problems. Always verify with course materials "
        "and your instructor."
    )


def chat_page():
    cfg = get_config()

    # Set auth cookie if pending (deferred from OAuth callback)
    _sc = st.session_state.pop("_set_cookie", None)
    if _sc:
        _set_auth_cookie(_sc)

    # Sidebar
    with st.sidebar:
        st.title(cfg.course_short_name)
        display_name = st.session_state.get("student_name") or st.session_state.student_id
        st.markdown(f"Signed in as: **{display_name}**")

        if st.button("New Conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.last_interaction_id = None
            st.rerun()

        st.markdown("---")

        # Current week display
        if cfg.test_mode:
            st.subheader("Current Week (Test Mode)")
            max_week = max(cfg.week_topics.keys()) if cfg.week_topics else 15
            st.session_state.current_week = st.slider(
                "Set current week:",
                min_value=1,
                max_value=max_week,
                value=st.session_state.current_week,
            )
        else:
            st.session_state.current_week = cfg.get_current_week()
            st.subheader(f"Week {st.session_state.current_week}")

        covered = cfg.get_topics_covered(st.session_state.current_week)
        future = cfg.get_topics_not_covered(st.session_state.current_week)

        with st.expander("Topics covered so far"):
            for t in covered:
                st.markdown(f"- {t}")

        if cfg.week_aware and future:
            with st.expander("Topics not yet covered"):
                for t in future:
                    st.markdown(f"- {t}")

        st.markdown("---")
        st.markdown(
            "**How to use:**\n"
            "- Ask about course concepts\n"
            "- Get hints on homework approach\n"
            "- Review for quizzes and exams\n"
            "- Understand lecture material"
        )

        st.markdown("---")

        # Feature Request section (feedback is now inline in chat)
        with st.expander("Request a Feature"):
            fr_title = st.text_input("Feature title:", key="fr_title")
            fr_desc = st.text_area("Description:", key="fr_desc", height=80)
            if st.button("Submit Request", key="fr_submit"):
                if fr_title.strip():
                    add_feature_request(
                        st.session_state.student_id,
                        fr_title.strip(),
                        fr_desc.strip(),
                    )
                    st.success("Feature request submitted!")
                else:
                    st.warning("Please provide a title.")

        st.markdown("---")
        if is_admin_user():
            if st.button("Admin Panel"):
                st.session_state.page = "admin"
                st.rerun()
        if st.button("Sign Out"):
            _delete_auth_cookie()
            for key in ["authenticated", "connected", "user_info", "oauth_id",
                        "student_name", "student_id", "google_code_verifier"]:
                st.session_state.pop(key, None)
            st.session_state.authenticated = False
            st.session_state.chat_history = []
            st.rerun()

    # Main chat area
    st.title(cfg.course_name)
    st.warning(
        "**Disclaimer:** This is an AI assistant and may generate "
        "inaccurate or incomplete information. Always verify responses "
        "with course materials, lecture notes, and your instructor."
    )

    # Initialize feedback tracking
    if "feedback_given" not in st.session_state:
        st.session_state.feedback_given = {}  # interaction_id -> True

    # Display chat history with inline feedback
    for i, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # Show sources and inline feedback for assistant messages
            if msg["role"] == "assistant":
                sources = msg.get("sources", [])
                if sources:
                    with st.expander("Sources referenced"):
                        for src in sources:
                            label = src["label"]
                            resolved = resolve_file_path(src["file_path"])
                            if resolved:
                                fname = os.path.basename(resolved)
                                with open(resolved, "rb") as f:
                                    file_bytes = f.read()
                                st.download_button(
                                    label=f"Download: {label}",
                                    data=file_bytes,
                                    file_name=fname,
                                    mime="application/pdf",
                                    key=f"dl_{i}_{hash(resolved)}",
                                )
                            elif src["file_path"].startswith("http"):
                                st.markdown(f"- [{label}]({src['file_path']})")
                            else:
                                st.markdown(f"- {label}")
                iid = msg.get("interaction_id")
                if iid is not None:
                    _render_inline_feedback(iid, i)

    # Show example prompt buttons when chat is empty
    if not st.session_state.chat_history:
        st.markdown("**Try asking:**")
        examples = cfg.example_prompts.get(st.session_state.current_week, [])
        cols = st.columns(2)
        for i, example in enumerate(examples):
            with cols[i % 2]:
                if st.button(example, key=f"example_{i}", use_container_width=True):
                    st.session_state.pending_prompt = example
                    st.rerun()

    # Determine input: either from chat box or from example button
    user_input = st.chat_input("Ask a question about the course...")
    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if user_input:
        # Generate response
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                history_for_rag = st.session_state.chat_history.copy()
                response, sources, messages = chat(
                    user_input,
                    history_for_rag,
                    current_week=st.session_state.current_week,
                )

        # Log interaction to DB
        source_labels = [s["label"] for s in sources]
        interaction_id = log_interaction(
            student_id=st.session_state.student_id,
            week=st.session_state.current_week,
            question=user_input,
            response=response,
            sources=source_labels,
        )
        st.session_state.last_interaction_id = interaction_id

        # Candidate-model evaluation on real traffic. No-op unless
        # AITA_SHADOW_MODEL is set; runs off-thread, so it cannot delay or
        # break the student's turn either way.
        shadow.fire(messages, interaction_id, response)

        # Update chat history (store interaction_id with assistant message)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "interaction_id": interaction_id,
            "sources": sources,
        })
        st.rerun()


def main():
    cfg = get_config()

    st.set_page_config(
        page_title=cfg.course_name,
        page_icon="📊",
        layout="centered",
    )

    # --- Mobile-friendly CSS ---
    st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    h1 { font-size: 1.5rem !important; }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    [data-testid="stChatInput"] {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    [data-testid="stSidebar"] {
        min-width: 260px !important;
        max-width: 260px !important;
    }
}
[data-testid="stChatMessage"] {
    overflow-wrap: break-word;
    word-break: break-word;
}
[data-testid="stDownloadButton"] button {
    white-space: normal !important;
    text-align: left !important;
}
</style>
""", unsafe_allow_html=True)

    # --- Session state init ---
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        cookie_data = _get_auth_cookie()
        if cookie_data and "email" in cookie_data:
            email = cookie_data["email"]
            st.session_state.authenticated = True
            st.session_state.student_id = _anon_student_id(cfg, email)
            st.session_state.student_email = email
            st.session_state.student_name = cookie_data.get("name", "")
    if "current_week" not in st.session_state:
        cfg_init = get_config()
        st.session_state.current_week = cfg_init.get_current_week()
    if "page" not in st.session_state:
        st.session_state.page = "chat"
    if "last_interaction_id" not in st.session_state:
        st.session_state.last_interaction_id = None
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None

    # Clean up leftover OAuth query params if already authenticated
    if st.session_state.authenticated and st.query_params.get("code"):
        st.query_params.clear()

    if st.session_state.get("page") == "admin":
        admin_page()
    elif not st.session_state.authenticated:
        login_page()
    else:
        chat_page()
