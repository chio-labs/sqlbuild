"""Native model config builds and validator checks match Python exactly or defer to it."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.compile.native_model_config._test_types import (
    ModelConfigBuildParityTestCase,
    ModelValidationParityTestCase,
    NativeErrorParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile.native_model_config.helpers import (
    BUILD_ENVIRONMENT,
    ModelConfigBuildParity,
    ModelValidationParity,
    generated_config_builds,
    generated_validation_requests,
    header_help,
    model_config_build_parity,
    model_validation_parity,
    validation_outcomes,
)

_INCREMENTAL: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "append",
    "cursor": "updated_at",
    "cursor_type": "timestamp",
    "cursor_grain": "day",
}


@pytest.mark.parametrize(
    "test_case",
    [
        ModelValidationParityTestCase(
            description="seeded profiles with invalid and unusual values",
            seed=20261008,
            count=6000,
            expected_minimum_native_accepted=1000,
            expected_minimum_python_rejected=1500,
            expected_minimum_acceptance_percent=90,
            expected_minimum_error_percent=85,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_configs_when_validating_then_native_matches_python_or_defers(
    test_case: ModelValidationParityTestCase,
) -> None:
    parity: ModelValidationParity = model_validation_parity(
        requests=generated_validation_requests(
            rng=random.Random(test_case.seed), count=test_case.count
        )
    )

    assert (
        parity.mismatches[:3],
        parity.native_accepted >= test_case.expected_minimum_native_accepted,
        parity.python_rejected >= test_case.expected_minimum_python_rejected,
        parity.native_accepted * 100
        >= parity.python_accepted * test_case.expected_minimum_acceptance_percent,
        parity.native_errors * 100
        >= parity.python_rejected * test_case.expected_minimum_error_percent,
    ) == ([], True, True, True, True), (
        parity.native_accepted,
        parity.native_errors,
        parity.python_accepted,
        parity.python_rejected,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ModelConfigBuildParityTestCase(
            description="seeded defaults, path defaults, headers and targets",
            seed=20261009,
            count=6000,
            expected_minimum_built=2000,
            expected_minimum_python_raised=500,
            expected_minimum_build_percent=90,
            expected_minimum_error_percent=80,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_layers_when_building_config_then_native_matches_python_or_defers(
    test_case: ModelConfigBuildParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in BUILD_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    parity: ModelConfigBuildParity = model_config_build_parity(
        cases=generated_config_builds(rng=random.Random(test_case.seed), count=test_case.count)
    )

    assert (
        parity.mismatches[:3],
        parity.built >= test_case.expected_minimum_built,
        parity.python_raised >= test_case.expected_minimum_python_raised,
        parity.built * 100
        >= (test_case.count - parity.python_raised) * test_case.expected_minimum_build_percent,
        parity.native_errors * 100
        >= parity.python_raised * test_case.expected_minimum_error_percent,
    ) == ([], True, True, True, True), (
        parity.built,
        parity.native_errors,
        parity.deferred,
        parity.python_raised,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeErrorParityTestCase(
            description="a start bound shifted before year 1 in UTC",
            values={
                **_INCREMENTAL,
                "cursor_start": "0001-01-01T00:00:00+01:00",
                "cursor_end": "2024-01-01",
            },
            expected_native_outcome=(
                "CompileInputError",
                "model 'orders_daily': cursor_start value '0001-01-01T00:00:00+01:00' falls "
                "outside years 1-9999 once converted to UTC",
                "P001",
                header_help(
                    purpose="keep cursor_start within years 1-9999 in UTC",
                    entry="cursor_start '0001-01-01T00:00:00+00:00'",
                ),
                True,
            ),
            expected_python_outcome="native outcome",
        ),
        NativeErrorParityTestCase(
            description="an end bound shifted past year 9999 in UTC",
            values={
                **_INCREMENTAL,
                "cursor_start": "2024-01-01",
                "cursor_end": "9999-12-31T23:59:30.5-01:00",
            },
            expected_native_outcome="native defers",
            expected_python_outcome=(
                "CompileInputError",
                "model 'orders_daily': cursor_end value '9999-12-31T23:59:30.5-01:00' falls "
                "outside years 1-9999 once converted to UTC",
                "P001",
                header_help(
                    purpose="keep cursor_end within years 1-9999 in UTC",
                    entry="cursor_end '9999-12-31T23:59:30.500000+00:00'",
                ),
                True,
            ),
        ),
        NativeErrorParityTestCase(
            description="an invalid replay policy with its header help",
            values={**_INCREMENTAL, "replay_on_change": "bounded-soon"},
            expected_native_outcome=(
                "CompileInputError",
                "model 'orders_daily': replay_on_change 'bounded-soon' has an invalid duration "
                "'soon'; use a positive duration such as 14d, 12h or 1mo",
                "P001",
                header_help(
                    purpose="use a valid replay_on_change", entry="replay_on_change bounded-14d"
                ),
                True,
            ),
            expected_python_outcome="native outcome",
        ),
        NativeErrorParityTestCase(
            description="a non-string materialization",
            values={"materialized": 5},
            expected_native_outcome=(
                "ConfigValueTypeError",
                "config key 'materialized' expected a string, got int",
                None,
                None,
                None,
            ),
            expected_python_outcome="native outcome",
        ),
        NativeErrorParityTestCase(
            description="an old-name view that is not a duration",
            values={"materialized": "table", "old_name_view": "soon"},
            expected_native_outcome=(
                "CompileInputError",
                "model 'orders_daily': old_name_view must be a positive duration such as 7d, or "
                "false; got 'soon'",
                "P001",
                "write for example old_name_view 7d, or old_name_view false",
                True,
            ),
            expected_python_outcome="native outcome",
        ),
        NativeErrorParityTestCase(
            description="an unreadable unique key under an enforced contract",
            values={
                "materialized": "incremental",
                "incremental_strategy": "merge",
                "unique_key": ["\udcff"],
                "contract": "enforced",
                "columns": {"order_id": None},
            },
            expected_native_outcome="native defers",
            expected_python_outcome=(
                "CompileInputError",
                "model 'orders_daily': unique_key references column '\udcff' not declared in "
                "enforced contract",
                "P001",
                None,
                True,
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_configs_when_validating_then_native_raises_python_error_or_defers(
    test_case: NativeErrorParityTestCase,
) -> None:
    native, python = validation_outcomes(values=test_case.values)

    assert (native, python) == (
        test_case.expected_native_outcome,
        {"native outcome": test_case.expected_native_outcome}.get(
            str(test_case.expected_python_outcome), test_case.expected_python_outcome
        ),
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
