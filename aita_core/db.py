"""
SQLite database for interaction logs, feedback, and feature requests.
"""

import sqlite3
import os
from datetime import datetime

from aita_core.config import get_config

_initialized = False


def get_conn():
    global _initialized
    cfg = get_config()
    db_path = os.path.join(cfg.data_dir, "aita.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if not _initialized:
        _init_db(conn)
        _initialized = True
    return conn


def _init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            student_id TEXT NOT NULL,
            week INTEGER NOT NULL,
            question TEXT NOT NULL,
            response TEXT NOT NULL,
            sources TEXT,
            rating INTEGER
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            student_id TEXT NOT NULL,
            interaction_id INTEGER,
            rating INTEGER,
            comment TEXT,
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );

        CREATE TABLE IF NOT EXISTS feature_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            student_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open'
        );
    """)
    conn.commit()


# --- Interactions ---

def log_interaction(student_id, week, question, response, sources):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO interactions (timestamp, student_id, week, question, response, sources) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), student_id, week, question, response,
         ", ".join(sources) if sources else ""),
    )
    interaction_id = cur.lastrowid
    conn.commit()
    conn.close()
    return interaction_id


def get_interactions(limit=100, offset=0, student_id=None):
    conn = get_conn()
    if student_id:
        rows = conn.execute(
            "SELECT * FROM interactions WHERE student_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (student_id, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM interactions ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_interactions(student_id=None):
    conn = get_conn()
    if student_id:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM interactions WHERE student_id = ?",
            (student_id,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as cnt FROM interactions").fetchone()
    conn.close()
    return row["cnt"]


def rate_interaction(interaction_id, rating):
    conn = get_conn()
    conn.execute(
        "UPDATE interactions SET rating = ? WHERE id = ?",
        (rating, interaction_id),
    )
    conn.commit()
    conn.close()


# --- Feedback ---

def add_feedback(student_id, interaction_id, rating, comment):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (timestamp, student_id, interaction_id, rating, comment) "
        "VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), student_id, interaction_id, rating, comment),
    )
    conn.commit()
    conn.close()


def get_feedback(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT f.*, i.question, i.response FROM feedback f "
        "LEFT JOIN interactions i ON f.interaction_id = i.id "
        "ORDER BY f.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Feature Requests ---

def add_feature_request(student_id, title, description):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feature_requests (timestamp, student_id, title, description) "
        "VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), student_id, title, description),
    )
    conn.commit()
    conn.close()


def get_feature_requests(status=None, limit=100):
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM feature_requests WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feature_requests ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_feature_request_status(request_id, status):
    conn = get_conn()
    conn.execute(
        "UPDATE feature_requests SET status = ? WHERE id = ?",
        (status, request_id),
    )
    conn.commit()
    conn.close()


# --- Analytics helpers ---

def get_interaction_stats():
    conn = get_conn()
    stats = {}

    stats["total_interactions"] = conn.execute(
        "SELECT COUNT(*) as cnt FROM interactions"
    ).fetchone()["cnt"]

    stats["unique_students"] = conn.execute(
        "SELECT COUNT(DISTINCT student_id) as cnt FROM interactions"
    ).fetchone()["cnt"]

    stats["avg_rating"] = conn.execute(
        "SELECT AVG(rating) as avg FROM interactions WHERE rating IS NOT NULL"
    ).fetchone()["avg"]

    stats["interactions_by_week"] = [
        dict(r) for r in conn.execute(
            "SELECT week, COUNT(*) as cnt FROM interactions GROUP BY week ORDER BY week"
        ).fetchall()
    ]

    stats["interactions_by_day"] = [
        dict(r) for r in conn.execute(
            "SELECT DATE(timestamp) as day, COUNT(*) as cnt "
            "FROM interactions GROUP BY DATE(timestamp) ORDER BY day DESC LIMIT 30"
        ).fetchall()
    ]

    stats["top_students"] = [
        dict(r) for r in conn.execute(
            "SELECT student_id, COUNT(*) as cnt FROM interactions "
            "GROUP BY student_id ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
    ]

    stats["feedback_count"] = conn.execute(
        "SELECT COUNT(*) as cnt FROM feedback"
    ).fetchone()["cnt"]

    stats["open_feature_requests"] = conn.execute(
        "SELECT COUNT(*) as cnt FROM feature_requests WHERE status = 'open'"
    ).fetchone()["cnt"]

    conn.close()
    return stats
