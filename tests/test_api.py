import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Broker, Proxy
from proxybroker.api import GRAB_PAUSE, MAX_CONCURRENT_PROVIDERS
from proxybroker.errors import ResolveError


@pytest.fixture
def broker():
    """Create a basic broker instance for testing."""
    return Broker(timeout=0.1, max_conn=5, max_tries=1)


@pytest.fixture
def mock_queue():
    """Create a mock queue for testing."""
    queue = asyncio.Queue()
    return queue


@pytest.mark.asyncio
async def test_broker_init():
    """Test Broker initialization with default values."""
    broker = Broker()
    assert broker._timeout == 8
    assert broker._max_tries == 3
    assert broker._verify_ssl is False
    assert broker._proxies is not None
    assert broker._resolver is not None
    assert broker._providers is not None


@pytest.mark.asyncio
async def test_broker_init_with_custom_values():
    """Test Broker initialization with custom values."""
    queue = asyncio.Queue()
    broker = Broker(
        queue=queue,
        timeout=5,
        max_conn=10,
        max_tries=2,
        verify_ssl=True
    )
    assert broker._timeout == 5
    assert broker._max_tries == 2
    assert broker._verify_ssl is True
    assert broker._proxies is queue


@pytest.mark.asyncio
async def test_broker_init_with_custom_judges():
    """Test Broker initialization with custom judges."""
    custom_judges = ['http://judge1.com', 'http://judge2.com']
    broker = Broker(judges=custom_judges)
    assert broker._judges == custom_judges


@pytest.mark.asyncio
async def test_broker_init_with_custom_providers():
    """Test Broker initialization with custom providers."""
    custom_providers = ['http://provider1.com', 'http://provider2.com']
    broker = Broker(providers=custom_providers)
    assert len(broker._providers) == 2


@pytest.mark.asyncio
async def test_broker_find_with_mock_provider(broker, mocker):
    """Test broker find method with mocked provider."""
    # Mock the provider to return test proxies
    mock_proxy1 = MagicMock(spec=Proxy)
    mock_proxy1.host = '127.0.0.1'
    mock_proxy1.port = 8080
    
    mock_proxy2 = MagicMock(spec=Proxy)
    mock_proxy2.host = '127.0.0.2'
    mock_proxy2.port = 8080
    
    # Mock the provider's get_proxies method
    async def mock_get_proxies(*args, **kwargs):
        for proxy in [mock_proxy1, mock_proxy2]:
            yield proxy
    
    # Mock the providers
    mock_provider = MagicMock()
    mock_provider.get_proxies = mock_get_proxies
    broker._providers = [mock_provider]
    
    # Mock the resolver create method
    async def mock_create(host, port, *args, **kwargs):
        proxy = MagicMock(spec=Proxy)
        proxy.host = host
        proxy.port = port
        return proxy
    
    mocker.patch.object(Proxy, 'create', side_effect=mock_create)
    
    # Test find method
    proxies = []
    async for proxy in broker.find(limit=2):
        proxies.append(proxy)
        
    assert len(proxies) == 2
    assert proxies[0].host in ['127.0.0.1', '127.0.0.2']


@pytest.mark.asyncio
async def test_broker_find_with_countries_filter(broker, mocker):
    """Test broker find method with countries filter."""
    # Mock proxy with geo info
    mock_proxy = MagicMock(spec=Proxy)
    mock_proxy.host = '127.0.0.1'
    mock_proxy.port = 8080
    mock_proxy.geo.code = 'US'
    
    async def mock_get_proxies(*args, **kwargs):
        yield mock_proxy
    
    mock_provider = MagicMock()
    mock_provider.get_proxies = mock_get_proxies
    broker._providers = [mock_provider]
    
    async def mock_create(host, port, *args, **kwargs):
        return mock_proxy
    
    mocker.patch.object(Proxy, 'create', side_effect=mock_create)
    
    # Test with matching country
    proxies = []
    async for proxy in broker.find(countries=['US'], limit=1):
        proxies.append(proxy)
    assert len(proxies) == 1
    
    # Test with non-matching country  
    proxies = []
    async for proxy in broker.find(countries=['CN'], limit=1):
        proxies.append(proxy)
    assert len(proxies) == 0


@pytest.mark.asyncio
async def test_broker_find_with_resolve_error(broker, mocker):
    """Test broker handling of resolve errors."""
    # Mock proxy that will cause resolve error
    mock_proxy = MagicMock(spec=Proxy)
    mock_proxy.host = 'invalid.domain'
    mock_proxy.port = 8080
    
    async def mock_get_proxies(*args, **kwargs):
        yield mock_proxy
    
    mock_provider = MagicMock()
    mock_provider.get_proxies = mock_get_proxies
    broker._providers = [mock_provider]
    
    # Mock Proxy.create to raise ResolveError
    async def mock_create_error(host, port, *args, **kwargs):
        raise ResolveError('Cannot resolve host')
    
    mocker.patch.object(Proxy, 'create', side_effect=mock_create_error)
    
    # Should handle error gracefully and return no proxies
    proxies = []
    async for proxy in broker.find(limit=1):
        proxies.append(proxy)
    assert len(proxies) == 0


@pytest.mark.asyncio 
async def test_broker_grab_with_queue(mock_queue, mocker):
    """Test broker grab method with queue."""
    broker = Broker(queue=mock_queue, timeout=0.1)
    
    # Mock proxy
    mock_proxy = MagicMock(spec=Proxy)
    mock_proxy.host = '127.0.0.1'
    mock_proxy.port = 8080
    
    async def mock_get_proxies(*args, **kwargs):
        yield mock_proxy
    
    mock_provider = MagicMock()
    mock_provider.get_proxies = mock_get_proxies
    broker._providers = [mock_provider]
    
    async def mock_create(host, port, *args, **kwargs):
        return mock_proxy
    
    mocker.patch.object(Proxy, 'create', side_effect=mock_create)
    
    # Mock the checker to avoid actual checking
    async def mock_check_proxy(proxy):
        # Simulate successful check
        pass
    
    mocker.patch.object(broker._checker, 'check_proxy', side_effect=mock_check_proxy)
    
    # Start grab task
    grab_task = asyncio.create_task(broker.grab())
    
    # Let it run briefly
    await asyncio.sleep(0.01)
    
    # Cancel the task
    grab_task.cancel()
    
    try:
        await grab_task
    except asyncio.CancelledError:
        pass
    
    # Check that proxies were found (queue should have items)
    assert not mock_queue.empty()


@pytest.mark.asyncio
async def test_broker_serve_basic(mocker):
    """Test broker serve method basic functionality."""
    broker = Broker(timeout=0.1)
    
    # Mock the server
    mock_server = MagicMock()
    mock_server.start = AsyncMock()
    mock_server.stop = AsyncMock()
    
    mocker.patch('proxybroker.api.Server', return_value=mock_server)
    
    # Start serve task
    serve_task = asyncio.create_task(broker.serve(host='127.0.0.1', port=8888))
    
    # Let it run briefly
    await asyncio.sleep(0.01)
    
    # Cancel the task
    serve_task.cancel()
    
    try:
        await serve_task
    except asyncio.CancelledError:
        pass
    
    # Verify server was created and started
    mock_server.start.assert_called_once()


def test_broker_constants():
    """Test that important constants are defined correctly."""
    assert GRAB_PAUSE == 180
    assert MAX_CONCURRENT_PROVIDERS == 3


@pytest.mark.asyncio
async def test_broker_show_stats(broker, capsys):
    """Test broker show_stats method."""
    # Add some mock stats
    broker._checker._ex_types = {'ProxyTimeoutError': 5, 'ProxyConnError': 3}
    broker._providers = [MagicMock(), MagicMock()]  # 2 providers
    
    await broker.show_stats()
    
    captured = capsys.readouterr()
    assert 'Providers' in captured.out
    assert 'Errors' in captured.out


@pytest.mark.asyncio
async def test_broker_context_manager():
    """Test broker as async context manager."""
    async with Broker(timeout=0.1) as broker:
        assert broker is not None
        assert hasattr(broker, '_resolver')
        assert hasattr(broker, '_checker')


@pytest.mark.asyncio
async def test_broker_stop_on_keyboard_interrupt(broker, mocker):
    """Test broker handles KeyboardInterrupt gracefully."""
    # Mock signal handling
    mock_signal = mocker.patch('proxybroker.api.signal')
    
    # Create broker with signal handling
    broker_with_signal = Broker(timeout=0.1, stop_broker_on_sigint=True)
    
    # Verify signal handler was set
    mock_signal.signal.assert_called()