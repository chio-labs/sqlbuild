"""Natively parsed MODEL header metadata and template expansions."""

from __future__ import annotations

from dataclasses import dataclass

import sqlbuild._native as _native


@dataclass(frozen=True, slots=True)
class NativeTemplateExpansion:
    """A natively expanded config value and the environment and context names it read, in order."""

    value: object
    reads: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class NativeTemplateRejection:
    """Python's exact template error for a config value and the names read before it, in order."""

    error: _native.NativeConfigError
    reads: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class TemplateResolutionFlags:
    """How one template expansion treats `CTX:` references."""

    allow_context: bool
    preserve_context_tokens: bool
    preserve_unknown_context: bool
