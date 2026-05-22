from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CreatePlaygroundProjectTestCase:
    description: str
    target_relative_path: Path
    expected_files: tuple[Path, ...]
    unexpected_paths: tuple[Path, ...]
    template: str = "waffle_shop"
    expected_error_fragment: str = ""
    expected_file_fragments: tuple[tuple[Path, tuple[str, ...]], ...] = ()
    unexpected_file_fragments: tuple[tuple[Path, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class RunPlaygroundTestCase:
    description: str
    target_path: str
    expected_stdout_fragments: tuple[str, ...]
    template: str = "waffle_shop"
