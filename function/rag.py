"""
RAG pipeline — hybrid cloud + local.

University indexes  →  Qdrant Cloud   (persistent, shared per university)
PDF session indexes →  in-memory FAISS (ephemeral, per user, cleared on 'stop')

Env vars required
-----------------
QDRANT_URL      — e.g. https://xyz.us-east4-0.gcp.cloud.qdrant.io
QDRANT_API_KEY  — from Qdrant Cloud console

Embedding model : all-MiniLM-L6-v2  (~90 MB, downloaded once, cached)
Vector dimension: 384
"""

import os
import uuid
import logging

import numpy as np
import faiss
import pdfplumber
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client import models as qm

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

UNI_COLLECTION = "university_chunks"   # single Qdrant collection, filtered by uni_id
CHUNK_SIZE     = 500
CHUNK_OVERLAP  = 80
TOP_K          = 5
EMBED_DIM      = 384

# ─── Singletons ──────────────────────────────────────────────────────────────

_model:  SentenceTransformer | None = None
_qdrant: QdrantClient        | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model (first run downloads ~90 MB)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model ready.")
    return _model


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
    return _qdrant


# ─── Qdrant collection bootstrap ─────────────────────────────────────────────

def _ensure_collection():
    """Create the university_chunks collection if it doesn't exist yet."""
    client = _get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if UNI_COLLECTION not in existing:
        client.create_collection(
            collection_name=UNI_COLLECTION,
            vectors_config=qm.VectorParams(size=EMBED_DIM, distance=qm.Distance.COSINE),
        )
        # Index the uni_id payload field for fast filtered queries
        client.create_payload_index(
            collection_name=UNI_COLLECTION,
            field_name="uni_id",
            field_schema=qm.PayloadSchemaType.INTEGER,
        )
        logger.info(f"Created Qdrant collection '{UNI_COLLECTION}'.")


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    text = text.strip()
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start: start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def _format_context(hits: list[dict]) -> str | None:
    if not hits:
        return None
    parts = []
    for h in hits:
        title = h.get("title", "")
        url   = h.get("url", "")
        page  = h.get("page", "")
        src   = h.get("source", "")
        text  = h.get("text", "")
        if url:
            header = f"[{title or url}]({url})"
        elif src:
            header = f"[Page {page} of {src}]"
        else:
            header = title or "Source"
        parts.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(parts)


# ─── University index (Qdrant Cloud) ─────────────────────────────────────────

def index_university_pages(uni_id: int, pages: list[dict]) -> int:
    """
    Embed scraped pages and upsert into Qdrant (replacing any previous vectors
    for this university).  Returns the number of chunks indexed.
    """
    _ensure_collection()
    client = _get_qdrant()

    # Remove stale vectors for this university before re-indexing
    client.delete(
        collection_name=UNI_COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="uni_id", match=qm.MatchValue(value=uni_id))]
            )
        ),
    )

    texts, payloads = [], []
    for page in pages:
        content = (page.get("content") or "").strip()
        if not content:
            continue
        for chunk in _chunk(content):
            texts.append(chunk)
            payloads.append({
                "uni_id":    uni_id,
                "text":      chunk,
                "url":       page.get("url", ""),
                "title":     page.get("title", ""),
                "page_type": page.get("page_type", "general"),
            })

    if not texts:
        return 0

    embeddings = _get_model().encode(texts, show_progress_bar=False)

    # Batch-upsert (Qdrant recommends ≤ 100 points per call)
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        client.upsert(
            collection_name=UNI_COLLECTION,
            points=[
                qm.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embeddings[j].tolist(),
                    payload=payloads[j],
                )
                for j in range(i, min(i + batch_size, len(texts)))
            ],
        )

    logger.info(f"University {uni_id}: upserted {len(texts)} chunks to Qdrant.")
    return len(texts)


def query_university(uni_id: int, question: str) -> str | None:
    """Semantic search over the university's Qdrant index."""
    try:
        _ensure_collection()
        client = _get_qdrant()
        query_vec = _get_model().encode([question], show_progress_bar=False)[0].tolist()

        results = client.search(
            collection_name=UNI_COLLECTION,
            query_vector=query_vec,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key="uni_id", match=qm.MatchValue(value=uni_id))]
            ),
            limit=TOP_K,
            with_payload=True,
        )

        if not results:
            return None

        hits = [r.payload for r in results]
        return _format_context(hits)

    except Exception as e:
        logger.warning(f"Qdrant query failed: {e}")
        return None


# ─── PDF session index (in-memory FAISS) ─────────────────────────────────────

class _SessionStore:
    """Lightweight in-memory vector store for a single user's PDF session."""

    def __init__(self):
        self.index  = faiss.IndexFlatL2(EMBED_DIM)
        self.chunks: list[dict] = []

    def add(self, texts: list[str], metas: list[dict]):
        if not texts:
            return
        vecs = _get_model().encode(texts, show_progress_bar=False)
        self.index.add(np.array(vecs, dtype="float32"))
        for t, m in zip(texts, metas):
            self.chunks.append({"text": t, **m})

    def search(self, query: str) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        vec = _get_model().encode([query], show_progress_bar=False)
        dists, idxs = self.index.search(
            np.array(vec, dtype="float32"),
            min(TOP_K, self.index.ntotal)
        )
        return [self.chunks[i] for i in idxs[0] if i != -1]


_session_stores: dict[int, _SessionStore] = {}


def index_pdf_for_session(user_id: int, pdf_path: str) -> int:
    """Extract, chunk, and embed a PDF into the user's session store."""
    texts, metas = [], []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for chunk in _chunk(page.extract_text() or ""):
                texts.append(chunk)
                metas.append({"source": os.path.basename(pdf_path), "page": page_num})

    if not texts:
        raise ValueError("No extractable text found in the PDF.")

    store = _SessionStore()
    store.add(texts, metas)
    _session_stores[user_id] = store
    logger.info(f"User {user_id}: indexed {len(texts)} PDF chunks in memory.")
    return len(texts)


def query_session(user_id: int, question: str) -> str | None:
    store = _session_stores.get(user_id)
    if not store:
        return None
    return _format_context(store.search(question))


def clear_session(user_id: int):
    _session_stores.pop(user_id, None)
