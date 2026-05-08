"""Behaviour tests for the Provider base class.

These tests exercise Provider in isolation without any network calls.
The 50+ concrete provider subclasses share this base, so coverage here
flows through the whole providers module.
"""

import pytest

from proxybroker.providers import Provider


class TestProviderConstruction:
    def test_url_extraction_sets_domain(self):
        p = Provider(url="http://www.example.com/proxylist")
        assert p.domain == "www.example.com"
        assert p.url == "http://www.example.com/proxylist"

    def test_no_url_omits_domain_attribute(self):
        # Provider must not crash when constructed without a url
        # (some discovery paths set the url later).
        p = Provider()
        assert p.url is None
        assert not hasattr(p, "domain") or p.domain is not None

    def test_default_proto_is_empty_tuple(self):
        p = Provider(url="http://example.com")
        assert p.proto == ()

    def test_custom_proto_preserved(self):
        p = Provider(url="http://example.com", proto=("HTTP", "HTTPS"))
        assert p.proto == ("HTTP", "HTTPS")

    def test_initial_proxies_is_empty_set(self):
        p = Provider(url="http://example.com")
        assert p.proxies == set()


class TestProviderProxiesSetter:
    """Provider.proxies setter is the contract every subclass relies on."""

    def test_setter_filters_empty_ports(self):
        """Items with an empty port string must be dropped."""
        p = Provider(url="http://example.com", proto=("HTTP",))
        p.proxies = [("192.0.2.1", "8080"), ("198.51.100.1", "")]
        # Only the entry with a real port should land
        assert any(item[0] == "192.0.2.1" for item in p.proxies)
        assert all(item[0] != "198.51.100.1" for item in p.proxies)

    def test_setter_attaches_proto_tuple(self):
        """Each stored entry is (host, port, proto-tuple)."""
        p = Provider(url="http://example.com", proto=("HTTP", "HTTPS"))
        p.proxies = [("192.0.2.1", "8080")]
        entry = next(iter(p.proxies))
        assert entry == ("192.0.2.1", "8080", ("HTTP", "HTTPS"))

    def test_setter_dedupes_via_set(self):
        """Adding the same (host, port) twice must store one entry."""
        p = Provider(url="http://example.com", proto=("HTTP",))
        p.proxies = [("192.0.2.1", "8080"), ("192.0.2.1", "8080")]
        assert len(p.proxies) == 1

    def test_setter_appends_across_calls(self):
        """Subsequent assignments add to (not replace) the proxy set."""
        p = Provider(url="http://example.com", proto=("HTTP",))
        p.proxies = [("192.0.2.1", "8080")]
        p.proxies = [("198.51.100.1", "3128")]
        hosts = {entry[0] for entry in p.proxies}
        assert hosts == {"192.0.2.1", "198.51.100.1"}


class TestProviderFindProxies:
    """find_proxies() / _find_proxies() use the global IP:port regex."""

    def test_finds_ip_port_pairs_in_arbitrary_text(self):
        """The regex pattern works on raw HTML scraped from provider sites."""
        page = """
        <html><body>
        <table>
          <tr><td>192.0.2.1:8080</td></tr>
          <tr><td>198.51.100.1:3128</td></tr>
          <tr><td>not-a-proxy</td></tr>
        </table>
        </body></html>
        """
        p = Provider(url="http://example.com")
        results = p.find_proxies(page)
        assert ("192.0.2.1", "8080") in results
        assert ("198.51.100.1", "3128") in results

    def test_empty_page_returns_empty(self):
        p = Provider(url="http://example.com")
        assert p.find_proxies("") == []

    def test_page_with_no_proxies_returns_empty(self):
        p = Provider(url="http://example.com")
        assert p.find_proxies("just some prose without any proxies") == []


@pytest.mark.asyncio
async def test_find_on_pages_handles_empty_url_list():
    """Edge case: callers occasionally hand _find_on_pages an empty list."""
    p = Provider(url="http://example.com")
    # Should return cleanly without raising or scheduling tasks.
    await p._find_on_pages([])
    assert p.proxies == set()
