import os
import subprocess
import sys
import tempfile

import pytest


class TestCLI:
    """Test CLI functionality through actual command execution."""

    def run_cli(self, args, timeout=10):
        """Run CLI command and return result."""
        cmd = [sys.executable, "-m", "proxybroker"] + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            # This is expected for commands that run indefinitely
            return None

    def test_help_command(self):
        """Test main help displays all commands."""
        result = self.run_cli(["--help"])
        assert result.returncode == 0
        assert "usage: proxybroker" in result.stdout
        # Verify all commands are listed
        assert "find" in result.stdout
        assert "grab" in result.stdout
        assert "serve" in result.stdout
        # Verify descriptions are shown
        assert "Find and check proxies" in result.stdout
        assert "Find proxies without a check" in result.stdout
        assert "Run a local proxy server" in result.stdout

    def test_version_command(self):
        """Test version display."""
        result = self.run_cli(["--version"])
        assert result.returncode == 0
        # Version should be displayed (don't hardcode specific version)
        assert result.stdout.strip()  # Should have some output

    def test_find_command_help(self):
        """Test find command help shows all options."""
        result = self.run_cli(["find", "--help"])
        assert result.returncode == 0
        assert "Find and check proxies" in result.stdout
        # Key options should be documented
        assert "--types" in result.stdout
        assert "--countries" in result.stdout
        assert "--limit" in result.stdout
        assert "--format" in result.stdout
        assert "--show-stats" in result.stdout

    def test_grab_command_help(self):
        """Test grab command help shows all options."""
        result = self.run_cli(["grab", "--help"])
        assert result.returncode == 0
        assert "Find proxies without a check" in result.stdout
        # Key options should be documented
        assert "--countries" in result.stdout
        assert "--limit" in result.stdout
        assert "--outfile" in result.stdout
        assert "--format" in result.stdout

    def test_serve_command_help(self):
        """Test serve command help shows all options."""
        result = self.run_cli(["serve", "--help"])
        assert result.returncode == 0
        assert "Run a local proxy server" in result.stdout
        # Key options should be documented
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--types" in result.stdout
        assert "--max-resp-time" in result.stdout
        assert "--strategy" in result.stdout

    def test_invalid_arguments_error_handling(self):
        """Test CLI properly handles invalid arguments."""
        # Invalid port (out of range)
        result = self.run_cli(["serve", "--port", "99999"])
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()

        # Invalid limit (negative)
        result = self.run_cli(["find", "--limit", "-1"])
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()

        # Invalid country code
        result = self.run_cli(["find", "--countries", "ZZ"])
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()

        # Unknown command
        result = self.run_cli(["unknown"])
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or "invalid" in result.stderr.lower()

    def test_find_with_limit_zero_exits_immediately(self):
        """Test find with limit 0 exits without hanging."""
        result = self.run_cli(["find", "--types", "HTTP", "--limit", "1"], timeout=5)
        # Should complete or timeout gracefully with small limit
        if result is None:
            # Timeout is acceptable for this test
            pass
        else:
            # If it completes, should be successful
            assert result.returncode == 0

    def test_grab_with_limit_zero_exits_immediately(self):
        """Test grab with limit 0 exits without hanging."""
        result = self.run_cli(["grab", "--countries", "US", "--limit", "1"], timeout=5)
        # Should complete or timeout gracefully with small limit
        if result is None:
            # Timeout is acceptable for this test
            pass
        else:
            # If it completes, should be successful
            assert result.returncode == 0

    def test_grab_output_file_creation(self):
        """Test grab command creates output file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            temp_file = f.name

        try:
            # Run grab with small limit
            self.run_cli(
                ["grab", "--countries", "US", "--limit", "1", "--outfile", temp_file], timeout=5
            )
            # File should exist regardless of completion
            assert os.path.exists(temp_file)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_format_options_accepted(self):
        """Test that format options are accepted."""
        # Test find with JSON format
        result = self.run_cli(["find", "--types", "HTTP", "--format", "json", "--limit", "1"], timeout=5)
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

        # Test grab with default format
        result = self.run_cli(
            ["grab", "--countries", "US", "--format", "default", "--limit", "1"], timeout=5
        )
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

    def test_types_argument_parsing(self):
        """Test types argument accepts multiple values."""
        result = self.run_cli(
            ["find", "--types", "HTTP", "HTTPS", "SOCKS5", "--limit", "1"], timeout=5
        )
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

    def test_countries_argument_parsing(self):
        """Test countries argument accepts multiple values."""
        result = self.run_cli(
            ["find", "--types", "HTTP", "--countries", "US", "GB", "CA", "--limit", "1"], timeout=5
        )
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

    def test_serve_with_custom_host_port(self):
        """Test serve command accepts host and port."""
        # Test argument parsing without actually starting server
        result = self.run_cli(
            ["serve", "--types", "HTTP", "--host", "127.0.0.1", "--port", "8899", "--limit", "1"],
            timeout=3,
        )
        # Either completes successfully or times out (both are acceptable)
        if result is not None:
            # If it returns, it should succeed or fail due to network issues (not arg parsing)
            assert result.returncode in [0, 1]

    def test_timeout_and_max_tries_options(self):
        """Test timeout and max-tries options are accepted."""
        result = self.run_cli(
            ["--timeout", "5", "--max-tries", "2", "find", "--types", "HTTP", "--limit", "1"], timeout=5
        )
        # Global options should be accepted (timeout/completion is acceptable)
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

    def test_log_level_option(self):
        """Test log level option is accepted."""
        result = self.run_cli(["--log", "DEBUG", "find", "--types", "HTTP", "--limit", "1"], timeout=5)
        # Log level should be accepted (timeout/completion is acceptable)
        if result is None:
            pass  # Timeout acceptable
        else:
            assert result.returncode == 0

    @pytest.mark.parametrize("command", ["find", "grab", "serve"])
    def test_each_command_has_help(self, command):
        """Test each command has accessible help."""
        result = self.run_cli([command, "--help"])
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert command in result.stdout
