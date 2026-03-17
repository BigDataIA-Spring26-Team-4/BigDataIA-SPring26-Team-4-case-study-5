"""
Hybrid retrieval with RRF fusion.

Task 8.1: Hybrid Retrieval combining dense and sparse search.
Dense retrieval finds semantically similar content.
Sparse retrieval (BM25) finds exact keyword matches.
Hybrid combines both using Reciprocal Rank Fusion:

    RRF_score(d) = Σ  w_r / (k + rank_r(d))
                   r∈R

Weights and RRF constant k are configurable via CS4Settings:
  CS4_DENSE_WEIGHT  (default 0.6)
  CS4_BM25_WEIGHT   (default 0.4)
  CS4_RRF_K         (default 60)
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

import structlog

from src.config import CS4Settings, get_cs4_settings
from src.services.search.vector_store import SearchResult, VectorStore

logger = structlog.get_logger()


# ============================================================================
# Retrieved Document (unified output)
# ============================================================================


class RetrievedDocument:
    """A document retrieved via hybrid search."""

    __slots__ = ("doc_id", "content", "metadata", "score", "retrieval_method")

    def __init__(
        self,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any],
        score: float,
        retrieval_method: str,
    ):
        self.doc_id = doc_id
        self.content = content
        self.metadata = metadata
        self.score = score
        self.retrieval_method = retrieval_method

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "metadata": self.metadata,
            "score": self.score,
            "retrieval_method": self.retrieval_method,
        }


# ============================================================================
# Hybrid Retriever
# ============================================================================


class HybridRetriever:
    """
    Hybrid retrieval combining dense (ChromaDB) and sparse (BM25) search.

    Index flow:
      1. index_documents() stores into both ChromaDB (dense) and
         an in-memory BM25 index (sparse).

    Retrieve flow:
      1. Dense retrieval via ChromaDB cosine similarity
      2. Sparse retrieval via BM25 keyword matching
      3. RRF fusion merges both ranked lists into a single ranking

    All hyperparameters come from CS4Settings (env vars).
    """

    def __init__(self, settings: CS4Settings = None, vector_store: VectorStore = None):
        self._settings = settings or get_cs4_settings()
        self._vector_store = vector_store or VectorStore(self._settings)

        # BM25 in-memory index
        self._bm25 = None
        self._corpus: List[str] = []
        self._doc_ids: List[str] = []
        self._doc_contents: List[str] = []
        self._doc_metadatas: List[Dict[str, Any]] = []

        # HyDE enhancer (lazy init — only activated if LLM is configured)
        self._hyde = None

    @property
    def vector_store(self) -> VectorStore:
        """Access the underlying vector store."""
        return self._vector_store

    # ── Indexing ────────────────────────────────────────────────

    def index_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        Index documents into both dense and sparse stores.

        Each document dict must have:
          - doc_id: str
          - content: str
          - metadata: dict (optional)

        Returns count of documents indexed.
        """
        if not documents:
            return 0

        # Dense indexing via ChromaDB
        self._vector_store.index_documents(documents)

        # Sparse indexing — upsert by doc_id to prevent duplicates
        existing_ids = set(self._doc_ids)
        for doc in documents:
            doc_id = doc["doc_id"]
            if doc_id in existing_ids:
                # Update existing entry
                idx = self._doc_ids.index(doc_id)
                self._corpus[idx] = doc["content"].lower()
                self._doc_contents[idx] = doc["content"]
                self._doc_metadatas[idx] = doc.get("metadata", {})
            else:
                # New entry
                self._corpus.append(doc["content"].lower())
                self._doc_ids.append(doc_id)
                self._doc_contents.append(doc["content"])
                self._doc_metadatas.append(doc.get("metadata", {}))
                existing_ids.add(doc_id)

        # Rebuild BM25 index from full corpus
        self._rebuild_bm25()

        logger.info(
            "hybrid_indexed",
            count=len(documents),
            total_corpus=len(self._corpus),
        )
        return len(documents)

    def _rebuild_bm25(self):
        """Rebuild BM25 index from current corpus."""
        from rank_bm25 import BM25Okapi

        tokenized = [doc.split() for doc in self._corpus]
        self._bm25 = BM25Okapi(tokenized)

    # ── Retrieval ───────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[RetrievedDocument]:
        """
        Run hybrid retrieval: dense + sparse + RRF fusion.

        Args:
            query: Search query text
            k: Number of final results to return
            filter_metadata: Optional metadata filter for dense search
                             e.g. {"company_id": "NVDA", "dimension": "data_infrastructure"}

        Returns:
            List of RetrievedDocument sorted by fused RRF score
        """
        # Over-retrieve from each method (3x) then fuse
        n = k * 3

        # ── HyDE query enhancement (if LLM configured) ───────
        dense_query = query  # Default: use raw query for dense
        hyde_used = False
        try:
            if self._hyde is None:
                from src.services.retrieval.hyde import HyDEEnhancer
                self._hyde = HyDEEnhancer(settings=self._settings)

            hyde_text = await self._hyde.generate_hypothetical_document(query)
            if hyde_text:
                dense_query = hyde_text
                hyde_used = True
                logger.info("hyde_enhanced", original_len=len(query), hyde_len=len(hyde_text))
        except Exception as e:
            logger.debug("hyde_skipped", reason=str(e))

        # ── Dense retrieval (uses HyDE text if available) ────
        dense_results = self._dense_retrieve(dense_query, n, filter_metadata)

        # ── Sparse retrieval (always uses raw query) ─────────
        sparse_results = self._sparse_retrieve(query, n, filter_metadata)

        # ── RRF Fusion ───────────────────────────────────────
        fused = self._rrf_fusion(dense_results, sparse_results, k)

        logger.info(
            "hybrid_retrieve",
            query_length=len(query),
            hyde_used=hyde_used,
            dense_count=len(dense_results),
            sparse_count=len(sparse_results),
            fused_count=len(fused),
        )
        return fused

    def _dense_retrieve(
        self,
        query: str,
        n: int,
        filter_metadata: Optional[Dict],
    ) -> List[RetrievedDocument]:
        """Dense retrieval via ChromaDB."""
        company_id = filter_metadata.get("company_id") if filter_metadata else None
        dimension = filter_metadata.get("dimension") if filter_metadata else None

        results = self._vector_store.search(
            query=query,
            top_k=n,
            company_id=company_id,
            dimension=dimension,
        )

        return [
            RetrievedDocument(
                doc_id=r.doc_id,
                content=r.content,
                metadata=r.metadata,
                score=r.score,
                retrieval_method="dense",
            )
            for r in results
        ]

    def _sparse_retrieve(
        self,
        query: str,
        n: int,
        filter_metadata: Optional[Dict],
    ) -> List[RetrievedDocument]:
        """Sparse retrieval via BM25."""
        if self._bm25 is None or len(self._corpus) == 0:
            return []

        # BM25 scoring
        query_tokens = query.lower().split()
        scores = self._bm25.get_scores(query_tokens)

        # Get top-n indices
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed_scores[:n]

        # Apply metadata filter if provided
        results = []
        for idx, score in top_indices:
            if score <= 0:
                continue

            meta = self._doc_metadatas[idx]

            # Filter check
            if filter_metadata:
                skip = False
                for fk, fv in filter_metadata.items():
                    if fk in meta and str(meta[fk]) != str(fv):
                        skip = True
                        break
                if skip:
                    continue

            results.append(RetrievedDocument(
                doc_id=self._doc_ids[idx],
                content=self._doc_contents[idx],
                metadata=meta,
                score=float(score),
                retrieval_method="sparse",
            ))

        return results

    def _rrf_fusion(
        self,
        dense: List[RetrievedDocument],
        sparse: List[RetrievedDocument],
        k: int,
    ) -> List[RetrievedDocument]:
        """
        Reciprocal Rank Fusion (RRF).

        RRF_score(d) = Σ  w_r / (rrf_k + rank_r(d) + 1)
                       r∈{dense, sparse}

        Parameters from CS4Settings:
          dense_weight (CS4_DENSE_WEIGHT, default 0.6)
          sparse_weight (CS4_BM25_WEIGHT, default 0.4)
          rrf_k (CS4_RRF_K, default 60)
        """
        dense_weight = self._settings.dense_weight
        sparse_weight = self._settings.bm25_weight
        rrf_k = self._settings.rrf_k

        rrf_scores: Dict[str, float] = defaultdict(float)
        doc_map: Dict[str, RetrievedDocument] = {}

        # Score dense results
        for rank, doc in enumerate(dense):
            rrf_scores[doc.doc_id] += dense_weight / (rrf_k + rank + 1)
            doc_map[doc.doc_id] = doc

        # Score sparse results
        for rank, doc in enumerate(sparse):
            rrf_scores[doc.doc_id] += sparse_weight / (rrf_k + rank + 1)
            if doc.doc_id not in doc_map:
                doc_map[doc.doc_id] = doc

        # Sort by fused score and take top-k
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda did: rrf_scores[did],
            reverse=True,
        )[:k]

        return [
            RetrievedDocument(
                doc_id=did,
                content=doc_map[did].content,
                metadata=doc_map[did].metadata,
                score=rrf_scores[did],
                retrieval_method="hybrid",
            )
            for did in sorted_ids
        ]

    # ── Stats ───────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Retriever statistics."""
        return {
            "dense": self._vector_store.get_stats(),
            "sparse": {
                "corpus_size": len(self._corpus),
                "bm25_initialized": self._bm25 is not None,
            },
            "weights": {
                "dense": self._settings.dense_weight,
                "sparse": self._settings.bm25_weight,
                "rrf_k": self._settings.rrf_k,
            },
        }
