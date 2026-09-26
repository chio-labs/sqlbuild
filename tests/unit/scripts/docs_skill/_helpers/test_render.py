from pathlib import Path

import pytest

from scripts.docs_skill.constants import GENERATED_MARKER
from scripts.docs_skill.main.generate import generate_docs_skill
from tests.unit.scripts.docs_skill._helpers._test_types import ReferencePagesTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ReferencePagesTestCase(
            description="pages become files with relative links and a grouped index",
            sidebar_json=(
                '[{"label":"Start","items":["docs"]},'
                '{"label":"Concepts","items":["docs/concepts/diff","docs/concepts/models"]},'
                '{"label":"CLI Reference","items":["docs/cli/diff"]}]'
            ),
            pages={
                "index.mdx": '---\ntitle: "Introduction"\n---\n\nWelcome.\n',
                "concepts/diff.mdx": (
                    '---\ntitle: "Data Diffs"\ndescription: "Compare data."\n---\n\n'
                    "import Note from '../../../../components/mintlify/Note.astro';\n"
                    "See [models](/docs/concepts/models/#schemas), [the CLI](/docs/cli/diff) and "
                    "[elsewhere](/docs/missing/page#details).\n\n<Note>\nkept text\n</Note>\n"
                    "[docs](/docs/) [home](/) [LLMs](/llms.txt)\n"
                    '<CardGroup cols={2}>\n<Card\n title="Example"\n href="/docs/quickstart"\n>\n'
                    "Card body.\n</Card>\n</CardGroup>\n<Steps>\nSteps body.\n</Steps>\n"
                    '```python\n<Card\n title="preserved code"\n>\n```\n'
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
                "index.md",
            ),
            expected_fragments=(
                ("concepts/diff.md", GENERATED_MARKER),
                ("concepts/diff.md", "# Data Diffs"),
                ("concepts/diff.md", "> Compare data."),
                ("concepts/diff.md", "Online: https://sqlbuild.com/docs/concepts/diff/\n"),
                ("index.md", "Online: https://sqlbuild.com/docs/\n"),
                ("concepts/diff.md", "[models](models.md#schemas)"),
                ("concepts/diff.md", "[the CLI](../cli/diff.md)"),
                (
                    "concepts/diff.md",
                    "[elsewhere](https://sqlbuild.com/docs/missing/page/#details)",
                ),
                ("concepts/diff.md", "[docs](../index.md)"),
                ("concepts/diff.md", "[home](https://sqlbuild.com/)"),
                ("concepts/diff.md", "[LLMs](https://sqlbuild.com/llms.txt)"),
                ("concepts/diff.md", "Card body."),
                ("concepts/diff.md", "Steps body."),
                ("concepts/diff.md", '```python\n<Card\n title="preserved code"\n>\n```'),
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
    docs_root: Path = tmp_path / "src/content/docs/docs"
    output_dir: Path = tmp_path / "references" / "docs"
    docs_root.mkdir(parents=True)
    (tmp_path / "src/sidebar.json").write_text(test_case.sidebar_json, encoding="utf-8")
    for relative_path, contents in test_case.pages.items():
        (docs_root / relative_path).parent.mkdir(parents=True, exist_ok=True)
        (docs_root / relative_path).write_text(contents, encoding="utf-8")
    (output_dir / test_case.stale_page).parent.mkdir(parents=True, exist_ok=True)
    (output_dir / test_case.stale_page).write_text(f"{GENERATED_MARKER}\nold\n", encoding="utf-8")

    result: int = generate_docs_skill(
        ["--docs-root", str(docs_root), "--output-dir", str(output_dir)]
    )

    assert result == 0
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
    assert "import Note" not in written["concepts/diff.md"]
    assert "<CardGroup" not in written["concepts/diff.md"]
    assert 'title="Example"' not in written["concepts/diff.md"]
    assert 'href="/docs/quickstart"' not in written["concepts/diff.md"]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
