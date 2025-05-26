import asyncio
import heapq
import time

from cachetools import TTLCache

from .errors import (
    BadResponseError,
    BadStatusError,
    BadStatusLine,
    ErrorOnStream,
    NoProxyError,
    ProxyConnError,
    ProxyEmptyRecvError,
    ProxyRecvError,
    ProxySendError,
    ProxyTimeoutError,
    ResolveError,
)
from .resolver import Resolver
from .utils import log, parse_headers, parse_status_line

# from pprint import pprint


history = TTLCache(maxsize=10000, ttl=600)
CONNECTED = b"HTTP/1.1 200 Connection established\r\n\r\n"


class ProxyPool:
    """Imports and gives proxies from queue on demand."""

    def __init__(
        self,
        proxies,
        min_req_proxy=5,
        max_error_rate=0.5,
        max_resp_time=8,
        min_queue=5,
        strategy="best",
        import_timeout=5.0,
        max_import_retries=100,
    ):
        self._proxies = proxies
        self._pool = []
        self._newcomers = []
        self._strategy = strategy
        self._min_req_proxy = min_req_proxy
        # if num of errors greater or equal 50% - proxy will be remove from pool
        self._max_error_rate = max_error_rate
        self._max_resp_time = max_resp_time
        self._min_queue = min_queue
        self._import_timeout = import_timeout
        self._max_import_retries = max_import_retries

        if strategy != "best":
            raise ValueError("`strategy` only support `best` for now.")

    async def get(self, scheme):
        scheme = scheme.upper()
        if len(self._pool) + len(self._newcomers) < self._min_queue:
            chosen = await self._import(scheme)
        elif len(self._newcomers) > 0:
            chosen = self._newcomers.pop(0)
        elif self._strategy == "best":
            # Create a temporary list to store items we need to put back
            temp_items = []
            chosen = None
            # Pop items from heap until we find a suitable proxy
            while self._pool:
                priority, proxy = heapq.heappop(self._pool)
                if scheme in proxy.schemes:
                    chosen = proxy
                    # Put back the items we popped but didn't use
                    for item in temp_items:
                        heapq.heappush(self._pool, item)
                    break
                else:
                    temp_items.append((priority, proxy))
            else:
                # Put back all items if we didn't find a suitable proxy
                for item in temp_items:
                    heapq.heappush(self._pool, item)
                chosen = await self._import(scheme)

        return chosen

    async def _import(self, expected_scheme):
        retry_count = 0

        while retry_count < self._max_import_retries:
            try:
                proxy = await asyncio.wait_for(
                    self._proxies.get(), timeout=self._import_timeout
                )
                self._proxies.task_done()

                if not proxy:
                    raise NoProxyError("No more available proxies")
                elif expected_scheme not in proxy.schemes:
                    self.put(proxy)
                    retry_count += 1
                else:
                    return proxy

            except asyncio.TimeoutError:
                raise NoProxyError(
                    f"Timeout waiting for proxy with scheme {expected_scheme}"
                ) from None

        raise NoProxyError(
            f"Exceeded max retries ({self._max_import_retries}) finding proxy with scheme {expected_scheme}"
        )

    def put(self, proxy):
        if proxy is None:
            return  # Ignore None proxies

        is_exceed_time = (proxy.error_rate > self._max_error_rate) or (
            proxy.avg_resp_time > self._max_resp_time
        )
        if proxy.stat["requests"] < self._min_req_proxy:
            self._newcomers.append(proxy)
        elif proxy.stat["requests"] >= self._min_req_proxy and is_exceed_time:
            log.debug("%s:%d removed from proxy pool" % (proxy.host, proxy.port))
        else:
            heapq.heappush(self._pool, (proxy.avg_resp_time, proxy))

        log.debug("%s:%d stat: %s" % (proxy.host, proxy.port, proxy.stat))

    def remove(self, host, port):
        # Check newcomers first
        for proxy in self._newcomers:
            if proxy.host == host and proxy.port == port:
                chosen = proxy
                self._newcomers.remove(proxy)
                return chosen

        # Check established pool - use heap-safe removal
        # Note: This is O(N log N) complexity to maintain heap invariant.
        # We prioritize correctness over performance here since removals
        # are relatively infrequent compared to get operations.
        temp_items = []
        chosen = None

        # Pop all items until we find the target or empty the heap
        while self._pool:
            priority, proxy = heapq.heappop(self._pool)
            if proxy.host == host and proxy.port == port:
                chosen = proxy
                # Put back all other items
                for item in temp_items:
                    heapq.heappush(self._pool, item)
                break
            else:
                temp_items.append((priority, proxy))
        else:
            # Target not found, restore all items
            for item in temp_items:
                heapq.heappush(self._pool, item)

        return chosen


class Server:
    """Server distributes incoming requests to a pool of found proxies.

    The Server can be used as an async context manager for automatic lifecycle management:

        async with Server('127.0.0.1', 8888, proxies) as server:
            # Server is automatically started
            # ... do work ...
        # Server is automatically closed (without stopping the event loop)

    Or managed manually:

        server = Server('127.0.0.1', 8888, proxies)
        await server.start()
        # ... do work ...
        await server.aclose()  # Async-safe cleanup
        # or
        server.stop()  # Synchronous cleanup (stops event loop)
    """

    def __init__(
        self,
        host,
        port,
        proxies,
        timeout=8,
        max_tries=3,
        min_queue=5,
        min_req_proxy=5,
        max_error_rate=0.5,
        max_resp_time=8,
        prefer_connect=False,
        http_allowed_codes=None,
        backlog=100,
        loop=None,
        **kwargs,
    ):
        self.host = host
        self.port = int(port)
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop, will be set later
            self._loop = loop
        self._timeout = timeout
        self._max_tries = max_tries
        self._backlog = backlog
        self._prefer_connect = prefer_connect

        self._server = None
        self._connections = {}
        self._proxy_pool = ProxyPool(
            proxies,
            min_req_proxy,
            max_error_rate,
            max_resp_time,
            min_queue,
            import_timeout=kwargs.get("import_timeout", 5.0),
            max_import_retries=kwargs.get("max_import_retries", 100),
        )
        self._resolver = Resolver(loop=self._loop)
        self._http_allowed_codes = http_allowed_codes or []

    async def start(self):
        srv = await asyncio.start_server(
            self._accept, self.host, self.port, backlog=self._backlog
        )
        self._server = srv

        log.info(f"Listening established on {self._server.sockets[0].getsockname()}")

    def stop(self):
        if not self._server:
            return
        for conn in self._connections:
            if not conn.done():
                conn.cancel()
        self._server.close()
        if not self._loop.is_running():
            self._loop.run_until_complete(self._server.wait_closed())
            # Time to close the running futures in self._connections
            self._loop.run_until_complete(asyncio.sleep(0.5))
        self._server = None
        self._loop.stop()
        log.info("Server is stopped")

    async def aclose(self):
        """Async-safe method to close the server without stopping the event loop.

        This method can be safely used in async contexts, including async context managers,
        without affecting other running tasks in the event loop.
        """
        if not self._server:
            return

        # Cancel all active connections
        for conn in self._connections:
            if not conn.done():
                conn.cancel()

        # Close the server
        self._server.close()
        await self._server.wait_closed()

        # Allow time for connections to close
        await asyncio.sleep(0.5)

        self._server = None
        log.info("Server is closed (async)")

    async def __aenter__(self):
        """Enter the async context manager, starting the server."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager, closing the server."""
        await self.aclose()
        return False

    def _accept(self, client_reader, client_writer):
        def _on_completion(f):
            reader, writer = self._connections.pop(f)
            writer.close()
            log.debug("client: %d; closed" % id(client_reader))
            try:
                exc = f.exception()
            except asyncio.CancelledError:
                log.debug("CancelledError in server._handle:_on_completion")
                exc = None
            if exc:
                if isinstance(exc, NoProxyError):
                    self.stop()
                else:
                    raise exc

        f = asyncio.create_task(self._handle(client_reader, client_writer))
        f.add_done_callback(_on_completion)
        self._connections[f] = (client_reader, client_writer)

    async def _handle(self, client_reader, client_writer):
        log.debug(
            "Accepted connection from %s" % (client_writer.get_extra_info("peername"),)
        )

        request, headers = await self._parse_request(client_reader)
        scheme = self._identify_scheme(headers)
        client = id(client_reader)
        log.debug(
            "client: %d; request: %s; headers: %s; scheme: %s"
            % (client, request, headers, scheme)
        )

        # API for controlling proxybroker2
        if headers["Host"] == "proxycontrol":
            _api, _operation, _params = headers["Path"].split("/", 5)[3:]
            if _api == "api":
                if _operation == "remove":
                    proxy_host, proxy_port = _params.split(":", 1)
                    self._proxy_pool.remove(proxy_host, int(proxy_port))
                    log.debug(
                        "Remove Proxy: client: %d; request: %s; headers: %s; scheme: %s; proxy_host: %s; proxy_port: %s"
                        % (client, request, headers, scheme, proxy_host, proxy_port)
                    )
                    client_writer.write(b"HTTP/1.1 204 No Content\r\n\r\n")
                    await client_writer.drain()
                    return
                elif _operation == "history":
                    query_type, url = _params.split(":", 1)
                    if query_type == "url":
                        previous_proxy = history.get(
                            f"{client_reader._transport.get_extra_info('peername')[0]}-{url}"
                        )
                        if previous_proxy is None:
                            client_writer.write(b"HTTP/1.1 204 No Content\r\n\r\n")
                            await client_writer.drain()
                            return
                        else:
                            previous_proxy_bytestring = (
                                '{"proxy": "%s"}' % previous_proxy
                            ).encode()
                            client_writer.write(b"HTTP/1.1 200 OK\r\n")
                            client_writer.write(b"Content-Type: application/json\r\n")
                            client_writer.write(
                                f"Content-Length: {str(len(previous_proxy_bytestring) + 2).encode()}\r\n"
                            )
                            client_writer.write(b"Access-Control-Allow-Origin: *\r\n")
                            client_writer.write(
                                b"Access-Control-Allow-Credentials: true\r\n\r\n"
                            )

                            client_writer.write(previous_proxy_bytestring + b"\r\n")
                            await client_writer.drain()
                            return

        for attempt in range(self._max_tries):
            stime, err = 0, None
            proxy = await self._proxy_pool.get(scheme)
            proto = self._choice_proto(proxy, scheme)
            log.debug(
                "client: %d; attempt: %d; proxy: %s; proto: %s"
                % (client, attempt, proxy, proto)
            )

            try:
                await proxy.connect()

                if proto in ("CONNECT:80", "SOCKS4", "SOCKS5"):
                    host = headers.get("Host")
                    port = headers.get("Port", 80)
                    try:
                        ip = await self._resolver.resolve(host)
                    except ResolveError:
                        return
                    proxy.ngtr = proto
                    await proxy.ngtr.negotiate(host=host, port=port, ip=ip)
                    if scheme == "HTTPS" and proto in ("SOCKS4", "SOCKS5"):
                        client_writer.write(CONNECTED)
                        await client_writer.drain()
                    else:  # HTTP
                        await proxy.send(request)
                else:  # proto: HTTP & HTTPS
                    await proxy.send(request)

                history[
                    f"{client_reader._transport.get_extra_info('peername')[0]}-{headers['Path']}"
                ] = proxy.host + ":" + str(proxy.port)
                inject_resp_header = {
                    "headers": {"X-Proxy-Info": proxy.host + ":" + str(proxy.port)}
                }

                stime = time.time()
                stream = [
                    asyncio.create_task(
                        self._stream(reader=client_reader, writer=proxy.writer)
                    ),
                    asyncio.create_task(
                        self._stream(
                            reader=proxy.reader,
                            writer=client_writer,
                            scheme=scheme,
                            inject=inject_resp_header,
                        )
                    ),
                ]
                await asyncio.gather(*stream)
            except asyncio.CancelledError:
                log.debug("Cancelled in server._handle")
                break
            except (
                ProxyTimeoutError,
                ProxyConnError,
                ProxyRecvError,
                ProxySendError,
                ProxyEmptyRecvError,
                BadStatusError,
                BadResponseError,
            ) as e:
                log.debug("client: %d; error: %r" % (client, e))
                continue
            except ErrorOnStream as e:
                log.debug(
                    "client: %d; error: %r; EOF: %s"
                    % (client, e, client_reader.at_eof())
                )
                for task in stream:
                    if not task.done():
                        task.cancel()
                if client_reader.at_eof() and "Timeout" in repr(e):
                    # Proxy may not be able to receive EOF and weel be raised a
                    # TimeoutError, but all the data has already successfully
                    # returned, so do not consider this error of proxy
                    break
                err = e
                if scheme == "HTTPS":  # SSL Handshake probably failed
                    break
            else:
                break
            finally:
                proxy.log(request.decode(), stime, err=err)
                proxy.close()
                self._proxy_pool.put(proxy)

    async def _parse_request(self, reader, length=65536):
        request = await reader.read(length)
        headers = parse_headers(request)
        if headers["Method"] == "POST" and request.endswith(b"\r\n\r\n"):
            # For aiohttp. POST data returns on second reading
            request += await reader.read(length)
        return request, headers

    def _identify_scheme(self, headers):
        if headers["Method"] == "CONNECT":
            return "HTTPS"
        else:
            return "HTTP"

    def _choice_proto(self, proxy, scheme):
        if scheme == "HTTP":
            if self._prefer_connect and ("CONNECT:80" in proxy.types):
                return "CONNECT:80"
            else:
                # Deterministic priority order for HTTP
                for proto in ["HTTP", "CONNECT:80", "SOCKS5", "SOCKS4"]:
                    if proto in proxy.types:
                        return proto
                raise RuntimeError(
                    f"No suitable protocol found for HTTP scheme in {proxy.types.keys()}"
                )
        else:  # HTTPS
            # Deterministic priority order for HTTPS
            for proto in ["HTTPS", "SOCKS5", "SOCKS4"]:
                if proto in proxy.types:
                    return proto
            raise RuntimeError(
                f"No suitable protocol found for HTTPS scheme in {proxy.types.keys()}"
            )

    async def _stream(self, reader, writer, length=65536, scheme=None, inject=None):
        checked = False

        try:
            while not reader.at_eof():
                data = await asyncio.wait_for(reader.read(length), self._timeout)
                if not data:
                    writer.close()
                    break
                elif scheme and not checked:
                    self._check_response(data, scheme)

                    if inject.get("headers") is not None and len(inject["headers"]) > 0:
                        data = self._inject_headers(data, scheme, inject["headers"])

                    checked = True

                writer.write(data)
                await writer.drain()

        except (
            asyncio.TimeoutError,
            ConnectionResetError,
            OSError,
            ProxyRecvError,
            BadStatusError,
            BadResponseError,
        ) as e:
            raise ErrorOnStream(e) from e

    def _check_response(self, data, scheme):
        if scheme == "HTTP" and self._http_allowed_codes:
            line = data.split(b"\r\n", 1)[0].decode()
            try:
                header = parse_status_line(line)
            except BadStatusLine as e:
                raise BadResponseError from e
            if header["Status"] not in self._http_allowed_codes:
                raise BadStatusError(
                    "%r not in %r" % (header["Status"], self._http_allowed_codes)
                )

    def _inject_headers(self, data, scheme, headers):
        custom_lines = []

        if scheme == "HTTP" or scheme == "HTTPS":
            status_line, rest_lines = data.split(b"\r\n", 1)
            custom_lines.append(status_line)

            for k, v in headers.items():
                custom_lines.append(("%s: %s" % (k, v)).encode())

            custom_lines.append(rest_lines)
            data = b"\r\n".join(custom_lines)

        return data
