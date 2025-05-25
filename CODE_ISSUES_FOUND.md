# Code Issues and Design Flaws Found During Test Review

## Critical Bugs Fixed

### 1. Broker.__init__ Event Loop Bug (FIXED)
**Location**: `proxybroker/api.py` line ~70
**Issue**: Crashes with AttributeError when no event loop is running
**Fix Applied**: Added null check before accessing loop methods
```python
# Before:
if stop_broker_on_sigint:
    self._loop.add_signal_handler(signal.SIGINT, self.stop)

# After:  
if stop_broker_on_sigint and self._loop:
    self._loop.add_signal_handler(signal.SIGINT, self.stop)
```

## Design Issues

### 1. Broker.serve() Async Design Flaw
**Location**: `proxybroker/api.py` 
**Issue**: Creates its own event loop, cannot be used in existing async contexts
**Impact**: Modern async applications cannot use this method
**Proposed Fix**: Add `Broker.aserve()` async method
```python
async def aserve(self, host='127.0.0.1', port=8888, limit=100, **kwargs):
    """Async version of serve() for use in existing event loops."""
    # Implementation would reuse existing Server class
```

### 2. ProxyPool Remove Operation Inefficiency
**Location**: `proxybroker/server.py` ProxyPool.remove()
**Issue**: O(N log N) complexity for removing a single proxy
**Impact**: Performance degrades with large proxy pools
**Current Implementation**:
- Removes from heap
- Rebuilds entire heap with heapify
- Also maintains separate dict for O(1) lookups
**Proposed Fix**: Consider alternative data structures like sorted containers

### 3. Version Management Scattered
**Locations**: Multiple files
**Issue**: Version is defined in multiple places
**Impact**: Version updates require multiple file changes
**Proposed Fix**: Single source of truth in `__version__.py`

### 4. Hardcoded Timeouts Throughout
**Locations**: Various components
**Issue**: Many hardcoded timeout values (5s, 8s, etc.)
**Impact**: Users cannot configure timeouts for their network conditions
**Examples**:
- ProxyPool import timeout: 5.0s hardcoded
- Provider timeout: Fixed values
- Judge timeout: Not configurable
**Proposed Fix**: Make timeouts configurable through Broker

## Technical Debt

### 1. Event Loop Handling Inconsistency
**Issue**: Mix of old and new asyncio patterns
- Some code uses `get_running_loop()` (modern)
- Some tries to create loops (legacy)
- Signal handling only works on main thread

### 2. Complex Mock Requirements in Tests
**Issue**: Heavy mocking required even for simple tests
**Impact**: Tests are brittle and hard to maintain
**Root Cause**: Tight coupling between components

### 3. Missing Error Recovery
**Locations**: Various
**Issue**: Many operations lack retry logic or graceful degradation
**Examples**:
- Judge failures stop all checking
- Provider errors not isolated
- No circuit breaker pattern

### 4. Resource Cleanup Issues
**Issue**: Some resources not properly cleaned up
**Examples**:
- Proxy connections may leak on errors
- Server doesn't always close all connections
- No context managers in some async code

## API Inconsistencies

### 1. Sync vs Async API Mix
**Issue**: Some APIs are sync, some async, no clear pattern
**Examples**:
- `Proxy()` is sync constructor
- `Proxy.create()` is async factory
- `Broker.serve()` is sync but does async work

### 2. Parameter Naming Inconsistencies
**Issue**: Same concept, different names
**Examples**:
- `max_conn` vs `max_concurrent_conn`
- `max_tries` vs `attempts_conn`
- `timeout` vs `request_timeout`

### 3. Return Value Inconsistencies
**Issue**: Similar methods return different types
**Examples**:
- `find()` populates queue, returns None
- `grab()` populates queue, returns None
- But users expect iterators based on method names

## Missing Features

### 1. No Built-in Rate Limiting
**Impact**: Can overwhelm proxy providers
**Need**: Per-provider rate limits

### 2. No Proxy Health Metrics Export
**Impact**: Users can't monitor proxy pool health
**Need**: Metrics/stats API

### 3. No Graceful Shutdown
**Impact**: Connections dropped on stop
**Need**: Drain connections before shutdown

### 4. Limited Protocol Support
**Current**: HTTP, HTTPS, SOCKS4, SOCKS5
**Missing**: SOCKS5 with auth, HTTP with auth

## Recommendations

### Immediate Fixes Needed
1. Add `Broker.aserve()` for async compatibility
2. Fix signal handling to work in non-main threads
3. Add configurable timeouts throughout

### Medium-term Improvements
1. Refactor ProxyPool to use more efficient data structure
2. Add proper retry/circuit breaker patterns
3. Implement connection pooling

### Long-term Architecture
1. Separate sync and async APIs clearly
2. Use dependency injection to reduce coupling
3. Add plugin system for custom providers/judges