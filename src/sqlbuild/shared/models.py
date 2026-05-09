from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


@dataclass(frozen=True)
class DiscoveredAdapter:
    """A discovered project-local adapter class."""

    adapter_name: str
    adapter_class: type[StrictAdapter]
    file_path: Path


@dataclass(frozen=True)
class ParsedScenarioArtifactName:
    """Parsed physical name for one scenario-owned artifact."""

    hash_prefix: str
    kind: str
    logical_name: str
