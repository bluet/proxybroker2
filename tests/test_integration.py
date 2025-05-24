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
    provider.proto = None  # Accept all protocols
    
    async def mock_get_proxies(*args, **kwargs):
        # Yield some test proxy tuples (not MagicMock objects)
        for i in range(3):
            yield (f'127.0.0.{i+1}', 8080)
    
    provider.get_proxies = mock_get_proxies
    return provider


@pytest.fixture
def mock_judge():
    """Create a mock judge for integration testing."""
    judge = MagicMock(spec=Judge)
    judge.url = 'http://test-judge.com'
    judge.scheme = 'HTTP'
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
            max_tries=1,
            stop_broker_on_sigint=False
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
        
        # Mock the resolver's get_real_ext_ip method
        mocker.patch.object(Resolver, 'get_real_ext_ip', return_value='127.0.0.1')
        
        # Test the find workflow
        await broker.find(types=['HTTP'], limit=2)
        
        # Check that find was called and parameters set
        assert broker._checker is not None
        assert broker._limit == 2

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
            max_tries=1,
            stop_broker_on_sigint=False
        )
        
        # Mock Proxy.create
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        
        # Test grab workflow
        await broker.grab(limit=2)
        
        # Check that grab was called and parameters set
        assert broker._limit == 2
        assert broker._checker is None  # grab doesn't create checker

    @pytest.mark.asyncio
    async def test_proxy_validation_workflow(self, mock_provider, mock_judge, mocker):
        """Test proxy validation through checker workflow."""
        broker = Broker(
            providers=[mock_provider],
            judges=[mock_judge],
            timeout=0.1,
            max_conn=5,
            max_tries=1,
            stop_broker_on_sigint=False
        )
        
        # Mock Proxy.create
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        mocker.patch.object(Resolver, 'get_real_ext_ip', return_value='127.0.0.1')
        
        # Test validation workflow
        await broker.find(types=['HTTP'], limit=1)
        
        # Check that validation setup was completed
        assert broker._checker is not None

    def test_resolver_integration(self):
        """Test Resolver component integration."""
        resolver = Resolver()
        assert resolver is not None
        # Basic test that resolver initializes correctly
        assert hasattr(resolver, 'get_real_ext_ip')

    def test_proxy_pool_integration(self):
        """Test ProxyPool integration with proxy management."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies)
        
        # Test basic pool operations
        assert pool._proxies is proxies
        assert hasattr(pool, 'get')
        assert hasattr(pool, 'put')

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mock_provider, mocker):
        """Test error handling across components."""
        broker = Broker(
            providers=[mock_provider],
            timeout=0.1,
            stop_broker_on_sigint=False
        )
        
        # Mock Proxy.create to raise errors
        async def mock_create_error(host, port, *args, **kwargs):
            from proxybroker.errors import ResolveError
            raise ResolveError('Test error')
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create_error)
        mocker.patch.object(Resolver, 'get_real_ext_ip', return_value='127.0.0.1')
        
        # Test error handling
        await broker.find(types=['HTTP'], limit=2)
        
        # Should complete without crashing despite errors
        assert broker._checker is not None

    @pytest.mark.asyncio
    async def test_country_filtering_integration(self, mock_provider, mocker):
        """Test country filtering integration."""
        broker = Broker(
            providers=[mock_provider],
            timeout=0.1,
            stop_broker_on_sigint=False
        )
        
        # Mock Proxy.create
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        mocker.patch.object(Resolver, 'get_real_ext_ip', return_value='127.0.0.1')
        
        # Test country filtering
        await broker.find(types=['HTTP'], countries=['US'], limit=1)
        
        # Check that country filter was applied
        assert broker._countries == ['US']

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_provider, mocker):
        """Test concurrent broker operations."""
        broker = Broker(
            providers=[mock_provider],
            timeout=0.1,
            max_conn=3,
            stop_broker_on_sigint=False
        )
        
        # Mock Proxy.create
        async def mock_create(host, port, *args, **kwargs):
            proxy = MagicMock(spec=Proxy)
            proxy.host = host
            proxy.port = port
            proxy.geo = MagicMock()
            proxy.geo.code = 'US'
            await asyncio.sleep(0.01)  # Simulate async work
            return proxy
        
        mocker.patch.object(Proxy, 'create', side_effect=mock_create)
        mocker.patch.object(Resolver, 'get_real_ext_ip', return_value='127.0.0.1')
        
        # Test concurrent operations
        await broker.find(types=['HTTP'], limit=3)
        
        # Check that concurrent operations were handled
        assert broker._checker is not None

    def test_configuration_integration(self):
        """Test that configuration is properly passed between components."""
        # Test custom timeout propagation
        timeout = 15
        broker = Broker(timeout=timeout, stop_broker_on_sigint=False)
        
        assert broker._timeout == timeout
        
        # Test max_conn propagation
        max_conn = 50
        broker = Broker(max_conn=max_conn, stop_broker_on_sigint=False)
        
        assert broker._on_check.maxsize == max_conn
        
        # Test max_tries propagation
        max_tries = 5
        broker = Broker(max_tries=max_tries, stop_broker_on_sigint=False)
        
        assert broker._max_tries == max_tries