from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.build_planning.execution_limits import (
    enforce_model_execution_limit,
)
from sqlbuild.cli.commands._helpers.build_planning.invocation import resolve_build_invocation
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import BuildCommandRequest
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning._test_types import (
    ModelExecutionLimitTestCase,
    UnsupportedDurationLimitTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelExecutionLimitTestCase(
            description="model count equals configured limit",
            model_count=25,
            maximum_models=25,
            expected_code=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_count_within_limit_when_enforcing_then_build_is_allowed(
    test_case: ModelExecutionLimitTestCase,
) -> None:
    result: None = enforce_model_execution_limit(
        model_count=test_case.model_count,
        target_name="dev",
        limits=ExecutionLimitsConfig(max_models=test_case.maximum_models),
    )
    assert result is test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        ModelExecutionLimitTestCase(
            description="model count exceeds configured limit",
            model_count=26,
            maximum_models=25,
            remediation=(
                "Review the expanded selection and request approval before changing the policy."
            ),
            expected_code="C413",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_count_above_limit_when_enforcing_then_error_has_custom_remediation(
    test_case: ModelExecutionLimitTestCase,
) -> None:

    with pytest.raises(CliUserError) as raised:
        enforce_model_execution_limit(
            model_count=test_case.model_count,
            target_name="dev",
            limits=ExecutionLimitsConfig(
                max_models=test_case.maximum_models,
                remediation=test_case.remediation,
            ),
        )

    assert raised.value.code == test_case.expected_code
    assert raised.value.help == test_case.remediation
    assert "Selected models: 26" in raised.value.message
    assert "Maximum models:  25" in raised.value.message
    assert "No warehouse changes were made." in raised.value.message


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedDurationLimitTestCase(
            description="DuckDB target cannot guarantee statement cancellation",
            max_duration="30m",
            remediation="Use an adapter with safe statement cancellation.",
            expected_code="C415",
            expected_error_fragment="cannot cancel active statements safely",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duration_limit_for_unsupported_adapter_when_resolving_then_configuration_is_rejected(
    tmp_path: Path,
    test_case: UnsupportedDurationLimitTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        """
name = "shop"
adapter = "duckdb"
default_target = "dev"

[targets.dev.execution_limits]
max_duration = "{test_case.max_duration}"
remediation = "{test_case.remediation}"
""".strip().format(test_case=test_case),
        encoding="utf-8",
    )

    with pytest.raises(CliUserError) as raised:
        resolve_build_invocation(request=BuildCommandRequest(project_dir=tmp_path))

    assert raised.value.code == test_case.expected_code
    assert test_case.expected_error_fragment in raised.value.message
    assert raised.value.help == test_case.remediation


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedDurationLimitTestCase(
            description="Snowflake target rejects duration beyond statement timeout range",
            max_duration="8d",
            remediation="Choose a duration supported by the configured warehouse.",
            expected_code="C416",
            expected_error_fragment="max_duration exceeds the largest duration supported",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duration_above_adapter_maximum_when_resolving_then_configuration_is_rejected(
    tmp_path: Path,
    test_case: UnsupportedDurationLimitTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        """
name = "shop"
adapter = "snowflake"
default_target = "dev"

[targets.dev]
database = "analytics"
schema = "dev"

[targets.dev.execution_limits]
max_duration = "{test_case.max_duration}"
remediation = "{test_case.remediation}"
""".strip().format(test_case=test_case),
        encoding="utf-8",
    )

    with pytest.raises(CliUserError) as raised:
        resolve_build_invocation(request=BuildCommandRequest(project_dir=tmp_path))

    assert raised.value.code == test_case.expected_code
    assert test_case.expected_error_fragment in raised.value.message
    assert raised.value.help == test_case.remediation
