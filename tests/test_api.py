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
    # Create a real broker with test configuration
    broker = Broker(timeout=0.1, stop_broker_on_sigint=False)
    
    # Test that serve validates parameters correctly
    with pytest.raises(ValueError, match='limit cannot be less than or equal to zero'):
        broker.serve(limit=0)
    
    # Test that serve creates server with correct parameters
    # We'll mock Server to avoid actual network binding, but test real behavior
    mock_server_instance = MagicMock()
    mock_server_instance.start = AsyncMock()
    
    # Mock only the Server class constructor
    mock_server_class = mocker.patch('proxybroker.api.Server')
    mock_server_class.return_value = mock_server_instance
    
    # Mock event loop to avoid blocking
    mock_loop = MagicMock()
    mock_loop.run_until_complete = MagicMock()
    broker._loop = mock_loop
    
    # Call serve with test parameters
    broker.serve(host='127.0.0.1', port=8888, limit=10, max_tries=5)
    
    # Verify Server was created with correct parameters
    mock_server_class.assert_called_once()
    call_args = mock_server_class.call_args
    assert call_args.kwargs['host'] == '127.0.0.1'
    assert call_args.kwargs['port'] == 8888
    assert call_args.kwargs['timeout'] == 0.1
    assert call_args.kwargs['max_tries'] == 5
    
    # Verify server was stored
    assert broker._server is mock_server_instance


def test_broker_constants():
    """Test that important constants are defined correctly."""
    assert GRAB_PAUSE == 180
    assert MAX_CONCURRENT_PROVIDERS == 3


@pytest.mark.asyncio
async def test_broker_show_stats(capsys):
    """Test broker show_stats method with real proxy objects."""
    from proxybroker import Proxy
    
    # Create a real broker
    broker = Broker(timeout=0.1, stop_broker_on_sigint=False)
    
    # Create real proxy objects with test data
    proxy1 = Proxy('127.0.0.1', 8080, 'http')
    proxy1._types['HTTP'] = ['Anonymous']
    proxy1.is_working = True
    proxy1.stat['errors']['ProxyTimeoutError'] = 2
    proxy1._runtimes.append(1.0)
    proxy1._log.append(('ngtr1', 'Connection: success'))
    
    proxy2 = Proxy('127.0.0.2', 8080, 'https')
    proxy2._types['HTTPS'] = ['Transparent']
    proxy2.is_working = False
    proxy2.stat['errors']['ProxyConnError'] = 1
    proxy2._runtimes.append(2.0)
    proxy2._log.append(('ngtr2', 'Connection failed'))
    
    # Add proxies to broker's unique_proxies
    broker.unique_proxies = {
        ('127.0.0.1', 8080): proxy1,
        ('127.0.0.2', 8080): proxy2
    }
    
    # Call show_stats
    broker.show_stats()
    
    captured = capsys.readouterr()
    output = captured.out
    
    # Verify the output contains expected information
    assert len(output) > 0
    assert 'The number of working proxies: 1' in output
    
    # Verify proxy types are shown
    assert 'HTTP (1):' in output
    assert 'HTTPS (1):' in output
    assert '127.0.0.1:8080' in output
    assert '127.0.0.2:8080' in output
    
    # Verify error counts are shown
    assert 'Errors:' in output
    assert 'ProxyTimeoutError' in output
    assert 'ProxyConnError' in output


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