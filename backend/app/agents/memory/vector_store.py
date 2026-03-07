from __future__ import annotations

import threading

import chromadb

_singleton: VectorStore | None = None
_singleton_lock = threading.Lock()


class VectorStore:
    """Thin wrapper around ChromaDB providing three domain collections."""

    def __init__(self, persist_directory: str | None = None) -> None:
        if persist_directory is None:
            self._client = chromadb.Client()
        else:
            self._client = chromadb.PersistentClient(path=persist_directory)

        self._ideas = self._client.get_or_create_collection(
            name="idea_summaries",
            metadata={"hnsw:space": "cosine"},
        )
        self._news = self._client.get_or_create_collection(
            name="news_items",
            metadata={"hnsw:space": "cosine"},
        )
        self._patterns = self._client.get_or_create_collection(
            name="decision_patterns",
            metadata={"hnsw:space": "cosine"},
        )
        self._market_evidence = self._client.get_or_create_collection(
            name="market_evidence",
            metadata={"hnsw:space": "cosine"},
        )

    # ---- idea summaries ----

    def add_idea_summary(self, idea_id: str, summary: str) -> None:
        self._ideas.upsert(
            ids=[idea_id],
            documents=[summary],
            metadatas=[{"idea_id": idea_id}],
        )

    def search_similar_ideas(
        self,
        query: str,
        n_results: int = 3,
        exclude_id: str | None = None,
    ) -> list[dict]:
        # Query more results if we need to exclude one
        fetch_n = n_results + 1 if exclude_id else n_results
        count = self._ideas.count()
        if count == 0:
            return []
        fetch_n = min(fetch_n, count)
        results = self._ideas.query(query_texts=[query], n_results=fetch_n)

        out: list[dict] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idea_id, doc, dist in zip(ids, documents, distances):
            if exclude_id and idea_id == exclude_id:
                continue
            out.append({"idea_id": idea_id, "summary": doc, "distance": dist})
            if len(out) >= n_results:
                break
        return out

    # ---- news items ----

    def add_news_item(self, news_id: str, title: str, content: str) -> None:
        self._news.upsert(
            ids=[news_id],
            documents=[f"{title}. {content}"],
            metadatas=[{"news_id": news_id, "title": title}],
        )

    def match_news_to_ideas(self, news_id: str, n_results: int = 3) -> list[dict]:
        """Find ideas that are most relevant to a given news item."""
        news_results = self._news.get(ids=[news_id], include=["documents"])
        documents = news_results.get("documents", [])
        if not documents:
            return []
        news_text = documents[0]

        count = self._ideas.count()
        if count == 0:
            return []
        fetch_n = min(n_results, count)
        results = self._ideas.query(query_texts=[news_text], n_results=fetch_n)

        out: list[dict] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for idea_id, doc, dist in zip(ids, docs, distances):
            out.append({"idea_id": idea_id, "summary": doc, "distance": dist})
        return out

    # ---- decision patterns ----

    def add_decision_pattern(self, pattern_id: str, description: str) -> None:
        self._patterns.upsert(
            ids=[pattern_id],
            documents=[description],
            metadatas=[{"pattern_id": pattern_id}],
        )

    def search_patterns(self, query: str, n_results: int = 3) -> list[dict]:
        count = self._patterns.count()
        if count == 0:
            return []
        fetch_n = min(n_results, count)
        results = self._patterns.query(query_texts=[query], n_results=fetch_n)

        out: list[dict] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for pid, doc, dist in zip(ids, documents, distances):
            out.append({"pattern_id": pid, "description": doc, "distance": dist})
        return out

    # ---- market evidence ----

    def add_competitor_chunk(
        self, chunk_id: str, text: str, metadata: dict
    ) -> None:
        self._market_evidence.upsert(
            ids=[chunk_id],
            documents=[text],
            metadatas=[metadata],
        )

    def add_market_signal_chunk(
        self, chunk_id: str, text: str, metadata: dict
    ) -> None:
        self._market_evidence.upsert(
            ids=[chunk_id],
            documents=[text],
            metadatas=[metadata],
        )

    def add_evidence_insight_chunk(
        self, chunk_id: str, text: str, metadata: dict
    ) -> None:
        self._market_evidence.upsert(
            ids=[chunk_id],
            documents=[text],
            metadatas=[metadata],
        )

    def search_market_evidence(
        self,
        query: str,
        n_results: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        count = self._market_evidence.count()
        if count == 0:
            return []
        fetch_n = min(n_results, count)
        kwargs: dict = {"query_texts": [query], "n_results": fetch_n}
        if filters is not None:
            kwargs["where"] = filters
        results = self._market_evidence.query(**kwargs)

        out: list[dict] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        for chunk_id, doc, dist, meta in zip(ids, documents, distances, metadatas):
            out.append({
                "chunk_id": chunk_id,
                "text": doc,
                "metadata": meta,
                "distance": dist,
            })
        return out


def get_vector_store() -> VectorStore:
    """Module-level singleton factory. Thread-safe via double-checked locking.

    Uses DECISIONOS_CHROMA_PATH for persistence (default: ./chroma_data).
    Set DECISIONOS_CHROMA_PATH="" to force in-memory mode (useful in tests).
    """
    global _singleton  # noqa: PLW0603
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                from app.core.settings import get_settings
                chroma_path = get_settings().chroma_path  # None or "" → in-memory
                _singleton = VectorStore(persist_directory=chroma_path or None)
    return _singleton
