"""dbt interop domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DbtCliOptions:
    """Resolved dbt CLI options shared by dbt commands."""

    project_dir: Path | None = None
    profiles_dir: Path | None = None
    target: str | None = None
    target_path: Path | None = None
    vars: str | None = None
    state: Path | None = None
    defer: bool = False


@dataclass(frozen=True)
class DbtCliConfigOverrides:
    """dbt config values supplied by CLI flags."""

    project_dir: str | None = None
    profiles_dir: str | None = None
    target: str | None = None
    target_path: str | None = None

    @property
    def has_any(self) -> bool:
        """Return whether any dbt CLI config flag was supplied."""

        return any(
            value is not None
            for value in (self.project_dir, self.profiles_dir, self.target, self.target_path)
        )


@dataclass(frozen=True)
class ResolvedDbtConfig:
    """Resolved dbt config after applying CLI overrides."""

    project_dir: Path | None
    profiles_dir: Path | None
    target: str | None
    target_path: Path | None


@dataclass(frozen=True)
class DbtCommandResult:
    """Completed dbt command output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DbtLsNode:
    """One node returned by `dbt ls --output json`."""

    unique_id: str
    resource_type: str | None = None
    package_name: str | None = None
    name: str | None = None
    original_file_path: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtLsResult:
    """Parsed result from one dbt ls invocation."""

    nodes: tuple[DbtLsNode, ...]
    command: DbtCommandResult
