from pathlib import Path

import pytest

from scripts.docs_skill._helpers.navigation import list_ordered_page_paths
from tests.unit.scripts.docs_skill._helpers._test_types import (
    OrderedNavigationPagesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OrderedNavigationPagesTestCase(
            description="group root precedes child pages and unlisted pages",
            docs_json=(
                '{"navigation":{"groups":[{"group":"Hooks",'
                '"root":"concepts/hooks","pages":["concepts/hooks/sql"]}]}}'
            ),
            page_paths=(
                "concepts/hooks.mdx",
                "concepts/hooks/sql.mdx",
                "concepts/unlisted.mdx",
            ),
            expected_paths=(
                "concepts/hooks.mdx",
                "concepts/hooks/sql.mdx",
                "concepts/unlisted.mdx",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_navigation_root_when_listing_pages_then_root_precedes_children(
    test_case: OrderedNavigationPagesTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "docs.json").write_text(test_case.docs_json, encoding="utf-8")
    page_path: str
    for page_path in test_case.page_paths:
        target: Path = tmp_path / page_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\ntitle: Test\n---\n", encoding="utf-8")

    result: list[Path] = list_ordered_page_paths(docs_root=tmp_path)

    assert tuple(path.as_posix() for path in result) == test_case.expected_paths


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
