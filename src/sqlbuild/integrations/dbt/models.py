"""dbt interop domain models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SelectedDbtProfileOutput:
    """Selected dbt profile target output before rendering."""

    profile_name: str
    target_name: str
    output: dict[str, object]


@dataclass(frozen=True)
class ResolvedDbtProfileOutput:
    """Rendered dbt profile target output."""

    project_dir: Path
    profiles_dir: Path
    profile_name: str
    target_name: str
    output: dict[str, object]

    @property
    def adapter_type(self) -> str:
        """Return the dbt adapter type from the rendered output."""

        value: object | None = self.output.get("type")
        return value if isinstance(value, str) else ""
