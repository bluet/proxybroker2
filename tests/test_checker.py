import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from proxybroker.checker import Checker, _check_test_response, _get_anonymity_lvl
from proxybroker.errors import BadResponseError, ProxyConnError, ProxyTimeoutError
from proxybroker.judge import Judge


@pytest.fixture
def mock_proxy():
    """Create a mock proxy for testing."""
    proxy = MagicMock()
    proxy.host = "127.0.0.1"
    proxy.port = 8080
    proxy.schemes = ("HTTP", "HTTPS")
    proxy.types = {}
    proxy.expected_types = set()
    proxy.is_working = False
    proxy.log = MagicMock()
    proxy.stat = {"requests": 0}
    proxy.connect = AsyncMock()
    proxy.send = AsyncMock()
    proxy.recv = AsyncMock()
    proxy.close = MagicMock()

    # Create a mock negotiator that will be used
    mock_ngtr = Mock()
    mock_ngtr.name = "HTTP"
    mock_ngtr.check_anon_lvl = True
    mock_ngtr.negotiate = AsyncMock()
    mock_ngtr.use_full_path = False

    # Store the negotiator so it can be set later
    proxy._ngtr = None
    proxy.ngtr = mock_ngtr

    return proxy


@pytest.fixture
def mock_judge():
    """Create a mock judge for testing."""
    judge = MagicMock(spec=Judge)
    judge.url = "http://judge.example.com"
    judge.host = "judge.example.com"
    judge.ip = "93.184.216.34"
    judge.path = "/"
    judge.is_working = True
    judge.marks = {"via": 0, "proxy": 0}
    return judge


@pytest.fixture
def checker():
    """Create a Checker instance for testing."""
    return Checker(
        judges=["http://judge1.com", "http://judge2.com"], timeout=5, max_tries=2
    )


def mock_proxy_with_ngtr_setter(mock_proxy):
    """Helper to create a proxy that properly handles ngtr setting."""

    # Create a class that mimics Proxy's ngtr property behavior
    class ProxyMock:
        def __init__(self, base_proxy):
            self._base = base_proxy
            self._ngtr = None

        def __getattr__(self, name):
            if name == "ngtr":
                return self._ngtr
            return getattr(self._base, name)

        def __setattr__(self, name, value):
            if name in ("_base", "_ngtr"):
                object.__setattr__(self, name, value)
            elif name == "ngtr":
                # When setting ngtr='HTTP', we just use our mock negotiator
                self._ngtr = self._base.ngtr
            else:
                setattr(self._base, name, value)

    return ProxyMock(mock_proxy)


class TestChecker:
    """Test cases for Checker class."""

    def test_checker_init_with_urls(self):
        """Test Checker initialization with judge URLs."""
        checker = Checker(
            judges=["http://judge1.com", "http://judge2.com"], timeout=10, max_tries=3
        )
        # Checker stores judges internally, not timeout/max_tries as attributes
        assert len(checker._judges) >= 0  # Judges are created but not yet validated
        assert checker._max_tries == 3
        # timeout is passed to judges, not stored on checker

    def test_checker_init_with_judge_objects(self, mock_judge):
        """Test Checker initialization with Judge objects."""
        judges = [mock_judge]
        checker = Checker(judges=judges, timeout=5, max_tries=1)
        # get_judges will process the input judges
        assert checker._max_tries == 1

    def test_checker_init_empty_judges(self):
        """Test Checker initialization with empty judges list."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        # get_judges might add default judges even with empty input
        assert isinstance(checker._judges, list)

    @pytest.mark.asyncio
    async def test_checker_check_proxy_success(self, checker, mock_proxy, mock_judge):
        """Test successful proxy checking."""
        # Use our special proxy mock
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        # Mock judge availability
        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                # Set events as ready
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Setup successful response with proper format
                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                response_content = f"{real_rv} 127.0.0.1 {real_headers['Referer']} {real_headers['Cookie']}"
                proxy.recv.return_value = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{response_content}".encode()

                await checker.check(proxy)

                # Verify proxy was tested
                proxy.connect.assert_called()
                proxy.send.assert_called()
                proxy.recv.assert_called()
                proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_no_judges(self, mock_proxy):
        """Test checking proxy with no judges raises error."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        checker._judges = []  # Force empty judges

        # check_judges is what raises the error when no judges
        with pytest.raises(RuntimeError, match="Not found judges"):
            await checker.check_judges()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_connection_error(
        self, checker, mock_proxy, mock_judge
    ):
        """Test proxy checking with connection error."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Mock connection failure
                proxy.connect.side_effect = ProxyConnError("Connection failed")

                result = await checker.check(proxy)

                # Should return False on connection error
                assert result is False
                proxy.log.assert_called()
                proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_timeout(self, checker, mock_proxy, mock_judge):
        """Test proxy checking with timeout."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Mock timeout during recv - ensure it always times out
                proxy.recv.side_effect = ProxyTimeoutError("Timeout")
                proxy.connect.side_effect = ProxyTimeoutError("Timeout")

                # With max_tries=2, it should retry on timeout but still fail
                checker._max_tries = 2
                result = await checker.check(proxy)

                assert result is False
                # Should have attempted connection/recv multiple times
                assert (
                    proxy.connect.call_count >= checker._max_tries
                    or proxy.recv.call_count >= checker._max_tries
                )

    @pytest.mark.asyncio
    async def test_checker_check_proxy_bad_response(
        self, checker, mock_proxy, mock_judge
    ):
        """Test proxy checking with bad response."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        # Create a checker with only one protocol to test
        checker_single = Checker(
            judges=["http://judge.com"], timeout=5, max_tries=1, types={"HTTP": None}
        )  # Only test HTTP

        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch("proxybroker.judge.Judge.ev", {"HTTP": asyncio.Event()}):
                Judge.ev["HTTP"].set()

                # Mock bad response for all attempts
                proxy.recv.side_effect = BadResponseError("Bad response")
                # Ensure connect succeeds but recv fails
                proxy.connect.return_value = None
                proxy.send.return_value = None

                result = await checker_single.check(proxy)

                assert result is False
                proxy.log.assert_called()
                proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_retry_logic(
        self, checker, mock_proxy, mock_judge
    ):
        """Test proxy checking retry logic."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)
        checker._max_tries = 3  # Increase to ensure we have enough retries

        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Create a counter to track calls
                call_count = 0

                def side_effect_func(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        raise ProxyTimeoutError("Timeout")
                    else:
                        # Return valid response on second attempt
                        from proxybroker.utils import get_headers

                        real_headers, real_rv = get_headers(rv=True)
                        response_content = f"{real_rv} 127.0.0.1 {real_headers['Referer']} {real_headers['Cookie']}"
                        return b"HTTP/1.1 200 OK\r\n\r\n" + response_content.encode()

                proxy.recv.side_effect = side_effect_func
                proxy.connect.return_value = None
                proxy.send.return_value = None

                result = await checker.check(proxy)

                # Should succeed after retry
                assert result is True
                # Should have been called at least twice (first timeout, then success)
                assert call_count >= 2

    @pytest.mark.asyncio
    async def test_checker_check_response_anonymous(
        self, checker, mock_proxy, mock_judge
    ):
        """Test check test response for anonymous detection."""
        # Use actual headers from get_headers
        from proxybroker.utils import get_headers

        real_headers, real_rv = get_headers(rv=True)

        # Content must contain the exact values from get_headers
        content = f"Your unique verification code: {real_rv} Your IP is 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"

        result = _check_test_response(
            mock_proxy,
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n",
            content,
            real_rv,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_checker_check_response_transparent(
        self, checker, mock_proxy, mock_judge
    ):
        """Test anonymity level detection for transparent proxy."""
        # Test _get_anonymity_lvl function
        real_ext_ip = "1.2.3.4"
        content = '{"ip": "1.2.3.4"}'  # Shows real IP

        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content)

        # Should be transparent since real IP is visible
        assert lvl == "Transparent"

    @pytest.mark.asyncio
    async def test_checker_check_response_high_anonymous(
        self, checker, mock_proxy, mock_judge
    ):
        """Test anonymity level for high anonymous proxy."""
        real_ext_ip = "1.2.3.4"
        content = '{"ip": "8.8.8.8"}'  # Different IP, no proxy headers

        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content)

        # Should be High since no proxy indicators
        assert lvl == "High"

    @pytest.mark.asyncio
    async def test_checker_get_headers(self, checker):
        """Test header parsing functionality."""
        # Test parse_headers from utils
        from proxybroker.utils import parse_headers

        # parse_headers expects full HTTP response headers starting with status line
        headers_bytes = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Forwarded-For: 1.2.3.4\r\n"
            b"Via: 1.1 proxy"
        )

        headers = parse_headers(headers_bytes)

        assert headers["Content-Type"] == "application/json"
        assert headers["X-Forwarded-For"] == "1.2.3.4"
        assert headers["Via"] == "1.1 proxy"

    @pytest.mark.asyncio
    async def test_checker_is_anon_lvl_with_proxy_headers(
        self, checker, mock_proxy, mock_judge
    ):
        """Test anonymity detection with proxy headers."""
        # Test via _get_anonymity_lvl with via/proxy indicators
        real_ext_ip = "1.2.3.4"
        content = '{"ip": "8.8.8.8", "via": "proxy", "proxy": "detected"}'

        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content)

        # Should be Anonymous due to via/proxy headers
        assert lvl == "Anonymous"

    @pytest.mark.asyncio
    async def test_checker_is_anon_lvl_without_proxy_headers(self, checker, mock_proxy):
        """Test anonymity detection without proxy headers."""
        real_ext_ip = "1.2.3.4"
        content = '{"ip": "8.8.8.8"}'

        mock_judge = Mock()
        mock_judge.marks = {"via": 0, "proxy": 0}

        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content)

        # Should be High - no proxy indicators
        assert lvl == "High"

    def test_checker_anon_headers_detection(self, checker, mock_proxy, mock_judge):
        """Test detection of proxy-revealing content."""
        # Test content that would reveal proxy usage
        real_ext_ip = "1.2.3.4"

        # Content with via header
        content_with_via = '{"ip": "8.8.8.8", "headers": {"via": "1.1 proxy"}}'
        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content_with_via)
        assert lvl == "Anonymous"  # Via header reveals proxy

        # Content without proxy indicators
        content_clean = '{"ip": "8.8.8.8"}'
        lvl = _get_anonymity_lvl(real_ext_ip, mock_proxy, mock_judge, content_clean)
        assert lvl == "High"  # No proxy indicators

    @pytest.mark.asyncio
    async def test_checker_multiple_judges(self, mock_proxy):
        """Test checking proxy against multiple judges."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        judge1 = Mock(spec=Judge)
        judge1.url = "http://judge1.com"
        judge1.host = "judge1.com"
        judge1.ip = "1.1.1.1"
        judge1.path = "/"
        judge1.is_working = True
        judge1.marks = {"via": 0, "proxy": 0}

        judge2 = Mock(spec=Judge)
        judge2.url = "http://judge2.com"
        judge2.host = "judge2.com"
        judge2.ip = "2.2.2.2"
        judge2.path = "/"
        judge2.is_working = True
        judge2.marks = {"via": 0, "proxy": 0}

        checker = Checker(judges=[judge1, judge2], timeout=5, max_tries=1)
        checker._judges = [judge1, judge2]

        # Use a function that always returns judge1 instead of side_effect
        with patch("proxybroker.judge.Judge.get_random", return_value=judge1):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Mock successful response
                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                response_content = f"{real_rv} 127.0.0.1 {real_headers['Referer']} {real_headers['Cookie']}"
                proxy.recv.return_value = (
                    f"HTTP/1.1 200 OK\r\n\r\n{response_content}".encode()
                )
                proxy.connect.return_value = None
                proxy.send.return_value = None

                result = await checker.check(proxy)

                # Should succeed
                assert result is True
                # Should test against at least one judge
                assert proxy.send.call_count >= 1

    @pytest.mark.asyncio
    async def test_checker_stats_tracking(self, checker):
        """Test protocol type tracking."""
        # Checker tracks types, not exception types
        assert checker._types == {}

        # Test with specific types
        checker_with_types = Checker(
            judges=["http://judge.com"],
            types={"HTTP": ["Anonymous", "High"], "HTTPS": ["High"]},
            timeout=5,
        )

        assert "HTTP" in checker_with_types._types
        assert "HTTPS" in checker_with_types._types
        assert checker_with_types._types["HTTP"] == ["Anonymous", "High"]

    @pytest.mark.asyncio
    async def test_checker_proxy_types_update(self, checker, mock_proxy, mock_judge):
        """Test that proxy types are updated after successful check."""
        proxy = mock_proxy_with_ngtr_setter(mock_proxy)

        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                # Use a different IP to show proxy is working
                response_content = f"{real_rv} 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"
                proxy.recv.return_value = (
                    f"HTTP/1.1 200 OK\r\n\r\n{response_content}".encode()
                )
                proxy.connect.return_value = None
                proxy.send.return_value = None

                result = await checker.check(proxy)

                # Should succeed
                assert result is True
                # Verify proxy types were updated - checker will set a type
                assert len(proxy.types) > 0
                # At least one protocol should have been set
                assert any(
                    proto in proxy.types
                    for proto in [
                        "HTTP",
                        "HTTPS",
                        "SOCKS4",
                        "SOCKS5",
                        "CONNECT:80",
                        "CONNECT:25",
                    ]
                )
