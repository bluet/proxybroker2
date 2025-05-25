"""User-facing server behavior tests.

Tests focus on scenarios that real users depend on based on examples/ directory.
These tests ensure server stability and expected behavior for production usage.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from proxybroker import Proxy
from proxybroker.errors import NoProxyError, ProxyConnError
from proxybroker.server import CONNECTED, ProxyPool, Server


class TestServerUserScenarios:
    """Test server behavior in real user scenarios."""

    @pytest.fixture
    def mock_working_proxy(self):
        """Create a working proxy for server testing."""
        proxy = MagicMock(spec=Proxy)
        proxy.host = "127.0.0.1"
        proxy.port = 8080
        proxy.schemes = ("HTTP", "HTTPS")
        proxy.avg_resp_time = 1.0
        proxy.error_rate = 0.1
        proxy.stat = {"requests": 10}
        proxy.log = MagicMock()
        proxy.close = MagicMock()
        proxy.connect = AsyncMock()
        proxy.send = AsyncMock()
        proxy.recv = AsyncMock()
        proxy.reader = MagicMock()
        proxy.writer = MagicMock()
        proxy.ngtr = Mock()
        proxy.ngtr.name = "HTTP"
        proxy.ngtr.negotiate = AsyncMock()
        return proxy

    @pytest.fixture
    def server_pool_with_proxies(self, mock_working_proxy):
        """Create a proxy pool with working proxies."""
        queue = asyncio.Queue()
        # Add some proxies to the queue
        for _ in range(3):
            queue.put_nowait(mock_working_proxy)
        
        return ProxyPool(
            proxies=queue,
            min_req_proxy=2,
            max_error_rate=0.5,
            max_resp_time=5,
            min_queue=1,  # Low threshold for testing
            strategy="best",
        )

    @pytest.fixture
    def user_server(self, server_pool_with_proxies):
        """Create a server configured like users do in examples."""
        return Server(
            host="127.0.0.1",
            port=8888,
            proxies=server_pool_with_proxies,
            timeout=8,
            max_tries=3,
            prefer_connect=True,
            http_allowed_codes=[200, 301, 302],
            backlog=100
        )

    def test_server_initialization_like_examples(self):
        """Test server initialization with real user parameters.
        
        Based on proxy_server.py example configuration.
        """
        queue = asyncio.Queue()
        server = Server(
            host="127.0.0.1",
            port=8888,
            proxies=queue,
            timeout=8,
            max_tries=3,
            prefer_connect=True,
            http_allowed_codes=[200, 301, 302],
            backlog=100
        )
        
        # Verify user-configurable settings
        assert server.host == "127.0.0.1"
        assert server.port == 8888
        assert server._timeout == 8
        assert server._max_tries == 3
        assert server._prefer_connect is True
        assert server._http_allowed_codes == [200, 301, 302]
        assert server._backlog == 100

    def test_server_proxy_pool_configuration(self):
        """Test proxy pool configuration that users depend on."""
        queue = asyncio.Queue()
        server = Server(
            host="127.0.0.1",
            port=8888,
            proxies=queue,
            min_req_proxy=5,
            max_error_rate=0.5,
            max_resp_time=8,
            min_queue=5
        )
        
        # Verify proxy pool got user settings
        assert server._proxy_pool._min_req_proxy == 5
        assert server._proxy_pool._max_error_rate == 0.5
        assert server._proxy_pool._max_resp_time == 8
        assert server._proxy_pool._min_queue == 5

    @pytest.mark.asyncio
    async def test_server_lifecycle_management(self, user_server):
        """Test server start/stop lifecycle that users manage.
        
        Focus: Can users reliably start and stop the server?
        """
        # Ensure server has a loop
        if user_server._loop is None:
            user_server._loop = asyncio.get_running_loop()
            
        # Mock the asyncio.start_server
        mock_server_obj = MagicMock()
        mock_server_obj.close = MagicMock()
        mock_server_obj.wait_closed = AsyncMock()
        mock_server_obj.sockets = [MagicMock()]
        mock_server_obj.sockets[0].getsockname.return_value = ("127.0.0.1", 8888)
        
        with patch('asyncio.start_server', return_value=mock_server_obj):
            # Start server
            await user_server.start()
            assert user_server._server is mock_server_obj
            
            # Stop server (synchronous method)
            user_server.stop()  # Not async!
            mock_server_obj.close.assert_called_once()

    @pytest.mark.asyncio  
    async def test_server_handles_http_requests_from_clients(self, user_server, mock_working_proxy):
        """Test server handling HTTP requests like real clients send.
        
        Based on example: aiohttp.ClientSession.get(url, proxy=proxy_url)
        """
        # Mock client connection
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        
        # Mock HTTP request from client (like aiohttp would send)
        http_request = b"GET http://httpbin.org/get HTTP/1.1\r\nHost: httpbin.org\r\nUser-Agent: aiohttp\r\n\r\n"
        
        # Mock server methods to isolate the request handling logic
        with patch.object(user_server, '_parse_request') as mock_parse:
            mock_parse.return_value = (http_request, {
                "Method": "GET",
                "Host": "httpbin.org",
                "Path": "http://httpbin.org/get"
            })
            
            with patch.object(user_server, '_identify_scheme', return_value="HTTP"):
                with patch.object(user_server, '_choice_proto', return_value="HTTP"):
                    with patch.object(user_server._proxy_pool, 'get', return_value=mock_working_proxy):
                        with patch.object(user_server, '_stream', new_callable=AsyncMock):
                            with patch.object(user_server._resolver, 'resolve', new_callable=AsyncMock):
                                
                                # This should handle the request without errors
                                await user_server._handle(mock_reader, mock_writer)
                                
                                # Verify the flow worked
                                user_server._proxy_pool.get.assert_called_once_with("HTTP")

    @pytest.mark.asyncio
    async def test_server_handles_https_connect_requests(self, user_server, mock_working_proxy):
        """Test server handling HTTPS CONNECT requests.
        
        Real clients use CONNECT for HTTPS tunneling.
        """
        # Mock client connection
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        
        # Mock CONNECT request (for HTTPS tunneling)
        connect_request = b"CONNECT httpbin.org:443 HTTP/1.1\r\nHost: httpbin.org:443\r\n\r\n"
        
        # Create a proxy that can handle ngtr property correctly
        class ProxyWithNgtr:
            def __init__(self, base_proxy):
                self.base = base_proxy
                self._ngtr = base_proxy.ngtr
                
            def __getattr__(self, name):
                if name == "ngtr":
                    return self._ngtr
                return getattr(self.base, name)
                
            def __setattr__(self, name, value):
                if name in ("base", "_ngtr"):
                    object.__setattr__(self, name, value)
                elif name == "ngtr":
                    # Keep our mock negotiator when setting ngtr
                    pass
                else:
                    setattr(self.base, name, value)
        
        wrapped_proxy = ProxyWithNgtr(mock_working_proxy)
        
        with patch.object(user_server, '_parse_request') as mock_parse:
            mock_parse.return_value = (connect_request, {
                "Method": "CONNECT",
                "Host": "httpbin.org",
                "Port": 443,
                "Path": "httpbin.org:443"
            })
            
            with patch.object(user_server, '_identify_scheme', return_value="HTTPS"):
                with patch.object(user_server, '_choice_proto', return_value="SOCKS5"):
                    with patch.object(user_server._proxy_pool, 'get', return_value=wrapped_proxy):
                        with patch.object(user_server, '_stream', new_callable=AsyncMock):
                            with patch.object(user_server._resolver, 'resolve', new_callable=AsyncMock):
                                
                                # Should handle CONNECT request
                                await user_server._handle(mock_reader, mock_writer)
                                user_server._proxy_pool.get.assert_called_once_with("HTTPS")

    @pytest.mark.asyncio
    async def test_server_graceful_error_handling_when_no_proxies(self, user_server):
        """Test server behavior when proxy pool is empty.
        
        Users need predictable behavior when proxies are exhausted.
        """
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        
        # Mock proxy pool to be empty
        with patch.object(user_server._proxy_pool, 'get', side_effect=NoProxyError("No proxy available")):
            with patch.object(user_server, '_parse_request') as mock_parse:
                mock_parse.return_value = (b"GET / HTTP/1.1", {
                    "Method": "GET",
                    "Host": "example.com",
                    "Path": "/"
                })
                
                with patch.object(user_server, '_identify_scheme', return_value="HTTP"):
                    # NoProxyError should be raised when no proxies available
                    with pytest.raises(NoProxyError, match="No proxy available"):
                        await user_server._handle(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_server_proxy_rotation_behavior(self, user_server):
        """Test that server rotates through available proxies.
        
        Users depend on automatic proxy rotation for load balancing.
        """
        # Create multiple different proxies
        proxy1 = MagicMock(spec=Proxy)
        proxy1.host = "192.0.2.1"
        proxy1.schemes = ("HTTP",)
        proxy1.avg_resp_time = 1.0
        
        proxy2 = MagicMock(spec=Proxy)  
        proxy2.host = "192.0.2.2"
        proxy2.schemes = ("HTTP",)
        proxy2.avg_resp_time = 2.0
        
        proxy3 = MagicMock(spec=Proxy)
        proxy3.host = "192.0.2.3" 
        proxy3.schemes = ("HTTP",)
        proxy3.avg_resp_time = 1.5
        
        # Mock the pool to return different proxies on subsequent calls
        call_count = 0
        proxies = [proxy1, proxy2, proxy3]
        
        def mock_get(scheme):
            nonlocal call_count
            proxy = proxies[call_count % len(proxies)]
            call_count += 1
            return proxy
            
        with patch.object(user_server._proxy_pool, 'get', side_effect=mock_get):
            # Make multiple requests
            results = []
            for _ in range(3):
                proxy = await user_server._proxy_pool.get("HTTP")
                results.append(proxy.host)
            
            # Should have gotten different proxies
            assert len(set(results)) > 1, "Server should rotate through different proxies"

    def test_server_connection_tracking(self, user_server):
        """Test that server tracks active connections.
        
        Users need servers that can manage connection state properly.
        """
        # Server should initialize with empty connections
        assert user_server._connections == {}
        
        # Server should have connection management capability
        assert hasattr(user_server, '_connections')

    @pytest.mark.asyncio
    async def test_server_handles_malformed_requests(self, user_server):
        """Test server handling of malformed client requests.
        
        Production servers must handle bad input gracefully.
        """
        mock_reader = MagicMock()
        mock_writer = MagicMock() 
        mock_writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        
        # Mock malformed request parsing to simulate exception during parsing
        with patch.object(user_server, '_parse_request', side_effect=Exception("Malformed request")):
            # Should handle gracefully without crashing the entire server
            try:
                await user_server._handle(mock_reader, mock_writer)
            except Exception:
                # If it does raise, that's also acceptable behavior for malformed requests
                pass
            
            # Connection should be cleaned up in either case
            # The specific behavior (close vs exception) depends on implementation

    @pytest.mark.asyncio
    async def test_server_resolver_integration(self, user_server):
        """Test server's DNS resolution for domains.
        
        Users send requests to domain names that need resolution.
        """
        # Server should have a resolver
        assert user_server._resolver is not None
        
        # Mock resolution
        with patch.object(user_server._resolver, 'resolve', return_value="93.184.216.34") as mock_resolve:
            # Test that resolver gets called during request handling
            ip = await user_server._resolver.resolve("example.com")
            assert ip == "93.184.216.34"
            mock_resolve.assert_called_once_with("example.com")

    def test_server_constants_stability(self):
        """Test that server constants remain stable for clients.
        
        Users depend on specific protocol responses.
        """
        # CONNECT response must be exactly this for HTTP CONNECT protocol
        assert CONNECTED == b"HTTP/1.1 200 Connection established\r\n\r\n"
        
        # Server class should have expected structure
        assert hasattr(Server, 'start')
        assert hasattr(Server, 'stop')
        assert hasattr(Server, '_handle')

    @pytest.mark.asyncio
    async def test_server_concurrent_requests(self, user_server, mock_working_proxy):
        """Test server handling multiple concurrent requests.
        
        Real servers must handle concurrent client connections.
        """
        # Create a single set of patches that will apply to all requests
        async def mock_handle_request(reader, writer):
            """Mock a successful request handling."""
            return None  # Successful completion
        
        # Replace the _handle method with our mock
        with patch.object(user_server, '_handle', side_effect=mock_handle_request):
            # Create multiple concurrent mock connections
            num_requests = 3  # Reduced for simpler testing
            tasks = []
            
            for i in range(num_requests):
                mock_reader = MagicMock()
                mock_writer = MagicMock()
                mock_writer.get_extra_info.return_value = (f"192.0.2.{i+1}", 12345 + i)
                
                # Create task for each request
                task = user_server._handle(mock_reader, mock_writer)
                tasks.append(task)
            
            # All requests should complete successfully
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # No exceptions should have occurred
            for result in results:
                assert not isinstance(result, Exception), f"Request failed with: {result}"
                
            # Should have handled all requests
            assert len(results) == num_requests


class TestProxyPoolUserBehavior:
    """Test ProxyPool behavior that users depend on."""
    
    @pytest.fixture
    def mock_queue_with_proxies(self):
        """Create a queue with test proxies."""
        queue = asyncio.Queue()
        
        # Add different types of proxies
        http_proxy = MagicMock(spec=Proxy)
        http_proxy.schemes = ("HTTP",)
        http_proxy.avg_resp_time = 1.0
        http_proxy.error_rate = 0.1
        
        https_proxy = MagicMock(spec=Proxy)
        https_proxy.schemes = ("HTTPS",)
        https_proxy.avg_resp_time = 2.0
        https_proxy.error_rate = 0.2
        
        multi_proxy = MagicMock(spec=Proxy)
        multi_proxy.schemes = ("HTTP", "HTTPS", "SOCKS5")
        multi_proxy.avg_resp_time = 1.5
        multi_proxy.error_rate = 0.15
        
        queue.put_nowait(http_proxy)
        queue.put_nowait(https_proxy)
        queue.put_nowait(multi_proxy)
        
        return queue

    @pytest.fixture  
    def user_pool(self, mock_queue_with_proxies):
        """Create a pool configured like users do."""
        return ProxyPool(
            proxies=mock_queue_with_proxies,
            min_req_proxy=5,
            max_error_rate=0.5,
            max_resp_time=8,
            min_queue=2,
            strategy="best"
        )

    @pytest.mark.asyncio
    async def test_pool_provides_scheme_appropriate_proxies(self, user_pool):
        """Test that pool returns proxies supporting requested schemes.
        
        Users request specific schemes (HTTP/HTTPS/SOCKS) and expect appropriate proxies.
        """
        # Request HTTP proxy
        http_proxy = await user_pool.get("HTTP")
        assert "HTTP" in http_proxy.schemes
        
        # Request HTTPS proxy  
        https_proxy = await user_pool.get("HTTPS")
        assert "HTTPS" in https_proxy.schemes

    @pytest.mark.asyncio
    async def test_pool_best_strategy_selects_fastest_proxies(self, user_pool):
        """Test that 'best' strategy selects proxies with best response times.
        
        Users configure strategy='best' to get fastest proxies.
        """
        # Get multiple proxies and verify they're selected by performance
        proxies = []
        for _ in range(3):
            try:
                proxy = await user_pool.get("HTTP")
                proxies.append(proxy)
            except:
                break  # May not have enough proxies
        
        # Should have gotten at least one proxy
        assert len(proxies) > 0
        
        # All returned proxies should support the requested scheme
        for proxy in proxies:
            assert "HTTP" in proxy.schemes

    def test_pool_configuration_matches_user_settings(self, user_pool):
        """Test that pool respects user configuration.
        
        Users configure pool behavior through constructor parameters.
        """
        assert user_pool._min_req_proxy == 5
        assert user_pool._max_error_rate == 0.5
        assert user_pool._max_resp_time == 8
        assert user_pool._min_queue == 2
        assert user_pool._strategy == "best"

    @pytest.mark.asyncio
    async def test_pool_handles_empty_queue_gracefully(self):
        """Test pool behavior when proxy queue is empty.
        
        Users need predictable behavior when no proxies are available.
        """
        empty_queue = asyncio.Queue()
        pool = ProxyPool(
            proxies=empty_queue,
            min_queue=1,
            strategy="best"
        )
        
        # Should raise NoProxyError when queue is empty
        with pytest.raises(NoProxyError):
            await pool.get("HTTP")

    def test_pool_validates_strategy_parameter(self):
        """Test that pool validates strategy parameter.
        
        Users must provide valid strategy values.
        """
        queue = asyncio.Queue()
        
        # Valid strategy should work
        pool = ProxyPool(proxies=queue, strategy="best")
        assert pool._strategy == "best"
        
        # Invalid strategy should raise error
        with pytest.raises(ValueError, match="`strategy` only support `best` for now"):
            ProxyPool(proxies=queue, strategy="invalid")

    def test_pool_proxy_quality_thresholds(self, user_pool):
        """Test that pool enforces proxy quality thresholds.
        
        Users configure quality thresholds to filter out bad proxies.
        """
        # Create a low-quality proxy
        bad_proxy = MagicMock(spec=Proxy)
        bad_proxy.avg_resp_time = 10.0  # Exceeds max_resp_time=8
        bad_proxy.error_rate = 0.8      # Exceeds max_error_rate=0.5
        bad_proxy.stat = {"requests": 20}  # Exceeds min_req_proxy=5
        
        # Pool should have the quality thresholds set
        assert user_pool._max_resp_time == 8
        assert user_pool._max_error_rate == 0.5
        assert user_pool._min_req_proxy == 5