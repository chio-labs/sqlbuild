"""Real cold compilation preserves publication gates and unchanged artifact files."""

import json
import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest
from filelock import FileLock

from sqlbuild.cli.commands.classes import prepared_compile_artifacts
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    AbandonedStagingCompileTestCase,
    CrossDeviceArtifactsCompileTestCase,
    PreparedArtifactsCompileTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    has_second_filesystem,
    staging_directories,
    unavailable_staging_directory,
    write_prepared_artifacts_project,
    write_staging_directory,
)

_SECOND_FILESYSTEM: Path = Path("/dev/shm")


@pytest.mark.parametrize(
    "test_case",
    (
        PreparedArtifactsCompileTestCase(
            "cold staged artifacts", 128, prepared_compile_artifacts._create_staging_directory
        ),
        PreparedArtifactsCompileTestCase(
            "unavailable staging storage", 128, unavailable_staging_directory
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_existing_artifacts_when_rules_fail_then_staged_changes_are_not_published(
    test_case: PreparedArtifactsCompileTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prepared_compile_artifacts, "_create_staging_directory", test_case.staging_directory_factory
    )
    config_path: Path = tmp_path / "sqlbuild_project.toml"
    config: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL021"]\n'
    config_path.write_text(config, encoding="utf-8")
    models: Path = tmp_path / "models"
    models.mkdir()
    header: str = "MODEL (description 'Test model.', materialized table, contract enforced, columns (order_id (type INTEGER)));\n"
    for index in range(test_case.model_count):
        (models / f"orders_{index:03}.sql").write_text(
            header + "SELECT CAST(1 AS INTEGER) AS order_id\n", encoding="utf-8"
        )
    arguments: list[str] = [
        "--project-dir",
        str(tmp_path),
        "compile",
        "--no-cache",
        "--json",
        "--manifest",
    ]
    assert main(arguments) == test_case.expected_exit_code
    first: dict[str, object] = json.loads(capsys.readouterr().out)
    assert first["has_errors"] is False
    compiled: Path = tmp_path / "target" / "compiled"
    before: dict[Path, bytes] = {path: path.read_bytes() for path in compiled.rglob("*.sql")}
    modified_times: dict[Path, int] = {path: path.stat().st_mtime_ns for path in before}
    assert len(before) == test_case.model_count
    assert staging_directories(tmp_path / "target") == []
    stale: Path = compiled / "models" / "obsolete.sql"
    stale.write_text("SELECT 0\n", encoding="utf-8")
    (models / "orders_000.sql").write_text(
        header + "SELECT CAST(2 AS INTEGER) AS order_id\n", encoding="utf-8"
    )
    rules: Path = tmp_path / "rules"
    rules.mkdir()
    (rules / "orders.py").write_text(
        "from sqlbuild.rules import Finding, Model, RuleContext, rule\n"
        '@rule(code="XSQBRARCH001", message="Model rejected", remediation="Update the model.")\n'
        "def check_orders(*, model: Model, ctx: RuleContext) -> list[Finding]:\n"
        '    return [ctx.finding(subject=model)] if model.name == "orders_000" else []\n',
        encoding="utf-8",
    )
    config_path.write_text(
        config.replace('select = ["SQBRSQL021"]', 'select = ["XSQBRARCH001"]'), encoding="utf-8"
    )
    assert main(arguments) == 1
    failed: dict[str, object] = json.loads(capsys.readouterr().out)
    assert failed["has_errors"] is True
    assert {path: path.read_bytes() for path in before} == before
    assert stale.exists()
    assert staging_directories(tmp_path / "target") == []

    config_path.write_text(config, encoding="utf-8")
    assert main(arguments) == 0
    final: dict[str, object] = json.loads(capsys.readouterr().out)
    assert final["has_errors"] is False
    assert not stale.exists()
    changed: Path = compiled / "models" / "orders_000.sql"
    for path in modified_times.keys() - {changed}:
        assert path.stat().st_mtime_ns == modified_times[path]
        assert path.read_bytes() == before[path]
    assert staging_directories(tmp_path / "target") == []
    with duckdb.connect() as connection:
        assert connection.execute(changed.read_text(encoding="utf-8")).fetchall() == [(2,)]


@pytest.mark.parametrize(
    "test_case",
    (
        AbandonedStagingCompileTestCase(
            description="only staging whose owner lock is free is removed",
            model_count=128,
            abandoned=(".sqlbuild-staging-killed",),
            locked=(".sqlbuild-staging-running",),
            expected_remaining=(".sqlbuild-staging-running", ".sqlbuild-staging-running.lock"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_leftover_staging_when_compiling_then_only_abandoned_staging_is_removed(
    test_case: AbandonedStagingCompileTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_prepared_artifacts_project(project_dir=tmp_path, model_count=test_case.model_count)
    target: Path = tmp_path / "target"
    for name in test_case.abandoned:
        write_staging_directory(target_dir=target, name=name)
    with ExitStack() as owners:
        for name in test_case.locked:
            owners.enter_context(FileLock(target / f"{name}.lock"))
            write_staging_directory(target_dir=target, name=name)
        exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache", "--json"])
        remaining: list[str] = staging_directories(target)

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["has_errors"] is False
    assert tuple(remaining) == test_case.expected_remaining
    assert len(list((target / "compiled" / "models").glob("*.sql"))) == test_case.model_count


@pytest.mark.skipif(
    not has_second_filesystem(_SECOND_FILESYSTEM),
    reason="needs /dev/shm on a different filesystem from the temporary directory",
)
@pytest.mark.parametrize(
    "test_case",
    (CrossDeviceArtifactsCompileTestCase("compiled directory on another filesystem", 128),),
    ids=lambda case: case.description,
)
def test_given_compiled_dir_on_other_filesystem_when_compiling_then_artifacts_are_published(
    test_case: CrossDeviceArtifactsCompileTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_prepared_artifacts_project(project_dir=tmp_path, model_count=test_case.model_count)
    with TemporaryDirectory(dir=_SECOND_FILESYSTEM) as other_filesystem:
        compiled: Path = Path(other_filesystem) / "compiled"
        compiled.mkdir()
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "compiled").symlink_to(compiled, target_is_directory=True)
        exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache", "--json"])
        published: list[Path] = sorted((compiled / "models").glob("*.sql"))
        leftovers: list[str] = sorted(path.name for path in compiled.rglob(".*"))
        with duckdb.connect() as connection:
            last_value: object = connection.execute(
                published[-1].read_text(encoding="utf-8")
            ).fetchone()
        device_differs: bool = os.stat(compiled).st_dev != os.stat(tmp_path).st_dev

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == test_case.expected_exit_code
    assert payload["has_errors"] is False
    assert device_differs
    assert (tmp_path / "target" / "compiled").is_symlink()
    assert len(published) == test_case.model_count
    assert last_value == (test_case.model_count - 1,)
    assert leftovers == []
    assert staging_directories(tmp_path / "target") == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
