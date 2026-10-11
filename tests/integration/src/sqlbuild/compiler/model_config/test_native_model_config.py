"""The native model config stage parses headers like the YAML schema parsers, on every engine."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.model_config._test_types import (
    HeaderMetadataParityTestCase,
    ModelConfigTierTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_config.helpers import (
    HeaderMetadataParity,
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
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_header_metadata_when_parsing_then_native_matches_yaml_schema_parsers(
    test_case: HeaderMetadataParityTestCase,
) -> None:
    parity: HeaderMetadataParity = header_metadata_parity(
        headers=generated_header_metadata(rng=random.Random(test_case.seed), count=test_case.count)
    )

    assert (
        parity.mismatches,
        parity.parsed >= test_case.expected_minimum_parsed,
        parity.rejected >= test_case.expected_minimum_rejected,
    ) == ([], True, True), (parity.parsed, parity.rejected)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelConfigTierTestCase(
            description="shipped native stages",
            engine="native",
            expected_native_calls={
                "parse_model_header_metadata": 2,
                "expand_config_templates": 1,
            },
        ),
        ModelConfigTierTestCase(
            description="native preview",
            engine="native-preview",
            expected_native_calls={
                "parse_model_header_metadata": 2,
                "expand_config_templates": 1,
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
