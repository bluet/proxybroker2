# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProxyBroker2 is an async proxy finder, checker, and server. It discovers public proxies from 50+ sources, validates them against judge servers, and can operate as a rotating proxy server.

**Repository**: `bluet/proxybroker2` (GitHub)  
**Python**: 3.10-3.13  
**Key Dependencies**: aiohttp, aiodns, asyncio

## Common Development Commands

### Setup
```bash
# Poetry (recommended)
poetry install
poetry shell

# Standard pip
pip install -e .
```

### Testing
```bash
# Run all tests
pytest

# Single test with output
pytest -xvs tests/test_api.py::TestBrokerAPI::test_broker_creation_without_queue

# With coverage
pytest --cov=proxybroker --cov-report=term-missing
```

### Code Quality
```bash
# Format and fix issues
ruff check . --fix && ruff format .
```

### CLI Usage
```bash
# Find proxies
python -m proxybroker find --types HTTP HTTPS --limit 10

# Run as proxy server
python -m proxybroker serve --host 127.0.0.1 --port 8888 --types HTTP HTTPS

# Grab without validation
python -m proxybroker grab --countries US --limit 10 --outfile proxies.txt
```

## Architecture

### Core Components

**Broker** (`api.py`)
- Orchestrates the entire pipeline
- Methods: `find()`, `grab()`, `serve()`
- Manages provider tasks and checker coordination

**ProxyPool** (`api.py`)
- Min-heap priority queue based on `proxy.avg_resp_time`
- Two-stage pool: `_newcomers` → `_pool` after validation
- Configurable retry limits and timeouts

**Providers** (`providers.py`)
- 50+ proxy sources inheriting from `Provider` base class
- Concurrent fetching limited to `MAX_CONCURRENT_PROVIDERS = 3`
- Each implements `get_proxies()` to extract proxy data

**Checker** (`checker.py`)
- Validates proxies against judge servers (httpbin.org, azenv.net)
- Detects anonymity levels by checking IP leakage
- Supports multiple protocols with protocol-specific negotiators

**Server** (`server.py`)
- Proxy server mode using validated proxies
- Automatic rotation and failure handling
- Supports HTTP(S) and SOCKS protocols

### Key Patterns

**Async Safety**
```python
try:
    self._loop = loop or asyncio.get_running_loop()
except RuntimeError:
    self._loop = loop
```

**Heap Invariant**
```python
# Always use heapq operations
heapq.heappush(self._pool, (proxy.avg_resp_time, proxy))
```

**Empty Provider List Handling**
```python
# Respect explicit empty list vs None
PROVIDERS if providers is None else providers
```

## Important Implementation Details

### Protocol Priority
Deterministic order: SOCKS5 → SOCKS4 → CONNECT:80 → CONNECT:25 → HTTPS → HTTP

### Signal Handler Cleanup
`Broker.stop()` properly removes signal handlers to prevent memory leaks

### Version Management
Single source of truth in `pyproject.toml`, auto-detected in development mode

### Testing Philosophy
- Test behavior, not implementation
- Focus on user-visible outcomes
- Don't test internal method calls or private attributes
- Don't write complex mock-heavy tests
- Don't overfit tests to current implementation
- Simple tests that serve as documentation

## Known Quirks

- Uses both Poetry and setuptools for compatibility
- GeoIP database bundled in `proxybroker/data/`
- Entry points: `__main__.py` (module), `py2exe_entrypoint.py` (executable)
- ProxyPool.remove() is O(N log N) - acceptable for correctness

## Recent Major Improvements (v2.0.0+)

### Production-Ready Status
- **Zero critical bugs** - Fixed all signal handler leaks, deadlocks, heap corruption
- **Modern async patterns** - Updated from deprecated asyncio patterns
- **Python 3.10-3.13 support** - Full compatibility with latest Python versions

### Testing & Quality
- **Behavior-focused tests** - Contract-based testing protects APIs during refactoring
- **Eliminated brittle tests** - Removed implementation-detail testing
- **Comprehensive coverage** - Tests protect user-visible functionality
- **CI/CD matrix testing** - Verified across Python 3.10-3.13

### Documentation
- **Updated Sphinx docs** - Correct GitHub references and modern examples
- **ReadTheDocs ready** - Modern v2 configuration
- **Modern changelog** - Converted to CHANGELOG.md following Keep a Changelog standard
- **Comprehensive CLAUDE.md** - Architecture insights for AI assistance
- **Conventional commits** - Template for structured commit messages