"""
Database layer for Timber Beam Designer.
SQLite-based persistence for users, projects, and beams.
"""

import sqlite3
import hashlib
import os
import json
from datetime import datetime

# ── Database file location ─────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "..", "timber_beams.db")

# ── Keys to skip when serialising a beam (non-serialisable objects) ─
_SKIP_KEYS = {
    "results", "beam_actions", "section", "grade",
    "line_loads", "line_loads_cant", "active_entries", "point_load_list",
}

# ── Salt for password hashing ──────────────────────────────────────
_SALT = "magnitude_timber_v1"


# ══════════════════════════════════════════════════════════════════
# Connection
# ══════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ══════════════════════════════════════════════════════════════════
# Initialisation
# ══════════════════════════════════════════════════════════════════

def init_db():
    """Create tables and default admin account if they don't exist."""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                is_admin      INTEGER DEFAULT 0,
                created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                name        TEXT    NOT NULL,
                number      TEXT    DEFAULT '',
                address     TEXT    DEFAULT '',
                designer    TEXT    DEFAULT '',
                date        TEXT    DEFAULT '',
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS beams (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                name        TEXT    NOT NULL,
                position    INTEGER DEFAULT 0,
                beam_data   TEXT    NOT NULL,
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create default admin account if absent
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = 'admin'"
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)",
                ("admin", _hash("magnitude2024"), 1),
            )
            conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# Password helpers
# ══════════════════════════════════════════════════════════════════

def _hash(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), _SALT.encode(), 100_000
    ).hex()


def verify_password(password: str, stored_hash: str) -> bool:
    return _hash(password) == stored_hash


# ══════════════════════════════════════════════════════════════════
# User operations
# ══════════════════════════════════════════════════════════════════

def get_user(username: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_users() -> list:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_user(username: str, password: str, is_admin: bool = False) -> bool:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)",
            (username.strip(), _hash(password), 1 if is_admin else 0),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_user(user_id: int):
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM beams WHERE project_id IN "
            "(SELECT id FROM projects WHERE user_id = ?)", (user_id,)
        )
        conn.execute("DELETE FROM projects WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def change_password(user_id: int, new_password: str):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# Project operations
# ══════════════════════════════════════════════════════════════════

def create_project(user_id: int, name: str, number: str = "",
                   address: str = "", designer: str = "",
                   date_str: str = "") -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO projects (user_id, name, number, address, designer, date) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, name, number, address, designer, date_str),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_project(project_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_projects(user_id: int) -> list:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_projects() -> list:
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT p.*, u.username
            FROM   projects p
            JOIN   users    u ON p.user_id = u.id
            ORDER  BY u.username, p.updated_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_project(project_id: int, name: str, number: str,
                   address: str, designer: str, date_str: str):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE projects SET name=?, number=?, address=?, designer=?, "
            "date=?, updated_at=? WHERE id=?",
            (name, number, address, designer, date_str,
             datetime.now().isoformat(), project_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_project(project_id: int):
    conn = _connect()
    try:
        conn.execute("DELETE FROM beams WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


def get_beam_count(project_id: int) -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM beams WHERE project_id = ?", (project_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# Beam operations
# ══════════════════════════════════════════════════════════════════

def _serialise_beam(beam: dict) -> str:
    safe = {k: v for k, v in beam.items() if k not in _SKIP_KEYS}
    return json.dumps(safe, default=str)


def save_beams(project_id: int, beams: list):
    """Replace all beams for a project with the current in-memory list."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM beams WHERE project_id = ?", (project_id,))
        for i, beam in enumerate(beams):
            conn.execute(
                "INSERT INTO beams (project_id, name, position, beam_data) "
                "VALUES (?,?,?,?)",
                (project_id,
                 beam.get("name", f"Beam {i + 1}"),
                 i,
                 _serialise_beam(beam)),
            )
        conn.execute(
            "UPDATE projects SET updated_at=? WHERE id=?",
            (datetime.now().isoformat(), project_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_beams(project_id: int) -> list:
    """Return list of raw beam dicts for a project (no computed objects)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM beams WHERE project_id = ? ORDER BY position",
            (project_id,),
        ).fetchall()
        return [json.loads(row["beam_data"]) for row in rows]
    finally:
        conn.close()
