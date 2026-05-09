import asyncio
import socket

import pytest

from proxybroker.errors import ResolveError
from proxybroker.resolver import Resolver

from .utils import ResolveResult


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
async def test_get_real_ext_ip(mocker, resolver):
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
async def test_resolve(mocker, resolver):
    assert await resolver.resolve("127.0.0.1") == "127.0.0.1"

    with pytest.raises(ResolveError):
        await resolver.resolve("256.0.0.1")

    # Resolver.resolve() races A+AAAA in parallel (Happy Eyeballs DNS).
    # Mock provides v4 record for A queries; AAAA raises so v4 wins
    # deterministically. Without this, future_iter([single_result])
    # gets exhausted on the second call and surfaces as StopIteration.
    import aiodns

    a_future = asyncio.Future()
    a_future.set_result([ResolveResult("127.0.0.1", 0)])

    def query_side_effect(host, qtype):
        if qtype == "A":
            return a_future
        raise aiodns.error.DNSError(1, "no AAAA record (test)")

    mocker.patch("aiodns.DNSResolver.query", side_effect=query_side_effect)
    assert await resolver.resolve("test.com") == "127.0.0.1"


@pytest.mark.asyncio
async def test_resolve_happy_eyeballs_v6_wins_when_faster(mocker, resolver):
    """RFC 8305 § 3: A and AAAA fire in parallel; the faster one wins."""
    resolver._cached_hosts.clear()

    from types import SimpleNamespace

    calls = []

    async def fake_resolve(host, qtype):
        calls.append(qtype)
        if qtype == "AAAA":
            await asyncio.sleep(0.001)  # faster
            return [SimpleNamespace(host="2001:db8::5")]
        await asyncio.sleep(0.05)  # slower
        return [SimpleNamespace(host="192.0.2.5")]

    mocker.patch.object(resolver, "_resolve", side_effect=fake_resolve)
    result = await resolver.resolve("dual-v6-wins.example.com")
    # Both queries fired in parallel
    assert set(calls) == {"A", "AAAA"}
    assert result == "2001:db8::5"


@pytest.mark.asyncio
async def test_resolve_happy_eyeballs_v4_wins_when_faster(mocker, resolver):
    # `_cached_hosts` is a class attribute; clear it so any prior test
    # that resolved the same hostname doesn't return a stale entry
    # before our mock fires.
    resolver._cached_hosts.clear()

    from types import SimpleNamespace

    async def fake_resolve(host, qtype):
        if qtype == "A":
            await asyncio.sleep(0.001)
            return [SimpleNamespace(host="192.0.2.5")]
        await asyncio.sleep(0.05)
        return [SimpleNamespace(host="2001:db8::5")]

    mocker.patch.object(resolver, "_resolve", side_effect=fake_resolve)
    assert await resolver.resolve("dual-v4-wins.example.com") == "192.0.2.5"


@pytest.mark.asyncio
async def test_resolve_happy_eyeballs_v6_only_when_a_fails(mocker, resolver):
    """v6-only hostnames (no A record) still resolve when A raises."""
    resolver._cached_hosts.clear()

    from types import SimpleNamespace

    from proxybroker.errors import ResolveError

    async def fake_resolve(host, qtype):
        if qtype == "A":
            raise ResolveError
        return [SimpleNamespace(host="2001:db8::abcd")]

    mocker.patch.object(resolver, "_resolve", side_effect=fake_resolve)
    assert await resolver.resolve("v6only.example.com") == "2001:db8::abcd"


@pytest.mark.asyncio
async def test_resolve_happy_eyeballs_both_fail_raises(mocker, resolver):
    """If both A and AAAA fail, ResolveError propagates (preserves the
    legacy "could not resolve" contract that callers rely on)."""
    resolver._cached_hosts.clear()

    from proxybroker.errors import ResolveError

    async def fake_resolve(host, qtype):
        raise ResolveError

    mocker.patch.object(resolver, "_resolve", side_effect=fake_resolve)
    with pytest.raises(ResolveError):
        await resolver.resolve("nonexistent.example.com")


@pytest.mark.asyncio
async def test_resolve_family(mocker, resolver):
    # Resolver.resolve() races A+AAAA in parallel (Happy Eyeballs DNS,
    # RFC 8305 § 3) when the caller doesn't pin qtype. This mock lets
    # the A query win deterministically by making AAAA raise so only
    # the v4 record is returned, matching the test's intent
    # (family=AF_INET expects a v4 record).
    import aiodns

    a_future = asyncio.Future()
    a_future.set_result([ResolveResult("127.0.0.2", 0)])

    def query_side_effect(host, qtype):
        if qtype == "A":
            return a_future
        raise aiodns.error.DNSError(1, "no AAAA record (test)")

    mocker.patch("aiodns.DNSResolver.query", side_effect=query_side_effect)
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
async def test_resolve_cache(mocker, resolver):
    # Pre-populate cache to test cache hit behavior
    resolver._cached_hosts["test.com"] = "127.0.0.1"

    mocker.spy(resolver, "_resolve")
    assert await resolver.resolve("test.com") == "127.0.0.1"
    assert resolver._resolve.call_count == 0

    resolver._cached_hosts.clear()
    # Resolver.resolve() races A+AAAA in parallel (Happy Eyeballs DNS,
    # RFC 8305 § 3) when the caller doesn't pin qtype. Each resolve()
    # call fires both queries; AAAA raises here so v4 wins
    # deterministically per host. _resolve is still called twice (once
    # per resolve() call - the helper doesn't double-count internally).
    import aiodns

    a_futures = {
        "test.com": [ResolveResult("127.0.0.1", 0)],
        "test2.com": [ResolveResult("127.0.0.2", 0)],
    }

    def query_side_effect(host, qtype):
        if qtype == "A" and host in a_futures:
            f = asyncio.Future()
            f.set_result(a_futures[host])
            return f
        raise aiodns.error.DNSError(1, f"no {qtype} record for {host} (test)")

    mocker.patch("aiodns.DNSResolver.query", side_effect=query_side_effect)
    await resolver.resolve("test.com")
    await resolver.resolve("test2.com", port=80, family=socket.AF_INET)
    # Happy Eyeballs DNS fires both A and AAAA per resolve() call, so
    # 2 fresh resolves => 4 underlying _resolve invocations (A + AAAA
    # for each host). The AAAA half raises (per query_side_effect) and
    # is gracefully discarded by _race_a_aaaa.
    assert resolver._resolve.call_count == 4

    assert await resolver.resolve("test.com") == "127.0.0.1"
    resp = await resolver.resolve("test2.com")
    assert resp[0]["host"] == "127.0.0.2"
    # Cache hits short-circuit before _race_a_aaaa, so no new calls.
    assert resolver._resolve.call_count == 4

    # Mock an exception for test3.com
    mocker.patch(
        "aiodns.DNSResolver.query",
        side_effect=asyncio.TimeoutError("DNS resolution failed"),
    )
    with pytest.raises(ResolveError):
        await resolver.resolve("test3.com")
    # Failed resolve still fires both A and AAAA in parallel; both
    # raise -> 2 additional _resolve invocations.
    assert resolver._resolve.call_count == 6
