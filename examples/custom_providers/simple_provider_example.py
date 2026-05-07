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

    async def consume(proxies):
        results = []
        while True:
            proxy = await proxies.get()
            if proxy is None:
                break
            print(proxy)
            results.append(proxy)
        print(f"\nFound {len(results)} proxies from custom providers")

    async def main():
        custom_providers = [MySimpleProvider(), MyPatternProvider(), MyJSONProvider()]
        proxies = asyncio.Queue()
        broker = Broker(proxies, providers=custom_providers)
        await asyncio.gather(
            broker.find(types=["HTTP", "HTTPS"], limit=10),
            consume(proxies),
        )

    asyncio.run(main())
