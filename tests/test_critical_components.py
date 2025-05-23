"""Critical component tests focusing on core functionality."""
import asyncio
import heapq
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker.api import Broker
from proxybroker.checker import Checker
from proxybroker.server import ProxyPool, CONNECTED
from proxybroker.errors import NoProxyError, ProxyConnError


class TestBrokerCritical:
    """Critical Broker functionality tests."""

    def test_broker_init_basic(self):
        """Test basic Broker initialization."""
        broker = Broker()
        assert broker._timeout == 8
        assert broker._max_tries == 3
        assert broker._verify_ssl is False
        assert broker._proxies is not None
        assert broker._resolver is not None
        assert broker._providers is not None

    def test_broker_init_custom_params(self):
        """Test Broker with custom parameters."""
        queue = asyncio.Queue()
        broker = Broker(
            queue=queue,
            timeout=10,
            max_tries=5,
            verify_ssl=True
        )
        assert broker._timeout == 10
        assert broker._max_tries == 5
        assert broker._verify_ssl is True
        assert broker._proxies is queue

    def test_broker_providers_setup(self):
        """Test provider setup in Broker."""
        providers = ['http://provider1.com', 'http://provider2.com']
        broker = Broker(providers=providers)
        assert len(broker._providers) == 2

    def test_broker_judges_setup(self):
        """Test judges setup in Broker."""
        judges = ['http://judge1.com', 'http://judge2.com']
        broker = Broker(judges=judges)
        assert broker._judges == judges


class TestCheckerCritical:
    """Critical Checker functionality tests."""

    def test_checker_init_basic(self):
        """Test basic Checker initialization."""
        checker = Checker(
            judges=['http://judge.com'],
            timeout=5,
            max_tries=2
        )
        assert len(checker._judges) == 1
        assert checker._max_tries == 2

    def test_checker_init_empty_judges(self):
        """Test Checker with empty judges."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        assert len(checker._judges) == 0

    @pytest.mark.asyncio
    async def test_checker_no_judges_error(self):
        """Test checker raises error with no judges."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        
        mock_proxy = MagicMock()
        mock_proxy.close = MagicMock()
        
        with pytest.raises(RuntimeError, match='Not found judges'):
            await checker.check_proxy(mock_proxy)

    def test_checker_get_headers(self):
        """Test _get_headers method."""
        checker = Checker(judges=['http://judge.com'], timeout=5, max_tries=1)
        
        response = (b'HTTP/1.1 200 OK\r\n'
                   b'Content-Type: application/json\r\n'
                   b'X-Forwarded-For: 1.2.3.4\r\n\r\n'
                   b'body')
        
        headers = checker._get_headers(response)
        assert 'Content-Type' in headers
        assert headers['Content-Type'] == 'application/json'
        assert headers['X-Forwarded-For'] == '1.2.3.4'

    @pytest.mark.asyncio
    async def test_checker_is_anon_lvl(self):
        """Test anonymity level detection."""
        checker = Checker(judges=['http://judge.com'], timeout=5, max_tries=1)
        
        # Headers with proxy indicators
        proxy_headers = {
            'X-Forwarded-For': '1.2.3.4',
            'Via': '1.1 proxy'
        }
        result = await checker._is_anon_lvl(proxy_headers)
        assert result is False
        
        # Headers without proxy indicators
        clean_headers = {
            'Content-Type': 'application/json',
            'Content-Length': '100'
        }
        result = await checker._is_anon_lvl(clean_headers)
        assert result is True


class TestProxyPoolCritical:
    """Critical ProxyPool functionality tests."""

    def test_proxy_pool_init(self):
        """Test ProxyPool initialization."""
        queue = asyncio.Queue()
        pool = ProxyPool(
            proxies=queue,
            min_req_proxy=5,
            max_error_rate=0.4,
            max_resp_time=10,
            min_queue=3,
            strategy='best'
        )
        assert pool._proxies is queue
        assert pool._min_req_proxy == 5
        assert pool._max_error_rate == 0.4
        assert pool._max_resp_time == 10
        assert pool._min_queue == 3
        assert pool._strategy == 'best'

    def test_proxy_pool_invalid_strategy(self):
        """Test ProxyPool rejects invalid strategy."""
        queue = asyncio.Queue()
        with pytest.raises(ValueError, match='`strategy` only support `best` for now'):
            ProxyPool(proxies=queue, strategy='invalid')

    def test_proxy_pool_put_newcomer(self):
        """Test putting newcomer proxy into pool."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=10)  # High threshold
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 5}  # Less than min_req_proxy
        
        pool.put(mock_proxy)
        assert mock_proxy in pool._newcomers

    def test_proxy_pool_put_experienced_good(self):
        """Test putting experienced good proxy into main pool."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=5, max_error_rate=0.5, max_resp_time=10)
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 10}  # Experienced
        mock_proxy.error_rate = 0.2  # Good error rate
        mock_proxy.avg_resp_time = 5.0  # Good response time
        
        pool.put(mock_proxy)
        assert (mock_proxy.avg_resp_time, mock_proxy) in pool._pool

    def test_proxy_pool_put_experienced_bad_error_rate(self):
        """Test bad proxy is discarded due to high error rate."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=5, max_error_rate=0.3, max_resp_time=10)
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 10}  # Experienced
        mock_proxy.error_rate = 0.8  # Bad error rate
        mock_proxy.avg_resp_time = 5.0
        
        pool.put(mock_proxy)
        # Should be discarded
        assert len(pool._pool) == 0
        assert len(pool._newcomers) == 0

    def test_proxy_pool_put_experienced_bad_response_time(self):
        """Test bad proxy is discarded due to slow response."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=5, max_error_rate=0.5, max_resp_time=8)
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 10}  # Experienced
        mock_proxy.error_rate = 0.2  # Good error rate
        mock_proxy.avg_resp_time = 15.0  # Too slow
        
        pool.put(mock_proxy)
        # Should be discarded
        assert len(pool._pool) == 0
        assert len(pool._newcomers) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_newcomers(self):
        """Test getting proxy from newcomers."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_queue=5)  # High min_queue to trigger newcomer use
        
        mock_proxy = MagicMock()
        mock_proxy.schemes = ('HTTP', 'HTTPS')
        pool._newcomers.append(mock_proxy)
        
        result = await pool.get('HTTP')
        assert result is mock_proxy
        assert len(pool._newcomers) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_main_pool(self):
        """Test getting proxy from main pool using heap."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_queue=1)
        
        # Create multiple proxies with different priorities
        proxy1 = MagicMock()
        proxy1.schemes = ('HTTP', 'HTTPS')
        proxy1.avg_resp_time = 2.0
        
        proxy2 = MagicMock()
        proxy2.schemes = ('HTTP', 'HTTPS')
        proxy2.avg_resp_time = 1.0  # Faster
        
        # Add to heap (priority queue)
        heapq.heappush(pool._pool, (proxy1.avg_resp_time, proxy1))
        heapq.heappush(pool._pool, (proxy2.avg_resp_time, proxy2))
        
        # Should get the fastest proxy first
        result = await pool.get('HTTP')
        assert result is proxy2  # The faster one

    @pytest.mark.asyncio
    async def test_proxy_pool_get_scheme_mismatch(self):
        """Test handling when no proxy supports requested scheme."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_queue=1)
        
        # Mock _import to return None
        original_import = pool._import
        async def mock_import(scheme):
            return None
        pool._import = mock_import
        
        mock_proxy = MagicMock()
        mock_proxy.schemes = ('HTTP', 'HTTPS')  # Doesn't support SOCKS
        heapq.heappush(pool._pool, (1.0, mock_proxy))
        
        result = await pool.get('SOCKS5')
        assert result is None

    @pytest.mark.asyncio
    async def test_proxy_pool_import_from_queue(self):
        """Test importing proxy from queue."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        mock_proxy = MagicMock()
        mock_proxy.schemes = ('HTTP', 'HTTPS')
        await queue.put(mock_proxy)
        
        result = await pool._import('HTTP')
        assert result is mock_proxy

    @pytest.mark.asyncio
    async def test_proxy_pool_import_empty_queue(self):
        """Test importing when queue is empty."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        result = await pool._import('HTTP')
        assert result is None


class TestServerCritical:
    """Critical Server functionality tests."""

    def test_server_constants(self):
        """Test server constants are defined."""
        assert CONNECTED == b'HTTP/1.1 200 Connection established\r\n\r\n'

    def test_server_init(self):
        """Test Server initialization."""
        from proxybroker.server import Server
        
        mock_pool = MagicMock()
        server = Server(
            host='127.0.0.1',
            port=8080,
            proxies=mock_pool,
            timeout=10,
            backlog=50
        )
        assert server.host == '127.0.0.1'
        assert server.port == 8080
        assert server.proxies is mock_pool
        assert server.timeout == 10
        assert server.backlog == 50


class TestCriticalErrorHandling:
    """Test critical error handling scenarios."""

    @pytest.mark.asyncio
    async def test_checker_proxy_error_handling(self):
        """Test checker handles proxy errors gracefully."""
        checker = Checker(judges=['http://judge.com'], timeout=1, max_tries=1)
        
        mock_proxy = MagicMock()
        mock_proxy.connect = AsyncMock(side_effect=ProxyConnError('Connection failed'))
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        # Should not raise exception, just log error
        await checker.check_proxy(mock_proxy)
        
        mock_proxy.log.assert_called()
        mock_proxy.close.assert_called()

    def test_proxy_pool_heap_integrity(self):
        """Test that proxy pool maintains heap integrity."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        # Add multiple proxies with different priorities
        proxies = []
        for i in range(5):
            proxy = MagicMock()
            proxy.avg_resp_time = i + 1.0
            proxy.schemes = ('HTTP',)
            proxy.stat = {'requests': 10}
            proxy.error_rate = 0.1
            proxies.append(proxy)
            pool.put(proxy)
        
        # Verify heap property is maintained
        heap_items = [item[0] for item in pool._pool]
        assert heap_items == sorted(heap_items), "Heap property violated"

    def test_broker_unique_proxies_tracking(self):
        """Test that broker tracks unique proxies correctly."""
        broker = Broker()
        
        # Verify unique_proxies dict is initialized
        assert hasattr(broker, 'unique_proxies')
        assert isinstance(broker.unique_proxies, dict)


class TestConstants:
    """Test important constants and configuration."""

    def test_api_constants(self):
        """Test API module constants."""
        from proxybroker.api import GRAB_PAUSE, MAX_CONCURRENT_PROVIDERS
        
        assert GRAB_PAUSE == 180
        assert MAX_CONCURRENT_PROVIDERS == 3

    def test_server_constants(self):
        """Test server module constants."""
        from proxybroker.server import CONNECTED
        
        assert CONNECTED == b'HTTP/1.1 200 Connection established\r\n\r\n'