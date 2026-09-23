from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SkillUpdateTestCase:
    description: str
    project_config: str | None = None
    requested_targets: tuple[str, ...] = ()
    existing_files: dict[Path, str] = field(default_factory=dict)
    global_install: bool = False
    force: bool = False
    expected_written_paths: tuple[Path, ...] = ()
    expected_content_fragment: str = "## Reach for these tools"
    project_path: Path = Path(".")
    git_marker_is_file: bool | None = None


@dataclass(frozen=True)
class SkillUpdateErrorTestCase:
    description: str
    existing_files: dict[Path, str]
    requested_targets: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class SkillMaintenanceTestCase:
    description: str
    project_config: str | None = None
    existing_files: dict[Path, str] = field(default_factory=dict)
    expected_message_fragment: str = ""
    expected_written_paths: tuple[Path, ...] = ()
    project_path: Path = Path(".")
    git_marker_is_file: bool | None = None


@dataclass(frozen=True)
class SkillDirectoryInstallTestCase:
    description: str
    existing_files: dict[Path, str] = field(default_factory=dict)
    expected_absent_paths: tuple[Path, ...] = ()
    expected_preserved_files: dict[Path, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillDirectoryCollisionTestCase:
    description: str
    existing_files: dict[Path, str]
    expected_error_fragment: str
    expected_unwritten_path: Path


@dataclass(frozen=True)
class SkillDirectoryMaintenanceTestCase:
    description: str
    project_config: str
    stale_relative_path: str
    expected_message_fragment: str
    expected_restored: bool


@dataclass(frozen=True)
class SkillContentTestCase:
    description: str
    max_entry_lines: int
    expected_broken_links: frozenset[str] = frozenset()
    expected_unknown_commands: frozenset[str] = frozenset()
