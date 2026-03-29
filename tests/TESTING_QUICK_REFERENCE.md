# Testing Quick Reference Card

## Installation (2 minutes)

```bash
# Install testing dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock

# OR use development requirements
pip install -r requirements-dev.txt
```

## Running Tests (Common Commands)

```bash
# Run all tests
pytest test_rag_pipeline.py -v

# Run specific test class
pytest test_rag_pipeline.py::TestConfig -v

# Run specific test
pytest test_rag_pipeline.py::TestConfig::test_config_imports -v

# Stop on first failure
pytest test_rag_pipeline.py -x

# Show print statements
pytest test_rag_pipeline.py -v -s

# Generate coverage report
pytest test_rag_pipeline.py --cov=. --cov-report=html --cov-report=term

# Run in parallel (faster)
pytest test_rag_pipeline.py -n auto

# Run with timeout
pytest test_rag_pipeline.py --timeout=300
```

## Coverage Reports

```bash
# Generate HTML coverage report
pytest test_rag_pipeline.py --cov=. --cov-report=html

# View report (3 options)
open htmlcov/index.html          # macOS
start htmlcov/index.html         # Windows
xdg-open htmlcov/index.html      # Linux

# Show coverage with missing lines
pytest test_rag_pipeline.py --cov=. --cov-report=term-missing
```

## Test Classes

| Class | Tests | Purpose |
|-------|-------|---------|
| TestConfig | 4 | Configuration validation |
| TestDocumentProcessor | 7 | Document loading/chunking |
| TestEmbeddings | 6 | Embedding providers |
| TestVectorStore | 5 | Vector database operations |
| TestRAGPipeline | 6 | RAG pipeline logic |
| TestMainAPI | 6 | FastAPI endpoints |
| TestIntegration | 2 | End-to-end workflows |
| TestPerformance | 2 | Performance checks |
| TestErrorHandling | 3 | Error scenarios |

## Files

| File | Purpose |
|------|---------|
| test_rag_pipeline.py | Main test suite (45+ tests) |
| pytest.ini | Pytest configuration |
| TESTING_GUIDE.md | Detailed documentation |
| requirements-dev.txt | Testing dependencies |
| TEST_IMPLEMENTATION_SUMMARY.md | Overview |
| TESTING_COMPREHENSIVE_GUIDE.pdf | Complete guide |

## Fixtures Available

```python
temp_dir                # Temporary directory
sample_text_file        # Pre-created test document
mock_embedding_manager  # Mocked embedding provider
mock_vector_store       # Mocked vector database
```

## Test Markers

```bash
# Mark tests by category
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.performance   # Performance tests
@pytest.mark.api          # API tests
@pytest.mark.asyncio      # Async tests
@pytest.mark.slow         # Slow tests

# Run specific marker
pytest test_rag_pipeline.py -m unit -v
```

## Expected Results

```
45+ tests passing
Coverage: 80%+
Execution time: ~15 seconds
All modules: 85%+ coverage
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ImportError | `cd` to project root |
| Module not found | `pip install -r requirements.txt` |
| API key error | Tests mock API calls (no key needed) |
| Timeout | Use `--timeout=600` |
| Slow tests | Use `pytest -n auto` for parallelization |

## CI/CD Command

```bash
pytest test_rag_pipeline.py --cov=. --cov-report=xml --cov-report=term
```

## Coverage Targets

- Overall: 80%+
- config.py: 90%+
- document_processor.py: 85%+
- embeddings.py: 80%+
- vector_store.py: 85%+
- rag_pipeline.py: 80%+
- main.py: 75%+

## Key Commands

| Command | Time | Purpose |
|---------|------|---------|
| `pytest test_rag_pipeline.py -v` | 15s | Quick test |
| `pytest --cov=.` | 20s | Full coverage |
| `pytest -x` | 5s | Quick validation |
| `pytest -n auto` | 10s | Parallel run |

## Tips

✅ Always run tests before committing
✅ Monitor coverage trends
✅ Use fixtures for reusable setup
✅ Mock external dependencies
✅ Run coverage reports weekly
✅ Aim for 80%+ coverage
✅ Write tests for new features

---

**Version**: 1.0
**Last Updated**: November 12, 2025
**Status**: Ready to Use
