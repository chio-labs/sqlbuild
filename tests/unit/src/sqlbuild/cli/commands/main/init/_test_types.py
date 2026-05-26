from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InitScaffoldTestCase:
    description: str
    project_dir_name: str
    expected_directories: tuple[str, ...]
    expected_gitkeep_files: tuple[str, ...]
    expected_config_fragment: str
