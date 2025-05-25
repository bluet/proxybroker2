import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from proxybroker.checker import Checker
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

    # Create a mock negotiator
    mock_ngtr = Mock()
    mock_ngtr.name = "HTTP"
    mock_ngtr.check_anon_lvl = True
    mock_ngtr.negotiate = AsyncMock()
    mock_ngtr.use_full_path = False
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


class TestCheckerBehavior:
    """Test Checker from user perspective - does it correctly validate proxy functionality?"""

    def test_checker_initialization(self):
        """Test that Checker can be created with different configurations."""
        # Basic initialization
        checker = Checker(judges=["http://judge.com"], timeout=10, max_tries=3)
        assert checker._max_tries == 3

        # With specific types
        checker_typed = Checker(
            judges=["http://judge.com"],
            types={"HTTP": ["High"], "HTTPS": ["Anonymous"]},
            timeout=5,
        )
        assert "HTTP" in checker_typed._types
        assert "HTTPS" in checker_typed._types

        # Empty judges should still work (might use defaults)
        checker_empty = Checker(judges=[], timeout=5, max_tries=1)
        assert isinstance(checker_empty._judges, list)

    @pytest.mark.asyncio
    async def test_proxy_validation_success(self, checker, mock_proxy, mock_judge):
        """Test that working proxies are correctly identified as functional."""
        # Setup: Mock a working proxy environment
        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch(
                "proxybroker.judge.Judge.ev",
                {
                    "HTTP": asyncio.Event(),
                    "HTTPS": asyncio.Event(),
                    "SMTP": asyncio.Event(),
                },
            ):
                # Set judge events as ready
                Judge.ev["HTTP"].set()
                Judge.ev["HTTPS"].set()
                Judge.ev["SMTP"].set()

                # Mock successful proxy response with expected format
                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                response_content = f"{real_rv} 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"
                mock_proxy.recv.return_value = (
                    f"HTTP/1.1 200 OK\r\n\r\n{response_content}".encode()
                )
                mock_proxy.connect.return_value = None
                mock_proxy.send.return_value = None

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Working proxy should return True
                assert result is True
                mock_proxy.connect.assert_called()
                mock_proxy.send.assert_called()
                mock_proxy.recv.assert_called()
                mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_proxy_validation_connection_failure(
        self, checker, mock_proxy, mock_judge
    ):
        """Test that proxies that fail to connect are correctly identified as non-functional."""
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
                mock_proxy.connect.side_effect = ProxyConnError("Connection refused")

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Non-working proxy should return False
                assert result is False
                mock_proxy.log.assert_called()
                mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_proxy_validation_timeout(self, checker, mock_proxy, mock_judge):
        """Test that slow/unresponsive proxies are correctly identified as non-functional."""
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

                # Mock timeout during connection/response
                mock_proxy.connect.side_effect = ProxyTimeoutError("Timeout")

                # Act: Check the proxy with retries
                result = await checker.check(mock_proxy)

                # Assert: Timed out proxy should return False
                assert result is False
                # Should have attempted connection multiple times due to retries
                assert mock_proxy.connect.call_count >= checker._max_tries

    @pytest.mark.asyncio
    async def test_proxy_validation_bad_response(self, checker, mock_proxy, mock_judge):
        """Test that proxies returning invalid responses are identified as non-functional."""
        with patch("proxybroker.judge.Judge.get_random", return_value=mock_judge):
            with patch("proxybroker.judge.Judge.ev", {"HTTP": asyncio.Event()}):
                Judge.ev["HTTP"].set()

                # Mock bad response from proxy
                mock_proxy.recv.side_effect = BadResponseError("Invalid HTTP response")
                mock_proxy.connect.return_value = None
                mock_proxy.send.return_value = None

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Proxy with bad response should return False
                assert result is False
                mock_proxy.log.assert_called()
                mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_proxy_retry_mechanism(self, checker, mock_proxy, mock_judge):
        """Test that checker retries failed checks before giving up."""
        checker._max_tries = 3  # Ensure enough retries for test

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

                # Mock: Fail first attempt, succeed on retry
                call_count = 0

                def side_effect_func(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        raise ProxyTimeoutError("First attempt timeout")
                    else:
                        from proxybroker.utils import get_headers

                        real_headers, real_rv = get_headers(rv=True)
                        response_content = f"{real_rv} 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"
                        return b"HTTP/1.1 200 OK\r\n\r\n" + response_content.encode()

                mock_proxy.recv.side_effect = side_effect_func
                mock_proxy.connect.return_value = None
                mock_proxy.send.return_value = None

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Should succeed after retry
                assert result is True
                assert call_count >= 2  # Should have been called multiple times

    @pytest.mark.asyncio
    async def test_anonymity_level_detection(self, checker, mock_proxy, mock_judge):
        """Test that checker correctly detects proxy anonymity levels."""
        from proxybroker.checker import _get_anonymity_lvl

        # Test transparent proxy (shows real IP)
        real_ip = "1.2.3.4"
        transparent_content = '{"ip": "1.2.3.4", "headers": {}}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, transparent_content)
        assert lvl == "Transparent"

        # Test anonymous proxy (different IP, some proxy headers)
        anonymous_content = '{"ip": "8.8.8.8", "via": "1.1 proxy"}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, anonymous_content)
        assert lvl == "Anonymous"

        # Test high anonymous proxy (different IP, no proxy headers)
        high_anon_content = '{"ip": "8.8.8.8"}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, high_anon_content)
        assert lvl == "High"

    @pytest.mark.asyncio
    async def test_proxy_types_are_updated(self, checker, mock_proxy, mock_judge):
        """Test that successful validation updates proxy types/protocols."""
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

                # Mock successful validation
                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                response_content = f"{real_rv} 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"
                mock_proxy.recv.return_value = (
                    f"HTTP/1.1 200 OK\r\n\r\n{response_content}".encode()
                )
                mock_proxy.connect.return_value = None
                mock_proxy.send.return_value = None

                # Initially no types
                assert len(mock_proxy.types) == 0

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Successful check should update proxy types
                assert result is True
                assert len(mock_proxy.types) > 0  # Should have protocol types set

    @pytest.mark.asyncio
    async def test_checker_with_no_judges_fails(self, mock_proxy):
        """Test that checker fails gracefully when no judges are available."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        checker._judges = []  # Force empty judges

        # Should raise error when no judges available
        with pytest.raises(RuntimeError, match="Not found judges"):
            await checker.check_judges()

    @pytest.mark.asyncio
    async def test_checker_with_multiple_judges(self, mock_proxy):
        """Test that checker can work with multiple judge servers."""
        judge1 = Mock(spec=Judge)
        judge1.url = "http://judge1.com"
        judge1.is_working = True
        judge1.marks = {"via": 0, "proxy": 0}

        judge2 = Mock(spec=Judge)
        judge2.url = "http://judge2.com"
        judge2.is_working = True
        judge2.marks = {"via": 0, "proxy": 0}

        checker = Checker(judges=[judge1, judge2], timeout=5, max_tries=1)

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

                # Mock successful validation
                from proxybroker.utils import get_headers

                real_headers, real_rv = get_headers(rv=True)
                response_content = f"{real_rv} 8.8.8.8 {real_headers['Referer']} {real_headers['Cookie']}"
                mock_proxy.recv.return_value = (
                    f"HTTP/1.1 200 OK\r\n\r\n{response_content}".encode()
                )
                mock_proxy.connect.return_value = None
                mock_proxy.send.return_value = None

                # Act: Check the proxy
                result = await checker.check(mock_proxy)

                # Assert: Should work with multiple judges
                assert result is True
                assert mock_proxy.send.call_count >= 1

    def test_checker_protocol_filtering(self):
        """Test that checker can be configured to only check specific protocols."""
        # Checker with specific protocol types
        checker_http_only = Checker(
            judges=["http://judge.com"],
            types={"HTTP": ["High", "Anonymous"]},
            timeout=5,
        )

        assert "HTTP" in checker_http_only._types
        assert checker_http_only._types["HTTP"] == ["High", "Anonymous"]

        # Checker with multiple protocols
        checker_multi = Checker(
            judges=["http://judge.com"],
            types={
                "HTTP": ["High"],
                "HTTPS": ["Anonymous", "High"],
                "SOCKS5": ["High"],
            },
            timeout=5,
        )

        assert len(checker_multi._types) == 3
        assert "HTTP" in checker_multi._types
        assert "HTTPS" in checker_multi._types
        assert "SOCKS5" in checker_multi._types

    @pytest.mark.asyncio
    async def test_response_validation_logic(self, checker):
        """Test the core response validation logic."""
        from proxybroker.checker import _check_test_response
        from proxybroker.utils import get_headers

        # Get real verification values
        real_headers, real_rv = get_headers(rv=True)

        # Test valid response with correct verification values
        valid_content = f"Your code: {real_rv} Your IP: 8.8.8.8 Referer: {real_headers['Referer']} Cookie: {real_headers['Cookie']}"
        result = _check_test_response(
            mock_proxy=MagicMock(),
            response=b"HTTP/1.1 200 OK\r\n\r\n",
            content=valid_content,
            rv=real_rv,
        )
        assert result is True

        # Test invalid response with wrong verification code
        invalid_content = (
            f"Your code: wrong_code Your IP: 8.8.8.8 Referer: {real_headers['Referer']}"
        )
        result = _check_test_response(
            mock_proxy=MagicMock(),
            response=b"HTTP/1.1 200 OK\r\n\r\n",
            content=invalid_content,
            rv=real_rv,
        )
        assert result is False
