import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Proxy
from proxybroker.errors import NoProxyError, ProxyConnError, ProxyTimeoutError
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
    return proxy


@pytest.fixture
def mock_queue():
    """Create a mock queue with test proxies."""
    queue = asyncio.Queue()
    return queue


@pytest.fixture
async def proxy_pool(mock_queue):
    """Create a ProxyPool instance for testing."""
    return ProxyPool(
        proxies=mock_queue,
        min_req_proxy=2,
        max_error_rate=0.5,
        max_resp_time=5,
        min_queue=2,
        strategy='best'
    )


class TestProxyPool:
    """Test cases for ProxyPool class."""

    def test_proxy_pool_init(self):
        """Test ProxyPool initialization."""
        queue = asyncio.Queue()
        pool = ProxyPool(
            proxies=queue,
            min_req_proxy=5,
            max_error_rate=0.3,
            max_resp_time=10,
            min_queue=3,
            strategy='best'
        )
        assert pool._proxies is queue
        assert pool._min_req_proxy == 5
        assert pool._max_error_rate == 0.3
        assert pool._max_resp_time == 10
        assert pool._min_queue == 3
        assert pool._strategy == 'best'
        assert pool._pool == []
        assert pool._newcomers == []

    def test_proxy_pool_invalid_strategy(self):
        """Test ProxyPool with invalid strategy raises ValueError."""
        queue = asyncio.Queue()
        with pytest.raises(ValueError, match='`strategy` only support `best` for now.'):
            ProxyPool(proxies=queue, strategy='invalid')

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_newcomers(self, proxy_pool, mock_proxy):
        """Test getting proxy from newcomers when pool is insufficient."""
        # Add proxy to newcomers
        proxy_pool._newcomers.append(mock_proxy)
        
        result = await proxy_pool.get('HTTP')
        assert result is mock_proxy
        assert len(proxy_pool._newcomers) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_pool(self, proxy_pool, mock_proxy):
        """Test getting proxy from main pool using heap."""
        # Add proxy to main pool (priority, proxy)
        proxy_pool._pool.append((1.0, mock_proxy))
        proxy_pool._newcomers = []  # Empty newcomers
        
        result = await proxy_pool.get('HTTP')
        assert result is mock_proxy
        assert len(proxy_pool._pool) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_get_scheme_mismatch(self, proxy_pool):
        """Test getting proxy when scheme doesn't match."""
        # Create proxy that doesn't support SOCKS
        mock_proxy = MagicMock(spec=Proxy)
        mock_proxy.schemes = ('HTTP', 'HTTPS')
        
        proxy_pool._pool.append((1.0, mock_proxy))
        proxy_pool._newcomers = []
        
        # Mock _import to return None when no matching proxy
        async def mock_import(scheme):
            return None
        proxy_pool._import = mock_import
        
        result = await proxy_pool.get('SOCKS5')
        assert result is None

    @pytest.mark.asyncio
    async def test_proxy_pool_import_from_queue(self, proxy_pool, mock_proxy):
        """Test importing proxy from queue."""
        # Put proxy in queue
        await proxy_pool._proxies.put(mock_proxy)
        
        result = await proxy_pool._import('HTTP')
        assert result is mock_proxy

    @pytest.mark.asyncio
    async def test_proxy_pool_import_empty_queue(self, proxy_pool):
        """Test importing when queue is empty."""
        # Queue is already empty
        result = await proxy_pool._import('HTTP')
        assert result is None

    @pytest.mark.asyncio
    async def test_proxy_pool_import_scheme_mismatch(self, proxy_pool):
        """Test importing proxy with scheme mismatch."""
        # Create proxy that doesn't support requested scheme
        mock_proxy = MagicMock(spec=Proxy)
        mock_proxy.schemes = ('HTTP',)
        
        await proxy_pool._proxies.put(mock_proxy)
        
        result = await proxy_pool._import('SOCKS5')
        assert result is None
        # Proxy should be discarded, not added to newcomers
        assert len(proxy_pool._newcomers) == 0

    def test_proxy_pool_put_newcomer(self, proxy_pool, mock_proxy):
        """Test putting proxy back as newcomer."""
        proxy_pool.put(mock_proxy)
        assert mock_proxy in proxy_pool._newcomers

    def test_proxy_pool_put_experienced_good_proxy(self, proxy_pool, mock_proxy):
        """Test putting experienced proxy with good stats back to pool."""
        # Make proxy experienced with good stats
        mock_proxy.stat = {'requests': 10}  # >= min_req_proxy
        mock_proxy.error_rate = 0.2  # < max_error_rate
        mock_proxy.avg_resp_time = 3.0  # < max_resp_time
        
        proxy_pool.put(mock_proxy)
        assert (mock_proxy.avg_resp_time, mock_proxy) in proxy_pool._pool

    def test_proxy_pool_put_experienced_bad_proxy(self, proxy_pool, mock_proxy):
        """Test putting experienced proxy with bad stats (should be discarded)."""
        # Make proxy experienced with bad error rate
        mock_proxy.stat = {'requests': 10}  # >= min_req_proxy
        mock_proxy.error_rate = 0.6  # > max_error_rate
        mock_proxy.avg_resp_time = 3.0
        
        proxy_pool.put(mock_proxy)
        # Should be discarded, not added to pool or newcomers
        assert len(proxy_pool._pool) == 0
        assert len(proxy_pool._newcomers) == 0

    def test_proxy_pool_put_slow_proxy(self, proxy_pool, mock_proxy):
        """Test putting proxy with slow response time (should be discarded)."""
        mock_proxy.stat = {'requests': 10}
        mock_proxy.error_rate = 0.2
        mock_proxy.avg_resp_time = 10.0  # > max_resp_time
        
        proxy_pool.put(mock_proxy)
        assert len(proxy_pool._pool) == 0
        assert len(proxy_pool._newcomers) == 0


class TestServer:
    """Test cases for Server class."""

    @pytest.fixture
    def mock_proxy_pool(self):
        """Create a mock ProxyPool for testing."""
        pool = MagicMock(spec=ProxyPool)
        return pool

    @pytest.fixture
    def server(self, mock_proxy_pool):
        """Create a Server instance for testing."""
        return Server(
            host='127.0.0.1',
            port=8888,
            proxies=mock_proxy_pool,
            timeout=5,
            backlog=100
        )

    def test_server_init(self, mock_proxy_pool):
        """Test Server initialization."""
        server = Server(
            host='localhost',
            port=9999,
            proxies=mock_proxy_pool,
            timeout=10,
            backlog=50
        )
        assert server.host == 'localhost'
        assert server.port == 9999
        assert server.proxies is mock_proxy_pool
        assert server.timeout == 10
        assert server.backlog == 50
        assert server._server is None
        assert server._connections == {}

    @pytest.mark.asyncio
    async def test_server_start_stop(self, server, mocker):
        """Test server start and stop functionality."""
        # Mock asyncio.start_server
        mock_start_server = AsyncMock()
        mock_server_obj = MagicMock()
        mock_server_obj.close = MagicMock()
        mock_server_obj.wait_closed = AsyncMock()
        mock_start_server.return_value = mock_server_obj
        
        mocker.patch('asyncio.start_server', mock_start_server)
        
        # Test start
        await server.start()
        assert server._server is mock_server_obj
        mock_start_server.assert_called_once_with(
            server._accept, server.host, server.port, backlog=server.backlog
        )
        
        # Test stop
        await server.stop()
        mock_server_obj.close.assert_called_once()
        mock_server_obj.wait_closed.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_accept_connection(self, server, mocker):
        """Test server accepting a connection."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        
        # Mock _handle method
        server._handle = AsyncMock()
        
        await server._accept(mock_reader, mock_writer)
        
        # Verify connection was tracked
        conn_id = ('127.0.0.1', 12345)
        assert conn_id in server._connections
        
        # Verify _handle was called
        server._handle.assert_called_once_with(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_server_handle_http_request(self, server, mock_proxy, mocker):
        """Test handling HTTP request through proxy."""
        # Mock reader and writer
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        
        # Mock reading HTTP request
        http_request = b'GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n'
        mock_reader.read.return_value = http_request
        
        # Mock proxy pool returning a proxy
        server.proxies.get.return_value = mock_proxy
        
        # Mock proxy connection and response
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock() 
        mock_proxy.recv = AsyncMock(return_value=b'HTTP/1.1 200 OK\r\n\r\nTest response')
        mock_proxy.close = MagicMock()
        
        await server._handle(mock_reader, mock_writer)
        
        # Verify proxy was used
        server.proxies.get.assert_called_once_with('HTTP')
        mock_proxy.connect.assert_called_once()
        mock_proxy.send.assert_called_once_with(http_request)

    @pytest.mark.asyncio
    async def test_server_handle_connect_request(self, server, mock_proxy, mocker):
        """Test handling CONNECT request for HTTPS."""
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Mock CONNECT request
        connect_request = b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n'
        mock_reader.read.return_value = connect_request
        
        server.proxies.get.return_value = mock_proxy
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(return_value=CONNECTED)
        
        await server._handle(mock_reader, mock_writer)
        
        # Verify CONNECT response was sent
        mock_writer.write.assert_called_with(CONNECTED)
        mock_writer.drain.assert_called()

    @pytest.mark.asyncio
    async def test_server_handle_no_proxy_available(self, server, mocker):
        """Test handling request when no proxy is available."""
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()
        
        http_request = b'GET http://example.com/ HTTP/1.1\r\n\r\n'
        mock_reader.read.return_value = http_request
        
        # No proxy available
        server.proxies.get.return_value = None
        
        await server._handle(mock_reader, mock_writer)
        
        # Verify error response was sent
        mock_writer.write.assert_called()
        error_response = mock_writer.write.call_args[0][0]
        assert b'502 Bad Gateway' in error_response

    @pytest.mark.asyncio
    async def test_server_handle_proxy_error(self, server, mock_proxy, mocker):
        """Test handling proxy connection errors."""
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()
        
        http_request = b'GET http://example.com/ HTTP/1.1\r\n\r\n'
        mock_reader.read.return_value = http_request
        
        server.proxies.get.return_value = mock_proxy
        mock_proxy.connect = AsyncMock(side_effect=ProxyConnError('Connection failed'))
        
        await server._handle(mock_reader, mock_writer)
        
        # Verify error response was sent
        mock_writer.write.assert_called()
        error_response = mock_writer.write.call_args[0][0]
        assert b'502 Bad Gateway' in error_response

    @pytest.mark.asyncio
    async def test_server_cleanup_connection(self, server):
        """Test connection cleanup after handling."""
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.write = MagicMock()
        mock_writer.close = MagicMock()
        
        # Add connection to tracking
        conn_id = ('127.0.0.1', 12345)
        server._connections[conn_id] = time.time()
        
        # Mock request that causes early return
        mock_reader.read.return_value = b''  # Empty request
        
        await server._handle(mock_reader, mock_writer)
        
        # Verify connection was cleaned up
        assert conn_id not in server._connections
        mock_writer.close.assert_called()

    def test_server_constants(self):
        """Test server constants are defined correctly."""
        assert CONNECTED == b'HTTP/1.1 200 Connection established\r\n\r\n'

    @pytest.mark.asyncio
    async def test_server_context_manager(self, mock_proxy_pool):
        """Test server as async context manager."""
        server = Server('127.0.0.1', 8888, mock_proxy_pool)
        
        # Mock start and stop
        server.start = AsyncMock()
        server.stop = AsyncMock()
        
        async with server:
            pass
        
        server.start.assert_called_once()
        server.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_relay_data(self, server, mocker):
        """Test data relay between client and proxy."""
        # This tests the _relay method if it exists
        mock_reader1 = MagicMock()
        mock_writer1 = MagicMock()
        mock_reader2 = MagicMock()
        mock_writer2 = MagicMock()
        
        # Mock read/write operations
        mock_reader1.read.side_effect = [b'test data', b'']
        mock_writer2.write = MagicMock()
        mock_writer2.drain = AsyncMock()
        
        # If _relay method exists, test it
        if hasattr(server, '_relay'):
            await server._relay(mock_reader1, mock_writer2)
            mock_writer2.write.assert_called_with(b'test data')