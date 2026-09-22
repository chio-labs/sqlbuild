"""Real cold compilation preserves publication gates and unchanged artifact files."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest

from sqlbuild.cli.commands.classes import prepared_compile_artifacts
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    PreparedArtifactsCompileTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import unavailable_artifact_directory


@pytest.mark.parametrize(
    "test_case",
    (
        PreparedArtifactsCompileTestCase("cold staged artifacts", 128, TemporaryDirectory),
        PreparedArtifactsCompileTestCase(
            "unavailable temporary storage", 128, unavailable_artifact_directory
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
        prepared_compile_artifacts, "TemporaryDirectory", test_case.temporary_directory_factory
    )
    config_path: Path = tmp_path / "sqlbuild_project.toml"
    config: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    config_path.write_text(config, encoding="utf-8")
    models: Path = tmp_path / "models"
    models.mkdir()
    header: str = (
        "MODEL (materialized table, contract enforced, columns (order_id (type INTEGER)));\n"
    )
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
        config.replace("select = []", 'select = ["XSQBRARCH001"]'), encoding="utf-8"
    )
    assert main(arguments) == 1
    failed: dict[str, object] = json.loads(capsys.readouterr().out)
    assert failed["has_errors"] is True
    assert {path: path.read_bytes() for path in before} == before
    assert stale.exists()

    config_path.write_text(config, encoding="utf-8")
    assert main(arguments) == 0
    final: dict[str, object] = json.loads(capsys.readouterr().out)
    assert final["has_errors"] is False
    assert not stale.exists()
    changed: Path = compiled / "models" / "orders_000.sql"
    for path in modified_times.keys() - {changed}:
        assert path.stat().st_mtime_ns == modified_times[path]
        assert path.read_bytes() == before[path]
    with duckdb.connect() as connection:
        assert connection.execute(changed.read_text(encoding="utf-8")).fetchall() == [(2,)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
