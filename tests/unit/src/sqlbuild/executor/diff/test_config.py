from __future__ import annotations

from decimal import Decimal

import pytest

from sqlbuild.adapter.contract.models import RowDiffSampling, RowDiffTolerance, RowDiffTolerances
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff._helpers.config import (
    parse_row_diff_tolerances,
    resolve_row_diff_sampling,
)
from sqlbuild.executor.diff.models import RowDiffSamplingOverride
from tests.unit.src.sqlbuild.executor.diff._test_types import (
    ParseRowDiffTolerancesErrorTestCase,
    ParseRowDiffTolerancesTestCase,
    ResolveRowDiffSamplingErrorTestCase,
    ResolveRowDiffSamplingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseRowDiffTolerancesTestCase(
            description="parses decimal tolerances by type and by column",
            raw={
                "by_type": {
                    "FLOAT": {"relative": 0.0001, "absolute": "0.000001"},
                    "integer": {"absolute": 1},
                },
                "by_column": {
                    "revenue": {"absolute": "0.01"},
                    "conversion_rate": {"relative": "0.001", "absolute": "0.0001"},
                },
            },
            expected_result=RowDiffTolerances(
                by_type={
                    "float": RowDiffTolerance(
                        relative=Decimal("0.0001"),
                        absolute=Decimal("0.000001"),
                    ),
                    "integer": RowDiffTolerance(absolute=Decimal("1")),
                },
                by_column={
                    "revenue": RowDiffTolerance(absolute=Decimal("0.01")),
                    "conversion_rate": RowDiffTolerance(
                        relative=Decimal("0.001"),
                        absolute=Decimal("0.0001"),
                    ),
                },
            ),
        ),
        ParseRowDiffTolerancesTestCase(
            description="returns empty tolerances for none",
            raw=None,
            expected_result=RowDiffTolerances(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_raw_row_diff_tolerances_when_parsing_then_returns_typed_tolerances(
    test_case: ParseRowDiffTolerancesTestCase,
) -> None:
    result: RowDiffTolerances = parse_row_diff_tolerances(raw=test_case.raw)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        ParseRowDiffTolerancesErrorTestCase(
            description="rejects non mapping root",
            raw=[],
            expected_error_fragment="row_diff_tolerances must be a mapping",
            expected_code="X401",
        ),
        ParseRowDiffTolerancesErrorTestCase(
            description="rejects empty tolerance rule",
            raw={"by_column": {"revenue": {}}},
            expected_error_fragment="must define absolute or relative",
            expected_code="X404",
        ),
        ParseRowDiffTolerancesErrorTestCase(
            description="rejects unsupported rule keys",
            raw={"by_type": {"float": {"disabled": True}}},
            expected_error_fragment="contains unsupported keys: disabled",
            expected_code="X403",
        ),
        ParseRowDiffTolerancesErrorTestCase(
            description="rejects boolean threshold",
            raw={"by_column": {"revenue": {"absolute": True}}},
            expected_error_fragment="absolute must be numeric",
            expected_code="X405",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_row_diff_tolerances_when_parsing_then_raises_clear_error(
    test_case: ParseRowDiffTolerancesErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment) as error_info:
        parse_row_diff_tolerances(raw=test_case.raw)

    assert error_info.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveRowDiffSamplingTestCase(
            description="absent policy remains exhaustive",
            raw_row_limit=None,
            raw_seed=None,
            override=RowDiffSamplingOverride(),
            expected_result=None,
        ),
        ResolveRowDiffSamplingTestCase(
            description="configured zero disables inherited sampling",
            raw_row_limit=0,
            raw_seed=7,
            override=RowDiffSamplingOverride(),
            expected_result=None,
        ),
        ResolveRowDiffSamplingTestCase(
            description="configured sample uses configured seed",
            raw_row_limit=100,
            raw_seed=7,
            override=RowDiffSamplingOverride(),
            expected_result=RowDiffSampling(row_limit=100, seed=7),
        ),
        ResolveRowDiffSamplingTestCase(
            description="cli values override configured sample",
            raw_row_limit=100,
            raw_seed=7,
            override=RowDiffSamplingOverride(row_limit=50, seed=11),
            expected_result=RowDiffSampling(row_limit=50, seed=11),
        ),
        ResolveRowDiffSamplingTestCase(
            description="cli exhaustive override disables configured sample",
            raw_row_limit=100,
            raw_seed=7,
            override=RowDiffSamplingOverride(exhaustive=True),
            expected_result=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sampling_layers_when_resolving_then_returns_effective_policy(
    test_case: ResolveRowDiffSamplingTestCase,
) -> None:
    result: RowDiffSampling | None = resolve_row_diff_sampling(
        raw_row_limit=test_case.raw_row_limit,
        raw_seed=test_case.raw_seed,
        override=test_case.override,
        label="model 'orders'",
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveRowDiffSamplingErrorTestCase(
            description="boolean row limit is rejected",
            raw_row_limit=True,
            raw_seed=0,
            expected_error_fragment="row_diff_sample_rows must be an integer",
            expected_code="X406",
        ),
        ResolveRowDiffSamplingErrorTestCase(
            description="negative row limit is rejected",
            raw_row_limit=-1,
            raw_seed=0,
            expected_error_fragment="row_diff_sample_rows must be zero or greater",
            expected_code="X407",
        ),
        ResolveRowDiffSamplingErrorTestCase(
            description="boolean seed is rejected",
            raw_row_limit=10,
            raw_seed=True,
            expected_error_fragment="row_diff_sample_seed must be an integer",
            expected_code="X406",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sampling_config_when_resolving_then_raises_clear_error(
    test_case: ResolveRowDiffSamplingErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment) as error_info:
        resolve_row_diff_sampling(
            raw_row_limit=test_case.raw_row_limit,
            raw_seed=test_case.raw_seed,
            override=RowDiffSamplingOverride(),
            label="model 'orders'",
        )

    assert error_info.value.code == test_case.expected_code
