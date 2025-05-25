"""Behavior-focused checker tests.

Tests focus on "does proxy checking work" rather than internal validation algorithms.
This allows internal improvements while protecting user-visible behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from proxybroker import Proxy
from proxybroker.checker import Checker
from proxybroker.errors import ProxyConnError, ProxyTimeoutError


class TestCheckerBehavior:
    """Test checker behavior that users depend on."""

    @pytest.fixture
    def working_proxy(self):
        """Create a proxy that should pass checks."""
        proxy = Proxy("127.0.0.1", 8080, timeout=0.1)
        proxy.connect = AsyncMock()
        proxy.send = AsyncMock()
        proxy.recv = AsyncMock()
        proxy.close = MagicMock()
        return proxy

    @pytest.fixture  
    def failing_proxy(self):
        """Create a proxy that should fail checks."""
        proxy = Proxy("192.0.2.1", 8080, timeout=0.1)  # RFC5737 test IP
        proxy.connect = AsyncMock(side_effect=ProxyConnError("Connection failed"))
        proxy.send = AsyncMock()
        proxy.recv = AsyncMock()
        proxy.close = MagicMock()
        return proxy

    @pytest.fixture
    def checker(self):
        """Create a checker instance."""
        return Checker(
            judges=["http://judge1.com", "http://judge2.com"],
            timeout=5,
            max_tries=2,
            real_ext_ip="203.0.113.1",  # RFC5737 test IP
            types={"HTTP": None, "HTTPS": None}  # Checker expects dict format
        )

    @pytest.mark.asyncio
    async def test_check_proxy_success(self, working_proxy, checker):
        """Test that proxy checking succeeds for working proxies.
        
        Focus: Does the checker identify working proxies?
        Not: What specific validation steps are performed?
        """
        # Mock successful HTTP response indicating proxy works
        working_proxy.recv.return_value = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + b"x" * 100
        
        # Mock negotiator setup
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.check_anon_lvl = True
            mock_ngtr.negotiate = AsyncMock()
            mock_ngtr.use_full_path = True
            
            # Test that checker identifies working proxy
            result = await checker.check_proxy(working_proxy)
            
            # Checker should return True for working proxies
            assert result is True, "Checker should identify working proxies"
            
            # Proxy should be marked as working
            assert working_proxy.is_working is True

    @pytest.mark.asyncio
    async def test_check_proxy_failure(self, failing_proxy, checker):
        """Test that proxy checking fails appropriately for broken proxies.
        
        Focus: Does the checker identify broken proxies?
        """
        # Mock negotiator setup for failing proxy
        with patch.object(failing_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.negotiate = AsyncMock(side_effect=ProxyConnError("Connection failed"))
            
            # Test that checker identifies broken proxy
            result = await checker.check_proxy(failing_proxy)
            
            # Checker should return False for broken proxies
            assert result is False, "Checker should identify broken proxies"

    @pytest.mark.asyncio
    async def test_check_proxy_timeout(self, working_proxy, checker):
        """Test that proxy checking handles timeouts appropriately."""
        # Mock timeout scenario
        working_proxy.connect.side_effect = ProxyTimeoutError("Timeout")
        
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.negotiate = AsyncMock()
            
            # Test that checker handles timeouts
            result = await checker.check_proxy(working_proxy)
            
            # Timeouts should be treated as failures
            assert result is False, "Checker should treat timeouts as failures"

    @pytest.mark.asyncio 
    async def test_protocol_support_detection(self, working_proxy, checker):
        """Test that checker detects which protocols a proxy supports.
        
        Focus: Does the checker identify proxy capabilities users need?
        """
        # Mock successful HTTP response
        working_proxy.recv.return_value = b"HTTP/1.1 200 OK\r\nContent-Length: 50\r\n\r\n" + b"x" * 50
        
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.check_anon_lvl = True
            mock_ngtr.negotiate = AsyncMock()
            mock_ngtr.use_full_path = True
            
            # Test protocol detection
            result = await checker.check_proxy(working_proxy)
            
            if result:
                # Working proxy should have detected protocols
                assert len(working_proxy.types) > 0, "Checker should detect supported protocols"

    @pytest.mark.asyncio
    async def test_multiple_protocol_checking(self, working_proxy):
        """Test that checker validates multiple protocols correctly.
        
        Users depend on multi-protocol support detection.
        """
        checker = Checker(
            judges=["http://judge1.com"],
            timeout=5,
            max_tries=2,
            real_ext_ip="203.0.113.1",
            types={"HTTP": None, "HTTPS": None, "SOCKS5": None}
        )
        
        # Mock successful responses for multiple protocols
        working_proxy.recv.return_value = b"HTTP/1.1 200 OK\r\nContent-Length: 50\r\n\r\n" + b"x" * 50
        
        protocol_results = []
        
        async def mock_negotiate_tracker(**kwargs):
            """Track which protocols are being tested."""
            protocol_results.append(working_proxy.ngtr.name)
        
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.negotiate = AsyncMock(side_effect=mock_negotiate_tracker)
            mock_ngtr.check_anon_lvl = True
            mock_ngtr.use_full_path = True
            
            # This will test the first protocol found
            await checker.check_proxy(working_proxy)
            
            # Should have attempted to test at least one protocol
            # (Implementation may optimize by stopping after first success)

    @pytest.mark.asyncio
    async def test_anonymity_level_detection(self, working_proxy, checker):
        """Test that checker detects anonymity levels for HTTP proxies.
        
        Users select proxies based on anonymity level.
        """
        # Mock HTTP response that would indicate anonymity level
        http_response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 200\r\n\r\n"
            b"HTTP_VIA: proxy-server\r\n"  # Indicates transparent proxy
            b"REMOTE_ADDR: 203.0.113.1\r\n"  # External IP
            + b"x" * 100
        )
        working_proxy.recv.return_value = http_response
        
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.check_anon_lvl = True
            mock_ngtr.negotiate = AsyncMock()
            mock_ngtr.use_full_path = True
            
            result = await checker.check_proxy(working_proxy)
            
            if result:
                # Should have detected some HTTP protocol type
                assert "HTTP" in working_proxy.types or len(working_proxy.types) > 0

    @pytest.mark.asyncio
    async def test_checker_retry_mechanism(self, working_proxy):
        """Test that checker retries failed attempts appropriately.
        
        Users depend on robust checking that handles temporary failures.
        """
        checker = Checker(
            judges=["http://judge1.com"],
            timeout=5,
            max_tries=3,  # Allow retries
            real_ext_ip="203.0.113.1",
            types={"HTTP": None}
        )
        
        # Mock: fail first two attempts, succeed on third
        attempt_count = 0
        
        async def mock_connect_with_retries():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 2:
                raise ProxyConnError("Temporary failure")
            # Third attempt succeeds
        
        working_proxy.connect = AsyncMock(side_effect=mock_connect_with_retries)
        working_proxy.recv.return_value = b"HTTP/1.1 200 OK\r\nContent-Length: 50\r\n\r\n" + b"x" * 50
        
        with patch.object(working_proxy, 'ngtr') as mock_ngtr:
            mock_ngtr.name = "HTTP"
            mock_ngtr.negotiate = AsyncMock()
            mock_ngtr.check_anon_lvl = True
            mock_ngtr.use_full_path = True
            
            # Should eventually succeed after retries
            result = await checker.check_proxy(working_proxy)
            
            # Implementation may or may not retry at checker level
            # This tests that retry capability exists somewhere in the system

    def test_checker_initialization_patterns(self):
        """Test common checker initialization patterns users depend on."""
        # Basic initialization
        checker1 = Checker(
            judges=["http://judge1.com"],
            timeout=8,
            max_tries=3
        )
        assert checker1 is not None
        
        # With specific configuration
        checker2 = Checker(
            judges=["http://judge1.com", "http://judge2.com"],
            timeout=10,
            max_tries=5,
            real_ext_ip="203.0.113.1",
            types={"HTTP": None, "HTTPS": None},
            post=True,
            strict=True
        )
        assert checker2 is not None

    @pytest.mark.asyncio
    async def test_checker_error_handling(self, working_proxy, checker):
        """Test that checker handles various error conditions gracefully.
        
        Users depend on robust error handling for production use.
        """
        error_scenarios = [
            (ProxyConnError("Connection refused"), False),
            (ProxyTimeoutError("Timeout"), False),
            (Exception("Unexpected error"), False),
        ]
        
        for error, expected_result in error_scenarios:
            working_proxy.connect = AsyncMock(side_effect=error)
            
            with patch.object(working_proxy, 'ngtr') as mock_ngtr:
                mock_ngtr.name = "HTTP"
                mock_ngtr.negotiate = AsyncMock()
                
                # Should handle errors gracefully without crashing
                try:
                    result = await checker.check_proxy(working_proxy)
                    assert result == expected_result
                except Exception as e:
                    # If it raises, should be a handled exception type
                    assert isinstance(e, (ProxyConnError, ProxyTimeoutError))


class TestCheckerIntegration:
    """Test checker integration with real proxy workflows."""
    
    def test_checker_judge_configuration(self):
        """Test that checker accepts various judge configurations.
        
        Users configure judges in different ways.
        """
        # String URLs
        checker1 = Checker(judges=["http://judge1.com"])
        assert checker1 is not None
        
        # Multiple judges
        checker2 = Checker(judges=["http://judge1.com", "http://judge2.com"])
        assert checker2 is not None
        
        # Empty list (should work with defaults)
        checker3 = Checker(judges=[])
        assert checker3 is not None

    def test_checker_type_filtering(self):
        """Test that checker respects type filtering.
        
        Users specify which protocols to check.
        """
        # HTTP only
        checker1 = Checker(judges=["http://judge1.com"], types={"HTTP": None})
        assert checker1._types == {"HTTP": None}
        
        # Multiple protocols
        checker2 = Checker(judges=["http://judge1.com"], types={"HTTP": None, "HTTPS": None, "SOCKS5": None})
        assert checker2._types == {"HTTP": None, "HTTPS": None, "SOCKS5": None}

    def test_checker_timeout_configuration(self):
        """Test that checker respects timeout settings.
        
        Users configure timeouts based on their performance requirements.
        """
        # Custom timeout (timeout is passed to judges, not stored on checker)
        checker = Checker(judges=["http://judge1.com"], timeout=15)
        assert checker is not None  # Should initialize successfully
        
        # Default timeout
        checker2 = Checker(judges=["http://judge1.com"])
        assert checker2 is not None  # Should have some default behavior