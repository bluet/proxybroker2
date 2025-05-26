"""
Copyright © 2015-2018 Constverum <constverum@gmail.com>.
Copyright © 2018-2025 BlueT - Matthew Lien - 練喆明 <bluet@bluet.org>.
All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

__title__ = "ProxyBroker"
__package__ = "proxybroker"
# Version management: Single source of truth in pyproject.toml
import os

# Check if we're in development mode by looking for pyproject.toml
_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_pyproject_path = os.path.join(_root_path, "pyproject.toml")

if os.path.exists(_pyproject_path):
    # Development environment - prioritize pyproject.toml
    import re

    with open(_pyproject_path, encoding="utf-8") as _f:
        _content = _f.read()
        _match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', _content)
        __version__ = _match.group(1) if _match else "unknown"
else:
    # Installed package - use importlib.metadata
    try:
        from importlib.metadata import version

        __version__ = version("proxybroker")
    except ImportError:
        # Python < 3.8 fallback
        try:
            from importlib_metadata import version

            __version__ = version("proxybroker")
        except ImportError:
            __version__ = "unknown"
__short_description__ = "[Finder/Checker/Server] Finds public proxies from multiple sources and concurrently checks them. Supports HTTP(S) and SOCKS4/5."  # noqa
__author__ = "BlueT - Matthew Lien - 練喆明"
__author_email__ = "bluet@bluet.org"
__url__ = "https://github.com/bluet/proxybroker2"
__license__ = "Apache License, Version 2.0"
__copyright__ = (
    "Copyright 2015-2018 Constverum, 2018-2025 BlueT - Matthew Lien - 練喆明"
)


import logging  # noqa
import warnings  # noqa

from .api import Broker  # noqa
from .checker import Checker  # noqa
from .judge import Judge  # noqa
from .providers import Provider  # noqa
from .proxy import Proxy  # noqa
from .server import ProxyPool, Server  # noqa

logger = logging.getLogger("asyncio")
logger.addFilter(logging.Filter("has no effect when using ssl"))

warnings.simplefilter("always", UserWarning)
warnings.simplefilter("once", DeprecationWarning)


__all__ = (Proxy, Judge, Provider, Checker, Server, ProxyPool, Broker)
