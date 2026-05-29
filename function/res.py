import os
import logging

logger = logging.getLogger(__name__)

# Path relative to the project root
LINKS_FILE = os.path.join(os.path.dirname(__file__), 'pdflinks.txt')


def findlink(query):
    """
    Search pdflinks.txt for a line whose keyword matches the user query.
    Each line is formatted as:  keyword  url
    Returns the URL string, or a not-found message.
    """
    query_lower = query.lower().strip()

    try:
        with open(LINKS_FILE, 'r') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                keyword = parts[0].lower()
                url = parts[-1]
                if keyword in query_lower or query_lower in keyword:
                    return f"Here's a resource for '{keyword}':\n{url}"
    except FileNotFoundError:
        logger.error(f"pdflinks.txt not found at {LINKS_FILE}")

    return "Sorry, I couldn't find any resource matching your query. Try keywords like 'mathematics', 'physics', 'chemistry', 'biology', or 'computer science'."
