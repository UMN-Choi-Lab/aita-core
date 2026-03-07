"""
Admin panel for AITA.
"""

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
    tab_history, tab_feedback, tab_requests = st.tabs([
        "Interaction History", "Feedback", "Feature Requests",
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


def admin_page():
    if not check_admin_auth():
        admin_login()
    else:
        admin_dashboard()
