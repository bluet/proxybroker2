# Custom Proxy Providers Guide

ProxyBroker2 lets you add your own proxy sources without modifying the codebase. The most common use case — a Docker user dropping YAML files into a folder — works out of the box.

## Docker (no coding required)

The recommended UX for the published Docker image. Drop YAML/JSON config files into a folder, bind-mount it to `/configs`, and ProxyBroker picks them up automatically.

### 1. Write a config file

```yaml
# ~/proxy-sources/my_secret_list.yaml
name: My Internal Source
type: simple
url: https://my-private-server.example.com/proxies.txt
format: text          # auto, text, json, csv, html
protocols:
  - HTTP
  - HTTPS
max_connections: 4
timeout: 20
```

### 2. Run the container

```bash
docker run --rm \
  -v ~/proxy-sources:/configs \
  bluet/proxybroker2 \
  find --types HTTP --limit 10
```

That is it. Multiple `*.yaml` / `*.yml` / `*.json` files in the directory are all loaded. Files starting with `_` are ignored.

### How the directory is discovered

The CLI looks for a provider directory in this order — the first match wins:

1. Each `--provider-dir PATH` (repeatable) on the command line.
2. `$PROXYBROKER_PROVIDER_DIR` environment variable (single path).
3. `/configs` if it exists in the container (the Docker convention shown above).

If none of those are set, only the bundled provider list is used (existing behaviour).

### Replacing the bundled providers entirely

By default, configs from your directory are **added** to the bundled provider list. To use *only* your own configs and skip every bundled source, you currently need the Python API:

```python
from proxybroker import Broker

# Only providers from /configs, no bundled defaults.
broker = Broker(providers=[], provider_dirs=['/configs'])
```

There is no CLI equivalent today — `--provider URL` always *adds* a single URL, it cannot express the empty list. If you need a no-defaults Docker workflow, run a tiny Python wrapper instead of `python -m proxybroker`. Tracking issue: open one if you want a `--no-default-providers` CLI flag.

## Python API (for developers)

If you are scripting against the library directly, you can also pass `Provider` instances or use the helper classes.

```python
from proxybroker import SimpleProvider, Broker

class MyProvider(SimpleProvider):
    domain = "mysite.com"

    def __init__(self):
        super().__init__(
            url="http://mysite.com/proxies.txt",
            format='text',
            proto=('HTTP', 'HTTPS')
        )

broker = Broker(providers=[MyProvider()])
```

### Loading Python provider modules from a directory

`load_python_providers_from_directory()` is also available, but **it executes arbitrary Python code** from every `.py` file in the directory. Only point it at a directory whose contents you fully control. The CLI never calls it; you must opt in from Python:

```python
from proxybroker import Broker, load_python_providers_from_directory

trusted_providers = load_python_providers_from_directory('/path/I/trust')
broker = Broker(providers=trusted_providers)
```

## Provider Types

### 1. SimpleProvider - For Basic Proxy Lists

Perfect for sites that provide proxies in common formats:

```python
from proxybroker import SimpleProvider

class TextListProvider(SimpleProvider):
    """Provider for plain text proxy lists."""
    domain = "example.com"

    def __init__(self):
        super().__init__(
            url="http://example.com/proxies.txt",
            format='text',  # auto-detect, text, json, csv, html
            proto=('HTTP', 'HTTPS')
        )

class JSONAPIProvider(SimpleProvider):
    """Provider for JSON APIs."""
    domain = "api.example.com"

    def __init__(self):
        super().__init__(
            url="http://api.example.com/proxies",
            format='json',
            proto=('HTTP', 'HTTPS', 'SOCKS5')
        )
```

**Supported Formats:**
- `text`: Plain text list (IP:PORT per line)
- `json`: JSON response with proxy data
- `csv`: CSV format proxy lists
- `html`: HTML pages (uses default pattern matching)
- `auto`: Automatically detect format

### 2. PaginatedProvider - For Multi-Page Sites

For sites with pagination:

```python
from proxybroker import PaginatedProvider

class PaginatedSite(PaginatedProvider):
    domain = "proxypages.com"

    def __init__(self):
        super().__init__(
            base_url="http://proxypages.com/list/page-{}.html",  # {} = page number
            start_page=1,
            max_pages=10,
            proto=('HTTP', 'HTTPS')
        )
```

**URL Patterns:**
- `http://site.com/page-{}.html` - Page number in URL path
- `http://site.com/proxies?page={}` - Page as query parameter

### 3. APIProvider - For Authenticated APIs

For APIs requiring authentication:

```python
from proxybroker import APIProvider

class AuthenticatedAPI(APIProvider):
    domain = "api.proxies.com"

    def __init__(self, api_key):
        super().__init__(
            api_url="https://api.proxies.com/v1/list",
            api_key=api_key,
            response_format='json',
            proxy_path='data.proxies',  # Path to proxy list in JSON
            proto=('HTTP', 'HTTPS')
        )
```

### 4. Custom Provider - Full Control

For complex sites requiring custom logic:

```python
from proxybroker import Provider
import re

class ComplexProvider(Provider):
    domain = "complex-site.com"

    async def _pipe(self):
        """Custom scraping pipeline."""
        # Step 1: Get main page
        main_page = await self.get("http://complex-site.com/")

        # Step 2: Extract proxy page URLs
        urls = re.findall(r'href="(/proxy/\d+)"', main_page)

        # Step 3: Fetch all proxy pages
        full_urls = [f"http://complex-site.com{u}" for u in urls]
        await self._find_on_pages(full_urls)

    def find_proxies(self, page):
        """Custom proxy extraction."""
        # Extract proxies from JavaScript
        pattern = r'addProxy\("(\d+\.\d+\.\d+\.\d+)",\s*(\d+)\)'
        return re.findall(pattern, page)
```

## Configuration File Reference

### Simple Provider Config

```yaml
name: My Simple Proxy List
type: simple
url: http://example.com/proxies.txt
format: text  # auto|text|json|csv|html
pattern: null  # Optional custom regex
protocols:
  - HTTP
  - HTTPS
max_connections: 4
timeout: 20
```

### Paginated Provider Config

```yaml
name: My Paginated Site
type: paginated
url: http://example.com/proxies/page-{}.html
page_param: page  # For query parameter style
start_page: 1
max_pages: 10
page_step: 1
protocols:
  - HTTP
  - HTTPS
  - SOCKS4
  - SOCKS5
max_connections: 4
timeout: 20
```

### API Provider Config

```json
{
  "name": "My Proxy API",
  "type": "api",
  "url": "http://api.example.com/v1/proxies",
  "api_key": "your-api-key",
  "headers": {
    "User-Agent": "ProxyBroker/2.0"
  },
  "response_format": "json",
  "proxy_path": "data.proxies",
  "protocols": ["HTTP", "HTTPS"],
  "max_connections": 2,
  "timeout": 30
}
```

## Usage Examples

### Loading Providers from Directory

```python
from proxybroker import Broker

# Load all providers from a directory
broker = Broker(provider_dirs=['./custom_providers/'])

# Combine with default providers
broker = Broker(provider_dirs=['./custom_providers/'])  # Uses defaults + custom

# Only custom providers (no defaults)
broker = Broker(
    providers=[],  # Empty list = no defaults
    provider_dirs=['./custom_providers/']
)
```

### Mixing Configuration and Code

```python
from proxybroker import Broker, SimpleProvider

# Define provider in code
code_provider = SimpleProvider(
    url="http://example.com/proxies.txt",
    format='text'
)

# Load from both code and config files
broker = Broker(
    providers=[code_provider],
    provider_dirs=['./config_providers/']
)
```

### Creating Provider Templates

```python
from proxybroker import create_provider_config_template

# Create a template configuration file
create_provider_config_template(
    'my_provider.yaml',
    provider_type='simple'  # simple|paginated|api
)
```

## Advanced Topics

### Custom Patterns

For sites with non-standard proxy formats:

```python
class CustomPatternProvider(SimpleProvider):
    def __init__(self):
        # Pattern for format: "proxy://192.168.1.1@8080"
        pattern = r'proxy://(\d+\.\d+\.\d+\.\d+)@(\d+)'

        super().__init__(
            url="http://site.com/proxies.html",
            pattern=pattern
        )
```

### Rate Limiting

Respect rate limits when scraping:

```python
class RateLimitedProvider(Provider):
    def __init__(self):
        super().__init__(
            url="http://site.com/proxies",
            max_conn=1,  # One connection at a time
            timeout=30
        )

    async def get(self, url, **kwargs):
        await asyncio.sleep(2)  # 2 second delay
        return await super().get(url, **kwargs)
```

### Handling Authentication

For complex authentication flows:

```python
class OAuthProvider(Provider):
    async def _pipe(self):
        # Get OAuth token
        token_response = await self.get(
            "http://site.com/oauth/token",
            data={"client_id": "...", "client_secret": "..."},
            method="POST"
        )

        token = json.loads(token_response)['access_token']

        # Use token for proxy list
        await self._find_on_page(
            "http://site.com/api/proxies",
            headers={"Authorization": f"Bearer {token}"}
        )
```

### Error Handling

```python
class RobustProvider(Provider):
    def find_proxies(self, page):
        try:
            # Try JSON parsing
            data = json.loads(page)
            return [(p['ip'], p['port']) for p in data['proxies']]
        except:
            # Fallback to regex
            return self._find_proxies(page)
```

## Best Practices

1. **Be Respectful**: Use appropriate `max_conn` and timeouts
2. **Handle Errors**: Always have fallback parsing logic
3. **Test First**: Test your provider with a small limit
4. **Use Caching**: Implement caching for expensive operations
5. **Document**: Add docstrings explaining the site's format

## Troubleshooting

### No Proxies Found

1. Check the URL is accessible
2. Verify the format detection
3. Test your regex pattern
4. Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Rate Limiting

If you get blocked:
- Reduce `max_conn` to 1 or 2
- Increase `timeout`
- Add delays between requests
- Use rotating user agents

### JSON Parsing Issues

For nested JSON structures:

```python
# Response: {"success": true, "data": {"proxies": [...]}}
provider = APIProvider(
    api_url="...",
    proxy_path="data.proxies"  # Navigate nested structure
)
```

## Contributing Providers

If you create a provider for a popular proxy source, consider contributing it:

1. Test thoroughly
2. Follow the existing code style
3. Add to the PROVIDERS list in `providers.py`
4. Submit a pull request

## Example: Complete Custom Provider

Here's a complete example for a fictional proxy site:

```python
from proxybroker import Provider
import re
import json

class MyProxySite(Provider):
    """Provider for myproxysite.com - a fictional proxy listing site."""

    domain = "myproxysite.com"

    def __init__(self):
        super().__init__(
            url="https://myproxysite.com/api/proxies",
            proto=('HTTP', 'HTTPS', 'SOCKS4', 'SOCKS5'),
            max_conn=3,
            timeout=30
        )

    async def _pipe(self):
        """Fetch proxy lists from multiple endpoints."""
        # Get list of available proxy lists
        index = await self.get(self.url + "/index")

        try:
            data = json.loads(index)
            endpoints = data.get('endpoints', [])
        except:
            endpoints = ['/free', '/premium']

        # Fetch each endpoint
        urls = [self.url + endpoint for endpoint in endpoints]
        await self._find_on_pages(urls)

    def find_proxies(self, page):
        """Extract proxies from API response."""
        proxies = []

        try:
            data = json.loads(page)

            # Handle API response format
            for item in data.get('proxies', []):
                ip = item.get('ip')
                port = str(item.get('port'))
                protocols = item.get('protocols', ['HTTP'])

                if ip and port:
                    # You can filter by protocol if needed
                    proxies.append((ip, port))

        except json.JSONDecodeError:
            # Fallback to HTML parsing
            # Look for: <span class="proxy">192.168.1.1:8080</span>
            pattern = r'<span class="proxy">(\d+\.\d+\.\d+\.\d+):(\d+)</span>'
            proxies = re.findall(pattern, page)

        return proxies

# Usage
if __name__ == "__main__":
    import asyncio
    from proxybroker import Broker

    async def main():
        broker = Broker(providers=[MyProxySite()])

        async for proxy in broker.find(types=['HTTP', 'HTTPS'], limit=10):
            print(f"{proxy.host}:{proxy.port} [{proxy.types}]")

    asyncio.run(main())
```

This provider:
- Fetches an index of available endpoints
- Handles both JSON and HTML responses
- Includes error handling
- Respects rate limits
- Can be easily modified for real sites
