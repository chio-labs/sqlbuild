"""E2E tests for managed resource namespace validation during compile."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NamespaceCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_PRESERVE_CONFIG: str = (
    dedent(
        """
    name = "namespace_validation"
    adapter = "duckdb"
    default_target = "dev"

    [connection]
    database = ":memory:"

    [targets.dev]
    schema = "preserve"
    """
    ).strip()
    + "\n"
)
_SEED_SCHEMA: str = (
    dedent(
        """
    seeds:
      - name: countries
        columns:
          - name: code
            type: VARCHAR
    """
    ).strip()
    + "\n"
)
_POSTGRES_CONFIG_WITHOUT_SCHEMA: str = (
    'name = "namespace_validation"\nadapter = "postgres"\n\n[connection]\ndatabase = "analytics"\n'
)
_PYTHON_FUNCTION: str = (
    "from sqlbuild.functions import udf\n\n"
    '@udf(arguments={}, returns="INTEGER", runtime_version="3.11")\n'
    "def main():\n"
    "    return 42\n"
)
_MANAGED_SOURCE: str = (
    "sources:\n"
    "  - name: raw_events\n"
    "    managed: true\n"
    "    write_strategy: table\n"
    "    columns:\n"
    "      - name: event_id\n"
    "        type: INTEGER\n"
)
_MANAGED_SOURCE_LOADER: str = (
    "from sqlbuild.loaders import loader\n\n"
    "@loader\n"
    "def raw_events(ctx):\n"
    "    return [{'event_id': 1}]\n"
)


@pytest.mark.parametrize(
    "test_case",
    (
        NamespaceCompileTestCase(
            description="model without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Model 'orders' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="seed without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "seeds/schema.yml": _SEED_SCHEMA,
                "seeds/countries.csv": "code\nGB\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Seed 'countries' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="SQL scalar function without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "functions/sql/answer.sql": "FUNCTION (returns INTEGER);\n\n42\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="SQL function 'answer' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="SQL table function without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "functions/sql/answers.sql": dedent(
                    """
                FUNCTION (
                  returns table (
                    answer INTEGER
                  )
                );

                SELECT 42 AS answer
                """
                ).strip()
                + "\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="SQL function 'answers' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="non inheriting Python UDF without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "functions/python/answer.py": dedent(
                    """
                from sqlbuild.functions import udf

                @udf(arguments={}, returns="INTEGER", runtime_version="3.11")
                def main():
                    return 42
                """
                ).strip()
                + "\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Python function 'answer' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="managed source without logical schema fails under preserve",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG,
                "sources/raw.yml": _MANAGED_SOURCE,
                "loaders/raw_events.py": _MANAGED_SOURCE_LOADER,
            },
            expected_exit_code=1,
            expected_stderr_fragment="Managed source 'raw_events' has no logical schema",
        ),
        NamespaceCompileTestCase(
            description="resource specific defaults resolve preserved schemas",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "namespace_validation"
                adapter = "duckdb"
                default_target = "dev"

                [connection]
                database = ":memory:"

                [defaults]
                seed_schema = "seed_data"
                function_schema = "functions"

                [path_defaults.marts]
                schema = "analytics"

                [targets.dev]
                schema = "preserve"
                """
                ).strip()
                + "\n",
                "models/marts/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
                "seeds/schema.yml": _SEED_SCHEMA,
                "seeds/countries.csv": "code\nGB\n",
                "functions/sql/answer.sql": "FUNCTION (returns INTEGER);\n\n42\n",
                "functions/python/python_answer.py": dedent(
                    """
                from sqlbuild.functions import udf

                @udf(arguments={}, returns="INTEGER", runtime_version="3.11")
                def main():
                    return 42
                """
                ).strip()
                + "\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="literal target schema supplies physical namespace",
            repo_files={
                "sqlbuild_project.toml": _PRESERVE_CONFIG.replace(
                    'schema = "preserve"', 'schema = "physical"'
                ),
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
                "seeds/schema.yml": _SEED_SCHEMA,
                "seeds/countries.csv": "code\nGB\n",
                "functions/sql/answer.sql": "FUNCTION (returns INTEGER);\n\n42\n",
                "functions/python/python_answer.py": dedent(
                    """
                from sqlbuild.functions import udf

                @udf(arguments={}, returns="INTEGER", runtime_version="3.11")
                def main():
                    return 42
                """
                ).strip()
                + "\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="warehouse model without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Model 'orders' has no explicitly resolved physical write schema",
        ),
        NamespaceCompileTestCase(
            description="warehouse seed without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "seeds/schema.yml": _SEED_SCHEMA,
                "seeds/countries.csv": "code\nGB\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Seed 'countries' has no explicitly resolved physical write schema",
        ),
        NamespaceCompileTestCase(
            description="warehouse SQL scalar function without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "functions/sql/answer.sql": "FUNCTION (returns INTEGER);\n\n42\n",
            },
            expected_exit_code=1,
            expected_stderr_fragment="Function 'answer' has no explicitly resolved physical write schema",
        ),
        NamespaceCompileTestCase(
            description="warehouse SQL table function without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "functions/sql/answers.sql": (
                    "FUNCTION (returns table (answer INTEGER));\n\nSELECT 42 AS answer\n"
                ),
            },
            expected_exit_code=1,
            expected_stderr_fragment="Function 'answers' has no explicitly resolved physical write schema",
        ),
        NamespaceCompileTestCase(
            description="warehouse Python UDF without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "functions/python/answer.py": _PYTHON_FUNCTION,
            },
            expected_exit_code=1,
            expected_stderr_fragment="Function 'answer' has no explicitly resolved physical write schema",
        ),
        NamespaceCompileTestCase(
            description="warehouse managed source without explicit schema fails offline",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "sources/raw.yml": _MANAGED_SOURCE,
                "loaders/raw_events.py": _MANAGED_SOURCE_LOADER,
            },
            expected_exit_code=1,
            expected_stderr_fragment=(
                "Managed source 'raw_events' has no explicitly resolved physical write schema"
            ),
        ),
        NamespaceCompileTestCase(
            description="resource schema supplies physical namespace",
            repo_files={
                "sqlbuild_project.toml": _POSTGRES_CONFIG_WITHOUT_SCHEMA,
                "models/orders.sql": "MODEL (schema analytics);\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="default schema supplies physical namespace",
            repo_files={
                "sqlbuild_project.toml": (
                    _POSTGRES_CONFIG_WITHOUT_SCHEMA + '\n[defaults]\nschema = "analytics"\n'
                ),
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="literal target schema supplies warehouse physical namespace",
            repo_files={
                "sqlbuild_project.toml": (
                    _POSTGRES_CONFIG_WITHOUT_SCHEMA.replace(
                        "\n[connection]\n", '\ndefault_target = "dev"\n\n[connection]\n'
                    )
                    + '\n[targets.dev]\nschema = "analytics"\n'
                ),
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="connection schema supplies physical namespace",
            repo_files={
                "sqlbuild_project.toml": (
                    _POSTGRES_CONFIG_WITHOUT_SCHEMA + 'schema = "analytics"\n'
                ),
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="loader schema supplies managed source physical namespace",
            repo_files={
                "sqlbuild_project.toml": (
                    _POSTGRES_CONFIG_WITHOUT_SCHEMA.replace(
                        "\n[connection]\n", '\ndefault_target = "dev"\n\n[connection]\n'
                    )
                    + '\n[targets.dev]\nloader_schema = "raw"\n'
                ),
                "sources/raw.yml": _MANAGED_SOURCE,
                "loaders/raw_events.py": _MANAGED_SOURCE_LOADER,
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
        NamespaceCompileTestCase(
            description="DuckDB may compile managed writes with implicit main schema",
            repo_files={
                "sqlbuild_project.toml": (
                    'name = "namespace_validation"\nadapter = "duckdb"\n\n'
                    "[connection]\n"
                    'database = ":memory:"\n'
                ),
                "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
                "seeds/schema.yml": _SEED_SCHEMA,
                "seeds/countries.csv": "code\nGB\n",
                "functions/sql/answer.sql": "FUNCTION (returns INTEGER);\n\n42\n",
                "sources/raw.yml": _MANAGED_SOURCE,
                "loaders/raw_events.py": _MANAGED_SOURCE_LOADER,
            },
            expected_exit_code=0,
            expected_stderr_fragment="",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_managed_resources_when_compiling_namespace_targets_then_validation_is_fail_closed(
    test_case: NamespaceCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="namespace_validation",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stderr_fragment in result.stderr
