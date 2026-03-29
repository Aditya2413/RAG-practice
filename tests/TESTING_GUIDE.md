# Unit Testing Guide for RAG Chatbot

## Overview

This guide explains how to run the comprehensive unit test suite for the RAG chatbot system.

## Test Structure

The test suite (`test_rag_pipeline.py`) is organized into the following test classes:

### 1. **TestConfig** - Configuration Module Tests
- Tests configuration loading
- Validates default values
- Verifies directory creation
- Tests backward compatibility exports

### 2. **TestDocumentProcessor** - Document Processing Tests
- Document loading (TXT, PDF, DOCX, etc.)
- Document chunking strategies
- Batch processing
- Error handling for unsupported types

### 3. **TestEmbeddings** - Embedding Module Tests
- Provider initialization (OpenAI, SentenceTransformers)
- Embedding manager functionality
- Caching mechanism
- Dimension validation

### 4. **TestVectorStore** - Vector Store Tests
- Vector store manager initialization
- Document addition/search/deletion
- Document counting
- Chroma and FAISS backends

### 5. **TestRAGPipeline** - RAG Pipeline Tests
- Pipeline initialization
- Document formatting
- Memory management
- Statistics retrieval
- Query rewriting

### 6. **TestMainAPI** - FastAPI Tests
- Health check endpoint
- Statistics endpoint
- Query endpoint (valid/invalid)
- Upload endpoint
- Clear memory endpoint

### 7. **TestIntegration** - End-to-End Tests
- Complete document-to-query pipeline
- Vector store persistence
- Multi-step workflows

### 8. **TestPerformance** - Performance Tests
- Batch embedding processing
- Document chunking performance
- Scalability checks

### 9. **TestErrorHandling** - Error Handling Tests
- Invalid configurations
- File not found errors
- Unsupported providers
- Graceful degradation

## Installation

### 1. Install Testing Dependencies

```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### 2. Update requirements.txt

Add these testing dependencies:
```txt
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
```

Install all dependencies:
```bash
pip install -r requirements.txt
```

## Running Tests

### Run All Tests

```bash
pytest test_rag_pipeline.py -v
```

### Run Specific Test Class

```bash
# Test configuration only
pytest test_rag_pipeline.py::TestConfig -v

# Test document processor only
pytest test_rag_pipeline.py::TestDocumentProcessor -v

# Test embeddings only
pytest test_rag_pipeline.py::TestEmbeddings -v
```

### Run Specific Test

```bash
pytest test_rag_pipeline.py::TestDocumentProcessor::test_load_text_document -v
```

### Run with Coverage

```bash
pytest test_rag_pipeline.py --cov=. --cov-report=html --cov-report=term
```

This generates:
- Terminal report with coverage percentage
- HTML report in `htmlcov/index.html`

### Run with Output

```bash
# Show print statements
pytest test_rag_pipeline.py -v -s

# Show more detailed output
pytest test_rag_pipeline.py -v --tb=long
```

### Run Performance Tests Only

```bash
pytest test_rag_pipeline.py::TestPerformance -v
```

### Run Integration Tests Only

```bash
pytest test_rag_pipeline.py::TestIntegration -v
```

## Test Fixtures

The test suite includes reusable fixtures:

### `temp_dir`
Creates a temporary directory for test files.

```python
def test_something(temp_dir):
    file_path = os.path.join(temp_dir, "test.txt")
    # Use file_path
```

### `sample_text_file`
Creates a sample text file with machine learning content.

```python
def test_document_loading(sample_text_file):
    processor = DocumentProcessor()
    docs = processor.load_document(sample_text_file)
```

### `mock_embedding_manager`
Provides a mocked embedding manager.

```python
def test_embeddings(mock_embedding_manager):
    # Use mock_embedding_manager
```

### `mock_vector_store`
Provides a mocked vector store.

```python
def test_vector_store(mock_vector_store):
    # Use mock_vector_store
```

## Mock Objects

Tests use mocking extensively to avoid external dependencies:

```python
from unittest.mock import Mock, MagicMock, patch

# Mock external API calls
@patch('main.rag_pipeline')
def test_query_endpoint(mock_pipeline):
    mock_pipeline.query.return_value = {...}
    # Test without real LLM
```

## Test Coverage Goals

Target coverage by module:

| Module | Target |
|--------|--------|
| config.py | 90%+ |
| document_processor.py | 85%+ |
| embeddings.py | 80%+ |
| vector_store.py | 85%+ |
| rag_pipeline.py | 80%+ |
| main.py | 75%+ |
| **Overall** | **80%+** |

### Check Coverage

```bash
# Generate coverage report
pytest --cov=config --cov=embeddings --cov=vector_store \
       --cov=document_processor --cov=rag_pipeline --cov=main \
       --cov-report=term-missing test_rag_pipeline.py
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: pytest test_rag_pipeline.py --cov=. --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Common Test Patterns

### Testing with Mocks

```python
@patch('module.external_call')
def test_something(mock_call):
    mock_call.return_value = "mocked result"
    # Your test
    mock_call.assert_called_once()
```

### Testing Async Functions

```python
@pytest.mark.asyncio
async def test_async_endpoint():
    client = TestClient(app)
    response = await client.get("/endpoint")
    assert response.status_code == 200
```

### Testing Fixtures

```python
def test_with_fixture(sample_text_file):
    # sample_text_file is automatically created
    assert os.path.exists(sample_text_file)
```

### Testing Exceptions

```python
def test_invalid_file():
    processor = DocumentProcessor()
    with pytest.raises(ValueError):
        processor.load_document("invalid.xyz")
```

## Debugging Tests

### Print Statements

```bash
pytest test_rag_pipeline.py -v -s  # Shows print() output
```

### Detailed Tracebacks

```bash
pytest test_rag_pipeline.py -v --tb=long
```

### Stop on First Failure

```bash
pytest test_rag_pipeline.py -x
```

### Run Last Failed Tests

```bash
pytest test_rag_pipeline.py --lf
```

### Run Failed Tests and New Tests

```bash
pytest test_rag_pipeline.py --ff
```

## Best Practices

1. **Use Fixtures**: Reuse setup code with fixtures
2. **Mock External Calls**: Don't depend on external APIs
3. **Test Edge Cases**: Empty inputs, invalid types, large batches
4. **Descriptive Names**: `test_load_document_with_valid_file` > `test_load`
5. **One Assertion**: Keep tests focused on one thing
6. **Setup/Teardown**: Use fixtures for setup and cleanup
7. **Isolate Tests**: Tests shouldn't depend on each other

## Troubleshooting

### ImportError: No module named 'config'

Make sure you're in the project root directory:
```bash
cd /path/to/rag-chatbot
pytest test_rag_pipeline.py
```

### API Key Issues

Tests mock API calls, but if you get API errors:

```bash
export OPENAI_API_KEY="test-key"
pytest test_rag_pipeline.py
```

### Module Not Found

Install all dependencies:
```bash
pip install -r requirements.txt
```

### Async Test Issues

Make sure pytest-asyncio is installed:
```bash
pip install pytest-asyncio
```

## Example Test Run

```bash
$ pytest test_rag_pipeline.py -v --cov=. 

collected 45 items

test_rag_pipeline.py::TestConfig::test_config_imports PASSED
test_rag_pipeline.py::TestConfig::test_config_values PASSED
test_rag_pipeline.py::TestDocumentProcessor::test_processor_initialization PASSED
test_rag_pipeline.py::TestDocumentProcessor::test_load_text_document PASSED
...
============= 45 passed in 12.34s ==============

coverage report:
Name                          Stmts   Miss  Cover
-------------------------------------------------
config.py                        42      4   90%
document_processor.py             65      8   88%
embeddings.py                     58      9   84%
vector_store.py                   87     12   86%
rag_pipeline.py                   72     10   86%
main.py                           95     15   84%
-------------------------------------------------
TOTAL                            419     58   86%
```

## Next Steps

1. Run all tests: `pytest test_rag_pipeline.py -v`
2. Check coverage: `pytest --cov=. test_rag_pipeline.py`
3. Add more tests for edge cases
4. Set up CI/CD pipeline
5. Aim for 80%+ coverage
6. Monitor test execution time

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Pytest-AsyncIO](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)

---

**Last Updated**: November 12, 2025
**Test Count**: 45+ unit and integration tests
**Target Coverage**: 80%+
