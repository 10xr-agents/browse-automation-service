# Part 2 (Knowledge Retrieval) Tests

This directory contains comprehensive tests for Part 2 (Knowledge Retrieval & Storage Flow) implementation.

## Test Structure

- **`conftest.py`**: Pytest fixtures for Part 2 components
- **`test_exploration_engine.py`**: Tests for Exploration Engine (Steps 2.1-2.5)
- **`test_e2e_exploration.py`**: End-to-end tests for complete exploration flow
- **`test_form_handling.py`**: Tests for Form Handling (Step 2.6)
- **`test_semantic_analyzer.py`**: Tests for Semantic Analyzer (Steps 2.7-2.10)
- **`test_e2e_semantic.py`**: End-to-end tests for semantic analysis workflow
- **`test_flow_mapper.py`**: Tests for Functional Flow Mapper (Steps 2.11-2.12)
- **`test_storage.py`**: Tests for Knowledge Storage (Steps 2.13-2.15)
- **`test_e2e_flow_storage.py`**: End-to-end tests for flow mapper and storage workflow
- **`integration_test_exploration.py`**: Integration test script for actual exploration testing
- **`integration_test_semantic.py`**: Integration test script for semantic analysis testing

## Running Tests

### Run All Part 2 Tests

```bash
uv run pytest tests/ci/knowledge/ -v
```

### Run Specific Test Files

```bash
# Exploration Engine tests
uv run pytest tests/ci/knowledge/test_exploration_engine.py -v

# E2E tests
uv run pytest tests/ci/knowledge/test_e2e_exploration.py -v
```

### Run Integration Test Script

```bash
# Run the integration test script
python tests/ci/knowledge/integration_test_exploration.py

# Or with uv
uv run python tests/ci/knowledge/integration_test_exploration.py
```

### Run Specific Tests

```bash
# Run specific test
uv run pytest tests/ci/knowledge/test_exploration_engine.py::TestLinkDiscovery::test_discover_links_from_page -v

# Run all tests matching a pattern
uv run pytest tests/ci/knowledge/ -k "discover" -v
```

## Test Coverage

### Steps 2.1-2.6: Exploration Engine
- ✅ Basic Link Discovery (Step 2.1)
  - Discover links from HTML
  - Extract link attributes
  - Resolve relative URLs
  - Filter invalid URLs

- ✅ Link Tracking (Step 2.2)
  - Track visited URLs
  - Check if URL is visited
  - Filter unvisited links

- ✅ Depth Management (Step 2.3)
  - Track depth per URL
  - Filter links by depth limit
  - Respect max_depth configuration

- ✅ BFS Strategy (Step 2.4)
  - Level-by-level exploration
  - Queue-based algorithm
  - Verify exploration order

- ✅ DFS Strategy (Step 2.5)
  - Deep paths first exploration
  - Stack-based algorithm
  - Verify exploration order

- ✅ Form Handling (Step 2.6)
  - Form detection
  - Form field extraction
  - Read-only form detection
  - GET form detection

### Steps 2.7-2.10: Semantic Analyzer
- ✅ Content Extraction (Step 2.7)
  - Extract headings hierarchy
  - Extract paragraphs
  - Extract metadata (title, description)
  - Remove navigation/footer/ads (via markdownify)

- ✅ Entity Recognition (Step 2.8)
  - Basic entity recognition (EMAIL, URL, PHONE, DATE, MONEY)
  - Entity structure validation
  - Extensible to spaCy

- ✅ Topic Modeling (Step 2.9)
  - Keyword extraction
  - Main topics from headings
  - Content categorization

- ✅ Embeddings (Step 2.10)
  - Embedding generation
  - Consistent dimensions
  - Extensible to sentence-transformers/OpenAI

### Steps 2.11-2.15: Flow Mapper and Storage
- ✅ Navigation Tracking (Step 2.11)
  - Page transition tracking
  - Referrer tracking
  - Visit count tracking
  - Entry point identification

- ✅ Click Path Mapping (Step 2.12)
  - Click sequence tracking
  - Path analysis
  - Popular path identification
  - Flow statistics

- ✅ ArangoDB Setup (Step 2.13)
  - ArangoDB connection (with fallback)
  - Collection initialization
  - In-memory storage fallback

- ✅ Page Storage (Step 2.14)
  - Store page data
  - Retrieve page data
  - Page updates (upsert)

- ✅ Link Storage (Step 2.15)
  - Store link relationships
  - Get links from/to pages
  - Link metadata support

### E2E Tests
- ✅ Complete exploration flow with BFS
- ✅ Complete exploration flow with DFS
- ✅ Link discovery and tracking integration
- ✅ Depth-limited exploration

### Integration Tests
- ✅ Actual browser automation calls
- ✅ Complete exploration workflow
- ✅ Complete semantic analysis workflow
- ✅ All features integrated

## Requirements

### Required
- Python 3.11+
- pytest
- pytest-asyncio
- pytest-httpserver
- Browser automation dependencies (browser-use)

### Optional
- Network access (for testing with real URLs)

## Notes

- Tests use pytest-httpserver for local test pages to avoid external dependencies
- Browser tests run in headless mode
- Integration test script performs actual calls and requires browser automation
- Some tests may require network access (for navigating to test URLs)
