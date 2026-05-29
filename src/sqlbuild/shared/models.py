from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.shared.constants import DEFAULT_MAX_DISPLAY_ENTRIES
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class DisplayOptions:
    """Options controlling bounded human output."""

    max_entries_per_section: int | None = DEFAULT_MAX_DISPLAY_ENTRIES
    overflow_flag: str = "--verbose"


@dataclass(frozen=True)
class TextStyle:
    """One ANSI style role in the CLI theme."""

    prefix: str
    suffix: str = "\033[0m"

    def apply(self, text: str, *, use_color: bool) -> str:
        """Apply this style when color is enabled."""

        if not use_color or not self.prefix:
            return text
        return f"{self.prefix}{text}{self.suffix}"


@dataclass(frozen=True)
class CliTheme:
    """Semantic style roles for human CLI output."""

    title: TextStyle
    section: TextStyle
    label: TextStyle
    value: TextStyle
    object_name: TextStyle
    command: TextStyle
    success: TextStyle
    warning: TextStyle
    error: TextStyle
    skipped: TextStyle
    muted: TextStyle
    dbt_section: TextStyle
    dbt_label: TextStyle
    dbt_object_name: TextStyle
    dbt_execution_label: TextStyle


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
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = ()
    columns: tuple[SourceColumnEntry, ...] = ()
    contract: str | None = None


@dataclass(frozen=True)
class ParsedScenarioArtifactName:
    """Parsed physical name for one scenario-owned artifact."""

    hash_prefix: str
    kind: str
    logical_name: str
