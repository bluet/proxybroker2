"""Example of creating an advanced custom provider with all features."""

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
        proxies = []

        try:
            # Try JSON format first
            data = json.loads(page)

            if "proxies" in data:
                # Format 1: {"proxies": [{"ip": "1.2.3.4", "port": 8080, "type": "HTTP"}, ...]}
                for proxy in data["proxies"]:
                    ip = proxy.get("ip")
                    port = str(proxy.get("port"))
                    if ip and port:
                        # Store additional metadata if needed
                        proxy.get("type", "HTTP")
                        proxies.append((ip, port))

            elif "data" in data:
                # Format 2: {"data": ["1.2.3.4:8080", ...]}
                for proxy_str in data["data"]:
                    if ":" in proxy_str:
                        ip, port = proxy_str.split(":", 1)
                        proxies.append((ip, port))

        except json.JSONDecodeError:
            # Not JSON, try other formats

            # Format 3: HTML table
            table_pattern = (
                r"<tr>.*?<td>(\d+\.\d+\.\d+\.\d+)</td>.*?<td>(\d+)</td>.*?</tr>"
            )
            table_proxies = re.findall(table_pattern, page, re.DOTALL)
            if table_proxies:
                proxies.extend(table_proxies)

            # Format 4: JavaScript array
            js_pattern = r'proxies\.push\(\s*["\'](\d+\.\d+\.\d+\.\d+):(\d+)["\']'
            js_proxies = re.findall(js_pattern, page)
            if js_proxies:
                proxies.extend(js_proxies)

            # Format 5: Plain text as fallback
            if not proxies:
                proxies = self._find_proxies(page)

        # Log results for debugging
        if proxies:
            log.debug(f"Found {len(proxies)} proxies from {self.domain}")
        else:
            log.warning(f"No proxies found on {self.domain}")

        return proxies


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
    import asyncio

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
