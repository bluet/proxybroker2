from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Proxy
from proxybroker.errors import BadResponseError, BadStatusError


@pytest.fixture
def mock_proxy():
    """Create a mock proxy for testing negotiators."""
    proxy = MagicMock(spec=Proxy)
    proxy.host = "127.0.0.1"
    proxy.port = 8080
    proxy.send = AsyncMock()
    proxy.recv = AsyncMock()
    proxy.connect = AsyncMock()
    proxy.log = MagicMock()
    proxy.get_log = MagicMock(return_value=[])
    return proxy


class TestNegotiatorBehavior:
    """Test negotiators from user perspective - do they successfully establish proxy connections?"""

    @pytest.mark.parametrize(
        "protocol,check_anon_lvl,use_full_path",
        [
            ("SOCKS5", False, False),
            ("SOCKS4", False, False),
            ("CONNECT:80", False, False),
            ("CONNECT:25", False, False),
            ("HTTPS", False, False),
            ("HTTP", True, True),
        ],
    )
    def test_negotiator_attributes(
        self, mock_proxy, protocol, check_anon_lvl, use_full_path
    ):
        """Test that negotiators have correct protocol attributes."""
        # This test validates the negotiator configuration that affects user behavior
        mock_proxy.ngtr = protocol
        assert mock_proxy.ngtr.name == protocol
        assert mock_proxy.ngtr.check_anon_lvl is check_anon_lvl
        assert mock_proxy.ngtr.use_full_path is use_full_path

    @pytest.mark.asyncio
    async def test_socks5_negotiation_success(self, mock_proxy):
        """Test successful SOCKS5 proxy negotiation."""
        mock_proxy.ngtr = "SOCKS5"

        # Mock successful SOCKS5 handshake responses
        mock_proxy.recv.side_effect = [
            b"\x05\x00",  # Authentication method accepted
            b"\x05\x00\x00\x01\xc0\xa8\x00\x18\xce\xdf",  # Connection established
        ]
        mock_proxy.get_log.return_value = [(None, "Request is granted")]

        # Act: Negotiate connection
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

        # Assert: Negotiation should complete successfully
        assert mock_proxy.send.call_count == 2  # Two handshake messages sent
        assert mock_proxy.recv.call_count == 2  # Two responses received

    @pytest.mark.asyncio
    async def test_socks4_negotiation_success(self, mock_proxy):
        """Test successful SOCKS4 proxy negotiation."""
        mock_proxy.ngtr = "SOCKS4"

        # Mock successful SOCKS4 response
        mock_proxy.recv.return_value = (
            b"\x00Z\x00\x00\x00\x00\x00\x00"  # Request granted
        )
        mock_proxy.get_log.return_value = [(None, "Request is granted")]

        # Act: Negotiate connection
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

        # Assert: Negotiation should complete successfully
        assert mock_proxy.send.call_count == 1  # One handshake message sent
        assert mock_proxy.recv.call_count == 1  # One response received

    @pytest.mark.asyncio
    async def test_connect_negotiation_success(self, mock_proxy):
        """Test successful HTTP CONNECT proxy negotiation."""
        mock_proxy.ngtr = "CONNECT:80"

        # Mock successful CONNECT response
        mock_proxy.recv.return_value = b"HTTP/1.1 200 Connection established\r\n\r\n"

        # Act: Negotiate connection
        await mock_proxy.ngtr.negotiate(host="example.com")

        # Assert: Negotiation should complete successfully
        assert mock_proxy.send.call_count == 1  # CONNECT request sent
        assert mock_proxy.recv.call_count == 1  # Response received

    @pytest.mark.asyncio
    async def test_https_negotiation_success(self, mock_proxy):
        """Test successful HTTPS proxy negotiation."""
        mock_proxy.ngtr = "HTTPS"

        # Mock successful HTTPS CONNECT response
        mock_proxy.recv.return_value = b"HTTP/1.1 200 Connection established\r\n\r\n"

        # Act: Negotiate connection
        await mock_proxy.ngtr.negotiate(host="example.com")

        # Assert: Negotiation should complete successfully
        assert mock_proxy.send.call_count == 1  # CONNECT request sent
        assert mock_proxy.recv.call_count == 1  # Response received

    @pytest.mark.asyncio
    async def test_smtp_connect_negotiation_success(self, mock_proxy):
        """Test successful SMTP CONNECT proxy negotiation."""
        mock_proxy.ngtr = "CONNECT:25"

        # Mock successful CONNECT response followed by SMTP greeting
        mock_proxy.recv.side_effect = [
            b"HTTP/1.1 200 Connection established\r\n\r\n",
            b"220 smtp.example.com",
        ]

        # Act: Negotiate connection
        await mock_proxy.ngtr.negotiate(host="smtp.example.com")

        # Assert: Negotiation should complete successfully
        assert mock_proxy.send.call_count == 1  # CONNECT request sent
        assert mock_proxy.recv.call_count == 2  # CONNECT response + SMTP greeting

    @pytest.mark.asyncio
    async def test_socks5_negotiation_failure(self, mock_proxy):
        """Test SOCKS5 negotiation failure scenarios."""
        mock_proxy.ngtr = "SOCKS5"

        # Mock authentication failure
        mock_proxy.recv.return_value = b"\x05\xff"  # No acceptable methods

        # Act & Assert: Should raise exception on negotiation failure
        with pytest.raises(BadResponseError):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_socks5_connection_failure(self, mock_proxy):
        """Test SOCKS5 connection failure after successful authentication."""
        mock_proxy.ngtr = "SOCKS5"

        # Mock successful auth but connection failure
        mock_proxy.recv.side_effect = [
            b"\x05\x00",  # Auth success
            b"\x05\x05",  # Connection refused by destination host
        ]

        # Act & Assert: Should raise exception on connection failure
        with pytest.raises(BadResponseError):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_socks4_negotiation_failure(self, mock_proxy):
        """Test SOCKS4 negotiation failure scenarios."""
        mock_proxy.ngtr = "SOCKS4"

        # Mock connection refused
        mock_proxy.recv.return_value = b"\x00["  # Request rejected or failed

        # Act & Assert: Should raise exception on negotiation failure
        with pytest.raises(BadResponseError):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_socks4_invalid_response(self, mock_proxy):
        """Test SOCKS4 with completely invalid response."""
        mock_proxy.ngtr = "SOCKS4"

        # Mock invalid HTTP response instead of SOCKS4
        mock_proxy.recv.return_value = b"HTTP/1.1 400 Bad Request"

        # Act & Assert: Should raise exception on invalid response
        with pytest.raises(BadResponseError):
            await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)

    @pytest.mark.asyncio
    async def test_connect_negotiation_failure(self, mock_proxy):
        """Test HTTP CONNECT negotiation failure scenarios."""
        mock_proxy.ngtr = "CONNECT:80"

        # Mock connection refused
        mock_proxy.recv.return_value = b"HTTP/1.1 400 Bad Request\r\n\r\n"

        # Act & Assert: Should raise exception on negotiation failure
        with pytest.raises(BadStatusError):
            await mock_proxy.ngtr.negotiate(host="example.com")

    @pytest.mark.asyncio
    async def test_connect_html_error_response(self, mock_proxy):
        """Test CONNECT with HTML error page response."""
        mock_proxy.ngtr = "CONNECT:80"

        # Mock HTML error page
        mock_proxy.recv.return_value = (
            b"<html>\r\n<head><title>400 Bad Request</title></head>\r\n"
        )

        # Act & Assert: Should raise exception on HTML error response
        with pytest.raises(BadStatusError):
            await mock_proxy.ngtr.negotiate(host="example.com")

    @pytest.mark.asyncio
    async def test_https_negotiation_failure(self, mock_proxy):
        """Test HTTPS negotiation failure scenarios."""
        mock_proxy.ngtr = "HTTPS"

        # Mock connection refused
        mock_proxy.recv.return_value = b"HTTP/1.1 403 Forbidden\r\n\r\n"

        # Act & Assert: Should raise exception on negotiation failure
        with pytest.raises(BadStatusError):
            await mock_proxy.ngtr.negotiate(host="example.com")

    @pytest.mark.asyncio
    async def test_smtp_connect_failure(self, mock_proxy):
        """Test SMTP CONNECT failure scenarios."""
        mock_proxy.ngtr = "CONNECT:25"

        # Mock CONNECT success but empty SMTP response
        mock_proxy.recv.side_effect = [
            b"HTTP/1.1 200 OK\r\n\r\n",
            b"",  # Empty SMTP response
        ]

        # Act & Assert: Should raise exception when SMTP greeting is missing
        with pytest.raises(BadStatusError):
            await mock_proxy.ngtr.negotiate(host="smtp.example.com")

    def test_protocol_specific_behavior(self, mock_proxy):
        """Test that different protocols have appropriate behavior characteristics."""
        # HTTP should check anonymity levels and use full paths
        mock_proxy.ngtr = "HTTP"
        assert mock_proxy.ngtr.check_anon_lvl is True
        assert mock_proxy.ngtr.use_full_path is True

        # SOCKS protocols should not check anonymity or use full paths
        mock_proxy.ngtr = "SOCKS5"
        assert mock_proxy.ngtr.check_anon_lvl is False
        assert mock_proxy.ngtr.use_full_path is False

        mock_proxy.ngtr = "SOCKS4"
        assert mock_proxy.ngtr.check_anon_lvl is False
        assert mock_proxy.ngtr.use_full_path is False

        # CONNECT protocols should not check anonymity or use full paths
        mock_proxy.ngtr = "CONNECT:80"
        assert mock_proxy.ngtr.check_anon_lvl is False
        assert mock_proxy.ngtr.use_full_path is False

    @pytest.mark.asyncio
    async def test_negotiation_with_different_ports(self, mock_proxy):
        """Test that negotiators work with different target ports."""
        mock_proxy.ngtr = "SOCKS5"

        # Test with standard HTTP port
        mock_proxy.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x01\xc0\xa8\x00\x18\x00\x50",
        ]
        mock_proxy.get_log.return_value = [(None, "Request is granted")]
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)
        assert mock_proxy.send.call_count == 2

        # Reset mocks for HTTPS port test
        mock_proxy.send.reset_mock()
        mock_proxy.recv.reset_mock()

        # Test with HTTPS port
        mock_proxy.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x01\xc0\xa8\x00\x18\x01\xbb",
        ]
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=443)
        assert mock_proxy.send.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_negotiation_rounds(self, mock_proxy):
        """Test that negotiators can handle multiple negotiation rounds correctly."""
        mock_proxy.ngtr = "SOCKS5"

        # First negotiation
        mock_proxy.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x01\xc0\xa8\x00\x18\xce\xdf",
        ]
        mock_proxy.get_log.return_value = [(None, "Request is granted")]
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=80)
        first_send_count = mock_proxy.send.call_count

        # Reset and second negotiation
        mock_proxy.send.reset_mock()
        mock_proxy.recv.reset_mock()
        mock_proxy.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x01\xc0\xa8\x00\x18\xce\xdf",
        ]
        await mock_proxy.ngtr.negotiate(ip="127.0.0.1", port=443)

        # Both should have same number of calls
        assert first_send_count == mock_proxy.send.call_count
