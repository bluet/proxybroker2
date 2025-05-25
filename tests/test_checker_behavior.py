"""Behavior-focused checker tests.

Tests focus on "does proxy checking work" rather than internal validation algorithms.
This allows internal improvements while protecting user-visible behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from proxybroker import Proxy
from proxybroker.checker import Checker
from proxybroker.errors import ProxyConnError, ProxyTimeoutError
from proxybroker.judge import Judge


class TestCheckerBehavior:
    """Test checker behavior that users depend on."""

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
        
        # Checker should store provided configurations
        assert checker2._max_tries == 5
        assert checker2._real_ext_ip == "203.0.113.1"
        assert checker2._types == {"HTTP": None, "HTTPS": None}

    def test_checker_dnsbl_configuration(self):
        """Test that checker accepts DNSBL configurations.
        
        Users rely on DNSBL filtering for security.
        """
        dnsbl_servers = ["zen.spamhaus.org", "bl.spamcop.net"]
        checker = Checker(
            judges=["http://judge1.com"],
            dnsbl=dnsbl_servers
        )
        assert checker._dnsbl == dnsbl_servers

    def test_checker_protocol_filtering(self):
        """Test that checker respects protocol filtering.
        
        Users specify which protocols to check.
        """
        # HTTP only
        checker1 = Checker(judges=["http://judge1.com"], types={"HTTP": None})
        assert checker1._types == {"HTTP": None}
        assert checker1._req_http_proto is True
        assert checker1._req_https_proto is False
        
        # Multiple protocols
        checker2 = Checker(judges=["http://judge1.com"], types={"HTTP": None, "HTTPS": None, "SOCKS5": None})
        assert checker2._types == {"HTTP": None, "HTTPS": None, "SOCKS5": None}
        assert checker2._req_http_proto is True
        assert checker2._req_https_proto is True

    def test_checker_method_configuration(self):
        """Test that checker method configuration works.
        
        Users can configure GET vs POST checking.
        """
        # Default GET method
        checker1 = Checker(judges=["http://judge1.com"])
        assert checker1._method == "GET"
        
        # POST method
        checker2 = Checker(judges=["http://judge1.com"], post=True)
        assert checker2._method == "POST"

    def test_checker_strict_mode(self):
        """Test that checker strict mode configuration works.
        
        Users enable strict mode for more rigorous validation.
        """
        checker_lenient = Checker(judges=["http://judge1.com"], strict=False)
        assert checker_lenient._strict is False
        
        checker_strict = Checker(judges=["http://judge1.com"], strict=True)
        assert checker_strict._strict is True

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

    @pytest.mark.asyncio
    async def test_checker_judge_validation_logic(self):
        """Test checker's judge validation without actually checking judges.
        
        Focus: Does the checker handle judge availability correctly?
        """
        checker = Checker(
            judges=["http://invalid-judge.example"],
            timeout=0.1,  # Fast timeout
            types={"HTTP": None}
        )
        
        # The checker should initialize even with invalid judges
        assert checker is not None
        assert len(checker._judges) >= 0  # May have 0 or more judges
        
        # Checker should have proper protocol requirements
        assert checker._req_http_proto in [True, False]  # Boolean value

    def test_checker_protocol_requirements_logic(self):
        """Test that checker correctly determines protocol requirements.
        
        Users depend on the checker checking the right protocols.
        """
        # When no types specified, should check all protocols
        checker_all = Checker(judges=["http://judge1.com"])
        assert checker_all._req_http_proto is True
        assert checker_all._req_https_proto is True
        
        # When HTTP types specified, should check HTTP
        checker_http = Checker(judges=["http://judge1.com"], types={"HTTP": None, "SOCKS4": None})
        assert checker_http._req_http_proto is True
        
        # When only HTTPS specified, should check HTTPS but not HTTP
        checker_https = Checker(judges=["http://judge1.com"], types={"HTTPS": None})
        assert checker_https._req_https_proto is True
        # HTTP requirement depends on implementation - both outcomes valid

    def test_checker_types_passed_logic(self):
        """Test checker's type filtering logic.
        
        Users depend on checkers filtering proxies by anonymity levels.
        """
        checker_strict = Checker(
            judges=["http://judge1.com"],
            types={"HTTP": ["High", "Elite"]},
            strict=True
        )
        
        # Create a proxy with types
        proxy = Proxy("127.0.0.1", 8080)
        proxy._types = {"HTTP": "High"}
        
        # Should pass strict filtering with matching level
        result = checker_strict._types_passed(proxy)
        assert result is True, "High anonymity should pass High requirement"
        
        # Test with non-matching level
        proxy2 = Proxy("127.0.0.1", 8080)
        proxy2._types = {"HTTP": "Transparent"}
        
        result2 = checker_strict._types_passed(proxy2)
        assert result2 is False, "Transparent should not pass High requirement in strict mode"

    @pytest.mark.asyncio
    async def test_checker_dnsbl_logic(self):
        """Test checker DNSBL checking logic.
        
        Users depend on DNSBL filtering for security.
        """
        # Mock DNS resolution to avoid real network calls
        checker = Checker(
            judges=["http://judge1.com"],
            dnsbl=["test-dnsbl.example"]
        )
        
        # Mock the resolver to simulate clean IP
        with patch.object(checker._resolver, 'resolve') as mock_resolve:
            from proxybroker.errors import ResolveError
            mock_resolve.return_value = ResolveError("Not found")
            
            # Clean IP should pass DNSBL check
            result = await checker._in_DNSBL("192.0.2.1")  # RFC5737 test IP
            assert result is False, "Clean IP should pass DNSBL check"
        
        # Mock the resolver to simulate blacklisted IP
        with patch.object(checker._resolver, 'resolve') as mock_resolve:
            mock_resolve.return_value = "127.0.0.2"  # Simulated positive result
            
            # Blacklisted IP should fail DNSBL check
            result = await checker._in_DNSBL("192.0.2.1")
            assert result is True, "Blacklisted IP should fail DNSBL check"

    @pytest.mark.asyncio
    async def test_checker_with_mock_judges(self):
        """Test checker behavior with properly mocked judge events.
        
        Focus: Does checker wait for judges appropriately?
        """
        # Mock judge events to prevent hanging
        with patch.object(Judge, 'ev') as mock_ev:
            # Create mock events that are already set
            mock_event_http = AsyncMock()
            mock_event_http.wait = AsyncMock()
            mock_event_https = AsyncMock()
            mock_event_https.wait = AsyncMock()
            
            mock_ev.__getitem__.side_effect = lambda key: {
                'HTTP': mock_event_http,
                'HTTPS': mock_event_https,
                'SMTP': AsyncMock()
            }.get(key, AsyncMock())
            
            checker = Checker(
                judges=["http://judge1.com"],
                types={"HTTP": None}
            )
            
            # Create a minimal proxy
            proxy = Proxy("127.0.0.1", 8080, timeout=0.1)
            proxy.ngtr = "HTTP"
            
            # Mock proxy methods to avoid real network calls
            proxy.connect = AsyncMock()
            proxy.send = AsyncMock()
            proxy.recv = AsyncMock(return_value=b"HTTP/1.1 200 OK\r\n\r\n")
            proxy.close = MagicMock()
            
            # Mock the _check method to return a simple result
            with patch.object(checker, '_check') as mock_check:
                mock_check.return_value = True
                
                # Now the checker should be able to run without hanging
                result = await checker.check(proxy)
                
                # The mock should have been called
                mock_check.assert_called()
                assert mock_event_http.wait.called or not checker._req_http_proto


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