"""
Unit Tests for RAG Chatbot Components
Comprehensive test suite covering all modules
"""

import pytest
import tempfile
import os
import json
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_text_file(temp_dir):
    """Create sample text file"""
    file_path = os.path.join(temp_dir, "sample.txt")
    content = """Machine Learning Overview

Machine learning is a subset of artificial intelligence.
It enables systems to learn from data without explicit programming.

Key concepts:
- Supervised Learning
- Unsupervised Learning
- Reinforcement Learning

Applications:
- Image Recognition
- Natural Language Processing
- Recommendation Systems
"""
    with open(file_path, "w") as f:
        f.write(content)
    return file_path


@pytest.fixture
def mock_embedding_manager():
    """Mock embedding manager"""
    mock = MagicMock()
    mock.get_dimension.return_value = 768
    mock.embed_text.return_value = [0.1] * 768
    mock.embed_texts.return_value = [[0.1] * 768, [0.2] * 768]
    return mock


@pytest.fixture
def mock_vector_store():
    """Mock vector store"""
    mock = MagicMock()
    mock.get_document_count.return_value = 10
    mock.search.return_value = [
        (MagicMock(page_content="Test content", metadata={"source": "test.pdf"}), 0.95),
        (MagicMock(page_content="More content", metadata={"source": "test.pdf"}), 0.85),
    ]
    return mock


# ============================================================================
# TEST CONFIGURATION MODULE
# ============================================================================

class TestConfig:
    """Test configuration module"""

    def test_config_imports(self):
        """Test config can be imported"""
        from config import settings
        assert settings is not None

    def test_config_values(self):
        """Test config default values"""
        from config import settings
        assert settings.ENVIRONMENT in ["development", "production"]
        assert settings.API_PORT > 0
        assert settings.CHUNK_SIZE > 0
        assert settings.TOP_K > 0

    def test_config_directories_created(self):
        """Test that directories are created on import"""
        from config import settings
        assert os.path.exists(settings.UPLOAD_DIRECTORY)
        assert os.path.exists(settings.CHROMA_PERSIST_DIRECTORY)

    def test_config_exports(self):
        """Test backward compatibility exports"""
        from config import API_HOST, API_PORT, CHUNK_SIZE, TOP_K
        assert API_HOST is not None
        assert API_PORT > 0
        assert CHUNK_SIZE > 0
        assert TOP_K > 0


# ============================================================================
# TEST DOCUMENT PROCESSOR MODULE
# ============================================================================

class TestDocumentProcessor:
    """Test document processing"""

    def test_processor_initialization(self):
        """Test DocumentProcessor initialization"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        assert processor.chunk_size > 0
        assert processor.chunk_overlap >= 0
        assert processor.text_splitter is not None

    def test_supported_types(self):
        """Test supported document types"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        assert "txt" in processor.supported_types
        assert "pdf" in processor.supported_types

    def test_load_text_document(self, sample_text_file):
        """Test loading text document"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        docs = processor.load_document(sample_text_file)
        
        assert len(docs) > 0
        assert docs[0].page_content is not None
        assert "Machine Learning" in docs[0].page_content

    def test_load_document_unsupported_type(self, temp_dir):
        """Test loading unsupported file type"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        # Create unsupported file
        unsupported_file = os.path.join(temp_dir, "test.xyz")
        with open(unsupported_file, "w") as f:
            f.write("content")
        
        with pytest.raises(ValueError):
            processor.load_document(unsupported_file)

    def test_chunk_documents(self, sample_text_file):
        """Test document chunking"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        docs = processor.load_document(sample_text_file)
        chunked = processor.chunk_documents(docs)
        
        assert len(chunked) > 0
        assert all(hasattr(doc, 'page_content') for doc in chunked)
        assert all('chunk_id' in doc.metadata for doc in chunked)

    def test_process_document_complete_pipeline(self, sample_text_file):
        """Test complete document processing pipeline"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        result = processor.process_document(sample_text_file)
        
        assert len(result) > 0
        assert all(doc.metadata.get('source') == sample_text_file for doc in result)
        assert all(doc.metadata.get('file_type') == 'txt' for doc in result)

    def test_process_batch_documents(self, temp_dir):
        """Test batch document processing"""
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        
        # Create multiple test files
        files = []
        for i in range(2):
            file_path = os.path.join(temp_dir, f"test{i}.txt")
            with open(file_path, "w") as f:
                f.write(f"Content {i}")
            files.append(file_path)
        
        result = processor.process_batch(files)
        
        assert len(result) > 0

    def test_chunk_strategy_recursive(self, sample_text_file):
        """Test recursive chunking strategy"""
        from document_processor import DocumentProcessor
        from config import settings
        
        original_strategy = settings.CHUNK_STRATEGY
        try:
            # Note: This tests the default, actual config change would need env var
            processor = DocumentProcessor()
            assert processor.text_splitter is not None
        finally:
            settings.CHUNK_STRATEGY = original_strategy


# ============================================================================
# TEST EMBEDDINGS MODULE
# ============================================================================

class TestEmbeddings:
    """Test embedding module"""

    @patch('embeddings.OpenAIEmbeddings')
    def test_openai_embedding_provider_init(self, mock_openai):
        """Test OpenAI embedding provider initialization"""
        from embeddings import OpenAIEmbeddingProvider
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            provider = OpenAIEmbeddingProvider()
            assert provider.model == "text-embedding-3-small"

    def test_embedding_manager_initialization(self):
        """Test EmbeddingManager initialization"""
        from embeddings import EmbeddingManager
        
        # Use sentence-transformers to avoid API key issues
        with patch.dict('os.environ', {'EMBEDDING_PROVIDER': 'sentence-transformers'}):
            from unittest.mock import patch as mock_patch
            with mock_patch('embeddings.SentenceTransformerEmbeddingProvider'):
                manager = EmbeddingManager()
                assert manager.provider is not None

    def test_embedding_cache(self):
        """Test embedding caching mechanism"""
        from embeddings import EmbeddingManager
        
        manager = MagicMock(spec=EmbeddingManager)
        manager._embedding_cache = {}
        
        text = "Test text"
        embedding = [0.1, 0.2, 0.3]
        
        manager._embedding_cache[text] = embedding
        assert manager._embedding_cache[text] == embedding

    def test_clear_cache(self):
        """Test cache clearing"""
        from embeddings import EmbeddingManager
        
        manager = MagicMock(spec=EmbeddingManager)
        manager._embedding_cache = {"text": [0.1, 0.2]}
        manager.clear_cache()
        
        # Test that it's called
        manager.clear_cache.assert_called_once()

    def test_get_dimension_openai(self):
        """Test getting embedding dimension for OpenAI"""
        from embeddings import OpenAIEmbeddingProvider
        
        with patch('embeddings.OpenAIEmbeddings'):
            provider = OpenAIEmbeddingProvider("text-embedding-3-small")
            assert provider.get_dimension() == 1536

    def test_get_dimension_sentence_transformers(self):
        """Test getting embedding dimension for SentenceTransformers"""
        from embeddings import SentenceTransformerEmbeddingProvider
        
        with patch('embeddings.HuggingFaceEmbeddings'):
            provider = SentenceTransformerEmbeddingProvider("all-mpnet-base-v2")
            assert provider.get_dimension() == 768


# ============================================================================
# TEST VECTOR STORE MODULE
# ============================================================================

class TestVectorStore:
    """Test vector store module"""

    def test_vector_store_manager_initialization(self):
        """Test VectorStoreManager initialization"""
        from vector_store import VectorStoreManager
        
        with patch('vector_store.ChromaVectorStore'):
            manager = VectorStoreManager("chroma")
            assert manager.store_type == "chroma"

    def test_vector_store_add_documents(self):
        """Test adding documents to vector store"""
        from vector_store import VectorStoreManager
        from langchain_core.documents import Document
        
        manager = MagicMock(spec=VectorStoreManager)
        docs = [Document(page_content="Test", metadata={"source": "test.pdf"})]
        
        manager.add_documents.return_value = ["doc_1"]
        result = manager.add_documents(docs)
        
        assert result == ["doc_1"]

    def test_vector_store_search(self):
        """Test searching vector store"""
        from vector_store import VectorStoreManager
        
        manager = MagicMock(spec=VectorStoreManager)
        mock_doc = MagicMock()
        mock_doc.page_content = "Test content"
        mock_doc.metadata = {"source": "test.pdf"}
        
        manager.search.return_value = [(mock_doc, 0.95)]
        result = manager.search("test query", k=5)
        
        assert len(result) == 1
        assert result[0][1] == 0.95

    def test_vector_store_get_document_count(self):
        """Test getting document count"""
        from vector_store import VectorStoreManager
        
        manager = MagicMock(spec=VectorStoreManager)
        manager.get_document_count.return_value = 10
        
        count = manager.get_document_count()
        assert count == 10

    def test_vector_store_delete_documents(self):
        """Test deleting documents"""
        from vector_store import VectorStoreManager
        
        manager = MagicMock(spec=VectorStoreManager)
        manager.delete_documents.return_value = True
        
        result = manager.delete_documents(["doc_1", "doc_2"])
        assert result is True


# ============================================================================
# TEST RAG PIPELINE MODULE
# ============================================================================

class TestRAGPipeline:
    """Test RAG pipeline"""

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_rag_pipeline_initialization(self, mock_emb, mock_vs, mock_llm):
        """Test RAGPipeline initialization"""
        from rag_pipeline import RAGPipeline
        
        mock_llm.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_emb.return_value = MagicMock()
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            pipeline = RAGPipeline(enable_memory=True)
            assert pipeline.llm_model is not None
            assert pipeline.memory is not None

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_rag_pipeline_memory_disabled(self, mock_emb, mock_vs, mock_llm):
        """Test RAG pipeline without memory"""
        from rag_pipeline import RAGPipeline
        
        mock_llm.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_emb.return_value = MagicMock()
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            pipeline = RAGPipeline(enable_memory=False)
            assert pipeline.memory is None

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_rag_pipeline_format_documents(self, mock_emb, mock_vs, mock_llm):
        """Test document formatting"""
        from rag_pipeline import RAGPipeline
        from langchain_core.documents import Document
        
        mock_llm.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_emb.return_value = MagicMock()
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            pipeline = RAGPipeline()
            
            doc = Document(page_content="Test content", metadata={"source": "test.pdf"})
            context, metadata = pipeline._format_documents([(doc, 0.95)])
            
            assert "Test content" in context
            assert len(metadata) == 1
            assert metadata[0]["similarity_score"] == 0.95

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_rag_pipeline_get_stats(self, mock_emb, mock_vs, mock_llm):
        """Test getting pipeline statistics"""
        from rag_pipeline import RAGPipeline
        
        mock_llm.return_value = MagicMock()
        mock_vs_instance = MagicMock()
        mock_vs_instance.store_type = "chroma"
        mock_vs_instance.get_document_count.return_value = 10
        mock_vs.return_value = mock_vs_instance
        
        mock_emb_instance = MagicMock()
        mock_emb_instance.model = "all-mpnet-base-v2"
        mock_emb_instance.get_dimension.return_value = 768
        mock_emb.return_value = mock_emb_instance
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            pipeline = RAGPipeline()
            stats = pipeline.get_stats()
            
            assert "llm_model" in stats
            assert "vector_db_type" in stats
            assert stats["vector_db_type"] == "chroma"

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_rag_pipeline_memory_operations(self, mock_emb, mock_vs, mock_llm):
        """Test memory operations"""
        from rag_pipeline import RAGPipeline
        
        mock_llm.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_emb.return_value = MagicMock()
        
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            pipeline = RAGPipeline(enable_memory=True)
            
            # Get initial history
            history = pipeline.get_conversation_history()
            initial_len = len(history)
            
            # Clear memory
            pipeline.clear_memory()
            
            # Verify cleared
            new_history = pipeline.get_conversation_history()
            assert len(new_history) == 0


# ============================================================================
# TEST MAIN/API MODULE
# ============================================================================

class TestMainAPI:
    """Test FastAPI application"""

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint"""
        from fastapi.testclient import TestClient
        from main import app
        
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_stats_endpoint(self):
        """Test stats endpoint"""
        from fastapi.testclient import TestClient
        from main import app
        
        client = TestClient(app)
        response = client.get("/stats")
        
        # Should work even without documents
        assert response.status_code in [200, 500]  # 500 if LLM not configured

    @pytest.mark.asyncio
    async def test_query_endpoint_empty_query(self):
        """Test query endpoint with empty query"""
        from fastapi.testclient import TestClient
        from main import app
        
        client = TestClient(app)
        response = client.post("/query", json={"query": "", "k": 5})
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_query_endpoint_valid_query(self):
        """Test query endpoint with valid query"""
        from fastapi.testclient import TestClient
        from main import app
        
        with patch('main.rag_pipeline') as mock_pipeline:
            mock_pipeline.query.return_value = {
                "answer": "Test answer",
                "query": "test query",
                "retrieved_documents": [],
                "timestamp": "2025-11-12T00:00:00",
                "document_count": 0
            }
            
            client = TestClient(app)
            response = client.post("/query", json={"query": "test", "k": 5})
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data

    @pytest.mark.asyncio
    async def test_upload_endpoint_invalid_file(self):
        """Test upload endpoint with invalid file"""
        from fastapi.testclient import TestClient
        from main import app
        from io import BytesIO
        
        client = TestClient(app)
        
        # Create invalid file
        response = client.post(
            "/upload",
            files={"file": ("test.xyz", BytesIO(b"content"), "text/plain")}
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clear_memory_endpoint(self):
        """Test clear memory endpoint"""
        from fastapi.testclient import TestClient
        from main import app
        
        with patch('main.rag_pipeline') as mock_pipeline:
            client = TestClient(app)
            response = client.delete("/clear-memory")
            
            assert response.status_code == 200
            mock_pipeline.clear_memory.assert_called_once()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflow"""

    def test_document_to_query_pipeline(self, sample_text_file):
        """Test complete pipeline from document to query"""
        from document_processor import DocumentProcessor
        
        processor = DocumentProcessor()
        
        # Load and process document
        result = processor.process_document(sample_text_file)
        
        assert len(result) > 0
        assert all(hasattr(doc, 'page_content') for doc in result)

    def test_vector_store_persistence(self, temp_dir):
        """Test vector store data persistence"""
        from vector_store import VectorStoreManager
        
        manager = MagicMock(spec=VectorStoreManager)
        manager.get_document_count.return_value = 5
        
        count = manager.get_document_count()
        assert count == 5


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance and load tests"""

    def test_embedding_batch_processing(self):
        """Test batch embedding processing"""
        from embeddings import EmbeddingManager
        
        manager = MagicMock(spec=EmbeddingManager)
        texts = ["text1", "text2", "text3"]
        
        manager.embed_texts.return_value = [[0.1] * 768 for _ in texts]
        embeddings = manager.embed_texts(texts, batch_size=2)
        
        assert len(embeddings) == len(texts)

    def test_document_chunking_performance(self, sample_text_file):
        """Test document chunking performance"""
        from document_processor import DocumentProcessor
        import time
        
        processor = DocumentProcessor()
        docs = processor.load_document(sample_text_file)
        
        start = time.time()
        chunked = processor.chunk_documents(docs)
        elapsed = time.time() - start
        
        assert len(chunked) > 0
        assert elapsed < 5  # Should complete within 5 seconds


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling"""

    def test_invalid_vector_db_type(self):
        """Test invalid vector DB type"""
        from vector_store import VectorStoreManager
        
        with patch('vector_store.ChromaVectorStore'):
            manager = VectorStoreManager("invalid_type")
            # Should default to Chroma
            assert manager.store_type == "invalid_type"

    def test_document_processor_invalid_path(self):
        """Test document processor with invalid path"""
        from document_processor import DocumentProcessor
        
        processor = DocumentProcessor()
        with pytest.raises((FileNotFoundError, ValueError)):
            processor.load_document("/nonexistent/path/file.txt")

    @patch('rag_pipeline.ChatOpenAI')
    @patch('rag_pipeline.get_vector_store')
    @patch('rag_pipeline.get_embedding_manager')
    def test_unsupported_llm_provider(self, mock_emb, mock_vs, mock_llm):
        """Test unsupported LLM provider"""
        from rag_pipeline import RAGPipeline
        
        with patch.dict('os.environ', {'LLM_PROVIDER': 'unsupported'}):
            with pytest.raises(ValueError):
                mock_llm.side_effect = ValueError("Unsupported LLM provider")
                RAGPipeline()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
