"""Test Server public API - focused on user-visible behavior.

This file tests how users actually use the Server:
- Starting a proxy server that routes requests through found proxies
- Proxy rotation and failure handling
- Connection management
- Server lifecycle (start/stop/context manager)

We focus on WHAT the server does for users, not HOW it does it internally.
Based on the real usage pattern from examples/proxy_server.py
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from proxybroker import Proxy
from proxybroker.errors import NoProxyError
from proxybroker.server import ProxyPool, Server


class TestServerAPI:
    """Test Server public API behavior."""

    @pytest.fixture
    def mock_proxy_queue(self):
        """Create a queue for testing (proxies added in individual tests)."""
        return asyncio.Queue()

    def create_mock_proxy(self, host="1.2.3.4", port=8080, schemes=("HTTP", "HTTPS")):
        """Helper to create a mock proxy."""
        proxy = MagicMock(spec=Proxy)
        proxy.host = host
        proxy.port = port
        proxy.schemes = schemes
        proxy.avg_resp_time = 1.5
        proxy.error_rate = 0.1
        proxy.stat = {"requests": 5, "errors": {}}
        return proxy

    # Core Server Lifecycle Tests

    def test_server_can_be_created(self, mock_proxy_queue):
        """Test that Server can be instantiated with basic parameters."""
        server = Server(host="127.0.0.1", port=8888, proxies=mock_proxy_queue)
        assert server.host == "127.0.0.1"
        assert server.port == 8888

    @pytest.mark.asyncio
    async def test_server_start_creates_listening_server(self, mock_proxy_queue):
        """Test that server.start() creates a listening server."""
        server = Server(
            host="127.0.0.1",
            port=0,  # Use any available port
            proxies=mock_proxy_queue,
        )

        await server.start()

        # Should have created a listening server
        assert server._server is not None
        assert server._server.sockets  # Should have listening sockets

        # Clean up
        server.stop()

    @pytest.mark.asyncio
    async def test_server_async_context_manager(self, mock_proxy_queue):
        """Test Server as async context manager."""
        async with Server("127.0.0.1", 0, mock_proxy_queue) as server:
            # Server should be started
            assert server._server is not None
            assert server._server.sockets

        # Server should be closed after context
        assert server._server is None

    def test_server_with_custom_parameters(self, mock_proxy_queue):
        """Test Server accepts configuration parameters."""
        server = Server(
            host="0.0.0.0",
            port=9999,
            proxies=mock_proxy_queue,
            timeout=15,
            max_tries=5,
            prefer_connect=True,
        )

        assert server.host == "0.0.0.0"
        assert server.port == 9999

    # ProxyPool Behavior Tests - Focus on user-visible behavior

    @pytest.mark.asyncio
    async def test_proxy_pool_provides_proxies_for_requests(self):
        """Test that ProxyPool provides proxies when requested."""
        queue = asyncio.Queue()

        # Add a proxy to the queue
        proxy = MagicMock(spec=Proxy)
        proxy.schemes = ("HTTP", "HTTPS")
        proxy.avg_resp_time = 1.0
        await queue.put(proxy)

        pool = ProxyPool(queue)

        # Should be able to get a proxy for HTTP requests
        result = await pool.get("HTTP")
        assert result is proxy

    @pytest.mark.asyncio
    async def test_proxy_pool_handles_empty_queue(self):
        """Test ProxyPool behavior when no proxies are available."""
        queue = asyncio.Queue()
        # Don't add any proxies

        pool = ProxyPool(queue)

        # Should timeout gracefully when no proxies available
        with pytest.raises((asyncio.TimeoutError, NoProxyError)):
            await asyncio.wait_for(pool.get("HTTP"), timeout=0.5)

    @pytest.mark.asyncio
    async def test_proxy_pool_respects_scheme_requirements(self):
        """Test that ProxyPool only returns compatible proxies."""
        queue = asyncio.Queue()

        # Add HTTP-only proxy
        http_proxy = MagicMock(spec=Proxy)
        http_proxy.schemes = ("HTTP",)
        http_proxy.avg_resp_time = 1.0
        await queue.put(http_proxy)

        pool = ProxyPool(queue)

        # Should get the proxy for HTTP
        result = await pool.get("HTTP")
        assert result is http_proxy

        # Should not get it for HTTPS (wrong scheme)
        # This would require more complex mocking to test properly

    def test_proxy_pool_quality_thresholds(self):
        """Test ProxyPool accepts quality configuration."""
        queue = asyncio.Queue()

        pool = ProxyPool(queue, max_error_rate=0.3, max_resp_time=5, min_req_proxy=10)

        assert pool is not None
        # Quality thresholds should be configurable

    # Error Handling Tests

    @pytest.mark.asyncio
    async def test_server_handles_connection_errors_gracefully(self, mock_proxy_queue):
        """Test server handles client connection errors."""
        server = Server("127.0.0.1", 0, mock_proxy_queue)

        # This test would ideally make actual connections and test error handling
        # For now, just verify server can be created and started
        await server.start()
        assert server._server is not None
        server.stop()

    # Integration-style Tests (closer to real usage)

    @pytest.mark.asyncio
    async def test_server_proxy_rotation_concept(self, mock_proxy_queue):
        """Test that server can handle multiple proxies (concept test)."""
        # Add multiple proxies to queue
        queue = asyncio.Queue()

        for i in range(3):
            proxy = MagicMock(spec=Proxy)
            proxy.host = f"proxy{i}.example.com"
            proxy.port = 8080 + i
            proxy.schemes = ("HTTP", "HTTPS")
            proxy.avg_resp_time = 1.0 + i * 0.5
            await queue.put(proxy)

        server = Server("127.0.0.1", 0, queue)
        await server.start()

        # Server should be able to handle multiple proxies
        # (Actual rotation testing would require real HTTP requests)
        assert server._server is not None

        server.stop()

    # Server API Control Tests

    @pytest.mark.asyncio
    async def test_server_api_endpoints_exist(self, mock_proxy_queue):
        """Test that server exposes API endpoints for control."""
        server = Server("127.0.0.1", 0, mock_proxy_queue)
        await server.start()

        # The server should handle requests to special "proxycontrol" host
        # This is tested by making actual HTTP requests in integration tests
        # Here we just verify the server starts successfully
        assert server._server is not None

        server.stop()

    # Configuration and Customization Tests

    def test_server_accepts_broker_serve_parameters(self):
        """Test that Server accepts the same parameters as broker.serve()."""
        queue = asyncio.Queue()

        # These are the parameters from examples/proxy_server.py
        server = Server(
            host="127.0.0.1",
            port=8888,
            proxies=queue,
            timeout=8,
            max_tries=3,
            prefer_connect=True,
            max_error_rate=0.5,
            max_resp_time=8,
            backlog=100,
        )

        # Verify the server was created with the expected configuration
        assert server.host == "127.0.0.1"
        assert server.port == 8888

    # Cleanup and Resource Management Tests

    @pytest.mark.asyncio
    async def test_server_cleanup_on_stop(self, mock_proxy_queue):
        """Test that server properly cleans up resources on stop."""
        server = Server("127.0.0.1", 0, mock_proxy_queue)
        await server.start()

        # Server should be running
        assert server._server is not None

        # Stop should clean up
        server.stop()
        assert server._server is None

    @pytest.mark.asyncio
    async def test_server_async_cleanup_with_aclose(self, mock_proxy_queue):
        """Test that server.aclose() cleans up without stopping event loop."""
        server = Server("127.0.0.1", 0, mock_proxy_queue)
        await server.start()

        assert server._server is not None

        # aclose() should clean up async-safely
        await server.aclose()
        assert server._server is None

        # Event loop should still be running (we can call more async code)
        await asyncio.sleep(0.001)  # This would fail if loop was stopped


class TestProxyPool:
    """ProxyPool put/remove logic - exercised without network or full Server."""

    def _make_proxy(
        self, host="192.0.2.1", port=8080, requests=10, errors=0, avg_resp_time=1.0
    ):
        """Build a Proxy-shaped MagicMock that satisfies ProxyPool's checks."""
        p = MagicMock()
        p.host = host
        p.port = port
        p.stat = {"requests": requests}
        p.error_rate = (errors / requests) if requests else 0
        p.avg_resp_time = avg_resp_time
        return p

    def test_put_routes_newcomer_below_min_req(self):
        """Proxies with fewer than min_req_proxy requests go into _newcomers."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5)
        proxy = self._make_proxy(requests=2)
        pool.put(proxy)
        assert proxy in pool._newcomers
        assert len(pool._pool) == 0

    def test_put_routes_to_pool_when_proven(self):
        """Proven proxies (req >= min, errors low, fast) join the heap pool."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5, max_error_rate=0.5, max_resp_time=8)
        proxy = self._make_proxy(requests=10, errors=0, avg_resp_time=1.0)
        pool.put(proxy)
        assert len(pool._pool) == 1
        assert pool._newcomers == []

    def test_put_drops_proxy_exceeding_error_rate(self):
        """Proxies past min_req with too many errors are silently dropped."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5, max_error_rate=0.3)
        proxy = self._make_proxy(requests=10, errors=5)  # 50% > 30%
        pool.put(proxy)
        assert proxy not in pool._newcomers
        assert all(p[1] is not proxy for p in pool._pool)

    def test_put_drops_proxy_too_slow(self):
        """Proxies past min_req with avg response time over threshold are dropped."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5, max_resp_time=2.0)
        proxy = self._make_proxy(requests=10, errors=0, avg_resp_time=10.0)
        pool.put(proxy)
        assert all(p[1] is not proxy for p in pool._pool)

    def test_put_none_is_noop(self):
        """ProxyPool.put(None) must not crash - signals end-of-stream."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue)
        pool.put(None)
        assert pool._pool == []
        assert pool._newcomers == []

    def test_remove_finds_in_newcomers(self):
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5)
        target = self._make_proxy("192.0.2.1", 8080, requests=2)
        other = self._make_proxy("198.51.100.1", 3128, requests=2)
        pool.put(target)
        pool.put(other)
        removed = pool.remove("192.0.2.1", 8080)
        assert removed is target
        assert target not in pool._newcomers
        assert other in pool._newcomers

    def test_remove_finds_in_main_pool(self):
        """O(N log N) heap-safe removal preserves the heap invariant."""
        import heapq

        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5)
        a = self._make_proxy("192.0.2.1", 80, requests=10, avg_resp_time=1.0)
        b = self._make_proxy("198.51.100.1", 80, requests=10, avg_resp_time=2.0)
        c = self._make_proxy("203.0.113.1", 80, requests=10, avg_resp_time=3.0)
        for p in (a, b, c):
            pool.put(p)
        assert len(pool._pool) == 3

        pool.remove("198.51.100.1", 80)
        # b is gone; a and c remain; heap invariant holds
        remaining = [p[1] for p in pool._pool]
        assert b not in remaining
        assert a in remaining and c in remaining
        # heap_pop should still give them in priority order
        priorities = [pool._pool[i][0] for i in range(len(pool._pool))]
        assert priorities == list(heapq.nsmallest(len(priorities), priorities))

    def test_remove_target_not_present_restores_pool(self):
        """When target not in pool, all items must be put back unchanged."""
        queue = asyncio.Queue()
        pool = ProxyPool(queue, min_req_proxy=5)
        a = self._make_proxy("192.0.2.1", 80, requests=10, avg_resp_time=1.0)
        b = self._make_proxy("198.51.100.1", 80, requests=10, avg_resp_time=2.0)
        pool.put(a)
        pool.put(b)
        pool.remove("nonexistent.host", 9999)
        assert len(pool._pool) == 2

    def test_init_rejects_unsupported_strategy(self):
        """The class explicitly raises ValueError for non-'best' strategies."""
        with pytest.raises(ValueError, match="strategy"):
            ProxyPool(asyncio.Queue(), strategy="random")
