"""Node source watermark state exceptions."""

from __future__ import annotations


class NodeSourceWatermarkInputError(ValueError):
    """Raised when node source watermark state cannot be read or decoded."""
