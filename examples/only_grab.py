"""Gather proxies from the providers without
   checking and save them to a file."""

import sys
import asyncio

from proxybroker import Broker

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def save(proxies, filename):
    """Save proxies to a file."""
    with open(filename, 'w') as f:
        while True:
            proxy = await proxies.get()
            if proxy is None:
                break
            f.write('%s:%d\n' % (proxy.host, proxy.port))


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    proxies = asyncio.Queue()
    broker = Broker(proxies, loop=loop)
    tasks = asyncio.gather(
        broker.grab(countries=['US', 'GB'], limit=10),
        save(proxies, filename='proxies.txt'),
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tasks)


if __name__ == '__main__':
    main()
