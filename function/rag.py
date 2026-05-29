"""
RAG pipeline — local, free, no external API.

University pages  ──embed──▶  FAISS on disk  (shared per university)
User-uploaded PDF ──embed──▶  FAISS in RAM   (per user session, cleared on stop)

Embedding model : all-MiniLM-L6-v2  (~90 MB, downloaded once, then cached)
Vector dim      : 384
"""

import os
import pickle
import logging

import numpy as np
import faiss
import pdfplumber
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

VECTOR_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'vector_stores')
CHUNK_SIZE   = 500    # characters per chunk
CHUNK_OVERLAP= 80
TOP_K        = 5
EMBED_DIM    = 384    # all-MiniLM-L6-v2

# ─── Singleton embedding model (loaded once on first use) ─────────────────────

_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model (first run downloads ~90 MB)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model ready.")
    return _model


# ─── VectorStore ─────────────────────────────────────────────────────────────

class VectorStore:
    """Thin wrapper around a FAISS flat index with metadata side-car."""

    def __init__(self):
        self.index  = faiss.IndexFlatL2(EMBED_DIM)
        self.chunks: list[dict] = []   # parallel list to FAISS vectors

    # ── write ──────────────────────────────────────────────────────────────

    def add(self, texts: list[str], metas: list[dict] | None = None):
        if not texts:
            return
        vecs = _get_model().encode(texts, show_progress_bar=False)
        self.index.add(np.array(vecs, dtype="float32"))
        for i, t in enumerate(texts):
            self.chunks.append({"text": t, "meta": (metas[i] if metas else {})})

    def save(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        faiss.write_index(self.index, os.path.join(directory, "index.faiss"))
        with open(os.path.join(directory, "chunks.pkl"), "wb") as f:
            pickle.dump(self.chunks, f)

    # ── read ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, directory: str) -> "VectorStore":
        store = cls()
        idx_path    = os.path.join(directory, "index.faiss")
        chunks_path = os.path.join(directory, "chunks.pkl")
        if os.path.exists(idx_path) and os.path.exists(chunks_path):
            store.index = faiss.read_index(idx_path)
            with open(chunks_path, "rb") as f:
                store.chunks = pickle.load(f)
            logger.info(f"Loaded {store.index.ntotal} vectors from {directory}")
        return store

    # ── query ──────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        vec = _get_model().encode([query], show_progress_bar=False)
        distances, indices = self.index.search(
            np.array(vec, dtype="float32"),
            min(top_k, self.index.ntotal)
        )
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:
                results.append({**self.chunks[idx], "score": float(dist)})
        return results


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    text = text.strip()
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start: start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _format_context(results: list[dict]) -> str | None:
    if not results:
        return None
    parts = []
    for r in results:
        meta  = r.get("meta", {})
        title = meta.get("title", "")
        url   = meta.get("url", "")
        page  = meta.get("page", "")
        src   = meta.get("source", "")
        if url:
            header = f"[{title or url}]({url})"
        elif src:
            header = f"[Page {page} of {src}]"
        else:
            header = title or "Source"
        parts.append(f"{header}\n{r['text']}")
    return "\n\n---\n\n".join(parts)


# ─── In-memory caches ────────────────────────────────────────────────────────

_uni_stores:     dict[int, VectorStore] = {}   # uni_id  → VectorStore (persisted)
_session_stores: dict[int, VectorStore] = {}   # user_id → VectorStore (in-RAM only)


# ─── University index (persisted to disk) ─────────────────────────────────────

def index_university_pages(uni_id: int, pages: list[dict]) -> int:
    """
    Build and save a FAISS index from a list of scraped pages.
    Returns the total number of chunks indexed.
    """
    store  = VectorStore()
    texts, metas = [], []

    for page in pages:
        content = (page.get("content") or "").strip()
        if not content:
            continue
        for chunk in _chunk(content):
            texts.append(chunk)
            metas.append({
                "url":       page.get("url", ""),
                "title":     page.get("title", ""),
                "page_type": page.get("page_type", "general"),
            })

    if texts:
        store.add(texts, metas)
        store.save(os.path.join(VECTOR_DIR, str(uni_id)))
        _uni_stores[uni_id] = store
        logger.info(f"University {uni_id}: indexed {len(texts)} chunks.")

    return len(texts)


def query_university(uni_id: int, question: str) -> str | None:
    """Return a formatted context string from the university index, or None."""
    if uni_id not in _uni_stores:
        path = os.path.join(VECTOR_DIR, str(uni_id))
        _uni_stores[uni_id] = VectorStore.load(path)

    results = _uni_stores[uni_id].search(question)
    return _format_context(results)


# ─── Session index (PDF uploads, in-memory only) ──────────────────────────────

def index_pdf_for_session(user_id: int, pdf_path: str) -> int:
    """
    Extract text from a PDF, chunk and embed it into a per-user session store.
    Returns total chunks indexed.
    """
    texts, metas = [], []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for chunk in _chunk(text):
                texts.append(chunk)
                metas.append({
                    "source": os.path.basename(pdf_path),
                    "page":   page_num,
                })

    if not texts:
        raise ValueError("No extractable text found in the PDF.")

    store = VectorStore()
    store.add(texts, metas)
    _session_stores[user_id] = store
    logger.info(f"User {user_id}: indexed {len(texts)} PDF chunks.")
    return len(texts)


def query_session(user_id: int, question: str) -> str | None:
    """Return formatted context from the user's active PDF session, or None."""
    store = _session_stores.get(user_id)
    if not store:
        return None
    return _format_context(store.search(question))


def clear_session(user_id: int):
    _session_stores.pop(user_id, None)
