"""
AcadBot — Telegram bot for university students.

Features
────────
  • AI chat   — Groq (Llama 3.3 70B) with Gemini fallback
  • Uni info  — scrapes the student's university, answers from indexed content
  • PDF Q&A   — upload any PDF; chat with it locally (no ChatPDF API needed)
  • Resources — semantic + keyword search over scraped university pages

Onboarding flow (new user)
──────────────────────────
  /start → ask for university URL
         → auto-detect if login required
         → if yes → ask username → ask password (encrypted at rest)
         → background scrape + FAISS index
         → bot is ready
"""

import os
import time
import logging
import threading

import dotenv
import telebot
from cryptography.fernet import Fernet

from function.chat     import chatmodel, clear_history
from function.res      import findlink
from function          import rag
from function.database import (
    init_db, get_user, upsert_user, get_university,
    create_university, set_user_university,
    store_scraped_pages, update_university_scraped,
    store_credentials, get_credentials,
)
from function.scraper import scrape_university, check_login_required

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Init ─────────────────────────────────────────────────────────────────────

dotenv.load_dotenv()
init_db()

bot       = telebot.TeleBot(os.getenv("BOT_TOKEN"))

# ─── Encryption ───────────────────────────────────────────────────────────────

def _cipher() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        key = Fernet.generate_key().decode()
        logger.warning(
            "ENCRYPTION_KEY not set in .env — a temporary key was generated. "
            "Stored passwords will be unreadable after restart. "
            "Run: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and add the output as ENCRYPTION_KEY in .env"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(text: str) -> str:
    return _cipher().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()


# ─── States ───────────────────────────────────────────────────────────────────

S_NONE              = 0
S_WAITING_RESOURCE  = 1
S_WAITING_PDF       = 2
S_PDF_QA            = 3
S_ONBOARD_URL       = 4
S_ONBOARD_USER      = 5
S_ONBOARD_PASS      = 6

_states: dict[int, int]  = {}
_obdata: dict[int, dict] = {}   # onboarding scratch-pad


def _state(uid: int) -> int:       return _states.get(uid, S_NONE)
def _set(uid: int, s: int):        _states[uid] = s
def _uni_id(uid: int) -> int | None:
    u = get_user(uid)
    return u["university_id"] if u else None


# ─── Background scraping ──────────────────────────────────────────────────────

def _scrape_in_background(chat_id: int, user_id: int, uni_id: int,
                           url: str, credentials: dict | None = None):
    def _run():
        try:
            bot.send_message(chat_id,
                "🔍 Crawling your university site...\n"
                "_(This usually takes 1–2 minutes.)_",
                parse_mode="Markdown",
            )
            pages = scrape_university(url, credentials)

            if not pages:
                bot.send_message(chat_id,
                    "⚠️ Couldn't find content to index.\n"
                    "Check the URL and try again with /setup.")
                return

            # Persist + index
            store_scraped_pages(uni_id, pages)
            uni_name = urlparse(url).netloc
            update_university_scraped(uni_id, len(pages), uni_name)
            chunk_count = rag.index_university_pages(uni_id, pages)

            # Type breakdown
            counts: dict[str, int] = {}
            for p in pages:
                counts[p["page_type"]] = counts.get(p["page_type"], 0) + 1
            summary = "  ".join(
                f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])
            )

            bot.send_message(chat_id,
                f"✅ *University indexed!*\n\n"
                f"📊 Pages scraped : *{len(pages)}*\n"
                f"🧩 Chunks indexed: *{chunk_count}*\n"
                f"🗂️ Content: {summary}\n\n"
                f"You're all set! Try:\n"
                f"💬 Just ask me anything about your university\n"
                f"/resource — find study materials, results & notices\n"
                f"/pdf\\_qna — chat with any PDF\n"
                f"/help — all commands",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Background scrape failed for user {user_id}: {e}")
            bot.send_message(chat_id,
                "❌ Scraping failed. Please try /setup again.")

    threading.Thread(target=_run, daemon=True).start()


# ─── Commands ─────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid  = message.from_user.id
    name = message.from_user.first_name or "there"
    upsert_user(uid, message.from_user.username, name)
    user = get_user(uid)

    if user and user["onboarded"] and user["university_id"]:
        uni  = get_university(user["university_id"])
        uname = uni["name"] if uni else "your university"
        bot.reply_to(message,
            f"👋 Welcome back, *{name}*!\n🏫 University: *{uname}*\n\nHow can I help?",
            parse_mode="Markdown")
        _set(uid, S_NONE)
    else:
        bot.reply_to(message,
            f"👋 Hello *{name}*! I'm *AcadBot*, your university assistant.\n\n"
            "I can:\n"
            "💬 Answer academic questions\n"
            "🏫 Fetch live info from your university website\n"
            "📄 Let you chat with any PDF\n\n"
            "To get started, send me your *university website URL*.\n"
            "_(e.g. https://www.du.ac.in)_",
            parse_mode="Markdown")
        _set(uid, S_ONBOARD_URL)


@bot.message_handler(commands=["setup"])
def cmd_setup(message):
    uid = message.from_user.id
    bot.reply_to(message,
        "🔄 *University setup*\n\nSend me your university website URL:\n"
        "_(e.g. https://www.vit.ac.in)_",
        parse_mode="Markdown")
    _set(uid, S_ONBOARD_URL)


@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.reply_to(message,
        "📖 *AcadBot Commands*\n\n"
        "💬 *Chat* — type anything\n"
        "/resource — search notices, results, study material\n"
        "/pdf\\_qna — upload a PDF and ask questions about it\n"
        "/setup    — change or re-index your university\n"
        "/clear    — clear chat history & PDF session\n"
        "/help     — this message",
        parse_mode="Markdown")


@bot.message_handler(commands=["resource"])
def cmd_resource(message):
    uid = message.from_user.id
    _set(uid, S_WAITING_RESOURCE)
    bot.reply_to(message,
        "🔍 What are you looking for?\n"
        "_(e.g. exam results, syllabus, upcoming events, timetable)_",
        parse_mode="Markdown")


@bot.message_handler(commands=["pdf_qna"])
def cmd_pdf_qna(message):
    uid = message.from_user.id
    _set(uid, S_WAITING_PDF)
    bot.reply_to(message, "📄 Send me a PDF file and I'll answer your questions about it.")


@bot.message_handler(commands=["clear"])
def cmd_clear(message):
    uid = message.from_user.id
    clear_history(uid)
    rag.clear_session(uid)
    _set(uid, S_NONE)
    bot.reply_to(message, "🧹 Chat history and PDF session cleared!")


# ─── Document handler ─────────────────────────────────────────────────────────

@bot.message_handler(content_types=["document"])
def handle_document(message):
    uid = message.from_user.id

    if _state(uid) != S_WAITING_PDF:
        bot.reply_to(message, "Use /pdf_qna first, then send your PDF.")
        return

    fname = message.document.file_name or "upload.pdf"
    if not fname.lower().endswith(".pdf"):
        bot.reply_to(message, "⚠️ Please send a PDF file.")
        return

    bot.send_message(message.chat.id,
        f"📥 Received *{fname}* — processing...", parse_mode="Markdown")

    local_path = fname
    try:
        info   = bot.get_file(message.document.file_id)
        data   = bot.download_file(info.file_path)
        with open(local_path, "wb") as f:
            f.write(data)

        chunks = rag.index_pdf_for_session(uid, local_path)
        _set(uid, S_PDF_QA)
        bot.send_message(message.chat.id,
            f"✅ *{fname}* indexed! ({chunks} chunks)\n\n"
            "Ask me anything about it.\n"
            "_(Type *stop* to end the PDF session)_",
            parse_mode="Markdown")

    except Exception as e:
        logger.error(f"PDF error for user {uid}: {e}")
        bot.reply_to(message, "❌ Failed to process the PDF. Please try again.")
        _set(uid, S_NONE)
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


# ─── Main message handler ─────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    uid  = message.from_user.id
    text = (message.text or "").strip()
    st   = _state(uid)

    # ── Onboarding: URL ──────────────────────────────────────────────────────
    if st == S_ONBOARD_URL:
        url = text if text.startswith("http") else f"https://{text}"
        url = url.rstrip("/")
        bot.send_chat_action(message.chat.id, "typing")
        bot.send_message(message.chat.id, "🔎 Checking the site...")

        try:
            login_needed = check_login_required(url)
        except Exception:
            login_needed = False

        _obdata[uid] = {"url": url}

        if login_needed:
            bot.send_message(message.chat.id,
                "🔐 This site requires login.\n\n"
                "Enter your university *username or email*:\n"
                "_(Credentials are encrypted before storage)_",
                parse_mode="Markdown")
            _set(uid, S_ONBOARD_USER)
        else:
            uni    = create_university(url)
            uni_id = uni["id"]
            set_user_university(uid, uni_id)
            _set(uid, S_NONE)
            _scrape_in_background(message.chat.id, uid, uni_id, url)

    # ── Onboarding: username ─────────────────────────────────────────────────
    elif st == S_ONBOARD_USER:
        _obdata[uid]["username"] = text
        bot.send_message(message.chat.id,
            "🔑 Now enter your *password*:\n_(Encrypted immediately after receipt)_",
            parse_mode="Markdown")
        _set(uid, S_ONBOARD_PASS)

    # ── Onboarding: password ─────────────────────────────────────────────────
    elif st == S_ONBOARD_PASS:
        data       = _obdata.pop(uid, {})
        url        = data.get("url", "")
        username   = data.get("username", "")
        enc_pw     = encrypt(text)

        uni        = create_university(url, login_required=True)
        uni_id     = uni["id"]
        store_credentials(uid, uni_id, username, enc_pw)
        set_user_university(uid, uni_id)
        _set(uid, S_NONE)

        bot.send_message(message.chat.id, "🔒 Credentials saved securely.")
        _scrape_in_background(
            message.chat.id, uid, uni_id, url,
            credentials={"username": username, "password": text},
        )

    # ── Resource search ──────────────────────────────────────────────────────
    elif st == S_WAITING_RESOURCE:
        bot.send_chat_action(message.chat.id, "typing")
        reply = findlink(text, _uni_id(uid))
        bot.reply_to(message, reply, parse_mode="Markdown")
        _set(uid, S_NONE)

    # ── PDF Q&A ──────────────────────────────────────────────────────────────
    elif st == S_PDF_QA:
        if text.lower() in ("stop", "/stop"):
            rag.clear_session(uid)
            _set(uid, S_NONE)
            bot.reply_to(message, "📄 PDF session ended. Ask me anything else!")
            return

        bot.send_chat_action(message.chat.id, "typing")
        try:
            context = rag.query_session(uid, text)
            reply   = chatmodel(uid, text, context=context)
            bot.reply_to(message, reply)
            bot.send_message(message.chat.id,
                "_Another question? Or type *stop* to end._",
                parse_mode="Markdown")
        except Exception as e:
            logger.error(f"PDF Q&A error uid={uid}: {e}")
            bot.reply_to(message, "❌ Something went wrong. Please try again.")

    # ── General chat (+ university RAG) ──────────────────────────────────────
    else:
        bot.send_chat_action(message.chat.id, "typing")
        try:
            # Enrich with university context if available
            context = None
            uid_uni = _uni_id(uid)
            if uid_uni:
                context = rag.query_university(uid_uni, text)

            reply = chatmodel(uid, text, context=context)
            bot.reply_to(message, reply)
        except Exception as e:
            logger.error(f"Chat error uid={uid}: {e}")
            bot.reply_to(message, "❌ I ran into an error. Please try again.")
        _set(uid, S_NONE)


# ─── Start ────────────────────────────────────────────────────────────────────

from urllib.parse import urlparse   # noqa: E402 (used in _scrape_in_background)

logger.info("AcadBot starting...")
while True:
    try:
        bot.polling(non_stop=True, interval=0, timeout=30)
    except Exception as e:
        logger.error(f"Polling error: {e} — restarting in 5 s...")
        time.sleep(5)
