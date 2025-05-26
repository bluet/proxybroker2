.. proxybroker documentation master file, created by
   sphinx-quickstart on Thu May 26 13:04:40 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

ProxyBroker2
============

[Finder | Checker | Server]

.. image:: https://img.shields.io/github/v/release/bluet/proxybroker2.svg?style=flat-square
    :target: https://github.com/bluet/proxybroker2/releases
.. image:: https://img.shields.io/github/actions/workflow/status/bluet/proxybroker2/python-test-versions.yml?style=flat-square
    :target: https://github.com/bluet/proxybroker2/actions
.. image:: https://img.shields.io/badge/python-3.10--3.13-blue.svg?style=flat-square
    :target: https://github.com/bluet/proxybroker2
.. image:: https://img.shields.io/github/license/bluet/proxybroker2.svg?style=flat-square
    :target: https://github.com/bluet/proxybroker2/blob/master/LICENSE

ProxyBroker2 is an async proxy finder, checker, and server that discovers public proxies from 50+ sources, validates them against judge servers, and can operate as a rotating proxy server.

.. image:: _static/index_find_example.gif


Features
--------

* Finds more than 7000 working proxies from ~50 sources.
* Support protocols: HTTP(S), SOCKS4/5. Also CONNECT method to ports 80 and 23 (SMTP).
* Proxies may be filtered by type, anonymity level, response time, country and status in DNSBL.
* Work as a proxy server that distributes incoming requests to external proxies. With automatic proxy rotation.
* All proxies are checked to support Cookies and Referer (and POST requests if required).
* Automatically removes duplicate proxies.
* Is asynchronous.


Requirements
------------

* Python **3.10** or higher
* `aiohttp <https://pypi.python.org/pypi/aiohttp>`_ >= 3.8.0
* `aiodns <https://pypi.python.org/pypi/aiodns>`_ >= 3.0.0
* `maxminddb <https://pypi.python.org/pypi/maxminddb>`_ >= 2.0.0


Installation
------------

Install from GitHub (recommended for latest features):

.. code-block:: bash

    $ pip install git+https://github.com/bluet/proxybroker2.git

Or clone and install locally:

.. code-block:: bash

    $ git clone https://github.com/bluet/proxybroker2.git
    $ cd proxybroker2
    $ pip install -e .


Usage
-----


CLI Examples
~~~~~~~~~~~~


Find
""""

Find and show 10 HTTP(S) proxies from United States with the high level of anonymity:

.. code-block:: bash

    $ python -m proxybroker find --types HTTP HTTPS --lvl High --countries US --strict -l 10

.. image:: _static/cli_find_example.gif


Grab
""""

Find and save to a file 10 US proxies (without a check):

.. code-block:: bash

    $ python -m proxybroker grab --countries US --limit 10 --outfile ./proxies.txt

.. image:: _static/cli_grab_example.gif


Serve
"""""

Run a local proxy server that distributes incoming requests to a pool
of found HTTP(S) proxies with the high level of anonymity:

.. code-block:: bash

    $ python -m proxybroker serve --host 127.0.0.1 --port 8888 --types HTTP HTTPS --lvl High


.. image:: _static/cli_serve_example.gif

.. note::

    Run ``python -m proxybroker --help`` for more information on the options available.

    Run ``python -m proxybroker <command> --help`` for more information on a command.


Basic code example
~~~~~~~~~~~~~~~~~~

Find and show 10 working HTTP(S) proxies:

.. literalinclude:: ../../examples/basic.py
    :lines: 3-

:doc:`More examples <examples>`.


TODO
----

* Check the ping, response time and speed of data transfer
* Check site access (Google, Twitter, etc) and even your own custom URL's
* Information about uptime
* Checksum of data returned
* Support for proxy authentication
* Finding outgoing IP for cascading proxy
* The ability to specify the address of the proxy without port (try to connect on defaulted ports)


Contributing
------------

* Fork it: https://github.com/bluet/proxybroker2/fork
* Create your feature branch: git checkout -b my-new-feature
* Commit your changes: git commit -am 'Add some feature'
* Push to the branch: git push origin my-new-feature
* Submit a pull request!


License
-------

Licensed under the Apache License, Version 2.0

*This product includes GeoLite2 data created by MaxMind, available from* `http://www.maxmind.com <http://www.maxmind.com>`_.



Contents:

.. toctree::

   api
   api_auto
   examples
   changelog.md


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
