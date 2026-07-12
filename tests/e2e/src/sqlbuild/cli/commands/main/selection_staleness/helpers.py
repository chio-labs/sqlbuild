from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness._test_types import (
    SelectionStalenessE2ETestCase,
    SelectionStalenessEngine,
    SelectionStalenessEngineE2ETestCase,
    SelectionStalenessEngineOverride,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


def assert_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    if test_case.engine == "dbt":
        skip_unless_dbt_is_runnable()
    xfail_reason: str | None = xfail_reason_for_engine(
        engine=test_case.engine,
        test_case=test_case.scenario,
    )
    if xfail_reason is not None:
        try:
            _assert_selection_staleness_case(tmp_path=tmp_path, test_case=test_case)
        except AssertionError:
            pytest.xfail(xfail_reason)
        pytest.fail(f"XPASS(strict): {xfail_reason}")
    _assert_selection_staleness_case(tmp_path=tmp_path, test_case=test_case)


def expand_selection_staleness_engines(
    scenarios: tuple[SelectionStalenessE2ETestCase, ...],
) -> list[tuple[SelectionStalenessE2ETestCase, SelectionStalenessEngine]]:
    cases: list[tuple[SelectionStalenessE2ETestCase, SelectionStalenessEngine]] = []
    for scenario in scenarios:
        for engine in scenario.engines:
            cases.append((scenario, engine))
    return cases


def _assert_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    rendered_case: SelectionStalenessE2ETestCase = render_selection_staleness_case(
        engine=test_case.engine,
        test_case=test_case.scenario,
    )
    if test_case.engine == "native":
        assert_native_selection_staleness_case(tmp_path=tmp_path, test_case=rendered_case)
        return
    assert_dbt_selection_staleness_case(tmp_path=tmp_path, test_case=rendered_case)


def render_selection_staleness_case(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> SelectionStalenessE2ETestCase:
    override: SelectionStalenessEngineOverride = test_case.engine_overrides.get(
        engine, SelectionStalenessEngineOverride()
    )
    return SelectionStalenessE2ETestCase(
        description=test_case.description,
        project_name=f"{engine}_{test_case.project_name}",
        scenario=test_case.scenario,
        graph=test_case.graph,
        exact_command=override.exact_command
        or _default_exact_command(engine=engine, test_case=test_case),
        repair_command=override.repair_command
        or _default_repair_command(engine=engine, test_case=test_case),
        expected_exact_stdout_fragments=(
            override.expected_exact_stdout_fragments
            if override.expected_exact_stdout_fragments is not None
            else _default_exact_fragments(engine=engine, test_case=test_case)
        ),
        unexpected_exact_stdout_fragments=(
            override.unexpected_exact_stdout_fragments
            if override.unexpected_exact_stdout_fragments is not None
            else _default_unexpected_exact_fragments(engine=engine, test_case=test_case)
        ),
        expected_repair_stdout_fragments=(
            override.expected_repair_stdout_fragments
            if override.expected_repair_stdout_fragments is not None
            else _default_repair_fragments(engine=engine, test_case=test_case)
        ),
        unexpected_repair_stdout_fragments=(
            override.unexpected_repair_stdout_fragments
            if override.unexpected_repair_stdout_fragments is not None
            else _default_unexpected_repair_fragments(engine=engine)
        ),
        expected_rows_after_baseline=test_case.expected_rows_after_baseline,
        expected_rows_after_exact=test_case.expected_rows_after_exact,
        expected_rows_after_second_exact=test_case.expected_rows_after_second_exact,
        expected_rows_after_repair=test_case.expected_rows_after_repair,
        leaf_materialization=test_case.leaf_materialization,
        repeat_exact_selection=test_case.repeat_exact_selection,
        engine_overrides=test_case.engine_overrides,
        notes=test_case.notes,
    )


def xfail_reason_for_engine(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> str | None:
    override: SelectionStalenessEngineOverride | None = test_case.engine_overrides.get(engine)
    return override.xfail_reason if override is not None else None


def assert_native_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessE2ETestCase
) -> None:
    project_dir: Path = prepare_native_selection_staleness_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        scenario=test_case.scenario,
        amount_cents=100,
        fact_adjustment=0,
        leaf_materialization=test_case.leaf_materialization,
    )
    baseline_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert baseline_result.returncode == 0, baseline_result.stdout + baseline_result.stderr
    assert_native_fact_rows(
        project_dir=project_dir, expected_rows=test_case.expected_rows_after_baseline
    )

    mutate_native_selection_staleness_project(
        project_dir=project_dir,
        scenario=test_case.scenario,
        amount_cents=125,
        fact_adjustment=1 if test_case.scenario == "leaf_own_change" else 0,
        leaf_materialization=test_case.leaf_materialization,
    )

    exact_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.exact_command,
        project_dir=project_dir,
    )
    assert exact_result.returncode == 0, exact_result.stdout + exact_result.stderr
    assert_stdout_fragments(
        result=exact_result,
        expected_fragments=test_case.expected_exact_stdout_fragments,
        unexpected_fragments=test_case.unexpected_exact_stdout_fragments,
    )
    assert_native_fact_rows(
        project_dir=project_dir, expected_rows=test_case.expected_rows_after_exact
    )
    if test_case.repeat_exact_selection:
        second_exact_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.exact_command,
            project_dir=project_dir,
        )
        assert second_exact_result.returncode == 0, (
            second_exact_result.stdout + second_exact_result.stderr
        )
        assert_stdout_fragments(
            result=second_exact_result,
            expected_fragments=test_case.expected_exact_stdout_fragments,
            unexpected_fragments=test_case.unexpected_exact_stdout_fragments,
        )
        assert_native_fact_rows(
            project_dir=project_dir,
            expected_rows=test_case.expected_rows_after_second_exact
            or test_case.expected_rows_after_exact,
        )

    repair_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.repair_command,
        project_dir=project_dir,
    )
    assert repair_result.returncode == 0, repair_result.stdout + repair_result.stderr
    assert_stdout_fragments(
        result=repair_result,
        expected_fragments=test_case.expected_repair_stdout_fragments,
        unexpected_fragments=test_case.unexpected_repair_stdout_fragments,
    )
    assert_native_fact_rows(
        project_dir=project_dir, expected_rows=test_case.expected_rows_after_repair
    )


def _default_exact_command(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> tuple[str, ...]:
    prefix: tuple[str, ...] = ("--no-color", "build")
    if engine == "dbt":
        prefix = ("--no-color", "dbt", "build")
    if test_case.scenario == "selected_root_leaf":
        return (*prefix, "--select", "raw_orders_model", "fact_orders")
    if test_case.scenario == "mixed_parents":
        return (*prefix, "--select", "selected_parent", "fact_orders")
    return (*prefix, "--select", "fact_orders")


def _default_repair_command(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> tuple[str, ...]:
    prefix: tuple[str, ...] = ("--no-color", "build")
    if engine == "dbt":
        prefix = ("--no-color", "dbt", "build")
    if test_case.scenario == "later_unscoped_repair":
        return prefix
    return (*prefix, "--select", "+fact_orders")


def _default_exact_fragments(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> tuple[str, ...]:
    model_label: str = "selected model 'fact_orders' will build on"
    if engine == "dbt":
        model_label = "selected dbt model 'fact_orders' will build on"
    if test_case.scenario == "direct_parent":
        return (model_label, _changed_parent_fragment(engine=engine, name="stg_orders"))
    if test_case.scenario == "seed_parent":
        if engine == "dbt":
            return (model_label, "- raw_orders")
        return (model_label, _stale_parent_fragment(engine=engine, name="order_amounts"))
    if test_case.scenario == "multi_hop":
        return (
            model_label,
            _changed_parent_fragment(engine=engine, name="raw_orders_model"),
            _stale_parent_fragment(engine=engine, name="stg_orders"),
        )
    if test_case.scenario == "leaf_own_change":
        return (
            "fact_orders",
            model_label,
            _changed_parent_fragment(engine=engine, name="stg_orders"),
        )
    if test_case.scenario == "selected_root_leaf":
        return (
            "raw_orders_model",
            model_label,
            _stale_parent_fragment(engine=engine, name="stg_orders"),
        )
    if test_case.scenario == "mixed_parents":
        return (
            "selected_parent",
            "fact_orders",
            model_label,
            _changed_parent_fragment(engine=engine, name="unselected_parent"),
        )
    if test_case.scenario == "plan_no_mutation":
        return (
            "Plan ready (0 selected)",
            model_label,
            _changed_parent_fragment(engine=engine, name="stg_orders"),
        )
    if test_case.scenario == "diamond":
        return (
            model_label,
            _stale_parent_fragment(engine=engine, name="stg_orders_a"),
            _stale_parent_fragment(engine=engine, name="stg_orders_b"),
        )
    return (model_label,)


def _default_unexpected_exact_fragments(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> tuple[str, ...]:
    model_prefix: str = "table    " if engine == "native" else "model    "
    if test_case.scenario in {
        "direct_parent",
        "seed_parent",
        "leaf_own_change",
        "plan_no_mutation",
    }:
        return (f"{model_prefix} stg_orders",)
    if test_case.scenario == "multi_hop":
        return (f"{model_prefix} raw_orders_model", f"{model_prefix} stg_orders")
    if test_case.scenario == "selected_root_leaf":
        return (f"{model_prefix} stg_orders",)
    if test_case.scenario == "mixed_parents":
        return ("- selected_parent",)
    if test_case.scenario == "diamond":
        return (f"{model_prefix} stg_orders_a", f"{model_prefix} stg_orders_b")
    return ()


def _default_repair_fragments(
    *, engine: SelectionStalenessEngine, test_case: SelectionStalenessE2ETestCase
) -> tuple[str, ...]:
    if engine == "dbt":
        if test_case.scenario == "diamond":
            return ("Upstream changed", "stg_orders_a", "stg_orders_b")
        if test_case.scenario == "mixed_parents":
            return ("Upstream changed", "unselected_parent")
        if test_case.scenario in {"selected_root_leaf", "seed_parent"}:
            return ("stg_orders", "fact_orders")
        return ("Upstream changed", "stg_orders", "fact_orders")
    if test_case.scenario == "multi_hop":
        return ("Plan ready (3 selected)", "table     raw_orders_model", "table     stg_orders")
    if test_case.scenario == "seed_parent":
        return ("Plan ready (3 selected)", "seed      order_amounts", "table     stg_orders")
    if test_case.scenario == "diamond":
        return ("Plan ready (4 selected)", "table     stg_orders_a", "table     stg_orders_b")
    if test_case.scenario in {"selected_root_leaf", "mixed_parents", "later_unscoped_repair"}:
        return ("Plan ready (2 selected)",)
    return ("Plan ready (2 selected)", "table     stg_orders")


def _default_unexpected_repair_fragments(*, engine: SelectionStalenessEngine) -> tuple[str, ...]:
    if engine == "dbt":
        return ("selected dbt model 'fact_orders' will build on",)
    return ("selected model 'fact_orders' will build on",)


def _changed_parent_fragment(*, engine: SelectionStalenessEngine, name: str) -> str:
    del engine
    return f"- {name}"


def _stale_parent_fragment(*, engine: SelectionStalenessEngine, name: str) -> str:
    del engine
    return f"- {name}"


def assert_dbt_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessE2ETestCase
) -> None:
    project_dir: Path = prepare_dbt_selection_staleness_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        scenario=test_case.scenario,
        amount_cents=100,
        fact_adjustment=0,
        leaf_materialization=test_case.leaf_materialization,
    )
    baseline_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert baseline_result.returncode == 0, baseline_result.stdout + baseline_result.stderr
    assert_dbt_fact_rows(
        project_dir=project_dir, expected_rows=test_case.expected_rows_after_baseline
    )

    mutate_dbt_selection_staleness_project(
        project_dir=project_dir,
        scenario=test_case.scenario,
        amount_cents=125,
        fact_adjustment=1 if test_case.scenario == "leaf_own_change" else 0,
        leaf_materialization=test_case.leaf_materialization,
    )

    exact_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.exact_command,
        project_dir=project_dir,
    )
    assert exact_result.returncode == 0, exact_result.stdout + exact_result.stderr
    assert_stdout_fragments(
        result=exact_result,
        expected_fragments=test_case.expected_exact_stdout_fragments,
        unexpected_fragments=test_case.unexpected_exact_stdout_fragments,
    )
    assert_dbt_fact_rows(project_dir=project_dir, expected_rows=test_case.expected_rows_after_exact)
    if test_case.repeat_exact_selection:
        second_exact_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.exact_command,
            project_dir=project_dir,
        )
        assert second_exact_result.returncode == 0, (
            second_exact_result.stdout + second_exact_result.stderr
        )
        assert_stdout_fragments(
            result=second_exact_result,
            expected_fragments=test_case.expected_exact_stdout_fragments,
            unexpected_fragments=test_case.unexpected_exact_stdout_fragments,
        )
        assert_dbt_fact_rows(
            project_dir=project_dir,
            expected_rows=test_case.expected_rows_after_second_exact
            or test_case.expected_rows_after_exact,
        )

    repair_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.repair_command,
        project_dir=project_dir,
    )
    assert repair_result.returncode == 0, repair_result.stdout + repair_result.stderr
    assert_stdout_fragments(
        result=repair_result,
        expected_fragments=test_case.expected_repair_stdout_fragments,
        unexpected_fragments=test_case.unexpected_repair_stdout_fragments,
    )
    assert_dbt_fact_rows(
        project_dir=project_dir, expected_rows=test_case.expected_rows_after_repair
    )


def prepare_native_selection_staleness_project(
    *,
    tmp_path: Path,
    project_name: str,
    scenario: str,
    amount_cents: int,
    fact_adjustment: int,
    leaf_materialization: str,
) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": _native_project_toml(project_name=project_name),
            **_native_model_files(
                scenario=scenario,
                amount_cents=amount_cents,
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        },
    )


def mutate_native_selection_staleness_project(
    *,
    project_dir: Path,
    scenario: str,
    amount_cents: int,
    fact_adjustment: int,
    leaf_materialization: str,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in _native_model_files(
        scenario=scenario,
        amount_cents=amount_cents,
        fact_adjustment=fact_adjustment,
        leaf_materialization=leaf_materialization,
    ).items():
        (project_dir / relative_path).write_text(contents, encoding="utf-8")


def prepare_dbt_selection_staleness_project(
    *,
    tmp_path: Path,
    project_name: str,
    scenario: str,
    amount_cents: int,
    fact_adjustment: int,
    leaf_materialization: str,
) -> Path:
    root_dir: Path = tmp_path / project_name
    dbt_project_dir: Path = root_dir / "dbt_project"
    dbt_seeds_dir: Path = dbt_project_dir / "seeds"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    (dbt_project_dir / "models").mkdir(parents=True)
    dbt_seeds_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_project_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "selection_staleness.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "seed-paths: ['seeds']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "selection_staleness_dbt"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "selection_staleness.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n',
        encoding="utf-8",
    )
    mutate_dbt_selection_staleness_project(
        project_dir=sqlbuild_project_dir,
        scenario=scenario,
        amount_cents=amount_cents,
        fact_adjustment=fact_adjustment,
        leaf_materialization=leaf_materialization,
    )
    return sqlbuild_project_dir


def mutate_dbt_selection_staleness_project(
    *,
    project_dir: Path,
    scenario: str,
    amount_cents: int,
    fact_adjustment: int,
    leaf_materialization: str,
) -> None:
    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    relative_path: str
    contents: str
    for relative_path, contents in _dbt_model_files(
        scenario=scenario,
        amount_cents=amount_cents,
        fact_adjustment=fact_adjustment,
        leaf_materialization=leaf_materialization,
    ).items():
        (dbt_models_dir / relative_path).write_text(contents, encoding="utf-8")


def assert_stdout_fragments(
    *,
    result: subprocess.CompletedProcess[str],
    expected_fragments: tuple[str, ...],
    unexpected_fragments: tuple[str, ...],
) -> None:
    fragment: str
    output: str = result.stdout + result.stderr
    for fragment in expected_fragments:
        assert fragment in output, output
    for fragment in unexpected_fragments:
        assert fragment not in output, output


def assert_native_fact_rows(
    *, project_dir: Path, expected_rows: tuple[tuple[object, ...], ...]
) -> None:
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_dollars FROM fact_orders ORDER BY order_id",
    )
    assert rows == list(expected_rows)


def assert_dbt_fact_rows(
    *, project_dir: Path, expected_rows: tuple[tuple[object, ...], ...]
) -> None:
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "selection_staleness.duckdb",
        sql="SELECT order_id, amount_dollars FROM main.fact_orders ORDER BY order_id",
    )
    assert rows == list(expected_rows)


def _native_project_toml(*, project_name: str) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        'database = "warehouse.duckdb"\n'
    )


def _native_model_files(
    *, scenario: str, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> dict[str, str]:
    files: dict[str, str] = {}
    if scenario in {"multi_hop", "selected_root_leaf"}:
        files["models/raw_orders_model.sql"] = _native_raw_orders_model_sql(
            amount_cents=amount_cents
        )
        files["models/stg_orders.sql"] = (
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __ref("raw_orders_model")\n'
        )
    elif scenario == "mixed_parents":
        files["models/selected_parent.sql"] = _native_parent_model_sql(
            model_name="selected_parent", amount_cents=amount_cents
        )
        files["models/unselected_parent.sql"] = _native_parent_model_sql(
            model_name="unselected_parent", amount_cents=amount_cents
        )
        files["models/fact_orders.sql"] = _native_mixed_parent_fact_orders_sql(
            leaf_materialization=leaf_materialization
        )
        return files
    elif scenario == "diamond":
        files["models/raw_orders_model.sql"] = _native_raw_orders_model_sql(
            amount_cents=amount_cents
        )
        files["models/stg_orders_a.sql"] = (
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __ref("raw_orders_model")\n'
        )
        files["models/stg_orders_b.sql"] = (
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __ref("raw_orders_model")\n'
        )
        files["models/fact_orders.sql"] = _native_diamond_fact_orders_sql(
            leaf_materialization=leaf_materialization
        )
        return files
    elif scenario == "seed_parent":
        files["seeds/schema.yml"] = (
            "seeds:\n"
            "  - name: order_amounts\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        type: INTEGER\n"
            "      - name: amount_cents\n"
            "        type: INTEGER\n"
        )
        files["seeds/order_amounts.csv"] = f"order_id,amount_cents\n1,{amount_cents}\n"
        files["models/stg_orders.sql"] = (
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
        )
    else:
        files["models/stg_orders.sql"] = _native_stg_orders_sql(amount_cents=amount_cents)
    files["models/fact_orders.sql"] = _native_fact_orders_sql(
        fact_adjustment=fact_adjustment,
        leaf_materialization=leaf_materialization,
    )
    return files


def _native_stg_orders_sql(*, amount_cents: int) -> str:
    return f"MODEL (materialized table);\n\nSELECT 1 AS order_id, {amount_cents} AS amount_cents\n"


def _native_raw_orders_model_sql(*, amount_cents: int) -> str:
    return f"MODEL (materialized table);\n\nSELECT 1 AS order_id, {amount_cents} AS amount_cents\n"


def _native_parent_model_sql(*, model_name: str, amount_cents: int) -> str:
    return (
        "MODEL (materialized table);\n\n"
        f"SELECT 1 AS order_id, {amount_cents} AS {model_name}_amount_cents\n"
    )


def _native_fact_orders_sql(*, fact_adjustment: int, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  order_id,\n"
        f"  amount_cents / 100.0 + {fact_adjustment} AS amount_dollars\n"
        'FROM __ref("stg_orders")\n'
    )


def _native_mixed_parent_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  s.order_id,\n"
        "  (s.selected_parent_amount_cents + u.unselected_parent_amount_cents) "
        " / 200.0 AS amount_dollars\n"
        'FROM __ref("selected_parent") s\n'
        'JOIN __ref("unselected_parent") u USING (order_id)\n'
    )


def _native_diamond_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  a.order_id,\n"
        "  (a.amount_cents + b.amount_cents) / 200.0 AS amount_dollars\n"
        'FROM __ref("stg_orders_a") a\n'
        'JOIN __ref("stg_orders_b") b USING (order_id)\n'
    )


def _dbt_model_files(
    *, scenario: str, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> dict[str, str]:
    files: dict[str, str] = {}
    if scenario in {"multi_hop", "selected_root_leaf"}:
        files["raw_orders_model.sql"] = _dbt_source_model_sql(amount_cents=amount_cents)
        files["stg_orders.sql"] = (
            "select order_id, amount_cents from {{ ref('raw_orders_model') }}\n"
        )
    elif scenario == "mixed_parents":
        files["selected_parent.sql"] = _dbt_parent_model_sql(
            model_name="selected_parent", amount_cents=amount_cents
        )
        files["unselected_parent.sql"] = _dbt_parent_model_sql(
            model_name="unselected_parent", amount_cents=amount_cents
        )
        files["fact_orders.sql"] = _dbt_mixed_parent_fact_orders_sql(
            leaf_materialization=leaf_materialization
        )
        return files
    elif scenario == "diamond":
        files["raw_orders_model.sql"] = _dbt_source_model_sql(amount_cents=amount_cents)
        files["stg_orders_a.sql"] = (
            "select order_id, amount_cents from {{ ref('raw_orders_model') }}\n"
        )
        files["stg_orders_b.sql"] = (
            "select order_id, amount_cents from {{ ref('raw_orders_model') }}\n"
        )
        files["fact_orders.sql"] = _dbt_diamond_fact_orders_sql(
            leaf_materialization=leaf_materialization
        )
        return files
    elif scenario == "seed_parent":
        files["../seeds/raw_orders.csv"] = f"order_id,amount_cents\n1,{amount_cents}\n"
        files["stg_orders.sql"] = "select order_id, amount_cents from {{ ref('raw_orders') }}\n"
    else:
        files["stg_orders.sql"] = _dbt_source_model_sql(amount_cents=amount_cents)
    files["fact_orders.sql"] = _dbt_fact_orders_sql(
        fact_adjustment=fact_adjustment,
        leaf_materialization=leaf_materialization,
    )
    return files


def _dbt_source_model_sql(*, amount_cents: int) -> str:
    return f"select 1 as order_id, {amount_cents} as amount_cents\n"


def _dbt_parent_model_sql(*, model_name: str, amount_cents: int) -> str:
    return f"select 1 as order_id, {amount_cents} as {model_name}_amount_cents\n"


def _dbt_fact_orders_sql(*, fact_adjustment: int, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  order_id,\n"
        f"  amount_cents / 100.0 + {fact_adjustment} as amount_dollars\n"
        "from {{ ref('stg_orders') }}\n"
    )


def _dbt_mixed_parent_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  s.order_id,\n"
        "  (s.selected_parent_amount_cents + u.unselected_parent_amount_cents) "
        " / 200.0 as amount_dollars\n"
        "from {{ ref('selected_parent') }} s\n"
        "join {{ ref('unselected_parent') }} u using (order_id)\n"
    )


def _dbt_diamond_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  a.order_id,\n"
        "  (a.amount_cents + b.amount_cents) / 200.0 as amount_dollars\n"
        "from {{ ref('stg_orders_a') }} a\n"
        "join {{ ref('stg_orders_b') }} b using (order_id)\n"
    )
