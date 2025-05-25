# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProxyBroker2 is an async proxy finder, checker, and server that discovers and validates public proxies from multiple sources. It supports HTTP(S), SOCKS4/5 protocols and can operate as a proxy server with automatic rotation.

**Repository**: `bluet/proxybroker2` (GitHub)

## GitHub CLI Commands

When using `gh` (GitHub CLI), always specify the repository as `bluet/proxybroker2`:
```bash
# View PR
gh pr view 185 --repo bluet/proxybroker2

# Get PR comments
gh api repos/bluet/proxybroker2/pulls/185/comments

# List PRs
gh pr list --repo bluet/proxybroker2

# Create PR
gh pr create --repo bluet/proxybroker2
```

## Development Commands

### Dependencies
Uses Poetry for dependency management:
```bash
poetry install         # Install dependencies
poetry shell          # Activate virtual environment
python3 -m venv venv && source venv/bin/activate  # Alternative: use project-level venv
```

### Testing
```bash
pytest                 # Run all tests
pytest tests/test_proxy.py  # Run specific test file
pytest -v             # Verbose output
pytest --cov=proxybroker --cov-report=term-missing  # Coverage analysis
pytest tests/test_api.py::test_broker_constants -v  # Run specific test
pytest -xvs tests/test_cli.py::TestCLI::test_cli_help  # Run single test with output
pytest --tb=short     # Short traceback for debugging
```

**Test Suite Status** (as of latest comprehensive testing implementation):
- ✅ **All tests passing**: 238/238 tests pass across all test files
- ✅ **Testing Philosophy**: Contract-based testing protecting user APIs while enabling internal improvements
- ✅ **New Test Files**: 
  - `test_public_contracts.py` (25 tests) - API signature and backward compatibility tests
  - `test_server_behavior.py` (18 tests) - User-facing server scenarios
  - `test_checker_behavior.py` (14 tests) - Checker behavior from user perspective
  - `test_integration.py` (13 tests) - Real-world usage patterns
  - `test_negotiators_behavior.py` (18 tests) - Protocol negotiation behaviors
- ✅ **Code Quality**: Zero linting errors, all code formatted with ruff
- ✅ **CI/CD**: Enhanced GitHub Actions with automated quality gates

### Linting and Code Quality
**Use automated tools for efficient formatting:**
```bash
# Modern approach: Use ruff (fastest, most comprehensive)
ruff check proxybroker/ tests/ --fix         # Fix linting issues automatically
ruff format proxybroker/ tests/              # Format code automatically

# Alternative: Traditional tools combination
isort proxybroker/ tests/                    # Organize imports automatically
black proxybroker/ tests/ --line-length 127 # Format code automatically
flake8 proxybroker/ tests/ --max-line-length=127 --exclude=__pycache__  # Verify clean

# One-liner for complete formatting:
ruff check . --fix && ruff format .

# Legacy manual approach (avoid)
# Manual fixes are tedious and error-prone - use automated tools instead
```

**Available Tools:**
- **`ruff`**: Ultra-fast linter + formatter (recommended)
- **`black`**: Code formatter (good alternative)
- **`isort`**: Import organizer (included in ruff)
- **`flake8`**: Linter (included in ruff)
- **`autopep8`**: PEP8 formatter (use ruff instead)

### Building and Packaging
```bash
# Build wheel/source distributions
poetry build

# Install locally for development
pip install -e .

# Create standalone executable (Windows/Mac/Linux)
pip install pyinstaller && pip install . && mkdir -p build && cd build && pyinstaller --onefile --name proxybroker --add-data "../proxybroker/data:data" --workpath ./tmp --distpath . --clean ../py2exe_entrypoint.py && rm -rf tmp *.spec
# Note: Creates .exe on Windows, binary executable on Mac/Linux
# Requires data files bundled with --add-data
```

### Docker
```bash
docker build -t proxybroker2 .
docker run --rm proxybroker2 --help
```

### Debugging Commands
```bash
# Run with debug logging
proxybroker --log debug find --types HTTP --limit 5

# Test specific provider
python -c "from proxybroker.providers import Proxy_list_org; import asyncio; asyncio.run(Proxy_list_org().find())"

# Profile performance
python -m cProfile -o profile.stats -m proxybroker find --types HTTP --limit 10

# Debug asyncio issues
PYTHONASYNCIODEBUG=1 python -m proxybroker find --types HTTP --limit 5
```

## Architecture Overview

### Core Components and Data Flow

**Broker** (`api.py`): Central orchestrator managing the proxy discovery pipeline. Coordinates providers, checkers, and servers. Contains critical `_grab()` method that implements the main discovery loop with provider concurrency limits.

**ProxyPool** (`server.py`): Implements sophisticated proxy selection using heap-based priority queue. Maintains separate pools for newcomers (untested proxies) and established proxies with health metrics. **Critical**: Uses `proxy.avg_resp_time` as priority key, not `proxy.priority`.

**Server** (`server.py`): HTTP/HTTPS proxy server with automatic proxy rotation. Implements protocol selection strategy and handles both HTTP CONNECT and direct proxy modes. Includes built-in API for proxy management (`proxycontrol` host).

**Checker** (`checker.py`): Validates proxy functionality through judge servers. Implements anonymity level detection by analyzing HTTP headers and IP address leakage. Supports multiple protocol testing (HTTP/HTTPS/SOCKS/SMTP).

**Negotiators** (`negotiators.py`): Protocol-specific connection handlers for HTTP CONNECT, SOCKS4, and SOCKS5. Each negotiator implements the specific handshake protocol.

### Provider System Architecture

**Provider Base** (`providers.py`): Abstract base class for all proxy providers. Key methods:
- `get()/get_proxies()`: Fetches proxy data from source
- `find()`: Main discovery method that yields proxies
- URL patterns and extraction logic specific to each provider

**Provider Registry**: ~50 provider implementations in PROVIDERS list, each handling:
- Static lists (e.g., `Provider` with direct URL)
- Dynamic scrapers (e.g., `Blogspot_com`, `Spys_ru`)
- API-based providers (e.g., `Pubproxy_com`)

**Concurrency Control**: `MAX_CONCURRENT_PROVIDERS=3` limits simultaneous provider requests to avoid overwhelming sources.

### Judge System Architecture

**Judges** (`checker.py`): External servers used to validate proxy functionality:
- HTTP judges return client info (IP, headers) to detect anonymity
- HTTPS judges validate SSL/TLS support
- Default judges include httpbin.org, azenv.net variants
- Round-robin selection for load distribution
- Fallback mechanism when judges fail

### Critical Async Patterns

The codebase uses modern asyncio patterns post-Python 3.10:
- **Event Loop Handling**: Uses `asyncio.get_running_loop()` with fallback for import-time instantiation
- **Task Creation**: `asyncio.create_task()` preferred over deprecated `asyncio.ensure_future()`
- **Concurrency Control**: Provider concurrency limited by `MAX_CONCURRENT_PROVIDERS` (default: 3)
- **Resource Management**: Comprehensive connection cleanup in proxy.close() with error handling

### ProxyPool Priority Logic

**Selection Strategy**: Uses min-heap where lower `avg_resp_time` = higher priority
```python
# Priority queue: (response_time, proxy)
heapq.heappush(self._pool, (proxy.avg_resp_time, proxy))
```

**Health Tracking**: Proxies move between pools based on experience:
- `_newcomers`: New proxies (< `min_req_proxy` requests)
- `_pool`: Established proxies meeting quality thresholds
- Discarded: High error rate (> `max_error_rate`) or slow response (> `max_resp_time`)

### Protocol Selection Strategy

Server chooses protocols deterministically with priority order:
- **HTTP**: `HTTP` > `CONNECT:80` > `SOCKS5` > `SOCKS4`
- **HTTPS**: `HTTPS` > `SOCKS5` > `SOCKS4`
- Uses `_prefer_connect` flag to prioritize CONNECT method when available

### Key Recent Improvements

1. ✅ **Heap-safe operations**: `ProxyPool.remove()` preserves heap invariant
2. ✅ **Deadlock prevention**: Timeouts and retry limits in critical paths
3. ✅ **Modern async patterns**: Uses `asyncio.create_task()` throughout
4. ✅ **Correct priority logic**: Uses `proxy.avg_resp_time` for selection
5. ✅ **Deterministic protocol selection**: Clear priority order
6. ✅ **Comprehensive test coverage**: 238 tests with contract-based approach

## Configuration and Environment

### Python Version Support
- **Minimum**: Python 3.10+ (updated from 3.9+ for better asyncio support)
- **Tested**: Python 3.10-3.13 in CI pipeline
- **Asyncio Compatibility**: All Python 3.13 deprecations resolved

### Available Testing Environments
Conda environments are pre-configured for cross-version testing:
- **System Python**: 3.10.12 (`/usr/bin/python3`)
- **py311-proxybroker**: Python 3.11.11 (`conda activate py311-proxybroker`)
- **py312-proxybroker**: Python 3.12.9 (`conda activate py312-proxybroker`)
- **py313-proxybroker**: Python 3.13.2 (`conda activate py313-proxybroker`)

To run tests in a specific Python version:
```bash
# Example: Test with Python 3.11
conda activate py311-proxybroker
pytest tests/test_server.py -v

# Or run without activating:
conda run -n py311-proxybroker pytest tests/test_server.py -v
```

### Key Configuration Points
- **Timeouts**: Default 8s, configurable per-component
- **Concurrency**: `max_conn` (default: 200), `MAX_CONCURRENT_PROVIDERS` (3)
- **Quality Thresholds**: `max_error_rate` (0.5), `max_resp_time` (8s), `min_req_proxy` (5)
- **Judge Selection**: Round-robin from available working judges per protocol

### Project Structure Quirks

- **Entry Points**: Both `py2exe_entrypoint.py` (PyInstaller) and Poetry script
- **Package Managers**: Poetry (preferred) + setuptools (legacy compatibility)
- **GeoIP Database**: Embedded MaxMind GeoLite2 in `proxybroker/data/`
- **CLI Architecture**: argparse-based with subcommands (find/grab/serve) - NOT Click!
- **Version**: Currently v2.0.0-alpha6 (stable and production-ready)
- **Python Support**: 3.10-3.13 officially tested and supported

## Testing Strategy & Philosophy

### Contract-Based Testing Approach

**Core Principle**: Test user-visible behavior, not implementation details.

#### ✅ What TO Test (Stable Public Contracts)
```python
# Public API signatures and behavior
broker = Broker(timeout=8, max_conn=200)
await broker.find(types=['HTTP'], limit=10)
proxy.as_json()  # JSON structure consistency
proxy.as_text()  # "host:port\n" format
```

#### ❌ What NOT to Test (Flexible Implementation)
```python
# Internal protocol details that should evolve
assert proxy.send.call_args_list == [call(b"\x05\x01\x00")]  # SOCKS bytes
# Internal algorithms and metrics calculations  
# Provider scraping specifics (need to adapt to site changes)
```

### Test File Strategy

- **`test_api_contracts.py`**: Critical API stability (never break users)
- **`test_integration.py`**: User workflows from `examples/` directory
- **`test_negotiators_behavior.py`**: Protocol behavior vs exact bytes
- **Core tests**: Focus on functionality users depend on

### Testing Guidelines

1. **Test Behavior, Not Implementation**
   - ✅ "Does SOCKS negotiation succeed?" 
   - ❌ "Are exact handshake bytes correct?"

2. **Protect User Contracts**
   - ✅ API signatures, return formats, error types
   - ❌ Internal algorithms, performance metrics

3. **Enable Innovation**
   - ✅ Allow protocol improvements, IPv6 support
   - ❌ Lock in current implementation details

4. **Real User Scenarios**
   - ✅ Test workflows from `examples/` directory
   - ❌ Test hypothetical edge cases

### Example: Good vs Bad Testing

```python
# ❌ BAD: Tests implementation details
def test_socks5_exact_bytes():
    assert proxy.send.called_with(b"\x05\x01\x00")

# ✅ GOOD: Tests user-visible behavior  
def test_socks5_negotiation_succeeds():
    # Mock successful SOCKS5 response
    proxy.recv.side_effect = [b"\x05\x00", b"\x05\x00\x00\x01..."]
    await proxy.ngtr.negotiate(ip="127.0.0.1", port=80)
    # Negotiation should complete without error
```

## Development Guidelines

### Working with ProxyPool
- **Never** directly manipulate `_pool` list - use `heapq` operations
- Always use `proxy.avg_resp_time` for priority calculations
- Understand newcomer → established proxy lifecycle

### Async Development
- Use `asyncio.create_task()` for new task creation
- Implement proper cleanup in `finally` blocks
- Use `asyncio.wait_for()` for timeout protection

### Error Handling Patterns
- Component-specific exceptions in `errors.py`
- Log errors before re-raising or handling
- Use contextual error messages with proxy/host information


## HTTP API Features

### Proxy Control API
Server exposes control API via special `proxycontrol` host:
- `GET /api/remove/HOST:PORT` - Remove specific proxy from pool
- `GET /api/history/url:URL` - Get proxy used for specific URL

### Proxy Information Headers
- **HTTP**: `X-Proxy-Info` header in response contains `host:port`
- **HTTPS**: Header sent after CONNECT establishment (limited client support)

## CLI Usage Examples

### Find Proxies
```bash
proxybroker find --types HTTP HTTPS --lvl High --countries US --strict -l 10
```

### Grab Without Checking
```bash
proxybroker grab --countries US --limit 10 --outfile ./proxies.txt
```

### Run Proxy Server
```bash
proxybroker serve --host 127.0.0.1 --port 8888 --types HTTP HTTPS --lvl High --min-queue 5
```

### Quick Testing Commands
```bash
# Find 5 HTTP proxies quickly
proxybroker find --types HTTP --limit 5

# Test with specific country
proxybroker find --countries US --types HTTP --limit 3

# Run server and test with curl
proxybroker serve --host 127.0.0.1 --port 8888 --types HTTP --limit 10 &
curl -x http://127.0.0.1:8888 http://httpbin.org/ip
```

## Common Development Workflows

### Adding a New Provider
1. Create class inheriting from `Provider` in `providers.py`
2. Implement `get_proxies()` method for extraction logic
3. Add to `PROVIDERS` list
4. Test with direct instantiation before full integration

### Modifying Proxy Selection Algorithm
1. Review `ProxyPool._pool` heap operations
2. Maintain heap invariant with `heapq` operations
3. Test with `test_server_behavior.py` scenarios

### Adding New Protocol Support
1. Create negotiator class in `negotiators.py`
2. Update `PROTOCOLS` mapping in `checker.py`
3. Add protocol-specific judges if needed
4. Update CLI argument choices

## Code Quality Maintenance

### Before Making Changes
1. Review `BUG_REPORT.md` for known issues in affected areas
2. Run tests to establish baseline: `pytest tests/ -v`
3. Use virtual environment to avoid system pollution

### Pre-Commit Checklist
**ALWAYS run these checks before committing:**
```bash
# 1. Run ruff checks and auto-fix
ruff check . --fix

# 2. Run ruff formatting
ruff format .

# 3. Verify everything passes
ruff check . && ruff format --check .

# 4. Run tests for changed files
pytest tests/test_affected_file.py -v

# Optional but recommended: Run full test suite
pytest tests/ -v
```

### Critical Areas Requiring Careful Changes
- **ProxyPool heap operations** (heap invariant preservation)
- **Async task lifecycle** (proper cleanup and cancellation)
- **Protocol negotiation** (SOCKS/HTTP handshake sequences)
- **Event loop handling** (compatibility across Python versions)

### Testing Changes
- Verify heap integrity after ProxyPool modifications
- Test async patterns with proper event loop setup
- Validate protocol compatibility with multiple proxy types
- Check resource cleanup under exception conditions

## Common Issues and Solutions

### AsyncIO Warnings
- "coroutine was never awaited" - check for missing `await` or `asyncio.create_task()`
- Event loop issues - ensure proper loop handling for Python 3.10+
- Use `asyncio.run()` for main entry points, not `loop.run_until_complete()`

### Import-Time Issues
- Some components try to get event loop at import time
- Use `asyncio.get_running_loop()` with try/except for compatibility
- Lazy initialization patterns help avoid import-time errors

## Performance Considerations

- **Provider Timeout**: Default 5s per provider, adjust for slow sources
- **Checker Concurrency**: `max_conn=200` simultaneous proxy checks
- **Memory Usage**: ~50-100MB base + ~1KB per proxy in pool
- **Database**: GeoLite2 loaded once, shared across instances
- **Async Limits**: ~10k concurrent connections practical maximum