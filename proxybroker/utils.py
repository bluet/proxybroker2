"""Utils."""

import ipaddress
import logging
import os
import os.path
import re
import secrets
import sys

from . import __version__ as version
from .errors import BadStatusLine

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
log = logging.getLogger(__package__)

IPPattern = re.compile(
    r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
)

# Narrow IPv6 candidate tokenizer: a run of hex/colon/dot/percent chars,
# anchored to start at a hex digit or colon (so `::1` is matched). Zero
# alternation, zero nesting - provably ReDoS-free. Validation is
# delegated to stdlib `ipaddress.ip_address` instead of a regex grammar.
_IPV6_CANDIDATE_PATTERN = re.compile(
    r"[0-9A-Fa-f:][0-9A-Fa-f:.]*(?:%[A-Za-z0-9_.\-]+)?"
)

IPPortPatternLine = re.compile(
    r"^.*?(?P<ip>(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)).*?(?P<port>\d{2,5}).*$",  # noqa
    flags=re.MULTILINE,
)

IPPortPatternGlobal = re.compile(
    r"(?P<ip>(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))"  # noqa
    r"(?=.*?(?:(?:(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?))|(?P<port>\d{2,5})))",  # noqa
    flags=re.DOTALL,
)

# Bracketed IPv6 + port: `[v6]:port`. RFC 3986 § 3.2.2 mandates this
# form for IPv6 in URI authority components and most public proxy
# feeds use it. The capture group is intentionally permissive (any
# hex/colon/dot/percent characters inside brackets) - validation is
# performed by `canonicalize_ip` afterwards, not by the regex grammar.
# Provably ReDoS-free (no alternation, no nested quantifiers).
# Bracketed [v6]:port. Char class includes alphanumeric+`_`+`-` to
# accept link-local zone IDs (e.g., `[fe80::1%eth0]:8080`); validation
# done by `canonicalize_ip` afterwards, not the regex grammar.
IPv6BracketedPortPattern = re.compile(r"\[([0-9A-Za-z:.%_\-]+)\]:(\d{2,5})")


def get_headers(rv=False):
    # secrets.randbelow (CSPRNG) clears SonarCloud S2245. Used as a request
    # marker to detect proxy header injection - non-cryptographic role, but
    # secrets is a drop-in for the small-int range.
    _rv = str(1000 + secrets.randbelow(9000)) if rv else ""
    headers = {
        "User-Agent": f"PxBroker/{version}/{_rv}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Pragma": "no-cache",
        "Cache-control": "no-cache",
        "Cookie": "cookie=ok",
        "Referer": "https://www.google.com/",
    }
    return headers if not rv else (headers, _rv)


def canonicalize_ip(s: str | None) -> str | None:
    """Return RFC 5952 canonical textual form of `s`, or None if invalid.

    For IPv4 the canonical form equals the input (identity). For IPv6 the
    canonical form is lowercase, leading zeros stripped, and the longest
    zero-run replaced with `::`. Zone IDs (RFC 6874, e.g. `fe80::1%eth0`)
    are preserved.

    Adopt the canonical form whenever IP strings cross a boundary where
    set-membership or substring comparison happens (e.g. anonymity-leak
    detection). Two textually different but semantically equal addresses
    must compare equal.
    """
    try:
        return str(ipaddress.ip_address(s))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def find_proxy_pairs(text: str) -> list[tuple[str, str]]:
    """Extract `(ip, port)` proxy pairs from arbitrary text.

    Returns a list of `(ip_canonical, port)` tuples. Both IPv4 and IPv6
    are canonicalised via stdlib `ipaddress` so callers get one
    consistent textual form regardless of how the source feed encoded
    the address (case, leading zeros, `::` placement). IPv4 canonical
    form equals the input, so legacy v4-only feeds see no behavior
    change.

    Bracketed v6 entries (`[v6]:port`, RFC 3986) and bare v4 entries
    are both recognised. Invalid bracketed garbage is silently
    dropped.
    """
    pairs: list[tuple[str, str]] = []
    for raw_v4, port in IPPortPatternGlobal.findall(text):
        canonical = canonicalize_ip(raw_v4)
        if canonical is not None:
            pairs.append((canonical, port))
    for raw_v6, port in IPv6BracketedPortPattern.findall(text):
        canonical = canonicalize_ip(raw_v6)
        if canonical is not None:
            pairs.append((canonical, port))
    return pairs


def get_all_ip(page: str) -> set[str]:
    """Extract all IPv4 and IPv6 literals from `page`.

    IPv4 addresses are extracted greedily as substrings (so
    `"127.0.0.1"` is found inside `"127.0.0.1:80"`), preserving the
    historical IPv4 contract. IPv6 candidates are validated by stdlib
    `ipaddress.ip_address` and returned in RFC 5952 canonical form so
    that different textual encodings of the same address (case,
    leading zeros, `::` placement) collapse to one set element.
    """
    found: set[str] = set(IPPattern.findall(page))
    for tok in _IPV6_CANDIDATE_PATTERN.findall(page):
        if ":" not in tok:
            # Pure IPv4 token (no colon) - already covered by IPPattern.
            continue
        # Strip trailing punctuation that the tokenizer greedily includes
        # (e.g., "Real IP: 2001:db8::1." would otherwise fail validation
        # silently). Leading dots are not allowed by IPv6 grammar so no
        # left strip needed.
        canonical = canonicalize_ip(tok.rstrip("."))
        if canonical is not None:
            found.add(canonical)
    return found


def get_status_code(resp, start=9, stop=12):
    try:
        if not isinstance(resp, (bytes, str)):
            raise TypeError(f"{type(resp).__name__} is not supported")
        code = int(resp[start:stop])
    except ValueError:
        return 400  # Bad Request
    else:
        return code


def parse_status_line(line):
    _headers = {}
    is_response = line.startswith("HTTP/")
    try:
        if is_response:  # HTTP/1.1 200 OK
            version, status, *reason = line.split()
        else:  # GET / HTTP/1.1
            method, path, version = line.split()
    except ValueError as e:
        raise BadStatusLine(line) from e

    _headers["Version"] = version.upper()
    if is_response:
        _headers["Status"] = int(status)
        reason = " ".join(reason)
        reason = reason.upper() if reason.lower() == "ok" else reason.title()
        _headers["Reason"] = reason
    else:
        _headers["Method"] = method.upper()
        _headers["Path"] = path
        if _headers["Method"] == "CONNECT":
            host, port = path.split(":")
            _headers["Host"], _headers["Port"] = host, int(port)
    return _headers


def parse_headers(headers):
    headers = headers.decode("utf-8", "ignore").split("\r\n")
    _headers = {}
    _headers.update(parse_status_line(headers.pop(0)))

    for h in headers:
        if not h:
            break
        name, val = h.split(":", 1)
        _headers[name.strip().title()] = val.strip()

    if ":" in _headers.get("Host", ""):
        host, port = _headers["Host"].split(":")
        _headers["Host"], _headers["Port"] = host, int(port)
    return _headers


def update_geoip_db():
    raise RuntimeError(
        "`proxybroker update-geo` is no longer functional. MaxMind retired "
        "the public GeoLite2 download endpoint on 2019-12-30 and now requires "
        "a license key. The bundled GeoLite2 databases in proxybroker/data/ "
        "still work for runtime IP lookups, but cannot be refreshed via this "
        "command. Tracking issue: "
        "https://github.com/bluet/proxybroker2/issues/200"
    )
