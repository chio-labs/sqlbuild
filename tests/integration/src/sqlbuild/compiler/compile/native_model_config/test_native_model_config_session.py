"""Native model config builds and validator checks match Python exactly or defer to it."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.compile.native_model_config._test_types import (
    ModelConfigBuildParityTestCase,
    ModelValidationParityTestCase,
    NativeRejectionParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile.native_model_config.helpers import (
    BUILD_ENVIRONMENT,
    ModelConfigBuildParity,
    ModelValidationParity,
    generated_config_builds,
    generated_validation_requests,
    model_config_build_parity,
    model_validation_parity,
    validation_outcomes,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelValidationParityTestCase(
            description="seeded profiles with invalid and unusual values",
            seed=20261008,
            count=6000,
            expected_minimum_native_accepted=1500,
            expected_minimum_python_rejected=1500,
            expected_minimum_acceptance_percent=90,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_configs_when_validating_then_native_accepts_only_what_python_accepts(
    test_case: ModelValidationParityTestCase,
) -> None:
    parity: ModelValidationParity = model_validation_parity(
        requests=generated_validation_requests(
            rng=random.Random(test_case.seed), count=test_case.count
        )
    )

    assert (
        parity.mismatches,
        parity.native_accepted >= test_case.expected_minimum_native_accepted,
        parity.python_rejected >= test_case.expected_minimum_python_rejected,
        parity.native_accepted * 100
        >= parity.python_accepted * test_case.expected_minimum_acceptance_percent,
    ) == ([], True, True, True), (
        parity.native_accepted,
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
    ) == ([], True, True, True), (parity.built, parity.deferred, parity.python_raised)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRejectionParityTestCase(
            description="a start bound shifted before year 1 in UTC",
            values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "cursor": "updated_at",
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_start": "0001-01-01T00:00:00+01:00",
                "cursor_end": "2024-01-01",
            },
            expected_native_accepted=False,
            expected_python_error=(
                "CompileInputError: model 'orders_daily': cursor_start value "
                "'0001-01-01T00:00:00+01:00' falls outside years 1-9999 once converted to UTC"
            ),
        ),
        NativeRejectionParityTestCase(
            description="an end bound shifted past year 9999 in UTC",
            values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "cursor": "updated_at",
                "cursor_type": "timestamp",
                "cursor_grain": "day",
                "cursor_start": "2024-01-01",
                "cursor_end": "9999-12-31T23:59:00-01:00",
            },
            expected_native_accepted=False,
            expected_python_error=(
                "CompileInputError: model 'orders_daily': cursor_end value "
                "'9999-12-31T23:59:00-01:00' falls outside years 1-9999 once converted to UTC"
            ),
        ),
        NativeRejectionParityTestCase(
            description="an unreadable unique key under an enforced contract",
            values={
                "materialized": "incremental",
                "incremental_strategy": "merge",
                "unique_key": ["\udcff"],
                "contract": "enforced",
                "columns": {"order_id": None},
            },
            expected_native_accepted=False,
            expected_python_error=(
                "CompileInputError: model 'orders_daily': unique_key references column "
                "'\udcff' not declared in enforced contract"
            ),
        ),
        NativeRejectionParityTestCase(
            description="an unreadable snapshot check column under an enforced contract",
            values={
                "materialized": "snapshot",
                "unique_key": "order_id",
                "snapshot_strategy": "check",
                "check_columns": ["\udcff"],
                "contract": "enforced",
                "columns": {"order_id": None},
            },
            expected_native_accepted=False,
            expected_python_error=(
                "CompileInputError: model 'orders_daily': check_columns references column "
                "'\udcff' not declared in enforced contract"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_rejected_edge_configs_when_validating_then_native_defers_to_python(
    test_case: NativeRejectionParityTestCase,
) -> None:
    accepted, python_error = validation_outcomes(values=test_case.values)

    assert (accepted, python_error) == (
        test_case.expected_native_accepted,
        test_case.expected_python_error,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
