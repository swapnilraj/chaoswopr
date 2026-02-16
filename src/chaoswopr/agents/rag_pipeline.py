"""RAG (Retrieval-Augmented Generation) pipeline for Ethereum documentation.

Indexes Ethereum consensus specs, client documentation, CVEs, and incident reports
into pgvector for semantic search. Used by the Observer Agent's root cause analysis
engine to retrieve relevant context.

Key features:
- Document chunking with overlap for better retrieval
- Vector embeddings using sentence-transformers (or mock in dry-run)
- pgvector storage in existing PostgreSQL database
- Semantic similarity search
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any

# Note: In production, would use sentence-transformers for embeddings
# For dry-run testing, we use mock embeddings


@dataclass
class Document:
    """A document to be indexed in the RAG pipeline.

    Attributes:
        content: Document text content.
        source: Source identifier (e.g., "consensus-spec", "nethermind-docs").
        metadata: Additional metadata (section, topic, etc.).
        chunk_id: Unique identifier for this chunk.
    """

    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str | None = None

    def __post_init__(self) -> None:
        """Generate chunk_id if not provided."""
        if self.chunk_id is None:
            # Generate deterministic ID from content hash
            content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
            self.chunk_id = f"{self.source}-{content_hash}"


@dataclass
class RetrievalResult:
    """A document retrieval result from RAG search.

    Attributes:
        content: Retrieved document content.
        source: Source identifier.
        relevance_score: Similarity score (0-1, higher is more relevant).
        metadata: Document metadata.
        chunk_id: Document chunk ID.
    """

    content: str
    source: str
    relevance_score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str | None = None


class RAGPipeline:
    """RAG pipeline for indexing and retrieving Ethereum documentation.

    Uses pgvector extension in PostgreSQL for vector storage and similarity search.
    In dry-run mode, uses in-memory storage with mock embeddings.

    Examples:
        >>> pipeline = RAGPipeline(dry_run=True)
        >>> docs = [Document(content="Ethereum uses PoS", source="ethereum-docs")]
        >>> pipeline.index_documents(docs)
        >>> results = pipeline.retrieve("proof of stake", top_k=3)
    """

    def __init__(
        self,
        postgres_engine: Any | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        dry_run: bool = False,
    ) -> None:
        """Initialize the RAG pipeline.

        Args:
            postgres_engine: SQLAlchemy engine with pgvector extension.
            embedding_model: Sentence-transformers model name.
            chunk_size: Maximum characters per document chunk.
            chunk_overlap: Overlap between chunks for context preservation.
            dry_run: If True, use in-memory storage with mock embeddings.
        """
        self._postgres_engine = postgres_engine
        self._embedding_model_name = embedding_model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._dry_run = dry_run

        # In-memory storage for dry-run mode
        self._documents: list[Document] = []
        self._embeddings: dict[str, list[float]] = {}

        # Embedding model (loaded lazily)
        self._embedding_model: Any | None = None

        # Stats
        self._is_indexed = False

    @property
    def is_indexed(self) -> bool:
        """Check if documents have been indexed."""
        return self._is_indexed

    @property
    def document_count(self) -> int:
        """Get the number of indexed documents."""
        return len(self._documents)

    def index_documents(self, documents: list[Document]) -> None:
        """Index a list of documents.

        Documents are chunked, embedded, and stored in the vector database.

        Args:
            documents: List of documents to index.
        """
        all_chunks: list[Document] = []

        # Chunk documents
        for doc in documents:
            chunks = self._chunk_document(doc, chunk_size=self._chunk_size)
            all_chunks.extend(chunks)

        # Generate embeddings and store
        for chunk in all_chunks:
            embedding = self._generate_embedding(chunk.content)

            if self._dry_run:
                # In-memory storage
                self._documents.append(chunk)
                self._embeddings[chunk.chunk_id or ""] = embedding
            else:
                # Store in PostgreSQL with pgvector
                self._store_in_pgvector(chunk, embedding)

        self._is_indexed = True

    def index_from_files(
        self,
        file_paths: list[str],
        source_prefix: str = "file",
    ) -> int:
        """Index documents from files.

        Args:
            file_paths: List of file paths to index.
            source_prefix: Prefix for source identifiers.

        Returns:
            Number of documents indexed.
        """
        documents: list[Document] = []

        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Extract filename for source
            filename = os.path.basename(file_path)
            source = f"{source_prefix}:{filename}"

            doc = Document(
                content=content,
                source=source,
                metadata={"file_path": file_path},
            )
            documents.append(doc)

        self.index_documents(documents)
        return len(documents)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_relevance: float = 0.0,
    ) -> list[RetrievalResult]:
        """Retrieve relevant documents for a query.

        Args:
            query: Query text.
            top_k: Maximum number of results to return.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of retrieval results, sorted by relevance.

        Raises:
            RuntimeError: If index has not been created.
        """
        if not self._is_indexed:
            raise RuntimeError("RAG pipeline has not been indexed yet")

        # Generate query embedding
        query_embedding = self._generate_embedding(query)

        if self._dry_run:
            # In-memory similarity search
            results = self._search_in_memory(
                query_embedding, top_k, min_relevance
            )
        else:
            # pgvector similarity search
            results = self._search_pgvector(query_embedding, top_k, min_relevance)

        return results

    def clear_index(self) -> None:
        """Clear the index."""
        self._documents = []
        self._embeddings = {}
        self._is_indexed = False

    def get_stats(self) -> dict[str, Any]:
        """Get pipeline statistics.

        Returns:
            Dictionary with index stats.
        """
        return {
            "is_indexed": self._is_indexed,
            "document_count": len(self._documents),
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
            "embedding_model": self._embedding_model_name,
        }

    def _chunk_document(
        self,
        document: Document,
        chunk_size: int,
    ) -> list[Document]:
        """Split a document into overlapping chunks.

        Args:
            document: Document to chunk.
            chunk_size: Maximum characters per chunk.

        Returns:
            List of document chunks.
        """
        content = document.content
        chunks: list[Document] = []

        if len(content) <= chunk_size:
            # No need to chunk
            return [document]

        # Split by sentences (approximate)
        sentences = re.split(r"(?<=[.!?])\s+", content)

        current_chunk = ""
        chunk_index = 0

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence + " "
            else:
                # Save current chunk
                if current_chunk:
                    chunk = Document(
                        content=current_chunk.strip(),
                        source=document.source,
                        metadata={**document.metadata, "chunk_index": chunk_index},
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                # Start new chunk with overlap
                if self._chunk_overlap > 0 and current_chunk:
                    # Keep last N characters for overlap
                    overlap = current_chunk[-self._chunk_overlap :]
                    current_chunk = overlap + sentence + " "
                else:
                    current_chunk = sentence + " "

        # Add final chunk
        if current_chunk:
            chunk = Document(
                content=current_chunk.strip(),
                source=document.source,
                metadata={**document.metadata, "chunk_index": chunk_index},
            )
            chunks.append(chunk)

        return chunks

    def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Args:
            text: Input text.

        Returns:
            Embedding vector.
        """
        if self._dry_run:
            # Mock embedding for dry-run testing
            # Use simple hash-based mock that's deterministic
            text_hash = hashlib.sha256(text.encode()).digest()
            # Convert to float values in [-1, 1]
            embedding = [
                (b / 128.0) - 1.0 for b in text_hash[:384]
            ]  # 384-dim mock
            return embedding

        # In production, use sentence-transformers
        if self._embedding_model is None:
            # Lazy load
            try:
                from sentence_transformers import SentenceTransformer

                self._embedding_model = SentenceTransformer(self._embedding_model_name)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

        embedding = self._embedding_model.encode(text, convert_to_tensor=False)
        return embedding.tolist()

    def _search_in_memory(
        self,
        query_embedding: list[float],
        top_k: int,
        min_relevance: float,
    ) -> list[RetrievalResult]:
        """Search in-memory document store (dry-run mode).

        Args:
            query_embedding: Query embedding vector.
            top_k: Number of results.
            min_relevance: Minimum relevance threshold.

        Returns:
            List of retrieval results.
        """
        import math

        results: list[tuple[Document, float]] = []

        for doc in self._documents:
            doc_embedding = self._embeddings.get(doc.chunk_id or "", [])
            if not doc_embedding:
                continue

            # Cosine similarity
            similarity = self._cosine_similarity(query_embedding, doc_embedding)
            results.append((doc, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)

        # Take top_k and filter by threshold
        retrieval_results: list[RetrievalResult] = []
        for doc, score in results[:top_k]:
            if score >= min_relevance:
                retrieval_results.append(
                    RetrievalResult(
                        content=doc.content,
                        source=doc.source,
                        relevance_score=score,
                        metadata=doc.metadata,
                        chunk_id=doc.chunk_id,
                    )
                )

        return retrieval_results

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity (0-1).
        """
        import math

        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return max(0.0, min(1.0, dot_product / (mag1 * mag2)))

    def _store_in_pgvector(self, document: Document, embedding: list[float]) -> None:
        """Store document and embedding in PostgreSQL with pgvector.

        Args:
            document: Document to store.
            embedding: Embedding vector.
        """
        # In production, would use SQLAlchemy with pgvector extension
        # For now, this is a placeholder
        raise NotImplementedError("pgvector storage not implemented in this version")

    def _search_pgvector(
        self,
        query_embedding: list[float],
        top_k: int,
        min_relevance: float,
    ) -> list[RetrievalResult]:
        """Search pgvector database.

        Args:
            query_embedding: Query embedding.
            top_k: Number of results.
            min_relevance: Minimum relevance threshold.

        Returns:
            List of retrieval results.
        """
        # In production, would query pgvector using <=> operator
        raise NotImplementedError("pgvector search not implemented in this version")
