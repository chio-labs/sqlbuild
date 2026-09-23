from dataclasses import dataclass


@dataclass(frozen=True)
class OrderedNavigationPagesTestCase:
    description: str
    docs_json: str
    page_paths: tuple[str, ...]
    expected_paths: tuple[str, ...]


@dataclass(frozen=True)
class ReferencePagesTestCase:
    description: str
    docs_json: str
    pages: dict[str, str]
    stale_page: str
    expected_files: tuple[str, ...]
    expected_fragments: tuple[tuple[str, str], ...]
