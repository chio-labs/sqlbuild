"""Portable process resource sampling helpers."""

from __future__ import annotations

import os
import sys

_DARWIN_PLATFORM: str = "darwin"


def read_process_resources() -> tuple[float, float, int | None]:
    """Read process user/system CPU and normalized maximum RSS."""

    times: os.times_result = os.times()
    return times.user, times.system, _read_max_rss_bytes()


def _read_max_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    try:
        max_rss: int = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (AttributeError, OSError):
        return None
    return max_rss if sys.platform == _DARWIN_PLATFORM else max_rss * 1024
