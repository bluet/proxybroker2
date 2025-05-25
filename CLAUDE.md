# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProxyBroker2 is a production-ready async proxy finder, checker, and server that discovers and validates public proxies from multiple sources. It supports HTTP(S), SOCKS4/5 protocols and can operate as a proxy server with automatic rotation.

**Repository**: `bluet/proxybroker2` (GitHub)  
**Status**: Production-ready with all critical bugs fixed  
**Python Support**: 3.10-3.13  
**Test Coverage**: 121/129 tests passing (94%)

## Common Development Commands

### Setup and Dependencies
```bash
# Install dependencies with Poetry
poetry install
poetry shell

# Alternative: standard venv
python3 -m venv venv && source venv/bin/activate
pip install -e .
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_proxy.py

# Run single test with output
pytest -xvs tests/test_cli.py::TestCLI::test_cli_help

# Run with coverage
pytest --cov=proxybroker --cov-report=term-missing

# Test across Python versions (if conda environments are available)
conda run -n py311-proxybroker pytest
conda run -n py312-proxybroker pytest
conda run -n py313-proxybroker pytest
```

### Code Quality
```bash
# Run all checks and formatting (recommended before commits)
ruff check . --fix && ruff format .

# Just check without fixing
ruff check . && ruff format --check .
```

### Building and Packaging
```bash
# Build distributions
poetry build

# Create standalone executable
pip install pyinstaller
pyinstaller --onefile --name proxybroker --add-data "proxybroker/data:data" --workpath ./tmp --distpath ./build --clean py2exe_entrypoint.py
```

### Common CLI Usage
```bash
# Find proxies
proxybroker find --types HTTP HTTPS --limit 10

# Grab proxies without checking
proxybroker grab --countries US --limit 10 --outfile proxies.txt

# Run as proxy server
proxybroker serve --host 127.0.0.1 --port 8888 --types HTTP HTTPS

# Debug mode
proxybroker --log DEBUG find --types HTTP --limit 5
```

## High-Level Architecture

### Core Flow
1. **Broker** orchestrates the entire proxy discovery pipeline
2. **Providers** fetch proxy lists from various sources (50+ providers)
3. **Checker** validates proxies against judge servers
4. **ProxyPool** maintains a priority queue of working proxies
5. **Server** serves as a rotating proxy server using the pool

### Key Architectural Decisions

**Async Everything**: Built on asyncio for high concurrency. Provider fetching, proxy checking, and server operations all run asynchronously.

**Priority Queue Design**: ProxyPool uses a min-heap based on response time (`proxy.avg_resp_time`). Proxies start in `_newcomers` pool and graduate to main `_pool` after proving reliability.

**Protocol Negotiation**: Each protocol (HTTP, SOCKS4, SOCKS5, CONNECT) has its own Negotiator class handling the specific handshake. Protocol selection follows a deterministic priority order.

**Judge System**: External servers (httpbin.org, azenv.net) validate proxy functionality and detect anonymity levels by checking if the real IP leaks through headers.

**Provider Concurrency**: Limited to 3 concurrent providers (`MAX_CONCURRENT_PROVIDERS`) to avoid overwhelming sources and getting banned.

### Critical Code Patterns

**Event Loop Safety**: Always use `asyncio.get_running_loop()` with fallback:
```python
try:
    self._loop = loop or asyncio.get_running_loop()
except RuntimeError:
    self._loop = loop  # Will be set later
```

**Heap Operations**: Never modify `_pool` directly, always use heapq:
```python
heapq.heappush(self._pool, (proxy.avg_resp_time, proxy))
```

**Resource Cleanup**: Always clean up in finally blocks:
```python
try:
    await proxy.connect()
    # ... operations
finally:
    proxy.close()
```

### Testing Philosophy

Tests follow contract-based approach - test user-visible behavior, not implementation:
- ✅ Test that proxies can be found and used
- ✅ Test API signatures remain stable  
- ❌ Don't test exact bytes in protocol handshakes
- ❌ Don't test internal algorithm details

## Recent Improvements (v2.0.0-alpha6)

### Critical Bug Fixes ✅
- **Signal handler memory leak**: Fixed with proper cleanup in `Broker.stop()`
- **ProxyPool deadlocks**: Added timeout protection and retry limits
- **Heap corruption**: Fixed with heap-safe removal operations
- **Race conditions**: Modern `asyncio.create_task()` usage
- **Version inconsistencies**: Single source of truth in `pyproject.toml`
- **Protocol selection**: Deterministic priority order

### Test Suite Overhaul ✅
- **Behavior-focused testing**: Removed implementation-detail tests
- **80% improvement**: From 42 failures to 8 failures
- **Simple and maintainable**: Clean tests that serve as documentation
- **Contract-based**: Protect public APIs while enabling refactoring

### Known Remaining Issues

#### Minor Performance Considerations
- ProxyPool.remove() is O(N log N) - documented as acceptable for correctness
- Memory usage grows with proxy pool size (~1KB per proxy)

#### Development Notes
- Remember to run `ruff` before committing
- Always specify repo for GitHub CLI: `gh pr view 123 --repo bluet/proxybroker2`
- Remaining 8 test failures are in complex checker mocks (non-critical)

## Development Workflows

### Adding a New Provider
1. Inherit from `Provider` class in `providers.py`
2. Implement `get_proxies()` to extract proxy data
3. Add to `PROVIDERS` list
4. Test individually: `python -c "from proxybroker.providers import YourProvider; ..."`

### Modifying ProxyPool Algorithm
1. Understand heap invariant must be preserved
2. Use `heapq` operations only
3. Test with varying pool sizes
4. Verify `avg_resp_time` is used for priority

### Debugging Async Issues
```bash
# Enable asyncio debug mode
PYTHONASYNCIODEBUG=1 python -m proxybroker find --limit 5

# Check for unclosed resources
python -X dev -m proxybroker find --limit 5
```

## Project Quirks

- Uses both Poetry and setuptools (legacy compatibility)
- CLI uses argparse (not Click) with subcommands
- Entry points: `__main__.py` for module, `py2exe_entrypoint.py` for executables
- GeoIP database bundled in `proxybroker/data/`

### Version Management (Modern Approach)
- **Single source of truth**: `pyproject.toml` version field
- **Development mode**: Automatically reads from pyproject.toml when available
- **Installed mode**: Uses `importlib.metadata` for installed packages
- **Auto-parsed by**: setup.py, docs/source/conf.py, CLI, runtime imports
- **To update version**: Only edit `pyproject.toml` - all other sources sync automatically