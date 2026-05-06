"""Example of creating a simple custom provider."""

from proxybroker import SimpleProvider


class MySimpleProvider(SimpleProvider):
    """Custom provider for a simple proxy list website."""

    domain = "myproxysite.com"

    def __init__(self):
        super().__init__(
            url="http://myproxysite.com/proxy-list.txt",
            format="text",  # The site provides a simple text list
            proto=("HTTP", "HTTPS"),  # Types of proxies this site provides
            max_conn=2,  # Be gentle with the server
            timeout=30,
        )


# Example 2: Provider with custom pattern
class MyPatternProvider(SimpleProvider):
    """Provider that uses a custom regex pattern."""

    domain = "customformat.com"

    def __init__(self):
        # Custom pattern for format like: "proxy://192.168.1.1@8080"
        pattern = r"proxy://(\d+\.\d+\.\d+\.\d+)@(\d+)"

        super().__init__(
            url="http://customformat.com/proxies.html",
            pattern=pattern,
            proto=("HTTP", "SOCKS4", "SOCKS5"),
        )


# Example 3: JSON API provider
class MyJSONProvider(SimpleProvider):
    """Provider that fetches from a JSON API."""

    domain = "api.myproxies.com"

    def __init__(self):
        super().__init__(
            url="http://api.myproxies.com/v1/proxies?format=json",
            format="json",
            proto=("HTTP", "HTTPS", "SOCKS5"),
        )


if __name__ == "__main__":
    # These providers can now be used with Broker
    import asyncio

    from proxybroker import Broker

    async def main():
        # Create custom providers
        custom_providers = [MySimpleProvider(), MyPatternProvider(), MyJSONProvider()]

        # Use them with Broker
        broker = Broker(providers=custom_providers)

        # Find proxies from custom sources
        proxies = []
        async for proxy in broker.find(types=["HTTP", "HTTPS"], limit=10):
            print(proxy)
            proxies.append(proxy)

        print(f"\nFound {len(proxies)} proxies from custom providers")

    asyncio.run(main())
