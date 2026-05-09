import asyncio
import ipaddress
import os.path
import secrets
import socket
from collections import namedtuple

import aiodns
import aiohttp
import maxminddb

from .errors import ResolveError
from .utils import DATA_DIR, canonicalize_ip, log

GeoData = namedtuple(
    "GeoData", ["code", "name", "region_code", "region_name", "city_name"]
)

_countrydb = os.path.join(DATA_DIR, "GeoLite2-Country.mmdb")
_citydb = os.path.join(DATA_DIR, "GeoLite2-City.mmdb")
_geo_db = _citydb if os.path.exists(_citydb) else _countrydb

_mmdb_reader = maxminddb.open_database(_geo_db)

# Sentinel for `Resolver.resolve(qtype=...)` so we can tell apart
# "caller didn't specify" (default → Happy Eyeballs A+AAAA race) from
# "caller explicitly passed qtype='A'" (legacy A-only single-query).
# Without the sentinel, the previous `qtype="A"` default would force
# every default call into the dual-stack race even when the caller
# wanted the legacy contract.
_QTYPE_DEFAULT = object()


class Resolver:
    """Async host resolver based on aiodns."""

    _cached_hosts = {}
    # External IP discovery endpoints. `api64.ipify.org` returns the IPv6
    # address if the network supports it, otherwise IPv4 - so this list
    # works for IPv4-only, IPv6-only, and dual-stack hosts. The remaining
    # entries are IPv4-only by URL/hostname; they continue to function on
    # dual-stack and act as fallbacks if api64 is unreachable.
    _ip_hosts = [
        "https://api64.ipify.org/",
        "https://wtfismyip.com/text",
        "http://api.ipify.org/",
        "http://ipinfo.io/ip",
        "http://ipv4.icanhazip.com/",
        "http://myexternalip.com/raw",
        "http://ifconfig.io/ip",
    ]
    # the list of resolvers will point a copy of original one
    _temp_host = []

    def __init__(self, timeout=5, loop=None):
        self._timeout = timeout
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop, will be set later
            self._loop = loop
        # aiodns.DNSResolver() falls back to asyncio.get_event_loop() when
        # no loop is passed, which raises RuntimeError on Python 3.14+.
        # Defer construction until first use if we have no loop yet.
        self._resolver = aiodns.DNSResolver(loop=self._loop) if self._loop else None

    @staticmethod
    def host_is_ip(host):
        """Return True iff `host` is a valid IPv4 or IPv6 literal.

        Both families use stdlib `ipaddress` for parsing. IPv4 addresses
        with leading zeros (e.g. `"127.0.0.001"`) are also accepted by
        normalizing octets - `ipaddress.IPv4Address` itself rejects them
        since CPython 3.9.5 (CVE-2021-29921), but provider feeds in the
        wild occasionally emit that form, and historical proxybroker
        accepted it. Preserved here to avoid silently dropping proxies.
        """
        if not isinstance(host, str) or not host:
            return False
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            pass
        if "." in host and ":" not in host:
            # Legacy IPv4-only normalization for octets with leading zeros.
            try:
                normalized = ".".join(f"{int(n)}" for n in host.split("."))
                ipaddress.IPv4Address(normalized)
                return True
            except (ipaddress.AddressValueError, ValueError):
                return False
        return False

    @staticmethod
    def get_ip_info(ip):
        """Return geo information about IP address.

        `code` - ISO country code
        `name` - Full name of country
        `region_code` - ISO region code
        `region_name` - Full name of region
        `city_name` - Full name of city
        """
        # from pprint import pprint
        try:
            ipInfo = _mmdb_reader.get(ip) or {}
        except (maxminddb.errors.InvalidDatabaseError, ValueError):
            ipInfo = {}

        code, name = "--", "Unknown"
        city_name, region_code, region_name = ("Unknown",) * 3
        if "country" in ipInfo:
            code = ipInfo["country"]["iso_code"]
            name = ipInfo["country"]["names"]["en"]
        elif "continent" in ipInfo:
            code = ipInfo["continent"]["code"]
            name = ipInfo["continent"]["names"]["en"]
        if "city" in ipInfo:
            city_name = ipInfo["city"]["names"]["en"]
        if "subdivisions" in ipInfo:
            region_code = ipInfo["subdivisions"][0]["iso_code"]
            region_name = ipInfo["subdivisions"][0]["names"]["en"]
        return GeoData(code, name, region_code, region_name, city_name)

    def _pop_random_ip_host(self):
        # secrets.choice (CSPRNG) instead of random.choice for SonarCloud
        # S2245. The selection isn't security-sensitive (just balances which
        # ext-IP-detection URL we hit), but secrets is a drop-in here.
        host = secrets.choice(self._temp_host)
        self._temp_host.remove(host)
        return host

    @staticmethod
    def _has_local_route(family):
        """Routable-interface check for `family`.

        Opens a UDP socket and "connects" it to a documentation address
        (RFC 5737 / RFC 3849). UDP-connect just consults the routing
        table; it does NOT send packets, perform DNS, or generate any
        network traffic. ``OSError`` (typically ``EHOSTUNREACH`` /
        ``ENETUNREACH``) means no usable route. Microsecond cost.

        Used by ``get_real_ext_ips()`` to skip family probes that have
        no chance of succeeding - keeps v4-only users from paying the
        v6 probe's timeout cost (and vice versa for v6-only users).
        """
        target = "2001:db8::1" if family == socket.AF_INET6 else "192.0.2.1"
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as s:
                try:
                    s.connect((target, 80))
                    return True
                except OSError:
                    return False
        except OSError:
            return False  # socket() itself failed (family not supported)

    async def _probe_family(self, family):
        """Discover the external IP for one address family.

        Pins the aiohttp ``TCPConnector`` to ``family`` so the SOCKET
        layer enforces the family - immune to DNS quirks (CDN, CNAME,
        AAAA spoofing). Tries ``_ip_hosts`` in random order, returns
        the first canonical IP that matches the requested family.

        Returns the canonical IP string on success, or raises
        ``RuntimeError`` if no endpoint succeeds for this family.
        """
        # CSPRNG-randomised trial order so we balance load across the
        # public ext-IP-detection services (good-citizen behaviour for
        # what could be many proxybroker instances on the internet).
        # Built via `secrets.choice` per pick - matches the existing
        # `_pop_random_ip_host` pattern and avoids SonarCloud's S2245
        # false-positive against `random.shuffle` / `SystemRandom().shuffle`.
        remaining = list(self._ip_hosts)
        candidates = []
        while remaining:
            pick = secrets.choice(remaining)
            remaining.remove(pick)
            candidates.append(pick)
        connector = aiohttp.TCPConnector(family=family)
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                for url in candidates:
                    try:
                        async with session.get(url) as resp:
                            text = (await resp.text()).strip()
                    except (
                        asyncio.TimeoutError,
                        aiohttp.ClientError,
                        OSError,
                    ):
                        continue
                    canonical = canonicalize_ip(text)
                    if canonical is None:
                        continue
                    # Defensive: confirm the returned address matches
                    # the family we pinned the connector to. Guards
                    # against endpoints that report client IP via
                    # X-Forwarded-For-style logic that can leak the
                    # other family across CDN/proxy hops.
                    is_v6 = ":" in canonical
                    if (family == socket.AF_INET6) != is_v6:
                        log.debug(
                            "Family-probe mismatch for %s: got %s, "
                            "discarding and trying next endpoint",
                            family,
                            canonical,
                        )
                        continue
                    return canonical
        except OSError as e:
            # connector creation can fail on hosts without v6 support
            log.debug("Family-probe %s failed at connector: %s", family, e)
        raise RuntimeError(f"No external IP returned for family {family}")

    async def get_real_ext_ips(self):
        """Discover all external IP addresses reachable from this host.

        Returns a ``frozenset`` of canonical IP strings - one entry on
        single-stack hosts (v4-only or v6-only), two entries on
        dual-stack hosts where both families reach the public internet.

        The dual-IP set is what makes ``Judge.check`` reliable on
        dual-stack: a judge response can echo whichever family the
        connection used, and the comparison passes if EITHER ext-IP
        appears in the response.

        Capability detection (``_has_local_route``) skips probes for
        families that lack a routable interface - v4-only users (~50%
        of the install base) pay zero startup-latency cost for the
        IPv6-fix machinery they don't need.

        Raises:
            RuntimeError: When no probe succeeds for any family, or
                when no family has a local route at all.
        """
        families = [
            f for f in (socket.AF_INET, socket.AF_INET6) if self._has_local_route(f)
        ]
        if not families:
            raise RuntimeError("No routable IPv4 or IPv6 interface")
        results = await asyncio.gather(
            *[self._probe_family(f) for f in families],
            return_exceptions=True,
        )
        found = frozenset(ip for ip in results if isinstance(ip, str))
        if not found:
            raise RuntimeError("Could not get the external IP")
        log.debug("External IPs discovered: %s", sorted(found))
        return found

    async def get_real_ext_ip(self):
        """Return one external IP address (backward-compatibility shim).

        Prefer :meth:`get_real_ext_ips` in new code: that returns the
        full set, which is what ``Judge.check`` and
        ``_get_anonymity_lvl`` need to correctly classify proxy
        responses on dual-stack hosts.

        For dual-stack hosts that this method serves, it returns the
        IPv6 address (matches Happy Eyeballs default preference). For
        single-stack hosts it returns whichever family is available.
        """
        ips = await self.get_real_ext_ips()
        # IPv6-preferred (`":" in s`); deterministic ordering for tests.
        return next(iter(sorted(ips, key=lambda s: (":" not in s, s))))

    async def resolve(
        self, host, port=80, family=None, qtype=_QTYPE_DEFAULT, logging=True
    ):
        """Resolve `host` to one or more IP addresses.

        When the caller doesn't pin a specific record type or address
        family, A and AAAA queries fire in parallel per Happy Eyeballs
        DNS (RFC 8305 § 3). The first non-empty answer wins; the slower
        query is cancelled. If both fail, the most recent error is
        re-raised to preserve the historical "could not resolve" contract.

        Callers that explicitly pass `qtype="A"`, `qtype="AAAA"`, or
        `family=socket.AF_INET[/INET6]` get the legacy single-family
        path and never see a result from the other family. This
        preserves the contract for callers that need A-only (or
        AAAA-only) results.

        Sequential A→AAAA fallback would add a full DNS round-trip of
        latency for v6-only hostnames; parallel race makes v4-only and
        v6-only hosts resolve at roughly the same speed and shaves the
        worst-case latency for dual-stack hosts on broken networks.
        """
        if self.host_is_ip(host):
            # Canonicalise the literal so callers downstream of resolve()
            # always see RFC 5952 canonical form, regardless of how the
            # caller wrote the input ("2001:DB8::1" vs "2001:db8::1").
            return canonicalize_ip(host) or host

        _host = self._cached_hosts.get(host)
        if _host and self._cache_compatible(_host, family, qtype):
            return _host

        resp = await self._fetch_records(host, family, qtype)

        if resp:
            hosts = [
                {
                    "hostname": host,
                    # Canonicalise DNS-returned host strings too. aiodns
                    # may emit different textual forms across resolvers/
                    # platforms; downstream comparison logic relies on
                    # canonical form to dedup equivalent addresses.
                    "host": canonicalize_ip(r.host) or r.host,
                    "port": port,
                    "family": family,
                    "proto": socket.IPPROTO_IP,
                    "flags": socket.AI_NUMERICHOST,
                }
                for r in resp
            ]
            if family:
                self._cached_hosts[host] = hosts
            else:
                self._cached_hosts[host] = hosts[0]["host"]
            if logging:
                log.debug(f"{host}: Host resolved: {self._cached_hosts[host]}")
        else:
            if logging:
                log.warning(f"{host}: Could not resolve host")
        return self._cached_hosts.get(host)

    @staticmethod
    def _cache_compatible(cached, family, qtype):
        """Return True iff `cached` matches the caller's family/qtype intent.

        The cache key is the bare hostname, so a prior default
        Happy-Eyeballs lookup may have stored an IPv6 winner under
        `host`. A subsequent caller pinning `family=AF_INET` or
        `qtype="A"` must not silently receive that v6 — we validate
        the cached IP's family before short-circuiting.
        """
        if family is None and qtype is _QTYPE_DEFAULT:
            return True  # default path accepts whatever was cached
        cached_ip = cached if isinstance(cached, str) else cached[0]["host"]
        try:
            cached_addr = ipaddress.ip_address(cached_ip)
        except (ValueError, TypeError):
            return False
        wants_v4 = family == socket.AF_INET or qtype == "A"
        wants_v6 = family == socket.AF_INET6 or qtype == "AAAA"
        if wants_v4:
            return isinstance(cached_addr, ipaddress.IPv4Address)
        if wants_v6:
            return isinstance(cached_addr, ipaddress.IPv6Address)
        return True

    async def _fetch_records(self, host, family, qtype):
        """Choose A-only / AAAA-only / parallel race based on caller intent.

        Extracted from `resolve()` to keep that method below the
        cognitive-complexity threshold (Sonar S3776) and to make the
        family/qtype dispatch explicit in one place.
        """
        if qtype is not _QTYPE_DEFAULT:
            # Caller pinned the query type - honor it without racing.
            return await self._resolve(host, qtype)
        if family == socket.AF_INET:
            return await self._resolve(host, "A")
        if family == socket.AF_INET6:
            return await self._resolve(host, "AAAA")
        # Default: Happy Eyeballs (race A and AAAA).
        return await self._race_a_aaaa(host)

    async def _race_a_aaaa(self, host):
        """Race A and AAAA queries; return the first non-empty answer.

        Implements Happy Eyeballs DNS (RFC 8305 § 3). Both queries are
        scheduled concurrently. When the first one completes:
          * Non-empty success: cancel the loser, return immediately.
          * Empty result or `ResolveError`: keep waiting for the other.
        If both fail, re-raise the most recent error so the surrounding
        `resolve()` keeps its "could not resolve" contract intact.
        """
        a_task = asyncio.create_task(self._resolve(host, "A"))
        aaaa_task = asyncio.create_task(self._resolve(host, "AAAA"))
        pending = {a_task, aaaa_task}
        last_error: Exception | None = None
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    try:
                        result = task.result()
                    except ResolveError as exc:
                        last_error = exc
                        continue
                    if result:
                        return result
        finally:
            for task in pending:
                task.cancel()
        if last_error is not None:
            raise last_error
        return None

    async def _resolve(self, host, qtype):
        if self._resolver is None:
            # Deferred construction - we are now inside a running loop.
            self._resolver = aiodns.DNSResolver()
        try:
            resp = await asyncio.wait_for(
                self._resolver.query(host, qtype), timeout=self._timeout
            )
        except (aiodns.error.DNSError, asyncio.TimeoutError) as e:
            raise ResolveError from e
        else:
            return resp
