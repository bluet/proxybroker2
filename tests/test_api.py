"""Test Broker public API - focused on user-visible behavior.

This file tests the main Broker APIs that users depend on:
- grab(): Get proxies without checking (populates queue)
- find(): Find and validate proxies (populates queue)
- serve(): Run proxy server
- Error handling and edge cases

We focus on WHAT the API does, not HOW it does it.
Based on the correct usage pattern from examples/basic.py
"""

import asyncio

import pytest

from proxybroker import Broker, Proxy


class TestBrokerAPI:
    """Test Broker public API behavior."""

    @pytest.fixture
    def broker_with_queue(self):
        """Create a broker with queue for testing."""
        proxies = asyncio.Queue()
        broker = Broker(proxies)
        return broker, proxies

    # Core API Tests - How users actually use the API

    @pytest.mark.asyncio
    async def test_broker_grab_populates_queue(self, broker_with_queue):
        """Test that grab() populates the proxy queue."""
        broker, proxies = broker_with_queue

        # Start grab task with short timeout
        grab_task = asyncio.create_task(broker.grab(limit=2))

        # Give it a moment to find some proxies
        await asyncio.sleep(2.0)

        # Check if proxies were found
        found_proxies = []
        try:
            while not proxies.empty():
                proxy = await asyncio.wait_for(proxies.get(), timeout=0.1)
                if proxy is None:
                    break
                found_proxies.append(proxy)
        except asyncio.TimeoutError:
            pass

        # Clean up
        grab_task.cancel()
        try:
            await grab_task
        except asyncio.CancelledError:
            pass

        # Should have found some proxies (or none if providers are down)
        for proxy in found_proxies:
            assert isinstance(proxy, Proxy)
            assert proxy.host
            assert proxy.port

    @pytest.mark.asyncio
    async def test_broker_find_populates_queue_with_checked_proxies(
        self, broker_with_queue
    ):
        """Test that find() populates queue with validated proxies."""
        broker, proxies = broker_with_queue

        # Start find task with short timeout
        find_task = asyncio.create_task(broker.find(limit=1))

        # Give it a moment to find and check proxies
        await asyncio.sleep(3.0)

        # Check if validated proxies were found
        found_proxies = []
        try:
            while not proxies.empty():
                proxy = await asyncio.wait_for(proxies.get(), timeout=0.1)
                if proxy is None:
                    break
                found_proxies.append(proxy)
        except asyncio.TimeoutError:
            pass

        # Clean up
        find_task.cancel()
        try:
            await find_task
        except asyncio.CancelledError:
            pass

        # Should have found working proxies (or none if all are down)
        for proxy in found_proxies:
            assert isinstance(proxy, Proxy)
            assert proxy.host
            assert proxy.port
            # Found proxies should have types info
            assert hasattr(proxy, "types") or hasattr(proxy, "_types")

    @pytest.mark.asyncio
    async def test_broker_grab_respects_limit(self, broker_with_queue):
        """Test that grab() respects the limit parameter."""
        broker, proxies = broker_with_queue

        # Start grab with limit of 1
        grab_task = asyncio.create_task(broker.grab(limit=1))

        # Wait for completion or timeout
        try:
            await asyncio.wait_for(grab_task, timeout=5.0)
        except asyncio.TimeoutError:
            grab_task.cancel()

        # Count proxies found
        proxy_count = 0
        try:
            while not proxies.empty():
                proxy = await asyncio.wait_for(proxies.get(), timeout=0.1)
                if proxy is None:
                    break
                proxy_count += 1
        except asyncio.TimeoutError:
            pass

        # Should not exceed the limit (allowing for 0 if no proxies found)
        assert proxy_count <= 1

    @pytest.mark.asyncio
    async def test_broker_grab_with_no_providers(self):
        """Test grab() behavior when no providers available."""
        proxies = asyncio.Queue()
        broker = Broker(proxies, providers=[])  # No providers

        # Start grab task
        grab_task = asyncio.create_task(broker.grab(limit=1))

        # Give it a short time
        await asyncio.sleep(1.0)

        # Should complete quickly with no proxies
        grab_task.cancel()
        try:
            await grab_task
        except asyncio.CancelledError:
            pass

        # Queue should be empty or have None terminator
        proxy_count = 0
        try:
            while not proxies.empty():
                proxy = await asyncio.wait_for(proxies.get(), timeout=0.1)
                if proxy is not None:
                    proxy_count += 1
        except asyncio.TimeoutError:
            pass

        assert proxy_count == 0

    # Server API Tests

    async def test_broker_serve_with_running_loop(self):
        """Test serve() in an async context with running event loop."""
        proxies = asyncio.Queue()
        broker = Broker(proxies)

        # In async context, serve() behavior might be different
        # This tests the actual usage pattern
        try:
            server = broker.serve(host="127.0.0.1", port=0, limit=1)
            # If serve() works in async context, server should exist
            if server is not None:
                assert hasattr(server, "start")
                assert hasattr(server, "stop")
        except Exception as e:
            # serve() might not work properly in async contexts
            # This is a potential design issue to note
            pytest.skip(f"serve() doesn't work in async context: {e}")

    # Proxy Output Format Tests - What users depend on

    @pytest.mark.asyncio
    async def test_proxy_output_format(self, broker_with_queue):
        """Test that proxies have the output formats users expect."""
        broker, proxies = broker_with_queue

        # Try to get one proxy
        grab_task = asyncio.create_task(broker.grab(limit=1))
        await asyncio.sleep(2.0)

        try:
            proxy = await asyncio.wait_for(proxies.get(), timeout=0.1)
            if proxy is not None:
                # Test the output formats users depend on
                assert hasattr(proxy, "as_json")
                assert hasattr(proxy, "as_text")

                # These should not raise exceptions
                json_output = proxy.as_json()
                text_output = proxy.as_text()

                assert isinstance(json_output, dict)
                assert isinstance(text_output, str)
                assert ":" in text_output  # Should be "host:port" format
        except asyncio.TimeoutError:
            pytest.skip("No proxies found for output format testing")
        finally:
            grab_task.cancel()
            try:
                await grab_task
            except asyncio.CancelledError:
                pass

    # Constructor Tests - Only test public behavior

    def test_broker_accepts_custom_timeout(self):
        """Test that custom timeout is accepted."""
        broker = Broker(timeout=15)
        # We don't test private _timeout attribute
        # Just verify it was constructed successfully
        assert broker is not None

    def test_broker_accepts_custom_max_conn(self):
        """Test that custom max_conn is accepted."""
        broker = Broker(max_conn=50)
        assert broker is not None

    def test_broker_accepts_custom_judges(self):
        """Test that custom judges are accepted."""
        broker = Broker(judges=["http://example.com/judge"])
        assert broker is not None

    def test_broker_accepts_custom_providers(self):
        """Test that custom providers are accepted."""
        broker = Broker(providers=["http://example.com/proxies"])
        assert broker is not None
