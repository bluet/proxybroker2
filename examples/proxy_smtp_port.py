"""Find 10 working proxies supporting CONNECT method
   to 25 port (SMTP) and save them to a file."""

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
            f.write('smtp://%s:%d\n' % (proxy.host, proxy.port))


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    proxies = asyncio.Queue()
    broker = Broker(proxies, judges=['smtp://smtp.gmail.com'], max_tries=1, loop=loop)

    # Check proxy in spam databases (DNSBL). By default is disabled.
    # more databases: http://www.dnsbl.info/dnsbl-database-check.php
    dnsbl = [
        'bl.spamcop.net',
        'cbl.abuseat.org',
        'dnsbl.sorbs.net',
        'zen.spamhaus.org',
        'bl.mcafee.com',
        'spam.spamrats.com',
    ]

    tasks = asyncio.gather(
        broker.find(types=['CONNECT:25'], dnsbl=dnsbl, limit=10),
        save(proxies, filename='proxies.txt'),
    )
    loop.run_until_complete(tasks)


if __name__ == '__main__':
    main()
