"""Find and show 10 working HTTP(S) proxies."""

import sys
import asyncio

from proxybroker import Broker


async def show(proxies):
    while True:
        proxy = await proxies.get()
        if proxy is None:
            break
        print('Found proxy: %s' % proxy)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

proxies = asyncio.Queue()
broker = Broker(proxies, loop=loop)
tasks = asyncio.gather(broker.find(types=['HTTP', 'HTTPS'], limit=10), show(proxies))

loop.run_until_complete(tasks)
