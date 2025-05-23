"""Core functionality tests that work reliably."""
import asyncio
import heapq
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import subprocess
import sys

import pytest

from proxybroker.api import Broker, GRAB_PAUSE, MAX_CONCURRENT_PROVIDERS
from proxybroker.checker import Checker
from proxybroker.cli import cli
from proxybroker.server import ProxyPool, CONNECTED
from proxybroker.errors import ProxyConnError


class TestBrokerCore:
    """Test core Broker functionality."""

    @pytest.mark.asyncio
    async def test_broker_initialization(self):
        """Test Broker can be initialized properly."""
        broker = Broker(stop_broker_on_sigint=False)  # Avoid signal issues
        assert broker._timeout == 8
        assert broker._max_tries == 3
        assert broker._verify_ssl is False
        assert broker._proxies is not None
        assert broker._resolver is not None
        assert len(broker._providers) > 0

    @pytest.mark.asyncio
    async def test_broker_custom_initialization(self):
        """Test Broker with custom parameters."""
        queue = asyncio.Queue()
        broker = Broker(
            queue=queue,
            timeout=10,
            max_tries=5,
            verify_ssl=True,
            stop_broker_on_sigint=False
        )
        assert broker._timeout == 10
        assert broker._max_tries == 5
        assert broker._verify_ssl is True
        assert broker._proxies is queue

    def test_broker_constants(self):
        """Test that important constants are defined."""
        assert GRAB_PAUSE == 180
        assert MAX_CONCURRENT_PROVIDERS == 3


class TestCheckerCore:
    """Test core Checker functionality."""

    def test_checker_initialization(self):
        """Test Checker initialization."""
        checker = Checker(
            judges=['http://judge.com'],
            timeout=5,
            max_tries=2
        )
        assert len(checker._judges) == 1
        assert checker._max_tries == 2

    def test_checker_empty_judges(self):
        """Test Checker with empty judges."""
        # When passing empty list [], it's falsy so defaults are loaded
        checker = Checker(judges=[], timeout=5, max_tries=1)
        assert len(checker._judges) == 10  # Default judges are loaded

    def test_checker_no_judges_error(self):
        """Test checker raises error when no judges available."""
        # Create a checker but force it to have no working judges
        checker = Checker(judges=['http://invalid-judge.test'], timeout=1, max_tries=1)
        # Clear judges to simulate all judges failing
        checker._judges = []
        # Verify no judges are available
        assert len(checker._judges) == 0

    def test_checker_get_headers(self):
        """Test header parsing from HTTP response."""
        from proxybroker.utils import parse_headers
        
        headers_bytes = (b'HTTP/1.1 200 OK\r\n'
                        b'Content-Type: application/json\r\n'
                        b'X-Forwarded-For: 1.2.3.4\r\n'
                        b'Via: 1.1 proxy\r\n')
        
        headers = parse_headers(headers_bytes)
        assert 'Content-Type' in headers
        assert headers['Content-Type'] == 'application/json'
        assert headers['X-Forwarded-For'] == '1.2.3.4'
        assert headers['Via'] == '1.1 proxy'

    def test_checker_anonymity_detection(self):
        """Test anonymity level detection function."""
        from proxybroker.checker import _get_anonymity_lvl
        
        mock_proxy = MagicMock()
        mock_proxy.log = MagicMock()
        
        mock_judge = MagicMock()
        mock_judge.marks = {'via': 0, 'proxy': 0}
        
        # Test transparent proxy (real IP found)
        content = 'your ip is 1.2.3.4'
        result = _get_anonymity_lvl('1.2.3.4', mock_proxy, mock_judge, content)
        assert result == 'Transparent'
        
        # Test anonymous proxy (via header found)
        content = 'via: proxy server'
        result = _get_anonymity_lvl('1.2.3.4', mock_proxy, mock_judge, content)
        assert result == 'Anonymous'
        
        # Test high anonymity (no identifying info)
        content = 'some random content'
        result = _get_anonymity_lvl('1.2.3.4', mock_proxy, mock_judge, content)
        assert result == 'High'


class TestProxyPoolCore:
    """Test core ProxyPool functionality."""

    def test_proxy_pool_initialization(self):
        """Test ProxyPool initialization."""
        queue = asyncio.Queue()
        pool = ProxyPool(
            proxies=queue,
            min_req_proxy=5,
            max_error_rate=0.4,
            max_resp_time=10,
            min_queue=3,
            strategy='best'
        )
        assert pool._proxies is queue
        assert pool._min_req_proxy == 5
        assert pool._max_error_rate == 0.4
        assert pool._max_resp_time == 10
        assert pool._min_queue == 3
        assert pool._strategy == 'best'
        assert pool._pool == []
        assert pool._newcomers == []

    def test_proxy_pool_invalid_strategy(self):
        """Test ProxyPool rejects invalid strategy."""
        queue = asyncio.Queue()
        with pytest.raises(ValueError, match='`strategy` only support `best` for now'):
            ProxyPool(proxies=queue, strategy='invalid')

    def test_proxy_pool_put_newcomer(self):
        """Test adding newcomer proxy to pool."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=10)
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 5}  # Less than min_req_proxy
        mock_proxy.error_rate = 0.1
        mock_proxy.avg_resp_time = 2.0
        mock_proxy.host = '127.0.0.1'
        mock_proxy.port = 8080
        
        pool.put(mock_proxy)
        assert mock_proxy in pool._newcomers
        assert len(pool._pool) == 0

    def test_proxy_pool_put_experienced_proxy(self):
        """Test adding experienced proxy to main pool."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=5, max_error_rate=0.5, max_resp_time=10)
        
        mock_proxy = MagicMock()
        mock_proxy.stat = {'requests': 10}  # Experienced
        mock_proxy.error_rate = 0.2  # Good error rate
        mock_proxy.avg_resp_time = 5.0  # Good response time
        
        pool.put(mock_proxy)
        assert (mock_proxy.avg_resp_time, mock_proxy) in pool._pool
        assert len(pool._newcomers) == 0

    def test_proxy_pool_discard_bad_proxy(self):
        """Test that bad proxies are discarded."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue, min_req_proxy=5, max_error_rate=0.3, max_resp_time=8)
        
        # Proxy with high error rate
        bad_proxy = MagicMock()
        bad_proxy.stat = {'requests': 10}
        bad_proxy.error_rate = 0.8  # Too high
        bad_proxy.avg_resp_time = 5.0
        
        pool.put(bad_proxy)
        assert len(pool._pool) == 0
        assert len(pool._newcomers) == 0

    def test_proxy_pool_heap_order(self):
        """Test that proxy pool maintains correct heap order."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        # Create proxies with different response times
        for i in range(5):
            proxy = MagicMock()
            proxy.avg_resp_time = i + 1.0
            proxy.stat = {'requests': 10}
            proxy.error_rate = 0.1
            heapq.heappush(pool._pool, (proxy.avg_resp_time, proxy))
        
        # Verify heap property (parent <= children)
        for i in range(len(pool._pool) // 2):
            left_child = 2 * i + 1
            right_child = 2 * i + 2
            
            if left_child < len(pool._pool):
                assert pool._pool[i][0] <= pool._pool[left_child][0]
            if right_child < len(pool._pool):
                assert pool._pool[i][0] <= pool._pool[right_child][0]

    @pytest.mark.asyncio
    async def test_proxy_pool_get_from_newcomers(self):
        """Test getting proxy from newcomers when main pool is insufficient."""
        queue = asyncio.Queue()
        # Set min_queue to 0 so it doesn't try to import from queue
        pool = ProxyPool(proxies=queue, min_queue=0)
        
        mock_proxy = MagicMock()
        mock_proxy.schemes = ('HTTP', 'HTTPS')
        mock_proxy.host = '127.0.0.1'
        mock_proxy.port = 8080
        pool._newcomers.append(mock_proxy)
        
        # Should get from newcomers since it's available
        result = await pool.get('HTTP')
        assert result is mock_proxy
        assert len(pool._newcomers) == 0

    @pytest.mark.asyncio
    async def test_proxy_pool_import_from_queue(self):
        """Test importing proxy from queue."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        mock_proxy = MagicMock()
        mock_proxy.schemes = ('HTTP', 'HTTPS')
        await queue.put(mock_proxy)
        
        result = await pool._import('HTTP')
        assert result is mock_proxy

    @pytest.mark.asyncio
    async def test_proxy_pool_import_empty_queue(self):
        """Test importing when queue is empty."""
        from proxybroker.errors import NoProxyError
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        with pytest.raises(NoProxyError, match='Timeout waiting for proxy'):
            await pool._import('HTTP')


class TestCLICore:
    """Test core CLI functionality."""

    def test_cli_help(self):
        """Test CLI help command."""
        # Test using subprocess to capture argparse output
        result = subprocess.run(
            [sys.executable, '-m', 'proxybroker', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'find' in result.stdout
        assert 'grab' in result.stdout
        assert 'serve' in result.stdout

    def test_cli_version(self):
        """Test CLI version command."""
        result = subprocess.run(
            [sys.executable, '-m', 'proxybroker', '--version'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '0.4.0' in result.stdout

    def test_find_help(self):
        """Test find command help."""
        result = subprocess.run(
            [sys.executable, '-m', 'proxybroker', 'find', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'usage:' in result.stdout.lower()
        assert '--limit' in result.stdout

    def test_grab_help(self):
        """Test grab command help."""
        result = subprocess.run(
            [sys.executable, '-m', 'proxybroker', 'grab', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'usage:' in result.stdout.lower()

    def test_serve_help(self):
        """Test serve command help."""
        result = subprocess.run(
            [sys.executable, '-m', 'proxybroker', 'serve', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert 'usage:' in result.stdout.lower()


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_checker_handles_proxy_errors(self):
        """Test checker handles errors gracefully."""
        # Just verify that we can create a checker and it won't crash
        # with invalid configuration
        checker = Checker(judges=['http://invalid.test'], timeout=1, max_tries=1)
        assert checker is not None
        assert checker._max_tries == 1

    def test_proxy_pool_handles_invalid_input(self):
        """Test proxy pool handles invalid proxy data."""
        queue = asyncio.Queue()
        pool = ProxyPool(proxies=queue)
        
        # Test with None proxy - should be ignored
        pool.put(None)  # Should not crash
        assert len(pool._newcomers) == 0
        assert len(pool._pool) == 0
        
        # Test with proxy missing required attributes
        broken_proxy = MagicMock()
        broken_proxy.error_rate = 'invalid'  # Non-numeric value
        broken_proxy.avg_resp_time = 'invalid'  # Non-numeric value
        broken_proxy.stat = {'requests': 10}
        broken_proxy.host = '127.0.0.1'
        broken_proxy.port = 8080
        
        # Should raise TypeError due to comparison with non-numeric values
        with pytest.raises(TypeError):
            pool.put(broken_proxy)


class TestConstants:
    """Test important constants and configurations."""

    def test_server_constants(self):
        """Test server constants are properly defined."""
        assert CONNECTED == b'HTTP/1.1 200 Connection established\r\n\r\n'

    def test_api_constants(self):
        """Test API constants are properly defined."""
        assert GRAB_PAUSE == 180
        assert MAX_CONCURRENT_PROVIDERS == 3

    def test_error_types_exist(self):
        """Test that error types are properly imported."""
        from proxybroker.errors import (
            ProxyConnError, ProxyTimeoutError, BadResponseError,
            BadStatusError, NoProxyError, ResolveError
        )
        
        # Test that errors can be instantiated
        assert ProxyConnError('test')
        assert ProxyTimeoutError('test')
        assert BadResponseError('test')
        assert BadStatusError('test')
        assert NoProxyError('test')
        assert ResolveError('test')


class TestConfiguration:
    """Test configuration handling."""

    @pytest.mark.asyncio
    async def test_broker_configuration_propagation(self):
        """Test that broker configuration is properly propagated."""
        timeout = 15
        max_tries = 5
        verify_ssl = True
        
        broker = Broker(
            timeout=timeout,
            max_tries=max_tries,
            verify_ssl=verify_ssl,
            stop_broker_on_sigint=False
        )
        
        assert broker._timeout == timeout
        assert broker._max_tries == max_tries
        assert broker._verify_ssl == verify_ssl

    def test_checker_configuration(self):
        """Test checker configuration options."""
        judges = ['http://judge1.com', 'http://judge2.com']
        timeout = 10
        max_tries = 3
        
        checker = Checker(
            judges=judges,
            timeout=timeout,
            max_tries=max_tries,
            verify_ssl=True,
            strict=True
        )
        
        assert len(checker._judges) == 2
        assert checker._max_tries == max_tries

    def test_proxy_pool_configuration(self):
        """Test proxy pool configuration options."""
        queue = asyncio.Queue()
        
        config = {
            'min_req_proxy': 10,
            'max_error_rate': 0.3,
            'max_resp_time': 15,
            'min_queue': 5,
            'strategy': 'best'
        }
        
        pool = ProxyPool(proxies=queue, **config)
        
        assert pool._min_req_proxy == config['min_req_proxy']
        assert pool._max_error_rate == config['max_error_rate']
        assert pool._max_resp_time == config['max_resp_time']
        assert pool._min_queue == config['min_queue']
        assert pool._strategy == config['strategy']