import codecs
import re

from setuptools import setup

# https://packaging.python.org/en/latest/distributing/


# Modern version management: Single source of truth in pyproject.toml
def get_version():
    """Get version from pyproject.toml."""
    try:
        with codecs.open("pyproject.toml", mode="r", encoding="utf-8") as f:
            content = f.read()
            # Match both [tool.poetry] and [project] sections
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
    except FileNotFoundError:
        pass
    raise RuntimeError("Unable to find version in pyproject.toml")


# Get metadata from __init__.py (everything except version)
with codecs.open("proxybroker/__init__.py", mode="r", encoding="utf-8") as f:
    content = f.read()
    INFO = dict(re.findall(r"__(\w+)__ = ['\"]([^'\"]+)['\"]", content, re.MULTILINE))

# Get version from pyproject.toml (single source of truth)
INFO["version"] = get_version()

with codecs.open("README.md", mode="r", encoding="utf-8") as f:
    INFO["long_description"] = f.read()

REQUIRES = [
    "aiohttp>=3.12.0",
    "aiodns>=3.4.0",
    "attrs>=25.3.0",
    "maxminddb>=2.7.0",
    "cachetools>=5.5.2",
    "click>=8.2.1",
]
SETUP_REQUIRES = ["pytest-runner>=6.0.1"]
TEST_REQUIRES = [
    "pytest>=8.3.5",
    "pytest-asyncio>=0.26.0",
    "pytest-runner>=6.0.1",
    "pytest-mock>=3.14.0",
    "pytest-cov>=6.1.1",
]
PACKAGES = ["proxybroker", "proxybroker.data"]
PACKAGE_DATA = {"": ["LICENSE"], INFO["package"]: ["data/*.mmdb"]}

setup(
    name=INFO["package"],
    version=INFO["version"],
    description=INFO["short_description"],
    long_description=INFO["long_description"],
    author=INFO["author"],
    author_email=INFO["author_email"],
    license=INFO["license"],
    url=INFO["url"],
    install_requires=REQUIRES,
    setup_requires=SETUP_REQUIRES,
    tests_require=TEST_REQUIRES,
    packages=PACKAGES,
    package_data=PACKAGE_DATA,
    platforms="any",
    python_requires=">=3.10",
    entry_points={"console_scripts": ["proxybroker = proxybroker.cli:cli"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: POSIX",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Internet :: WWW/HTTP :: Indexing/Search",
        "Topic :: Internet :: Proxy Servers",
        "License :: OSI Approved :: Apache Software License",
    ],
    keywords=(
        "proxy finder grabber scraper parser graber scrapper checker "
        "broker async asynchronous http https connect socks socks4 socks5"
    ),
    zip_safe=False,
    test_suite="tests",
)
