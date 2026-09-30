from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnEditTestCase:
    description: str
    sql: str
    cascade: bool
    expected_sql: str
    expected_manual: str = ""
    expected_passes_through: bool = False


@dataclass(frozen=True)
class HeaderEditTestCase:
    description: str
    contents: str
    expected_contents: str


@dataclass(frozen=True)
class IdentifierSitesTestCase:
    description: str
    text: str
    expected_offsets: tuple[int, ...]


@dataclass(frozen=True)
class ApplyEditsTestCase:
    description: str
    text: str
    spans: tuple[tuple[int, int, str], ...]
    expected_text: str


@dataclass(frozen=True)
class ApplyEditsErrorTestCase:
    description: str
    text: str
    spans: tuple[tuple[int, int, str], ...]
    expected_error: type[Exception]


@dataclass(frozen=True)
class CommitChangesTestCase:
    description: str
    files: dict[str, str]
    current_files: dict[str, str]
    locked_directory: str
    spans: tuple[tuple[int, int, str], ...]
    edited_path: str
    moved_from: str
    moved_to: str
    expected_error: type[Exception]
    expected_files: dict[str, str]
