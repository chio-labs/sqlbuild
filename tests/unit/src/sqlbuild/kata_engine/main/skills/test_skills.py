"""Generated kata skill freshness behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.skills import install_skills
from sqlbuild.kata_engine.models import KataConfig
from tests.unit.src.sqlbuild.kata_engine.main.skills._test_types import (
    SkillDivergenceTestCase,
    SkillFreshnessTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SkillFreshnessTestCase(
            description="changed active rules make installed guidance stale",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_fresh=True,
            expected_stale=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_rules_when_installing_skills_then_check_tracks_policy_freshness(
    tmp_path: Path,
    test_case: SkillFreshnessTestCase,
) -> None:
    config: KataConfig = KataConfig(select=(test_case.selected_rule,))

    installed: bool = install_skills(config=config, project_dir=tmp_path, check=False)
    fresh: bool = install_skills(config=config, project_dir=tmp_path, check=True)
    stale: bool = install_skills(
        config=KataConfig(select=(test_case.changed_rule,)),
        project_dir=tmp_path,
        check=True,
    )

    assert installed is True
    assert fresh is test_case.expected_fresh
    assert stale is test_case.expected_stale
    skill: str = (tmp_path / ".agents/skills/sqlbuild-kata/SKILL.md").read_text(encoding="utf-8")
    assert test_case.selected_rule in skill
    assert test_case.changed_rule not in skill


@pytest.mark.parametrize(
    "test_case",
    [
        SkillDivergenceTestCase(
            description="locally edited owned skill",
            selected_rule="SQBKS001",
            local_edit="local edit\n",
            expected_error="refusing to overwrite divergent kata skill",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_locally_edited_owned_skill_when_installing_then_refuses_to_overwrite(
    tmp_path: Path,
    test_case: SkillDivergenceTestCase,
) -> None:
    config: KataConfig = KataConfig(select=(test_case.selected_rule,))
    _ = install_skills(config=config, project_dir=tmp_path, check=False)
    path: Path = tmp_path / ".agents/skills/sqlbuild-kata/SKILL.md"
    path.write_text(
        path.read_text(encoding="utf-8") + test_case.local_edit,
        encoding="utf-8",
    )

    with pytest.raises(KataError, match=test_case.expected_error):
        install_skills(config=config, project_dir=tmp_path, check=False)
