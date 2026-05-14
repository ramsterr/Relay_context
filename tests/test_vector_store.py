"""Tests for vector store in-memory backend."""
import pytest
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestInMemoryBackend:
    """Test in-memory vector store backend."""

    def test_add_and_count(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1", "id2", "id3"]
        embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        metadatas = [{"key": "val1"}, {"key": "val2"}, {"key": "val3"}]
        
        backend.add(ids, embeddings, metadatas)
        assert backend.count() == 3

    def test_query_by_similarity(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1", "id2"]
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        metadatas = [{"label": "a"}, {"label": "b"}]
        
        backend.add(ids, embeddings, metadatas)
        
        # Query similar to id1
        results = backend.query([0.9, 0.1], n_results=1)
        assert len(results) == 1
        assert results[0]["id"] == "id1"

    def test_query_with_filter(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1", "id2", "id3"]
        embeddings = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
        metadatas = [
            {"category": "A", "score": 10},
            {"category": "B", "score": 20},
            {"category": "A", "score": 30}
        ]
        
        backend.add(ids, embeddings, metadatas)
        
        # Filter by category A
        results = backend.query(
            [0.5, 0.5], 
            n_results=10,
            filter_metadata={"category": "A"}
        )
        assert len(results) <= 2
        for r in results:
            assert r["metadata"]["category"] == "A"

    def test_delete(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1", "id2"]
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        metadatas = [{"a": 1}, {"b": 2}]
        
        backend.add(ids, embeddings, metadatas)
        assert backend.count() == 2
        
        backend.delete(["id1"])
        assert backend.count() == 1

    def test_clear(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1", "id2"]
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        metadatas = [{"a": 1}, {"b": 2}]
        
        backend.add(ids, embeddings, metadatas)
        backend.clear()
        assert backend.count() == 0

    def test_numpy_array_conversion(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        ids = ["id1"]
        embeddings = [np.array([1.0, 0.0])]
        metadatas = [{"test": True}]
        
        backend.add(ids, embeddings, metadatas)
        assert backend.count() == 1

    def test_empty_query(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        results = backend.query([0.5, 0.5], n_results=5)
        assert results == []

    def test_query_more_than_available(self):
        from context_handover.storage.vector_store import InMemoryBackend
        
        backend = InMemoryBackend()
        backend.add(["id1"], [[1.0, 0.0]], [{"a": 1}])
        results = backend.query([1.0, 0.0], n_results=100)
        assert len(results) == 1

    def test_vector_store_protocol(self):
        from context_handover.storage.vector_store import InMemoryBackend, VectorStoreBackend
        
        backend = InMemoryBackend()
        # Verify it implements the protocol
        assert hasattr(backend, 'add')
        assert hasattr(backend, 'query')
        assert hasattr(backend, 'delete')
        assert hasattr(backend, 'count')
        assert hasattr(backend, 'clear')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
