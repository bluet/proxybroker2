import asyncio
import ssl
import time
from asyncio.streams import StreamReader

import pytest

from proxybroker import Proxy
from proxybroker.errors import ProxyConnError, ProxyTimeoutError, ResolveError
from proxybroker.negotiators import HttpsNgtr
from proxybroker.utils import log as logger

from .utils import ResolveResult


def test_ssl_context_unverified_by_default():
    """When verify_ssl is False (the default for proxy testing),
    self._ssl_context must be a real SSLContext with cert verification
    fully disabled. Guards the migration from the private
    ssl._create_unverified_context() to the public
    ssl.create_default_context() + override path.
    """
    p = Proxy("127.0.0.1", "80", verify_ssl=False)
    assert isinstance(p._ssl_context, ssl.SSLContext)
    assert p._ssl_context.check_hostname is False
    assert p._ssl_context.verify_mode == ssl.CERT_NONE


def test_ssl_context_verified_when_requested():
    """verify_ssl=True keeps the True sentinel - existing contract."""
    p = Proxy("127.0.0.1", "80", verify_ssl=True)
    assert p._ssl_context is True


def test_proxy_accepts_ipv6_host_literal():
    """Proxy(host=v6) must construct without raising.

    Relies on Resolver.host_is_ip accepting v6 literals (L1).
    Geo-info lookup tolerates absent v6 ranges in the bundled
    GeoLite2 DB and falls back to "Unknown".
    """
    p = Proxy("2001:db8::1", "8080")
    assert p.host == "2001:db8::1"
    assert p.port == 8080


def test_proxy_rejects_v6_with_brackets():
    """Brackets are URI authority syntax (RFC 3986), not the literal
    host - must NOT be accepted as a Proxy host. Caller should strip
    brackets before constructing.
    """
    with pytest.raises(ValueError):
        Proxy("[2001:db8::1]", "8080")


def test_proxy_as_text_brackets_v6():
    """as_text emits standard host:port form. For IPv6 hosts, RFC 3986
    requires brackets so the colon doesn't ambiguate against the port.
    """
    v4 = Proxy("127.0.0.1", "80")
    assert v4.as_text() == "127.0.0.1:80\n"

    v6 = Proxy("2001:db8::1", "8080")
    assert v6.as_text() == "[2001:db8::1]:8080\n"


def test_proxy_repr_brackets_v6():
    """repr() of a v6-host proxy must bracket the host so logs are
    unambiguous.
    """
    p = Proxy("2001:db8::1", "8080")
    assert "[2001:db8::1]:8080" in repr(p)


@pytest.fixture
async def proxy():
    # async fixture so pytest-asyncio sets up an event loop first.
    # StreamReader() requires a running loop on Python 3.14+
    # (was a DeprecationWarning on 3.10-3.13, became RuntimeError in 3.14).
    proxy = Proxy("127.0.0.1", "80", timeout=0.1)
    proxy._reader["conn"] = StreamReader()
    return proxy


@pytest.mark.asyncio
async def test_create_by_ip():
    assert isinstance(await Proxy.create("127.0.0.1", "80"), Proxy)
    with pytest.raises(ValueError):
        await Proxy.create("127.0.0.1", "65536")
    with pytest.raises(ResolveError):
        await Proxy.create("256.0.0.1", "80")


@pytest.mark.asyncio
async def test_create_by_domain(mocker):
    # Resolver.resolve() races A and AAAA in parallel (Happy Eyeballs DNS,
    # RFC 8305 § 3). Mock provides a v4 record for A and explicitly fails
    # AAAA so the v4 result wins deterministically.
    import aiodns

    a_future = asyncio.Future()
    a_future.set_result([ResolveResult("127.0.0.1", 0)])

    def query_side_effect(host, qtype):
        if qtype == "A":
            return a_future
        raise aiodns.error.DNSError(1, "no AAAA record (test)")

    mocker.patch("aiodns.DNSResolver.query", side_effect=query_side_effect)
    proxy = await Proxy.create("testhost.com", "80")
    assert proxy.host == "127.0.0.1"


def test_repr():
    p = Proxy("8.8.8.8", "80")
    p._runtimes = [1, 3, 3]
    p.types.update({"HTTP": "Anonymous", "HTTPS": None})
    assert repr(p) == "<Proxy US 2.33s [HTTP: Anonymous, HTTPS] 8.8.8.8:80>"

    p = Proxy("4.4.4.4", "8080")
    p.types.update({"SOCKS4": None, "SOCKS5": None})
    assert repr(p) == "<Proxy US 0.00s [SOCKS4, SOCKS5] 4.4.4.4:8080>"

    p = Proxy("127.0.0.1", "3128")
    assert repr(p) == "<Proxy -- 0.00s [] 127.0.0.1:3128>"


def test_as_json_w_geo():
    p = Proxy("8.8.8.8", "3128")
    p._runtimes = [1, 3, 3]
    p.types.update({"HTTP": "Anonymous", "HTTPS": None})

    json_tpl = {
        "host": "8.8.8.8",
        "port": 3128,
        "geo": {
            "country": {"code": "US", "name": "United States"},
            "region": {"code": "Unknown", "name": "Unknown"},
            "city": "Unknown",
        },
        "types": [
            {"type": "HTTP", "level": "Anonymous"},
            {"type": "HTTPS", "level": ""},
        ],
        "avg_resp_time": 2.33,
        "error_rate": 0,
    }
    assert p.as_json() == json_tpl


def test_as_json_wo_geo():
    p = Proxy("127.0.0.1", "80")
    p.log("MSG", time.time(), ProxyConnError)
    p.stat["requests"] = 4

    json_tpl = {
        "host": "127.0.0.1",
        "port": 80,
        "geo": {
            "country": {"code": "--", "name": "Unknown"},
            "region": {"code": "Unknown", "name": "Unknown"},
            "city": "Unknown",
        },
        "types": [],
        "avg_resp_time": 0,
        "error_rate": 0.25,
    }
    assert p.as_json() == json_tpl


def test_schemes():
    p = Proxy("127.0.0.1", "80")
    p.types.update({"HTTP": "Anonymous", "HTTPS": None})
    assert p.schemes == ("HTTP", "HTTPS")

    p = Proxy("127.0.0.1", "80")
    p.types["HTTPS"] = None
    assert p.schemes == ("HTTPS",)

    p = Proxy("127.0.0.1", "80")
    p.types.update({"SOCKS4": None, "SOCKS5": None})
    assert p.schemes == ("HTTP", "HTTPS")


def test_avg_resp_time():
    p = Proxy("127.0.0.1", "80")
    assert p.avg_resp_time == 0.0
    p._runtimes = [1, 3, 4]
    assert p.avg_resp_time == 2.67


def test_error_rate():
    p = Proxy("127.0.0.1", "80")
    p.log("Error", time.time(), ProxyConnError)
    p.log("Error", time.time(), ProxyConnError)
    p.stat["requests"] = 4
    assert p.error_rate == 0.5


def test_geo():
    p = Proxy("127.0.0.1", "80")
    assert p.geo.code == "--"
    assert p.geo.name == "Unknown"

    p = Proxy("8.8.8.8", "80")
    assert p.geo.code == "US"
    assert p.geo.name == "United States"


def test_ngtr():
    p = Proxy("127.0.0.1", "80")
    p.ngtr = "HTTPS"
    assert isinstance(p.ngtr, HttpsNgtr)
    assert p.ngtr._proxy is p


def test_log(log):
    p = Proxy("127.0.0.1", "80")
    msg = "MSG"
    stime = time.time()
    err = ProxyConnError

    assert p.get_log() == []
    assert p._runtimes == []

    with log(logger.name, level="DEBUG") as cm:
        p.log(msg)
        p.ngtr = "HTTP"
        p.log(msg)
        assert ("INFO", msg, 0) in p.get_log()
        assert ("HTTP", msg, 0) in p.get_log()
        assert len(p.stat["errors"]) == 0
        assert p._runtimes == []
        assert cm.output == [
            "DEBUG:proxybroker:127.0.0.1:80 [INFO]: MSG; Runtime: 0.00",
            "DEBUG:proxybroker:127.0.0.1:80 [HTTP]: MSG; Runtime: 0.00",
        ]

    p.log(msg, stime, err)
    p.log(msg, stime, err)
    assert len(p.stat["errors"]) == 1
    assert sum(p.stat["errors"].values()) == 2
    assert p.stat["errors"][err.errmsg] == 2
    assert round(p._runtimes[-1], 2) == 0.0

    len_runtimes = len(p._runtimes)
    p.log(msg + "timeout", stime)
    assert len(p._runtimes) == len_runtimes

    msg = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do"
    p.log(msg)
    last_msg = p.get_log()[-1][1]
    cropped = msg[:60] + "..."
    assert last_msg == cropped


@pytest.mark.asyncio
async def test_recv(proxy):
    resp = b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\nabcdef\n"
    proxy.reader.feed_data(resp)
    assert await proxy.recv() == resp


@pytest.mark.asyncio
async def test_recv_eof(proxy):
    resp = b"HTTP/1.1 200 OK\r\n\r\nabcdef"
    proxy.reader.feed_data(resp)
    proxy.reader.feed_eof()
    assert await proxy.recv() == resp


@pytest.mark.asyncio
async def test_recv_length(proxy):
    proxy.reader.feed_data(b"abc")
    assert await proxy.recv(length=3) == b"abc"
    proxy.reader._buffer.clear()

    proxy.reader.feed_data(b"abcdef")
    assert await proxy.recv(length=3) == b"abc"
    assert await proxy.recv(length=3) == b"def"
    proxy.reader._buffer.clear()

    proxy.reader.feed_data(b"ab")
    with pytest.raises(ProxyTimeoutError):
        await proxy.recv(length=3)


@pytest.mark.asyncio
async def test_recv_head_only(proxy):
    data = b"HTTP/1.1 200 Connection established\r\n\r\n"
    proxy.reader.feed_data(data)
    assert await proxy.recv(head_only=True) == data
    proxy.reader._buffer.clear()

    data = b"HTTP/1.1 200 OK\r\nServer: 0\r\n\r\n"
    proxy.reader.feed_data(data + b"abcd")
    assert await proxy.recv(head_only=True) == data
    proxy.reader._buffer.clear()

    proxy.reader.feed_data(b"<html>abc</html>")
    with pytest.raises(ProxyTimeoutError):
        await proxy.recv(head_only=True)


@pytest.mark.asyncio
async def test_recv_content_length(proxy):
    resp = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n{a}\n"
    proxy.reader.feed_data(resp)
    assert await proxy.recv() == resp


@pytest.mark.asyncio
async def test_recv_content_encoding(proxy):
    resp = (
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n"
        b"Content-Length: 7\r\n\r\n\x1f\x8b\x08\x00\n\x00\x00"
    )
    proxy.reader.feed_data(resp)
    proxy.reader.feed_eof()
    assert await proxy.recv() == resp


@pytest.mark.asyncio
async def test_recv_content_encoding_without_eof(proxy):
    resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Encoding: gzip\r\n"
        b"Content-Length: 7\r\n\r\n"
        b"\x1f\x8b\x08\x00\n\x00\x00"
    )
    proxy.reader.feed_data(resp)
    with pytest.raises(ProxyTimeoutError):
        await proxy.recv()


@pytest.mark.asyncio
async def test_recv_content_encoding_chunked(proxy):
    resp = (
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n3\x1f\x8b\x00\r\n0\r\n"
    )
    proxy.reader.feed_data(resp)
    assert await proxy.recv() == resp
    proxy.reader._buffer.clear()

    resp = (
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"5a" + b"\x1f" * 90 + b"\r\n\r\n0\r\n"
    )
    proxy.reader.feed_data(resp)
    assert await proxy.recv() == resp
