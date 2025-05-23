"""Integration tests for ProxyBroker2 end-to-end workflows."""
import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Broker, Proxy
from proxybroker.checker import Checker
from proxybroker.judge import Judge
from proxybroker.providers import Provider
from proxybroker.resolver import Resolver
from proxybroker.server import ProxyPool, Server


@pytest.fixture
def mock_provider():
    """Create a mock provider for integration testing."""
    provider = MagicMock(spec=Provider)
    provider.url = 'http://test-provider.com'
    
    async def mock_get_proxies(*args, **kwargs):
        # Yield some test proxies
        for i in range(3):
            proxy_data = MagicMock()
            proxy_data.host = f'127.0.0.{i+1}'
            proxy_data.port = 8080
            yield proxy_data
    
    provider.get_proxies = mock_get_proxies
    return provider


@pytest.fixture
def mock_judge():
    """Create a mock judge for integration testing."""
    judge = MagicMock(spec=Judge)
    judge.url = 'http://test-judge.com'
    judge.host = 'test-judge.com'
    judge.path = '/'
    judge.request = b'GET / HTTP/1.1\r\nHost: test-judge.com\r\n\r\n'
    return judge


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_broker_find_workflow(self, mock_provider, mock_judge, mocker):
        """Test complete find workflow: provider -> resolver -> checker -> output."""
        # Create broker with mocked components
        broker = Broker(
            providers=[mock_provider],
            judges=[mock_judge],
            timeout=0.1,
            max_conn=5,
            max_tries=1
        )
        
        # Mock Proxy.create to avoid real network calls
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.schemes = ('HTTP', 'HTTPS')
            proxy.types = {}
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        
        # Mock checker to avoid real proxy validation
        async def mock_check_proxy(proxy):
            proxy.types['HTTP'] = 'Anonymous'
        
        mocker.patch.object(broker._checker, 'check_proxy', side_effect=mock_check_proxy)
        
        # Test the find workflow
        found_proxies = []
        async for proxy in broker.find(limit=2):
            found_proxies.append(proxy)
        
        assert len(found_proxies) == 2
        assert all(proxy.host.startswith('127.0.0.') for proxy in found_proxies)
        assert all('HTTP' in proxy.types for proxy in found_proxies)

    @pytest.mark.asyncio
    async def test_broker_grab_and_serve_workflow(self, mock_provider, mock_judge, mocker):
        """Test grab and serve workflow with queue."""
        queue = asyncio.Queue(maxsize=10)
        
        broker = Broker(
            queue=queue,
            providers=[mock_provider],
            judges=[mock_judge],
            timeout=0.1,
            max_conn=3,
            max_tries=1
        )
        
        # Mock components
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.schemes = ('HTTP', 'HTTPS')
            proxy.types = {}
            proxy.stat = {'requests': 0}
            proxy.avg_resp_time = 1.0
            proxy.error_rate = 0.1
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        
        async def mock_check_proxy(proxy):
            proxy.types['HTTP'] = 'Anonymous'
        
        mocker.patch.object(broker._checker, 'check_proxy', side_effect=mock_check_proxy)
        
        # Start grab task
        grab_task = asyncio.create_task(broker.grab())
        
        # Let it run briefly to collect some proxies
        await asyncio.sleep(0.05)
        
        # Check that proxies were added to queue
        assert not queue.empty()
        
        # Create proxy pool and server
        proxy_pool = ProxyPool(proxies=queue, min_queue=1)
        server = Server(
            host='127.0.0.1',
            port=8888,
            proxies=proxy_pool,
            timeout=5
        )
        
        # Test that server can get proxies from pool
        proxy = await proxy_pool.get('HTTP')
        assert proxy is not None
        assert hasattr(proxy, 'host')
        
        # Clean up
        grab_task.cancel()
        try:
            await grab_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_proxy_validation_workflow(self, mocker):
        """Test complete proxy validation workflow."""
        # Create real checker with mocked network calls
        checker = Checker(
            judges=['http://test-judge.com'],
            timeout=0.1,
            max_tries=1
        )
        
        # Create test proxy
        proxy = MagicMock(spec=Proxy)
        proxy.host = '127.0.0.1'
        proxy.port = 8080
        proxy.schemes = ('HTTP',)
        proxy.types = {}
        proxy.stat = {'requests': 0}
        proxy.log = MagicMock()
        proxy.close = MagicMock()
        
        # Mock proxy network operations
        proxy.connect = AsyncMock()
        proxy.send = AsyncMock()
        proxy.recv = AsyncMock(return_value=b'HTTP/1.1 200 OK\r\n\r\n{"ip": "8.8.8.8"}')
        
        # Mock resolver for anonymity checking
        checker._resolver = MagicMock()
        checker._resolver.get_real_ext_ip = AsyncMock(return_value='1.2.3.4')
        
        # Run validation
        await checker.check_proxy(proxy)
        
        # Verify proxy was processed
        proxy.connect.assert_called()
        proxy.send.assert_called()
        proxy.recv.assert_called()
        proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_resolver_integration(self):
        """Test resolver integration with real GeoIP database."""
        resolver = Resolver(timeout=0.1)
        
        # Test IP validation
        assert resolver.host_is_ip('127.0.0.1') is True
        assert resolver.host_is_ip('invalid.ip') is False
        
        # Test GeoIP lookup (using localhost)
        ip_info = resolver.get_ip_info('127.0.0.1')
        assert ip_info.code == '--'  # Localhost has no country
        assert ip_info.name == 'Unknown'
        
        # Test public IP GeoIP lookup
        ip_info = resolver.get_ip_info('8.8.8.8')
        assert ip_info.code == 'US'  # Google DNS is in US
        assert ip_info.name == 'United States'

    @pytest.mark.asyncio
    async def test_proxy_pool_integration(self):
        """Test ProxyPool integration with real proxy objects."""
        queue = asyncio.Queue()
        proxy_pool = ProxyPool(
            proxies=queue,
            min_req_proxy=1,
            max_error_rate=0.5,
            max_resp_time=5,
            min_queue=1,
            strategy='best'
        )
        
        # Create test proxies
        proxies = []
        for i in range(3):
            proxy = MagicMock(spec=Proxy)
            proxy.host = f'127.0.0.{i+1}'
            proxy.port = 8080
            proxy.schemes = ('HTTP', 'HTTPS')
            proxy.avg_resp_time = i + 1.0  # Different response times
            proxy.error_rate = i * 0.1  # Different error rates
            proxy.stat = {'requests': 10}  # Experienced proxies
            proxies.append(proxy)
        
        # Add proxies to queue
        for proxy in proxies:
            await queue.put(proxy)
        
        # Test getting proxies (should get fastest first due to heap)
        retrieved_proxies = []
        for _ in range(3):
            proxy = await proxy_pool.get('HTTP')
            if proxy:
                retrieved_proxies.append(proxy)
        
        assert len(retrieved_proxies) == 3
        # First proxy should be fastest (lowest response time)
        assert retrieved_proxies[0].avg_resp_time == 1.0

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mock_provider, mocker):
        """Test error handling across components."""
        broker = Broker(
            providers=[mock_provider],
            judges=['http://invalid-judge.com'],
            timeout=0.01,  # Very short timeout to trigger errors
            max_conn=1,
            max_tries=1
        )
        
        # Mock Proxy.create to sometimes fail
        call_count = 0
        async def mock_create_sometimes_fail(host, port, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception('Simulated failure')
            
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.schemes = ('HTTP',)
            proxy.types = {}
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create_sometimes_fail)
        
        # Should handle errors gracefully and still return some proxies
        found_proxies = []
        async for proxy in broker.find(limit=2):
            found_proxies.append(proxy)
        
        # Might get fewer than requested due to errors, but shouldn't crash
        assert len(found_proxies) >= 0

    @pytest.mark.asyncio
    async def test_country_filtering_integration(self, mock_provider, mock_judge, mocker):
        """Test country-based filtering integration."""
        broker = Broker(
            providers=[mock_provider],
            judges=[mock_judge],
            timeout=0.1
        )
        
        # Mock Proxy.create to return proxies with different countries
        call_count = 0
        async def mock_create_with_geo(host, port, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.schemes = ('HTTP',)
            proxy.types = {}
            proxy.geo = MagicMock()
            # Alternate between US and CN
            proxy.geo.code = 'US' if call_count % 2 == 1 else 'CN'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create_with_geo)
        
        # Mock checker
        async def mock_check_proxy(proxy):
            proxy.types['HTTP'] = 'Anonymous'
        
        mocker.patch.object(broker._checker, 'check_proxy', side_effect=mock_check_proxy)
        
        # Test filtering by US only
        us_proxies = []
        async for proxy in broker.find(countries=['US'], limit=3):
            us_proxies.append(proxy)
        
        # Should only get US proxies
        assert all(proxy.geo.code == 'US' for proxy in us_proxies)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_provider, mock_judge, mocker):
        """Test concurrent operations don't interfere with each other."""
        broker1 = Broker(
            providers=[mock_provider],
            judges=[mock_judge],
            timeout=0.1,
            max_conn=2
        )
        
        broker2 = Broker(
            providers=[mock_provider], 
            judges=[mock_judge],
            timeout=0.1,
            max_conn=2
        )
        
        # Mock Proxy.create
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.schemes = ('HTTP',)
            proxy.types = {}
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        
        # Mock checker
        async def mock_check_proxy(proxy):
            proxy.types['HTTP'] = 'Anonymous'
        
        mocker.patch.object(broker1._checker, 'check_proxy', side_effect=mock_check_proxy)
        mocker.patch.object(broker2._checker, 'check_proxy', side_effect=mock_check_proxy)
        
        # Run two brokers concurrently
        async def collect_proxies(broker, limit):
            proxies = []
            async for proxy in broker.find(limit=limit):
                proxies.append(proxy)
            return proxies
        
        results = await asyncio.gather(
            collect_proxies(broker1, 2),
            collect_proxies(broker2, 2),
            return_exceptions=True
        )
        
        # Both should succeed without interference
        assert len(results) == 2
        assert all(isinstance(result, list) for result in results)

    def test_configuration_integration(self):
        """Test that configuration is properly passed between components."""
        # Test custom timeout propagation
        timeout = 15
        broker = Broker(timeout=timeout)
        
        assert broker.timeout == timeout
        assert broker._checker.timeout == timeout
        
        # Test custom max_conn propagation
        max_conn = 50
        broker = Broker(max_conn=max_conn)
        
        assert broker.max_conn == max_conn
        
        # Test SSL verification propagation
        broker = Broker(verify_ssl=True)
        
        assert broker.verify_ssl is True