"""Example of creating an advanced custom provider with all features."""

import asyncio
import json
import re

from proxybroker import Provider
from proxybroker.utils import log


class AdvancedProvider(Provider):
    """Advanced provider demonstrating all customization options."""

    domain = "advanced.proxysite.com"

    def __init__(self):
        super().__init__(
            url="https://advanced.proxysite.com/api/list",
            proto=("HTTP", "HTTPS", "SOCKS4", "SOCKS5"),
            max_conn=5,
            max_tries=3,
            timeout=30,
        )
        # Custom instance variables
        self.total_pages = None
        self.session_token = None

    async def _pipe(self):
        """Custom pipeline for complex scraping logic."""
        # Step 1: Get session token
        auth_page = await self.get("https://advanced.proxysite.com/api/auth")
        self.session_token = self._extract_token(auth_page)

        if not self.session_token:
            log.error(f"Failed to get session token from {self.domain}")
            return

        # Step 2: Get total pages
        info_page = await self.get(
            "https://advanced.proxysite.com/api/info",
            headers={"X-Session-Token": self.session_token},
        )
        self.total_pages = self._extract_page_count(info_page)

        # Step 3: Fetch all pages
        urls = []
        for page in range(1, min(self.total_pages + 1, 11)):  # Max 10 pages
            urls.append(
                {
                    "url": f"https://advanced.proxysite.com/api/proxies?page={page}",
                    "headers": {"X-Session-Token": self.session_token},
                }
            )

        await self._find_on_pages(urls)

    def _extract_token(self, page):
        """Extract session token from auth response."""
        try:
            data = json.loads(page)
            return data.get("token")
        except (json.JSONDecodeError, AttributeError):
            # Fallback to regex if not JSON
            match = re.search(r'token["\']:\s*["\']([^"\']+)', page)
            return match.group(1) if match else None

    def _extract_page_count(self, page):
        """Extract total page count from info response."""
        try:
            data = json.loads(page)
            return data.get("total_pages", 1)
        except (json.JSONDecodeError, AttributeError):
            return 1

    def find_proxies(self, page):
        """Advanced proxy extraction with multiple formats."""
        try:
            proxies = self._parse_json_proxies(page)

        except json.JSONDecodeError:
            proxies = self._parse_non_json_proxies(page)

        # Log results for debugging
        if proxies:
            log.debug(f"Found {len(proxies)} proxies from {self.domain}")
        else:
            log.warning(f"No proxies found on {self.domain}")

        return proxies

    def _parse_json_proxies(self, page):
        data = json.loads(page)
        if "proxies" in data:
            return self._extract_proxies_from_json_objects(data["proxies"])
        if "data" in data:
            return self._extract_proxies_from_strings(data["data"])
        return []

    def _parse_non_json_proxies(self, page):
        proxies = []
        proxies.extend(self._extract_proxies_from_html_table(page))
        proxies.extend(self._extract_proxies_from_js_array(page))
        if not proxies:
            return self._find_proxies(page)
        return proxies

    @staticmethod
    def _extract_proxies_from_json_objects(items):
        """Extract ``(ip, port)`` tuples from JSON proxy objects."""
        # Format 1: {"proxies": [{"ip": "1.2.3.4", "port": 8080, ...}, ...]}
        proxies = []
        for proxy in items:
            if not isinstance(proxy, dict):
                continue
            ip = proxy.get("ip")
            port = proxy.get("port")
            if ip and port is not None:
                proxies.append((ip, str(port)))
        return proxies

    @staticmethod
    def _extract_proxies_from_strings(items):
        """Extract ``(ip, port)`` tuples from ``['ip:port', ...]`` items."""
        # Format 2: {"data": ["1.2.3.4:8080", ...]}
        proxies = []
        for proxy_str in items:
            if isinstance(proxy_str, str) and ":" in proxy_str:
                ip, port = proxy_str.split(":", 1)
                proxies.append((ip, port))
        return proxies

    @staticmethod
    def _extract_proxies_from_html_table(page):
        """Extract proxies from ``<tr><td>IP</td><td>PORT</td></tr>`` rows."""
        # Format 3: HTML table
        octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
        table_pattern = (
            r"<tr[^>]*>\s*"
            rf"<td[^>]*>\s*({octet}(?:\.{octet}){{3}})\s*</td>\s*"
            r"<td[^>]*>\s*(\d+)\s*</td>\s*"
            r"</tr>"
        )
        return re.findall(table_pattern, page, re.IGNORECASE)

    @staticmethod
    def _extract_proxies_from_js_array(page):
        """Extract proxies from JavaScript ``proxies.push('ip:port')`` calls."""
        # Format 4: JavaScript array
        js_pattern = r'proxies\.push\(\s*["\'](\d+\.\d+\.\d+\.\d+):(\d+)["\']'
        return re.findall(js_pattern, page)


class RateLimitedProvider(Provider):
    """Provider that respects rate limits."""

    domain = "ratelimited.com"

    def __init__(self):
        super().__init__(
            url="https://ratelimited.com/proxies",
            proto=("HTTP", "HTTPS"),
            max_conn=1,  # Only one connection at a time
            timeout=30,
        )
        self.last_request_time = 0
        self.rate_limit_delay = 2  # 2 seconds between requests

    async def get(self, url, **kwargs):
        """Override get to add rate limiting."""
        import time

        # Enforce rate limit
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)

        self.last_request_time = time.time()
        return await super().get(url, **kwargs)


if __name__ == "__main__":
    # Example usage
    from proxybroker import Broker

    async def main():
        # Create advanced providers
        providers = [AdvancedProvider(), RateLimitedProvider()]

        async def consume(q):
            while True:
                proxy = await q.get()
                if proxy is None:
                    break
                print(f"Found proxy: {proxy.host}:{proxy.port}")

        proxies = asyncio.Queue()
        broker = Broker(proxies, providers=providers)
        await asyncio.gather(
            broker.find(types=["HTTP", "HTTPS"], limit=20),
            consume(proxies),
        )

    asyncio.run(main())
