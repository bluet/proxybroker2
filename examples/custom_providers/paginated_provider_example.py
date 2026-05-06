"""Example of creating a paginated custom provider."""

from proxybroker import PaginatedProvider


class MyPaginatedSite(PaginatedProvider):
    """Custom provider for a site with pagination."""

    domain = "proxypages.com"

    def __init__(self):
        super().__init__(
            # URL with {} placeholder for page number
            base_url="http://proxypages.com/list/page-{}.html",
            start_page=1,
            max_pages=5,  # Fetch first 5 pages
            proto=("HTTP", "HTTPS", "SOCKS4", "SOCKS5"),
            max_conn=3,
            timeout=25,
        )

    def find_proxies(self, page):
        """Custom parsing logic for this specific site."""
        # Example: Site has proxies in <div class="proxy"> tags
        # Format: <div class="proxy">192.168.1.1:8080</div>

        import re

        pattern = r'<div class="proxy">(\d+\.\d+\.\d+\.\d+):(\d+)</div>'
        return re.findall(pattern, page)


class MyAPIPaginatedProvider(PaginatedProvider):
    """Provider for an API with pagination."""

    domain = "api.proxies.io"

    def __init__(self):
        super().__init__(
            # API with page parameter
            base_url="http://api.proxies.io/v2/proxies",
            page_param="offset",  # Uses offset instead of page
            start_page=0,  # Starting offset
            page_step=50,  # 50 items per page
            max_pages=3,  # Fetch 150 proxies total (3 * 50)
            proto=("HTTP", "HTTPS"),
            timeout=30,
        )

    def find_proxies(self, page):
        """Parse JSON response from API."""
        import json

        try:
            data = json.loads(page)
            proxies = []

            # Assuming API returns: {"proxies": [{"ip": "1.2.3.4", "port": 8080}, ...]}
            for item in data.get("proxies", []):
                ip = item.get("ip")
                port = str(item.get("port"))
                if ip and port:
                    proxies.append((ip, port))

            return proxies
        except:
            return []


if __name__ == "__main__":
    # Example usage
    import asyncio

    from proxybroker import Broker

    async def main():
        # Create paginated providers
        providers = [MyPaginatedSite(), MyAPIPaginatedProvider()]

        broker = Broker(providers=providers)

        # The providers will automatically fetch multiple pages
        async for proxy in broker.find(types=["HTTP"], limit=20):
            print(f"Found proxy: {proxy.host}:{proxy.port}")

    asyncio.run(main())
