import asyncio
import ipaddress
import struct
from abc import ABC, abstractmethod
from socket import inet_aton

from .errors import BadResponseError, BadStatusError
from .utils import get_headers, get_status_code

__all__ = [
    "Socks5Ngtr",
    "Socks4Ngtr",
    "Connect80Ngtr",
    "Connect25Ngtr",
    "HttpsNgtr",
    "HttpNgtr",
    "NGTRS",
]


SMTP_READY = 220


def _CONNECT_request(host, port, **kwargs):
    kwargs.setdefault("User-Agent", get_headers()["User-Agent"])
    # RFC 9112 § 3.2.3 (request-target authority-form) and RFC 9110 § 7.2
    # (Host header field) both require IPv6 literals to be bracketed in
    # URI authority components. Without brackets, "CONNECT 2001:db8::1:443"
    # is ambiguous (where does the host end and the port begin?) and
    # standards-compliant proxies will reject it.
    #
    # Strip any caller-supplied brackets first so callers passing values
    # straight from `urlparse('https://[2001:db8::1]/').netloc` (already
    # bracketed) don't end up with double brackets like
    # `[[2001:db8::1]]:443`.
    host_str = str(host)
    if host_str.startswith("[") and host_str.endswith("]"):
        host_str = host_str[1:-1]
    if ":" in host_str:
        authority = f"[{host_str}]:{port}"
        host_header = f"[{host_str}]"
    else:
        authority = f"{host_str}:{port}"
        host_header = f"{host_str}"
    headers = "\r\n".join(f"{k}: {v}" for k, v in kwargs.items())
    return (
        f"CONNECT {authority} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        f"{headers}\r\nConnection: keep-alive\r\n\r\n"
    ).encode()


class BaseNegotiator(ABC):
    """Base Negotiator."""

    name = None
    check_anon_lvl = False
    use_full_path = False

    def __init__(self, proxy):
        self._proxy = proxy

    @abstractmethod
    async def negotiate(self, **kwargs):
        """Negotiate with proxy."""


class Socks5Ngtr(BaseNegotiator):
    """SOCKS5 Negotiator."""

    name = "SOCKS5"

    async def negotiate(self, **kwargs):
        await self._proxy.send(struct.pack("3B", 5, 1, 0))
        resp = await self._proxy.recv(2)

        if not isinstance(resp, (bytes, str)):
            raise TypeError(f"{type(resp).__name__} is not supported")
        if resp[0] == 0x05 and resp[1] == 0xFF:
            self._proxy.log("Failed (auth is required)", err=BadResponseError)
            raise BadResponseError
        elif resp[0] != 0x05 or resp[1] != 0x00:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError

        # SOCKS5 (RFC 1928) supports IPv4 (ATYP=0x01, 4 bytes) and IPv6
        # (ATYP=0x04, 16 bytes). We dispatch on `ipaddress.ip_address`
        # rather than catching `inet_aton` failures so the encoding is
        # explicit and v6-only callers don't pay an exception round-trip.
        addr = ipaddress.ip_address(kwargs.get("ip"))
        port = kwargs.get("port", 80)
        if isinstance(addr, ipaddress.IPv6Address):
            atyp = 0x04
        else:
            atyp = 0x01
        # VER(1) + CMD(1) + RSV(1) + ATYP(1) + ADDR(4 or 16) + PORT(2)
        request = (
            struct.pack(">4B", 5, 1, 0, atyp) + addr.packed + struct.pack(">H", port)
        )

        await self._proxy.send(request)
        # Per RFC 1928 § 6, the reply's BND.ADDR can be a different
        # address family from the client's request - dual-stack proxies
        # may bind to v6 even when the client requested v4 (or vice
        # versa). So we must read the 4-byte fixed header first
        # (VER+REP+RSV+ATYP), inspect the *response* ATYP, then read
        # the variable-length BND.ADDR + BND.PORT.
        header = await self._proxy.recv(4)
        if header[0] != 0x05 or header[1] != 0x00:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        rep_atyp = header[3]
        if rep_atyp == 0x01:  # IPv4
            addr_len = 4
        elif rep_atyp == 0x04:  # IPv6
            addr_len = 16
        elif rep_atyp == 0x03:  # Domain name (1-byte length prefix)
            length = await self._proxy.recv(1)
            addr_len = length[0]
        else:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        # Drain BND.ADDR + BND.PORT (2 bytes); we don't use them.
        await self._proxy.recv(addr_len + 2)
        self._proxy.log("Request is granted")


class Socks4Ngtr(BaseNegotiator):
    """SOCKS4 Negotiator.

    SOCKS4 (RFC 1928 lacks SOCKS4; original Ying-Da Lee spec) only
    defines a 4-byte IPv4 address field - there is no ATYP byte and
    no IPv6 address type. Callers attempting v6 destinations get a
    domain-specific BadResponseError instead of a cryptic
    `OSError: illegal IP address string passed to inet_aton`.
    """

    name = "SOCKS4"

    async def negotiate(self, **kwargs):
        ip = kwargs.get("ip")
        try:
            addr = ipaddress.ip_address(ip) if ip else None
        except ValueError:
            addr = None
        if isinstance(addr, ipaddress.IPv6Address):
            self._proxy.log(
                "Failed (SOCKS4 does not support IPv6 destinations; "
                "use SOCKS5 for IPv6)",
                err=BadResponseError,
            )
            raise BadResponseError("SOCKS4 protocol does not support IPv6 destinations")
        bip = inet_aton(ip)
        port = kwargs.get("port", 80)

        await self._proxy.send(struct.pack(">2BH5B", 4, 1, port, *bip, 0))
        resp = await self._proxy.recv(8)
        if isinstance(resp, asyncio.Future):
            resp = await resp
        assert not isinstance(resp, asyncio.Future)

        if resp[0] != 0x00 or resp[1] != 0x5A:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        # resp = b'\x00Z\x00\x00\x00\x00\x00\x00' // ord('Z') == 90 == 0x5A
        else:
            self._proxy.log("Request is granted")


class Connect80Ngtr(BaseNegotiator):
    """CONNECT Negotiator."""

    name = "CONNECT:80"

    async def negotiate(self, **kwargs):
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 80))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(f"Connect: failed. HTTP status: {code}", err=BadStatusError)
            raise BadStatusError


class Connect25Ngtr(BaseNegotiator):
    """SMTP Negotiator (connect to 25 port)."""

    name = "CONNECT:25"

    async def negotiate(self, **kwargs):
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 25))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(f"Connect: failed. HTTP status: {code}", err=BadStatusError)
            raise BadStatusError

        resp = await self._proxy.recv(length=3)
        code = get_status_code(resp, start=0, stop=3)
        if code != SMTP_READY:
            self._proxy.log(f"Failed (invalid data): {code}", err=BadStatusError)
            raise BadStatusError


class HttpsNgtr(BaseNegotiator):
    """HTTPS Negotiator (CONNECT + SSL)."""

    name = "HTTPS"

    async def negotiate(self, **kwargs):
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 443))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(f"Connect: failed. HTTP status: {code}", err=BadStatusError)
            raise BadStatusError
        await self._proxy.connect(ssl=True)


class HttpNgtr(BaseNegotiator):
    """HTTP Negotiator."""

    name = "HTTP"
    check_anon_lvl = True
    use_full_path = True

    async def negotiate(self, **kwargs):
        pass


NGTRS = {
    "HTTP": HttpNgtr,
    "HTTPS": HttpsNgtr,
    "SOCKS4": Socks4Ngtr,
    "SOCKS5": Socks5Ngtr,
    "CONNECT:80": Connect80Ngtr,
    "CONNECT:25": Connect25Ngtr,
}
