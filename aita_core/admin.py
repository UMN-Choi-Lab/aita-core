"""
Admin panel for AITA.
"""

import json

import streamlit as st
import pandas as pd
from aita_core.db import (
    get_interaction_stats, get_interactions, get_feedback,
    get_feature_requests, update_feature_request_status,
)
from aita_core.config import get_config


def check_admin_auth():
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    return st.session_state.admin_authenticated


def admin_login():
    st.title("Admin Login")
    password = st.text_input("Admin password:", type="password")
    if st.button("Login"):
        cfg = get_config()
        if password == cfg.admin_password:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")


def admin_dashboard():
    st.title("AITA Admin Dashboard")

    stats = get_interaction_stats()

    # --- Overview metrics ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Interactions", stats["total_interactions"])
    col2.metric("Unique Students", stats["unique_students"])
    col3.metric("Avg Rating", f"{stats['avg_rating']:.1f}" if stats["avg_rating"] else "N/A")
    col4.metric("Open Requests", stats["open_feature_requests"])

    st.markdown("---")

    # --- Tabs ---
    tab_history, tab_feedback, tab_requests, tab_settings = st.tabs([
        "Interaction History", "Feedback", "Feature Requests", "Course Settings",
    ])

    # --- Interaction History ---
    with tab_history:
        st.subheader("Interaction History")

        # Filters
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            filter_student = st.text_input("Filter by student ID:", key="filter_student")
        with col_filter2:
            page_size = st.selectbox("Per page:", [25, 50, 100], key="page_size")

        student_filter = filter_student.strip() if filter_student else None
        interactions = get_interactions(limit=page_size, student_id=student_filter)

        if not interactions:
            st.info("No interactions recorded yet.")
        else:
            for ix in interactions:
                with st.expander(
                    f"#{ix['id']} | {ix['student_id']} | Week {ix['week']} | "
                    f"{ix['timestamp'][:16]} | "
                    f"{'Rating: ' + str(ix['rating']) if ix['rating'] else 'Unrated'}"
                ):
                    st.markdown("**Question:**")
                    st.markdown(ix["question"])
                    st.markdown("**Response:**")
                    st.markdown(ix["response"])
                    if ix["sources"]:
                        st.markdown(f"**Sources:** {ix['sources']}")

    # --- Feedback ---
    with tab_feedback:
        st.subheader("Student Feedback")
        feedback_list = get_feedback(limit=100)

        if not feedback_list:
            st.info("No feedback submitted yet.")
        else:
            for fb in feedback_list:
                rating_display = ""
                if fb["rating"]:
                    rating_display = " | " + ("thumbs up" if fb["rating"] == 1 else "thumbs down")
                with st.expander(
                    f"#{fb['id']} | {fb['student_id']} | {fb['timestamp'][:16]}{rating_display}"
                ):
                    if fb["comment"]:
                        st.markdown(f"**Comment:** {fb['comment']}")
                    if fb.get("question"):
                        st.markdown(f"**Original question:** {fb['question']}")
                    if fb.get("response"):
                        st.markdown(f"**Bot response:** {fb['response']}")

    # --- Feature Requests ---
    with tab_requests:
        st.subheader("Feature Requests")

        status_filter = st.selectbox(
            "Status:", ["all", "open", "in_progress", "done", "wontfix"],
            key="req_status",
        )
        requests = get_feature_requests(
            status=status_filter if status_filter != "all" else None
        )

        if not requests:
            st.info("No feature requests yet.")
        else:
            for req in requests:
                with st.expander(
                    f"#{req['id']} [{req['status']}] {req['title']} — {req['student_id']} | {req['timestamp'][:16]}"
                ):
                    if req["description"]:
                        st.markdown(req["description"])

                    new_status = st.selectbox(
                        "Update status:",
                        ["open", "in_progress", "done", "wontfix"],
                        index=["open", "in_progress", "done", "wontfix"].index(req["status"]),
                        key=f"status_{req['id']}",
                    )
                    if new_status != req["status"]:
                        if st.button(f"Save", key=f"save_{req['id']}"):
                            update_feature_request_status(req["id"], new_status)
                            st.success(f"Updated to {new_status}")
                            st.rerun()

    # --- Course Settings ---
    with tab_settings:
        admin_settings()

    # --- Sidebar ---
    with st.sidebar:
        st.title("Admin Panel")
        if st.button("Back to Chat"):
            st.session_state.page = "chat"
            st.rerun()
        if st.button("Logout Admin"):
            st.session_state.admin_authenticated = False
            st.session_state.page = "chat"
            st.rerun()


def _dict_to_json(d, int_keys=False):
    """Convert dict to formatted JSON string, with int keys as strings for display."""
    if int_keys:
        d = {str(k): v for k, v in sorted(d.items(), key=lambda x: int(x[0]))}
    return json.dumps(d, indent=2)


def _parse_json_dict(text, int_keys=False):
    """Parse JSON text to dict, optionally converting keys to int."""
    d = json.loads(text)
    if int_keys:
        d = {int(k): v for k, v in d.items()}
    return d


def admin_settings():
    cfg = get_config()
    st.subheader("Course Settings")
    st.caption("Changes are saved to disk and persist across restarts.")

    with st.form("settings_form"):
        # --- Course Identity ---
        st.markdown("#### Course Identity")
        course_name = st.text_input("Course Name", value=cfg.course_name)
        course_short_name = st.text_input("Short Name", value=cfg.course_short_name)
        course_description = st.text_area(
            "Description (shown on login page)", value=cfg.course_description, height=80,
        )

        st.markdown("---")

        # --- System Prompt ---
        st.markdown("#### System Prompt")
        system_prompt = st.text_area("System Prompt", value=cfg.system_prompt, height=300)

        st.markdown("---")

        # --- LLM Settings ---
        st.markdown("#### LLM Settings")
        col1, col2, col3 = st.columns(3)
        with col1:
            llm_model = st.text_input("LLM Model", value=cfg.llm_model)
        with col2:
            llm_temperature = st.number_input(
                "Temperature", value=float(cfg.llm_temperature),
                min_value=0.0, max_value=2.0, step=0.1,
            )
        with col3:
            retrieval_k = st.number_input(
                "Retrieval K", value=int(cfg.retrieval_k),
                min_value=1, max_value=20, step=1,
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            chunk_size = st.number_input(
                "Chunk Size", value=int(cfg.chunk_size),
                min_value=256, max_value=8192, step=256,
            )
        with col5:
            chunk_overlap = st.number_input(
                "Chunk Overlap", value=int(cfg.chunk_overlap),
                min_value=0, max_value=2048, step=64,
            )
        with col6:
            embedding_model = st.text_input("Embedding Model", value=cfg.embedding_model)

        st.caption(
            "Changes to embedding model, chunk size, and chunk overlap "
            "require re-ingestion of documents to take effect."
        )

        st.markdown("---")

        # --- Textbook ---
        st.markdown("#### Textbook")
        textbook_url = st.text_input("Textbook URL", value=cfg.textbook_url)
        textbook_ch_json = st.text_area(
            "Chapter → Week mapping (JSON)",
            value=json.dumps(cfg.textbook_chapter_to_week, indent=2),
            height=200,
        )

        st.markdown("---")

        # --- Week Schedule ---
        st.markdown("#### Week Schedule")
        week_topics_json = st.text_area(
            "Week Topics — {week_number: [topic1, topic2, ...]}",
            value=_dict_to_json(cfg.week_topics, int_keys=True),
            height=300,
        )

        st.markdown("---")

        # --- Content Mappings ---
        st.markdown("#### Content Mappings")
        st.caption(
            "These control which week each piece of content is available. "
            "Changes to topic/lab mappings require re-ingestion."
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            hw_json = st.text_area(
                "HW → Week — {hw_num: week}",
                value=_dict_to_json(cfg.hw_num_to_week, int_keys=True),
                height=200,
            )
        with col_m2:
            topic_json = st.text_area(
                "Topic → Week — {topic_num: week}",
                value=_dict_to_json(cfg.topic_num_to_week, int_keys=True),
                height=200,
            )

        col_m3, col_m4 = st.columns(2)
        with col_m3:
            lab_json = st.text_area(
                "Lab → Week — {lab_num: week}",
                value=_dict_to_json(cfg.lab_num_to_week, int_keys=True),
                height=150,
            )
        with col_m4:
            study_json = st.text_area(
                "Study Guide → Week — {name: week}",
                value=json.dumps(cfg.study_guide_to_week, indent=2),
                height=150,
            )

        st.markdown("---")

        # --- Example Prompts ---
        st.markdown("#### Example Prompts")
        example_json = st.text_area(
            "Example Prompts by Week — {week: [prompt1, prompt2, ...]}",
            value=_dict_to_json(cfg.example_prompts, int_keys=True),
            height=300,
        )

        submitted = st.form_submit_button("Save Settings", type="primary")

    if submitted:
        try:
            overrides = {
                "course_name": course_name,
                "course_short_name": course_short_name,
                "course_description": course_description,
                "system_prompt": system_prompt,
                "llm_model": llm_model,
                "llm_temperature": llm_temperature,
                "retrieval_k": retrieval_k,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "embedding_model": embedding_model,
                "textbook_url": textbook_url,
                "textbook_chapter_to_week": json.loads(textbook_ch_json),
                "week_topics": _parse_json_dict(week_topics_json, int_keys=True),
                "hw_num_to_week": _parse_json_dict(hw_json, int_keys=True),
                "topic_num_to_week": _parse_json_dict(topic_json, int_keys=True),
                "lab_num_to_week": _parse_json_dict(lab_json, int_keys=True),
                "study_guide_to_week": json.loads(study_json),
                "example_prompts": _parse_json_dict(example_json, int_keys=True),
            }
            cfg.save_overrides(overrides)
            st.success("Settings saved! Changes take effect immediately (except embedding/chunk settings).")
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
        except (ValueError, TypeError) as e:
            st.error(f"Invalid value: {e}")


def admin_page():
    if not check_admin_auth():
        admin_login()
    else:
        admin_dashboard()
