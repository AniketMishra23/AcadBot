"""
Universal university website scraper.

Strategy
--------
1. Try to GET the base URL; detect if a login form is present.
2. If credentials are supplied, attempt form-based login via the requests session.
3. BFS-crawl the domain up to MAX_PAGES / MAX_DEPTH.
4. For every HTML page: extract title + clean text + PDF links.
5. Classify each page into one of the academic categories below.

No headless browser required — works for any university with a standard HTML
portal. For JavaScript-heavy SPAs, the text content will be minimal (a future
enhancement would swap the requests session for Playwright).
"""

import re
import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

MAX_PAGES  = 80
MAX_DEPTH  = 3
TIMEOUT    = 12  # seconds per request

SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
    ".zip", ".rar", ".exe", ".mp4", ".mp3", ".ppt",
    ".doc", ".docx", ".xls", ".xlsx",
}

PAGE_TYPES: dict[str, list[str]] = {
    "result":    ["result", "marksheet", "grade", "score", "merit list", "cgpa", "sgpa"],
    "notice":    ["notice", "circular", "announcement", "notification", "bulletin", "news"],
    "event":     ["event", "festival", "seminar", "workshop", "conference", "webinar", "fest"],
    "material":  ["syllabus", "material", "notes", "lecture", "study", "module", "question paper"],
    "timetable": ["timetable", "time table", "schedule", "routine", "exam date", "academic calendar"],
    "admission": ["admission", "enroll", "registration", "apply", "application", "fee"],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _same_domain(base: str, url: str) -> bool:
    return urlparse(base).netloc == urlparse(url).netloc


def _normalise(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def _detect_page_type(title: str, content: str) -> str:
    combined = f"{title} {content}".lower()
    for ptype, keywords in PAGE_TYPES.items():
        if any(kw in combined for kw in keywords):
            return ptype
    return "general"


def _has_login_form(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        pw_input = form.find("input", {"type": "password"})
        if pw_input:
            return True
    return False


def _extract_content(soup: BeautifulSoup, page_url: str) -> tuple[str, str]:
    """Return (title, clean_text) from a parsed page."""
    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
        tag.decompose()

    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # Prefer main content block if present
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"content|main|body", re.I))
        or soup.find(class_=re.compile(r"content|main|body", re.I))
    )
    body = main or soup.body or soup

    text = body.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    # Append PDF links found anywhere on the page
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            full = urljoin(page_url, href)
            label = a.get_text(strip=True) or "PDF"
            pdf_links.append(f"{label}: {full}")

    if pdf_links:
        text += "\n\nPDF Resources:\n" + "\n".join(pdf_links)

    return title, text[:6000]   # cap per page to keep index lean


# ─── Login ───────────────────────────────────────────────────────────────────

def _attempt_login(session: requests.Session, url: str, username: str, password: str) -> bool:
    """
    Detect the login form, fill it in, and POST.
    Returns True if login appears successful.
    """
    try:
        resp = session.get(url, timeout=TIMEOUT)
        soup = BeautifulSoup(resp.text, "html.parser")

        login_form = None
        for form in soup.find_all("form"):
            if form.find("input", {"type": "password"}):
                login_form = form
                break

        if not login_form:
            logger.warning("No login form found.")
            return False

        # Build form payload
        payload: dict[str, str] = {}
        for inp in login_form.find_all("input"):
            name = inp.get("name", "")
            itype = inp.get("type", "text").lower()
            if not name:
                continue
            if itype == "password":
                payload[name] = password
            elif itype in ("text", "email"):
                payload[name] = username
            elif itype == "hidden":
                payload[name] = inp.get("value", "")
            # skip submit / checkbox / radio

        action = login_form.get("action") or url
        if not action.startswith("http"):
            action = urljoin(url, action)

        method = login_form.get("method", "post").lower()
        post_resp = (
            session.post(action, data=payload, timeout=TIMEOUT)
            if method == "post"
            else session.get(action, params=payload, timeout=TIMEOUT)
        )

        # Heuristic success checks
        body_lower = post_resp.text.lower()
        if "logout" in body_lower or "dashboard" in body_lower or "welcome" in body_lower:
            logger.info("Login successful.")
            return True
        if "password" not in body_lower and "invalid" not in body_lower:
            logger.info("Login likely successful (no error keywords in response).")
            return True

        logger.warning("Login may have failed — password/invalid still present in response.")
        return False

    except Exception as e:
        logger.error(f"Login attempt raised: {e}")
        return False


# ─── Public API ──────────────────────────────────────────────────────────────

def check_login_required(url: str) -> bool:
    """
    GET the URL and return True if a password input field is found,
    or if we were redirected to a different page containing one.
    """
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        return _has_login_form(resp.text)
    except Exception as e:
        logger.warning(f"Could not check login requirement: {e}")
        return False


def scrape_university(base_url: str, credentials: dict | None = None) -> list[dict]:
    """
    Crawl *base_url* (same domain only) and return a list of page dicts:
        {"url", "title", "content", "page_type"}

    Parameters
    ----------
    base_url    : The university homepage URL.
    credentials : {"username": ..., "password": ...} or None.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # ── Login ────────────────────────────────────────────────────
    if credentials:
        logger.info(f"Attempting login at {base_url}")
        ok = _attempt_login(session, base_url, credentials["username"], credentials["password"])
        if not ok:
            logger.warning("Proceeding without successful login.")

    # ── BFS crawl ────────────────────────────────────────────────
    pages: list[dict] = []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]

    logger.info(f"Starting crawl: {base_url}")

    while queue and len(pages) < MAX_PAGES:
        url, depth = queue.pop(0)
        url = _normalise(url)

        if url in visited or depth > MAX_DEPTH:
            continue
        visited.add(url)

        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.status_code != 200:
                continue
            if "html" not in resp.headers.get("content-type", ""):
                continue

            soup  = BeautifulSoup(resp.text, "html.parser")
            title, content = _extract_content(soup, url)

            if len(content) < 60:    # skip nearly-empty pages
                continue

            ptype = _detect_page_type(title, content)
            pages.append({"url": url, "title": title, "content": content, "page_type": ptype})
            logger.info(f"  [{ptype:9s}] {title[:55]}")

            # Enqueue child links (same domain, skip files)
            if depth < MAX_DEPTH:
                for a in soup.find_all("a", href=True):
                    child = _normalise(urljoin(url, a["href"]))
                    ext   = os.path.splitext(urlparse(child).path)[1].lower()
                    if (
                        child not in visited
                        and _same_domain(base_url, child)
                        and ext not in SKIP_EXTENSIONS
                    ):
                        queue.append((child, depth + 1))

        except Exception as e:
            logger.debug(f"  Skipped {url}: {e}")

    logger.info(f"Crawl done — {len(pages)} pages scraped.")
    return pages


# ─── Needed by scraper only ──────────────────────────────────────────────────
import os   # noqa: E402  (needed for os.path.splitext inside the loop above)
