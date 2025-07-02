from __future__ import annotations

import asyncio
import struct

from abc import ABC, abstractmethod
from socket import inet_aton
from typing import Any

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
        "headers": "\r\n".join(("%s: %s" % (k, v) for k, v in kwargs.items())),
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

    # The concrete protocol name – assigned in subclasses.
    name: str | None = None
    # Whether anonymity level should be evaluated (HTTP only).
    check_anon_lvl: bool = False
    # Whether the full URI is required in the request line (HTTP only).
    use_full_path: bool = False

    def __init__(self, proxy) -> None:
        # Keep a strongly-typed reference to the parent proxy to satisfy the
        # linter when accessing ``send`` / ``recv`` etc.
        from .proxy import Proxy  # Local import to avoid circular dependency

        self._proxy: Proxy = proxy  # type: ignore[assignment]

    @abstractmethod
    async def negotiate(self, **kwargs: Any) -> None:
        """Negotiate with proxy."""


class Socks5Ngtr(BaseNegotiator):
    """SOCKS5 Negotiator."""

    name = "SOCKS5"

    async def negotiate(self, **kwargs: Any) -> None:
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

        ip_str = str(kwargs.get("ip", "0.0.0.0"))
        bip = inet_aton(ip_str)
        port = int(kwargs.get("port", 80))

        await self._proxy.send(struct.pack(">8BH", 5, 1, 0, 1, *bip, port))
        resp = await self._proxy.recv(10)

        if resp[0] != 0x05 or resp[1] != 0x00:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        else:
            self._proxy.log("Request is granted")


class Socks4Ngtr(BaseNegotiator):
    """SOCKS4 Negotiator."""

    name = "SOCKS4"

    async def negotiate(self, **kwargs: Any) -> None:
        ip_str = str(kwargs.get("ip", "0.0.0.0"))
        bip = inet_aton(ip_str)
        port = int(kwargs.get("port", 80))

        await self._proxy.send(struct.pack(">2BH5B", 4, 1, port, *bip, 0))
        resp = await self._proxy.recv(8)

        if resp[0] != 0x00 or resp[1] != 0x5A:
            self._proxy.log("Failed (invalid data)", err=BadResponseError)
            raise BadResponseError
        # resp = b'\x00Z\x00\x00\x00\x00\x00\x00' // ord('Z') == 90 == 0x5A
        else:
            self._proxy.log("Request is granted")


class Connect80Ngtr(BaseNegotiator):
    """CONNECT Negotiator."""

    name = "CONNECT:80"

    async def negotiate(self, **kwargs: Any) -> None:
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 80))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(
                "Connect: failed. HTTP status: %s" % code, err=BadStatusError
            )
            raise BadStatusError


class Connect25Ngtr(BaseNegotiator):
    """SMTP Negotiator (connect to 25 port)."""

    name = "CONNECT:25"

    async def negotiate(self, **kwargs: Any) -> None:
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 25))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(
                "Connect: failed. HTTP status: %s" % code, err=BadStatusError
            )
            raise BadStatusError

        resp = await self._proxy.recv(length=3)
        code = get_status_code(resp, start=0, stop=3)
        if code != SMTP_READY:
            self._proxy.log("Failed (invalid data): %s" % code, err=BadStatusError)
            raise BadStatusError


class HttpsNgtr(BaseNegotiator):
    """HTTPS Negotiator (CONNECT + SSL)."""

    name = "HTTPS"

    async def negotiate(self, **kwargs: Any) -> None:
        await self._proxy.send(_CONNECT_request(kwargs.get("host"), 443))
        resp = await self._proxy.recv(head_only=True)
        code = get_status_code(resp)
        if code != 200:
            self._proxy.log(
                "Connect: failed. HTTP status: %s" % code, err=BadStatusError
            )
            raise BadStatusError
        await self._proxy.connect(ssl=True)


class HttpNgtr(BaseNegotiator):
    """HTTP Negotiator."""

    name = "HTTP"
    check_anon_lvl = True
    use_full_path = True

    async def negotiate(self, **kwargs: Any) -> None:
        pass


NGTRS = {
    "HTTP": HttpNgtr,
    "HTTPS": HttpsNgtr,
    "SOCKS4": Socks4Ngtr,
    "SOCKS5": Socks5Ngtr,
    "CONNECT:80": Connect80Ngtr,
    "CONNECT:25": Connect25Ngtr,
}
