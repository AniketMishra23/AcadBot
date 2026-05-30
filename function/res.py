"""
Resource finder.

Priority order:
  1. Semantic search via Qdrant (university vector index)
  2. Keyword search in PostgreSQL (scraped_pages table)
  3. Static pdflinks.txt fallback
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

LINKS_FILE = os.path.join(os.path.dirname(__file__), "pdflinks.txt")
MAX_RESPONSE = 3800   # Telegram hard limit is 4096; leave room for header


def _clean(text: str) -> str:
    """
    Convert markdown links [title](url) → title + url on separate lines,
    and strip other markdown so Telegram doesn't choke on special chars.
    """
    # [title](url) → title\nurl
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1\n\2', text)
    # Remove leftover * _ ` ~ characters
    text = re.sub(r'[*_`~]', '', text)
    return text.strip()


def findlink(query: str, uni_id: int | None = None) -> str:

    # ── 1. Semantic search via Qdrant ─────────────────────────────────────────
    if uni_id:
        try:
            from function import rag
            context = rag.query_university(uni_id, query)
            if context:
                body = _clean(context)
                result = f"🔍 Results for '{query}':\n\n{body}"
                return result[:MAX_RESPONSE]
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")

    # ── 2. DB keyword search ──────────────────────────────────────────────────
    if uni_id:
        try:
            from function.database import search_pages
            rows = search_pages(uni_id, query, limit=4)
            if rows:
                emoji_map = {
                    "result": "📊", "notice": "📢", "event": "🎉",
                    "material": "📚", "timetable": "🗓", "admission": "📝",
                }
                lines = [f"📋 Results for '{query}':\n"]
                for r in rows:
                    e = emoji_map.get(r["page_type"], "📄")
                    lines.append(f"{e} {r['title']} [{r['page_type']}]\n{r['url']}\n")
                result = "\n".join(lines)
                return result[:MAX_RESPONSE]
        except Exception as e:
            logger.warning(f"DB search failed: {e}")

    # ── 3. Static fallback ────────────────────────────────────────────────────
    query_lower = query.lower().strip()
    try:
        with open(LINKS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                keyword, url = parts[0].lower(), parts[-1]
                if keyword in query_lower or query_lower in keyword:
                    return f"📄 Resource for '{keyword}':\n{url}"
    except FileNotFoundError:
        logger.warning("pdflinks.txt not found.")

    return (
        "❌ No results found for your query.\n"
        "Try: results, syllabus, notices, events, timetable, admission"
    )
