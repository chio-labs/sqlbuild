from dataclasses import dataclass


@dataclass(frozen=True)
class OrderedNavigationPagesTestCase:
    description: str
    docs_json: str
    page_paths: tuple[str, ...]
    expected_paths: tuple[str, ...]
