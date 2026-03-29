"""
Vector Database Module
Handles vector storage and retrieval using different backends (Chroma, FAISS, Pinecone)
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod
from datetime import datetime
import json

from langchain_chroma import Chroma
from langchain_community.vectorstores import FAISS
from langchain_qdrant import QdrantVectorStore as LangChainQdrant
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import (
    VECTOR_DB_TYPE,
    CHROMA_PERSIST_DIRECTORY,
    CHROMA_COLLECTION_NAME,
    FAISS_INDEX_PATH,
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    QDRANT_PREFER_GRPC,
    TOP_K,
    SIMILARITY_THRESHOLD,
)
from embeddings import get_embedding_manager

logger = logging.getLogger(__name__)

class VectorStore(ABC):
    """Abstract base class for vector stores"""

    @abstractmethod
    def add_documents(self, documents: List[Document], ids: Optional[List[str]] = None) -> List[str]:
        """Add documents to the vector store"""
        pass

    @abstractmethod
    def search(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search for similar documents"""
        pass

    @abstractmethod
    def similarity_search_with_score(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search with similarity scores"""
        pass

    @abstractmethod
    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents by IDs"""
        pass

    @abstractmethod
    def get_document_count(self) -> int:
        """Get total document count"""
        pass

class ChromaVectorStore(VectorStore):
    """Chroma Vector Store implementation"""

    def __init__(self):
        logger.info(f"Initializing Chroma Vector Store")
        logger.info(f"Persist directory: {CHROMA_PERSIST_DIRECTORY}")
        
        embedding_manager = get_embedding_manager()
        
        self.vectorstore = Chroma(
            collection_name=CHROMA_COLLECTION_NAME,
            embedding_function=embedding_manager.embeddings,
            persist_directory=CHROMA_PERSIST_DIRECTORY,
        )
        
        logger.info("Chroma Vector Store initialized successfully")

    def add_documents(
        self, 
        documents: List[Document], 
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """Add documents to Chroma"""
        try:
            if ids is None:
                ids = [f"doc_{i}_{datetime.now().timestamp()}" for i in range(len(documents))]
            
            logger.info(f"Adding {len(documents)} documents to Chroma")
            added_ids = self.vectorstore.add_documents(documents, ids=ids)
            # Note: persist() removed - Chroma 0.4.x+ auto-persists documents
            
            logger.info(f"Successfully added {len(added_ids)} documents")
            return added_ids
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            raise

    def search(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search similar documents"""
        try:
            logger.debug(f"Searching for: {query[:100]}... (k={k})")
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            
            # Filter by similarity threshold
            filtered_results = [
                (doc, score) for doc, score in results 
                if (1 - score) >= SIMILARITY_THRESHOLD
            ]
            
            logger.debug(f"Found {len(filtered_results)} relevant documents")
            return filtered_results
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            raise

    def similarity_search_with_score(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search with scores"""
        return self.search(query, k=k)

    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents"""
        try:
            logger.info(f"Deleting {len(ids)} documents")
            self.vectorstore._collection.delete(ids=ids)
            # Note: persist() removed - Chroma 0.4.x+ auto-persists
            return True
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            return False

    def get_document_count(self) -> int:
        """Get document count"""
        try:
            count = self.vectorstore._collection.count()
            logger.info(f"Total documents in Chroma: {count}")
            return count
        except Exception as e:
            logger.error(f"Error getting document count: {str(e)}")
            return 0

class FAISSVectorStore(VectorStore):
    """FAISS Vector Store implementation"""

    def __init__(self):
        logger.info(f"Initializing FAISS Vector Store")
        logger.info(f"Index path: {FAISS_INDEX_PATH}")
        
        embedding_manager = get_embedding_manager()
        self.embedding_manager = embedding_manager
        
        try:
            self.vectorstore = FAISS.load_local(
                FAISS_INDEX_PATH,
                embedding_manager.embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("Loaded existing FAISS index")
        except Exception as e:
            logger.warning(f"No existing FAISS index found: {e}")
            self.vectorstore = None
        
        logger.info("FAISS Vector Store initialized")

    def add_documents(
        self, 
        documents: List[Document], 
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """Add documents to FAISS"""
        try:
            logger.info(f"Adding {len(documents)} documents to FAISS")
            
            if self.vectorstore is None:
                self.vectorstore = FAISS.from_documents(
                    documents,
                    self.embedding_manager.embeddings
                )
            else:
                self.vectorstore.add_documents(documents)
            
            # Save index
            self.vectorstore.save_local(FAISS_INDEX_PATH)
            
            if ids is None:
                ids = [f"doc_{i}" for i in range(len(documents))]
            
            logger.info(f"Successfully added {len(documents)} documents")
            return ids
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            raise

    def search(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search similar documents"""
        try:
            if self.vectorstore is None:
                logger.warning("FAISS index is empty")
                return []
            
            logger.debug(f"Searching for: {query[:100]}... (k={k})")
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            
            # Filter by similarity threshold
            filtered_results = [
                (doc, 1 - score) for doc, score in results 
                if (1 - score) >= SIMILARITY_THRESHOLD
            ]
            
            logger.debug(f"Found {len(filtered_results)} relevant documents")
            return filtered_results
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            return []

    def similarity_search_with_score(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search with scores"""
        return self.search(query, k=k)

    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents - FAISS doesn't support deletion, need to rebuild"""
        logger.warning("FAISS doesn't support document deletion. Please rebuild the index.")
        return False

    def get_document_count(self) -> int:
        """Get document count"""
        if self.vectorstore is None:
            return 0
        try:
            return self.vectorstore.index.ntotal
        except Exception as e:
            logger.error(f"Error getting document count: {str(e)}")
            return 0

class QdrantVectorStore(VectorStore):
    """Qdrant Vector Store implementation"""

    def __init__(self):
        logger.info(f"Initializing Qdrant Vector Store")
        logger.info(f"Qdrant URL: {QDRANT_URL}")
        logger.info(f"Collection name: {QDRANT_COLLECTION_NAME}")
        
        embedding_manager = get_embedding_manager()
        self.embedding_manager = embedding_manager
        
        # Initialize Qdrant client
        client_kwargs = {"url": QDRANT_URL}
        if QDRANT_API_KEY:
            client_kwargs["api_key"] = QDRANT_API_KEY
        if QDRANT_PREFER_GRPC:
            client_kwargs["prefer_grpc"] = True
        
        self.client = QdrantClient(**client_kwargs)
        
        # Initialize or get existing collection
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if QDRANT_COLLECTION_NAME not in collection_names:
                logger.info(f"Creating new collection: {QDRANT_COLLECTION_NAME}")
                self.client.create_collection(
                    collection_name=QDRANT_COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=embedding_manager.dimension,
                        distance=Distance.COSINE,
                    ),
                )
            else:
                logger.info(f"Using existing collection: {QDRANT_COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Error initializing collection: {str(e)}")
            raise
        
        # Initialize LangChain Qdrant wrapper
        self.vectorstore = LangChainQdrant(
            client=self.client,
            collection_name=QDRANT_COLLECTION_NAME,
            embeddings=embedding_manager.embeddings,
        )
        
        logger.info("Qdrant Vector Store initialized successfully")

    def add_documents(
        self, 
        documents: List[Document], 
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """Add documents to Qdrant"""
        try:
            if ids is None:
                ids = [f"doc_{i}_{datetime.now().timestamp()}" for i in range(len(documents))]
            
            logger.info(f"Adding {len(documents)} documents to Qdrant")
            added_ids = self.vectorstore.add_documents(documents, ids=ids)
            
            logger.info(f"Successfully added {len(added_ids)} documents")
            return added_ids
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            raise

    def search(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search similar documents"""
        try:
            logger.debug(f"Searching for: {query[:100]}... (k={k})")
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            
            # Qdrant returns scores where higher is more similar (cosine similarity)
            # Convert to standard format and filter by threshold
            filtered_results = [
                (doc, score) for doc, score in results 
                if score >= SIMILARITY_THRESHOLD
            ]
            
            logger.debug(f"Found {len(filtered_results)} relevant documents")
            return filtered_results
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            raise

    def similarity_search_with_score(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search with scores"""
        return self.search(query, k=k)

    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents from Qdrant"""
        try:
            logger.info(f"Deleting {len(ids)} documents from Qdrant")
            self.client.delete(
                collection_name=QDRANT_COLLECTION_NAME,
                points_selector=ids,
            )
            logger.info(f"Successfully deleted {len(ids)} documents")
            return True
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            return False

    def get_document_count(self) -> int:
        """Get document count from Qdrant"""
        try:
            collection_info = self.client.get_collection(QDRANT_COLLECTION_NAME)
            count = collection_info.points_count
            logger.info(f"Total documents in Qdrant: {count}")
            return count
        except Exception as e:
            logger.error(f"Error getting document count: {str(e)}")
            return 0

class VectorStoreManager:
    """Manages vector store operations with support for multiple backends"""

    def __init__(self, store_type: str = VECTOR_DB_TYPE):
        self.store_type = store_type
        self._init_store()

    def _init_store(self):
        """Initialize the vector store"""
        if self.store_type == "chroma":
            self.store = ChromaVectorStore()
        elif self.store_type == "faiss":
            self.store = FAISSVectorStore()
        elif self.store_type == "qdrant":
            self.store = QdrantVectorStore()
        else:
            logger.warning(f"Unknown store type {self.store_type}, defaulting to Chroma")
            self.store = ChromaVectorStore()

        logger.info(f"Vector store initialized: {self.store_type}")

    def add_documents(
        self, 
        documents: List[Document], 
        batch_size: int = 50
    ) -> List[str]:
        """
        Add documents in batches
        
        Args:
            documents: List of documents
            batch_size: Batch size for adding
            
        Returns:
            List of added document IDs
        """
        all_ids = []
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            logger.info(f"Adding batch {i//batch_size + 1}/{(len(documents) + batch_size - 1)//batch_size}")
            
            ids = self.store.add_documents(batch)
            all_ids.extend(ids)
        
        return all_ids

    def search(self, query: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Search for documents"""
        return self.store.search(query, k=k)

    def delete_documents(self, ids: List[str]) -> bool:
        """Delete documents"""
        return self.store.delete_documents(ids)

    def get_document_count(self) -> int:
        """Get total documents"""
        return self.store.get_document_count()

# Global vector store manager instance
_vector_store_manager: Optional[VectorStoreManager] = None

def get_vector_store() -> VectorStoreManager:
    """Get or create vector store manager singleton"""
    global _vector_store_manager
    if _vector_store_manager is None:
        _vector_store_manager = VectorStoreManager()
    return _vector_store_manager
