from pathlib import Path

import pytest

from scripts.docs_skill.constants import GENERATED_MARKER
from scripts.docs_skill.main.check import check_docs_skill
from scripts.docs_skill.main.generate import generate_docs_skill
from tests.unit.scripts.docs_skill.main._test_types import DocsSkillCheckTestCase

_SIDEBAR_JSON: str = '[{"label":"Concepts","items":["docs/concepts/orders"]}]'
_ORDERS_PAGE: str = '---\ntitle: "Orders"\n---\n\nOrders body.\n'


@pytest.mark.parametrize(
    "test_case",
    [
        DocsSkillCheckTestCase(
            description="freshly generated pages pass",
            output_edits={},
            expected_exit_code=0,
            expected_outdated=(),
        ),
        DocsSkillCheckTestCase(
            description="hand-edited generated page fails",
            output_edits={"concepts/orders.md": f"{GENERATED_MARKER}\nold orders body\n"},
            expected_exit_code=1,
            expected_outdated=("concepts/orders.md",),
        ),
        DocsSkillCheckTestCase(
            description="generated page with no docs source fails",
            output_edits={"concepts/retired.md": f"{GENERATED_MARKER}\nretired\n"},
            expected_exit_code=1,
            expected_outdated=("concepts/retired.md",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reference_pages_when_checking_docs_skill_then_outdated_pages_fail_with_fix_command(
    test_case: DocsSkillCheckTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    docs_root: Path = tmp_path / "src/content/docs/docs"
    output_dir: Path = tmp_path / "references/docs"
    (docs_root / "concepts").mkdir(parents=True)
    (tmp_path / "src/sidebar.json").write_text(_SIDEBAR_JSON, encoding="utf-8")
    (docs_root / "concepts/orders.mdx").write_text(_ORDERS_PAGE, encoding="utf-8")
    arguments: list[str] = [
        "--docs-root",
        str(docs_root),
        "--output-dir",
        str(output_dir),
        "--investigation-guide",
        "",
    ]
    _ = generate_docs_skill(arguments)
    for relative_path, contents in test_case.output_edits.items():
        (output_dir / relative_path).write_text(contents, encoding="utf-8")
    _ = capsys.readouterr()

    result: int = check_docs_skill(arguments)

    errors: str = capsys.readouterr().err
    assert result == test_case.expected_exit_code, (test_case.description, errors)
    assert all(f"  {path}\n" in errors for path in test_case.expected_outdated), errors
    assert ("make skills" in errors) is bool(test_case.expected_outdated), errors
