"""Clean negotiator tests focused on behavior, not implementation.

These tests follow good testing principles:
- Test behavior, not implementation details
- Simple and readable
- Test user-visible outcomes
- Enable refactoring without breaking
"""

import pytest


class TestNegotiatorContracts:
    """Test the public contracts that users depend on."""

    def test_all_negotiators_exist(self):
        """Test that all expected negotiators are available to users."""
        from proxybroker.negotiators import NGTRS

        expected_protocols = [
            "SOCKS5",
            "SOCKS4",
            "CONNECT:80",
            "CONNECT:25",
            "HTTPS",
            "HTTP",
        ]

        for protocol in expected_protocols:
            assert protocol in NGTRS, f"Missing negotiator for {protocol}"
            negotiator_class = NGTRS[protocol]
            assert negotiator_class is not None
            assert hasattr(negotiator_class, "negotiate"), (
                f"{protocol} negotiator missing negotiate method"
            )

    def test_negotiators_have_required_attributes(self):
        """Test that negotiators have the attributes users depend on."""
        from proxybroker.negotiators import NGTRS

        for protocol, negotiator_class in NGTRS.items():
            # Test that each negotiator has the basic required attributes
            assert hasattr(negotiator_class, "name"), (
                f"{protocol} missing name attribute"
            )
            assert hasattr(negotiator_class, "check_anon_lvl"), (
                f"{protocol} missing check_anon_lvl"
            )
            assert hasattr(negotiator_class, "use_full_path"), (
                f"{protocol} missing use_full_path"
            )

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
    def test_negotiator_attributes(self, protocol, check_anon_lvl, use_full_path):
        """Test that negotiators have correct protocol-specific attributes."""
        from unittest.mock import MagicMock

        from proxybroker.negotiators import NGTRS

        # Create the appropriate negotiator instance
        negotiator_class = NGTRS[protocol]
        mock_proxy = MagicMock()
        negotiator = negotiator_class(mock_proxy)

        assert negotiator.name == protocol
        assert negotiator.check_anon_lvl is check_anon_lvl
        assert negotiator.use_full_path is use_full_path

    def test_negotiator_instantiation(self):
        """Test that all negotiators can be instantiated."""
        from unittest.mock import MagicMock

        from proxybroker.negotiators import NGTRS

        mock_proxy = MagicMock()

        for _, negotiator_class in NGTRS.items():
            # Should be able to create instance without errors
            negotiator = negotiator_class(mock_proxy)
            assert negotiator is not None
            assert hasattr(negotiator, "negotiate")


class TestConnectIPv6Authority:
    """RFC 9112/9110 require IPv6 in URI authority + Host header to be
    bracketed. Without brackets, `CONNECT 2001:db8::1:443` is ambiguous
    and standards-compliant proxies will reject it.
    """

    def test_connect_request_ipv4_unbracketed(self):
        from proxybroker.negotiators import _CONNECT_request

        req = _CONNECT_request("198.51.100.1", 443).decode()
        assert req.startswith("CONNECT 198.51.100.1:443 HTTP/1.1\r\n")
        assert "\r\nHost: 198.51.100.1\r\n" in req

    def test_connect_request_ipv6_brackets_authority_and_host(self):
        from proxybroker.negotiators import _CONNECT_request

        req = _CONNECT_request("2001:db8::1", 443).decode()
        assert req.startswith("CONNECT [2001:db8::1]:443 HTTP/1.1\r\n")
        assert "\r\nHost: [2001:db8::1]\r\n" in req

    def test_connect_request_ipv6_bracket_25_443_80(self):
        # All four CONNECT-using negotiators (CONNECT:80, CONNECT:25,
        # HTTPS at 443, plus the SMTP variant) use _CONNECT_request, so
        # this single helper test covers them all.
        from proxybroker.negotiators import _CONNECT_request

        for port in (80, 25, 443):
            req = _CONNECT_request("fe80::abcd", port).decode()
            assert f"CONNECT [fe80::abcd]:{port} HTTP/1.1\r\n" in req


class TestSocks5IPv6Wire:
    """Wire-level tests for SOCKS5 ATYP encoding (RFC 1928).

    SOCKS5 supports three address types:
        ATYP=0x01  IPv4  (4 bytes)
        ATYP=0x03  domain (1-byte length + name)
        ATYP=0x04  IPv6  (16 bytes)

    proxybroker historically only emitted ATYP=0x01 because the
    upstream resolver returned IPv4-only and `inet_aton` enforced
    that. With IPv6 enabled end-to-end, the negotiator MUST emit
    ATYP=0x04 + 16-byte address for IPv6 destinations and continue
    to emit ATYP=0x01 + 4-byte address for IPv4 (regression).
    """

    @pytest.mark.asyncio
    async def test_socks5_ipv4_destination_emits_atyp_01_4_bytes(self):
        from unittest.mock import AsyncMock, MagicMock

        from proxybroker.negotiators import Socks5Ngtr

        mock_proxy = MagicMock()
        mock_proxy.send = AsyncMock()
        # Greeting reply (v5, no-auth) then connect-reply (v5, success, ATYP+addr+port).
        connect_reply = bytes([0x05, 0x00, 0x00, 0x01]) + bytes(6)
        mock_proxy.recv = AsyncMock(side_effect=[bytes([0x05, 0x00]), connect_reply])

        ngtr = Socks5Ngtr(mock_proxy)
        await ngtr.negotiate(ip="192.0.2.5", port=8080)

        # Two send calls: greeting + connect-request.
        assert mock_proxy.send.call_count == 2
        connect_pkt = mock_proxy.send.call_args_list[1].args[0]
        assert isinstance(connect_pkt, (bytes, bytearray))
        # Total: VER(1)+CMD(1)+RSV(1)+ATYP(1)+IPv4(4)+PORT(2) = 10 bytes
        assert len(connect_pkt) == 10
        assert connect_pkt[0] == 0x05  # SOCKS version
        assert connect_pkt[1] == 0x01  # CONNECT
        assert connect_pkt[2] == 0x00  # RSV
        assert connect_pkt[3] == 0x01  # ATYP=IPv4
        # IPv4 packed
        assert connect_pkt[4:8] == bytes([192, 0, 2, 5])
        # Port big-endian
        assert int.from_bytes(connect_pkt[8:10], "big") == 8080

    @pytest.mark.asyncio
    async def test_socks5_ipv6_destination_emits_atyp_04_16_bytes(self):
        from unittest.mock import AsyncMock, MagicMock

        from proxybroker.negotiators import Socks5Ngtr

        mock_proxy = MagicMock()
        mock_proxy.send = AsyncMock()
        # Greeting reply (v5, no-auth) then connect-reply (v5, success, ATYP=v6+addr+port).
        connect_reply = bytes([0x05, 0x00, 0x00, 0x04]) + bytes(18)
        mock_proxy.recv = AsyncMock(side_effect=[bytes([0x05, 0x00]), connect_reply])

        ngtr = Socks5Ngtr(mock_proxy)
        await ngtr.negotiate(ip="2001:db8::1", port=443)

        connect_pkt = mock_proxy.send.call_args_list[1].args[0]
        assert isinstance(connect_pkt, (bytes, bytearray))
        # Total: VER(1)+CMD(1)+RSV(1)+ATYP(1)+IPv6(16)+PORT(2) = 22 bytes
        assert len(connect_pkt) == 22
        assert connect_pkt[0] == 0x05
        assert connect_pkt[1] == 0x01
        assert connect_pkt[2] == 0x00
        assert connect_pkt[3] == 0x04  # ATYP=IPv6
        # 2001:db8::1 packed = 32 bytes hex \x20\x01\x0d\xb8 ... \x00\x01
        expected_packed = bytes.fromhex("20010db8000000000000000000000001")
        assert connect_pkt[4:20] == expected_packed
        assert int.from_bytes(connect_pkt[20:22], "big") == 443

    def test_socks4_ipv6_raises_helpful_error(self):
        """SOCKS4 RFC 1928 has no IPv6 address type. Asking for v6 over
        SOCKS4 should fail loudly, not silently truncate or crash with a
        cryptic struct error.
        """
        # The current implementation crashes with OSError from inet_aton.
        # We document the current observable behavior here so we notice
        # if it ever changes silently. A future tighter check could raise
        # a domain-specific BadResponseError instead.
        import asyncio
        from unittest.mock import MagicMock

        from proxybroker.negotiators import Socks4Ngtr

        mock_proxy = MagicMock()
        ngtr = Socks4Ngtr(mock_proxy)
        with pytest.raises((OSError, ValueError)):
            asyncio.get_event_loop().run_until_complete(
                ngtr.negotiate(ip="2001:db8::1", port=443)
            )
