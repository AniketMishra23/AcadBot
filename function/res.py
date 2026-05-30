"""
Resource finder — formats output as Telegram HTML (parse_mode="HTML").
HTML is far more reliable than Markdown for URLs with dots/dashes/parens.

Priority order:
  1. Semantic search via Qdrant (university vector index)
  2. Keyword search in PostgreSQL (scraped_pages table)
  3. Static pdflinks.txt fallback
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

LINKS_FILE  = os.path.join(os.path.dirname(__file__), "pdflinks.txt")
MAX_RESPONSE = 3800   # Telegram hard limit is 4096


def _esc(text: str) -> str:
    """Escape special HTML chars so Telegram doesn't misparse them."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _context_to_html(context: str) -> str:
    """
    Convert _format_context() markdown output to Telegram HTML.
    Input pattern:  [Title](https://url)\nchunk text\n\n---\n\n...
    Output:         <b>Title</b>\n<a href="url">url</a>\nchunk text
    """
    html_parts = []
    for block in context.split("\n\n---\n\n"):
        block = block.strip()
        if not block:
            continue

        # Extract markdown link from first line if present
        match = re.match(r'^\[([^\]]*)\]\(([^)]+)\)(.*)', block, re.DOTALL)
        if match:
            title, url, rest = match.group(1), match.group(2), match.group(3).strip()
            html_parts.append(
                f'<b>{_esc(title)}</b>\n'
                f'<a href="{url}">{_esc(url)}</a>\n'
                f'{_esc(rest)}'
            )
        else:
            html_parts.append(_esc(block))

    return "\n\n".join(html_parts)


def findlink(query: str, uni_id: int | None = None) -> tuple[str, str]:
    """
    Returns (text, parse_mode) — caller passes both to bot.reply_to().
    """

    # ── 1. Semantic search via Qdrant ─────────────────────────────────────────
    if uni_id:
        try:
            from function import rag
            context = rag.query_university(uni_id, query)
            if context:
                body   = _context_to_html(context)
                result = f"🔍 <b>Results for '{_esc(query)}':</b>\n\n{body}"
                return result[:MAX_RESPONSE], "HTML"
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
                lines = [f"📋 <b>Results for '{_esc(query)}':</b>\n"]
                for r in rows:
                    e     = emoji_map.get(r["page_type"], "📄")
                    title = _esc(r["title"] or "")
                    url   = r["url"] or ""
                    ptype = _esc(r["page_type"] or "")
                    lines.append(
                        f'{e} <b>{title}</b> [{ptype}]\n'
                        f'<a href="{url}">{_esc(url)}</a>\n'
                    )
                result = "\n".join(lines)
                return result[:MAX_RESPONSE], "HTML"
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
                    return (
                        f"📄 Resource for <b>{_esc(keyword)}</b>:\n"
                        f'<a href="{url}">{_esc(url)}</a>',
                        "HTML"
                    )
    except FileNotFoundError:
        logger.warning("pdflinks.txt not found.")

    return (
        "❌ No results found for your query.\n"
        "Try: <b>results</b>, <b>syllabus</b>, <b>notices</b>, "
        "<b>events</b>, <b>timetable</b>, <b>admission</b>",
        "HTML"
    )
