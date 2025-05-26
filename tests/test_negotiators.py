"""Clean negotiator tests focused on behavior, not implementation.

These tests follow good testing principles:
- Test behavior, not implementation details
- Simple and readable
- Test user-visible outcomes
- Enable refactoring without breaking
"""

import pytest


class TestNegotiatorContracts:
    """Test the public contracts that users depend on."""

    def test_all_negotiators_exist(self):
        """Test that all expected negotiators are available to users."""
        from proxybroker.negotiators import NGTRS

        expected_protocols = [
            "SOCKS5",
            "SOCKS4",
            "CONNECT:80",
            "CONNECT:25",
            "HTTPS",
            "HTTP",
        ]

        for protocol in expected_protocols:
            assert protocol in NGTRS, f"Missing negotiator for {protocol}"
            negotiator_class = NGTRS[protocol]
            assert negotiator_class is not None
            assert hasattr(negotiator_class, "negotiate"), (
                f"{protocol} negotiator missing negotiate method"
            )

    def test_negotiators_have_required_attributes(self):
        """Test that negotiators have the attributes users depend on."""
        from proxybroker.negotiators import NGTRS

        for protocol, negotiator_class in NGTRS.items():
            # Test that each negotiator has the basic required attributes
            assert hasattr(negotiator_class, "name"), (
                f"{protocol} missing name attribute"
            )
            assert hasattr(negotiator_class, "check_anon_lvl"), (
                f"{protocol} missing check_anon_lvl"
            )
            assert hasattr(negotiator_class, "use_full_path"), (
                f"{protocol} missing use_full_path"
            )

    @pytest.mark.parametrize(
        "protocol,check_anon_lvl,use_full_path",
        [
            ("SOCKS5", False, False),
            ("SOCKS4", False, False),
            ("CONNECT:80", False, False),
            ("CONNECT:25", False, False),
            ("HTTPS", False, False),
            ("HTTP", True, True),
        ],
    )
    def test_negotiator_attributes(self, protocol, check_anon_lvl, use_full_path):
        """Test that negotiators have correct protocol-specific attributes."""
        from unittest.mock import MagicMock

        from proxybroker.negotiators import NGTRS

        # Create the appropriate negotiator instance
        negotiator_class = NGTRS[protocol]
        mock_proxy = MagicMock()
        negotiator = negotiator_class(mock_proxy)

        assert negotiator.name == protocol
        assert negotiator.check_anon_lvl is check_anon_lvl
        assert negotiator.use_full_path is use_full_path

    def test_negotiator_instantiation(self):
        """Test that all negotiators can be instantiated."""
        from unittest.mock import MagicMock

        from proxybroker.negotiators import NGTRS

        mock_proxy = MagicMock()

        for _, negotiator_class in NGTRS.items():
            # Should be able to create instance without errors
            negotiator = negotiator_class(mock_proxy)
            assert negotiator is not None
            assert hasattr(negotiator, "negotiate")
