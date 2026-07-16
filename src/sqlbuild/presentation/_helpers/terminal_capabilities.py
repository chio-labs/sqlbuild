"""Terminal capability implementations."""

from __future__ import annotations

import os
import sys


def supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()
