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
    kw = {
        "host": host,
        "port": port,
        "headers": "\r\n".join((f"{k}: {v}" for k, v in kwargs.items())),
    }
    req = (
        (
            "CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}\r\n"
            "{headers}\r\nConnection: keep-alive\r\n\r\n"
        )
        .format(**kw)
        .encode()
    )
    return req


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
        # Reply size: VER(1)+REP(1)+RSV(1)+ATYP(1)+BND.ADDR(4 or 16)+BND.PORT(2)
        reply_size = 22 if atyp == 0x04 else 10
        resp = await self._proxy.recv(reply_size)

        if resp[0] != 0x05 or resp[1] != 0x00:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        else:
            self._proxy.log("Request is granted")


class Socks4Ngtr(BaseNegotiator):
    """SOCKS4 Negotiator."""

    name = "SOCKS4"

    async def negotiate(self, **kwargs):
        bip = inet_aton(kwargs.get("ip"))
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
