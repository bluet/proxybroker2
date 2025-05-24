"""Integration tests that mirror real user workflows from examples/.

These tests focus on user-facing behavior and API contracts that must remain stable.
They test end-to-end scenarios that users actually depend on.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proxybroker import Broker, Proxy, ProxyPool, Server
from proxybroker.errors import NoProxyError


class TestUserWorkflows:
    """Test real user workflows based on examples/ directory."""

    @pytest.mark.asyncio
    async def test_basic_find_workflow(self):
        """Test the basic find workflow from examples/basic.py.
        
        Users depend on this workflow pattern working consistently.
        """
        proxies = asyncio.Queue()
        broker = Broker(proxies, timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
        
        # Mock the core components that interact with external services
        with patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1'):
            with patch.object(broker, '_grab', return_value=None):
                # Test that the basic API contract works
                await broker.find(types=['HTTP', 'HTTPS'], limit=2)
                
                # Verify broker was properly configured
                assert broker._types == ['HTTP', 'HTTPS']
                assert broker._limit == 2
                assert broker._checker is not None

    @pytest.mark.asyncio
    async def test_proxy_pool_workflow(self):
        """Test the ProxyPool workflow from examples/find_and_use.py.
        
        Users depend on getting and putting proxies consistently.
        """
        proxies = asyncio.Queue()
        proxy_pool = ProxyPool(proxies, min_req_proxy=1, max_error_rate=0.5, max_resp_time=5)
        
        # Create a working proxy (as users would get from broker.find())
        proxy = Proxy('127.0.0.1', 8080)
        proxy.types = {'HTTP': 'Anonymous'}
        proxy._runtimes = [1.0]  # Good response time
        proxy.stat = {'requests': 1, 'errors': 0}  # Good error rate
        
        # Test the get/put cycle users depend on
        await proxies.put(proxy)
        
        retrieved_proxy = await proxy_pool.get(scheme='http')
        assert retrieved_proxy is not None
        assert retrieved_proxy.host == '127.0.0.1'
        assert retrieved_proxy.port == 8080
        
        # Test that users can put proxy back
        proxy_pool.put(retrieved_proxy)

    @pytest.mark.asyncio
    async def test_proxy_json_api_contract(self):
        """Test Proxy.as_json() contract that users depend on.
        
        The JSON structure must remain stable for users who parse output.
        """
        proxy = Proxy('8.8.8.8', 3128)
        proxy._runtimes = [1.5, 2.0, 2.5]
        proxy.types.update({'HTTP': 'Anonymous', 'HTTPS': None})
        
        json_data = proxy.as_json()
        
        # Test required fields that users depend on
        assert json_data['host'] == '8.8.8.8'
        assert json_data['port'] == 3128
        assert 'geo' in json_data
        assert 'types' in json_data
        assert 'avg_resp_time' in json_data
        assert 'error_rate' in json_data
        
        # Test types structure
        assert len(json_data['types']) == 2
        assert any(t['type'] == 'HTTP' and t['level'] == 'Anonymous' for t in json_data['types'])
        assert any(t['type'] == 'HTTPS' and t['level'] == '' for t in json_data['types'])

    @pytest.mark.asyncio
    async def test_broker_serve_api_contract(self):
        """Test Broker.serve() API that users depend on.
        
        This is the main server interface from examples/proxy_server.py.
        """
        broker = Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
        
        # Mock external dependencies
        with patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1'):
            with patch.object(broker, '_grab', return_value=None):
                with patch('proxybroker.server.Server') as MockServer:
                    mock_server = MagicMock()
                    MockServer.return_value = mock_server
                    mock_server.start = AsyncMock()
                    
                    # Test the serve API contract
                    await broker.serve(
                        host='127.0.0.1',
                        port=8888,
                        types=['HTTP', 'HTTPS'],
                        limit=10,
                        prefer_connect=True,
                        min_req_proxy=5,
                        max_error_rate=0.5,
                        max_resp_time=8
                    )
                    
                    # Verify the server was configured correctly
                    MockServer.assert_called_once()
                    mock_server.start.assert_called_once()

    def test_proxy_text_representation(self):
        """Test proxy string representations that users see.
        
        Users depend on readable proxy information for debugging.
        """
        proxy = Proxy('8.8.8.8', 80)
        proxy._runtimes = [1, 3, 3]
        proxy.types.update({'HTTP': 'Anonymous', 'HTTPS': None})
        
        # Test __repr__ output users see in logs/debug
        repr_str = repr(proxy)
        assert '8.8.8.8:80' in repr_str
        assert 'HTTP: Anonymous' in repr_str
        assert 'HTTPS' in repr_str
        
        # Test as_text() output for saving to files
        text_str = proxy.as_text()
        assert text_str == '8.8.8.8:80'

    @pytest.mark.asyncio
    async def test_broker_grab_workflow(self):
        """Test Broker.grab() workflow for finding proxies without checking.
        
        This is used when users want fast proxy discovery.
        """
        broker = Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
        
        with patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1'):
            with patch.object(broker, '_grab', return_value=None):
                # Test grab API contract
                await broker.grab(countries=['US'], limit=5)
                
                # Verify configuration
                assert broker._countries == ['US']
                assert broker._limit == 5
                assert broker._checker is None  # No checking in grab mode

    def test_proxy_creation_api(self):
        """Test Proxy creation APIs that users depend on."""
        # Test direct creation
        proxy = Proxy('127.0.0.1', 8080)
        assert proxy.host == '127.0.0.1'
        assert proxy.port == 8080
        
        # Test validation - users depend on proper error handling
        with pytest.raises(ValueError):
            Proxy('127.0.0.1', 65536)  # Port too high

    @pytest.mark.asyncio
    async def test_proxy_async_creation(self):
        """Test Proxy.create() async API."""
        # Mock DNS resolution
        with patch('proxybroker.resolver.Resolver.resolve') as mock_resolve:
            mock_resolve.return_value = [('127.0.0.1', 0)]
            
            proxy = await Proxy.create('127.0.0.1', 8080)
            assert proxy.host == '127.0.0.1'
            assert proxy.port == 8080


class TestErrorHandling:
    """Test error handling patterns users depend on."""
    
    @pytest.mark.asyncio
    async def test_no_proxy_error_contract(self):
        """Test NoProxyError is raised when no proxies available.
        
        Users catch this exception to handle empty proxy pools.
        """
        proxies = asyncio.Queue()
        proxy_pool = ProxyPool(proxies, min_req_proxy=1, max_error_rate=0.5, max_resp_time=5)
        
        # When no proxies available, should raise NoProxyError
        with pytest.raises(NoProxyError):
            await proxy_pool.get(scheme='http')

    def test_proxy_validation_errors(self):
        """Test proxy validation errors users handle."""
        # Invalid port
        with pytest.raises(ValueError, match="Port must be"):
            Proxy('127.0.0.1', 65536)
        
        # Invalid host format gets caught during IP validation


class TestPublicAPIStability:
    """Test that public API signatures remain stable."""
    
    def test_broker_init_signature(self):
        """Test Broker.__init__ signature stability."""
        # Users depend on these parameter names and defaults
        broker = Broker(
            queue=None,
            timeout=8,
            max_conn=200,
            max_tries=3,
            judges=None,
            providers=None,
            verify_ssl=False,
            stop_broker_on_sigint=True
        )
        
        # Verify defaults are set correctly
        assert broker._timeout == 8
        assert broker._max_tries == 3
        assert broker._verify_ssl is False

    def test_proxy_pool_init_signature(self):
        """Test ProxyPool.__init__ signature stability."""
        proxies = asyncio.Queue()
        pool = ProxyPool(
            proxies=proxies,
            min_req_proxy=5,
            max_error_rate=0.5,
            max_resp_time=8,
            min_queue=2,
            strategy='best'
        )
        
        assert pool._min_req_proxy == 5
        assert pool._max_error_rate == 0.5
        assert pool._max_resp_time == 8

    def test_exported_classes(self):
        """Test that all expected classes are properly exported."""
        from proxybroker import Broker, Proxy, ProxyPool, Checker, Judge, Provider
        
        # Verify all main classes are available to users
        assert Broker is not None
        assert Proxy is not None
        assert ProxyPool is not None
        assert Server is not None
        assert Checker is not None
        assert Judge is not None
        assert Provider is not None