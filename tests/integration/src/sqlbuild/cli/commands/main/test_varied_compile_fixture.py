"""Execute diverse generated queries and verify unchanged-cache equivalence."""

import json
from pathlib import Path

import pytest

from scripts.cold_compile_performance._helpers.varied_project import write_varied_compile_project
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    VariedCompileFixtureTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (VariedCompileFixtureTestCase("varied windows arrays and shared dependencies", 64, 0),),
    ids=lambda case: case.description,
)
def test_given_varied_fixture_when_compiling_warm_and_executing_tests_then_results_match(
    test_case: VariedCompileFixtureTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project: Path = tmp_path / "orders"
    write_varied_compile_project(project_dir=project, model_count=test_case.model_count)
    config: Path = project / "sqlbuild_project.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        .replace('adapter = "snowflake"', 'adapter = "duckdb"')
        .replace('database = "warehouse"\n', "")
        .replace('schema = "analytics"', 'schema = "main"')
        + f'\n[connection]\ndatabase = "{project / "orders.duckdb"}"\n',
        encoding="utf-8",
    )
    arguments: list[str] = ["--project-dir", str(project), "compile", "--json"]
    cold_exit: int = main(arguments)
    cold_output: str = capsys.readouterr().out
    assert cold_exit == test_case.expected_exit_code, cold_output
    cold: dict = json.loads(cold_output)
    compiled: Path = project / "target" / "compiled"
    artifacts: dict[Path, bytes] = {path: path.read_bytes() for path in compiled.rglob("*.sql")}
    warm_exit: int = main(arguments)
    warm_output: str = capsys.readouterr().out
    assert warm_exit == test_case.expected_exit_code, warm_output
    warm: dict = json.loads(warm_output)
    assert cold["resources"] == warm["resources"]
    assert cold["diagnostics"] == warm["diagnostics"] == []
    assert (
        warm["compile_timings"]["analysis_batch_cache_hits"]
        + warm["compile_timings"]["analysis_entry_cache_hits"]
    ) == test_case.model_count
    assert warm["compile_timings"]["analysis_cache_misses"] == 0
    assert {path: path.read_bytes() for path in compiled.rglob("*.sql")} == artifacts
    built: int = main(
        [
            "--project-dir",
            str(project),
            "build",
            "--select",
            "fn_00000",
            "--no-tests",
            "--no-audits",
        ]
    )
    captured: str = "".join(capsys.readouterr())
    assert built == test_case.expected_exit_code, captured
    tested: int = main(["--project-dir", str(project), "test"])
    captured = "".join(capsys.readouterr())
    assert tested == test_case.expected_exit_code, captured


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
