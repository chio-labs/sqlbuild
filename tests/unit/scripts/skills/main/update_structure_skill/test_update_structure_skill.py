from __future__ import annotations

from pathlib import Path

import pytest

from scripts.skills._helpers.structure_generation import build_skill_markdown
from scripts.skills.constants import GENERATED_MARKER
from tests.unit.scripts.skills.main.update_structure_skill._test_types import (
    StructureSkillGenerationTestCase,
)
from tests.unit.scripts.skills.main.update_structure_skill.helpers import write_structure_rules_file


@pytest.mark.parametrize(
    "test_case",
    [
        StructureSkillGenerationTestCase(
            description="renders structure skill from violation messages",
            source_relative_path=Path("scripts/structure/rules/example.py"),
            source_contents="""
from scripts.structure.models import Violation


def check_example(file_path):
    code = "SC010" if file_path.name == "main.py" else "SC022"
    message = (
        "_helpers/ must not contain main.py; keep orchestration outside helper packages"
        if code == "SC010"
        else "helper subpackages must stay shallow"
    )
    return [
        Violation(
            code=code,
            path=file_path,
            line=1,
            message=message,
        ),
        Violation(
            code="SC011",
            path=file_path,
            line=1,
            message=(
                "subpackage code must not import sibling package internals; "
                "promote shared code to sqlbuild.example.shared"
            ),
        ),
        Violation(
            code="SC033",
            path=file_path,
            line=1,
            message=f"cross-package import reaches into internal structure of '{file_path}'",
        ),
    ]
""",
            expected_fragments=(
                "---\nname: sqlbuild-structure\n",
                GENERATED_MARKER,
                "Load it before changing runtime or script structure",
                "## Main Orchestrators And Phase Functions",
                "A `main/` public function is an orchestrator",
                "`SC063`, `SC064`, and `SC065` cap statements, distinct calls, and locals",
                (
                    "- `SC010`: _helpers/ must not contain main.py; keep orchestration "
                    "outside helper packages"
                ),
                "- `SC022`: helper subpackages must stay shallow",
                (
                    "- `SC011`: subpackage code must not import sibling package internals; "
                    "promote shared code to sqlbuild.example.shared"
                ),
                "- `SC033`: cross-package import reaches into internal structure of '{file_path}'",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_structure_rules_when_building_skill_then_renders_boundary_guidance(
    test_case: StructureSkillGenerationTestCase,
    tmp_path: Path,
) -> None:
    write_structure_rules_file(
        repo_root=tmp_path,
        relative_path=test_case.source_relative_path,
        contents=test_case.source_contents,
    )

    skill_markdown: str = build_skill_markdown(
        repo_root=tmp_path,
        source_path=test_case.source_relative_path,
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in skill_markdown
    assert "- `SC010`: helper subpackages must stay shallow" not in skill_markdown
    assert "- `SC022`: _helpers/ must not contain main.py" not in skill_markdown
