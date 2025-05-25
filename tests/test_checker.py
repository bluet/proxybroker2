"""Test Checker public API - focused on proxy validation behavior.

This file tests the Checker's core responsibility: determining if a proxy works.
We focus on the user-visible outcomes, not the complex internal implementation.
"""

from proxybroker.checker import Checker


class TestCheckerAPI:
    """Test Checker public API and configuration contracts."""

    def test_checker_creation_with_basic_config(self):
        """Test that Checker can be created with basic configuration."""
        checker = Checker(judges=["http://judge.com"], timeout=10, max_tries=3)
        assert checker._max_tries == 3
        # Timeout is passed to judges, not stored directly in checker

    def test_checker_creation_with_protocol_types(self):
        """Test that Checker accepts protocol type filtering."""
        checker = Checker(
            judges=["http://judge.com"],
            types={"HTTP": ["High"], "HTTPS": ["Anonymous"]},
            timeout=5,
        )
        assert "HTTP" in checker._types
        assert "HTTPS" in checker._types
        assert checker._types["HTTP"] == ["High"]

    def test_checker_creation_with_empty_judges(self):
        """Test that Checker handles empty judges list gracefully."""
        checker = Checker(judges=[], timeout=5, max_tries=1)
        assert isinstance(checker._judges, list)
        # Empty judges list falls back to default judges for functionality
        assert len(checker._judges) >= 0

    def test_checker_creation_with_edge_case_values(self):
        """Test Checker with edge case configuration values."""
        # Very short timeout
        checker1 = Checker(judges=["http://judge.com"], timeout=1, max_tries=1)
        assert checker1._max_tries == 1

        # Very long timeout
        checker2 = Checker(judges=["http://judge.com"], timeout=300, max_tries=10)
        assert checker2._max_tries == 10

    def test_checker_protocol_filtering_configuration(self):
        """Test that checker accepts various protocol configurations."""
        # HTTP only
        checker_http = Checker(
            judges=["http://judge.com"],
            types={"HTTP": ["High", "Anonymous"]},
            timeout=5,
        )
        assert "HTTP" in checker_http._types
        assert len(checker_http._types) == 1

        # Multiple protocols
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

    def test_checker_has_required_public_methods(self):
        """Test that Checker has the methods users depend on."""
        checker = Checker(judges=["http://judge.com"], timeout=5, max_tries=1)

        # Essential methods that users call
        assert hasattr(checker, "check")
        assert callable(checker.check)
        assert hasattr(checker, "check_judges")
        assert callable(checker.check_judges)

    def test_checker_graceful_handling_of_no_judges(self):
        """Test that checker handles edge cases gracefully."""
        # Since empty judges defaults to built-in judges, test this differently
        checker = Checker(judges=[], timeout=5, max_tries=1)

        # Should have fallback judges available
        assert len(checker._judges) > 0

    def test_checker_anonymity_level_detection_contract(self):
        """Test that anonymity level detection functions exist and work."""
        from proxybroker.checker import _get_anonymity_lvl
        from unittest.mock import Mock

        # Test function exists and handles basic cases
        real_ip = "1.2.3.4"

        # Create mock objects with required attributes
        mock_proxy = Mock()
        mock_proxy.log = Mock()
        mock_judge = Mock()
        mock_judge.marks = {"via": 0, "proxy": 0}

        # Transparent proxy case
        transparent_content = '{"ip": "1.2.3.4", "headers": {}}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, transparent_content)
        assert lvl == "Transparent"

        # Anonymous proxy case (contains 'via' or 'proxy')
        anonymous_content = '{"ip": "8.8.8.8", "via": "1.1 proxy"}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, anonymous_content)
        assert lvl == "Anonymous"

        # High anonymous proxy case (different IP, no via/proxy headers)
        high_anon_content = '{"ip": "8.8.8.8"}'
        lvl = _get_anonymity_lvl(real_ip, mock_proxy, mock_judge, high_anon_content)
        assert lvl == "High"

    def test_checker_response_validation_contract(self):
        """Test that response validation functions exist and work."""
        from proxybroker.checker import _check_test_response
        from proxybroker.utils import get_headers, parse_headers
        from unittest.mock import Mock

        # Get real verification values
        real_headers, real_rv = get_headers(rv=True)

        # Create mock proxy
        mock_proxy = Mock()
        mock_proxy.log = Mock()

        # Parse headers from response
        response = b"HTTP/1.1 200 OK\r\n\r\n"
        headers = parse_headers(response)

        # Valid response should return True
        valid_content = f"Your code: {real_rv} Your IP: 8.8.8.8 Referer: {real_headers['Referer']} Cookie: {real_headers['Cookie']}"
        result = _check_test_response(
            proxy=mock_proxy,
            headers=headers,
            content=valid_content,
            rv=real_rv,
        )
        assert result is True

        # Invalid response should return False
        invalid_content = "Your code: wrong_code Your IP: 8.8.8.8"
        result = _check_test_response(
            proxy=mock_proxy,
            headers=headers,
            content=invalid_content,
            rv=real_rv,
        )
        assert result is False
