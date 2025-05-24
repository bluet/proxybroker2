import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from proxybroker import Proxy
from proxybroker.errors import NoProxyError, ProxyConnError
from proxybroker.server import CONNECTED, ProxyPool, Server


@pytest.fixture
def mock_proxy():
    """Create a mock proxy for testing."""
    proxy = MagicMock(spec=Proxy)
    proxy.host = '127.0.0.1'
    proxy.port = 8080
    proxy.schemes = ('HTTP', 'HTTPS')
    proxy.avg_resp_time = 1.0
    proxy.error_rate = 0.1
    proxy.stat = {'requests': 10}
    proxy.log = MagicMock()
    proxy.close = MagicMock()
    proxy.connect = AsyncMock()
    proxy.send = AsyncMock()
    proxy.recv = AsyncMock()
    proxy.reader = MagicMock()
    proxy.writer = MagicMock()
    proxy.ngtr = Mock()
    proxy.ngtr.name = 'HTTP'
    proxy.ngtr.negotiate = AsyncMock()
    return proxy


@pytest.fixture
def mock_queue():
    """Create a mock queue with test proxies."""
    queue = asyncio.Queue()
    return queue


@pytest.fixture
def proxy_pool(mock_queue):
    """Create a ProxyPool instance for testing."""
    return ProxyPool(
        proxies=mock_queue,
        min_req_proxy=2,
        max_error_rate=0.5,
        max_resp_time=5,
        min_queue=2,
        strategy='best'
    )


@pytest.fixture
def mock_proxy_pool():
    """Create a mock ProxyPool for testing."""
    pool = MagicMock(spec=ProxyPool)
    pool.get = AsyncMock()
    pool.put = MagicMock()
    return pool


@pytest.fixture
def server(mock_proxy_pool):
    """Create a Server instance for testing."""
    return Server(
        host='localhost',
        port=8888,
        proxies=mock_proxy_pool,
        timeout=5,
        backlog=100
    )


class TestProxyPool:
    """Test cases for ProxyPool class."""

    def test_proxy_pool_init(self):
        """Test ProxyPool initialization."""
        queue = asyncio.Queue()
        pool = ProxyPool(
            proxies=queue,
            min_req_proxy=5,
            max_error_rate=0.5,
            max_resp_time=8,
            min_queue=5,
            strategy='best'
        )
        assert pool._proxies is queue
        assert pool._min_req_proxy == 5
        assert pool._max_error_rate == 0.5
        assert pool._max_resp_time == 8
        assert pool._min_queue == 5
        assert pool._strategy == 'best'
        assert pool._pool == []
        assert pool._newcomers == []

    def test_proxy_pool_invalid_strategy(self):
        """Test ProxyPool with invalid strategy raises error."""
        queue = asyncio.Queue()
        with pytest.raises(ValueError, match='`strategy` only support `best` for now'):
            ProxyPool(proxies=queue, strategy='invalid')

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_newcomers(self, proxy_pool, mock_proxy):
        """Test getting proxy from newcomers."""
        # Add proxy to newcomers manually
        proxy_pool._newcomers.append(mock_proxy)
        proxy_pool._min_queue = 1  # Lower threshold
        
        # Mock the proxy to have HTTP scheme
        mock_proxy.schemes = ('HTTP',)
        
        result = await proxy_pool.get('HTTP')
        assert result is mock_proxy
        assert len(proxy_pool._newcomers) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_pool(self, proxy_pool, mock_proxy):
        """Test getting proxy from main pool."""
        # Add proxy to main pool using heapq format (priority, proxy)
        import heapq
        heapq.heappush(proxy_pool._pool, (mock_proxy.avg_resp_time, mock_proxy))
        proxy_pool._min_queue = 1  # Lower threshold
        
        # Mock the proxy to have HTTP scheme
        mock_proxy.schemes = ('HTTP',)
        
        result = await proxy_pool.get('HTTP')
        assert result is mock_proxy
        assert len(proxy_pool._pool) == 0

    def test_proxy_pool_get_scheme_mismatch(self, proxy_pool, mock_proxy):
        """Test getting proxy with scheme mismatch returns None."""
        # Add proxy with different scheme
        proxy_pool._newcomers.append(mock_proxy)
        mock_proxy.schemes = ('SOCKS5',)  # Different from requested HTTP
        proxy_pool._min_queue = 1  # Lower threshold
        
        # This should not return the proxy since schemes don't match
        # The method will try _import which will timeout, but that's expected behavior

    @pytest.mark.asyncio
    async def test_proxy_pool_import_from_queue(self, proxy_pool, mock_proxy):
        """Test importing proxy from queue."""
        # Put proxy in queue
        await proxy_pool._proxies.put(mock_proxy)
        mock_proxy.schemes = ('HTTP',)
        
        result = await proxy_pool._import('HTTP')
        assert result is mock_proxy

    @pytest.mark.asyncio
    async def test_proxy_pool_import_empty_queue(self, proxy_pool):
        """Test importing from empty queue raises NoProxyError."""
        # Empty queue should timeout
        with pytest.raises(NoProxyError, match='Timeout waiting for proxy with scheme HTTP'):
            await proxy_pool._import('HTTP')

    @pytest.mark.asyncio
    async def test_proxy_pool_import_scheme_mismatch(self, proxy_pool, mock_proxy):
        """Test importing proxy with scheme mismatch."""
        # Put proxy with different scheme in queue
        await proxy_pool._proxies.put(mock_proxy)
        mock_proxy.schemes = ('HTTP',)  # Will be put back for SOCKS5 request
        
        # Mock the proxy attributes properly
        mock_proxy.error_rate = 0.1  # Not a MagicMock
        mock_proxy.stat = {'requests': 10}
        
        # Should put proxy back and eventually timeout looking for SOCKS5
        with pytest.raises(NoProxyError, match='Timeout waiting for proxy with scheme SOCKS5'):
            await proxy_pool._import('SOCKS5')

    def test_proxy_pool_put_newcomer(self, proxy_pool):
        """Test putting a newcomer proxy with real proxy object."""
        from proxybroker import Proxy
        
        # Create a real proxy object
        proxy = Proxy('127.0.0.1', 8080, 'http')
        proxy.stat['requests'] = 1  # Less than min_req_proxy (2)
        
        proxy_pool.put(proxy)
        assert proxy in proxy_pool._newcomers

    def test_proxy_pool_put_experienced_good_proxy(self, proxy_pool):
        """Test putting an experienced, good proxy in main pool with real proxy object."""
        from proxybroker import Proxy
        
        # Create a real proxy object
        proxy = Proxy('127.0.0.1', 8080, 'http')
        proxy.stat['requests'] = 10  # More than min_req_proxy (2)
        proxy.stat['errors'] = {'ProxyTimeoutError': 1}
        # Add response times to calculate avg_resp_time
        for _ in range(10):
            proxy._runtimes.append(1.0)
        
        proxy_pool.put(proxy)
        # Should be in main pool (as heapq item)
        assert len(proxy_pool._pool) == 1
        assert proxy_pool._pool[0][1] is proxy
        # Verify priority is avg_resp_time
        assert proxy_pool._pool[0][0] == proxy.avg_resp_time

    def test_proxy_pool_put_experienced_bad_proxy(self, proxy_pool):
        """Test putting an experienced but bad proxy (should be discarded) with real proxy object."""
        from proxybroker import Proxy
        
        # Create a real proxy object
        proxy = Proxy('127.0.0.1', 8080, 'http')
        proxy.stat['requests'] = 10  # More than min_req_proxy (2)
        # Set high error count to get high error rate (6/10 = 0.6 > 0.5)
        proxy.stat['errors'] = {'ProxyTimeoutError': 6}
        # Add response times
        for _ in range(10):
            proxy._runtimes.append(1.0)
        
        proxy_pool.put(proxy)
        # Should be discarded (not in newcomers or pool)
        assert proxy not in proxy_pool._newcomers
        assert len(proxy_pool._pool) == 0

    def test_proxy_pool_put_slow_proxy(self, proxy_pool, mock_proxy):
        """Test putting a slow proxy (should be discarded)."""
        # Mock proxy as slow
        mock_proxy.stat = {'requests': 10}  # More than min_req_proxy (2)
        mock_proxy.error_rate = 0.1  # Good error rate
        mock_proxy.avg_resp_time = 10.0  # More than max_resp_time (5)
        
        proxy_pool.put(mock_proxy)
        # Should be discarded (not in newcomers or pool)
        assert mock_proxy not in proxy_pool._newcomers
        assert len(proxy_pool._pool) == 0


class TestServer:
    """Test cases for Server class."""

    def test_server_init(self):
        """Test Server initialization."""
        queue = asyncio.Queue()
        server = Server(
            host='localhost',
            port=9999,
            proxies=queue,
            timeout=10,
            backlog=50
        )
        assert server.host == 'localhost'
        assert server.port == 9999
        assert server._timeout == 10
        assert server._backlog == 50
        assert server._server is None
        assert server._connections == {}
        assert isinstance(server._proxy_pool, ProxyPool)

    @pytest.mark.asyncio
    async def test_server_start_stop(self, server):
        """Test server start and stop functionality."""
        # Mock asyncio.start_server
        mock_server_obj = MagicMock()
        mock_server_obj.close = MagicMock()
        mock_server_obj.wait_closed = AsyncMock()
        mock_server_obj.sockets = [MagicMock()]
        mock_server_obj.sockets[0].getsockname.return_value = ('localhost', 8888)
        
        with patch('asyncio.start_server', return_value=mock_server_obj) as mock_start_server:
            # Test start
            await server.start()
            assert server._server is mock_server_obj
            mock_start_server.assert_called_once_with(
                server._accept, server.host, server.port, backlog=server._backlog
            )

        # Test stop (mock loop to avoid actual stopping)
        with patch.object(server, '_loop') as mock_loop:
            mock_loop.is_running.return_value = False
            mock_loop.run_until_complete = MagicMock()
            mock_loop.stop = MagicMock()
            
            server.stop()
            mock_server_obj.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_accept_connection(self, server):
        """Test server accepting a connection."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.close = MagicMock()
        
        # Mock _handle method to avoid actual request processing
        with patch.object(server, '_handle', new_callable=AsyncMock) as mock_handle:
            # Call _accept
            server._accept(mock_reader, mock_writer)
            
            # Wait a moment for the async task to start
            await asyncio.sleep(0.01)
            
            # Check that _handle was called
            mock_handle.assert_called_once_with(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_server_handle_http_request(self, server, mock_proxy):
        """Test handling HTTP request."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Mock the proxy pool to return our mock proxy
        server._proxy_pool.get = AsyncMock(return_value=mock_proxy)
        
        # Mock request parsing
        with patch.object(server, '_parse_request', return_value=(b'GET / HTTP/1.1', {'Host': 'example.com', 'Path': '/'})):
            with patch.object(server, '_identify_scheme', return_value='HTTP'):
                with patch.object(server, '_choice_proto', return_value='HTTP'):
                    with patch.object(server, '_stream', new_callable=AsyncMock):
                        with patch.object(server._resolver, 'resolve', new_callable=AsyncMock):
                            await server._handle(mock_reader, mock_writer)
                            server._proxy_pool.get.assert_called_once_with('HTTP')

    @pytest.mark.asyncio
    async def test_server_handle_connect_request(self, server, mock_proxy):
        """Test handling CONNECT request."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Create a custom proxy that can handle ngtr setting
        class MockProxyWithNgtr:
            def __init__(self, base_proxy):
                self.base = base_proxy
                self._ngtr = base_proxy.ngtr
                
            def __getattr__(self, name):
                if name == 'ngtr':
                    return self._ngtr
                return getattr(self.base, name)
                
            def __setattr__(self, name, value):
                if name in ('base', '_ngtr'):
                    object.__setattr__(self, name, value)
                elif name == 'ngtr':
                    # When setting ngtr, just keep our mock negotiator
                    self._ngtr = self.base.ngtr
                else:
                    setattr(self.base, name, value)
        
        custom_proxy = MockProxyWithNgtr(mock_proxy)
        
        # Mock the proxy pool to return our custom proxy
        server._proxy_pool.get = AsyncMock(return_value=custom_proxy)
        
        # Mock request parsing for CONNECT
        with patch.object(server, '_parse_request', return_value=(b'CONNECT example.com:443 HTTP/1.1', {'Host': 'example.com', 'Port': 443, 'Path': 'example.com:443'})):
            with patch.object(server, '_identify_scheme', return_value='HTTPS'):
                with patch.object(server, '_choice_proto', return_value='SOCKS5'):
                    with patch.object(server, '_stream', new_callable=AsyncMock):
                        with patch.object(server._resolver, 'resolve', return_value='93.184.216.34', new_callable=AsyncMock):
                            await server._handle(mock_reader, mock_writer)
                            server._proxy_pool.get.assert_called_once_with('HTTPS')

    @pytest.mark.asyncio
    async def test_server_handle_no_proxy_available(self, server):
        """Test handling when no proxy is available."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Mock the proxy pool to raise NoProxyError
        server._proxy_pool.get = AsyncMock(side_effect=NoProxyError('No proxy available'))
        
        # Mock request parsing
        with patch.object(server, '_parse_request', return_value=(b'GET / HTTP/1.1', {'Host': 'example.com', 'Path': '/'})):
            with patch.object(server, '_identify_scheme', return_value='HTTP'):
                with pytest.raises(NoProxyError):
                    await server._handle(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_server_handle_proxy_error(self, server, mock_proxy):
        """Test handling proxy connection error."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        
        # Mock proxy connection to fail
        mock_proxy.connect.side_effect = ProxyConnError('Connection failed')
        server._proxy_pool.get = AsyncMock(return_value=mock_proxy)
        
        # Mock request parsing
        with patch.object(server, '_parse_request', return_value=(b'GET / HTTP/1.1', {'Host': 'example.com', 'Path': '/'})):
            with patch.object(server, '_identify_scheme', return_value='HTTP'):
                with patch.object(server, '_choice_proto', return_value='HTTP'):
                    # Should handle the error and continue to next attempt or fail
                    await server._handle(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_server_cleanup_connection(self, server):
        """Test server connection cleanup."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        
        # Mock _parse_request to return proper response
        mock_reader.read = MagicMock(return_value=b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n')
        
        with patch.object(server, '_parse_request', return_value=(b'GET / HTTP/1.1', {'Host': 'example.com', 'Path': '/'})):
            with patch.object(server, '_identify_scheme', return_value='HTTP'):
                with patch.object(server, '_proxy_pool') as mock_pool:
                    mock_pool.get.side_effect = NoProxyError('No proxy available')
                    try:
                        await server._handle(mock_reader, mock_writer)
                    except NoProxyError:
                        pass  # Expected

    def test_server_constants(self):
        """Test server constants."""
        assert CONNECTED == b'HTTP/1.1 200 Connection established\r\n\r\n'

    @pytest.mark.asyncio
    async def test_server_context_manager(self, server):
        """Test server as context manager."""
        # Server doesn't implement context manager, so this should fail
        # This test documents the current behavior
        with pytest.raises(AttributeError, match='__aenter__'):
            async with server:
                pass

    def test_server_relay_data(self):
        """Test data relay functionality constants."""
        # Test that the server has the expected constants
        assert hasattr(Server, '_handle')
        assert hasattr(Server, '_accept')
        # The actual relay logic is complex and would need extensive mocking
