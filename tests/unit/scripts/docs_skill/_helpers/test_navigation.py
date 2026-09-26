from pathlib import Path

import pytest

from scripts.docs_skill._helpers.navigation import list_navigation_groups, list_ordered_page_paths
from tests.unit.scripts.docs_skill._helpers._test_types import (
    OrderedNavigationPagesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        OrderedNavigationPagesTestCase(
            description="nested sidebar groups preserve ordering with index and unlisted pages",
            sidebar_json=(
                '[{"label":"Start","items":["docs"]},{"label":"Hooks","items":['
                '{"label":"Overview","slug":"docs/concepts/hooks"},'
                '{"label":"Nested","collapsed":true,"items":["docs/concepts/hooks/sql",'
                '"docs/missing","docs/concepts/hooks"]}]}]'
            ),
            page_paths=(
                "index.mdx",
                "concepts/hooks.mdx",
                "concepts/hooks/sql.mdx",
                "concepts/unlisted.md",
            ),
            expected_paths=(
                "index.mdx",
                "concepts/hooks.mdx",
                "concepts/hooks/sql.mdx",
                "concepts/unlisted.md",
            ),
            expected_labels=("Start", "Hooks", "Other pages"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_navigation_root_when_listing_pages_then_root_precedes_children(
    test_case: OrderedNavigationPagesTestCase,
    tmp_path: Path,
) -> None:
    sidebar_path: Path = tmp_path / "sidebar.json"
    sidebar_path.write_text(test_case.sidebar_json, encoding="utf-8")
    page_path: str
    for page_path in test_case.page_paths:
        target: Path = tmp_path / page_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\ntitle: Test\n---\n", encoding="utf-8")

    result: list[Path] = list_ordered_page_paths(docs_root=tmp_path, sidebar_path=sidebar_path)

    assert tuple(path.as_posix() for path in result) == test_case.expected_paths
    assert (
        tuple(
            group.label
            for group in list_navigation_groups(docs_root=tmp_path, sidebar_path=sidebar_path)
        )
        == test_case.expected_labels
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
