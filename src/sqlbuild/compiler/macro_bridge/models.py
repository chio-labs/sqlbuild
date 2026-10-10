"""Macro call sites found by the native scan and the classes of their results."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass


@dataclass(frozen=True)
class MacroCallSite:
    """One top-level macro call in an authored string, in Python string offsets."""

    start: int
    end: int
    name: str
    tree_names: tuple[str, ...] | None
    """Every macro name of the call; None where a nested call is not one the scan completes."""
    typed_reference_text: bool


@dataclass(frozen=True)
class MacroScanFailure:
    """Where Python's scan of a string raises: in the call at `call_start`, or between calls."""

    call_start: int | None
    message: str


@dataclass(frozen=True)
class MacroCallScan:
    """A string's complete top-level call sites in order, and where its scan raises, if it does."""

    sites: tuple[MacroCallSite, ...]
    failure: MacroScanFailure | None


@dataclass(frozen=True)
class MacroCallClass:
    """A call's inputs besides its text: by object identity for the memo, by value for the store."""

    key: Hashable
    macro_store_tokens: tuple[str, ...]
    context_store_token: str | None
    persistent: bool


@dataclass(frozen=True)
class ModuleSources:
    """Files backing loaded modules, and whether every module's backing could be identified."""

    paths: tuple[str, ...]
    complete: bool
