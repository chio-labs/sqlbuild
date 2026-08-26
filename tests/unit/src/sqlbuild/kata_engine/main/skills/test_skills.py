"""Generated kata skill freshness behavior tests."""

from multiprocessing import get_context
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path
from stat import S_IMODE
from unittest.mock import patch

import pytest

from sqlbuild.kata_engine.constants import KATA_SKILL_PATHS
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.skills import install_skills
from sqlbuild.kata_engine.models import KataConfig, RuleExemption
from tests.unit.src.sqlbuild.kata_engine.main.skills._test_types import (
    SkillDivergenceTestCase,
    SkillFreshnessTestCase,
    SkillGuidanceTestCase,
    SkillInstallationTestCase,
)
from tests.unit.src.sqlbuild.kata_engine.main.skills.conftest import (
    EditAfterBackupRead,
    FailingReplacement,
    ReplacementFailure,
    install_failing_skills_in_process,
    install_skills_in_process,
)
from tests.unit.src.sqlbuild.kata_engine.main.skills.helpers import write_custom_rule


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


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="later divergent target leaves every target unchanged",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="refusing to overwrite divergent kata skill",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_later_target_failure_when_installing_then_all_targets_remain_unchanged(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    original_config: KataConfig = KataConfig(select=(test_case.selected_rule,))
    _ = install_skills(config=original_config, project_dir=tmp_path, check=False)
    paths: tuple[Path, ...] = tuple(tmp_path / value for value in KATA_SKILL_PATHS)
    divergent: Path = paths[-1]
    divergent.write_text(divergent.read_text(encoding="utf-8") + "local edit\n", encoding="utf-8")
    expected_contents: tuple[bytes, ...] = tuple(path.read_bytes() for path in paths)
    unrelated: Path = tmp_path / ".claude" / "notes.txt"
    unrelated.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(KataError, match=test_case.expected_error):
        install_skills(
            config=KataConfig(select=(test_case.changed_rule,)),
            project_dir=tmp_path,
            check=False,
        )

    assert tuple(path.read_bytes() for path in paths) == expected_contents
    assert unrelated.read_bytes() == b"keep me\n"


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="partial staging failure leaves every target unchanged",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="staging failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_staging_failure_when_installing_then_no_target_is_replaced(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    _ = install_skills(
        config=KataConfig(select=(test_case.selected_rule,)),
        project_dir=tmp_path,
        check=False,
    )
    paths: tuple[Path, ...] = tuple(tmp_path / value for value in KATA_SKILL_PATHS)
    expected_contents: tuple[bytes, ...] = tuple(path.read_bytes() for path in paths)

    with (
        patch.object(
            Path,
            "read_bytes",
            side_effect=(expected_contents[0], OSError(test_case.expected_error)),
        ),
        pytest.raises(OSError, match=test_case.expected_error),
    ):
        install_skills(
            config=KataConfig(select=(test_case.changed_rule,)),
            project_dir=tmp_path,
            check=False,
        )

    assert tuple(path.read_bytes() for path in paths) == expected_contents
    assert tuple(tmp_path.rglob("*.tmp")) == ()
    assert tuple(tmp_path.rglob("*.bak")) == ()


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="missing targets are only inspected",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_targets_when_checking_then_filesystem_is_not_mutated(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    unrelated: Path = tmp_path / "notes.txt"
    unrelated.write_text("keep me\n", encoding="utf-8")

    fresh: bool = install_skills(
        config=KataConfig(select=(test_case.selected_rule,)),
        project_dir=tmp_path,
        check=True,
    )

    assert fresh is test_case.expected_fresh
    assert tuple(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == (Path("notes.txt"),)
    assert unrelated.read_bytes() == b"keep me\n"


@pytest.mark.parametrize(
    "test_case",
    [
        SkillGuidanceTestCase(
            description="exact exception retains its selected rule guidance",
            expected_fragment="### SQBKS001:",
            absent_fragment="### SQBKS002:",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_exact_exception_when_installing_then_selected_guidance_is_retained(
    tmp_path: Path,
    test_case: SkillGuidanceTestCase,
) -> None:
    config: KataConfig = KataConfig(
        select=("SQBKS001",),
        rule_exceptions=(
            RuleExemption(
                rule="SQBKS001",
                path="models/mart/market__mart__prices.sql",
                reason="Migration is tracked",
            ),
        ),
    )

    _ = install_skills(config=config, project_dir=tmp_path, check=False)

    skill: str = (tmp_path / KATA_SKILL_PATHS[0]).read_text(encoding="utf-8")
    assert test_case.expected_fragment in skill
    assert test_case.absent_fragment not in skill
    assert "Migration is tracked" in skill


@pytest.mark.parametrize(
    "test_case",
    [
        SkillGuidanceTestCase(
            description="global ignore removes selected family guidance",
            expected_fragment="### SQBKL001:",
            absent_fragment="### SQBKS001:",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_global_ignore_when_installing_then_ignored_guidance_is_removed(
    tmp_path: Path,
    test_case: SkillGuidanceTestCase,
) -> None:
    config: KataConfig = KataConfig(select=("SQBKS001", "SQBKL001"), ignore=("SQBKS",))

    _ = install_skills(config=config, project_dir=tmp_path, check=False)

    skill: str = (tmp_path / KATA_SKILL_PATHS[0]).read_text(encoding="utf-8")
    assert test_case.expected_fragment in skill
    assert test_case.absent_fragment not in skill


@pytest.mark.parametrize(
    "test_case",
    [
        SkillGuidanceTestCase(
            description="selected custom rule renders configured effective option",
            expected_fragment="Effective options: {'required_domain': 'configured_domain'}",
            absent_fragment="'required_domain': 'default_domain'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_custom_rule_when_installing_then_effective_options_are_rendered(
    tmp_path: Path,
    test_case: SkillGuidanceTestCase,
) -> None:
    rule_path: Path = write_custom_rule(root=tmp_path)
    config: KataConfig = KataConfig(
        select=("XSQBKT101",),
        rule_paths=(rule_path.as_posix(),),
        rule_options={"XSQBKT101": {"required_domain": "configured_domain"}},
    )

    _ = install_skills(config=config, project_dir=tmp_path, check=False)

    skill: str = (tmp_path / KATA_SKILL_PATHS[0]).read_text(encoding="utf-8")
    assert "### XSQBKT101: skill-test-rule" in skill
    assert "custom guidance message" in skill
    assert test_case.expected_fragment in skill
    assert test_case.absent_fragment not in skill


@pytest.mark.parametrize(
    "test_case",
    [
        SkillGuidanceTestCase(
            description="repeated all-target installation is byte deterministic",
            expected_fragment="### SQBKS001:",
            absent_fragment="### SQBKS002:",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_policy_when_reinstalling_then_all_targets_are_byte_identical(
    tmp_path: Path,
    test_case: SkillGuidanceTestCase,
) -> None:
    config: KataConfig = KataConfig(select=("SQBKS001",))
    _ = install_skills(config=config, project_dir=tmp_path, check=False)
    paths: tuple[Path, ...] = tuple(tmp_path / value for value in KATA_SKILL_PATHS)
    first: tuple[bytes, ...] = tuple(path.read_bytes() for path in paths)
    assert tuple(S_IMODE(path.stat().st_mode) for path in paths) == (0o644, 0o644, 0o644)
    for path in paths:
        path.chmod(0o640)

    _ = install_skills(config=config, project_dir=tmp_path, check=False)

    second: tuple[bytes, ...] = tuple(path.read_bytes() for path in paths)
    assert first == second
    assert len(set(second)) == 1
    assert test_case.expected_fragment.encode() in second[0]
    assert test_case.absent_fragment.encode() not in second[0]
    assert tuple(S_IMODE(path.stat().st_mode) for path in paths) == (0o640, 0o640, 0o640)


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="different concurrent policies serialize complete installations",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_different_concurrent_policies_when_installing_then_last_writer_is_atomic(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    context: SpawnContext = get_context("spawn")
    result_queue: Queue[object] = context.Queue()
    first_attempting: Event = context.Event()
    first_staged: Event = context.Event()
    release_first: Event = context.Event()
    second_attempting: Event = context.Event()
    first: BaseProcess = context.Process(
        target=install_skills_in_process,
        kwargs={
            "root": str(tmp_path),
            "selected_rule": test_case.selected_rule,
            "result_queue": result_queue,
            "attempting": first_attempting,
            "staged": first_staged,
            "release": release_first,
        },
    )
    second: BaseProcess = context.Process(
        target=install_skills_in_process,
        kwargs={
            "root": str(tmp_path),
            "selected_rule": test_case.changed_rule,
            "result_queue": result_queue,
            "attempting": second_attempting,
        },
    )

    first.start()
    assert first_staged.wait(timeout=20)
    second.start()
    assert second_attempting.wait(timeout=20)
    release_first.set()
    first.join(timeout=20)
    second.join(timeout=20)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert sorted((result_queue.get(timeout=5), result_queue.get(timeout=5))) == [
        (test_case.selected_rule, "ok", test_case.expected_error),
        (test_case.changed_rule, "ok", test_case.expected_error),
    ]
    contents: tuple[str, ...] = tuple(
        (tmp_path / value).read_text(encoding="utf-8") for value in KATA_SKILL_PATHS
    )
    assert len(set(contents)) == 1
    assert test_case.changed_rule in contents[0]
    assert test_case.selected_rule not in contents[0]


@pytest.mark.parametrize(
    "test_case",
    [
        SkillDivergenceTestCase(
            description="target edited after staging",
            selected_rule="SQBKS001",
            local_edit="concurrent local edit\n",
            expected_error="changed during installation",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_edit_between_validation_and_replacement_when_installing_then_edit_is_preserved(
    tmp_path: Path,
    test_case: SkillDivergenceTestCase,
) -> None:
    _ = install_skills(
        config=KataConfig(select=(test_case.selected_rule,)),
        project_dir=tmp_path,
        check=False,
    )
    target: Path = tmp_path / KATA_SKILL_PATHS[0]
    edit_after_backup: EditAfterBackupRead = EditAfterBackupRead(
        original_read=Path.read_bytes,
        target=target,
    )

    with (
        patch.object(Path, "read_bytes", autospec=True, side_effect=edit_after_backup),
        pytest.raises(KataError, match=test_case.expected_error),
    ):
        install_skills(
            config=KataConfig(select=("SQBKS002",)),
            project_dir=tmp_path,
            check=False,
        )

    paths: tuple[Path, ...] = tuple(tmp_path / value for value in KATA_SKILL_PATHS)
    assert paths[0].read_text(encoding="utf-8") == test_case.local_edit
    assert test_case.selected_rule in paths[1].read_text(encoding="utf-8")
    assert test_case.selected_rule in paths[2].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="rollback failure retains original error and recovery backup",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="replacement failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rollback_failure_when_replacement_fails_then_original_error_and_backup_are_preserved(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    _ = install_skills(
        config=KataConfig(select=(test_case.selected_rule,)),
        project_dir=tmp_path,
        check=False,
    )
    original_contents: bytes = (tmp_path / KATA_SKILL_PATHS[0]).read_bytes()
    replacement: FailingReplacement = FailingReplacement(original_replace=Path.replace)

    with (
        patch.object(Path, "replace", autospec=True, side_effect=replacement),
        pytest.raises(OSError, match=test_case.expected_error) as raised,
    ):
        install_skills(
            config=KataConfig(select=(test_case.changed_rule,)),
            project_dir=tmp_path,
            check=False,
        )

    backups: tuple[Path, ...] = tuple(tmp_path.rglob("*.bak"))
    assert raised.value.__notes__ is not None
    assert "rollback failed" in raised.value.__notes__[0]
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_contents


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="successful rollback restores original modes",
            selected_rule="SQBKS001",
            changed_rule="SQBKS002",
            expected_error="replacement failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_replacement_failure_when_rolling_back_then_original_modes_are_restored(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    _ = install_skills(
        config=KataConfig(select=(test_case.selected_rule,)),
        project_dir=tmp_path,
        check=False,
    )
    paths: tuple[Path, ...] = tuple(tmp_path / value for value in KATA_SKILL_PATHS)
    for path in paths:
        path.chmod(0o640)
    replacement: ReplacementFailure = ReplacementFailure(original_replace=Path.replace)

    with (
        patch.object(Path, "replace", autospec=True, side_effect=replacement),
        pytest.raises(OSError, match=test_case.expected_error),
    ):
        install_skills(
            config=KataConfig(select=(test_case.changed_rule,)),
            project_dir=tmp_path,
            check=False,
        )

    assert tuple(S_IMODE(path.stat().st_mode) for path in paths) == (0o640, 0o640, 0o640)


@pytest.mark.parametrize(
    "test_case",
    [
        SkillInstallationTestCase(
            description="failed writer rolls back before successful writer installs",
            selected_rule="SQBKS002",
            changed_rule="SQBKL001",
            expected_error="replacement failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_and_successful_concurrent_writers_when_installing_then_rollback_cannot_stale_overwrite(
    tmp_path: Path,
    test_case: SkillInstallationTestCase,
) -> None:
    _ = install_skills(
        config=KataConfig(select=("SQBKS001",)),
        project_dir=tmp_path,
        check=False,
    )
    context: SpawnContext = get_context("spawn")
    result_queue: Queue[object] = context.Queue()
    failure_reached: Event = context.Event()
    successful_writer_attempting: Event = context.Event()
    failed: BaseProcess = context.Process(
        target=install_failing_skills_in_process,
        kwargs={
            "root": str(tmp_path),
            "selected_rule": test_case.selected_rule,
            "result_queue": result_queue,
            "failure_reached": failure_reached,
            "other_writer_attempting": successful_writer_attempting,
        },
    )
    successful: BaseProcess = context.Process(
        target=install_skills_in_process,
        kwargs={
            "root": str(tmp_path),
            "selected_rule": test_case.changed_rule,
            "result_queue": result_queue,
            "attempting": successful_writer_attempting,
        },
    )

    failed.start()
    assert failure_reached.wait(timeout=20)
    successful.start()
    failed.join(timeout=20)
    successful.join(timeout=20)

    assert failed.exitcode == 0
    assert successful.exitcode == 0
    results: set[tuple[str, str, str]] = {
        result_queue.get(timeout=5),
        result_queue.get(timeout=5),
    }
    assert results == {
        (test_case.selected_rule, "OSError", test_case.expected_error),
        (test_case.changed_rule, "ok", ""),
    }
    contents: tuple[str, ...] = tuple(
        (tmp_path / value).read_text(encoding="utf-8") for value in KATA_SKILL_PATHS
    )
    assert len(set(contents)) == 1
    assert test_case.changed_rule in contents[0]
    assert test_case.selected_rule not in contents[0]
