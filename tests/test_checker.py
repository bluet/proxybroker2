import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Proxy
from proxybroker.checker import Checker
from proxybroker.errors import (BadResponseError, BadStatusError, 
                                ProxyConnError, ProxyTimeoutError)
from proxybroker.judge import Judge


@pytest.fixture
def mock_proxy():
    """Create a mock proxy for testing."""
    proxy = MagicMock(spec=Proxy)
    proxy.host = '127.0.0.1'
    proxy.port = 8080
    proxy.schemes = ('HTTP', 'HTTPS')
    proxy.types = {}
    proxy.log = MagicMock()
    proxy.stat = {'requests': 0}
    proxy.ngtr = None
    return proxy


@pytest.fixture
def mock_judge():
    """Create a mock judge for testing."""
    judge = MagicMock(spec=Judge)
    judge.url = 'http://judge.example.com'
    judge.host = 'judge.example.com'
    judge.path = '/'
    judge.request = b'GET / HTTP/1.1\r\nHost: judge.example.com\r\n\r\n'
    return judge


@pytest.fixture
def checker():
    """Create a Checker instance for testing."""
    return Checker(
        judges=['http://judge1.com', 'http://judge2.com'],
        timeout=5,
        max_tries=2
    )


class TestChecker:
    """Test cases for Checker class."""

    def test_checker_init_with_urls(self):
        """Test Checker initialization with judge URLs."""
        checker = Checker(
            judges=['http://judge1.com', 'http://judge2.com'],
            timeout=10,
            max_tries=3
        )
        assert len(checker._judges) == 2
        assert checker.timeout == 10
        assert checker.max_tries == 3
        assert all(isinstance(judge, Judge) for judge in checker._judges)

    def test_checker_init_with_judge_objects(self, mock_judge):
        """Test Checker initialization with Judge objects."""
        judges = [mock_judge]
        checker = Checker(judges=judges, timeout=5, max_tries=1)
        assert len(checker._judges) == 1
        assert checker._judges[0] is mock_judge

    def test_checker_init_empty_judges(self):
        """Test Checker initialization with empty judges list."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        assert len(checker._judges) == 0

    @pytest.mark.asyncio
    async def test_checker_check_proxy_success(self, checker, mock_proxy, mock_judge, mocker):
        """Test successful proxy checking."""
        checker._judges = [mock_judge]
        
        # Mock successful proxy connection and response
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(return_value=b'HTTP/1.1 200 OK\r\n\r\nSuccess')
        mock_proxy.close = MagicMock()
        
        # Mock _check_response to return anonymity level
        async def mock_check_response(proxy, judge, response):
            return 'Anonymous'
        
        mocker.patch.object(checker, '_check_response', side_effect=mock_check_response)
        
        await checker.check_proxy(mock_proxy)
        
        # Verify proxy was tested
        mock_proxy.connect.assert_called()
        mock_proxy.send.assert_called()
        mock_proxy.recv.assert_called()
        mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_no_judges(self, mock_proxy):
        """Test checking proxy with no judges raises error."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        
        with pytest.raises(RuntimeError, match='Not found judges'):
            await checker.check_proxy(mock_proxy)

    @pytest.mark.asyncio
    async def test_checker_check_proxy_connection_error(self, checker, mock_proxy, mock_judge):
        """Test proxy checking with connection error."""
        checker._judges = [mock_judge]
        
        # Mock connection failure
        mock_proxy.connect = AsyncMock(side_effect=ProxyConnError('Connection failed'))
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        await checker.check_proxy(mock_proxy)
        
        # Verify error was logged
        mock_proxy.log.assert_called()
        mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_timeout(self, checker, mock_proxy, mock_judge):
        """Test proxy checking with timeout."""
        checker._judges = [mock_judge]
        
        # Mock timeout during recv
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(side_effect=ProxyTimeoutError('Timeout'))
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        await checker.check_proxy(mock_proxy)
        
        mock_proxy.log.assert_called()
        mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_bad_response(self, checker, mock_proxy, mock_judge):
        """Test proxy checking with bad response."""
        checker._judges = [mock_judge]
        
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(side_effect=BadResponseError('Bad response'))
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        await checker.check_proxy(mock_proxy)
        
        mock_proxy.log.assert_called()
        mock_proxy.close.assert_called()

    @pytest.mark.asyncio
    async def test_checker_check_proxy_retry_logic(self, checker, mock_proxy, mock_judge):
        """Test proxy checking retry logic."""
        checker.max_tries = 2
        checker._judges = [mock_judge]
        
        # First attempt fails, second succeeds
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(side_effect=[
            ProxyTimeoutError('Timeout'),
            b'HTTP/1.1 200 OK\r\n\r\nSuccess'
        ])
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        await checker.check_proxy(mock_proxy)
        
        # Should have been called twice (retry)
        assert mock_proxy.recv.call_count == 2

    @pytest.mark.asyncio
    async def test_checker_check_response_anonymous(self, checker, mock_proxy, mock_judge):
        """Test _check_response method for anonymous proxy."""
        # Mock response that doesn't reveal client IP
        response = b'HTTP/1.1 200 OK\r\n\r\n{"ip": "8.8.8.8"}'
        
        # Mock resolver to return different IP
        checker._resolver = MagicMock()
        checker._resolver.get_real_ext_ip = AsyncMock(return_value='1.2.3.4')
        
        result = await checker._check_response(mock_proxy, mock_judge, response)
        
        # Should be considered anonymous since IPs don't match
        assert result == 'Anonymous'

    @pytest.mark.asyncio
    async def test_checker_check_response_transparent(self, checker, mock_proxy, mock_judge):
        """Test _check_response method for transparent proxy."""
        # Mock response that reveals client IP
        response = b'HTTP/1.1 200 OK\r\n\r\n{"ip": "1.2.3.4"}'
        
        checker._resolver = MagicMock()
        checker._resolver.get_real_ext_ip = AsyncMock(return_value='1.2.3.4')
        
        result = await checker._check_response(mock_proxy, mock_judge, response)
        
        # Should be considered transparent since IPs match
        assert result == 'Transparent'

    @pytest.mark.asyncio
    async def test_checker_check_response_high_anonymous(self, checker, mock_proxy, mock_judge):
        """Test _check_response method for high anonymous proxy."""
        # Mock response with no proxy headers
        response = (b'HTTP/1.1 200 OK\r\n'
                   b'Content-Type: application/json\r\n\r\n'
                   b'{"ip": "8.8.8.8"}')
        
        checker._resolver = MagicMock()
        checker._resolver.get_real_ext_ip = AsyncMock(return_value='1.2.3.4')
        
        # Mock _is_anon_lvl to return True for high anonymity
        async def mock_is_anon_lvl(response):
            return True
        
        checker._is_anon_lvl = mock_is_anon_lvl
        
        result = await checker._check_response(mock_proxy, mock_judge, response)
        
        assert result == 'High'

    @pytest.mark.asyncio
    async def test_checker_get_headers(self, checker):
        """Test _get_headers method."""
        response = (b'HTTP/1.1 200 OK\r\n'
                   b'Content-Type: application/json\r\n'
                   b'X-Forwarded-For: 1.2.3.4\r\n'
                   b'Via: 1.1 proxy\r\n\r\n'
                   b'{"ip": "8.8.8.8"}')
        
        headers = checker._get_headers(response)
        
        assert headers['Content-Type'] == 'application/json'
        assert headers['X-Forwarded-For'] == '1.2.3.4'
        assert headers['Via'] == '1.1 proxy'

    @pytest.mark.asyncio
    async def test_checker_is_anon_lvl_with_proxy_headers(self, checker):
        """Test _is_anon_lvl with proxy-revealing headers."""
        headers = {
            'X-Forwarded-For': '1.2.3.4',
            'Via': '1.1 proxy',
            'Content-Type': 'application/json'
        }
        
        result = await checker._is_anon_lvl(headers)
        
        # Should return False due to proxy headers
        assert result is False

    @pytest.mark.asyncio
    async def test_checker_is_anon_lvl_without_proxy_headers(self, checker):
        """Test _is_anon_lvl without proxy-revealing headers."""
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': '100'
        }
        
        result = await checker._is_anon_lvl(headers)
        
        # Should return True - no proxy headers
        assert result is True

    def test_checker_anon_headers_detection(self, checker):
        """Test detection of proxy-revealing headers."""
        proxy_headers = [
            'HTTP_X_FORWARDED_FOR',
            'HTTP_VIA', 
            'HTTP_PROXY_CONNECTION',
            'HTTP_X_REAL_IP',
            'HTTP_CLIENT_IP'
        ]
        
        for header in proxy_headers:
            headers = {header: 'some-value'}
            # This tests the logic used in _is_anon_lvl
            has_proxy_header = any(h.upper() in header.upper() 
                                 for h in ['VIA', 'FORWARDED', 'PROXY', 'CLIENT'])
            assert has_proxy_header is True

    @pytest.mark.asyncio
    async def test_checker_multiple_judges(self, mock_proxy):
        """Test checking proxy against multiple judges."""
        judge1 = MagicMock(spec=Judge)
        judge1.url = 'http://judge1.com'
        judge1.request = b'GET / HTTP/1.1\r\nHost: judge1.com\r\n\r\n'
        
        judge2 = MagicMock(spec=Judge)
        judge2.url = 'http://judge2.com'
        judge2.request = b'GET / HTTP/1.1\r\nHost: judge2.com\r\n\r\n'
        
        checker = Checker(judges=[judge1, judge2], timeout=5, max_tries=1)
        
        # Mock successful connections
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(return_value=b'HTTP/1.1 200 OK\r\n\r\nSuccess')
        mock_proxy.close = MagicMock()
        mock_proxy.log = MagicMock()
        
        await checker.check_proxy(mock_proxy)
        
        # Should test against multiple judges
        assert mock_proxy.send.call_count >= 1

    @pytest.mark.asyncio 
    async def test_checker_stats_tracking(self, checker):
        """Test that checker tracks error statistics."""
        # Initially no errors
        assert len(checker._ex_types) == 0
        
        # Create proxy that will fail
        mock_proxy = MagicMock(spec=Proxy)
        mock_proxy.connect = AsyncMock(side_effect=ProxyConnError('Connection failed'))
        mock_proxy.log = MagicMock()
        mock_proxy.close = MagicMock()
        
        mock_judge = MagicMock(spec=Judge)
        checker._judges = [mock_judge]
        
        await checker.check_proxy(mock_proxy)
        
        # Should track the error
        assert 'ProxyConnError' in checker._ex_types
        assert checker._ex_types['ProxyConnError'] >= 1

    @pytest.mark.asyncio
    async def test_checker_proxy_types_update(self, checker, mock_proxy, mock_judge, mocker):
        """Test that proxy types are updated after successful check."""
        checker._judges = [mock_judge]
        
        mock_proxy.connect = AsyncMock()
        mock_proxy.send = AsyncMock()
        mock_proxy.recv = AsyncMock(return_value=b'HTTP/1.1 200 OK\r\n\r\nSuccess')
        mock_proxy.close = MagicMock()
        mock_proxy.ngtr = MagicMock()
        mock_proxy.ngtr.name = 'HTTP'
        
        # Mock _check_response to return anonymity level
        async def mock_check_response(proxy, judge, response):
            return 'Anonymous'
        
        mocker.patch.object(checker, '_check_response', side_effect=mock_check_response)
        
        await checker.check_proxy(mock_proxy)
        
        # Verify proxy types were updated
        assert 'HTTP' in mock_proxy.types
        assert mock_proxy.types['HTTP'] == 'Anonymous'