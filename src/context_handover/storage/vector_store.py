"""
Vector database backends for scalable AtomRegistry storage.

Supports multiple backends:
- ChromaDB (default, lightweight)
- Qdrant (production-grade)
- In-memory (fallback for testing)
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Protocol, runtime_checkable
from abc import ABC, abstractmethod
import logging
import uuid
import numpy as np

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorStoreBackend(Protocol):
    """Protocol for vector store backends."""
    
    def add(self, ids: List[str], embeddings: List[List[float]], metadatas: List[Dict]) -> None:
        """Add vectors to the store."""
        ...
    
    def query(
        self, 
        query_embedding: List[float], 
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Query for similar vectors."""
        ...
    
    def delete(self, ids: List[str]) -> None:
        """Delete vectors by ID."""
        ...
    
    def count(self) -> int:
        """Return total number of vectors."""
        ...
    
    def clear(self) -> None:
        """Clear all vectors from the store."""
        ...


class ChromaBackend:
    """
    ChromaDB backend for vector storage.
    
    Features:
    - Persistent or in-memory storage
    - Metadata filtering
    - Automatic collection management
    """
    
    def __init__(
        self,
        collection_name: str = "context_atoms",
        persist_directory: Optional[str] = None,
        embedding_function: Optional[Any] = None,
    ):
        try:
            import chromadb
            from chromadb.config import Settings
            
            if persist_directory:
                self.client = chromadb.PersistentClient(path=persist_directory)
            else:
                self.client = chromadb.Client()
            
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},  # Cosine similarity by default
            )
            
            logger.info(f"ChromaDB backend initialized: {collection_name}")
            
        except ImportError:
            raise ImportError(
                "chromadb not installed. Install with: pip install chromadb"
            )
    
    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ) -> None:
        """Add atoms to ChromaDB collection."""
        if len(ids) != len(embeddings) or len(ids) != len(metadatas):
            raise ValueError("ids, embeddings, and metadatas must have same length")
        
        # Convert numpy arrays to lists if needed
        embeddings = [
            emb.tolist() if isinstance(emb, np.ndarray) else emb
            for emb in embeddings
        ]
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        
        logger.debug(f"Added {len(ids)} atoms to ChromaDB")
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Query similar atoms from ChromaDB."""
        where = filter_metadata if filter_metadata else None
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["embeddings", "metadatas", "distances"],
        )
        
        if not results["ids"] or not results["ids"][0]:
            return []
        
        # Format results
        formatted = []
        for i, atom_id in enumerate(results["ids"][0]):
            formatted.append({
                "id": atom_id,
                "embedding": results["embeddings"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else None,
                "similarity": 1 - results["distances"][0][i] if results["distances"] else None,
            })
        
        return formatted
    
    def delete(self, ids: List[str]) -> None:
        """Delete atoms from ChromaDB."""
        if ids:
            self.collection.delete(ids=ids)
            logger.debug(f"Deleted {len(ids)} atoms from ChromaDB")
    
    def count(self) -> int:
        """Return total atom count."""
        return self.collection.count()
    
    def clear(self) -> None:
        """Clear all atoms from collection."""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Cleared ChromaDB collection")


class QdrantBackend:
    """
    Qdrant backend for production-grade vector storage.
    
    Features:
    - Distributed deployment support
    - Advanced filtering
    - Payload-based metadata storage
    - High scalability
    """
    
    def __init__(
        self,
        collection_name: str = "context_atoms",
        url: Optional[str] = None,
        path: Optional[str] = None,
        embedding_size: int = 1536,  # Default for OpenAI embeddings
    ):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams
            
            if url:
                self.client = QdrantClient(url=url)
            elif path:
                self.client = QdrantClient(path=path)
            else:
                self.client = QdrantClient()  # In-memory
            
            self.collection_name = collection_name
            
            # Create collection if it doesn't exist
            collections = self.client.get_collections().collections
            if not any(c.name == collection_name for c in collections):
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=embedding_size,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {collection_name}")
            else:
                logger.info(f"Using existing Qdrant collection: {collection_name}")
            
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Install with: pip install qdrant-client"
            )
    
    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ) -> None:
        """Add atoms to Qdrant collection."""
        from qdrant_client.http.models import PointStruct
        
        if len(ids) != len(embeddings) or len(ids) != len(metadatas):
            raise ValueError("ids, embeddings, and metadatas must have same length")
        
        points = []
        for atom_id, embedding, metadata in zip(ids, embeddings, metadatas):
            # Convert ID to integer for Qdrant (or use UUID string hashing)
            point_id = uuid.UUID(atom_id).int if len(atom_id) > 20 else hash(atom_id) % (2**63)
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={**metadata, "original_id": atom_id},
                )
            )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        
        logger.debug(f"Added {len(ids)} atoms to Qdrant")
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Query similar atoms from Qdrant."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        query_filter = None
        if filter_metadata:
            conditions = [
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filter_metadata.items()
            ]
            query_filter = Filter(must=conditions)
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=n_results,
            query_filter=query_filter,
        )
        
        formatted = []
        for result in results:
            formatted.append({
                "id": result.payload.get("original_id", str(result.id)),
                "embedding": result.vector,
                "metadata": result.payload,
                "distance": result.score,
                "similarity": result.score,  # Qdrant returns cosine similarity directly
            })
        
        return formatted
    
    def delete(self, ids: List[str]) -> None:
        """Delete atoms from Qdrant."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        if not ids:
            return
        
        # Delete by original_id in payload
        conditions = [
            FieldCondition(key="original_id", match=MatchValue(value=atom_id))
            for atom_id in ids
        ]
        
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(must=conditions),
        )
        
        logger.debug(f"Deleted {len(ids)} atoms from Qdrant")
    
    def count(self) -> int:
        """Return total atom count."""
        from qdrant_client.http.models import CountRequest
        
        result = self.client.count(
            collection_name=self.collection_name,
        )
        return result.count
    
    def clear(self) -> None:
        """Clear all atoms from collection."""
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=self.client.get_collection(self.collection_name).config.params.vectors,
        )
        logger.info("Cleared Qdrant collection")


class InMemoryBackend:
    """
    Simple in-memory vector store for testing and development.
    
    NOT recommended for production use.
    Uses brute-force cosine similarity search.
    """
    
    def __init__(self):
        self.vectors: Dict[str, np.ndarray] = {}
        self.metadatas: Dict[str, Dict] = {}
        logger.warning("Using in-memory backend - not suitable for production")
    
    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ) -> None:
        """Add vectors to in-memory store."""
        for atom_id, embedding, metadata in zip(ids, embeddings, metadatas):
            self.vectors[atom_id] = np.array(embedding)
            self.metadatas[atom_id] = metadata
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Query using brute-force cosine similarity."""
        if not self.vectors:
            return []
        
        query_vec = np.array(query_embedding)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        
        scores = []
        for atom_id, vec in self.vectors.items():
            # Apply metadata filter if specified
            if filter_metadata:
                meta = self.metadatas.get(atom_id, {})
                if not all(meta.get(k) == v for k, v in filter_metadata.items()):
                    continue
            
            vec_norm = vec / (np.linalg.norm(vec) + 1e-10)
            similarity = float(np.dot(query_norm, vec_norm))
            scores.append((atom_id, similarity))
        
        # Sort by similarity (descending)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top n_results
        formatted = []
        for atom_id, similarity in scores[:n_results]:
            formatted.append({
                "id": atom_id,
                "embedding": self.vectors[atom_id].tolist(),
                "metadata": self.metadatas[atom_id],
                "distance": 1 - similarity,
                "similarity": similarity,
            })
        
        return formatted
    
    def delete(self, ids: List[str]) -> None:
        """Delete vectors from memory."""
        for atom_id in ids:
            self.vectors.pop(atom_id, None)
            self.metadatas.pop(atom_id, None)
    
    def count(self) -> int:
        """Return total vector count."""
        return len(self.vectors)
    
    def clear(self) -> None:
        """Clear all vectors."""
        self.vectors.clear()
        self.metadatas.clear()


def create_backend(
    backend_type: str = "chroma",
    **kwargs
) -> VectorStoreBackend:
    """
    Factory function to create vector store backend.
    
    Args:
        backend_type: One of 'chroma', 'qdrant', 'memory'
        **kwargs: Backend-specific arguments
    
    Returns:
        Configured VectorStoreBackend instance
    """
    backends = {
        "chroma": ChromaBackend,
        "qdrant": QdrantBackend,
        "memory": InMemoryBackend,
    }
    
    if backend_type not in backends:
        raise ValueError(
            f"Unknown backend type: {backend_type}. "
            f"Available: {list(backends.keys())}"
        )
    
    return backends[backend_type](**kwargs)
