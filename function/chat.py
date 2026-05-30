"""
Chat model — Groq (Llama 3.3 70B) as primary, Google Gemini as fallback.

Flow:
  user message + optional RAG context
        ↓
    Try Groq  ──fail──▶  Try Gemini  ──fail──▶  raise
        ↓
    response
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = (
    "You are AcadBot, an intelligent academic assistant for university students. "
    "You help with academic questions, understanding university notices and results, "
    "finding study resources, and general academic guidance. "
    "Be concise, friendly, and accurate. "
    "When answering from provided university context, cite the source title."
)

# Per-user message history:  {user_id: [{"role": "user"|"assistant", "content": "..."}]}
_histories: dict = {}
MAX_TURNS = 10          # keep last N user+assistant pairs


# ─── Public API ──────────────────────────────────────────────────────────────

def chatmodel(user_id: int, prompt: str, context: str | None = None) -> str:
    """
    Generate a reply for *user_id*.

    Parameters
    ----------
    user_id : Telegram user id (used to keep per-user history)
    prompt  : The user's raw message
    context : Optional RAG context injected before the question
    """
    history = _histories.get(user_id, [])

    # Build the actual message sent to the LLM
    if context:
        user_msg = (
            f"The following content was retrieved from the student's university website. "
            f"You MUST use this to answer the question. "
            f"Do NOT say you lack access to university data — it is provided below.\n\n"
            f"--- UNIVERSITY WEBSITE CONTENT ---\n{context}\n"
            f"--- END OF CONTENT ---\n\n"
            f"Student question: {prompt}"
        )
    else:
        user_msg = prompt

    history.append({"role": "user", "content": user_msg})

    # Try providers in order
    response = _try_groq(history) or _try_gemini(history)

    if response is None:
        raise RuntimeError("Both Groq and Gemini are unavailable. Please try again later.")

    history.append({"role": "assistant", "content": response})

    # Trim to MAX_TURNS pairs
    if len(history) > MAX_TURNS * 2:
        history = history[-(MAX_TURNS * 2):]

    _histories[user_id] = history
    return response


def clear_history(user_id: int):
    _histories.pop(user_id, None)


# ─── Providers ───────────────────────────────────────────────────────────────

def _try_groq(history: list) -> str | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping Groq.")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
            max_tokens=1024,
            temperature=0.7,
        )
        logger.info("Response served by Groq.")
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq failed ({e}) — falling back to Gemini.")
        return None


def _try_gemini(history: list) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping Gemini.")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
        )
        # Convert to Gemini format (all messages except the last)
        gemini_history = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in history[:-1]
        ]
        chat = model.start_chat(history=gemini_history)
        resp = chat.send_message(history[-1]["content"])
        logger.info("Response served by Gemini (fallback).")
        return resp.text
    except Exception as e:
        logger.warning(f"Gemini failed ({e}).")
        return None
