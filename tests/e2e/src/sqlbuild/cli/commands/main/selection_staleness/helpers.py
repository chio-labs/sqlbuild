from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.selection_staleness._test_types import (
    SelectionStalenessEngineE2ETestCase,
    SelectionStalenessFiles,
    SelectionStalenessRows,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


def assert_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    test_case.runner(tmp_path=tmp_path, test_case=test_case)


def assert_native_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": native_project_toml(project_name=test_case.project_name),
            **dict(test_case.baseline_files),
        },
    )
    execute_selection_staleness_case(project_dir=project_dir, test_case=test_case)


def assert_dbt_selection_staleness_case(
    *, tmp_path: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_selection_staleness_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        baseline_files=test_case.baseline_files,
    )
    execute_selection_staleness_case(project_dir=project_dir, test_case=test_case)


def execute_selection_staleness_case(
    *, project_dir: Path, test_case: SelectionStalenessEngineE2ETestCase
) -> None:
    baseline_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.baseline_command,
        project_dir=project_dir,
    )
    assert_success(result=baseline_result)
    assert_fact_rows(
        project_dir=project_dir,
        database_relative_path=test_case.database_relative_path,
        fact_rows_query=test_case.fact_rows_query,
        expected_rows=test_case.expected_rows_after_baseline,
    )
    write_selection_staleness_files(
        project_dir=project_dir,
        files=test_case.mutated_files,
    )

    exact_command: tuple[str, ...]
    expected_rows: SelectionStalenessRows
    for exact_command, expected_rows in zip(
        test_case.exact_commands,
        test_case.expected_rows_after_exact_commands,
        strict=True,
    ):
        exact_result: subprocess.CompletedProcess[str] = run_sqb(
            command=exact_command,
            project_dir=project_dir,
        )
        assert_success(result=exact_result)
        assert_stdout_fragments(
            result=exact_result,
            expected_fragments=test_case.expected_exact_stdout_fragments,
            unexpected_fragments=test_case.unexpected_exact_stdout_fragments,
        )
        assert_fact_rows(
            project_dir=project_dir,
            database_relative_path=test_case.database_relative_path,
            fact_rows_query=test_case.fact_rows_query,
            expected_rows=expected_rows,
        )

    repair_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.repair_command,
        project_dir=project_dir,
    )
    assert_success(result=repair_result)
    assert_stdout_fragments(
        result=repair_result,
        expected_fragments=test_case.expected_repair_stdout_fragments,
        unexpected_fragments=test_case.unexpected_repair_stdout_fragments,
    )
    assert_fact_rows(
        project_dir=project_dir,
        database_relative_path=test_case.database_relative_path,
        fact_rows_query=test_case.fact_rows_query,
        expected_rows=test_case.expected_rows_after_repair,
    )


def assert_success(*, result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def assert_stdout_fragments(
    *,
    result: subprocess.CompletedProcess[str],
    expected_fragments: tuple[str, ...],
    unexpected_fragments: tuple[str, ...],
) -> None:
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in expected_fragments:
        assert fragment in output, output
    for fragment in unexpected_fragments:
        assert fragment not in output, output


def assert_fact_rows(
    *,
    project_dir: Path,
    database_relative_path: Path,
    fact_rows_query: str,
    expected_rows: SelectionStalenessRows,
) -> None:
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / database_relative_path,
        sql=fact_rows_query,
    )
    assert rows == list(expected_rows)


def prepare_dbt_selection_staleness_project(
    *,
    tmp_path: Path,
    project_name: str,
    baseline_files: SelectionStalenessFiles,
) -> Path:
    root_dir: Path = tmp_path / project_name
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    (dbt_project_dir / "models").mkdir(parents=True)
    (dbt_project_dir / "seeds").mkdir(parents=True)
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
    write_selection_staleness_files(
        project_dir=sqlbuild_project_dir,
        files=baseline_files,
    )
    return sqlbuild_project_dir


def write_selection_staleness_files(*, project_dir: Path, files: SelectionStalenessFiles) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in files:
        destination: Path = project_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")


def native_project_toml(*, project_name: str) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        'database = "warehouse.duckdb"\n'
    )


def native_direct_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "models/stg_orders.sql",
            native_source_model_sql(amount_cents=amount_cents),
        ),
        (
            "models/fact_orders.sql",
            native_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def native_multi_hop_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "models/raw_orders_model.sql",
            native_source_model_sql(amount_cents=amount_cents),
        ),
        (
            "models/stg_orders.sql",
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __ref("raw_orders_model")\n',
        ),
        (
            "models/fact_orders.sql",
            native_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def native_mixed_parent_files(
    *, amount_cents: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "models/selected_parent.sql",
            native_parent_model_sql(model_name="selected_parent", amount_cents=amount_cents),
        ),
        (
            "models/unselected_parent.sql",
            native_parent_model_sql(model_name="unselected_parent", amount_cents=amount_cents),
        ),
        (
            "models/fact_orders.sql",
            native_mixed_parent_fact_orders_sql(leaf_materialization=leaf_materialization),
        ),
    )


def native_diamond_files(
    *, amount_cents: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    intermediate_sql: str = (
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount_cents FROM __ref("raw_orders_model")\n'
    )
    return (
        (
            "models/raw_orders_model.sql",
            native_source_model_sql(amount_cents=amount_cents),
        ),
        ("models/stg_orders_a.sql", intermediate_sql),
        ("models/stg_orders_b.sql", intermediate_sql),
        (
            "models/fact_orders.sql",
            native_diamond_fact_orders_sql(leaf_materialization=leaf_materialization),
        ),
    )


def native_seed_parent_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "seeds/schema.yml",
            "seeds:\n"
            "  - name: order_amounts\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        type: INTEGER\n"
            "      - name: amount_cents\n"
            "        type: INTEGER\n",
        ),
        (
            "seeds/order_amounts.csv",
            f"order_id,amount_cents\n1,{amount_cents}\n",
        ),
        (
            "models/stg_orders.sql",
            "MODEL (materialized table);\n\n"
            'SELECT order_id, amount_cents FROM __seed("order_amounts")\n',
        ),
        (
            "models/fact_orders.sql",
            native_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def dbt_direct_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "../dbt_project/models/stg_orders.sql",
            dbt_source_model_sql(amount_cents=amount_cents),
        ),
        (
            "../dbt_project/models/fact_orders.sql",
            dbt_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def dbt_multi_hop_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "../dbt_project/models/raw_orders_model.sql",
            dbt_source_model_sql(amount_cents=amount_cents),
        ),
        (
            "../dbt_project/models/stg_orders.sql",
            "select order_id, amount_cents from {{ ref('raw_orders_model') }}\n",
        ),
        (
            "../dbt_project/models/fact_orders.sql",
            dbt_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def dbt_mixed_parent_files(
    *, amount_cents: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "../dbt_project/models/selected_parent.sql",
            dbt_parent_model_sql(model_name="selected_parent", amount_cents=amount_cents),
        ),
        (
            "../dbt_project/models/unselected_parent.sql",
            dbt_parent_model_sql(model_name="unselected_parent", amount_cents=amount_cents),
        ),
        (
            "../dbt_project/models/fact_orders.sql",
            dbt_mixed_parent_fact_orders_sql(leaf_materialization=leaf_materialization),
        ),
    )


def dbt_diamond_files(*, amount_cents: int, leaf_materialization: str) -> SelectionStalenessFiles:
    intermediate_sql: str = "select order_id, amount_cents from {{ ref('raw_orders_model') }}\n"
    return (
        (
            "../dbt_project/models/raw_orders_model.sql",
            dbt_source_model_sql(amount_cents=amount_cents),
        ),
        ("../dbt_project/models/stg_orders_a.sql", intermediate_sql),
        ("../dbt_project/models/stg_orders_b.sql", intermediate_sql),
        (
            "../dbt_project/models/fact_orders.sql",
            dbt_diamond_fact_orders_sql(leaf_materialization=leaf_materialization),
        ),
    )


def dbt_seed_parent_files(
    *, amount_cents: int, fact_adjustment: int, leaf_materialization: str
) -> SelectionStalenessFiles:
    return (
        (
            "../dbt_project/seeds/raw_orders.csv",
            f"order_id,amount_cents\n1,{amount_cents}\n",
        ),
        (
            "../dbt_project/models/stg_orders.sql",
            "select order_id, amount_cents from {{ ref('raw_orders') }}\n",
        ),
        (
            "../dbt_project/models/fact_orders.sql",
            dbt_fact_orders_sql(
                fact_adjustment=fact_adjustment,
                leaf_materialization=leaf_materialization,
            ),
        ),
    )


def native_source_model_sql(*, amount_cents: int) -> str:
    return f"MODEL (materialized table);\n\nSELECT 1 AS order_id, {amount_cents} AS amount_cents\n"


def native_parent_model_sql(*, model_name: str, amount_cents: int) -> str:
    return (
        "MODEL (materialized table);\n\n"
        f"SELECT 1 AS order_id, {amount_cents} AS {model_name}_amount_cents\n"
    )


def native_fact_orders_sql(*, fact_adjustment: int, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  order_id,\n"
        f"  amount_cents / 100.0 + {fact_adjustment} AS amount_dollars\n"
        'FROM __ref("stg_orders")\n'
    )


def native_mixed_parent_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  s.order_id,\n"
        "  (s.selected_parent_amount_cents + u.unselected_parent_amount_cents) "
        " / 200.0 AS amount_dollars\n"
        'FROM __ref("selected_parent") s\n'
        'JOIN __ref("unselected_parent") u USING (order_id)\n'
    )


def native_diamond_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"MODEL (materialized {leaf_materialization});\n\n"
        "SELECT\n"
        "  a.order_id,\n"
        "  (a.amount_cents + b.amount_cents) / 200.0 AS amount_dollars\n"
        'FROM __ref("stg_orders_a") a\n'
        'JOIN __ref("stg_orders_b") b USING (order_id)\n'
    )


def dbt_source_model_sql(*, amount_cents: int) -> str:
    return f"select 1 as order_id, {amount_cents} as amount_cents\n"


def dbt_parent_model_sql(*, model_name: str, amount_cents: int) -> str:
    return f"select 1 as order_id, {amount_cents} as {model_name}_amount_cents\n"


def dbt_fact_orders_sql(*, fact_adjustment: int, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  order_id,\n"
        f"  amount_cents / 100.0 + {fact_adjustment} as amount_dollars\n"
        "from {{ ref('stg_orders') }}\n"
    )


def dbt_mixed_parent_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  s.order_id,\n"
        "  (s.selected_parent_amount_cents + u.unselected_parent_amount_cents) "
        " / 200.0 as amount_dollars\n"
        "from {{ ref('selected_parent') }} s\n"
        "join {{ ref('unselected_parent') }} u using (order_id)\n"
    )


def dbt_diamond_fact_orders_sql(*, leaf_materialization: str) -> str:
    return (
        f"{{{{ config(materialized='{leaf_materialization}') }}}}\n"
        "select\n"
        "  a.order_id,\n"
        "  (a.amount_cents + b.amount_cents) / 200.0 as amount_dollars\n"
        "from {{ ref('stg_orders_a') }} a\n"
        "join {{ ref('stg_orders_b') }} b using (order_id)\n"
    )
