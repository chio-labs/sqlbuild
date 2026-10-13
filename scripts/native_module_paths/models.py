"""Native module path scan models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModulePathReference:
    """One Python module path, or module and attribute, that native source imports."""

    location: str
    path: str
    attribute: str | None = None


@dataclass(frozen=True)
class NativeModulePathScan:
    """What a scan of native source found: checked references and policy violations."""

    references: tuple[ModulePathReference, ...]
    logger_names: tuple[str, ...]
    violations: tuple[str, ...]
