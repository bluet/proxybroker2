"""Mock HTTP server for testing ProxyBroker components."""

from aiohttp import web


class MockJudgeServer:
    """Mock judge server that returns JSON responses for testing."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.app = None
        self.runner = None
        self.site = None
        self.server_port = None

    async def start(self):
        """Start the mock server."""
        self.app = web.Application()
        self.app.router.add_get("/", self.judge_handler)
        self.app.router.add_post("/", self.judge_handler)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        # Get the actual port if we used port 0
        self.server_port = self.site._server.sockets[0].getsockname()[1]

    async def stop(self):
        """Stop the mock server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def judge_handler(self, request):
        """Handle judge requests and return appropriate responses."""
        # Simulate different judge responses
        response_data = {
            "ip": "8.8.8.8",  # Different from client IP to simulate anonymity
            "headers": {
                "User-Agent": request.headers.get("User-Agent", ""),
                "Accept": request.headers.get("Accept", ""),
            },
        }

        # Check for proxy headers to simulate transparency detection
        proxy_headers = {}
        for header in request.headers:
            if any(
                h.lower() in header.lower()
                for h in ["via", "forwarded", "proxy", "client"]
            ):
                proxy_headers[header] = request.headers[header]

        if proxy_headers:
            response_data["proxy_headers"] = proxy_headers

        return web.json_response(response_data)

    @property
    def url(self):
        """Get the server URL."""
        return f"http://{self.host}:{self.server_port}"


class MockProviderServer:
    """Mock provider server that returns proxy lists."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.app = None
        self.runner = None
        self.site = None
        self.server_port = None
        self.proxy_list = [
            "127.0.0.1:8080",
            "127.0.0.2:8080",
            "127.0.0.3:8080",
        ]

    async def start(self):
        """Start the mock server."""
        self.app = web.Application()
        self.app.router.add_get("/", self.provider_handler)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        self.server_port = self.site._server.sockets[0].getsockname()[1]

    async def stop(self):
        """Stop the mock server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def provider_handler(self, request):
        """Handle provider requests and return proxy lists."""
        # Return HTML page with proxy list
        html_content = f"""
        <html>
        <body>
        <h1>Proxy List</h1>
        <p>Here are some proxies:</p>
        <ul>
        {"".join(f"<li>{proxy}</li>" for proxy in self.proxy_list)}
        </ul>
        <div>
        More proxies: {" ".join(self.proxy_list)}
        </div>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type="text/html")

    @property
    def url(self):
        """Get the server URL."""
        return f"http://{self.host}:{self.server_port}"


async def create_mock_judge(host="127.0.0.1", port=0):
    """Create and start a mock judge server."""
    server = MockJudgeServer(host, port)
    await server.start()
    return server


async def create_mock_provider(host="127.0.0.1", port=0):
    """Create and start a mock provider server."""
    server = MockProviderServer(host, port)
    await server.start()
    return server
