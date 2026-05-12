import asyncio
import secrets
from urllib.parse import urlparse

import aiohttp

from .errors import ResolveError
from .resolver import Resolver
from .utils import canonicalize_ip, get_all_ip, get_headers, log


class Judge:
    """Proxy Judge."""

    available = {"HTTP": [], "HTTPS": [], "SMTP": []}
    ev = {
        "HTTP": asyncio.Event(),
        "HTTPS": asyncio.Event(),
        "SMTP": asyncio.Event(),
    }

    def __init__(self, url, timeout=8, verify_ssl=False, loop=None):
        self.url = url
        self.scheme = urlparse(url).scheme.upper()
        self.host = urlparse(url).netloc
        self.path = url.split(self.host)[-1]
        self.ip = None
        self._is_working = False
        self.marks = {"via": 0, "proxy": 0}
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop, will be set later
            self._loop = loop
        self._resolver = Resolver(loop=self._loop)

    def __repr__(self):
        """Class representation"""
        return f"<Judge [{self.scheme}] {self.host}>"

    @property
    def is_working(self):
        return self._is_working

    @is_working.setter
    def is_working(self, val):
        self._is_working = val

    @classmethod
    def get_random(cls, proto):
        if proto == "HTTPS":
            scheme = "HTTPS"
        elif proto == "CONNECT:25":
            scheme = "SMTP"
        else:
            scheme = "HTTP"
        # secrets.choice (CSPRNG) clears SonarCloud S2245; the selection
        # is not security-sensitive (just round-robins judges) but secrets
        # is a drop-in replacement.
        return secrets.choice(cls.available[scheme])

    @classmethod
    def clear(cls):
        cls.available["HTTP"].clear()
        cls.available["HTTPS"].clear()
        cls.available["SMTP"].clear()
        cls.ev["HTTP"].clear()
        cls.ev["HTTPS"].clear()
        cls.ev["SMTP"].clear()

    async def check(self, real_ext_ips=None, real_ext_ip=None):
        """Probe judge endpoint and verify it echoes a known real ext-IP.

        ``real_ext_ips`` (set/iterable, preferred) accepts the FULL set
        of host external IPs from ``Resolver.get_real_ext_ips()`` so the
        comparison passes whichever family the judge connection used.
        ``real_ext_ip`` (single string, legacy) is kept for backward
        compatibility; if both are passed, ``real_ext_ips`` wins.
        """
        # TODO: need refactoring
        # Normalise legacy single-string input into the set-aware path.
        if real_ext_ips is None and real_ext_ip is not None:
            real_ext_ips = (real_ext_ip,)
        # Defensive: a caller passing a single str (e.g. via the OLD
        # positional API `judge.check("203.0.113.5")` where the string
        # now binds to `real_ext_ips`) gets it treated as one IP, not
        # iterated into a set of individual characters.
        if isinstance(real_ext_ips, str):
            real_ext_ips = (real_ext_ips,)
        real_ext_ips = frozenset(real_ext_ips or ())

        try:
            self.ip = await self._resolver.resolve(self.host)
        except ResolveError:
            return

        if self.scheme == "SMTP":
            self.is_working = True
            self.available[self.scheme].append(self)
            self.ev[self.scheme].set()
            return

        page = False
        headers, rv = get_headers(rv=True)
        connector = aiohttp.TCPConnector(
            loop=self._loop, ssl=self.verify_ssl, force_close=True
        )
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with (
                aiohttp.ClientSession(connector=connector, timeout=timeout) as session,
                session.get(
                    url=self.url, headers=headers, allow_redirects=False
                ) as resp,
            ):
                page = await resp.text()
        except (
            asyncio.TimeoutError,
            aiohttp.ClientOSError,
            aiohttp.ClientResponseError,
            aiohttp.ServerDisconnectedError,
        ) as e:
            log.debug(f"{self} is failed. Error: {e!r};")
            return

        page = page.lower()
        # Canonical-form set membership: judges may echo whichever family
        # the connection used, and the host may have v4 OR v6 reachable
        # (or both on dual-stack). Pass if ANY of the host's real ext-IPs
        # appears in the page.
        page_ips = get_all_ip(page)
        real_canonicals = frozenset(canonicalize_ip(ip) or ip for ip in real_ext_ips)
        real_ip_visible = bool(real_canonicals & page_ips)

        if resp.status == 200 and real_ip_visible and rv in page:
            self.marks["via"] = page.count("via")
            self.marks["proxy"] = page.count("proxy")
            self.is_working = True
            self.available[self.scheme].append(self)
            self.ev[self.scheme].set()
            log.debug(f"{self} is verified")
        else:
            log.debug(
                f"{self} is failed. HTTP status code: {resp.status}; "
                f"Real IP on page: {real_ip_visible}; Version: {rv in page}; "
                f"Response: {page}"
            )


def get_judges(judges=None, timeout=8, verify_ssl=False):
    judges = judges or [
        "http://httpbin.org/get?show_env",
        "https://httpbin.org/get?show_env",
        "smtp://smtp.gmail.com",
        "smtp://aspmx.l.google.com",
        "http://azenv.net/",
        "https://www.proxy-listen.de/azenv.php",
        "http://www.proxyfire.net/fastenv",
        "http://proxyjudge.us/azenv.php",
        "http://ip.spys.ru/",
        "http://www.proxy-listen.de/azenv.php",
        "http://httpbin.com.br/anything?show_env",
        "https://httpbin.com.br/anything?show_env",
    ]
    _judges = []
    for j in judges:
        j = j if isinstance(j, Judge) else Judge(j)
        j.timeout = timeout
        j.verify_ssl = verify_ssl
        _judges.append(j)
    return _judges
