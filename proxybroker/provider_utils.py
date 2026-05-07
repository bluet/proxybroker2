"""Utilities and enhanced base classes for creating custom proxy providers."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

from .providers import Provider
from .utils import log


class SimpleProvider(Provider):
    """Simplified provider for basic proxy lists.

    This provider handles common patterns like:
    - Plain text lists (IP:PORT per line)
    - Simple HTML tables
    - JSON/CSV formats
    """

    def __init__(self, url, pattern=None, format="auto", **kwargs):
        """
        :param str url: URL of the proxy list
        :param str pattern: Custom regex pattern for proxy extraction
        :param str format: Format of the proxy list ('auto', 'text', 'json', 'csv', 'html')
        """
        super().__init__(url=url, **kwargs)
        self.format = format
        self.custom_pattern = pattern

    async def _pipe(self):
        """Simple pipe that just fetches and parses the main URL."""
        await self._find_on_page(self.url)

    def find_proxies(self, page):
        """Automatically detect format and extract proxies.

        Detection is per-call: an earlier transient empty/error response
        must NOT permanently lock self.format to the wrong parser, which
        was the previous bug when the same SimpleProvider instance is
        reused across grab cycles in serve mode.
        """
        if self.custom_pattern:
            matches = re.findall(self.custom_pattern, page)
            # Provider.proxies setter expects (host, port) tuples. With a
            # 2-capture-group pattern, re.findall already returns tuples.
            # With 0 or 1 groups it returns strings - try to recover by
            # splitting on ':'.
            normalized = []
            for m in matches:
                if isinstance(m, tuple) and len(m) >= 2:
                    normalized.append((m[0], m[1]))
                elif isinstance(m, str) and ":" in m:
                    host, _, port = m.rpartition(":")
                    normalized.append((host, port))
                # else: cannot extract a host/port pair, drop silently
            return normalized

        fmt = self.format if self.format != "auto" else self._detect_format(page)

        if fmt == "json":
            return self._parse_json(page)
        elif fmt == "csv":
            return self._parse_csv(page)
        elif fmt == "text":
            return self._parse_text(page)
        else:  # html or fallback
            return self._find_proxies(page)

    def _detect_format(self, content):
        """Detect the format of the proxy list."""
        content = content.strip()

        # Check for JSON
        if content.startswith(("[", "{")) and content.endswith(("]", "}")):
            try:
                json.loads(content)
                return "json"
            except json.JSONDecodeError:
                pass

        # Check for CSV (has commas and multiple lines)
        lines = content.split("\n")
        if len(lines) > 1 and "," in lines[0]:
            return "csv"

        # Check for HTML
        if "<" in content and ">" in content:
            return "html"

        # Default to text
        return "text"

    def _parse_json(self, content):
        """Parse JSON format proxy lists."""
        try:
            data = json.loads(content)
            proxies = []

            # Handle different JSON structures
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Try common field names. Take the FIRST (ip,port)
                        # pair we find and stop - otherwise an item with
                        # both 'ip' and 'host' would be added twice.
                        matched = False
                        for ip_field in ["ip", "host", "address", "proxy"]:
                            for port_field in ["port", "p"]:
                                if ip_field in item and port_field in item:
                                    proxies.append(
                                        (item[ip_field], str(item[port_field]))
                                    )
                                    matched = True
                                    break
                            if matched:
                                break
                    elif isinstance(item, str) and ":" in item:
                        # Format: "IP:PORT"
                        ip, port = item.split(":", 1)
                        proxies.append((ip, port))

            return proxies
        except Exception as e:
            log.error(f"Error parsing JSON from {self.domain}: {e}")
            return []

    def _parse_csv(self, content):
        """Parse CSV format proxy lists.

        Uses the stdlib csv module so quoted fields with embedded commas
        ("Server, Inc",80) round-trip correctly. The previous str.split(",")
        path corrupted any line whose first field contained a comma.
        """
        import csv
        import io

        proxies = []
        reader = csv.reader(io.StringIO(content.strip()))
        for row in reader:
            if len(row) >= 2:
                ip = row[0].strip()
                port = row[1].strip()
                if ip and port:
                    proxies.append((ip, port))
        return proxies

    def _parse_text(self, content):
        """Parse plain text proxy lists."""
        proxies = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                # Format: IP:PORT, with optional trailing junk like
                #   "1.2.3.4:8080"
                #   "1.2.3.4:8080 # US"
                #   "1.2.3.4:8080:tag"
                # Keep only the leading digit run after the FIRST `:` as
                # the port. Without this guard the whole suffix becomes
                # the port string and Proxy.create's int(port) crashes.
                host, _, rest = line.partition(":")
                port_chars = []
                for ch in rest.lstrip():
                    if ch.isdigit():
                        port_chars.append(ch)
                    else:
                        break
                if port_chars:
                    proxies.append((host.strip(), "".join(port_chars)))
            elif "\t" in line or " " in line:
                # Format: IP PORT or IP\tPORT
                parts = line.split()
                if len(parts) >= 2:
                    proxies.append((parts[0], parts[1]))
        return proxies


class PaginatedProvider(Provider):
    """Provider for sites with pagination."""

    def __init__(
        self,
        base_url,
        page_param="page",
        start_page=1,
        max_pages=10,
        page_step=1,
        **kwargs,
    ):
        """
        :param str base_url: Base URL with placeholder for page number
        :param str page_param: URL parameter name for pagination
        :param int start_page: First page number
        :param int max_pages: Maximum number of pages to fetch
        :param int page_step: Step between page numbers
        """
        super().__init__(url=base_url, **kwargs)
        self.base_url = base_url
        self.page_param = page_param
        self.start_page = start_page
        self.max_pages = max_pages
        self.page_step = page_step

    async def _pipe(self):
        """Fetch all pages."""
        urls = []
        for page in range(
            self.start_page,
            self.start_page + (self.max_pages * self.page_step),
            self.page_step,
        ):
            urls.append(self._build_page_url(page))

        await self._find_on_pages(urls)

    def _build_page_url(self, page):
        """Substitute the page number into base_url cleanly.

        - `{}` placeholder => format()
        - existing `?<page_param>=...` => REPLACE the value (don't append a
          duplicate param; many servers honor only the first occurrence)
        - otherwise => append `?<page_param>=N`
        """
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        if "{}" in self.base_url:
            return self.base_url.format(page)

        parsed = urlparse(self.base_url)
        if parsed.query:
            params = parse_qsl(parsed.query, keep_blank_values=True)
            replaced = False
            new_params = []
            for key, value in params:
                if key == self.page_param:
                    new_params.append((key, str(page)))
                    replaced = True
                else:
                    new_params.append((key, value))
            if not replaced:
                new_params.append((self.page_param, str(page)))
            return urlunparse(parsed._replace(query=urlencode(new_params)))
        return f"{self.base_url}?{self.page_param}={page}"


class APIProvider(Provider):
    """Provider for API-based proxy sources."""

    def __init__(
        self,
        api_url,
        api_key=None,
        headers=None,
        response_format="json",
        proxy_path=None,
        **kwargs,
    ):
        """
        :param str api_url: API endpoint URL
        :param str api_key: API key (if required)
        :param dict headers: Additional headers
        :param str response_format: Response format ('json', 'xml', 'text')
        :param str proxy_path: Path to proxy data in response (for nested JSON)
        """
        super().__init__(url=api_url, **kwargs)
        self.api_key = api_key
        self.custom_headers = headers or {}
        self.response_format = response_format
        self.proxy_path = proxy_path

    async def _pipe(self):
        """Fetch from API with authentication."""
        headers = self.custom_headers.copy()

        if self.api_key:
            # Try common API key header names
            headers.update(
                {
                    "X-API-Key": self.api_key,
                    "Authorization": f"Bearer {self.api_key}",
                    "apikey": self.api_key,
                }
            )

        await self._find_on_page(self.url, headers=headers)

    def find_proxies(self, page):
        """Parse API response based on format."""
        if self.response_format == "json":
            try:
                data = json.loads(page)

                # Navigate to proxy data using path. Stop walking once
                # we hit a non-dict (list/scalar): calling .get on those
                # would raise AttributeError and kill the provider.
                if self.proxy_path:
                    for key in self.proxy_path.split("."):
                        if isinstance(data, dict):
                            data = data.get(key, data)
                        else:
                            break

                # Extract proxies from data
                if isinstance(data, list):
                    return self._extract_from_list(data)
                elif isinstance(data, dict):
                    # Look for common proxy list keys
                    for key in ["proxies", "data", "results", "items"]:
                        if key in data and isinstance(data[key], list):
                            return self._extract_from_list(data[key])

            except Exception as e:
                log.error(f"Error parsing API response from {self.domain}: {e}")

        # Fallback to default pattern matching
        return self._find_proxies(page)

    def _extract_from_list(self, items):
        """Extract proxy info from a list of items."""
        proxies = []
        for item in items:
            if isinstance(item, dict):
                # Try to find IP and port fields
                ip = None
                port = None

                for ip_key in ["ip", "host", "address", "proxy_ip"]:
                    if ip_key in item:
                        ip = item[ip_key]
                        break

                for port_key in ["port", "proxy_port", "p"]:
                    if port_key in item:
                        port = str(item[port_key])
                        break

                if ip and port:
                    proxies.append((ip, port))

            elif isinstance(item, str) and ":" in item:
                parts = item.split(":", 1)
                if len(parts) == 2:
                    proxies.append((parts[0], parts[1]))

        return proxies


class ConfigurableProvider(Provider):
    """Provider that can be configured via YAML/JSON without coding."""

    @classmethod
    def from_config(cls, config: str | Path | dict):
        """Create provider from configuration.

        :param config: Path to YAML/JSON file or dict configuration
        """
        if isinstance(config, (str, Path)):
            config_path = Path(config)
            if config_path.suffix in [".yaml", ".yml"]:
                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
            elif config_path.suffix == ".json":
                with open(config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            else:
                raise ValueError(
                    f"Unsupported config file extension: {config_path.suffix}"
                )
        else:
            cfg = config

        if not isinstance(cfg, dict):
            raise ValueError(
                f"Provider config must be a mapping, got {type(cfg).__name__}"
            )

        url = cfg.get("url")
        if not url:
            raise ValueError("Provider config must include a 'url' field")
        provider_type = cfg.get("type", "simple")

        # Create appropriate provider instance
        if provider_type == "simple":
            return SimpleProvider(
                url=url,
                pattern=cfg.get("pattern"),
                format=cfg.get("format", "auto"),
                proto=tuple(cfg.get("protocols", [])),
                max_conn=cfg.get("max_connections", 4),
                timeout=cfg.get("timeout", 20),
            )
        elif provider_type == "paginated":
            return PaginatedProvider(
                base_url=url,
                page_param=cfg.get("page_param", "page"),
                start_page=cfg.get("start_page", 1),
                max_pages=cfg.get("max_pages", 10),
                page_step=cfg.get("page_step", 1),
                proto=tuple(cfg.get("protocols", [])),
                max_conn=cfg.get("max_connections", 4),
                timeout=cfg.get("timeout", 20),
            )
        elif provider_type == "api":
            return APIProvider(
                api_url=url,
                api_key=cfg.get("api_key"),
                headers=cfg.get("headers"),
                response_format=cfg.get("response_format", "json"),
                proxy_path=cfg.get("proxy_path"),
                proto=tuple(cfg.get("protocols", [])),
                max_conn=cfg.get("max_connections", 4),
                timeout=cfg.get("timeout", 20),
            )
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")


def load_provider_configs_from_directory(
    directory: str | Path,
) -> list[Provider]:
    """Load YAML/JSON provider configs from a directory.

    Safe to point at a Docker bind-mount or any user-controlled directory:
    only data files (.yaml, .yml, .json) are read. No code is executed.

    :param directory: Path to directory containing *.yaml / *.yml / *.json
    :return: List of Provider instances built from the configs
    """
    providers = []
    directory = Path(directory)

    if not directory.exists():
        log.warning(f"Provider directory does not exist: {directory}")
        return providers

    # Files starting with "_" are skipped (mirrors the Python loader's
    # convention) so users can disable a config by renaming it.
    config_paths = sorted(
        p
        for p in (
            list(directory.glob("*.yaml"))
            + list(directory.glob("*.yml"))
            + list(directory.glob("*.json"))
        )
        if not p.name.startswith("_")
    )
    for config_path in config_paths:
        try:
            provider = ConfigurableProvider.from_config(str(config_path))
            providers.append(provider)
            log.info(f"Loaded provider from config: {config_path}")
        except Exception as e:
            log.error(f"Error loading provider config {config_path}: {e}")

    return providers


def load_python_providers_from_directory(
    directory: str | Path,
) -> list[Provider]:
    """Load Provider subclasses from *.py files in a directory.

    SECURITY: This function executes arbitrary Python code from every .py
    file in the given directory. Only point it at directories whose
    contents you fully trust. It is NOT safe for Docker bind-mounts or any
    path a less-privileged user can write to. The CLI does not expose this
    loader by default — callers must opt in explicitly.

    :param directory: Path to directory containing custom provider modules
    :return: List of Provider instances discovered and instantiated
    """
    providers = []
    directory = Path(directory)

    if not directory.exists():
        log.warning(f"Provider directory does not exist: {directory}")
        return providers

    for module_path in sorted(directory.glob("*.py")):
        if module_path.name.startswith("_"):
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"custom_provider_{module_path.stem}", module_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                # Only instantiate Provider subclasses DEFINED in this
                # module - skip ones merely imported into its namespace
                # (e.g. `from proxybroker import SimpleProvider`), otherwise
                # we would inadvertently spin up a SimpleProvider per file.
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Provider)
                    and attr is not Provider
                    and getattr(attr, "__module__", None) == spec.name
                ):
                    try:
                        provider = attr()
                        providers.append(provider)
                        log.info(
                            f"Loaded custom provider: {attr_name} from {module_path}"
                        )
                    except Exception as e:
                        log.error(f"Error instantiating provider {attr_name}: {e}")

        except Exception as e:
            log.error(f"Error loading provider module {module_path}: {e}")

    return providers


def load_providers_from_directory(
    directory: str | Path,
    *,
    allow_python: bool = False,
) -> list[Provider]:
    """Load providers from a directory.

    By default, only YAML/JSON config files are loaded — safe for Docker
    bind-mounts and other user-controlled paths. Pass ``allow_python=True``
    to additionally execute *.py files in the directory; only do that for
    directories you fully trust.

    :param directory: Path to directory containing provider definitions
    :param allow_python: If True, also load Provider subclasses from .py
        files. SECURITY: executes arbitrary Python.
    :return: List of Provider instances
    """
    providers = load_provider_configs_from_directory(directory)
    if allow_python:
        providers.extend(load_python_providers_from_directory(directory))
    return providers


def create_provider_config_template(
    filepath: str | Path, provider_type: str = "simple"
):
    """Create a template configuration file for a provider.

    :param filepath: Path where to save the template
    :param provider_type: Type of provider ('simple', 'paginated', 'api')
    """
    templates = {
        "simple": {
            "name": "My Proxy List",
            "type": "simple",
            "url": "http://example.com/proxy-list.txt",
            "format": "text",  # auto, text, json, csv, html
            "pattern": None,  # Custom regex pattern (optional)
            "protocols": ["HTTP", "HTTPS"],
            "max_connections": 4,
            "timeout": 20,
        },
        "paginated": {
            "name": "My Paginated Proxy Site",
            "type": "paginated",
            "url": "http://example.com/proxies?page={}",
            "page_param": "page",
            "start_page": 1,
            "max_pages": 10,
            "protocols": ["HTTP", "HTTPS", "SOCKS4", "SOCKS5"],
            "max_connections": 4,
            "timeout": 20,
        },
        "api": {
            "name": "My Proxy API",
            "type": "api",
            "url": "http://api.example.com/v1/proxies",
            # Optional. Recommendation: don't paste a literal here -
            # leave blank and have your code do
            #     api_key=os.environ["PROXY_API_KEY"]
            # before calling ConfigurableProvider.from_config().
            "api_key": "",
            "headers": {  # Optional custom headers
                "User-Agent": "ProxyBroker/2.0"
            },
            "response_format": "json",
            "proxy_path": "data.proxies",  # Path to proxy list in JSON response
            "protocols": ["HTTP", "HTTPS"],
            "max_connections": 2,
            "timeout": 30,
        },
    }

    template = templates.get(provider_type, templates["simple"])
    filepath = Path(filepath)

    if filepath.suffix == ".json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(template, f, default_flow_style=False)

    log.info(f"Created provider template at: {filepath}")
