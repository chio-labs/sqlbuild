"""The native model config stage matches Python exactly or defers to it."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.model_config._test_types import (
    ConfigPresenceParityTestCase,
    HeaderMetadataParityTestCase,
    ModelConfigTierTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_config.helpers import (
    ConfigPresenceParity,
    HeaderMetadataParity,
    config_presence_parity,
    generated_config_values,
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
            expected_minimum_unsupported=100,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_header_metadata_when_parsing_then_native_matches_python_or_defers(
    test_case: HeaderMetadataParityTestCase,
) -> None:
    parity: HeaderMetadataParity = header_metadata_parity(
        headers=generated_header_metadata(rng=random.Random(test_case.seed), count=test_case.count)
    )

    assert (
        parity.mismatches,
        parity.parsed >= test_case.expected_minimum_parsed,
        parity.rejected >= test_case.expected_minimum_rejected,
        parity.unsupported >= test_case.expected_minimum_unsupported,
    ) == ([], True, True, True), (parity.parsed, parity.rejected, parity.unsupported)


@pytest.mark.parametrize(
    "test_case",
    [
        ConfigPresenceParityTestCase(
            description="seeded nested config with templates and macro calls",
            seed=20261008,
            count=4000,
            expected_minimum_present=400,
            expected_minimum_deferred=20,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_config_when_scanning_presence_then_native_matches_python_or_defers(
    test_case: ConfigPresenceParityTestCase,
) -> None:
    parity: ConfigPresenceParity = config_presence_parity(
        values=generated_config_values(rng=random.Random(test_case.seed), count=test_case.count)
    )

    assert (
        parity.mismatches,
        parity.present >= test_case.expected_minimum_present,
        parity.deferred >= test_case.expected_minimum_deferred,
    ) == ([], True, True), (parity.present, parity.deferred)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelConfigTierTestCase(
            description="python oracle",
            engine="python",
            expected_native_calls={
                "parse_model_header_metadata": 0,
                "expand_config_templates": 14,
                "config_contains_template": 0,
                "config_contains_macro_call": 0,
            },
        ),
        ModelConfigTierTestCase(
            description="shipped native stages",
            engine="native",
            expected_native_calls={
                "parse_model_header_metadata": 1,
                "expand_config_templates": 8,
                "config_contains_template": 0,
                "config_contains_macro_call": 0,
            },
        ),
        ModelConfigTierTestCase(
            description="native preview",
            engine="native-preview",
            expected_native_calls={
                "parse_model_header_metadata": 1,
                "expand_config_templates": 8,
                "config_contains_template": 0,
                "config_contains_macro_call": 0,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_tier_when_building_model_inputs_then_native_config_runs_only_in_native_engines(
    test_case: ModelConfigTierTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, config = model_config_engine_outcome(
        project_dir=tmp_path / test_case.engine, engine=test_case.engine, monkeypatch=monkeypatch
    )
    _, python_config = model_config_engine_outcome(
        project_dir=tmp_path / "python", engine="python", monkeypatch=monkeypatch
    )

    assert (calls, config.replace(test_case.engine, "python")) == (
        test_case.expected_native_calls,
        python_config,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
