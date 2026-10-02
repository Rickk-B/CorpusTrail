"""Optional bounded HTTPS transport adapted from the historical metadata transport.

No redirects, no secret-bearing URL parameters, no provider substitution.
"""

from __future__ import annotations

import email.utils
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from corpustrail._internal.values import ContractError


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class HttpTransport(Protocol):
    network: bool
    def request(self, url: str, *, method: str, headers: Mapping[str, str], body: bytes | None) -> HttpResponse: ...


class ProviderTransportError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrlLibTransport:
    network = True

    def __init__(self, *, timeout=30, max_bytes=20_000_000):
        if not 0 < timeout <= 60 or not 0 < max_bytes <= 50_000_000:
            raise ContractError("transport must be bounded")
        self.timeout, self.max_bytes = timeout, max_bytes
        self._opener = urllib.request.build_opener(_NoRedirect())

    def request(self, url, *, method, headers, body):
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                result = HttpResponse(int(response.status), dict(response.headers.items()),
                                      response.read(self.max_bytes + 1), response.geturl())
        except urllib.error.HTTPError as exc:
            result = HttpResponse(int(exc.code), dict(exc.headers.items()),
                                  exc.read(self.max_bytes + 1), exc.geturl())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Never persist an exception containing headers, credentials or arbitrary remote messages.
            raise ProviderTransportError("transport_failed") from exc
        if len(result.body) > self.max_bytes:
            raise ProviderTransportError("response_too_large")
        return result


def safe_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username
            or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
        raise ContractError("request/response URL outside approved HTTPS adapter hosts")


def outcome(status):
    if 200 <= status < 300:
        return "success"
    if status == 404:
        return "not_found"
    if status == 429 or status >= 500:
        return "retryable_error"
    return "permanent_error"


def rate_headers(headers):
    allowed = {"retry-after", "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset",
               "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"}
    return {key.casefold(): str(value) for key, value in headers.items() if key.casefold() in allowed}


def retry_after(headers, *, clock=None):
    value = next((v for k, v in headers.items() if k.casefold() == "retry-after"), None)
    if value is None:
        return None
    if str(value).isdigit():
        return int(value)
    try:
        date = email.utils.parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(0, math.ceil((date - (clock or datetime.now(timezone.utc))).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


def sleep(seconds):
    time.sleep(seconds)
