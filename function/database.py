"""
PostgreSQL database layer (Railway-hosted).

Env var required
----------------
DATABASE_URL  — provided automatically by Railway when you add a Postgres addon,
                or set manually for any other hosted Postgres (Neon, Supabase, etc.)

Tables
------
universities  — one row per university URL, shared across users
users         — one row per Telegram user, linked to a university
credentials   — encrypted login credentials per user
scraped_pages — raw page content per university (used for keyword fallback search)
"""

import os
import logging
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ─── Connection ───────────────────────────────────────────────────────────────

def _conn():
    url = os.getenv("DATABASE_URL", "")
    # Normalize older 'postgres://' prefix that some platforms still emit
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(url, connect_timeout=10)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def init_db():
    conn = _conn()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS universities (
            id             SERIAL PRIMARY KEY,
            url            TEXT UNIQUE NOT NULL,
            name           TEXT,
            login_required BOOLEAN  DEFAULT FALSE,
            last_scraped   TIMESTAMP,
            page_count     INTEGER  DEFAULT 0,
            created_at     TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       BIGINT PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            university_id INTEGER REFERENCES universities(id),
            onboarded     BOOLEAN   DEFAULT FALSE,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            id            SERIAL PRIMARY KEY,
            user_id       BIGINT UNIQUE REFERENCES users(user_id),
            university_id INTEGER   REFERENCES universities(id),
            uni_username  TEXT,
            uni_password  TEXT,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scraped_pages (
            id            SERIAL PRIMARY KEY,
            university_id INTEGER REFERENCES universities(id),
            url           TEXT,
            title         TEXT,
            content       TEXT,
            page_type     TEXT      DEFAULT 'general',
            scraped_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_scraped_pages_uni
            ON scraped_pages(university_id)
    """)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database ready.")


# ─── Users ────────────────────────────────────────────────────────────────────

def get_user(user_id):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row


def upsert_user(user_id, username, first_name):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO users (user_id, username, first_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (user_id) DO NOTHING""",
        (user_id, username, first_name)
    )
    conn.commit()
    cur.close(); conn.close()


def set_user_university(user_id, uni_id):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE users SET university_id = %s, onboarded = TRUE WHERE user_id = %s",
        (uni_id, user_id)
    )
    conn.commit()
    cur.close(); conn.close()


# ─── Universities ─────────────────────────────────────────────────────────────

def get_university(uni_id):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM universities WHERE id = %s", (uni_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row


def get_university_by_url(url):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM universities WHERE url = %s", (url,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row


def create_university(url, name=None, login_required=False):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO universities (url, name, login_required)
           VALUES (%s, %s, %s)
           ON CONFLICT (url) DO NOTHING""",
        (url, name, login_required)
    )
    conn.commit()
    cur.execute("SELECT * FROM universities WHERE url = %s", (url,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row


def update_university_scraped(uni_id, page_count, name=None):
    conn = _conn()
    cur  = conn.cursor()
    if name:
        cur.execute(
            "UPDATE universities SET page_count=%s, last_scraped=%s, name=%s WHERE id=%s",
            (page_count, datetime.now(), name, uni_id)
        )
    else:
        cur.execute(
            "UPDATE universities SET page_count=%s, last_scraped=%s WHERE id=%s",
            (page_count, datetime.now(), uni_id)
        )
    conn.commit()
    cur.close(); conn.close()


# ─── Scraped pages ────────────────────────────────────────────────────────────

def store_scraped_pages(uni_id, pages):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM scraped_pages WHERE university_id = %s", (uni_id,))
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO scraped_pages (university_id, url, title, content, page_type)
           VALUES (%s, %s, %s, %s, %s)""",
        [(uni_id, p["url"], p["title"], p["content"], p["page_type"]) for p in pages]
    )
    conn.commit()
    cur.close(); conn.close()


def search_pages(uni_id, query, limit=5):
    """Keyword fallback search over scraped page content."""
    like = f"%{query.lower()}%"
    conn = _conn()
    cur  = conn.cursor()
    cur.execute(
        """SELECT title, content, url, page_type
           FROM scraped_pages
           WHERE university_id = %s
             AND (LOWER(content) LIKE %s OR LOWER(title) LIKE %s)
           LIMIT %s""",
        (uni_id, like, like, limit)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


# ─── Credentials ─────────────────────────────────────────────────────────────

def store_credentials(user_id, uni_id, uni_username, encrypted_password):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO credentials (user_id, university_id, uni_username, uni_password)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_id) DO UPDATE
               SET university_id=%s, uni_username=%s, uni_password=%s""",
        (user_id, uni_id, uni_username, encrypted_password,
         uni_id, uni_username, encrypted_password)
    )
    conn.commit()
    cur.close(); conn.close()


def get_credentials(user_id):
    conn = _conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM credentials WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row
