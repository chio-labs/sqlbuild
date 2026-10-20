"""Build feature alignment models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedCrate:
    """A crate version on one side of a build: compiled for the target or for the host."""

    package: str
    side: str


@dataclass(frozen=True)
class FeatureDrift:
    """A crate both builds compile with different features, so Cargo compiles it twice."""

    target: str
    crate: ResolvedCrate
    sqb_features: frozenset[str]
    extension_features: frozenset[str]
