"""Debug process resource reporting entrypoint."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics.models import ProcessResourceUsage


def log_process_resources(*, usage: ProcessResourceUsage) -> None:
    """Write one debug-only process resource report."""

    max_rss: str = (
        "unavailable" if usage.max_rss_bytes is None else _format_bytes(usage.max_rss_bytes)
    )
    logging.getLogger("sqlbuild.process").debug(
        "Process resources  wall %.2fs, user CPU %.2fs, system CPU %.2fs, max RSS %s",
        usage.wall_seconds,
        usage.user_cpu_seconds,
        usage.system_cpu_seconds,
        max_rss,
    )


def _format_bytes(value: int) -> str:
    mebibytes: float = value / (1024 * 1024)
    return f"{mebibytes:.1f} MiB"
