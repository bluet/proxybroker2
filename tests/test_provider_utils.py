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
        assert provider._detect_format("192.0.2.1:8080\n198.51.100.1:3128") == "text"

    def test_json_format_detection(self):
        """Test that JSON format is detected correctly."""
        provider = SimpleProvider("http://example.com/proxies.json")
        json_data = '[{"ip": "192.0.2.1", "port": 8080}]'
        assert provider._detect_format(json_data) == "json"

    def test_csv_format_detection(self):
        """Test that CSV format is detected correctly."""
        provider = SimpleProvider("http://example.com/proxies.csv")
        csv_data = "192.0.2.1,8080\n198.51.100.1,3128"
        assert provider._detect_format(csv_data) == "csv"

    def test_parse_text(self):
        """Test parsing text format proxies."""
        provider = SimpleProvider("http://example.com/proxies.txt", format="text")
        text_data = "192.0.2.1:8080\n198.51.100.1:3128\n203.0.113.1:8888"
        proxies = provider._parse_text(text_data)
        assert len(proxies) == 3
        assert ("192.0.2.1", "8080") in proxies

    def test_parse_json(self):
        """Test parsing JSON format proxies."""
        provider = SimpleProvider("http://example.com/proxies.json", format="json")
        json_data = '[{"ip": "192.0.2.1", "port": 8080}, {"host": "198.51.100.1", "port": "3128"}]'
        proxies = provider._parse_json(json_data)
        assert len(proxies) == 2
        assert ("192.0.2.1", "8080") in proxies
        assert ("198.51.100.1", "3128") in proxies

    def test_parse_csv(self):
        """Test parsing CSV format proxies."""
        provider = SimpleProvider("http://example.com/proxies.csv", format="csv")
        csv_data = '"192.0.2.1","8080"\n198.51.100.1,3128'
        proxies = provider._parse_csv(csv_data)
        assert len(proxies) == 2
        assert ("192.0.2.1", "8080") in proxies

    def test_parse_csv_handles_quoted_commas(self):
        """The csv module path must round-trip fields containing commas
        (e.g. "Server, Inc",80) - the previous str.split(',') corrupted those.
        """
        provider = SimpleProvider("http://example.com/proxies.csv", format="csv")
        csv_data = '"Server, Inc",8080\n"Other, Co",3128'
        proxies = provider._parse_csv(csv_data)
        assert proxies == [("Server, Inc", "8080"), ("Other, Co", "3128")]

    def test_parse_text_strips_whitespace_and_extra_colons(self):
        """split(':',1) + .strip() must accept lines like 'host:port  '
        and 'host:port:comment', not silently drop them.
        """
        provider = SimpleProvider("http://example.com/proxies.txt", format="text")
        text_data = "  192.0.2.1:8080  \n198.51.100.1:3128:trailing-comment"
        proxies = provider._parse_text(text_data)
        assert ("192.0.2.1", "8080") in proxies
        # Second line: the colon after port is part of the port field
        # (split limit=1 keeps it). That's intentionally lenient: better
        # to capture a slightly-off port than silently drop the line.
        assert any(p[0] == "198.51.100.1" for p in proxies)

    def test_parse_json_does_not_duplicate_when_both_ip_and_host(self):
        """An item with both 'ip' and 'host' keys must be emitted once,
        not twice. Guards against the previous nested-loop bug.
        """
        provider = SimpleProvider("http://example.com/proxies.json", format="json")
        json_data = '[{"ip": "192.0.2.1", "host": "192.0.2.1", "port": 8080}]'
        proxies = provider._parse_json(json_data)
        assert proxies == [("192.0.2.1", "8080")]


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
            {"ip": "192.0.2.1", "port": 8080},
            {"host": "198.51.100.1", "proxy_port": "3128"},
            "203.0.113.1:8888",
        ]
        proxies = provider._extract_from_list(items)
        assert len(proxies) == 3
        assert ("192.0.2.1", "8080") in proxies
        assert ("198.51.100.1", "3128") in proxies
        assert ("203.0.113.1", "8888") in proxies

    def test_find_proxies_proxy_path_handles_non_dict(self):
        """When proxy_path walks into a non-dict (e.g. middle key is a
        list), the previous code crashed with AttributeError. Now we
        stop walking and let the extraction step handle whatever we
        landed on.
        """
        provider = APIProvider(
            "http://api.example.com/proxies",
            response_format="json",
            proxy_path="data.proxies",
        )
        # data is a list, not a dict - the .get('proxies') would crash.
        json_response = '{"data": [{"ip": "192.0.2.1", "port": 8080}]}'
        # Should not raise; should fall through to fallback pattern matching
        # (which returns whatever IPPortPatternGlobal finds in the raw text).
        result = provider.find_proxies(json_response)
        # The exact return depends on fallback behaviour; key assertion
        # is that this call does not raise AttributeError.
        assert isinstance(result, list)


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


def test_config_without_url_is_rejected():
    """A YAML/JSON config that omits 'url' must raise ValueError, not silently
    construct a Provider with url=None.
    """
    with pytest.raises(ValueError, match="url"):
        ConfigurableProvider.from_config({"type": "simple", "format": "text"})


def test_paginated_config_propagates_page_step():
    """page_step in YAML must reach the PaginatedProvider constructor."""
    cfg = {
        "type": "paginated",
        "url": "http://example.com/page-{}.html",
        "page_step": 5,
    }
    provider = ConfigurableProvider.from_config(cfg)
    assert isinstance(provider, PaginatedProvider)
    assert provider.page_step == 5


def test_underscore_prefix_yaml_files_are_skipped():
    """Files starting with '_' are skipped by the config loader, mirroring
    the Python loader. Lets users disable a config by renaming.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_yaml_config(Path(tmpdir) / "active.yaml")
        _write_yaml_config(Path(tmpdir) / "_disabled.yaml")

        providers = load_provider_configs_from_directory(tmpdir)
        assert len(providers) == 1


def test_simple_provider_custom_pattern_normalises_strings():
    """When a custom regex has 0 or 1 capture groups, re.findall returns
    strings. find_proxies must convert those to (host, port) tuples so
    Provider.proxies setter doesn't blow up on iter unpacking. Real
    user-supplied patterns commonly omit explicit capture groups.
    """
    page = "192.0.2.1:8080\nnot-a-proxy\n198.51.100.1:3128"
    # Pattern with NO capture groups
    p = SimpleProvider("http://example.com/list.txt", pattern=r"\d+\.\d+\.\d+\.\d+:\d+")
    assert p.find_proxies(page) == [
        ("192.0.2.1", "8080"),
        ("198.51.100.1", "3128"),
    ]
    # Pattern with TWO capture groups (already returns tuples)
    p2 = SimpleProvider(
        "http://example.com/list.txt", pattern=r"(\d+\.\d+\.\d+\.\d+):(\d+)"
    )
    assert p2.find_proxies(page) == [
        ("192.0.2.1", "8080"),
        ("198.51.100.1", "3128"),
    ]


def test_python_loader_skips_imported_classes():
    """A user file that does `from proxybroker import SimpleProvider` should
    NOT cause SimpleProvider to be instantiated. Only classes defined in
    the file itself should be loaded.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "imports_only.py"
        path.write_text(
            textwrap.dedent(
                """
                # No locally-defined Provider subclasses, only imports.
                from proxybroker import SimpleProvider, PaginatedProvider, APIProvider  # noqa: F401
                """
            ).lstrip()
        )

        providers = load_python_providers_from_directory(tmpdir)
        assert providers == []
