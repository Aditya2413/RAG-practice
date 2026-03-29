"""
Configuration module for RAG Pipeline application settings.

This module loads environment variables and provides a global Settings instance
using Pydantic's BaseSettings. It supports .env file loading and centralizes
all configuration for databases, APIs, and external services.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Optional, Literal, Set
import os
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Main configuration settings for RAG Pipeline"""
    
    # ============= Environment Configuration =============
    ENVIRONMENT: str = Field(default="development", description="Application environment")
    DEBUG: bool = Field(default=True, description="Debug mode flag")
    
    # ============= API Configuration =============
    API_HOST: str = Field(default="0.0.0.0", description="API host address")
    API_PORT: int = Field(default=8000, description="API port number")
    API_WORKERS: int = Field(default=4, description="Number of API workers")
    RELOAD_API: bool = Field(default=False, description="Enable API auto-reload in development")
    
    # ============= LLM Configuration =============
    LLM_PROVIDER: str = Field(default="openai", description="LLM provider (openai, local)")
    LLM_MODEL: str = Field(default="gpt-3.5-turbo", description="LLM model name")
    LLM_TEMPERATURE: float = Field(default=0.3, description="LLM temperature")
    LLM_MAX_TOKENS: int = Field(default=1024, description="Maximum tokens for LLM")
    OPENAI_API_KEY: Optional[str] = Field(default="", description="OpenAI API key")
    GROQ_API_KEY: Optional[str] = Field(default="", description="Groq API key")
    
    # ============= Embedding Configuration =============
    EMBEDDING_PROVIDER: str = Field(
        default="sentence-transformers", 
        description="Embedding provider (openai, sentence-transformers)"
    )
    EMBEDDING_MODEL: str = Field(
        default="all-mpnet-base-v2", 
        description="Embedding model name"
    )
    EMBEDDING_DIMENSION: int = Field(default=768, description="Embedding dimension")
    
    # ============= Vector Database Configuration =============
    VECTOR_DB_TYPE: str = Field(
        default="chroma", 
        description="Vector DB type (chroma, faiss, pinecone, qdrant)"
    )
    
    # Chroma Configuration
    CHROMA_PERSIST_DIRECTORY: str = Field(
        default="./data/chroma_db", 
        description="Chroma persistence directory"
    )
    CHROMA_COLLECTION_NAME: str = Field(
        default="rag_documents", 
        description="Chroma collection name"
    )
    
    # FAISS Configuration
    FAISS_INDEX_PATH: str = Field(
        default="./data/faiss_index", 
        description="FAISS index path"
    )
    
    # Pinecone Configuration
    PINECONE_API_KEY: Optional[str] = Field(default="", description="Pinecone API key")
    PINECONE_ENVIRONMENT: str = Field(
        default="production", 
        description="Pinecone environment"
    )
    PINECONE_INDEX_NAME: str = Field(
        default="rag-index", 
        description="Pinecone index name"
    )
    
    # Qdrant Configuration
    QDRANT_URL: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL"
    )
    QDRANT_API_KEY: Optional[str] = Field(default="", description="Qdrant API key")
    QDRANT_COLLECTION_NAME: str = Field(
        default="rag_documents",
        description="Qdrant collection name"
    )
    QDRANT_PREFER_GRPC: bool = Field(
        default=False,
        description="Use gRPC protocol for Qdrant (better performance)"
    )
    
    # ============= Document Processing Configuration =============
    SUPPORTED_DOCUMENT_TYPES: list[str] = Field(
        default=["pdf", "txt", "docx", "pptx", "csv", "xlsx", "html", "xml"],
        description="Supported document types"
    )
    
    # Chunking Configuration
    CHUNK_SIZE: int = Field(default=512, description="Document chunk size")
    CHUNK_OVERLAP: int = Field(default=51, description="Chunk overlap size")
    CHUNK_STRATEGY: str = Field(
        default="recursive", 
        description="Chunking strategy (fixed, recursive, semantic)"
    )
    
    # ============= Retrieval Configuration =============
    RETRIEVAL_TYPE: str = Field(
        default="similarity", 
        description="Retrieval type (similarity, hybrid, mmr)"
    )
    TOP_K: int = Field(default=5, description="Top K documents to retrieve")
    SIMILARITY_THRESHOLD: float = Field(
        default=0.3, 
        description="Similarity threshold for retrieval"
    )
    
    # Hybrid Search Configuration
    HYBRID_SEARCH_ENABLED: bool = Field(
        default=False, 
        description="Enable hybrid search"
    )
    KEYWORD_WEIGHT: float = Field(default=0.3, description="Keyword search weight")
    SEMANTIC_WEIGHT: float = Field(default=0.7, description="Semantic search weight")
    
    # ============= Memory Configuration =============
    CONVERSATION_MEMORY_TYPE: str = Field(
        default="buffer", 
        description="Conversation memory type (buffer, summary)"
    )
    MAX_MEMORY_MESSAGES: int = Field(
        default=10, 
        description="Maximum messages in memory"
    )
    ENABLE_QUERY_REWRITING: bool = Field(
        default=True, 
        description="Enable query rewriting"
    )
    
    # ============= Cache Configuration =============
    ENABLE_CACHE: bool = Field(default=True, description="Enable caching")
    CACHE_TTL_SECONDS: int = Field(default=3600, description="Cache TTL in seconds")
    
    # ============= Logging Configuration =============
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE: str = Field(
        default="./logs/rag_pipeline.log", 
        description="Log file path"
    )
    
    # ============= File Upload Configuration =============
    UPLOAD_DIRECTORY: str = Field(
        default="./data/uploads", 
        description="Upload directory path"
    )
    MAX_FILE_SIZE_MB: int = Field(
        default=100, 
        description="Maximum file size in MB"
    )
    
    # ============= Database Configuration =============
    MONGODB_URI: Optional[str] = Field(
        default="mongodb://localhost:27017", 
        description="MongoDB URI"
    )
    DATABASE_NAME: str = Field(
        default="rag_chatbot", 
        description="Database name"
    )
    
    # ============= Performance Configuration =============
    BATCH_SIZE: int = Field(default=32, description="Batch size for processing")
    NUM_THREADS: int = Field(default=4, description="Number of threads")
    ENABLE_GPU: bool = Field(default=False, description="Enable GPU acceleration")
    
    # ============= Feature Flags =============
    ENABLE_RERANKING: bool = Field(default=False, description="Enable reranking")
    ENABLE_QUERY_EXPANSION: bool = Field(
        default=False, 
        description="Enable query expansion"
    )
    ENABLE_SEMANTIC_CHUNKING: bool = Field(
        default=False, 
        description="Enable semantic chunking"
    )
    
    # ============= Evaluation Configuration =============
    ENABLE_EVALUATION_METRICS: bool = Field(
        default=True, 
        description="Enable evaluation metrics"
    )
    SAVE_EVALUATION_RESULTS: bool = Field(
        default=True, 
        description="Save evaluation results"
    )
    EVALUATION_OUTPUT_DIR: str = Field(
        default="./data/evaluation_results", 
        description="Evaluation output directory"
    )
    
    # ============= AWS Configuration =============
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default="", 
        description="AWS Access Key ID"
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default="", 
        description="AWS Secret Access Key"
    )
    AWS_REGION: str = Field(
        default="us-east-1", 
        description="AWS Region"
    )
    AWS_S3_BUCKET_NAME: str = Field(
        default="rag-chatbot-documents", 
        description="AWS S3 bucket name for document storage"
    )
    
    class Config:
        """Pydantic configuration"""
        env_file = env_path
        env_file_encoding = 'utf-8'
        extra = "ignore"
        case_sensitive = True


# Create global settings instance
settings = Settings()


# ============= Derived Properties =============
# Computed from settings for convenience
ALLOWED_EXTENSIONS: Set[str] = {ext.lower() for ext in settings.SUPPORTED_DOCUMENT_TYPES}


# ============= Directory Creation =============
# Create necessary directories on import
def _create_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        settings.UPLOAD_DIRECTORY,
        settings.CHROMA_PERSIST_DIRECTORY,
        os.path.dirname(settings.LOG_FILE),
        settings.EVALUATION_OUTPUT_DIR,
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)


# Auto-create directories on module import
_create_directories()


# ============= Exports =============
# Export commonly used settings for backward compatibility
ENVIRONMENT = settings.ENVIRONMENT
DEBUG = settings.DEBUG
API_HOST = settings.API_HOST
API_PORT = settings.API_PORT
API_WORKERS = settings.API_WORKERS
RELOAD_API = settings.RELOAD_API

LLM_PROVIDER = settings.LLM_PROVIDER
LLM_MODEL = settings.LLM_MODEL
LLM_TEMPERATURE = settings.LLM_TEMPERATURE
LLM_MAX_TOKENS = settings.LLM_MAX_TOKENS
OPENAI_API_KEY = settings.OPENAI_API_KEY
GROQ_API_KEY = settings.GROQ_API_KEY

EMBEDDING_PROVIDER = settings.EMBEDDING_PROVIDER
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION

VECTOR_DB_TYPE = settings.VECTOR_DB_TYPE
CHROMA_PERSIST_DIRECTORY = settings.CHROMA_PERSIST_DIRECTORY
CHROMA_COLLECTION_NAME = settings.CHROMA_COLLECTION_NAME
FAISS_INDEX_PATH = settings.FAISS_INDEX_PATH
PINECONE_API_KEY = settings.PINECONE_API_KEY
PINECONE_ENVIRONMENT = settings.PINECONE_ENVIRONMENT
PINECONE_INDEX_NAME = settings.PINECONE_INDEX_NAME
QDRANT_URL = settings.QDRANT_URL
QDRANT_API_KEY = settings.QDRANT_API_KEY
QDRANT_COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME
QDRANT_PREFER_GRPC = settings.QDRANT_PREFER_GRPC

SUPPORTED_DOCUMENT_TYPES = settings.SUPPORTED_DOCUMENT_TYPES
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
CHUNK_STRATEGY = settings.CHUNK_STRATEGY

RETRIEVAL_TYPE = settings.RETRIEVAL_TYPE
TOP_K = settings.TOP_K
SIMILARITY_THRESHOLD = settings.SIMILARITY_THRESHOLD
HYBRID_SEARCH_ENABLED = settings.HYBRID_SEARCH_ENABLED
KEYWORD_WEIGHT = settings.KEYWORD_WEIGHT
SEMANTIC_WEIGHT = settings.SEMANTIC_WEIGHT

CONVERSATION_MEMORY_TYPE = settings.CONVERSATION_MEMORY_TYPE
MAX_MEMORY_MESSAGES = settings.MAX_MEMORY_MESSAGES
ENABLE_QUERY_REWRITING = settings.ENABLE_QUERY_REWRITING

ENABLE_CACHE = settings.ENABLE_CACHE
CACHE_TTL_SECONDS = settings.CACHE_TTL_SECONDS

LOG_LEVEL = settings.LOG_LEVEL
LOG_FILE = settings.LOG_FILE

UPLOAD_DIRECTORY = settings.UPLOAD_DIRECTORY
MAX_FILE_SIZE_MB = settings.MAX_FILE_SIZE_MB

MONGODB_URI = settings.MONGODB_URI
DATABASE_NAME = settings.DATABASE_NAME

BATCH_SIZE = settings.BATCH_SIZE
NUM_THREADS = settings.NUM_THREADS
ENABLE_GPU = settings.ENABLE_GPU

ENABLE_RERANKING = settings.ENABLE_RERANKING
ENABLE_QUERY_EXPANSION = settings.ENABLE_QUERY_EXPANSION
ENABLE_SEMANTIC_CHUNKING = settings.ENABLE_SEMANTIC_CHUNKING

ENABLE_EVALUATION_METRICS = settings.ENABLE_EVALUATION_METRICS
SAVE_EVALUATION_RESULTS = settings.SAVE_EVALUATION_RESULTS
EVALUATION_OUTPUT_DIR = settings.EVALUATION_OUTPUT_DIR
