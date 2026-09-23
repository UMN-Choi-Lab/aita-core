"""
SQLite database for interaction logs, feedback, and feature requests.
"""

import sqlite3
import os
import statistics
from datetime import datetime

from aita_core.config import get_config

_initialized = False


def get_conn():
    global _initialized
    cfg = get_config()
    db_path = os.path.join(cfg.data_dir, "aita.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
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
            reason TEXT,
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

        -- Replies from a candidate model, never shown to students. Written by
        -- aita_core.shadow so a migration can be judged on real traffic.
        CREATE TABLE IF NOT EXISTS shadow_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interaction_id INTEGER,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_variant TEXT,
            baseline_response TEXT,
            shadow_response TEXT,
            latency_ms INTEGER,
            baseline_latency_ms INTEGER,
            error TEXT,
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );
    """)
    conn.commit()

    # Migrations for existing databases
    try:
        conn.execute("SELECT reason FROM feedback LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE feedback ADD COLUMN reason TEXT")
        conn.commit()

    # shadow_interactions shipped without these; the table already exists in prod.
    for col, decl in (("prompt_variant", "TEXT"),
                      ("baseline_latency_ms", "INTEGER")):
        try:
            conn.execute(f"SELECT {col} FROM shadow_interactions LIMIT 0")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE shadow_interactions ADD COLUMN {col} {decl}")
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

def add_feedback(student_id, interaction_id, rating, comment, reason=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (timestamp, student_id, interaction_id, rating, reason, comment) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), student_id, interaction_id, rating, reason, comment),
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


# --- Shadow model ---

def get_shadow_pairs(limit=50, errors_only=False):
    """Recent shadow pairs, joined to the student turn that produced them."""
    conn = get_conn()
    where = "WHERE s.error IS NOT NULL" if errors_only else ""
    rows = conn.execute(
        f"""SELECT s.*, i.question, i.student_id, i.week, i.rating, i.sources
            FROM shadow_interactions s
            LEFT JOIN interactions i ON i.id = s.interaction_id
            {where}
            ORDER BY s.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _median(values):
    return round(statistics.median(values)) if values else None


def get_shadow_stats():
    """Descriptive comparison of every shadow pair logged so far.

    Deliberately cheap and judge-free: length, latency, and whether the reply ends
    on a question, which is the dimension the candidate model was weakest on.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT model, prompt_variant, latency_ms, baseline_latency_ms, error,"
            " shadow_response, baseline_response FROM shadow_interactions"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()

    ok = [r for r in rows if not r["error"]]

    def ends_q(col):
        texts = [r[col] or "" for r in ok]
        asked = sum(1 for t in texts if t.rstrip().endswith("?"))
        return round(100 * asked / len(texts)) if texts else None

    return {
        "total": len(rows),
        "errors": sum(1 for r in rows if r["error"]),
        "models": sorted({r["model"] for r in rows}),
        "variants": sorted({r["prompt_variant"] or "base" for r in rows}),
        "shadow_ms": _median([r["latency_ms"] for r in ok if r["latency_ms"]]),
        "baseline_ms": _median([r["baseline_latency_ms"] for r in ok
                                if r["baseline_latency_ms"]]),
        "shadow_chars": _median([len(r["shadow_response"] or "") for r in ok]),
        "baseline_chars": _median([len(r["baseline_response"] or "") for r in ok]),
        "shadow_ends_q": ends_q("shadow_response"),
        "baseline_ends_q": ends_q("baseline_response"),
    }
