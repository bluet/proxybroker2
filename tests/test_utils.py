import pytest

from proxybroker.errors import BadStatusLine
from proxybroker.utils import (
    canonicalize_ip,
    get_all_ip,
    get_status_code,
    parse_headers,
    parse_status_line,
    update_geoip_db,
)


def test_update_geoip_db_raises_runtime_error():
    # MaxMind retired the unauthenticated GeoLite2 download endpoint on
    # 2019-12-30. Until a replacement strategy is picked (tracking issue
    # #200), `update-geo` must fail loudly with a pointer to the issue
    # rather than silently NXDOMAIN. Locks in the PR #199 mitigation.
    with pytest.raises(RuntimeError) as excinfo:
        update_geoip_db()
    msg = str(excinfo.value)
    assert "update-geo" in msg
    assert "https://github.com/bluet/proxybroker2/issues/200" in msg


def test_get_all_ip():
    page = "abc127.0.0.1:80abc127.0.0.1xx127.0.0.2:8080h"
    assert get_all_ip(page) == {"127.0.0.1", "127.0.0.2"}


def test_get_all_ip_ipv6_loopback():
    assert "::1" in get_all_ip("real ip is ::1 leak")


def test_get_all_ip_ipv6_documentation_range():
    # RFC 3849 documentation prefix; canonical lowercase per RFC 5952.
    assert "2001:db8::1" in get_all_ip("server: 2001:DB8::1 here")


def test_get_all_ip_ipv6_ipv4_mapped():
    found = get_all_ip("transparent: ::ffff:192.0.2.1 leak")
    # IPv4-mapped form preserved as-is by stdlib canonicalisation.
    assert "::ffff:192.0.2.1" in found
    # The embedded v4 part should also be picked up by the v4 path.
    assert "192.0.2.1" in found


def test_get_all_ip_ipv6_with_zone_id():
    # Link-local addresses include zone IDs (RFC 6874).
    assert "fe80::1%eth0" in get_all_ip("link-local fe80::1%eth0 trailing")


def test_get_all_ip_ipv6_with_port_brackets():
    # Bracketed [v6]:port form is the standard textual notation;
    # the v6 part inside the brackets must still be extracted.
    assert "2001:db8::1" in get_all_ip("contact [2001:db8::1]:8080 here")


def test_get_all_ip_rejects_malformed_ipv4():
    # Out-of-range octets must NOT appear in the set. Note: the existing
    # IPv4 regex over-matches "999.999.999.999" as substrings of valid
    # octets ("99.99.99.99"), so we assert the malformed form is absent
    # rather than asserting the set is empty.
    assert "999.999.999.999" not in get_all_ip("bad: 999.999.999.999 here")


def test_get_all_ip_rejects_random_hex_garbage():
    # "dead.beef.cafe" looks IP-shaped (hex chars + dots) but is not an IP;
    # the v6 path must reject it via stdlib validation, not match it.
    found = get_all_ip("dead.beef.cafe and feed:face::dead in text")
    assert "dead.beef.cafe" not in found
    # but a syntactically valid v6 in the same string IS extracted
    assert "feed:face::dead" in found


def test_get_all_ip_canonicalises_ipv6_for_set_dedup():
    # Two textual forms of the same v6 address must collapse to one
    # element in the set (canonical form contract).
    page = "leak1: 2001:DB8::1 and leak2: 2001:0db8:0000:0000:0000:0000:0000:0001"
    found = get_all_ip(page)
    v6_entries = {ip for ip in found if ":" in ip}
    assert v6_entries == {"2001:db8::1"}


def test_get_all_ip_mixed_prose():
    page = (
        "Headers: X-Real-IP: 203.0.113.7\n"
        "X-Forwarded-For: 198.51.100.10, 2001:db8::42\n"
        "Random text 192.0.2.50:443 trailing"
    )
    found = get_all_ip(page)
    assert {"203.0.113.7", "198.51.100.10", "192.0.2.50", "2001:db8::42"} <= found


def test_get_all_ip_empty_page():
    assert get_all_ip("") == set()
    assert get_all_ip("no IPs in this prose at all") == set()


def test_canonicalize_ip_ipv4_identity():
    assert canonicalize_ip("127.0.0.1") == "127.0.0.1"
    assert canonicalize_ip("203.0.113.7") == "203.0.113.7"


def test_canonicalize_ip_ipv6_lowercase_compressed():
    # RFC 5952: lowercase, leading zeros stripped, longest zero-run as ::
    assert canonicalize_ip("2001:DB8::1") == "2001:db8::1"
    assert canonicalize_ip("2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"


def test_canonicalize_ip_ipv6_zone_id_preserved():
    assert canonicalize_ip("fe80::1%eth0") == "fe80::1%eth0"


def test_canonicalize_ip_invalid_returns_none():
    assert canonicalize_ip("not-an-ip") is None
    assert canonicalize_ip("999.999.999.999") is None
    assert canonicalize_ip("") is None


def test_find_proxy_pairs_ipv4_baseline():
    """Drop-in equivalent for the legacy IPPortPatternGlobal usage."""
    from proxybroker.utils import find_proxy_pairs

    text = "192.0.2.1:8080 trailer 198.51.100.5 9999 mid 203.0.113.10:3128"
    pairs = find_proxy_pairs(text)
    assert ("192.0.2.1", "8080") in pairs
    assert ("203.0.113.10", "3128") in pairs


def test_find_proxy_pairs_ipv6_bracketed():
    """RFC 3986 [v6]:port form must be extracted, with the v6 part
    canonicalized (lowercase, compressed) so downstream comparison
    works regardless of the source feed's encoding choice."""
    from proxybroker.utils import find_proxy_pairs

    text = "Try [2001:DB8::1]:8080 and [fe80::abcd]:1080 for SOCKS"
    pairs = find_proxy_pairs(text)
    assert ("2001:db8::1", "8080") in pairs
    assert ("fe80::abcd", "1080") in pairs


def test_find_proxy_pairs_skips_invalid_brackets():
    """Bracketed garbage that's not a valid v6 must NOT pollute the
    results."""
    from proxybroker.utils import find_proxy_pairs

    text = "[zzz::nope]:8080 and [2001:db8::cafe]:443"
    pairs = find_proxy_pairs(text)
    assert ("2001:db8::cafe", "443") in pairs
    assert all(host != "zzz::nope" for host, _ in pairs)


def test_find_proxy_pairs_mixed_v4_v6():
    """One feed with both v4 and v6 entries -> both extracted."""
    from proxybroker.utils import find_proxy_pairs

    text = "192.0.2.1:8080\n[2001:db8::1]:9090\n198.51.100.5:443\n[fe80::1]:1080"
    pairs = find_proxy_pairs(text)
    assert {("192.0.2.1", "8080"), ("198.51.100.5", "443")} <= set(pairs)
    assert {("2001:db8::1", "9090"), ("fe80::1", "1080")} <= set(pairs)


def test_find_proxy_pairs_ipv6_with_zone_id():
    """RFC 6874 zone IDs in bracketed v6 proxies must be accepted.

    Without this, link-local proxies (fe80::1%eth0) silently never
    parse, even though canonicalize_ip and Resolver.host_is_ip both
    accept the form.
    """
    from proxybroker.utils import find_proxy_pairs

    pairs = find_proxy_pairs("Try [fe80::1%eth0]:8080 for SOCKS")
    assert ("fe80::1%eth0", "8080") in pairs


def test_get_all_ip_strips_trailing_punctuation():
    """A v6 literal at the end of a sentence (e.g., `Real IP: ::1.`)
    should still parse - the tokenizer greedily includes trailing dots
    but they must not break canonicalize_ip validation.
    """
    found = get_all_ip("Server says: 2001:db8::1. Cool!")
    assert "2001:db8::1" in found


def test_get_status_code():
    assert get_status_code("HTTP/1.1 200 OK\r\n") == 200
    assert get_status_code("<html>123</html>\r\n") == 400
    assert get_status_code(b"HTTP/1.1 403 Forbidden\r\n") == 403
    assert get_status_code(b"HTTP/1.1 400 Bad Request\r\n") == 400


def test_parse_status_line():
    assert parse_status_line("HTTP/1.1 200 OK") == {
        "Version": "HTTP/1.1",
        "Status": 200,
        "Reason": "OK",
    }
    assert parse_status_line("HTTP/1.1 404 NOT FOUND") == {
        "Version": "HTTP/1.1",
        "Status": 404,
        "Reason": "Not Found",
    }
    assert parse_status_line("GET / HTTP/1.1") == {
        "Version": "HTTP/1.1",
        "Method": "GET",
        "Path": "/",
    }
    with pytest.raises(BadStatusLine):
        parse_status_line("<!DOCTYPE html ")


def test_parse_headers():
    req = (
        b"GET /go HTTP/1.1\r\nContent-Length: 0\r\nAccept-Encoding: "
        b"gzip, deflate\r\nHost: host.com\r\nConnection: close\r\n\r\n"
    )
    hdrs = {
        "Method": "GET",
        "Version": "HTTP/1.1",
        "Path": "/go",
        "Content-Length": "0",
        "Host": "host.com",
        "Connection": "close",
        "Accept-Encoding": "gzip, deflate",
    }
    assert parse_headers(req) == hdrs
    resp = (
        b"HTTP/1.1 200 OK\r\nContent-Length: 1133\r\nConnection: close"
        b"\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n"
    )
    hdrs = {
        "Version": "HTTP/1.1",
        "Status": 200,
        "Reason": "OK",
        "Content-Length": "1133",
        "Connection": "close",
        "Content-Type": "text/html; charset=UTF-8",
    }
    assert parse_headers(resp) == hdrs
