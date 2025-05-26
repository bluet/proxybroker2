
User Guide - Essential API
===========================

This guide covers the most commonly used API methods. For complete technical reference, see :doc:`api_auto`.

.. _proxybroker-api-broker:

Broker - Main Interface
-----------------------

.. autoclass:: proxybroker.api.Broker
    :members: grab, find, serve, stop, show_stats
    :exclude-members: __init__


.. _proxybroker-api-proxy:

Proxy - Proxy Objects
---------------------

.. autoclass:: proxybroker.proxy.Proxy
    :members: create, types, is_working, avg_resp_time, geo, error_rate, get_log
    :member-order: groupwise
    :exclude-members: __init__


.. _proxybroker-api-provider:

Provider - Data Sources
-----------------------

.. autoclass:: proxybroker.providers.Provider
    :members: proxies, get_proxies
    :member-order: groupwise
    :exclude-members: __init__
