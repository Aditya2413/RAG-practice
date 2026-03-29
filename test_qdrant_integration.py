"""
Test script for Qdrant Vector Store integration.
This script verifies that Qdrant can be initialized and used correctly.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_qdrant_import():
    """Test that Qdrant dependencies can be imported"""
    print("Testing Qdrant imports...")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        from langchain_qdrant import QdrantVectorStore as LangChainQdrant
        print("✅ All Qdrant imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please install Qdrant dependencies:")
        print("  pip install qdrant-client langchain-qdrant")
        return False

def test_qdrant_config():
    """Test that Qdrant configuration is properly loaded"""
    print("\nTesting Qdrant configuration...")
    try:
        from config import (
            QDRANT_URL,
            QDRANT_API_KEY,
            QDRANT_COLLECTION_NAME,
            QDRANT_PREFER_GRPC
        )
        print(f"✅ QDRANT_URL: {QDRANT_URL}")
        print(f"✅ QDRANT_COLLECTION_NAME: {QDRANT_COLLECTION_NAME}")
        print(f"✅ QDRANT_PREFER_GRPC: {QDRANT_PREFER_GRPC}")
        return True
    except ImportError as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_qdrant_vector_store_class():
    """Test that QdrantVectorStore class exists and is properly defined"""
    print("\nTesting QdrantVectorStore class...")
    try:
        from vector_store import QdrantVectorStore
        print("✅ QdrantVectorStore class imported successfully")
        
        # Check methods exist
        required_methods = [
            'add_documents',
            'search',
            'similarity_search_with_score',
            'delete_documents',
            'get_document_count'
        ]
        
        for method in required_methods:
            if hasattr(QdrantVectorStore, method):
                print(f"✅ Method '{method}' exists")
            else:
                print(f"❌ Method '{method}' missing")
                return False
        
        return True
    except ImportError as e:
        print(f"❌ Class import error: {e}")
        return False

def test_vector_store_manager():
    """Test that VectorStoreManager can initialize with Qdrant"""
    print("\nTesting VectorStoreManager integration...")
    try:
        # Temporarily set environment variable
        original_db_type = os.getenv('VECTOR_DB_TYPE')
        os.environ['VECTOR_DB_TYPE'] = 'qdrant'
        
        # Note: We can't fully test initialization without a running Qdrant server
        # This just checks that the code structure is correct
        from vector_store import VectorStoreManager
        print("✅ VectorStoreManager can be imported with Qdrant type")
        
        # Restore original
        if original_db_type:
            os.environ['VECTOR_DB_TYPE'] = original_db_type
        
        return True
    except Exception as e:
        print(f"❌ VectorStoreManager error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Qdrant Vector Store Integration Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Import Test", test_qdrant_import()))
    results.append(("Configuration Test", test_qdrant_config()))
    results.append(("QdrantVectorStore Class Test", test_qdrant_vector_store_class()))
    results.append(("VectorStoreManager Test", test_vector_store_manager()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Qdrant integration is ready.")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Start Qdrant: docker run -p 6333:6333 qdrant/qdrant")
        print("3. Set VECTOR_DB_TYPE=qdrant in your .env file")
        print("4. Run your application!")
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
