"""Utils."""

import logging
import os
import os.path
import random
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request

from . import __version__ as version
from .errors import BadStatusLine

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
log = logging.getLogger(__package__)

IPPattern = re.compile(
    r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
)

IPv6Pattern = re.compile(
    r"\s*((([0-9A-Fa-f]{1,4}:){7}([0-9A-Fa-f]{1,4}|:))|(([0-9A-Fa-f]{1,4}:){6}(:[0-9A-Fa-f]{1,4}|((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){5}(((:[0-9A-Fa-f]{1,4}){1,2})|:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})|:))|(([0-9A-Fa-f]{1,4}:){4}(((:[0-9A-Fa-f]{1,4}){1,3})|((:[0-9A-Fa-f]{1,4})?:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){3}(((:[0-9A-Fa-f]{1,4}){1,4})|((:[0-9A-Fa-f]{1,4}){0,2}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){2}(((:[0-9A-Fa-f]{1,4}){1,5})|((:[0-9A-Fa-f]{1,4}){0,3}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(([0-9A-Fa-f]{1,4}:){1}(((:[0-9A-Fa-f]{1,4}){1,6})|((:[0-9A-Fa-f]{1,4}){0,4}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:))|(:(((:[0-9A-Fa-f]{1,4}){1,7})|((:[0-9A-Fa-f]{1,4}){0,5}:((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}))|:)))(%.+)?\s*"
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


def get_headers(rv=False):
    _rv = str(random.randint(1000, 9999)) if rv else ""
    headers = {
        "User-Agent": "PxBroker/%s/%s" % (version, _rv),
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Pragma": "no-cache",
        "Cache-control": "no-cache",
        "Cookie": "cookie=ok",
        "Referer": "https://www.google.com/",
    }
    return headers if not rv else (headers, _rv)


def get_all_ip(page):
    # NOTE: IPv6 addresses support need to be tested
    return set(IPPattern.findall(page) + IPv6Pattern.findall(page))


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
    print("The update in progress, please waite for a while...")
    filename = "GeoLite2-City.tar.gz"
    local_file = os.path.join(DATA_DIR, filename)
    city_db = os.path.join(DATA_DIR, "GeoLite2-City.mmdb")
    url = "http://geolite.maxmind.com/download/geoip/database/%s" % filename

    urllib.request.urlretrieve(url, local_file)

    tmp_dir = tempfile.gettempdir()
    with tarfile.open(name=local_file, mode="r:gz") as tf:
        for tar_info in tf.getmembers():
            if tar_info.name.endswith(".mmdb"):
                tf.extract(tar_info, tmp_dir)
                tmp_path = os.path.join(tmp_dir, tar_info.name)
    shutil.move(tmp_path, city_db)
    os.remove(local_file)

    if os.path.exists(city_db):
        print(
            "The GeoLite2-City DB successfully downloaded and now you "
            "have access to detailed geolocation information of the proxy."
        )
    else:
        print("Something went wrong, please try again later.")
