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

    def test_connect_request_does_not_double_bracket(self):
        """If caller passes an already-bracketed v6 host (e.g. from
        urlparse('https://[2001:db8::1]/').netloc), don't emit
        `CONNECT [[2001:db8::1]]:443` which standards-compliant proxies
        will reject.
        """
        from proxybroker.negotiators import _CONNECT_request

        req = _CONNECT_request("[2001:db8::1]", 443).decode()
        assert "CONNECT [2001:db8::1]:443 HTTP/1.1\r\n" in req
        assert "[[" not in req
        assert "]]" not in req
        assert "\r\nHost: [2001:db8::1]\r\n" in req


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
    async def test_socks5_dual_stack_proxy_returns_v6_bnd_for_v4_request(self):
        """RFC 1928 § 6: BND.ADDR can be a different family than the
        client requested (dual-stack proxy may bind v6 even for a v4
        request). Negotiator must parse reply ATYP from the response,
        not assume it matches the request.
        """
        from unittest.mock import AsyncMock, MagicMock

        from proxybroker.negotiators import Socks5Ngtr

        mock_proxy = MagicMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(
            side_effect=[
                bytes([0x05, 0x00]),
                # Client requested v4 dest, but proxy bound v6 → ATYP=0x04.
                # Old code that derived reply_size from the *request* atyp
                # would under-read by 12 bytes and stall.
                bytes([0x05, 0x00, 0x00, 0x04]),
                bytes(18),
            ]
        )

        ngtr = Socks5Ngtr(mock_proxy)
        await ngtr.negotiate(ip="192.0.2.5", port=8080)
        # Three recvs: greeting, header, body. The negotiator correctly
        # noticed the response was v6 even though the request was v4.
        assert mock_proxy.recv.call_count == 3

    @pytest.mark.asyncio
    async def test_socks5_ipv4_destination_emits_atyp_01_4_bytes(self):
        from unittest.mock import AsyncMock, MagicMock

        from proxybroker.negotiators import Socks5Ngtr

        mock_proxy = MagicMock()
        mock_proxy.send = AsyncMock()
        # Three recv calls: greeting reply, fixed 4-byte connect-reply
        # header (VER+REP+RSV+ATYP), then variable BND.ADDR+BND.PORT.
        # Negotiator parses ATYP from the response, not the request.
        mock_proxy.recv = AsyncMock(
            side_effect=[
                bytes([0x05, 0x00]),  # greeting reply
                bytes([0x05, 0x00, 0x00, 0x01]),  # connect-reply header (v4 BND)
                bytes(6),  # 4-byte v4 BND.ADDR + 2-byte BND.PORT
            ]
        )

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
        # Three recv calls: greeting reply, fixed 4-byte connect-reply
        # header with ATYP=0x04 (v6), then 16-byte BND.ADDR + 2-byte
        # BND.PORT. Confirms the negotiator reads in two stages and
        # picks reply_size from the response ATYP, not the request ATYP.
        mock_proxy.recv = AsyncMock(
            side_effect=[
                bytes([0x05, 0x00]),  # greeting reply
                bytes([0x05, 0x00, 0x00, 0x04]),  # connect-reply header (v6 BND)
                bytes(18),  # 16-byte v6 BND.ADDR + 2-byte BND.PORT
            ]
        )

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

    @pytest.mark.asyncio
    async def test_socks4_ipv6_raises_bad_response_with_clear_message(self):
        """SOCKS4 has no v6 address type. Callers asking for v6 get a
        domain-specific BadResponseError pointing them to SOCKS5 - not
        a cryptic OSError from inet_aton.
        """
        from unittest.mock import MagicMock

        from proxybroker.errors import BadResponseError
        from proxybroker.negotiators import Socks4Ngtr

        mock_proxy = MagicMock()
        ngtr = Socks4Ngtr(mock_proxy)
        with pytest.raises(BadResponseError) as exc_info:
            await ngtr.negotiate(ip="2001:db8::1", port=443)
        assert "IPv6" in str(exc_info.value)
