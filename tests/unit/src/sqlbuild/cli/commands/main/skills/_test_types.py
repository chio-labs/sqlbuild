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
    expected_content_fragment: str = "# SQLBuild Skill"
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
