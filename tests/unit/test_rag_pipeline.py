"""Unit tests for RAG pipeline over Ethereum documentation.

Tests document indexing, vector storage with pgvector, and retrieval
for root cause analysis.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from chaoswopr.agents.rag_pipeline import (
    Document,
    RAGPipeline,
    RetrievalResult,
)


class TestDocument:
    """Tests for Document data class."""

    def test_creation(self) -> None:
        doc = Document(
            content="Ethereum consensus spec section 4.3.2",
            source="consensus-spec",
            metadata={"section": "4.3.2", "topic": "finality"},
        )
        assert doc.content == "Ethereum consensus spec section 4.3.2"
        assert doc.source == "consensus-spec"
        assert doc.metadata["topic"] == "finality"

    def test_chunk_id_generation(self) -> None:
        doc = Document(content="Test", source="test", chunk_id="test-1")
        assert doc.chunk_id == "test-1"


class TestRetrievalResult:
    """Tests for RetrievalResult data class."""

    def test_creation(self) -> None:
        result = RetrievalResult(
            content="Finality happens when...",
            source="consensus-spec",
            relevance_score=0.85,
            metadata={"section": "finality"},
        )
        assert result.content == "Finality happens when..."
        assert result.relevance_score == 0.85


class TestRAGPipeline:
    """Tests for RAG pipeline."""

    def test_initialization(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        assert pipeline.is_indexed is False

    def test_index_documents(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        docs = [
            Document(
                content="Ethereum uses proof-of-stake",
                source="ethereum-docs",
            ),
            Document(
                content="Validators propose and attest to blocks",
                source="consensus-spec",
            ),
        ]
        pipeline.index_documents(docs)
        assert pipeline.is_indexed
        assert pipeline.document_count == 2

    def test_index_from_files(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        # Mock file reading and existence check
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", create=True
        ) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                "Test content"
            )
            count = pipeline.index_from_files(["test.txt"])
            assert count == 1

    def test_retrieve_without_index(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        with pytest.raises(RuntimeError, match="not been indexed"):
            pipeline.retrieve("test query")

    def test_retrieve_in_dry_run(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        docs = [
            Document(content="Test content", source="test"),
        ]
        pipeline.index_documents(docs)
        results = pipeline.retrieve("test query", top_k=3)
        # In dry run mode, should return mock results
        assert len(results) >= 1
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_retrieve_with_threshold(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        docs = [Document(content="Test", source="test")]
        pipeline.index_documents(docs)
        results = pipeline.retrieve("query", top_k=5, min_relevance=0.8)
        # Results should be filtered by relevance threshold
        assert all(r.relevance_score >= 0.8 for r in results)

    def test_clear_index(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        docs = [Document(content="Test", source="test")]
        pipeline.index_documents(docs)
        assert pipeline.is_indexed
        pipeline.clear_index()
        assert not pipeline.is_indexed
        assert pipeline.document_count == 0

    def test_get_stats(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        stats = pipeline.get_stats()
        assert stats["is_indexed"] is False
        assert stats["document_count"] == 0

    def test_get_stats_after_indexing(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        docs = [
            Document(content="Doc 1", source="source1"),
            Document(content="Doc 2", source="source2"),
        ]
        pipeline.index_documents(docs)
        stats = pipeline.get_stats()
        assert stats["is_indexed"] is True
        assert stats["document_count"] == 2


class TestRAGPipelineChunking:
    """Tests for document chunking functionality."""

    def test_chunk_document(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        # Create a large document that needs chunking
        content = "Paragraph 1. " * 100 + "Paragraph 2. " * 100
        doc = Document(content=content, source="test")
        chunks = pipeline._chunk_document(doc, chunk_size=500)
        assert len(chunks) > 1
        assert all(len(chunk.content) <= 600 for chunk in chunks)  # Allow overlap

    def test_chunk_document_small(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        doc = Document(content="Short content", source="test")
        chunks = pipeline._chunk_document(doc, chunk_size=1000)
        assert len(chunks) == 1

    def test_chunk_preserves_metadata(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        doc = Document(
            content="Long content. " * 100,
            source="test",
            metadata={"section": "4.2"},
        )
        chunks = pipeline._chunk_document(doc, chunk_size=200)
        assert all(chunk.metadata.get("section") == "4.2" for chunk in chunks)
        assert all(chunk.source == "test" for chunk in chunks)


class TestRAGPipelineEmbedding:
    """Tests for embedding generation (dry-run mode)."""

    def test_generate_embedding(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        embedding = pipeline._generate_embedding("test text")
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    def test_embedding_dimensions(self) -> None:
        pipeline = RAGPipeline(dry_run=True)
        embedding1 = pipeline._generate_embedding("text 1")
        embedding2 = pipeline._generate_embedding("text 2")
        assert len(embedding1) == len(embedding2)
