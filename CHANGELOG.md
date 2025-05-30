# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Type validation for Proxy.types setter with clear error messages
- Comprehensive test coverage for type validation scenarios
- Enhanced cache invalidation when proxy types are updated

### Fixed
- Resolver test exception handling with proper asyncio.TimeoutError usage
- Broad exception handling in tests replaced with specific exception types
- Code formatting consistency across all test files

### Changed
- Pre-commit configuration updated to ignore false positive security warnings for test files
- Improved error messages for invalid type assignments to proxy.types

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
