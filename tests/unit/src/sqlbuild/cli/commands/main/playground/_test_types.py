from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CreatePlaygroundProjectTestCase:
    description: str
    target_relative_path: Path
    expected_files: tuple[Path, ...]
    unexpected_paths: tuple[Path, ...]
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class RunPlaygroundTestCase:
    description: str
    target_path: str
    expected_stdout_fragments: tuple[str, ...]
