"""Executor run enum types."""

from __future__ import annotations

from enum import StrEnum


class HookPhase(StrEnum):
    PRE_HOOKS = "pre_hooks"
    POST_HOOKS = "post_hooks"
