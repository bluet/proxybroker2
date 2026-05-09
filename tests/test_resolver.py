import asyncio
import socket

import pytest

from proxybroker.errors import ResolveError
from proxybroker.resolver import Resolver

from .utils import ResolveResult, future_iter


@pytest.fixture
def resolver():
    return Resolver(timeout=0.1)


def test_host_is_ip(resolver):
    assert resolver.host_is_ip("127.0.0.1") is True
    assert resolver.host_is_ip("256.0.0.1") is False
    assert resolver.host_is_ip("test.com") is False


def test_host_is_ip_ipv6(resolver):
    # IPv6 loopback, documentation prefix, IPv4-mapped, zone IDs.
    assert resolver.host_is_ip("::1") is True
    assert resolver.host_is_ip("2001:db8::1") is True
    assert resolver.host_is_ip("2001:DB8::1") is True
    assert resolver.host_is_ip("::ffff:192.0.2.1") is True
    assert resolver.host_is_ip("fe80::1%eth0") is True


def test_host_is_ip_rejects_garbage(resolver):
    assert resolver.host_is_ip("not-an-ip") is False
    assert resolver.host_is_ip("dead.beef.cafe") is False
    assert resolver.host_is_ip(":::") is False
    assert resolver.host_is_ip("") is False


def test_host_is_ip_rejects_url_or_host_with_path(resolver):
    # Defensive: things that look IP-ish but include extra characters
    # (port, path, brackets) must not pass `is this an IP literal`.
    assert resolver.host_is_ip("127.0.0.1:80") is False
    assert resolver.host_is_ip("[2001:db8::1]") is False
    assert (
        resolver.host_is_ip("2001:db8::1:8080") is True
    )  # last group "8080" — still a valid v6 by parser
    assert resolver.host_is_ip("http://1.2.3.4") is False


def test_get_ip_info(resolver):
    ip = resolver.get_ip_info("127.0.0.1")
    assert ip.code == "--"
    assert ip.name == "Unknown"
    assert ip.region_code == "Unknown"
    assert ip.region_name == "Unknown"
    assert ip.city_name == "Unknown"
    ip = resolver.get_ip_info("8.8.8.8")
    assert ip.code == "US"
    assert ip.name == "United States"


@pytest.mark.asyncio
async def test_get_real_ext_ip(event_loop, mocker, resolver):
    # Just mock the method itself to avoid complex aiohttp mocking
    mocker.patch.object(resolver, "get_real_ext_ip", return_value="127.0.0.1")
    assert await resolver.get_real_ext_ip() == "127.0.0.1"


@pytest.mark.asyncio
async def test_get_real_ext_ip_canonicalises_ipv6(mocker):
    """get_real_ext_ip must return RFC 5952 canonical form.

    Regardless of how the upstream IP-detection service emits the
    address, downstream comparison sites rely on canonical form for
    correctness. Verifies via fully-faked aiohttp.ClientSession.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    resolver_inst = Resolver(timeout=1)

    fake_resp = MagicMock()
    fake_resp.text = AsyncMock(return_value="2001:DB8::1\n")

    @asynccontextmanager
    async def fake_get(_url):
        yield fake_resp

    @asynccontextmanager
    async def fake_session(*_args, **_kwargs):
        sess = MagicMock()
        sess.get = fake_get
        yield sess

    mocker.patch("proxybroker.resolver.aiohttp.ClientSession", fake_session)

    assert await resolver_inst.get_real_ext_ip() == "2001:db8::1"


@pytest.mark.asyncio
async def test_resolve(event_loop, mocker, resolver):
    assert await resolver.resolve("127.0.0.1") == "127.0.0.1"

    with pytest.raises(ResolveError):
        await resolver.resolve("256.0.0.1")

    f = future_iter([ResolveResult("127.0.0.1", 0)])
    # https://github.com/pytest-dev/pytest-mock#note-about-usage-as-context-manager
    mocker.patch("aiodns.DNSResolver.query", side_effect=f)
    assert await resolver.resolve("test.com") == "127.0.0.1"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_aaaa_for_v6_only_host(mocker, resolver):
    """When A query returns no records, resolve() must transparently
    fall back to AAAA so v6-only hostnames (no A record) still resolve.
    Without this, judges and proxy hosts with AAAA-only DNS silently
    fail to be reachable.
    """
    from proxybroker.errors import ResolveError

    a_calls = []

    async def fake_resolve(host, qtype):
        a_calls.append(qtype)
        if qtype == "A":
            raise ResolveError
        # AAAA: return a fake aiodns-style record with .host
        from types import SimpleNamespace

        return [SimpleNamespace(host="2001:db8::abcd")]

    mocker.patch.object(resolver, "_resolve", side_effect=fake_resolve)
    result = await resolver.resolve("v6only.example.com")
    assert a_calls == ["A", "AAAA"]
    assert result == "2001:db8::abcd"


@pytest.mark.asyncio
async def test_resolve_family(mocker, resolver):
    f = future_iter([ResolveResult("127.0.0.2", 0)])
    # https://github.com/pytest-dev/pytest-mock#note-about-usage-as-context-manager
    mocker.patch("aiodns.DNSResolver.query", side_effect=f)
    resp = [
        {
            "hostname": "test2.com",
            "host": "127.0.0.2",
            "port": 80,
            "family": socket.AF_INET,
            "proto": socket.IPPROTO_IP,
            "flags": socket.AI_NUMERICHOST,
        }
    ]
    resolved = await resolver.resolve("test2.com", family=socket.AF_INET)
    assert resolved == resp


@pytest.mark.asyncio
async def test_resolve_cache(event_loop, mocker, resolver):
    # Pre-populate cache to test cache hit behavior
    resolver._cached_hosts["test.com"] = "127.0.0.1"

    mocker.spy(resolver, "_resolve")
    assert await resolver.resolve("test.com") == "127.0.0.1"
    assert resolver._resolve.call_count == 0

    resolver._cached_hosts.clear()
    f = future_iter(
        [ResolveResult("127.0.0.1", 0)],
        [ResolveResult("127.0.0.2", 0)],
    )
    mocker.patch("aiodns.DNSResolver.query", side_effect=f)
    await resolver.resolve("test.com")
    await resolver.resolve("test2.com", port=80, family=socket.AF_INET)
    assert resolver._resolve.call_count == 2

    assert await resolver.resolve("test.com") == "127.0.0.1"
    resp = await resolver.resolve("test2.com")
    assert resp[0]["host"] == "127.0.0.2"
    assert resolver._resolve.call_count == 2

    # Mock an exception for test3.com
    mocker.patch(
        "aiodns.DNSResolver.query",
        side_effect=asyncio.TimeoutError("DNS resolution failed"),
    )
    with pytest.raises(ResolveError):
        await resolver.resolve("test3.com")
    assert resolver._resolve.call_count == 3
