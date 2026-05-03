"""Executor domain types."""

from __future__ import annotations

from enum import StrEnum


class TablePromotionMode(StrEnum):
    DIRECT = "direct"
    STAGED = "staged"
