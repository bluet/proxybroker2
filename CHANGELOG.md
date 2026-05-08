# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0b2] - 2026-05-08

🎯 **Custom Provider System & Quality Pass**

This release adds a user-extensible proxy provider system (the headline feature) and bundles a focused quality pass: parser bug fixes with regression tests, removal of recurring SAST false positives by fixing the underlying code (not just suppressing), modernization of `%`-formatting to f-strings, and isolation of the unverified-SSL bypass into a named helper.

Tracked follow-ups for next releases: #200 (GeoIP replacement), #201 (IPv6 regex via stdlib `ipaddress`), #202 (cognitive-complexity refactor in parsers), #203 (`argparse.FileType` and `asyncio.get_event_loop()` deprecation).

### Added
- **Custom proxy provider system**: users can register their own proxy
  sources without modifying the package. Drop YAML/JSON config files
  into a directory, mount it into the container, and the broker
  auto-loads them at startup. Targets the Docker bind-mount workflow
  for entry-level / no-code users.
- Four provider helper classes in `proxybroker.provider_utils`:
  `SimpleProvider` (text/CSV/JSON list endpoints with format
  autodetect), `PaginatedProvider` (numbered-page endpoints with
  configurable URL templates and step), `APIProvider` (JSON APIs with
  optional Bearer/key auth and dotted `proxy_path` navigation), and
  `ConfigurableProvider` (factory that reads YAML/JSON and dispatches
  to the right class).
- CLI flag `--provider-dir PATH` (repeatable) on top-level and on
  every subcommand. Falls back to env var
  `PROXYBROKER_PROVIDER_DIR`, then to the `/configs` Docker
  convention if the directory exists.
- Python API: `Broker(provider_dirs=[...])` for programmatic use. The
  empty-list contract is preserved: `providers=[]` means "no bundled
  defaults" (distinct from `providers=None` which means "use defaults").
- `load_provider_configs_from_directory()` (safe-by-default YAML/JSON
  loader, used by Docker UX) and `load_python_providers_from_directory()`
  (Python file loader, opt-in only - not wired to the CLI; users must
  call it explicitly from their own code).
- Type validation for `Proxy.types` setter with clear error messages.
- Comprehensive test coverage: 32 tests for `provider_utils` parsers,
  13 tests for `Provider` base class behavior, 9 tests for `ProxyPool`,
  expanded CLI tests including `--provider-dir` placement validation.
- Documentation: `docs/custom_providers.md` (Docker-first user guide
  with YAML config recipes and Python examples).
- Eight worked examples under `examples/custom_providers/` covering
  each provider type and the configuration-directory loading flow.
- Python 3.14 to the supported version matrix (now 3.10-3.14).
- Pre-commit hook: ruff hook now runs with `--unsafe-fixes` enabled,
  so future `%`-formatting and similar modernization lints get
  auto-fixed at commit time instead of accumulating.

### Changed
- `Judge.is_working` is now a `@property` with setter (was a plain
  attribute). Mirrors the pattern already used by `Proxy.is_working`
  and removes a recurring SAST false-positive flag. Behavior is
  unchanged - read/write sites work as before.
- The unverified-SSL context construction in `Proxy.__init__` is
  extracted into a private helper
  `_make_unverified_ssl_context_for_proxy_testing()`. Suppression
  annotations are concentrated on the helper instead of bracketing
  four lines of inline code. Behavior unchanged.
- `aiodns.DNSResolver()` is now lazy-initialised on first resolve
  call rather than at module-import time. Required for Python 3.14
  where the eager call raises `RuntimeError` (no running event loop).
- Eighteen `%`-formatting calls across `api.py`, `checker.py`,
  `cli.py`, `providers.py`, and `server.py` are now f-strings.
  Modernization debt that had been silently accumulating because the
  pre-commit ruff hook was missing `--unsafe-fixes`.
- Dockerfile is pinned to a specific SHA256 digest of `python:3.14-slim`
  (was a floating tag). Tag is retained alongside the digest as
  human-readable documentation.
- CLI subcommand `update-geo` help text now reads
  `(broken since 2019) Download GeoIP database - see issue #200`
  so users see the deprecation before they run the command.
- Pre-commit configuration tightened to actually enforce the rule
  selection it was already configured for.

### Removed
- `proxybroker.utils.update_geoip_db()` body. The function previously
  attempted to download from `geolite.maxmind.com`, which has been
  NXDOMAIN since 2019-12-30 (MaxMind retired the unauthenticated
  endpoint and now requires a license key). The function now raises
  `RuntimeError` with a message linking to the tracking issue
  (#200). Bundled GeoLite2 databases in `proxybroker/data/` continue
  to work for runtime IP lookups; they just cannot be refreshed via
  this command.
- Four now-unused stdlib imports (`shutil`, `tarfile`, `tempfile`,
  `urllib.request`) along with the `update_geoip_db()` body.

### Fixed
- `SimpleProvider._parse_csv` now uses the stdlib `csv` module so
  quoted fields with embedded commas (e.g. `"Company, Inc",80`)
  round-trip correctly. The previous `str.split(",")` path corrupted
  any line whose first field contained a comma.
- `SimpleProvider._parse_text` now extracts only the leading digit
  run after the first `:` as the port. Lines like `"1.2.3.4:8080:tag"`
  or `"1.2.3.4:8080 # US"` previously crashed `Proxy.create` because
  the entire suffix was treated as the port string.
- `SimpleProvider._parse_json` no longer emits duplicate proxies for
  items that have both `ip` and `host` keys (these are alias fields,
  not separate proxies).
- `SimpleProvider._parse_json` now unwraps single-level object-wrapped
  list responses (`{"proxies": [...]}`, `{"data": [...]}`, etc.).
  Previously it silently returned zero proxies for the very common
  JSON:API style.
- `PaginatedProvider` URL building now replaces an existing `page=`
  query parameter rather than appending a duplicate, so URLs like
  `https://example.com/list?page=1` are paginated correctly.
- `APIProvider.find_proxies` `proxy_path` navigation now stops
  gracefully when it encounters a non-dict, instead of raising
  `AttributeError` and killing the provider.
- `Resolver` test exception handling uses `asyncio.TimeoutError`
  rather than catching `Exception`.
- `tests/test_public_contracts.py` swapped `asyncio.iscoroutinefunction`
  for `inspect.iscoroutinefunction`. The asyncio alias is deprecated
  in Python 3.14 and slated for removal in 3.16.
- Multiple SAST false-positive suppressions removed by fixing the
  underlying code patterns (e.g. converting `Judge.is_working` to a
  property removed five `# nosemgrep` annotations).

## [2.0.0b1] - 2025-05-26

🎯 **Production-Ready Beta - All Critical Bugs Fixed & Enhanced Documentation**

### Added
- Python 3.10-3.13 support with full async context manager compatibility
- Contract-based testing to protect public APIs
- Comprehensive architecture documentation in CLAUDE.md
- CI/CD pipeline for Python 3.10-3.13 matrix testing
- Modernized examples using asyncio.run() instead of deprecated patterns
- Updated Sphinx documentation with correct GitHub references
- ReadTheDocs configuration v2 format
- Enhanced auto-generated documentation with Napoleon and autosummary
- Comprehensive serve command testing and production verification
- Modern MyST-Parser configuration with advanced Markdown features
- Cross-references to Python and aiohttp documentation
- Conventional commit template for structured development

### Changed
- **BREAKING**: Minimum Python version is now 3.10+ (was 3.5.3+ in v0.3.2)
- **BREAKING**: Installation method changed from `pip install proxybroker` to GitHub installation
- **BREAKING**: CLI entry point changed from `proxybroker` to `python -m proxybroker`
- Package renamed to ProxyBroker2 (this is a maintained fork of abandoned original)
- Implemented single source of truth version management in pyproject.toml
- Enhanced ProxyPool with configurable timeout and retry parameters
- Modern packaging compliance following PEP 621 standards
- Replaced deprecated asyncio.ensure_future() with asyncio.create_task()
- Made protocol selection deterministic with explicit priority order
- Modernized documentation stack to 2025 best practices (Sphinx 8.x, MyST-Parser 4.x)
- Updated all README examples to work correctly (fixed missing --types parameters)
- Corrected ReadTheDocs project name to proxybroker2
- Enhanced CLAUDE.md with comprehensive documentation strategy
- Improved migration guide with correct v0.3.2 baseline
- Optimized Sphinx configuration with latest extensions
- Modernized test fixtures to remove deprecated pytest-asyncio event_loop usage where possible
- Cleaned up obsolete flake8 configuration in favor of ruff toolchain
- Improved async test patterns while maintaining functionality for tests requiring event_loop fixture

### Fixed
- Signal handler memory leak in Broker.stop() - proper cleanup prevents resource leaks
- ProxyPool deadlocks with timeout protection and retry limits
- Heap corruption in ProxyPool.remove() using heap-safe operations
- Race conditions by replacing deprecated asyncio patterns
- Undefined proxy.priority usage - now correctly uses proxy.avg_resp_time
- Provider initialization bug - empty providers list now properly respected
- All remaining test bugs to achieve complete test coverage
- All README command examples now work without errors
- ReadTheDocs URLs point to proxybroker2 instead of legacy proxybroker
- Documentation builds successfully with modern toolchain
- Serve command thoroughly tested for Docker/production use
- Eliminated most ResourceWarnings from aiohttp sessions during test execution
- Removed deprecated pytest configuration for discontinued flake8 integration
- Resolved pytest-asyncio deprecation warnings for tests that could be safely updated

### Removed
- **BREAKING**: Dropped support for Python 3.5-3.9
- Complex mock-heavy tests that tested implementation details
- Outdated analysis files (BUG_REPORT.md, CODE_ISSUES_FOUND.md, CRITICAL_FIXES.py)
- Old RST changelog in favor of modern Markdown format
- Redundant test status documentation (CI badges show real-time status)

## [0.3.2] - 2018-03-12

_Note: This is the last release of the original ProxyBroker project by constverum_

### Changed
- Update dependencies and minor fixes
- Improve formatting (by `black`)

## [0.3.1] - 2018-02-22

### Changed
- Update dependencies and minor fixes

## [0.3.0] - 2017-10-31

### Added
- `update-geo` command for updating GeoIP database with additional geolocation information
- `--format` flag indicating result presentation format
- Improved `--outfile` flag behavior with real-time results

### Changed
- Improved way to get the external IP address

## [0.2.0] - 2017-09-17

### Added
- CLI interface
- `Broker.serve` function for proxy server mode with request distribution
- New proxy types: `CONNECT:80` and `CONNECT:25` (SMTP)
- New filtering options: `post`, `strict`, `dnsbl` parameters
- Support for Cookies and Referer checking
- gzip and deflate support

### Changed
- Parameter `types` in `Broker.find` and `Broker.serve` is now required
- `ProxyChecker` renamed to `Checker`
- `Proxy.avgRespTime` renamed to `Proxy.avg_resp_time`

### Deprecated
- `max_concurrent_conn` and `attempts_conn` (use `max_conn` and `max_tries`)
- Parameter `full` in `Broker.show_stats` (use `verbose`)
- `ProxyChecker` class (use `Checker`)
- `Proxy.avgRespTime` (use `Proxy.avg_resp_time`)

## [0.1.4] - 2016-04-07

### Fixed
- Bug when launched the second time to find proxies

## [0.1.3] - 2016-03-26

### Changed
- `ProxyProvider` renamed to `Provider`
- `Broker` now accepts Provider and Judge objects, not just strings

### Fixed
- Signal handler bug on Windows

### Deprecated
- `ProxyProvider` class (use `Provider`)

## [0.1.2] - 2016-02-27

### Fixed
- SIGINT bug on Linux
- Bug with clearing the queue of proxy check

## [0.1] - 2016-02-23

### Added
- Updated and added new providers

### Fixed
- Few minor fixes

## [0.1b4] - 2016-01-21

### Added
- A few tests
- Updated documentation

## [0.1b3] - 2016-01-16

### Fixed
- Few minor fixes

## [0.1b2] - 2016-01-10

### Fixed
- Few minor fixes

## [0.1b1] - 2015-12-29

### Added
- Support of multiple proxy providers
- Initial public release on PyPI

### Changed
- Project renamed from PyProxyChecker to ProxyBroker

### Fixed
- Many improvements and bug fixes

## [0.1a2] - 2015-11-24

### Added
- Support of multiple proxy judges

## [0.1a1] - 2015-11-11

### Added
- Initial commit with proxy checking functionality

[Unreleased]: https://github.com/bluet/proxybroker2/compare/v2.0.0b1...HEAD
[2.0.0b1]: https://github.com/bluet/proxybroker2/compare/v2.0.0-alpha8...v2.0.0b1
[2.0.0-alpha8]: https://github.com/bluet/proxybroker2/compare/v0.3.2...v2.0.0-alpha8
[0.3.2]: https://github.com/constverum/ProxyBroker/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/constverum/ProxyBroker/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/constverum/ProxyBroker/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/constverum/ProxyBroker/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/constverum/ProxyBroker/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/constverum/ProxyBroker/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/constverum/ProxyBroker/compare/v0.1...v0.1.2
[0.1]: https://github.com/constverum/ProxyBroker/compare/v0.1b4...v0.1
[0.1b4]: https://github.com/constverum/ProxyBroker/compare/v0.1b3...v0.1b4
[0.1b3]: https://github.com/constverum/ProxyBroker/compare/v0.1b2...v0.1b3
[0.1b2]: https://github.com/constverum/ProxyBroker/compare/v0.1b1...v0.1b2
[0.1b1]: https://github.com/constverum/ProxyBroker/compare/v0.1a2...v0.1b1
[0.1a2]: https://github.com/constverum/ProxyBroker/compare/v0.1a1...v0.1a2
[0.1a1]: https://github.com/constverum/ProxyBroker/releases/tag/v0.1a1
