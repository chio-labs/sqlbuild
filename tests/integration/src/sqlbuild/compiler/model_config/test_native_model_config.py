"""The native model config stage parses headers like the YAML schema parsers, on every engine."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.model_config._test_types import (
    ColumnMetadataExpansionTestCase,
    HeaderMetadataParityTestCase,
    ModelConfigTierTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_config.helpers import (
    HeaderMetadataParity,
    column_metadata_outcome,
    generated_header_metadata,
    header_metadata_parity,
    model_config_engine_outcome,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderMetadataParityTestCase(
            description="seeded columns and audits, valid and invalid",
            seed=20261007,
            count=4000,
            expected_minimum_parsed=400,
            expected_minimum_rejected=2000,
            expected_maximum_later_validated=60,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_header_metadata_when_attaching_then_model_loop_matches_yaml_parsers(
    test_case: HeaderMetadataParityTestCase, tmp_path: Path
) -> None:
    parity: HeaderMetadataParity = header_metadata_parity(
        project_dir=tmp_path,
        headers=generated_header_metadata(rng=random.Random(test_case.seed), count=test_case.count),
    )

    assert (
        parity.mismatches,
        parity.parsed >= test_case.expected_minimum_parsed,
        parity.rejected >= test_case.expected_minimum_rejected,
        parity.later_validated <= test_case.expected_maximum_later_validated,
    ) == ([], True, True, True), (parity.parsed, parity.rejected, parity.later_validated)


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnMetadataExpansionTestCase(
            description="a project variable template expands in a column type",
            header_column="amount (type '${column_type}')",
            expected_type="BIGINT",
            expected_error=None,
        ),
        ColumnMetadataExpansionTestCase(
            description="an unknown template variable in a column type is rejected",
            header_column="amount (type '${target.schema}')",
            expected_type=None,
            expected_error="model config references unknown variable 'target.schema'",
        ),
        ColumnMetadataExpansionTestCase(
            description="a macro call in a column description is rejected",
            header_column="amount (description '@cents(amount)')",
            expected_type=None,
            expected_error="model config field 'columns.amount.description' does not allow macros",
        ),
        ColumnMetadataExpansionTestCase(
            description="a macro marker after a space in a column type is rejected",
            header_column="amount (type '@cents\u2003(amount)')",
            expected_type=None,
            expected_error="model config field 'columns.amount.type' does not allow macros",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_template_or_macro_column_metadata_when_attaching_then_loop_expands_or_rejects(
    test_case: ColumnMetadataExpansionTestCase, tmp_path: Path
) -> None:
    column_type, error = column_metadata_outcome(
        project_dir=tmp_path, header_column=test_case.header_column
    )

    assert (column_type, error) == (test_case.expected_type, test_case.expected_error)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelConfigTierTestCase(
            description="shipped native stages",
            engine="native",
            expected_native_calls={
                "expand_config_templates": 0,
            },
        ),
        ModelConfigTierTestCase(
            description="native preview",
            engine="native-preview",
            expected_native_calls={
                "expand_config_templates": 0,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_tier_when_building_model_inputs_then_every_engine_runs_native_config(
    test_case: ModelConfigTierTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, config = model_config_engine_outcome(
        project_dir=tmp_path / test_case.engine, engine=test_case.engine, monkeypatch=monkeypatch
    )
    _, shipped_config = model_config_engine_outcome(
        project_dir=tmp_path / "shipped", engine="native", monkeypatch=monkeypatch
    )

    assert (calls, config.replace(test_case.engine, "shipped")) == (
        test_case.expected_native_calls,
        shipped_config,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
