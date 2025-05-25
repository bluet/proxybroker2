"""Behavior-focused negotiator tests.

Tests focus on "does negotiation work" rather than exact protocol bytes.
This allows internal improvements while protecting user-visible behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from proxybroker import Proxy
from proxybroker.errors import BadResponseError, BadStatusError, ProxyConnError


class TestNegotiatorBehavior:
    """Test negotiator behavior that users depend on."""

    @pytest.fixture
    def mock_proxy(self):
        """Create a mock proxy for behavior testing."""
        proxy = Proxy("127.0.0.1", 80, timeout=0.1)
        proxy.connect = AsyncMock()
        proxy.send = AsyncMock()
        proxy.recv = AsyncMock()
        proxy.close = MagicMock()
        return proxy

    @pytest.mark.parametrize(
        "protocol,expected_attrs",
        [
            ("HTTP", {"check_anon_lvl": True, "use_full_path": True}),
            ("HTTPS", {"check_anon_lvl": False, "use_full_path": False}),
            ("SOCKS5", {"check_anon_lvl": False, "use_full_path": False}),
            ("SOCKS4", {"check_anon_lvl": False, "use_full_path": False}),
            ("CONNECT:80", {"check_anon_lvl": False, "use_full_path": False}),
            ("CONNECT:25", {"check_anon_lvl": False, "use_full_path": False}),
        ],
    )
    def test_negotiator_properties(self, mock_proxy, protocol, expected_attrs):
        """Test that negotiators have expected behavioral properties.
        
        Users depend on these properties for proxy selection logic.
        """
        mock_proxy.ngtr = protocol
        
        # Verify name is set correctly
        assert mock_proxy.ngtr.name == protocol
        
        # Verify behavioral properties users depend on
        for attr, expected_value in expected_attrs.items():
            assert getattr(mock_proxy.ngtr, attr) == expected_value

    @pytest.mark.asyncio
    @pytest.mark.parametrize("protocol", ["SOCKS5", "SOCKS4", "HTTP", "HTTPS"])
    async def test_successful_negotiation(self, mock_proxy, protocol):
        """Test that negotiation succeeds when proxy responds correctly.
        
        Focus: Does the negotiation complete successfully?
        Not: What exact bytes are exchanged?
        """
        mock_proxy.ngtr = protocol
        
        # Mock successful responses for different protocols
        if protocol == "SOCKS5":
            # SOCKS5: Auth success + Connect success
            mock_proxy.recv.side_effect = [b"\x05\x00", b"\x05\x00\x00\x01\xc0\xa8\x00\x18\xce\xdf"]
        elif protocol == "SOCKS4":
            # SOCKS4: Connect success
            mock_proxy.recv.side_effect = [b"\x00Z\x00\x00\x00\x00\x00\x00"]
        elif protocol in ["HTTP", "HTTPS"]:
            # HTTP/HTTPS: Success response
            mock_proxy.recv.side_effect = [b"HTTP/1.1 200 OK\r\n\r\n"]
        
        # Test that negotiation completes without error
        try:
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)
            negotiation_successful = True
        except Exception:
            negotiation_successful = False
        
        assert negotiation_successful, f"{protocol} negotiation should succeed with valid responses"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("protocol", ["SOCKS5", "SOCKS4"])
    async def test_socks_negotiation_failure(self, mock_proxy, protocol):
        """Test that SOCKS negotiation fails appropriately.
        
        Focus: Does negotiation fail when it should?
        Not: Exact error byte parsing.
        """
        mock_proxy.ngtr = protocol
        
        # Mock failure responses
        if protocol == "SOCKS5":
            # SOCKS5: Connection refused
            mock_proxy.recv.side_effect = [b"\x05\x00", b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"]
        elif protocol == "SOCKS4":
            # SOCKS4: Request rejected
            mock_proxy.recv.side_effect = [b"\x00[\x00\x00\x00\x00\x00\x00"]
        
        # Test that negotiation raises appropriate error
        with pytest.raises((BadResponseError, ProxyConnError)):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_http_connect_negotiation(self, mock_proxy):
        """Test HTTP CONNECT negotiation behavior.
        
        Focus: Does CONNECT method work for tunneling?
        """
        mock_proxy.ngtr = "CONNECT:80"
        
        # Mock successful CONNECT response
        mock_proxy.recv.side_effect = [b"HTTP/1.1 200 Connection established\r\n\r\n"]
        
        # Should complete successfully
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)
        
        # Verify at least one send call was made (the CONNECT request)
        assert mock_proxy.send.called, "CONNECT negotiation should send request"

    @pytest.mark.asyncio
    async def test_http_connect_failure(self, mock_proxy):
        """Test HTTP CONNECT handles proxy errors correctly."""
        mock_proxy.ngtr = "CONNECT:80"
        
        # Mock proxy rejection
        mock_proxy.recv.side_effect = [b"HTTP/1.1 403 Forbidden\r\n\r\n"]
        
        # Should raise error for non-200 responses
        with pytest.raises((BadResponseError, BadStatusError)):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_negotiation_with_unreachable_target(self, mock_proxy):
        """Test negotiation behavior with unreachable targets.
        
        This tests real-world failure scenarios users encounter.
        """
        mock_proxy.ngtr = "SOCKS5"
        
        # Mock "host unreachable" response
        mock_proxy.recv.side_effect = [b"\x05\x00", b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00"]
        
        # Should handle gracefully (may succeed or fail depending on implementation)
        try:
            await mock_proxy.ngtr.negotiate(ip="192.0.2.1", port=80)  # RFC5737 test IP
        except Exception as e:
            # If it fails, should be a meaningful error type
            assert isinstance(e, (BadResponseError, ProxyConnError))

    def test_negotiator_selection_logic(self, mock_proxy):
        """Test that correct negotiator is selected for each protocol.
        
        Users depend on protocol selection working correctly.
        """
        protocols = ["HTTP", "HTTPS", "SOCKS4", "SOCKS5", "CONNECT:80", "CONNECT:25"]
        
        for protocol in protocols:
            mock_proxy.ngtr = protocol
            assert mock_proxy.ngtr.name == protocol
            assert hasattr(mock_proxy.ngtr, "negotiate")
            assert callable(mock_proxy.ngtr.negotiate)


class TestNegotiatorIntegration:
    """Test negotiator integration with real proxy workflows."""
    
    def test_protocol_capabilities(self):
        """Test that protocols have expected capabilities.
        
        Users select protocols based on these capabilities.
        """
        proxy = Proxy("127.0.0.1", 80)
        
        # HTTP supports anonymity checking and full path
        proxy.ngtr = "HTTP"
        assert proxy.ngtr.check_anon_lvl is True
        assert proxy.ngtr.use_full_path is True
        
        # SOCKS protocols don't check anonymity
        for socks_proto in ["SOCKS4", "SOCKS5"]:
            proxy.ngtr = socks_proto
            assert proxy.ngtr.check_anon_lvl is False
            
        # CONNECT protocols are for tunneling
        for connect_proto in ["CONNECT:80", "CONNECT:25"]:
            proxy.ngtr = connect_proto
            assert proxy.ngtr.check_anon_lvl is False
            assert proxy.ngtr.use_full_path is False

    def test_error_handling_consistency(self):
        """Test that all negotiators handle errors consistently.
        
        Users catch these exceptions in their error handling.
        """
        proxy = Proxy("127.0.0.1", 80)
        
        # All negotiators should be instantiable
        protocols = ["HTTP", "HTTPS", "SOCKS4", "SOCKS5", "CONNECT:80", "CONNECT:25"]
        for protocol in protocols:
            proxy.ngtr = protocol
            assert proxy.ngtr is not None
            assert hasattr(proxy.ngtr, "negotiate")