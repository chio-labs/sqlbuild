from pathlib import Path

import pytest

from scripts.docs_skill._helpers.output import write_reference_pages
from scripts.docs_skill._helpers.render import build_reference_pages
from scripts.docs_skill.constants import GENERATED_MARKER
from tests.unit.scripts.docs_skill._helpers._test_types import ReferencePagesTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ReferencePagesTestCase(
            description="pages become files with relative links and a grouped index",
            docs_json=(
                '{"navigation":{"groups":['
                '{"group":"Concepts","pages":["concepts/diff","concepts/models"]},'
                '{"group":"CLI Reference","pages":["cli/diff"]}]}}'
            ),
            pages={
                "concepts/diff.mdx": (
                    '---\ntitle: "Data Diffs"\ndescription: "Compare data."\n---\n\n'
                    "See [models](/concepts/models#schemas), [the CLI](/cli/diff) and "
                    "[elsewhere](/missing/page).\n\n<Note>\nkept text\n</Note>\n"
                ),
                "concepts/models.mdx": '---\ntitle: "Models"\n---\n\n## Schemas\n\nBody.\n',
                "cli/diff.mdx": '---\ntitle: "diff"\ndescription: "Diff command."\n---\n\nUsage.\n',
            },
            stale_page="concepts/retired.md",
            expected_files=(
                "CONTENTS.md",
                "cli/diff.md",
                "concepts/diff.md",
                "concepts/models.md",
            ),
            expected_fragments=(
                ("concepts/diff.md", GENERATED_MARKER),
                ("concepts/diff.md", "# Data Diffs"),
                ("concepts/diff.md", "> Compare data."),
                ("concepts/diff.md", "Online: https://docs.sqlbuild.com/concepts/diff"),
                ("concepts/diff.md", "[models](models.md#schemas)"),
                ("concepts/diff.md", "[the CLI](../cli/diff.md)"),
                ("concepts/diff.md", "[elsewhere](https://docs.sqlbuild.com/missing/page)"),
                ("concepts/diff.md", "kept text"),
                ("CONTENTS.md", "## Concepts"),
                (
                    "CONTENTS.md",
                    "- [Data Diffs](concepts/diff.md) (`concepts/diff`) - Compare data.",
                ),
                ("CONTENTS.md", "## CLI Reference"),
                ("CONTENTS.md", "- [diff](cli/diff.md) (`cli/diff`) - Diff command."),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_docs_pages_when_writing_references_then_each_page_is_a_linked_file(
    test_case: ReferencePagesTestCase,
    tmp_path: Path,
) -> None:
    docs_root: Path = tmp_path / "docs"
    output_dir: Path = tmp_path / "references" / "docs"
    (docs_root).mkdir()
    (docs_root / "docs.json").write_text(test_case.docs_json, encoding="utf-8")
    for relative_path, contents in test_case.pages.items():
        (docs_root / relative_path).parent.mkdir(parents=True, exist_ok=True)
        (docs_root / relative_path).write_text(contents, encoding="utf-8")
    (output_dir / test_case.stale_page).parent.mkdir(parents=True, exist_ok=True)
    (output_dir / test_case.stale_page).write_text(f"{GENERATED_MARKER}\nold\n", encoding="utf-8")

    write_reference_pages(output_dir=output_dir, pages=build_reference_pages(docs_root=docs_root))

    written: dict[str, str] = {
        path.relative_to(output_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(output_dir.rglob("*.md"))
    }
    assert tuple(written) == test_case.expected_files
    found: dict[tuple[str, str], bool] = {
        (name, fragment): fragment in written[name]
        for name, fragment in test_case.expected_fragments
    }
    assert found == dict.fromkeys(test_case.expected_fragments, True)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
