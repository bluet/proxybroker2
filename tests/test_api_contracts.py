"""Simplified tests for critical API contracts that must remain stable.

These tests ensure backward compatibility for the most important user-facing APIs.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from proxybroker import Broker, Proxy, ProxyPool, Server
from proxybroker.errors import NoProxyError


class TestCriticalAPIContracts:
    """Test the most critical API contracts that users depend on."""

    def test_broker_basic_creation(self):
        """Test Broker can be created with common parameter patterns."""
        # Default creation
        broker1 = Broker(stop_broker_on_sigint=False)
        assert broker1._timeout == 8
        assert broker1._max_tries == 3

        # With parameters users commonly use
        broker2 = Broker(timeout=5, max_conn=100, stop_broker_on_sigint=False)
        assert broker2._timeout == 5

    @pytest.mark.asyncio
    async def test_broker_find_basic_contract(self):
        """Test Broker.find() basic API contract."""
        broker = Broker(timeout=0.1, max_tries=1, stop_broker_on_sigint=False)

        with patch.object(
            broker._resolver, "get_real_ext_ip", return_value="127.0.0.1"
        ):
            with patch.object(broker, "_grab", return_value=None):
                # Test basic find call patterns users depend on
                await broker.find(types=["HTTP", "HTTPS"], limit=5)
                assert broker._limit == 5

                # Test find with countries
                await broker.find(types=["HTTP"], countries=["US"], limit=2)
                assert broker._countries == ["US"]

    @pytest.mark.asyncio
    async def test_broker_grab_basic_contract(self):
        """Test Broker.grab() basic API contract."""
        broker = Broker(timeout=0.1, max_tries=1, stop_broker_on_sigint=False)

        with patch.object(
            broker._resolver, "get_real_ext_ip", return_value="127.0.0.1"
        ):
            with patch.object(broker, "_grab", return_value=None):
                # Test basic grab call patterns
                await broker.grab(countries=["US"], limit=10)
                assert broker._countries == ["US"]
                assert broker._limit == 10

    def test_proxy_basic_creation_and_properties(self):
        """Test Proxy creation and basic properties."""
        # Basic creation
        proxy = Proxy("127.0.0.1", 8080)
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 8080

        # With additional parameters
        proxy2 = Proxy("8.8.8.8", 3128, timeout=10)
        assert proxy2._timeout == 10

    def test_proxy_json_output_structure(self):
        """Test Proxy.as_json() returns expected structure."""
        proxy = Proxy("8.8.8.8", 3128)
        proxy._runtimes = [1.0, 2.0]
        proxy.types.update({"HTTP": "Anonymous"})

        json_data = proxy.as_json()

        # Essential fields users depend on
        assert "host" in json_data
        assert "port" in json_data
        assert "types" in json_data
        assert "avg_resp_time" in json_data
        assert "error_rate" in json_data
        assert "geo" in json_data

        assert json_data["host"] == "8.8.8.8"
        assert json_data["port"] == 3128
        assert isinstance(json_data["types"], list)

    def test_proxy_text_output(self):
        """Test Proxy.as_text() format."""
        proxy = Proxy("127.0.0.1", 8080)
        text = proxy.as_text()
        # Users depend on this format for saving to files
        assert "127.0.0.1:8080" in text
        assert isinstance(text, str)

    def test_proxy_repr_readable(self):
        """Test Proxy.__repr__ is human readable."""
        proxy = Proxy("8.8.8.8", 80)
        proxy.types.update({"HTTP": "Anonymous"})

        repr_str = repr(proxy)
        # Users see this in logs and debug output
        assert "8.8.8.8:80" in repr_str
        assert "HTTP" in repr_str

    @pytest.mark.asyncio
    async def test_proxy_create_async_factory(self):
        """Test Proxy.create() async factory method."""
        with patch("proxybroker.resolver.Resolver.resolve") as mock_resolve:
            mock_resolve.return_value = "127.0.0.1"  # Return IP string, not list

            proxy = await Proxy.create("example.com", 8080)
            assert proxy.host == "127.0.0.1"
            assert proxy.port == 8080

    def test_proxy_pool_basic_usage(self):
        """Test ProxyPool basic creation and usage patterns."""
        proxies = asyncio.Queue()

        # Basic creation
        pool = ProxyPool(proxies)
        assert pool._min_req_proxy == 5  # Default value

        # With custom parameters
        pool2 = ProxyPool(proxies, min_req_proxy=3, max_error_rate=0.3)
        assert pool2._min_req_proxy == 3
        assert pool2._max_error_rate == 0.3

    @pytest.mark.asyncio
    async def test_proxy_pool_get_put_cycle(self):
        """Test ProxyPool get/put cycle that users depend on."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies, min_req_proxy=1)

        # Create a good proxy
        proxy = Proxy("127.0.0.1", 8080)
        proxy._types = {"HTTP": "Anonymous"}  # Set internal attribute
        proxy._runtimes = [1.0]
        proxy.stat = {"requests": 1, "errors": {}}

        # Test the cycle users depend on
        await proxies.put(proxy)
        retrieved = await pool.get("http")
        assert retrieved is not None

        # Put it back
        pool.put(retrieved)

    @pytest.mark.asyncio
    async def test_proxy_pool_empty_raises_error(self):
        """Test ProxyPool raises NoProxyError when empty."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies)

        # Users catch this exception
        with pytest.raises(NoProxyError):
            await pool.get("http")

    def test_server_basic_creation(self):
        """Test Server basic creation patterns."""
        proxies = MagicMock()

        # Basic creation
        server = Server("localhost", 8888, proxies)
        assert server.host == "localhost"
        assert server.port == 8888

        # With options
        server2 = Server("127.0.0.1", 9999, proxies, timeout=10, backlog=50)
        assert server2._timeout == 10
        assert server2._backlog == 50

    def test_error_inheritance_stability(self):
        """Test that error classes maintain inheritance."""
        from proxybroker.errors import (
            ProxyError,
            NoProxyError,
            ProxyConnError,
            ProxyTimeoutError,
        )

        # Users catch these exception types
        assert issubclass(ProxyConnError, ProxyError)
        assert issubclass(ProxyTimeoutError, ProxyError)
        assert issubclass(NoProxyError, Exception)

    def test_main_module_imports(self):
        """Test that main classes can be imported as expected."""
        # Users do: from proxybroker import Broker, Proxy, etc.
        from proxybroker import Broker, Proxy, ProxyPool, Server

        assert Broker is not None
        assert Proxy is not None
        assert ProxyPool is not None
        assert Server is not None

    def test_proxy_validation_errors(self):
        """Test Proxy validation raises appropriate errors."""
        # Users depend on validation working
        with pytest.raises(ValueError):
            Proxy("127.0.0.1", 65536)  # Port too high

        with pytest.raises(ValueError):
            Proxy("127.0.0.1", None)  # No port
