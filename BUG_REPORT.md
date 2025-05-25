# ProxyBroker2 Code Review - Bugs and Issues Report

## 🚨 Critical Issues

### 1. **Race Condition in api.py `_grab()` method** 
**File**: `proxybroker/api.py:332`
**Severity**: High
**Status**: **FIXED** - Now uses `asyncio.create_task()` instead of deprecated `asyncio.ensure_future()`
**Issue**: Uses deprecated `asyncio.ensure_future()` which can cause race conditions
```python
# Line 332 - PROBLEMATIC
tasks = [asyncio.ensure_future(pr.get_proxies()) for pr in providers[:by]]
```
**Fix**: Replace with `asyncio.create_task()`
```python
tasks = [asyncio.create_task(pr.get_proxies()) for pr in providers[:by]]
```

### 2. **Potential Deadlock in server.py `ProxyPool._import()`**
**File**: `proxybroker/server.py:76-84`
**Severity**: High
**Status**: **FIXED** - Added timeout and maximum retry limit to prevent infinite loops
**Issue**: Infinite loop with potential deadlock when proxy queue is exhausted
```python
async def _import(self, expected_scheme):
    while True:  # ⚠️ INFINITE LOOP - can hang forever
        proxy = await self._proxies.get()
        self._proxies.task_done()
        if not proxy:
            raise NoProxyError('No more available proxies')
        elif expected_scheme not in proxy.schemes:
            self.put(proxy)  # ⚠️ Can cause infinite recycling
        else:
            return proxy
```
**Fix**: Add maximum retry limit and timeout

### 3. **Heap Corruption in server.py `ProxyPool.remove()`**
**File**: `proxybroker/server.py:99-112`
**Severity**: High
**Status**: **FIXED** - Now properly rebuilds heap using heapq.heapify() after removal
**Issue**: Direct list removal from heap breaks heap property
```python
# Lines 106-110 - HEAP CORRUPTION
for priority, proxy in self._pool:
    if proxy.host == host and proxy.port == port:
        chosen = proxy
        self._pool.remove((proxy.priority, proxy))  # ⚠️ BREAKS HEAP INVARIANT
        break
```
**Fix**: Rebuild heap after removal or use proper heap operations

### 4. **Memory Leak in api.py Signal Handler**
**File**: `proxybroker/api.py:113`
**Severity**: Medium-High
**Status**: **FIXED** - Signal handlers are now properly removed in cleanup/stop methods
**Issue**: Signal handler may not be properly cleaned up
```python
self._loop.add_signal_handler(signal.SIGINT, self.stop)
```
**Fix**: Remove signal handler in cleanup methods

### 5. **Resource Leak in server.py Connection Handling**
**File**: `proxybroker/server.py:183-202`
**Severity**: Medium-High
**Issue**: Connections may not be properly cleaned up on exceptions
```python
def _accept(self, client_reader, client_writer):
    def _on_completion(f):
        reader, writer = self._connections.pop(f)
        writer.close()  # ⚠️ May not be called if callback fails
```

## 🔧 Logic Issues

### 6. **Incorrect Error Handling in checker.py**
**File**: `proxybroker/checker.py:104`
**Severity**: Medium
**Issue**: Missing `raise` statement causes silent failures
```python
# Line 104 - ALREADY FIXED in previous commits
raise RuntimeError('Not found judges')  # ✅ Now correctly raises
```

### 7. **Inconsistent Event Loop Handling**
**File**: Multiple files
**Severity**: Medium
**Issue**: Mixed patterns for event loop initialization
- Some use `asyncio.get_event_loop()` (deprecated)
- Some use `asyncio.get_running_loop()` with try/catch
- Inconsistent handling of missing event loops

### 8. **Proxy Priority Logic Issue in server.py**
**File**: `proxybroker/server.py:95`
**Severity**: Medium
**Status**: **FIXED** - Now correctly uses `proxy.avg_resp_time` for heap priority
**Issue**: Uses `proxy.priority` but Proxy class doesn't define this attribute
```python
heapq.heappush(self._pool, (proxy.priority, proxy))  # ⚠️ AttributeError risk
```
**Fix**: Should use `proxy.avg_resp_time` or define priority property

### 9. **Type Safety Issues in server.py**
**File**: `proxybroker/server.py:361-374`
**Severity**: Medium
**Status**: **FIXED** - Now uses deterministic priority order for protocol selection
**Issue**: Protocol selection uses `.pop()` on set which is non-deterministic
```python
relevant = {'HTTP', 'CONNECT:80', 'SOCKS4', 'SOCKS5'} & proxy.types.keys()
proto = relevant.pop()  # ⚠️ Non-deterministic selection
```

### 10. **Uncaught Exception in api.py Task Callback**
**File**: `proxybroker/api.py:390-399`
**Severity**: Medium
**Issue**: Task callback can raise unhandled exceptions
```python
def _task_done(proxy, f):
    # ... code ...
    try:
        if f.result():  # ⚠️ Can raise various exceptions
            self._push_to_result(proxy)
    except asyncio.CancelledError:
        pass  # ⚠️ Only catches CancelledError, not other exceptions
```

## ⚠️ Potential Issues

### 11. **Thread Safety Concerns**
**Files**: `proxybroker/server.py`, `proxybroker/api.py`
**Issue**: Global state and shared resources without proper synchronization
- `history` TTLCache is global and accessed from multiple coroutines
- `unique_proxies` dict accessed without locks

### 12. **Error Propagation Issues**
**File**: `proxybroker/api.py:364`
**Issue**: Broad exception catching may hide important errors
```python
except (ResolveError, ValueError):
    return  # ⚠️ Silent failure - should log errors
```

### 13. **Resource Exhaustion Risk**
**File**: `proxybroker/api.py:339`
**Issue**: Infinite loop in `_grab()` without proper exit conditions
```python
while True:  # ⚠️ Can run forever
    for tasks in _get_tasks():
        # ... processing ...
    if self._server:
        await asyncio.sleep(GRAB_PAUSE)
    else:
        break  # Only breaks in non-server mode
```

### 14. **Input Validation Missing**
**File**: `proxybroker/server.py:218-256`
**Issue**: API endpoints don't validate input parameters
```python
_api, _operation, _params = headers['Path'].split('/', 5)[3:]
# ⚠️ No validation of _api, _operation, or _params
```

### 15. **Incomplete Error Recovery**
**File**: `proxybroker/server.py:258-344`
**Issue**: Server doesn't implement proper retry logic for transient failures

## 🐛 Minor Issues

### 16. **Import Organization**
**Files**: Various
**Issue**: Inconsistent import ordering and unused imports

### 17. **String Encoding Issues**
**File**: `proxybroker/server.py:247`
**Issue**: Potential encoding issue in header construction
```python
f"Content-Length: {str(len(previous_proxy_bytestring) + 2).encode()}\r\n"
# ⚠️ Calling .encode() on str() result
```

### 18. **Deprecated Warning Handling**
**File**: `proxybroker/api.py:84-101`
**Issue**: Deprecated parameter handling but still processed

### 19. **Logging Inconsistencies**
**Files**: Various
**Issue**: Mix of print statements and logging calls

### 20. **Configuration Validation Missing**
**Files**: Various  
**Issue**: No validation of configuration parameters (timeouts, limits, etc.)

## 🔍 Performance Issues

### 21. **Inefficient Heap Operations**
**File**: `proxybroker/server.py:52-72`
**Issue**: Heap search is O(n) instead of using proper priority queue

### 22. **Unnecessary String Operations**
**File**: `proxybroker/checker.py:123`
**Issue**: String reversing for DNSBL could be optimized

### 23. **Blocking Operations in Async Context**
**Files**: Various
**Issue**: Some operations that could block the event loop

## 💡 Recommendations

### High Priority Fixes
1. **Fix heap corruption** in ProxyPool.remove()
2. **Replace asyncio.ensure_future()** with asyncio.create_task()
3. **Add deadlock protection** in ProxyPool._import()
4. **Fix proxy.priority** attribute issue
5. **Improve error handling** and logging

### Medium Priority Fixes  
1. **Add input validation** for API endpoints
2. **Implement proper resource cleanup**
3. **Add timeouts** to prevent infinite loops
4. **Improve exception handling** specificity
5. **Add configuration validation**

### Low Priority Improvements
1. **Optimize heap operations**
2. **Standardize logging**
3. **Clean up imports**
4. **Add type hints**
5. **Improve documentation**

## 🧪 Testing Recommendations

1. **Add stress tests** for ProxyPool operations
2. **Test heap invariant** preservation
3. **Add timeout tests** for infinite loop scenarios  
4. **Test resource cleanup** under exception conditions
5. **Add concurrency tests** for race conditions

## 🔧 Code Quality Improvements

1. **Use dataclasses** or attrs for configuration objects
2. **Add type hints** throughout the codebase
3. **Implement proper interfaces** for components
4. **Add comprehensive docstrings**
5. **Use enum** for protocol types and states

This comprehensive review identifies critical bugs that could cause crashes, hangs, or data corruption, as well as design issues that affect maintainability and performance.