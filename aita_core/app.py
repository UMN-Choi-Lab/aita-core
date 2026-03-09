"""
AITA Streamlit chat application.
Parameterized by CourseConfig — no course-specific strings hardcoded.
"""

import os
import sys
import jwt
import streamlit as st
from streamlit.components.v1 import html as _st_html

from aita_core.config import get_config
from aita_core.rag import chat
from aita_core.db import log_interaction, add_feedback, add_feature_request
from aita_core.admin import admin_page


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
            st.session_state.student_id = email.split("@")[0]
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
                st.session_state.student_id = student_id.strip()
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

        # Week selector for testing
        st.subheader("Current Week")
        st.session_state.current_week = st.slider(
            "Set current week (for testing):",
            min_value=1,
            max_value=15,
            value=st.session_state.current_week,
        )

        covered = cfg.get_topics_covered(st.session_state.current_week)
        future = cfg.get_topics_not_covered(st.session_state.current_week)

        with st.expander("Topics covered so far"):
            for t in covered:
                st.markdown(f"- {t}")

        if future:
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

        # Feedback & Feature Request section
        with st.expander("Give Feedback"):
            fb_comment = st.text_area("Your feedback:", key="fb_comment", height=80)
            fb_rating = st.radio("Rating:", ["Positive", "Negative"], horizontal=True, key="fb_rating")
            if st.button("Submit Feedback", key="fb_submit"):
                if fb_comment.strip():
                    add_feedback(
                        st.session_state.student_id,
                        st.session_state.last_interaction_id,
                        1 if fb_rating == "Positive" else -1,
                        fb_comment.strip(),
                    )
                    st.success("Thanks for your feedback!")
                else:
                    st.warning("Please write a comment.")

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

    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

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
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                history_for_rag = st.session_state.chat_history.copy()
                response, sources = chat(
                    user_input,
                    history_for_rag,
                    current_week=st.session_state.current_week,
                )
                st.markdown(response)

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
                                    key=f"dl_{hash(resolved)}_{hash(user_input)}",
                                )
                            elif src["file_path"].startswith("http"):
                                st.markdown(f"- [{label}]({src['file_path']})")
                            else:
                                st.markdown(f"- {label}")

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

        # Update chat history
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.chat_history.append({"role": "assistant", "content": response})


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
            st.session_state.student_id = email.split("@")[0] if "@" in email else email
            st.session_state.student_name = cookie_data.get("name", "")
    if "current_week" not in st.session_state:
        st.session_state.current_week = 1
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
