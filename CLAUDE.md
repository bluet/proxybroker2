# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProxyBroker2 is an async proxy finder, checker, and server. It discovers public proxies from 50+ sources, validates them against judge servers, and can operate as a rotating proxy server.

**Repository**: `bluet/proxybroker2` (GitHub)
**Python**: 3.10-3.13
**Key Dependencies**: aiohttp 3.12.0+, aiodns 3.4.0+, attrs 25.3.0+, asyncio

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

### Documentation
```bash
# Build documentation locally
cd docs && make html

# Clean build
cd docs && make clean && make html

# Docstring coverage check
python -c "import ast; import os; ..." # See script in README for details
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

### Warning Management
- **Function over form** - Keep warnings that preserve functionality (e.g., event_loop fixture for working tests)
- **Fix fixable warnings** - Address RST syntax errors, deprecated configurations, resource leaks
- **External dependency warnings** - Accept pycares/aiodns DNS resolver cleanup warnings (unfixable)
- **Documentation warnings** - Reduce from 42 to 34 using proper architecture, maintain full content
- **Avoid anti-patterns** - No broad warning suppressions or `:noindex:` misuse

## Documentation Guidelines

### Auto-Generated vs Hand-Written Strategy
- **Auto-generate**: API reference, function signatures, class hierarchies
- **Hand-write**: Getting started, tutorials, architecture explanations, migration guides
- **Leverage existing**: 44/224 (19.6%) functions have high-quality docstrings

### Sphinx Configuration (docs/source/conf.py)
```python
extensions = [
    "sphinx.ext.autodoc",      # Auto-generate from docstrings
    "sphinx.ext.autosummary",  # Create overview tables
    "sphinx.ext.napoleon",     # Google/NumPy style docstrings
    "myst_parser",            # Modern Markdown support
]
```

### MyST-Parser Features Enabled
- `colon_fence` - ::: directive fences
- `deflist` - Definition lists
- `tasklist` - GitHub-style checkboxes
- `linkify` - Auto-link URLs
- `strikethrough` - ~~text~~ support

### Documentation Structure
```
docs/source/
├── api.rst          # Curated API guide
├── api_auto.rst     # Auto-generated complete reference
├── examples.rst     # Hand-written tutorials
├── changelog.md     # Auto-included from root CHANGELOG.md
└── index.rst        # Main documentation page
```

## Known Quirks

- Uses both Poetry and setuptools for compatibility
- GeoIP database bundled in `proxybroker/data/`
- Entry points: `__main__.py` (module), `py2exe_entrypoint.py` (executable)
- ProxyPool.remove() is O(N log N) - acceptable for correctness

## Recent Major Improvements (v2.0.0b1 - Released May 26, 2025)

### Production-Ready Status
- **Zero critical bugs** - Fixed all signal handler leaks, deadlocks, heap corruption
- **Modern async patterns** - Updated from deprecated asyncio patterns
- **Python 3.10-3.13 support** - Full compatibility with latest Python versions
- **Modern dependencies** - Updated to latest stable versions (May 2025)

### Testing & Quality
- **Behavior-focused tests** - Contract-based testing protects APIs during refactoring
- **Eliminated brittle tests** - Removed implementation-detail testing
- **Comprehensive coverage** - Tests protect user-visible functionality
- **CI/CD matrix testing** - Verified across Python 3.10-3.13
- **Modern toolchain** - ruff for linting/formatting, pytest 8.3.5+

### Dependency Updates (May 2025)
- **aiohttp** 3.10.11 → 3.12.0 (asyncio deprecation fixes)
- **aiodns** 3.1.1 → 3.4.0 (DNS resolution improvements)
- **attrs** 22.1.0 → 25.3.0 (Python 3.10+ optimizations)
- **pytest** 7.1.2 → 8.3.5 (modern testing framework)
- **Removed redundant tools** - flake8/isort replaced by ruff
- **Clean warning profile** - Fixed asyncio SSL deprecations, minimal remaining warnings

### Documentation Strategy
- **80% Auto-generated** - API reference from docstrings (19.6% coverage, high quality)
- **20% Hand-written** - Guides, tutorials, architecture explanations
- **Sphinx 8.1.3 + MyST-Parser 4.0.1** - Latest stable versions (Feb 2025)
- **Enhanced autodoc** - Napoleon, autosummary, inheritance display
- **Modern changelog** - CHANGELOG.md following Keep a Changelog standard
- **ReadTheDocs hosting** - Multiple formats (HTML, PDF, htmlzip)
- **Conventional commits** - Structured format for release automation
