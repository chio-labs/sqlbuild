"""Kata cache and suppression behavior tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataConfig, KataResult, RuleExemption, RuleIgnore
from tests.unit.src.sqlbuild.kata_engine.main.evaluate._test_types import KataBehaviorTestCase
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project


@pytest.mark.parametrize(
    "test_case",
    [
        KataBehaviorTestCase(
            description="unchanged built-in inputs hit cache",
            expected_cache_hits=1,
            expected_cache_misses=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_builtin_inputs_when_evaluating_twice_then_second_run_hits_cache(
    tmp_path: Path,
    test_case: KataBehaviorTestCase,
) -> None:
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path="models/mart/market__mart__prices.sql",
        sql="SELECT * FROM prices",
        config_values={},
    )
    config: KataConfig = KataConfig(select=("KTS001",))

    first: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)
    second: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert first.cache_hits == 0
    assert first.cache_misses == 1
    assert second.cache_hits == test_case.expected_cache_hits
    assert second.cache_misses == test_case.expected_cache_misses
    assert second.faults == first.faults


@pytest.mark.parametrize(
    "test_case",
    [
        KataBehaviorTestCase(
            description="changed authored SQL invalidates equivalent compiled SQL",
            expected_fault_count=1,
            expected_cache_hits=0,
            expected_cache_misses=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_authored_sql_changes_when_compiled_sql_is_same_then_cache_is_invalidated(
    tmp_path: Path,
    test_case: KataBehaviorTestCase,
) -> None:
    compiled_sql: str = "WITH final AS (SELECT 1 AS id) SELECT id FROM final WHERE id > 7"
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path="models/mart/market__mart__prices.sql",
        sql=compiled_sql,
        config_values={},
    )
    constant_source: str = compiled_sql.replace("7", '@const("minimum_id")')
    first_project: CompiledProject = replace(
        project,
        models=(replace(project.models[0], authored_sql=constant_source),),
    )
    bare_project: CompiledProject = replace(
        project,
        models=(replace(project.models[0], authored_sql=compiled_sql),),
    )
    config: KataConfig = KataConfig(select=("KTH002",))
    _ = evaluate(project=first_project, config=config, project_dir=tmp_path)

    result: KataResult = evaluate(project=bare_project, config=config, project_dir=tmp_path)

    assert len(result.faults) == test_case.expected_fault_count
    assert result.cache_hits == test_case.expected_cache_hits
    assert result.cache_misses == test_case.expected_cache_misses


@pytest.mark.parametrize(
    "test_case",
    [
        KataBehaviorTestCase(
            description="matching exact exception suppresses fault",
            expected_fault_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_exact_exception_when_fault_exists_then_suppresses_fault(
    tmp_path: Path,
    test_case: KataBehaviorTestCase,
) -> None:
    relative_path = "models/mart/market__mart__prices.sql"
    target: Path = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text("SELECT * FROM prices\n", encoding="utf-8")
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path=relative_path,
        sql="SELECT * FROM prices",
        config_values={},
    )
    config: KataConfig = KataConfig(
        select=("KTS001",),
        rule_exceptions=(
            RuleExemption(
                rule="KTS001",
                path=relative_path,
                reason="Migration is tracked",
            ),
        ),
    )

    result: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert len(result.faults) == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        KataBehaviorTestCase(
            description="stale exact exception fails",
            expected_error_pattern="stale kata exception",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_stale_exact_exception_when_evaluating_then_raises_error(
    tmp_path: Path,
    test_case: KataBehaviorTestCase,
) -> None:
    relative_path = "models/mart/market__mart__prices.sql"
    target: Path = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text("WITH final AS (SELECT 1 AS id) SELECT id FROM final\n", encoding="utf-8")
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path=relative_path,
        sql="WITH final AS (SELECT 1 AS id) SELECT id FROM final",
        config_values={},
    )
    config: KataConfig = KataConfig(
        select=("KTS001",),
        rule_exceptions=(
            RuleExemption(rule="KTS001", path=relative_path, reason="Migration is tracked"),
        ),
    )

    with pytest.raises(KataError, match=test_case.expected_error_pattern):
        evaluate(project=project, config=config, project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        KataBehaviorTestCase(
            description="scoped ignore suppresses matching path",
            expected_fault_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_ignore_when_fault_exists_then_suppresses_fault(
    tmp_path: Path,
    test_case: KataBehaviorTestCase,
) -> None:
    relative_path = "models/legacy/market__mart__prices.sql"
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path=relative_path,
        sql="SELECT * FROM prices",
        config_values={},
    )
    config: KataConfig = KataConfig(
        select=("KTS001",),
        rule_ignores=(
            RuleIgnore(
                rules=("KTS",),
                paths=("models/legacy/**",),
                reason="Legacy migration boundary",
            ),
        ),
    )

    result: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert len(result.faults) == test_case.expected_fault_count
