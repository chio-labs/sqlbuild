"""Render storage format constants."""

from __future__ import annotations

RENDER_STATE_MAGIC: bytes = b"SQBRENDER2\n"
RENDER_COMPRESSION_LEVEL: int = 1
RENDER_OVERLAY_MAX_SHARE: float = 0.25
RENDER_INDEX_FIELD_COUNT: int = 2
RENDER_LOAD_NOTICE_BYTES: int = 8 * 1024 * 1024
RENDER_LOAD_START_MESSAGE: str = "Loading stored renders ({mebibytes:.0f} MiB)..."
RENDER_LOAD_DONE_MESSAGE: str = "Loaded stored renders ({seconds:.1f} s)"
RENDER_LOAD_FAILED_MESSAGE: str = (
    "Stored renders are unusable; rendering every model again ({seconds:.1f} s)"
)
