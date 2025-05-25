"""Tests for public API contracts that must remain stable.

These tests ensure that the public interfaces that users depend on remain
backward compatible. Changes that break these tests require major version bumps.

Focus: API signatures, return types, exception contracts, and data structures.
"""

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from proxybroker import Broker, Proxy, ProxyPool, Server
from proxybroker.errors import (
    ProxyError,
    NoProxyError,
    ResolveError,
    ProxyConnError,
    ProxyRecvError,
    ProxySendError,
    ProxyTimeoutError,
    ProxyEmptyRecvError,
)


class TestBrokerPublicContract:
    """Test Broker class public API contracts."""

    def test_broker_init_signature(self):
        """Test Broker.__init__ signature remains stable."""
        sig = inspect.signature(Broker.__init__)
        expected_params = {
            "self",
            "queue",
            "timeout",
            "max_conn",
            "max_tries",
            "judges",
            "providers",
            "verify_ssl",
            "loop",
            "stop_broker_on_sigint",
            "kwargs",
        }
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params, (
            f"Missing params: {expected_params - actual_params}"
        )

        # Test default values that users depend on
        params = sig.parameters
        assert params["timeout"].default == 8
        assert params["max_conn"].default == 200
        assert params["max_tries"].default == 3
        assert params["verify_ssl"].default is False
        assert params["stop_broker_on_sigint"].default is True

    @pytest.mark.asyncio
    async def test_broker_find_signature(self):
        """Test Broker.find() signature remains stable."""
        broker = Broker(timeout=0.1, max_tries=1, stop_broker_on_sigint=False)
        sig = inspect.signature(broker.find)

        expected_params = {
            "types",
            "data",
            "countries",
            "post",
            "strict",
            "dnsbl",
            "limit",
            "kwargs",
        }
        actual_params = set(sig.parameters.keys()) - {"self"}
        assert expected_params == actual_params

        # Test that method is async
        assert asyncio.iscoroutinefunction(broker.find)

    @pytest.mark.asyncio
    async def test_broker_grab_signature(self):
        """Test Broker.grab() signature remains stable."""
        broker = Broker(timeout=0.1, max_tries=1, stop_broker_on_sigint=False)
        sig = inspect.signature(broker.grab)

        expected_params = {"countries", "limit"}
        actual_params = set(sig.parameters.keys()) - {"self"}
        assert expected_params == actual_params

        assert asyncio.iscoroutinefunction(broker.grab)

    @pytest.mark.asyncio
    async def test_broker_serve_signature(self):
        """Test Broker.serve() signature remains stable."""
        broker = Broker(timeout=0.1, max_tries=1, stop_broker_on_sigint=False)
        sig = inspect.signature(broker.serve)

        # Core serve parameters users depend on
        expected_params = {
            "host",
            "port",
            "limit",
            "kwargs",
        }
        actual_params = set(sig.parameters.keys()) - {"self"}
        assert expected_params == actual_params

    def test_broker_show_stats_signature(self):
        """Test Broker.show_stats() signature remains stable."""
        broker = Broker(stop_broker_on_sigint=False)
        sig = inspect.signature(broker.show_stats)

        expected_params = {"verbose", "kwargs"}
        actual_params = set(sig.parameters.keys()) - {"self"}
        assert expected_params == actual_params


class TestProxyPublicContract:
    """Test Proxy class public API contracts."""

    def test_proxy_init_signature(self):
        """Test Proxy.__init__ signature remains stable."""
        sig = inspect.signature(Proxy.__init__)
        expected_params = {"self", "host", "port", "types", "timeout", "verify_ssl"}
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

    @pytest.mark.asyncio
    async def test_proxy_create_signature(self):
        """Test Proxy.create() classmethod signature remains stable."""
        sig = inspect.signature(Proxy.create)
        expected_params = {"host", "args", "kwargs"}
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

        assert asyncio.iscoroutinefunction(Proxy.create)

    def test_proxy_as_json_contract(self):
        """Test Proxy.as_json() return structure contract."""
        proxy = Proxy("8.8.8.8", 3128)
        proxy._runtimes = [1.0, 2.0]
        proxy.types.update({"HTTP": "Anonymous"})

        json_data = proxy.as_json()

        # Required fields in JSON output
        required_fields = {
            "host",
            "port",
            "geo",
            "types",
            "avg_resp_time",
            "error_rate",
        }
        assert set(json_data.keys()) == required_fields

        # Field type contracts
        assert isinstance(json_data["host"], str)
        assert isinstance(json_data["port"], int)
        assert isinstance(json_data["geo"], dict)
        assert isinstance(json_data["types"], list)
        assert isinstance(json_data["avg_resp_time"], (int, float))
        assert isinstance(json_data["error_rate"], (int, float))

        # Geo structure contract
        geo = json_data["geo"]
        assert "country" in geo
        assert "region" in geo
        assert "city" in geo
        assert "code" in geo["country"]
        assert "name" in geo["country"]

    def test_proxy_as_text_contract(self):
        """Test Proxy.as_text() return format contract."""
        proxy = Proxy("127.0.0.1", 8080)
        text = proxy.as_text()
        assert text == "127.0.0.1:8080\n"  # Include newline as per implementation
        assert isinstance(text, str)

    def test_proxy_repr_contract(self):
        """Test Proxy.__repr__ format contract."""
        proxy = Proxy("8.8.8.8", 80)
        proxy._runtimes = [1.5]
        proxy.types.update({"HTTP": "Anonymous"})

        repr_str = repr(proxy)

        # Required elements in repr
        assert "8.8.8.8:80" in repr_str
        assert "HTTP: Anonymous" in repr_str
        assert "<Proxy" in repr_str
        assert ">" in repr_str

    def test_proxy_validation_contracts(self):
        """Test Proxy validation error contracts."""
        # Invalid port should raise ValueError
        with pytest.raises(ValueError, match="cannot be greater than 65535"):
            Proxy("127.0.0.1", 65536)

        # None port should raise ValueError
        with pytest.raises(ValueError, match="cannot be None"):
            Proxy("127.0.0.1", None)


class TestProxyPoolPublicContract:
    """Test ProxyPool class public API contracts."""

    def test_proxy_pool_init_signature(self):
        """Test ProxyPool.__init__ signature remains stable."""
        sig = inspect.signature(ProxyPool.__init__)
        expected_params = {
            "self",
            "proxies",
            "min_req_proxy",
            "max_error_rate",
            "max_resp_time",
            "min_queue",
            "strategy",
        }
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

    @pytest.mark.asyncio
    async def test_proxy_pool_get_signature(self):
        """Test ProxyPool.get() signature remains stable."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies)
        sig = inspect.signature(pool.get)

        expected_params = {"scheme"}
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

        assert asyncio.iscoroutinefunction(pool.get)

    def test_proxy_pool_put_signature(self):
        """Test ProxyPool.put() signature remains stable."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies)
        sig = inspect.signature(pool.put)

        expected_params = {"proxy"}
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

    @pytest.mark.asyncio
    async def test_proxy_pool_get_error_contract(self):
        """Test ProxyPool.get() raises NoProxyError when empty."""
        proxies = asyncio.Queue()
        pool = ProxyPool(proxies)

        with pytest.raises(NoProxyError):
            await pool.get("http")


class TestServerPublicContract:
    """Test Server class public API contracts."""

    def test_server_init_signature(self):
        """Test Server.__init__ signature remains stable."""
        sig = inspect.signature(Server.__init__)
        expected_params = {
            "host",
            "port",
            "proxies",
            "timeout",
            "max_tries",
            "min_queue",
            "min_req_proxy",
            "max_error_rate",
            "max_resp_time",
            "prefer_connect",
            "http_allowed_codes",
            "backlog",
            "loop",
            "kwargs",
        }
        actual_params = set(sig.parameters.keys()) - {"self"}
        assert expected_params == actual_params

    @pytest.mark.asyncio
    async def test_server_start_signature(self):
        """Test Server.start() signature remains stable."""
        proxies = MagicMock()
        server = Server("localhost", 8888, proxies)
        sig = inspect.signature(server.start)

        # start() should take no parameters
        expected_params = set()
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

        assert asyncio.iscoroutinefunction(server.start)


class TestErrorContractStability:
    """Test that exception hierarchy and contracts remain stable."""

    def test_exception_hierarchy(self):
        """Test exception inheritance contracts."""
        # All proxy errors should inherit from ProxyError
        proxy_errors = [
            ProxyConnError,
            ProxyRecvError,
            ProxySendError,
            ProxyTimeoutError,
            ProxyEmptyRecvError,
        ]

        for error_class in proxy_errors:
            assert issubclass(error_class, ProxyError)
            assert issubclass(error_class, Exception)

        # Other errors should inherit from Exception
        assert issubclass(NoProxyError, Exception)
        assert issubclass(ResolveError, Exception)

    def test_error_message_attributes(self):
        """Test error classes have required attributes."""
        proxy_errors = [
            ProxyConnError,
            ProxyRecvError,
            ProxySendError,
            ProxyTimeoutError,
            ProxyEmptyRecvError,
        ]

        for error_class in proxy_errors:
            # Each should have an errmsg attribute
            assert hasattr(error_class, "errmsg")
            assert isinstance(error_class.errmsg, str)

    def test_error_instantiation(self):
        """Test errors can be instantiated with standard patterns."""
        # Test basic instantiation
        errors = [
            ProxyError("test"),
            NoProxyError("no proxies"),
            ResolveError("resolve failed"),
            ProxyConnError("connection failed"),
            ProxyTimeoutError("timeout"),
        ]

        for error in errors:
            assert str(error)  # Should have string representation


class TestExportedInterfaceStability:
    """Test that __all__ exports remain stable."""

    def test_main_module_exports(self):
        """Test main module exports the expected classes."""
        import proxybroker

        # Core classes that must be available
        required_exports = [
            "Broker",
            "Proxy",
            "ProxyPool",
            "Server",
            "Checker",
            "Judge",
            "Provider",
        ]

        for export_name in required_exports:
            assert hasattr(proxybroker, export_name), f"Missing export: {export_name}"

        # Verify they're the correct classes
        assert proxybroker.Broker is Broker
        assert proxybroker.Proxy is Proxy
        assert proxybroker.ProxyPool is ProxyPool
        assert proxybroker.Server is Server

    def test_error_module_exports(self):
        """Test error module exports remain stable."""
        from proxybroker import errors

        required_errors = [
            "ProxyError",
            "NoProxyError",
            "ResolveError",
            "ProxyConnError",
            "ProxyRecvError",
            "ProxySendError",
            "ProxyTimeoutError",
            "ProxyEmptyRecvError",
        ]

        for error_name in required_errors:
            assert hasattr(errors, error_name), f"Missing error: {error_name}"


class TestBackwardCompatibilityContracts:
    """Test backward compatibility requirements."""

    @pytest.mark.asyncio
    async def test_broker_legacy_parameters(self):
        """Test that deprecated parameters still work with warnings."""
        # Create broker with legacy parameter style in async context
        broker = Broker(timeout=5, max_conn=100, stop_broker_on_sigint=False)

        # Should work without error (may emit deprecation warnings)
        assert broker._timeout == 5

    def test_proxy_legacy_creation(self):
        """Test legacy Proxy creation patterns still work."""
        # Direct instantiation should work
        proxy = Proxy("127.0.0.1", 8080, timeout=5)
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 8080

        # With types parameter
        proxy = Proxy("127.0.0.1", 8080, types=["HTTP"])
        assert proxy.host == "127.0.0.1"

    def test_types_attribute_compatibility(self):
        """Test Proxy.types attribute remains dict-like."""
        proxy = Proxy("127.0.0.1", 8080)

        # Should support dict operations
        proxy.types["HTTP"] = "Anonymous"
        assert "HTTP" in proxy.types
        assert proxy.types["HTTP"] == "Anonymous"

        # Should support .update()
        proxy.types.update({"HTTPS": "High"})
        assert proxy.types["HTTPS"] == "High"
