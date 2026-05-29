"""
Resource finder.

Priority order:
  1. Semantic search via RAG (university vector index) — most relevant
  2. Keyword search in DB (scraped_pages table)         — fast text match
  3. Static pdflinks.txt fallback
"""

import os
import logging

logger = logging.getLogger(__name__)

LINKS_FILE = os.path.join(os.path.dirname(__file__), "pdflinks.txt")


def findlink(query: str, uni_id: int | None = None) -> str:
    # ── 1. RAG semantic search ────────────────────────────────────
    if uni_id:
        try:
            from function import rag
            context = rag.query_university(uni_id, query)
            if context:
                return f"🔍 *Best matches for '{query}':*\n\n{context}"
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")

    # ── 2. DB keyword search ──────────────────────────────────────
    if uni_id:
        try:
            from function.database import search_pages
            rows = search_pages(uni_id, query, limit=4)
            if rows:
                lines = [f"📋 *Results for '{query}':*\n"]
                for r in rows:
                    emoji = {
                        "result": "📊", "notice": "📢", "event": "🎉",
                        "material": "📚", "timetable": "🗓️", "admission": "📝",
                    }.get(r["page_type"], "📄")
                    lines.append(f"{emoji} *{r['title']}*\n{r['url']}\n")
                return "\n".join(lines)
        except Exception as e:
            logger.warning(f"DB search failed: {e}")

    # ── 3. Static fallback ────────────────────────────────────────
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
                    return f"📄 Resource for *{keyword}*:\n{url}"
    except FileNotFoundError:
        logger.warning("pdflinks.txt not found.")

    return (
        "❌ Sorry, I couldn't find anything matching your query.\n"
        "Try keywords like: *results*, *syllabus*, *notices*, *events*, *timetable*, *admission*."
    )
