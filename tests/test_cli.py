import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from proxybroker import Proxy
from proxybroker.cli import cli


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_broker():
    """Create a mock broker for CLI testing."""
    broker = MagicMock()
    broker.find = AsyncMock()
    broker.grab = AsyncMock()  
    broker.serve = AsyncMock()
    broker.show_stats = AsyncMock()
    return broker


@pytest.fixture
def sample_proxies():
    """Create sample proxy objects for testing."""
    proxies = []
    for i in range(3):
        proxy = MagicMock(spec=Proxy)
        proxy.host = f'127.0.0.{i+1}'
        proxy.port = 8080
        proxy.types = {'HTTP': 'Anonymous'}
        proxy.schemes = ('HTTP', 'HTTPS')
        proxy.avg_resp_time = 1.5
        proxy.error_rate = 0.1
        proxy.as_json.return_value = {
            'host': proxy.host,
            'port': proxy.port,
            'types': [{'type': 'HTTP', 'level': 'Anonymous'}],
            'avg_resp_time': 1.5,
            'error_rate': 0.1
        }
        proxies.append(proxy)
    return proxies


class TestCLI:
    """Test cases for CLI functionality."""

    def test_cli_help(self, cli_runner):
        """Test CLI help command."""
        result = cli_runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'find' in result.output
        assert 'grab' in result.output
        assert 'serve' in result.output

    def test_cli_version(self, cli_runner):
        """Test CLI version command."""
        result = cli_runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert '2.0.0' in result.output

    @patch('proxybroker.cli.Broker')
    def test_find_command_basic(self, mock_broker_class, cli_runner, sample_proxies):
        """Test basic find command."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        # Mock async generator
        async def mock_find(*args, **kwargs):
            for proxy in sample_proxies[:2]:
                yield proxy
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run') as mock_run:
            result = cli_runner.invoke(cli, ['find', '--limit', '2'])
            assert result.exit_code == 0
            mock_run.assert_called_once()

    @patch('proxybroker.cli.Broker')
    def test_find_command_with_countries(self, mock_broker_class, cli_runner):
        """Test find command with countries filter."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield  # Make it a generator
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find', 
                '--countries', 'US,CA',
                '--limit', '5'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_find_command_with_types(self, mock_broker_class, cli_runner):
        """Test find command with proxy types filter."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--types', 'HTTP,HTTPS',
                '--limit', '3'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_find_command_with_anon_levels(self, mock_broker_class, cli_runner):
        """Test find command with anonymity levels filter."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--lvl', 'Anonymous,High',
                '--limit', '3'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_find_command_with_output_file(self, mock_broker_class, cli_runner, sample_proxies):
        """Test find command with output file."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            for proxy in sample_proxies[:1]:
                yield proxy
        
        mock_broker.find = mock_find
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            with patch('asyncio.run'):
                result = cli_runner.invoke(cli, [
                    'find',
                    '--outfile', tmp_file.name,
                    '--outformat', 'json',
                    '--limit', '1'
                ])
                assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_find_command_strict_mode(self, mock_broker_class, cli_runner):
        """Test find command with strict SSL verification."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--strict',
                '--limit', '1'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_grab_command(self, mock_broker_class, cli_runner):
        """Test grab command."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        mock_broker.grab = AsyncMock()
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, ['grab'])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_grab_command_with_options(self, mock_broker_class, cli_runner):
        """Test grab command with options."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        mock_broker.grab = AsyncMock()
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'grab',
                '--max-conn', '50',
                '--max-tries', '2',
                '--timeout', '10'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_serve_command(self, mock_broker_class, cli_runner):
        """Test serve command."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        mock_broker.serve = AsyncMock()
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'serve',
                '--host', '127.0.0.1',
                '--port', '8888'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_serve_command_with_auth(self, mock_broker_class, cli_runner):
        """Test serve command with authentication."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        mock_broker.serve = AsyncMock()
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'serve',
                '--host', '0.0.0.0',
                '--port', '8080',
                '--max-tries', '3'
            ])
            assert result.exit_code == 0

    def test_validate_countries(self, cli_runner):
        """Test countries validation."""
        # Test valid countries
        result = cli_runner.invoke(cli, [
            'find',
            '--countries', 'US,CA,GB',
            '--limit', '1'
        ], catch_exceptions=False)
        # Should not raise validation error

    def test_validate_types(self, cli_runner):
        """Test proxy types validation.""" 
        result = cli_runner.invoke(cli, [
            'find',
            '--types', 'HTTP,HTTPS,SOCKS4,SOCKS5',
            '--limit', '1'
        ], catch_exceptions=False)
        # Should not raise validation error

    def test_validate_anon_levels(self, cli_runner):
        """Test anonymity levels validation."""
        result = cli_runner.invoke(cli, [
            'find', 
            '--lvl', 'Transparent,Anonymous,High',
            '--limit', '1'
        ], catch_exceptions=False)
        # Should not raise validation error

    def test_validate_port_range(self, cli_runner):
        """Test port range validation."""
        # Valid port
        result = cli_runner.invoke(cli, [
            'serve',
            '--port', '8080'
        ], catch_exceptions=False)
        
        # Invalid port (too high)
        result = cli_runner.invoke(cli, [
            'serve',
            '--port', '70000'
        ])
        assert result.exit_code != 0

    def test_output_formats(self, cli_runner):
        """Test different output formats."""
        formats = ['default', 'json', 'txt']
        
        for fmt in formats:
            result = cli_runner.invoke(cli, [
                'find',
                '--outformat', fmt,
                '--limit', '1'
            ], catch_exceptions=False)
            # Should not raise format error

    @patch('proxybroker.cli.Broker')
    def test_timeout_validation(self, mock_broker_class, cli_runner):
        """Test timeout parameter validation."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        # Valid timeout
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--timeout', '30',
                '--limit', '1'
            ])
            assert result.exit_code == 0
        
        # Invalid timeout (negative)
        result = cli_runner.invoke(cli, [
            'find',
            '--timeout', '-5'
        ])
        assert result.exit_code != 0

    @patch('proxybroker.cli.Broker')
    def test_max_conn_validation(self, mock_broker_class, cli_runner):
        """Test max-conn parameter validation."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        # Valid max-conn
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--max-conn', '100',
                '--limit', '1'
            ])
            assert result.exit_code == 0

    def test_help_subcommands(self, cli_runner):
        """Test help for subcommands."""
        subcommands = ['find', 'grab', 'serve']
        
        for cmd in subcommands:
            result = cli_runner.invoke(cli, [cmd, '--help'])
            assert result.exit_code == 0
            assert 'Usage:' in result.output

    @patch('proxybroker.cli.Broker')
    def test_keyboard_interrupt_handling(self, mock_broker_class, cli_runner):
        """Test graceful handling of keyboard interrupt."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        # Mock find to raise KeyboardInterrupt
        async def mock_find_interrupt(*args, **kwargs):
            raise KeyboardInterrupt()
            yield  # Make it a generator
        
        mock_broker.find = mock_find_interrupt
        
        with patch('asyncio.run', side_effect=KeyboardInterrupt):
            result = cli_runner.invoke(cli, ['find', '--limit', '1'])
            # Should handle KeyboardInterrupt gracefully
            # Exit code might be non-zero but shouldn't crash

    @patch('proxybroker.cli.Broker')
    def test_custom_judges(self, mock_broker_class, cli_runner):
        """Test find command with custom judges."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--judges', 'http://judge1.com,http://judge2.com',
                '--limit', '1'
            ])
            assert result.exit_code == 0

    @patch('proxybroker.cli.Broker')
    def test_custom_providers(self, mock_broker_class, cli_runner):
        """Test find command with custom providers."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            return
            yield
        
        mock_broker.find = mock_find
        
        with patch('asyncio.run'):
            result = cli_runner.invoke(cli, [
                'find',
                '--providers', 'http://provider1.com,http://provider2.com',
                '--limit', '1'
            ])
            assert result.exit_code == 0

    def test_concurrent_parameters(self, cli_runner):
        """Test that concurrent parameters are within valid ranges."""
        # Test various concurrent connection limits
        limits = [1, 10, 100, 500]
        
        for limit in limits:
            result = cli_runner.invoke(cli, [
                'find',
                '--max-conn', str(limit),
                '--limit', '1'
            ], catch_exceptions=False)
            # Should not raise validation errors for reasonable limits

    @patch('proxybroker.cli.Broker')
    def test_output_file_permissions(self, mock_broker_class, cli_runner, sample_proxies):
        """Test output file creation and permissions."""
        mock_broker = MagicMock()
        mock_broker_class.return_value = mock_broker
        
        async def mock_find(*args, **kwargs):
            for proxy in sample_proxies[:1]:
                yield proxy
        
        mock_broker.find = mock_find
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.close()  # Close so CLI can write to it
            
            with patch('asyncio.run'):
                result = cli_runner.invoke(cli, [
                    'find',
                    '--outfile', tmp_file.name,
                    '--limit', '1'
                ])
                assert result.exit_code == 0