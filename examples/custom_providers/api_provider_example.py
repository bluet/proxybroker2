"""Example of creating an API-based custom provider."""

from proxybroker import APIProvider


class MyAuthenticatedAPI(APIProvider):
    """Provider for an API that requires authentication."""

    domain = "secure-api.proxies.com"

    def __init__(self, api_key):
        super().__init__(
            api_url="https://secure-api.proxies.com/v1/list",
            api_key=api_key,
            response_format="json",
            proxy_path="data.proxies",  # Nested path in JSON response
            proto=("HTTP", "HTTPS", "SOCKS5"),
            max_conn=2,  # Respect API rate limits
            timeout=30,
        )


class MyCustomHeaderAPI(APIProvider):
    """Provider for an API with custom headers."""

    domain = "custom.proxyapi.net"

    def __init__(self):
        custom_headers = {
            "X-Client-ID": "proxybroker2",
            "Accept": "application/json",
            "X-Request-Type": "proxy-list",
        }

        super().__init__(
            api_url="https://custom.proxyapi.net/proxies/all",
            headers=custom_headers,
            response_format="json",
            proto=("HTTP", "HTTPS"),
        )

    def find_proxies(self, page):
        """Handle custom API response format."""
        import json

        try:
            data = json.loads(page)
            proxies = []

            # Custom format: {"success": true, "items": [{"endpoint": "1.2.3.4:8080"}, ...]}
            if data.get("success"):
                for item in data.get("items", []):
                    endpoint = item.get("endpoint", "")
                    if ":" in endpoint:
                        ip, port = endpoint.split(":", 1)
                        proxies.append((ip, port))

            return proxies
        except Exception as e:
            print(f"Error parsing API response: {e}")
            return []


class MyRESTfulAPI(APIProvider):
    """Provider for a RESTful API with filtering."""

    domain = "rest.proxyprovider.com"

    def __init__(self, country="US", proxy_type="elite"):
        # Build API URL with query parameters
        base_url = "https://rest.proxyprovider.com/api/proxies"
        params = f"?country={country}&type={proxy_type}&format=json"

        super().__init__(
            api_url=base_url + params,
            response_format="json",
            proto=("HTTP", "HTTPS", "SOCKS4", "SOCKS5"),
        )


if __name__ == "__main__":
    # Example usage
    import asyncio

    from proxybroker import Broker

    async def main():
        # Create API providers
        providers = [
            MyAuthenticatedAPI(api_key="your-api-key-here"),
            MyCustomHeaderAPI(),
            MyRESTfulAPI(country="US", proxy_type="anonymous"),
        ]

        broker = Broker(providers=providers)

        async for proxy in broker.find(types=["HTTP", "HTTPS"], limit=10):
            print(f"Found proxy: {proxy.host}:{proxy.port} ({proxy.types})")

    asyncio.run(main())
