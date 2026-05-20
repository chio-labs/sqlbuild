from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.shared.constants import DEFAULT_MAX_DISPLAY_ENTRIES


@dataclass(frozen=True)
class DisplayOptions:
    """Options controlling bounded human output."""

    max_entries_per_section: int | None = DEFAULT_MAX_DISPLAY_ENTRIES
    overflow_flag: str = "--verbose"


@dataclass(frozen=True)
class DiscoveredAdapter:
    """A discovered project-local adapter class."""

    adapter_name: str
    adapter_class: type[StrictAdapter]
    file_path: Path


@dataclass(frozen=True)
class LoaderDefinition:
    """Metadata attached to a decorated source loader function."""

    name: str
    depends_on: tuple[Callable[..., object], ...] = ()
    target: str | None = None


@dataclass(frozen=True)
class ParsedScenarioArtifactName:
    """Parsed physical name for one scenario-owned artifact."""

    hash_prefix: str
    kind: str
    logical_name: str
