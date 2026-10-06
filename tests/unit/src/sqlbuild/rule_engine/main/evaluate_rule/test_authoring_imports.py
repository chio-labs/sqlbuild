"""Importing the Rule authoring API stays cheap for every custom-rule host."""

import json
import subprocess
import sys

import pytest

from tests.unit.src.sqlbuild.rule_engine.main.evaluate_rule._test_types import (
    AuthoringImportTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AuthoringImportTestCase(
            description="rule modules import the authoring API",
            imported_module="sqlbuild.rules",
            checked_modules=(
                "sqlbuild.rule_engine._helpers.engine.rule_harness",
                "sqlbuild.compiler.pipeline.main.project",
                "sqlbuild.adapters.duckdb.classes.duckdb_adapter",
            ),
            expected_loaded_modules=(),
        ),
        AuthoringImportTestCase(
            description="hosts import the custom-rule host",
            imported_module="sqlbuild.rule_engine._helpers.host.custom_host",
            checked_modules=(
                "sqlbuild.rule_engine._helpers.engine.rule_harness",
                "sqlbuild.compiler.pipeline.main.project",
            ),
            expected_loaded_modules=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_fresh_interpreter_when_importing_authoring_api_then_harness_is_not_loaded(
    test_case: AuthoringImportTestCase,
) -> None:
    script: str = (
        f"import json, sys\nimport {test_case.imported_module}\n"
        f"print(json.dumps(sorted(set({list(test_case.checked_modules)!r}) & set(sys.modules))))"
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    assert tuple(json.loads(result.stdout)) == test_case.expected_loaded_modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
