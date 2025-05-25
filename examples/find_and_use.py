"""Find working proxies and use them concurrently.

Note: Pay attention to Broker.serve(), instead of the code listed below.
      Perhaps it will be much useful and friendlier.
"""

import asyncio
from urllib.parse import urlparse

import aiohttp

from proxybroker import Broker, ProxyPool
from proxybroker.errors import NoProxyError


async def fetch(url, proxy_pool, timeout=10):
    resp, proxy = None, None
    try:
        print("Waiting a proxy...")
        proxy = await proxy_pool.get(scheme=urlparse(url).scheme)
        print("Found proxy:", proxy)
        proxy_url = "http://%s:%d" % (proxy.host, proxy.port)
        _timeout = aiohttp.ClientTimeout(total=timeout)
        async with (
            aiohttp.ClientSession(timeout=_timeout) as session,
            session.get(url, proxy=proxy_url) as response,
        ):
            resp = await response.text()
    except (
        aiohttp.ClientOSError,
        aiohttp.ClientResponseError,
        aiohttp.ServerDisconnectedError,
        asyncio.TimeoutError,
        NoProxyError,
    ) as e:
        print("Error!\nURL: %s;\nError: %r\n", url, e)
    finally:
        if proxy:
            proxy_pool.put(proxy)
        return (url, resp)


async def get_pages(urls, proxy_pool, timeout=10):
    tasks = [fetch(url, proxy_pool, timeout) for url in urls]
    for task in asyncio.as_completed(tasks):
        url, content = await task
        print("%s\nDone!\nURL: %s;\nContent: %s" % ("-" * 20, url, content))


async def main():
    proxies = asyncio.Queue()
    proxy_pool = ProxyPool(proxies)

    judges = [
        "http://httpbin.org/get?show_env",
        "https://httpbin.org/get?show_env",
    ]

    providers = [
        "http://www.proxylists.net/",
        "http://ipaddress.com/proxy-list/",
        "https://www.sslproxies.org/",
    ]

    broker = Broker(
        proxies,
        timeout=8,
        max_conn=200,
        max_tries=3,
        verify_ssl=False,
        judges=judges,
        providers=providers,
    )

    types = [("HTTP", ("Anonymous", "High"))]
    countries = ["US", "UK", "DE", "FR"]

    urls = [
        "http://httpbin.org/get",
        "http://httpbin.org/redirect/1",
        "http://httpbin.org/anything",
        "http://httpbin.org/status/404",
    ]

    await asyncio.gather(
        broker.find(types=types, countries=countries, strict=True, limit=10),
        get_pages(urls, proxy_pool),
    )

    # broker.show_stats(verbose=True)


if __name__ == "__main__":
    asyncio.run(main())
