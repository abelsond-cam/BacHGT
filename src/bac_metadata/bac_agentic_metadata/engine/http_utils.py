"""Shared polite HTTP client for the engine (retry/backoff GET).

Generalises the retry/backoff pattern first written for ``ena_sizing._ena_search`` so the
later network layers — ``fulltext`` (Europe PMC), ``europepmc``, and the extended ``ena_sizing``
study-description query — reuse one well-behaved client instead of each re-implementing it.

A single :func:`get` retries on transient failures (HTTP 429 / 5xx and connection errors) with a
linear backoff, and gives up after :data:`RETRY_MAX` attempts. It returns the
:class:`requests.Response` on success (status 200) so callers can read ``.text``, ``.content`` or
``.json()`` as needed; on definitive failure it returns ``None``.
"""

from __future__ import annotations

import sys
import time

import requests

RETRY_MAX = 3
RETRY_PAUSE = 10  # seconds; multiplied by the attempt number for a linear backoff
#: Status codes worth retrying — rate limiting and transient server-side errors.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 120,
    retry_max: int = RETRY_MAX,
    retry_pause: int = RETRY_PAUSE,
) -> requests.Response | None:
    """Run one GET with retry/backoff; return the 200 response or ``None``.

    Parameters
    ----------
    url
        Target URL.
    params
        Optional query parameters.
    headers
        Optional request headers (e.g. an ``Accept`` content negotiation).
    timeout
        Per-request timeout in seconds.
    retry_max
        Maximum number of attempts before giving up.
    retry_pause
        Base backoff in seconds; the wait is ``retry_pause * (attempt + 1)``.

    Returns
    -------
    requests.Response | None
        The response on HTTP 200, else ``None`` after exhausting retries or on a
        non-retryable status.
    """
    label = url if params is None else f"{url}?{params}"
    for attempt in range(retry_max):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in RETRYABLE_STATUS:
                wait = retry_pause * (attempt + 1)
                print(f"    [HTTP {resp.status_code}] retrying in {wait}s ...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"    [HTTP {resp.status_code}] {label} — giving up", file=sys.stderr)
                return None
        except requests.RequestException as exc:
            print(f"    [request error] {exc}", file=sys.stderr)
            time.sleep(retry_pause // 2 or 1)
    print(f"    [failed after {retry_max} retries] {label}", file=sys.stderr)
    return None
