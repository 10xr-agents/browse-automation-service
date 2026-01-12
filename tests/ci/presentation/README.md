# Phase 1 (Presentation Flow) Tests

This directory contains comprehensive tests for Phase 1 (Presentation/Agent Flow) implementation.

## Test Structure

- **`conftest.py`**: Pytest fixtures for Phase 1 components
- **`test_flow_manager.py`**: Tests for Presentation Flow Manager (Steps 1.1-1.4)
- **`test_action_registry.py`**: Tests for Action Registry (Steps 1.5-1.12)
- **`test_action_queue.py`**: Tests for Action Queue Management (Steps 1.13-1.15)
- **`test_event_broadcasting.py`**: Tests for Event Broadcasting (Step 1.16)
- **`test_session_persistence.py`**: Tests for Session Persistence (Step 1.17)
- **`test_e2e_phase1.py`**: End-to-end tests for complete Phase 1 flow
- **`integration_test_phase1.py`**: Integration test script for actual flow testing

## Running Tests

### Run All Phase 1 Tests

```bash
uv run pytest tests/ci/presentation/ -v
```

### Run Specific Test Files

```bash
# Flow Manager tests
uv run pytest tests/ci/presentation/test_flow_manager.py -v

# Action Registry tests
uv run pytest tests/ci/presentation/test_action_registry.py -v

# Action Queue tests
uv run pytest tests/ci/presentation/test_action_queue.py -v

# Event Broadcasting tests
uv run pytest tests/ci/presentation/test_event_broadcasting.py -v

# Session Persistence tests
uv run pytest tests/ci/presentation/test_session_persistence.py -v

# E2E tests
uv run pytest tests/ci/presentation/test_e2e_phase1.py -v
```

### Run Integration Test Script

```bash
# Run the integration test script
python tests/ci/presentation/integration_test_phase1.py

# Or with uv
uv run python tests/ci/presentation/integration_test_phase1.py
```

### Run Specific Tests

```bash
# Run specific test
uv run pytest tests/ci/presentation/test_flow_manager.py::TestPresentationFlowManagerBasic::test_start_session -v

# Run all tests matching a pattern
uv run pytest tests/ci/presentation/ -k "test_execute" -v
```

## Test Coverage

### Steps 1.1-1.4: Presentation Flow Manager
- ✅ Basic structure (session lifecycle)
- ✅ Timeout management
- ✅ Queue integration (in-memory mode)
- ✅ Browser Session Manager integration

### Steps 1.5-1.12: Action Registry
- ✅ Basic actions (navigate, click, type, scroll, wait)
- ✅ Navigation actions (go_back, refresh)
- ✅ Extended actions (right_click, keyboard_shortcut, zoom, screenshot, presentation_mode, etc.)

### Steps 1.13-1.15: Action Queue Management
- ✅ BullMQ integration (with in-memory fallback)
- ✅ Rate limiting
- ✅ Retry logic with exponential backoff

### Step 1.16: Event Broadcasting
- ✅ Redis Pub/Sub integration (with WebSocket fallback)
- ✅ All new event types (presentation_started, action_queued, etc.)

### Step 1.17: Session Persistence
- ✅ Save/load session from Redis
- ✅ Session serialization/deserialization
- ✅ TTL handling

### E2E Tests
- ✅ Complete presentation flow
- ✅ Action queue integration
- ✅ Event broadcasting integration
- ✅ Session persistence integration
- ✅ All components integrated

## Requirements

### Required
- Python 3.11+
- pytest
- pytest-asyncio
- pytest-httpserver
- Browser automation dependencies (browser-use)

### Optional (for full testing)
- Redis (for Redis Pub/Sub and session persistence tests)
- LiveKit server (for LiveKit streaming tests)

## Notes

- Tests use in-memory queues and mocks where possible to avoid external dependencies
- Browser tests run in headless mode
- Integration test script performs actual calls and requires browser automation
- Some tests may require network access (for navigating to test URLs)
