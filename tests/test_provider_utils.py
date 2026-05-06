"""Tests for custom provider utilities."""

import json
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from proxybroker.provider_utils import (
    APIProvider,
    ConfigurableProvider,
    PaginatedProvider,
    SimpleProvider,
    create_provider_config_template,
    load_provider_configs_from_directory,
    load_providers_from_directory,
    load_python_providers_from_directory,
)


class TestSimpleProvider:
    """Test SimpleProvider functionality."""

    def test_text_format_detection(self):
        """Test that text format is detected correctly."""
        provider = SimpleProvider("http://example.com/proxies.txt")
        assert provider._detect_format("192.168.1.1:8080\n10.0.0.1:3128") == "text"

    def test_json_format_detection(self):
        """Test that JSON format is detected correctly."""
        provider = SimpleProvider("http://example.com/proxies.json")
        json_data = '[{"ip": "192.168.1.1", "port": 8080}]'
        assert provider._detect_format(json_data) == "json"

    def test_csv_format_detection(self):
        """Test that CSV format is detected correctly."""
        provider = SimpleProvider("http://example.com/proxies.csv")
        csv_data = "192.168.1.1,8080\n10.0.0.1,3128"
        assert provider._detect_format(csv_data) == "csv"

    def test_parse_text(self):
        """Test parsing text format proxies."""
        provider = SimpleProvider("http://example.com/proxies.txt", format="text")
        text_data = "192.168.1.1:8080\n10.0.0.1:3128\n172.16.0.1:8888"
        proxies = provider._parse_text(text_data)
        assert len(proxies) == 3
        assert ("192.168.1.1", "8080") in proxies

    def test_parse_json(self):
        """Test parsing JSON format proxies."""
        provider = SimpleProvider("http://example.com/proxies.json", format="json")
        json_data = '[{"ip": "192.168.1.1", "port": 8080}, {"host": "10.0.0.1", "port": "3128"}]'
        proxies = provider._parse_json(json_data)
        assert len(proxies) == 2
        assert ("192.168.1.1", "8080") in proxies
        assert ("10.0.0.1", "3128") in proxies

    def test_parse_csv(self):
        """Test parsing CSV format proxies."""
        provider = SimpleProvider("http://example.com/proxies.csv", format="csv")
        csv_data = '"192.168.1.1","8080"\n10.0.0.1,3128'
        proxies = provider._parse_csv(csv_data)
        assert len(proxies) == 2
        assert ("192.168.1.1", "8080") in proxies


class TestPaginatedProvider:
    """Test PaginatedProvider functionality."""

    @pytest.mark.asyncio
    async def test_url_formatting(self):
        """Test that paginated URLs are formatted correctly."""
        provider = PaginatedProvider(
            base_url="http://example.com/page-{}.html",
            start_page=1,
            max_pages=3,
        )
        # We'd need to mock the actual HTTP calls to test _pipe()
        # For now, just test the initialization
        assert provider.base_url == "http://example.com/page-{}.html"
        assert provider.start_page == 1
        assert provider.max_pages == 3


class TestAPIProvider:
    """Test APIProvider functionality."""

    def test_api_provider_init(self):
        """Test APIProvider initialization."""
        provider = APIProvider(
            api_url="http://api.example.com/proxies",
            api_key="test-key",
            response_format="json",
        )
        assert provider.url == "http://api.example.com/proxies"
        assert provider.api_key == "test-key"
        assert provider.response_format == "json"

    def test_extract_from_list(self):
        """Test extracting proxies from JSON list."""
        provider = APIProvider("http://api.example.com/proxies")
        items = [
            {"ip": "192.168.1.1", "port": 8080},
            {"host": "10.0.0.1", "proxy_port": "3128"},
            "172.16.0.1:8888",
        ]
        proxies = provider._extract_from_list(items)
        assert len(proxies) == 3
        assert ("192.168.1.1", "8080") in proxies
        assert ("10.0.0.1", "3128") in proxies
        assert ("172.16.0.1", "8888") in proxies


class TestConfigurableProvider:
    """Test ConfigurableProvider functionality."""

    def test_from_yaml_config(self):
        """Test creating provider from YAML config."""
        config = {
            "name": "Test Provider",
            "type": "simple",
            "url": "http://example.com/proxies.txt",
            "format": "text",
            "protocols": ["HTTP", "HTTPS"],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()

            provider = ConfigurableProvider.from_config(f.name)
            assert isinstance(provider, SimpleProvider)
            assert provider.url == "http://example.com/proxies.txt"
            assert provider.format == "text"

        Path(f.name).unlink()

    def test_from_json_config(self):
        """Test creating provider from JSON config."""
        config = {
            "name": "Test API",
            "type": "api",
            "url": "http://api.example.com/proxies",
            "api_key": "test-key",
            "response_format": "json",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            f.flush()

            provider = ConfigurableProvider.from_config(f.name)
            assert isinstance(provider, APIProvider)
            assert provider.url == "http://api.example.com/proxies"
            assert provider.api_key == "test-key"

        Path(f.name).unlink()


def test_create_provider_config_template():
    """Test creating provider configuration templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test YAML template
        yaml_path = Path(tmpdir) / "test.yaml"
        create_provider_config_template(yaml_path, "simple")
        assert yaml_path.exists()

        with open(yaml_path) as f:
            config = yaml.safe_load(f)
            assert config["type"] == "simple"
            assert "url" in config

        # Test JSON template
        json_path = Path(tmpdir) / "test.json"
        create_provider_config_template(json_path, "api")
        assert json_path.exists()

        with open(json_path) as f:
            config = json.load(f)
            assert config["type"] == "api"
            assert "url" in config


def _write_yaml_config(path):
    config = {
        "name": "Test Provider",
        "type": "simple",
        "url": "http://example.com/proxies.txt",
        "format": "text",
    }
    with open(path, "w") as f:
        yaml.dump(config, f)


def _write_python_provider_module(path):
    path.write_text(
        textwrap.dedent(
            """
            from proxybroker.provider_utils import SimpleProvider

            class _TouchSentinel:
                touched = False

            class TouchOnImportProvider(SimpleProvider):
                def __init__(self):
                    super().__init__(
                        url="http://example.com/touch.txt",
                        format="text",
                    )
                    _TouchSentinel.touched = True
            """
        ).lstrip()
    )


def test_load_providers_from_directory():
    """Default loader: YAML/JSON only, .py files are ignored.

    This is the safe-by-default contract relied on by Docker bind-mount
    use cases — dropping a .py file in the configs directory must not
    cause arbitrary Python execution.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_yaml_config(Path(tmpdir) / "test_provider.yaml")
        _write_python_provider_module(Path(tmpdir) / "evil.py")

        providers = load_providers_from_directory(tmpdir)

        assert len(providers) == 1
        assert isinstance(providers[0], SimpleProvider)

        # Non-existent directory still returns empty list, not an error.
        assert load_providers_from_directory("/non/existent/path") == []


def test_load_provider_configs_from_directory_ignores_python():
    """The config-only loader never touches .py files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_yaml_config(Path(tmpdir) / "ok.yaml")
        _write_python_provider_module(Path(tmpdir) / "evil.py")

        providers = load_provider_configs_from_directory(tmpdir)

        assert len(providers) == 1
        assert isinstance(providers[0], SimpleProvider)


def test_load_providers_from_directory_with_allow_python():
    """allow_python=True opts in to executing *.py files.

    This is the trusted-directory path; not used by the CLI default.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_yaml_config(Path(tmpdir) / "ok.yaml")
        _write_python_provider_module(Path(tmpdir) / "trusted.py")

        providers = load_providers_from_directory(tmpdir, allow_python=True)

        # One from YAML + one from the Python module.
        assert len(providers) == 2
        assert any(isinstance(p, SimpleProvider) for p in providers)


def test_load_python_providers_directly():
    """The explicit Python loader executes .py modules and discovers Provider subclasses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_python_provider_module(Path(tmpdir) / "trusted.py")

        providers = load_python_providers_from_directory(tmpdir)

        assert len(providers) == 1
        assert isinstance(providers[0], SimpleProvider)
