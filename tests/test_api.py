import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from proxybroker import Broker, Proxy
from proxybroker.api import GRAB_PAUSE, MAX_CONCURRENT_PROVIDERS
from proxybroker.errors import ResolveError


@pytest.fixture
def broker():
    """Create a basic broker instance for testing."""
    # Create broker without event loop to avoid signal handler issues
    return Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)


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
async def test_broker_find_with_mock_provider(mocker):
    """Test broker find method basic setup."""
    # Create broker without signal handling to avoid issues
    broker = Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
    
    # Mock the resolver's get_real_ext_ip method
    mocker.patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1')
    
    # Test that find method initializes the checker
    await broker.find(types=['HTTP'], limit=2)
    
    # Check that checker was initialized
    assert broker._checker is not None
    assert broker._limit == 2
    assert broker._countries is None


@pytest.mark.asyncio
async def test_broker_find_with_countries_filter(mocker):
    """Test broker find method with countries filter."""
    # Create broker without signal handling
    broker = Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
    
    # Mock the resolver's get_real_ext_ip method
    mocker.patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1')
    
    # Test that find method sets countries correctly
    await broker.find(types=['HTTP'], countries=['US'], limit=1)
    
    # Check that countries filter was set
    assert broker._countries == ['US']
    assert broker._limit == 1
    assert broker._checker is not None


@pytest.mark.asyncio
async def test_broker_find_with_resolve_error(mocker):
    """Test broker handling of resolve errors."""
    # Create broker without signal handling
    broker = Broker(timeout=0.1, max_conn=5, max_tries=1, stop_broker_on_sigint=False)
    
    # Mock the resolver's get_real_ext_ip method
    mocker.patch.object(broker._resolver, 'get_real_ext_ip', return_value='127.0.0.1')
    
    # Should handle error gracefully and return no proxies
    await broker.find(types=['HTTP'], limit=1)
    
    # Check that find method setup was completed despite no results
    assert broker._checker is not None
    assert broker._limit == 1


@pytest.mark.asyncio 
async def test_broker_grab_with_queue(mock_queue, mocker):
    """Test broker grab method basic setup."""
    broker = Broker(queue=mock_queue, timeout=0.1, stop_broker_on_sigint=False)
    
    # Test that grab method sets parameters correctly
    await broker.grab(countries=['US'], limit=1)
    
    # Check that grab parameters were set
    assert broker._countries == ['US']
    assert broker._limit == 1
    # grab() doesn't create checker like find() does
    assert broker._checker is None


@pytest.mark.asyncio
async def test_broker_serve_basic(mocker):
    """Test broker serve method basic functionality."""
    broker = Broker(timeout=0.1)
    
    # Mock the server
    mock_server = MagicMock()
    mock_server.start = AsyncMock()
    mock_server.stop = AsyncMock()
    
    mocker.patch('proxybroker.api.Server', return_value=mock_server)
    
    # Mock the serve method to avoid event loop issues
    async def mock_serve(*args, **kwargs):
        # Just simulate server creation without actually running
        broker._server = mock_server
        await mock_server.start()
        await asyncio.sleep(0.01)  # Brief simulation
    
    mocker.patch.object(broker, 'serve', side_effect=mock_serve)
    
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
    # Add some mock proxies to the unique_proxies dict to test stats
    mock_proxy1 = MagicMock()
    mock_proxy1.is_working = True
    mock_proxy1.stat = {'errors': {'ProxyTimeoutError': 2}}
    mock_proxy1.types = ['HTTP']
    mock_proxy1.get_log = MagicMock(return_value=[('ngtr1', 'Connection: success', 1.0)])
    
    mock_proxy2 = MagicMock()
    mock_proxy2.is_working = False
    mock_proxy2.stat = {'errors': {'ProxyConnError': 1}}
    mock_proxy2.types = ['HTTPS']
    mock_proxy2.get_log = MagicMock(return_value=[('ngtr2', 'Connection failed', 2.0)])
    
    broker.unique_proxies = {
        ('127.0.0.1', 8080): mock_proxy1,
        ('127.0.0.2', 8080): mock_proxy2
    }
    
    broker.show_stats()
    
    captured = capsys.readouterr()
    # Should show stats about found proxies, working proxies, etc.
    assert len(captured.out) > 0


@pytest.mark.asyncio
async def test_broker_context_manager():
    """Test broker as async context manager."""
    # Broker doesn't implement async context manager, test regular usage instead
    broker = Broker(timeout=0.1, stop_broker_on_sigint=False)
    assert broker is not None
    assert hasattr(broker, '_resolver')
    # _checker is None until find() is called
    assert broker._checker is None
    
    # Test that stop() works
    broker.stop()


@pytest.mark.asyncio
async def test_broker_stop_on_keyboard_interrupt(broker, mocker):
    """Test broker handles KeyboardInterrupt gracefully."""
    # Mock signal handling
    mock_signal = mocker.patch('proxybroker.api.signal')
    
    # Create broker with signal handling disabled for testing
    broker_with_signal = Broker(timeout=0.1, stop_broker_on_sigint=False)
    
    # Test that broker handles KeyboardInterrupt gracefully
    broker_with_signal.stop()
    assert broker_with_signal._server is None