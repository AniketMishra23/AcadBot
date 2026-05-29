"""
SQLite database layer.

Tables
------
universities  — one row per university URL (shared across users)
users         — one row per Telegram user, linked to a university
credentials   — encrypted login credentials per user per university
scraped_pages — raw page content indexed per university
"""

import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'acadbot.db')

# ─── Connection ───────────────────────────────────────────────────────────────

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    con = _conn()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS universities (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url            TEXT    UNIQUE NOT NULL,
            name           TEXT,
            login_required INTEGER DEFAULT 0,
            last_scraped   TEXT,
            page_count     INTEGER DEFAULT 0,
            created_at     TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT,
            first_name   TEXT,
            university_id INTEGER,
            onboarded    INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (university_id) REFERENCES universities(id)
        );

        CREATE TABLE IF NOT EXISTS credentials (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER UNIQUE,
            university_id  INTEGER,
            uni_username   TEXT,
            uni_password   TEXT,
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id)       REFERENCES users(user_id),
            FOREIGN KEY (university_id) REFERENCES universities(id)
        );

        CREATE TABLE IF NOT EXISTS scraped_pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id  INTEGER,
            url            TEXT,
            title          TEXT,
            content        TEXT,
            page_type      TEXT DEFAULT 'general',
            scraped_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (university_id) REFERENCES universities(id)
        );

        CREATE INDEX IF NOT EXISTS idx_pages_uni
            ON scraped_pages(university_id);
    """)
    con.commit()
    con.close()
    logger.info("Database ready.")


# ─── Users ────────────────────────────────────────────────────────────────────

def get_user(user_id):
    con = _conn()
    row = con.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    con.close()
    return row


def upsert_user(user_id, username, first_name):
    con = _conn()
    con.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)",
        (user_id, username, first_name)
    )
    con.commit()
    con.close()


def set_user_university(user_id, uni_id):
    con = _conn()
    con.execute(
        "UPDATE users SET university_id = ?, onboarded = 1 WHERE user_id = ?",
        (uni_id, user_id)
    )
    con.commit()
    con.close()


# ─── Universities ─────────────────────────────────────────────────────────────

def get_university(uni_id):
    con = _conn()
    row = con.execute("SELECT * FROM universities WHERE id = ?", (uni_id,)).fetchone()
    con.close()
    return row


def get_university_by_url(url):
    con = _conn()
    row = con.execute("SELECT * FROM universities WHERE url = ?", (url,)).fetchone()
    con.close()
    return row


def create_university(url, name=None, login_required=False):
    con = _conn()
    con.execute(
        "INSERT OR IGNORE INTO universities (url, name, login_required) VALUES (?,?,?)",
        (url, name, int(login_required))
    )
    con.commit()
    row = con.execute("SELECT * FROM universities WHERE url = ?", (url,)).fetchone()
    con.close()
    return row


def update_university_scraped(uni_id, page_count, name=None):
    con = _conn()
    if name:
        con.execute(
            "UPDATE universities SET page_count=?, last_scraped=?, name=? WHERE id=?",
            (page_count, datetime.now().isoformat(), name, uni_id)
        )
    else:
        con.execute(
            "UPDATE universities SET page_count=?, last_scraped=? WHERE id=?",
            (page_count, datetime.now().isoformat(), uni_id)
        )
    con.commit()
    con.close()


# ─── Scraped pages ────────────────────────────────────────────────────────────

def store_scraped_pages(uni_id, pages):
    con = _conn()
    con.execute("DELETE FROM scraped_pages WHERE university_id = ?", (uni_id,))
    con.executemany(
        "INSERT INTO scraped_pages (university_id, url, title, content, page_type) VALUES (?,?,?,?,?)",
        [(uni_id, p['url'], p['title'], p['content'], p['page_type']) for p in pages]
    )
    con.commit()
    con.close()


def search_pages(uni_id, query, limit=5):
    """Simple full-text keyword search over scraped pages."""
    like = f"%{query.lower()}%"
    con = _conn()
    rows = con.execute(
        """SELECT title, content, url, page_type
           FROM scraped_pages
           WHERE university_id = ?
             AND (LOWER(content) LIKE ? OR LOWER(title) LIKE ?)
           LIMIT ?""",
        (uni_id, like, like, limit)
    ).fetchall()
    con.close()
    return rows


# ─── Credentials ─────────────────────────────────────────────────────────────

def store_credentials(user_id, uni_id, uni_username, encrypted_password):
    con = _conn()
    con.execute(
        """INSERT OR REPLACE INTO credentials
           (user_id, university_id, uni_username, uni_password)
           VALUES (?,?,?,?)""",
        (user_id, uni_id, uni_username, encrypted_password)
    )
    con.commit()
    con.close()


def get_credentials(user_id):
    con = _conn()
    row = con.execute("SELECT * FROM credentials WHERE user_id = ?", (user_id,)).fetchone()
    con.close()
    return row
