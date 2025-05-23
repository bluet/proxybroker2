import asyncio
from collections import namedtuple
from unittest.mock import MagicMock

from proxybroker import Proxy

ResolveResult = namedtuple('ResolveResult', ['host', 'ttl'])


def future_iter(*args):
    for resp in args:
        f = asyncio.Future()
        f.set_result(resp)
        yield f


def create_mock_proxy(host='127.0.0.1', port=8080, schemes=None, types=None):
    """Create a mock proxy with common attributes."""
    if schemes is None:
        schemes = ('HTTP', 'HTTPS')
    if types is None:
        types = {}
    
    proxy = MagicMock(spec=Proxy)
    proxy.host = host
    proxy.port = port
    proxy.schemes = schemes
    proxy.types = types
    proxy.avg_resp_time = 1.5
    proxy.error_rate = 0.1
    proxy.stat = {'requests': 5}
    proxy.log = MagicMock()
    proxy.close = MagicMock()
    proxy.geo = MagicMock()
    proxy.geo.code = 'US'
    proxy.geo.name = 'United States'
    
    # Mock as_json method
    proxy.as_json.return_value = {
        'host': host,
        'port': port,
        'types': [{'type': k, 'level': v} for k, v in types.items()],
        'avg_resp_time': proxy.avg_resp_time,
        'error_rate': proxy.error_rate,
        'geo': {
            'country': {'code': proxy.geo.code, 'name': proxy.geo.name},
            'region': {'code': 'Unknown', 'name': 'Unknown'},
            'city': 'Unknown'
        }
    }
    
    return proxy


def create_mock_judge(url='http://judge.example.com'):
    """Create a mock judge for testing."""
    from proxybroker.judge import Judge
    
    judge = MagicMock(spec=Judge)
    judge.url = url
    judge.host = 'judge.example.com'
    judge.path = '/'
    judge.request = b'GET / HTTP/1.1\r\nHost: judge.example.com\r\n\r\n'
    return judge


def create_mock_provider(url='http://provider.example.com'):
    """Create a mock provider for testing."""
    from proxybroker.providers import Provider
    
    provider = MagicMock(spec=Provider)
    provider.url = url
    
    async def mock_get_proxies(*args, **kwargs):
        # Yield some test proxy data
        for i in range(3):
            proxy_data = MagicMock()
            proxy_data.host = f'127.0.0.{i+1}'
            proxy_data.port = 8080
            yield proxy_data
    
    provider.get_proxies = mock_get_proxies
    return provider


async def async_mock_context_manager(mock_obj):
    """Helper to create async context manager from mock object."""
    return mock_obj


class AsyncContextManagerMock:
    """Mock async context manager for testing."""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
        self.enter_called = False
        self.exit_called = False
    
    async def __aenter__(self):
        self.enter_called = True
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exit_called = True
        return False
