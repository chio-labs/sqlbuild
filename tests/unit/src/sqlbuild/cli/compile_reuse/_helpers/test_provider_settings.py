"""Provider settings inputs must be enumerated exactly, or reuse must be refused."""

from __future__ import annotations

import pytest

from sqlbuild.cli.compile_reuse._helpers.provider_settings import provider_settings_inputs
from sqlbuild.cli.compile_reuse.models import SettingsInputsResult
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers._test_types import (
    ProviderSettingsInputsTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers.helpers import (
    SETTINGS_ENV_FILE_NAME,
    SETTINGS_SECRETS_DIR_NAME,
    AliasedOrdersSettings,
    CaseSensitiveOrdersSettings,
    CommandLineOrdersSettings,
    CustomSourceOrdersSettings,
    FileOrdersSettings,
    NestedOrdersSettings,
    OrdersApiSettings,
    PrefixedOrdersSettings,
    described_settings_inputs,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderSettingsInputsTestCase(
            description="field_name",
            settings_class=OrdersApiSettings,
            expected_names=("orders_api_token",),
        ),
        ProviderSettingsInputsTestCase(
            description="env_prefix",
            settings_class=PrefixedOrdersSettings,
            expected_names=("orders_token",),
        ),
        ProviderSettingsInputsTestCase(
            description="alias_choices",
            settings_class=AliasedOrdersSettings,
            expected_names=("legacy_key", "orders_key"),
        ),
        ProviderSettingsInputsTestCase(
            description="nested_delimiter",
            settings_class=NestedOrdersSettings,
            expected_names=("endpoint",),
            expected_prefixes=("endpoint__",),
        ),
        ProviderSettingsInputsTestCase(
            description="case_sensitive",
            settings_class=CaseSensitiveOrdersSettings,
            expected_case_sensitive=True,
            expected_names=("OrdersToken",),
        ),
        ProviderSettingsInputsTestCase(
            description="env_file_and_secrets_dir",
            settings_class=FileOrdersSettings,
            expected_names=("orders_api_token",),
            expected_env_file_names=(SETTINGS_ENV_FILE_NAME,),
            expected_secrets_dir_names=(SETTINGS_SECRETS_DIR_NAME,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_provider_settings_class_when_enumerating_then_every_external_input_is_listed(
    test_case: ProviderSettingsInputsTestCase,
) -> None:
    result: SettingsInputsResult = provider_settings_inputs(
        settings_classes=(test_case.settings_class,)
    )
    assert result.unsupported_reason is None
    assert described_settings_inputs(result=result) == (
        (
            test_case.expected_case_sensitive,
            test_case.expected_names,
            test_case.expected_prefixes,
            test_case.expected_env_file_names,
            test_case.expected_secrets_dir_names,
        ),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderSettingsInputsTestCase(
            description="customized_sources",
            settings_class=CustomSourceOrdersSettings,
            expected_unsupported=True,
        ),
        ProviderSettingsInputsTestCase(
            description="command_line_source",
            settings_class=CommandLineOrdersSettings,
            expected_unsupported=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_settings_with_unlisted_sources_when_enumerating_then_reuse_is_refused(
    test_case: ProviderSettingsInputsTestCase,
) -> None:
    result: SettingsInputsResult = provider_settings_inputs(
        settings_classes=(OrdersApiSettings, test_case.settings_class)
    )

    assert (result.inputs, result.unsupported_reason is not None) == (
        (),
        test_case.expected_unsupported,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
