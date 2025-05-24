#!/usr/bin/env python3
"""
Critical fixes for ProxyBroker2 identified issues.
This file contains the corrected code for the most severe bugs.
"""

# Fix 1: api.py - Replace asyncio.ensure_future with asyncio.create_task
# Original problematic code from api.py line 332:
"""
BEFORE (BUGGY):
tasks = [asyncio.ensure_future(pr.get_proxies()) for pr in providers[:by]]

AFTER (FIXED):
tasks = [asyncio.create_task(pr.get_proxies()) for pr in providers[:by]]
"""

# Fix 2: server.py - Fix ProxyPool._import deadlock
"""
BEFORE (BUGGY):
async def _import(self, expected_scheme):
    while True:  # Infinite loop - can hang forever
        proxy = await self._proxies.get()
        self._proxies.task_done()
        if not proxy:
            raise NoProxyError('No more available proxies')
        elif expected_scheme not in proxy.schemes:
            self.put(proxy)  # Can cause infinite recycling
        else:
            return proxy

AFTER (FIXED):
"""
import asyncio
from .errors import NoProxyError, ProxyTimeoutError

async def _import_fixed(self, expected_scheme, max_retries=10, timeout=30):
    """Import proxy with deadlock protection."""
    start_time = time.time()
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Add timeout to prevent hanging forever
            proxy = await asyncio.wait_for(
                self._proxies.get(), 
                timeout=timeout
            )
            self._proxies.task_done()
            
            if not proxy:
                raise NoProxyError('No more available proxies')
            elif expected_scheme not in proxy.schemes:
                self.put(proxy)
                retry_count += 1
                
                # Prevent infinite recycling
                if time.time() - start_time > timeout:
                    raise ProxyTimeoutError('Timeout waiting for suitable proxy')
                    
                # Add small delay to prevent tight loop
                await asyncio.sleep(0.1)
            else:
                return proxy
                
        except asyncio.TimeoutError:
            raise ProxyTimeoutError('Timeout waiting for proxy from queue')
    
    raise NoProxyError(f'No suitable proxy found after {max_retries} retries')


# Fix 3: server.py - Fix heap corruption in ProxyPool.remove
"""
BEFORE (BUGGY):
def remove(self, host, port):
    for proxy in self._newcomers:
        if proxy.host == host and proxy.port == port:
            chosen = proxy
            self._newcomers.remove(proxy)
            break
    else:
        for priority, proxy in self._pool:
            if proxy.host == host and proxy.port == port:
                chosen = proxy
                self._pool.remove((proxy.priority, proxy))  # BREAKS HEAP INVARIANT
                break
    return chosen

AFTER (FIXED):
"""
import heapq

def remove_fixed(self, host, port):
    """Remove proxy without corrupting heap structure."""
    chosen = None
    
    # Check newcomers first
    for i, proxy in enumerate(self._newcomers):
        if proxy.host == host and proxy.port == port:
            chosen = self._newcomers.pop(i)
            return chosen
    
    # For main pool, we need to rebuild heap to maintain invariant
    if self._pool:
        # Extract all items
        temp_items = []
        target_item = None
        
        while self._pool:
            item = heapq.heappop(self._pool)
            priority, proxy = item
            if proxy.host == host and proxy.port == port and not target_item:
                target_item = item
                chosen = proxy
            else:
                temp_items.append(item)
        
        # Rebuild heap without the target item
        for item in temp_items:
            heapq.heappush(self._pool, item)
    
    return chosen


# Fix 4: server.py - Fix proxy.priority attribute issue
"""
BEFORE (BUGGY):
heapq.heappush(self._pool, (proxy.priority, proxy))  # AttributeError risk

AFTER (FIXED):
"""
def put_fixed(self, proxy):
    """Put proxy in pool with correct priority calculation."""
    is_exceed_time = (proxy.error_rate > self._max_error_rate) or (
        proxy.avg_resp_time > self._max_resp_time
    )
    
    if proxy.stat['requests'] < self._min_req_proxy:
        self._newcomers.append(proxy)
    elif proxy.stat['requests'] >= self._min_req_proxy and is_exceed_time:
        log.debug('%s:%d removed from proxy pool' % (proxy.host, proxy.port))
    else:
        # Use avg_resp_time as priority (lower is better)
        priority = getattr(proxy, 'avg_resp_time', float('inf'))
        heapq.heappush(self._pool, (priority, proxy))

    log.debug('%s:%d stat: %s' % (proxy.host, proxy.port, proxy.stat))


# Fix 5: server.py - Fix non-deterministic protocol selection
"""
BEFORE (BUGGY):
def _choice_proto(self, proxy, scheme):
    if scheme == 'HTTP':
        if self._prefer_connect and ('CONNECT:80' in proxy.types):
            proto = 'CONNECT:80'
        else:
            relevant = {
                'HTTP',
                'CONNECT:80', 
                'SOCKS4',
                'SOCKS5',
            } & proxy.types.keys()
            proto = relevant.pop()  # Non-deterministic!
    else:  # HTTPS
        relevant = {'HTTPS', 'SOCKS4', 'SOCKS5'} & proxy.types.keys()
        proto = relevant.pop()  # Non-deterministic!
    return proto

AFTER (FIXED):
"""
def _choice_proto_fixed(self, proxy, scheme):
    """Choose protocol with deterministic priority."""
    if scheme == 'HTTP':
        if self._prefer_connect and ('CONNECT:80' in proxy.types):
            return 'CONNECT:80'
        else:
            # Prioritized order for HTTP
            preferred_order = ['HTTP', 'CONNECT:80', 'SOCKS5', 'SOCKS4']
            for proto in preferred_order:
                if proto in proxy.types:
                    return proto
    else:  # HTTPS
        # Prioritized order for HTTPS  
        preferred_order = ['HTTPS', 'SOCKS5', 'SOCKS4']
        for proto in preferred_order:
            if proto in proxy.types:
                return proto
    
    # Fallback - should not happen
    available = set(proxy.types.keys())
    if available:
        return list(available)[0]  # At least deterministic
    
    raise ValueError(f'No suitable protocol found for {scheme}')


# Fix 6: api.py - Better error handling in _handle
"""
BEFORE (BUGGY):
async def _handle(self, proxy, check=False):
    try:
        proxy = await Proxy.create(
            *proxy,
            timeout=self._timeout,
            resolver=self._resolver,
            verify_ssl=self._verify_ssl,
            loop=self._loop,
        )
    except (ResolveError, ValueError):
        return  # Silent failure

AFTER (FIXED):
"""

async def _handle_fixed(self, proxy, check=False):
    """Handle proxy with proper error logging."""
    try:
        proxy = await Proxy.create(
            *proxy,
            timeout=self._timeout,
            resolver=self._resolver,
            verify_ssl=self._verify_ssl,
            loop=self._loop,
        )
    except ResolveError as e:
        log.debug(f'Failed to resolve proxy {proxy}: {e}')
        return
    except ValueError as e:
        log.debug(f'Invalid proxy data {proxy}: {e}')
        return
    except Exception as e:
        log.error(f'Unexpected error handling proxy {proxy}: {e}')
        return

    if not self._is_unique(proxy) or not self._geo_passed(proxy):
        return

    if check:
        await self._push_to_check(proxy)
    else:
        self._push_to_result(proxy)


# Fix 7: api.py - Better task callback error handling
"""
BEFORE (BUGGY):
def _task_done(proxy, f):
    self._on_check.task_done()
    if not self._on_check.empty():
        self._on_check.get_nowait()
    try:
        if f.result():  # Can raise various exceptions
            self._push_to_result(proxy)
    except asyncio.CancelledError:
        pass  # Only catches CancelledError

AFTER (FIXED):
"""
def _task_done_fixed(proxy, f):
    """Task completion callback with comprehensive error handling."""
    try:
        self._on_check.task_done()
        if not self._on_check.empty():
            self._on_check.get_nowait()
        
        try:
            result = f.result()
            if result:
                self._push_to_result(proxy)
        except asyncio.CancelledError:
            log.debug(f'Task cancelled for proxy {proxy}')
        except Exception as e:
            log.error(f'Task failed for proxy {proxy}: {e}')
            
    except Exception as e:
        log.error(f'Error in task completion callback: {e}')


# Fix 8: Add proper signal handler cleanup
"""
BEFORE (MISSING):
# No cleanup for signal handlers

AFTER (FIXED):
"""
import signal

class BrokerFixed:
    def __init__(self, *args, stop_broker_on_sigint=True, **kwargs):
        # ... existing init code ...
        self._signal_handler_set = False
        
        if stop_broker_on_sigint:
            try:
                self._loop.add_signal_handler(signal.SIGINT, self.stop)
                self._signal_handler_set = True
            except NotImplementedError:
                pass
    
    def stop(self):
        """Stop with proper cleanup."""
        self._done()
        
        # Clean up signal handler
        if self._signal_handler_set:
            try:
                self._loop.remove_signal_handler(signal.SIGINT)
                self._signal_handler_set = False
            except (NotImplementedError, ValueError):
                pass
        
        if self._server:
            self._server.stop()
            self._server = None
        log.info('Stop!')


# Fix 9: Add input validation for server API
"""
BEFORE (MISSING):
# No validation

AFTER (FIXED):
"""
import re

def _validate_api_input(operation, params):
    """Validate API input parameters."""
    if operation == 'remove':
        # Validate host:port format
        if not re.match(r'^[a-zA-Z0-9.-]+:\d+$', params):
            raise ValueError(f'Invalid host:port format: {params}')
        
        host, port_str = params.split(':', 1)
        port = int(port_str)
        
        if not (1 <= port <= 65535):
            raise ValueError(f'Invalid port number: {port}')
            
        return host, port
        
    elif operation == 'history':
        # Validate query format
        if ':' not in params:
            raise ValueError(f'Invalid history query format: {params}')
            
        query_type, url = params.split(':', 1)
        if query_type not in ['url']:
            raise ValueError(f'Invalid query type: {query_type}')
            
        return query_type, url
    
    else:
        raise ValueError(f'Unknown operation: {operation}')


print("Critical fixes defined. Apply these changes to fix the most severe bugs.")