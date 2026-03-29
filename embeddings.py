"""
Embedding Module
Handles text embeddings using various providers (OpenAI, SentenceTransformers)
"""

import logging
from typing import List, Optional
from abc import ABC, abstractmethod
import numpy as np

from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import (
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    OPENAI_API_KEY,
    ENABLE_GPU,
)

logger = logging.getLogger(__name__)

class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers"""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embed a single text"""
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get embedding dimension"""
        pass

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI Embeddings provider"""

    def __init__(self, model: str = "text-embedding-3-small"):
        logger.info(f"Initializing OpenAI Embeddings with model: {model}")
        self.model = model
        self.embeddings = OpenAIEmbeddings(
            model=model,
            api_key=OPENAI_API_KEY,
        )

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text"""
        return self.embeddings.embed_query(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        return self.embeddings.embed_documents(texts)

    def get_dimension(self) -> int:
        """Get embedding dimension"""
        if "small" in self.model:
            return 1536
        elif "large" in self.model:
            return 3072
        return 1536

class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Sentence Transformers Embeddings provider"""

    def __init__(self, model: str = "all-mpnet-base-v2"):
        logger.info(f"Initializing SentenceTransformers with model: {model}")
        self.model = model
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model,
            encode_kwargs={
                "normalize_embeddings": True,
                "device": "cuda" if ENABLE_GPU else "cpu",
            },
        )

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text"""
        return self.embeddings.embed_query(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        return self.embeddings.embed_documents(texts)

    def get_dimension(self) -> int:
        """Get embedding dimension"""
        if "base" in self.model:
            return 768
        elif "mini" in self.model or "small" in self.model:
            return 384
        return 768

class EmbeddingManager:
    """Manages embeddings with caching and batching"""

    def __init__(self, provider: str = EMBEDDING_PROVIDER, model: str = EMBEDDING_MODEL):
        self.provider_name = provider
        self.model = model
        self._init_provider()
        self._embedding_cache = {}

    def _init_provider(self):
        """Initialize the embedding provider"""
        if self.provider_name == "openai":
            self.provider = OpenAIEmbeddingProvider(self.model)
        elif self.provider_name == "sentence-transformers":
            self.provider = SentenceTransformerEmbeddingProvider(self.model)
        else:
            logger.warning(f"Unknown provider {self.provider_name}, using SentenceTransformers")
            self.provider = SentenceTransformerEmbeddingProvider()

        logger.info(
            f"Embedding provider initialized: {self.provider_name}, "
            f"Dimension: {self.provider.get_dimension()}"
        )

    @property
    def embeddings(self):
        """
        Property to access the underlying embeddings object
        Required for compatibility with LangChain vector stores
        """
        return self.provider.embeddings

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text with caching
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        # Check cache
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        # Generate embedding
        embedding = self.provider.embed_text(text)

        # Cache result
        self._embedding_cache[text] = embedding

        return embedding

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embed multiple texts with batching
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            
        Returns:
            List of embedding vectors
        """
        embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self.provider.embed_texts(batch)
            embeddings.extend(batch_embeddings)

            logger.debug(f"Embedded batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")

        return embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension"""
        return self.provider.get_dimension()

    def clear_cache(self):
        """Clear embedding cache"""
        self._embedding_cache.clear()
        logger.info("Embedding cache cleared")

# Global embedding manager instance
_embedding_manager: Optional[EmbeddingManager] = None

def get_embedding_manager() -> EmbeddingManager:
    """Get or create embedding manager singleton"""
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = EmbeddingManager()
    return _embedding_manager
