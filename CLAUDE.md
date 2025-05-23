# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProxyBroker2 is an async proxy finder, checker, and server that discovers and validates public proxies from multiple sources. It supports HTTP(S), SOCKS4/5 protocols and can operate as a proxy server with automatic rotation.

## Development Commands

### Dependencies
Uses Poetry for dependency management:
```bash
poetry install         # Install dependencies
poetry shell          # Activate virtual environment
```

### Testing
```bash
pytest                 # Run all tests
pytest tests/test_proxy.py  # Run specific test file
pytest -v             # Verbose output
pytest --flake8       # Run with linting
pytest --isort        # Run with import sorting
pytest --cov          # Run with coverage reporting
```

### Linting and Code Quality
```bash
flake8                # Check code style
isort .               # Sort imports
```

### Building
```bash
pip install pyinstaller && pip install . && mkdir -p build && cd build && pyinstaller --onefile --name proxybroker --add-data "../proxybroker/data:data" --workpath ./tmp --distpath . --clean ../py2exe_entrypoint.py && rm -rf tmp *.spec
```

### Docker
```bash
docker build -t proxybroker2 .
docker run --rm proxybroker2 --help
```

## Architecture Overview

### Core Components

**Broker** (`api.py`): Central orchestrator that manages the entire proxy discovery and checking pipeline. Coordinates providers, checkers, and servers.

**ProxyPool** (`server.py`): Manages proxy selection strategies and health tracking. Maintains separate pools for newcomers and established proxies with error rate monitoring.

**Server** (`server.py`): HTTP/HTTPS proxy server that distributes incoming requests across the proxy pool with automatic rotation and failure handling.

**Checker** (`checker.py`): Validates proxy functionality by testing connectivity, anonymity levels, and protocol support through configurable judges.

**Provider** (`providers.py`): Web scrapers that extract proxy lists from various public sources (~50 different websites).

**Negotiators** (`negotiators.py`): Protocol-specific handlers for HTTP CONNECT, SOCKS4, and SOCKS5 proxy connections.

### Key Data Flow

1. **Discovery**: Providers scrape proxy sources concurrently (max 3 at once, configurable via MAX_CONCURRENT_PROVIDERS)
2. **Validation**: Checker tests each proxy against judge servers for connectivity and anonymity
3. **Pooling**: Valid proxies enter ProxyPool with health tracking and rotation strategies
4. **Serving**: Server distributes client requests across healthy proxies with automatic failover

### Important Implementation Details

**Async Architecture**: Entire codebase is built on asyncio with careful resource management for connections and timeouts.

**Error Handling**: Comprehensive exception hierarchy in `errors.py` for different failure modes (connection, timeout, protocol-specific errors).

**Geolocation**: Uses MaxMind GeoLite2 database (`data/GeoLite2-Country.mmdb`) for country-based proxy filtering.

**Configuration**: CLI interface (`cli.py`) with extensive options for timeouts, concurrency limits, filtering criteria, and output formats.

### Project Structure Quirks

- `py2exe_entrypoint.py`: Special entry point for PyInstaller builds
- Two package managers: Poetry (preferred) and setuptools (legacy)
- GeoIP database included in package data (`proxybroker/data/GeoLite2-Country.mmdb`)
- Docker support with multi-stage builds
- Python 3.8+ support (current version targets 3.8-3.10)
- CLI entry point defined via Poetry scripts: `proxybroker = "proxybroker.cli:cli"`

### Python Version Support

The project currently supports Python 3.8-3.10. Python 3.11+ support is in progress but not yet complete. Development dependencies include pytest plugins for async testing, linting (flake8), import sorting (isort), and code coverage.