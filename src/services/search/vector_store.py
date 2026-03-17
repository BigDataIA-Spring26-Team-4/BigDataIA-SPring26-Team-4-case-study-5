"""
ChromaDB vector store with CS2 evidence metadata.

Task 7.2: Semantic Search with Metadata.
Indexes CS2 evidence with rich metadata (company_id, source_type,
signal_category, dimension, confidence, fiscal_year) for filtered
semantic retrieval.

Uses sentence-transformers for embedding (model name from CS4Settings).
"""

from typing import Any, Dict, List, Optional

import structlog

from src.config import CS4Settings, get_cs4_settings

logger = structlog.get_logger()


# ============================================================================
# Search Result
# ============================================================================


class SearchResult:
    """A single search result with score and metadata."""

    __slots__ = ("doc_id", "content", "score", "metadata")

    def __init__(self, doc_id: str, content: str, score: float, metadata: Dict[str, Any]):
        self.doc_id = doc_id
        self.content = content
        self.score = score
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


# ============================================================================
# Vector Store
# ============================================================================


class VectorStore:
    """
    Vector store preserving CS2 evidence metadata.

    Wraps ChromaDB PersistentClient with:
      - Cosine similarity search
      - Rich metadata filtering (company, dimension, source, confidence)
      - Sentence-transformer embeddings (model from env var)

    The encoder and ChromaDB client are lazily initialized on first use,
    so importing this module doesn't download models or create files.
    """

    def __init__(self, settings: CS4Settings = None):
        self._settings = settings or get_cs4_settings()
        self._client = None
        self._collection = None
        self._encoder = None

    # ── Lazy Initialization ─────────────────────────────────────

    @property
    def encoder(self):
        """Lazy-load sentence-transformer encoder."""
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            model_name = self._settings.embedding_model
            logger.info("loading_encoder", model=model_name)
            self._encoder = SentenceTransformer(model_name)
        return self._encoder

    @property
    def collection(self):
        """Lazy-load ChromaDB collection."""
        if self._collection is None:
            import chromadb

            persist_dir = self._settings.chroma_persist_dir
            logger.info("initializing_chromadb", persist_dir=persist_dir)

            try:
                # ChromaDB 1.x API
                self._client = chromadb.PersistentClient(
                    path=persist_dir,
                )
            except TypeError:
                # ChromaDB 0.4.x fallback
                from chromadb.config import Settings
                self._client = chromadb.PersistentClient(
                    path=persist_dir,
                    settings=Settings(anonymized_telemetry=False),
                )

            self._collection = self._client.get_or_create_collection(
                name="pe_evidence",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── Indexing ────────────────────────────────────────────────

    def index_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        Index documents with metadata into ChromaDB.

        Each document dict must have:
          - doc_id: str
          - content: str
          - metadata: dict (company_id, source_type, dimension, confidence, etc.)

        Returns count of documents indexed.
        """
        if not documents:
            return 0

        ids = []
        contents = []
        metadatas = []

        for doc in documents:
            doc_id = doc["doc_id"]
            content = doc["content"]
            metadata = doc.get("metadata", {})

            # ChromaDB requires metadata values to be str, int, float, or bool
            clean_meta = {}
            for k, v in metadata.items():
                if v is None:
                    clean_meta[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)

            ids.append(doc_id)
            contents.append(content)
            metadatas.append(clean_meta)

        # Encode all content at once (batched)
        embeddings = self.encoder.encode(contents).tolist()

        # Upsert into ChromaDB (handles duplicates)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )

        logger.info("documents_indexed", count=len(ids))
        return len(ids)

    def index_cs2_evidence(
        self,
        evidence_list: list,
        dimension_mapper: "DimensionMapper",
    ) -> int:
        """
        Index CS2Evidence objects with dimension mapping.

        Preserves: source_type, signal_category, confidence,
        company_id, dimension (from mapper), fiscal_year.
        """
        docs = []
        for e in evidence_list:
            primary_dim = dimension_mapper.get_primary_dimension(e.signal_category)
            dim_weights = dimension_mapper.get_dimension_weights(e.signal_category)

            docs.append({
                "doc_id": e.evidence_id,
                "content": e.content,
                "metadata": {
                    "company_id": e.company_id,
                    "source_type": e.source_type.value,
                    "signal_category": e.signal_category.value,
                    "dimension": primary_dim.value,
                    "dimension_weights": str({d.value: w for d, w in dim_weights.items()}),
                    "confidence": e.confidence,
                    "fiscal_year": e.fiscal_year or 0,
                    "source_url": e.source_url or "",
                },
            })

        return self.index_documents(docs)

    # ── Search ──────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 10,
        company_id: Optional[str] = None,
        dimension: Optional[str] = None,
        source_types: Optional[List[str]] = None,
        min_confidence: float = 0.0,
    ) -> List[SearchResult]:
        """
        Search with metadata filters.

        Args:
            query: Search text
            top_k: Number of results to return
            company_id: Filter by company
            dimension: Filter by dimension
            source_types: Filter by source types (OR logic)
            min_confidence: Minimum confidence threshold

        Returns:
            List of SearchResult sorted by relevance score (descending)
        """
        # Build ChromaDB where clause
        where_clauses = []
        if company_id:
            where_clauses.append({"company_id": company_id})
        if dimension:
            where_clauses.append({"dimension": dimension})
        if min_confidence > 0:
            where_clauses.append({"confidence": {"$gte": min_confidence}})
        if source_types and len(source_types) == 1:
            where_clauses.append({"source_type": source_types[0]})
        elif source_types and len(source_types) > 1:
            where_clauses.append({"source_type": {"$in": source_types}})

        # Combine clauses
        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        # Encode query
        query_embedding = self.encoder.encode(query).tolist()

        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where if where else None,
        )

        # Parse results
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                search_results.append(SearchResult(
                    doc_id=results["ids"][0][i],
                    content=results["documents"][0][i],
                    score=1 - results["distances"][0][i],  # cosine distance → similarity
                    metadata=results["metadatas"][0][i],
                ))

        return search_results

    def search_by_embedding(
        self,
        embedding: List[float],
        top_k: int = 10,
        company_id: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search by pre-computed embedding vector.

        Used by HyDE to search with a hypothetical document's embedding.
        """
        where = {}
        if company_id:
            where["company_id"] = company_id
        if dimension:
            where["dimension"] = dimension

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where if where else None,
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                search_results.append(SearchResult(
                    doc_id=results["ids"][0][i],
                    content=results["documents"][0][i],
                    score=1 - results["distances"][0][i],
                    metadata=results["metadatas"][0][i],
                ))

        return search_results

    # ── Stats ───────────────────────────────────────────────────

    def count(self) -> int:
        """Total number of indexed documents."""
        return self.collection.count()

    def get_stats(self) -> Dict[str, Any]:
        """Index statistics for health checks."""
        return {
            "total_documents": self.count(),
            "persist_dir": self._settings.chroma_persist_dir,
            "embedding_model": self._settings.embedding_model,
            "collection_name": "pe_evidence",
        }
