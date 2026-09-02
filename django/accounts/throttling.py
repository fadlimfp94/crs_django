"""
IP-keyed rate limiting for the web login form.

DRF's ``ScopedRateThrottle`` already protects the token-auth endpoint
(``api/views.py``); the session-based login view has no DRF machinery to hang
a throttle off, so this reuses the same "auth" rate from
``REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`` (settings/base.py) via Django's own
cache framework rather than adding a rate-limiting dependency for one view.

Only *failed* attempts count against the limit — a burst of legitimate,
successful logins from one IP (a shared office NAT, or a test suite) must
never be locked out; the point is slowing down credential stuffing, which is
characterised by repeated failures, not by successful logins.

``LocMemCache`` (the default when no ``CACHES`` setting is configured) is
per-process, so in a multi-worker deployment this limits per worker, not
globally — good enough for slowing down credential stuffing against one form,
not a substitute for a shared store if that ever matters.
"""

import re

from django.conf import settings
from django.core.cache import cache

_RATE_RE = re.compile(r"^(\d+)/(sec|min|hour|day)$")
_PERIOD_SECONDS = {"sec": 1, "min": 60, "hour": 3600, "day": 86400}


def _auth_rate_limit():
    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth"]
    count, period = _RATE_RE.match(rate).groups()
    return int(count), _PERIOD_SECONDS[period]


def _key(request, scope):
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"throttle:{scope}:{ip}"


def is_rate_limited(request, scope):
    """Report whether this client IP has exceeded the shared "auth" rate for failed attempts."""
    limit, _window = _auth_rate_limit()
    return cache.get(_key(request, scope), 0) >= limit


def record_failed_attempt(request, scope):
    """Increment the failed-attempt counter for this client IP + scope."""
    _limit, window = _auth_rate_limit()
    key = _key(request, scope)
    cache.set(key, cache.get(key, 0) + 1, timeout=window)
