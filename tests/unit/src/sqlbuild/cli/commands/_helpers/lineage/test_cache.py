from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild._native as _native
from sqlbuild.cli.commands._helpers.lineage.cache import relation_lineage_fingerprint
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.unit.src.sqlbuild.cli.commands._helpers.lineage._test_types import (
    LineageFingerprintAvailabilityTestCase,
    LineageFingerprintEnvironmentTestCase,
    NativeFingerprintParityTestCase,
)

_LAYOUT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\nschema = "${ENV:ORDERS_SCHEMA}"\n',
    "models/a/b.sql": "SELECT 1 AS order_id\n",
    "models/a-c.sql": "SELECT '${ENV:  ORDERS_REGION}' AS region\n",
    "models/a.sql": "SELECT 2 AS order_id\n",
    "models/Z.SQL": "SELECT 3 AS order_id\n",
    "models/é.sql": "SELECT 'café' AS label\n",
    "seeds/customers.csv": "customer_id\n1\n",
    "sources/raw.YML": "sources: []\n",
    "macros/helpers.py": "def total():\n    return 1\n",
    ".hidden/notes.yaml": "a: 1\n",
    ".gitignore": "target/\n",
    "nested/.sqlbuildignore": "*.tmp\n",
    ".sql": "SELECT 'not a suffix'\n",
    "README.md": "${CTX:ignored}\n",
    "noext": "ENV:\n",
    "target/ignored.sql": "ENV:\n",
    ".venv/ignored.py": "ENV:\n",
    "models/__pycache__/ignored.py": "ENV:\n",
    "nested/target/kept.sql": "SELECT 4 AS order_id\n",
}
_LAYOUT_LINKS: dict[str, str] = {
    "models/linked.sql": "models/a.sql",
    "linked_dir": "models",
    "models/broken.sql": "models/missing.sql",
}


@pytest.mark.parametrize(
    "test_case",
    (
        LineageFingerprintEnvironmentTestCase(
            description="referenced environment value participates in cache identity",
            config=(
                'name = "orders"\nadapter = "duckdb"\n'
                '[targets.dev]\nschema = "${if(eq( ENV:ORDERS_SCHEMA, '
                "'orders_dev'), 'dev', 'test')}\"\n"
            ),
            environment_name="ORDERS_SCHEMA",
            first_value="orders_dev",
            second_value="orders_test",
            expected_equal=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_referenced_environment_change_when_fingerprinting_then_invalidates_cache_identity(
    test_case: LineageFingerprintEnvironmentTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.config, encoding="utf-8")
    monkeypatch.setenv(test_case.environment_name, test_case.first_value)
    first: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)
    monkeypatch.setenv(test_case.environment_name, test_case.second_value)

    second: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)

    assert (first == second) is test_case.expected_equal


@pytest.mark.parametrize(
    "test_case",
    (
        LineageFingerprintAvailabilityTestCase(
            description="dynamic invocation context disables structural cache",
            relative_path="sqlbuild_project.toml",
            config=(
                'name = "orders"\nadapter = "duckdb"\n'
                '[targets.dev]\nschema = "orders_${CTX:run_id}"\n'
            ),
            expected_available=False,
        ),
        LineageFingerprintAvailabilityTestCase(
            description="unicode environment name disables structural cache",
            relative_path="sqlbuild_project.toml",
            config=(
                'name = "orders"\nadapter = "duckdb"\n[targets.dev]\nschema = "${ENV:ORDERS_ÉTÉ}"\n'
            ),
            expected_available=False,
        ),
        LineageFingerprintAvailabilityTestCase(
            description="SQL output context preserves structural cache availability",
            relative_path="models/orders.sql",
            config=(
                "MODEL (description 'Test model orders.', materialized view);\n\n"
                "SELECT '${CTX:run_id}' AS invocation_id, 1 AS order_id\n"
            ),
            expected_available=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_invocation_context_when_fingerprinting_then_disables_cache(
    test_case: LineageFingerprintAvailabilityTestCase,
    tmp_path: Path,
) -> None:
    authored_path: Path = tmp_path / test_case.relative_path
    authored_path.parent.mkdir(parents=True, exist_ok=True)
    authored_path.write_text(test_case.config, encoding="utf-8")

    observed: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)

    assert (observed is not None) is test_case.expected_available


@pytest.mark.parametrize(
    "test_case",
    (
        NativeFingerprintParityTestCase(
            description="sorting, suffixes, exclusions, links and environment values",
            files=_LAYOUT_FILES,
            links=_LAYOUT_LINKS,
            environment={"ORDERS_SCHEMA": "orders_dev"},
            cli_vars={"region": "north", "limits": [1, 2.5, None], "label": "café"},
            expected_available=True,
        ),
        NativeFingerprintParityTestCase(
            description="an environment marker without a name",
            files={**_LAYOUT_FILES, "models/bad.sql": "SELECT 'ENV: ' AS broken\n"},
            links={},
            environment={},
            cli_vars=None,
            expected_available=False,
        ),
        NativeFingerprintParityTestCase(
            description="an environment name followed by a non-ASCII byte",
            files={"models/bad.sql": "SELECT '${ENV:ORDERSÉ}' AS broken\n"},
            links={},
            environment={},
            cli_vars=None,
            expected_available=False,
        ),
        NativeFingerprintParityTestCase(
            description="overlapping markers inside one matched name",
            files={"models/bad.sql": "SELECT 'ENV: ENV:X' AS broken\n"},
            links={},
            environment={},
            cli_vars=None,
            expected_available=False,
        ),
        NativeFingerprintParityTestCase(
            description="dynamic context in Python source",
            files={"macros/run.py": "RUN = 'CTX:run_id'\n", "models/a.sql": "SELECT 1\n"},
            links={},
            environment={},
            cli_vars=None,
            expected_available=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_authored_files_when_fingerprinting_natively_then_matches_python(
    test_case: NativeFingerprintParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for relative_path, contents in test_case.files.items():
        path: Path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    for relative_path, target in test_case.links.items():
        (tmp_path / relative_path).symlink_to(tmp_path / target)
    for name, value in test_case.environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ORDERS_REGION", raising=False)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "native")
    python_digest: str | None = relation_lineage_fingerprint(
        project_dir=tmp_path, cli_vars=test_case.cli_vars
    )
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "native-preview")

    native_digest: str | None = relation_lineage_fingerprint(
        project_dir=tmp_path, cli_vars=test_case.cli_vars
    )

    assert native_digest == python_digest
    assert (native_digest is not None) is test_case.expected_available
    assert _native.relation_lineage_fingerprint(tmp_path, b"")[0] != "deferred"
