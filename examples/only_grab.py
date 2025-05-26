"""Gather proxies from the providers without
checking and save them to a file."""

import asyncio

from proxybroker import Broker


async def save(proxies, filename):
    """Save proxies to a file."""
    with open(filename, "w") as f:
        while True:
            proxy = await proxies.get()
            if proxy is None:
                break
            f.write("%s:%d\n" % (proxy.host, proxy.port))


async def main():
    proxies = asyncio.Queue()
    broker = Broker(proxies)
    await asyncio.gather(
        broker.grab(countries=["US", "GB"], limit=10),
        save(proxies, filename="proxies.txt"),
    )


if __name__ == "__main__":
    asyncio.run(main())
