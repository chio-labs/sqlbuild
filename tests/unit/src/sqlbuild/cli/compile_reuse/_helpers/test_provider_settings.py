"""Provider settings inputs must be enumerated exactly, or reuse must be refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.compile_reuse._helpers.provider_settings import provider_settings_inputs
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import settings_inputs_digest
from sqlbuild.cli.compile_reuse.models import SettingsEnvironmentInputs, SettingsInputsResult
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers._test_types import (
    ProviderSettingsInputsTestCase,
    SettingsDigestTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers.helpers import (
    SETTINGS_ENV_FILE_NAME,
    SETTINGS_SECRETS_DIR_NAME,
    SETTINGS_TOKEN_ENV_VAR,
    AliasedOrdersSettings,
    CaseSensitiveOrdersSettings,
    CommandLineOrdersSettings,
    CustomSourceOrdersSettings,
    FileOrdersSettings,
    NestedOrdersSettings,
    OrdersApiSettings,
    PrefixedOrdersSettings,
    described_settings_inputs,
    file_settings_inputs,
    set_token,
    write_settings_file,
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


@pytest.mark.parametrize(
    "test_case",
    [
        SettingsDigestTestCase(
            description="unrelated_variable",
            change=lambda mp, _root: mp.setenv("OTHER", "1"),
            expected_changed=False,
        ),
        SettingsDigestTestCase(
            description="token_unset",
            change=lambda mp, _root: mp.delenv(SETTINGS_TOKEN_ENV_VAR),
            expected_changed=True,
        ),
        SettingsDigestTestCase(
            description="token_changed",
            change=lambda mp, _root: set_token(mp, "beta"),
            expected_changed=True,
        ),
        SettingsDigestTestCase(
            description="token_set_in_other_case",
            change=lambda mp, _root: mp.setenv(SETTINGS_TOKEN_ENV_VAR.lower(), "gamma"),
            expected_changed=True,
        ),
        SettingsDigestTestCase(
            description="env_file_changed",
            change=lambda _mp, root: write_settings_file(
                root, SETTINGS_ENV_FILE_NAME, "ORDERS_API_TOKEN=delta\n"
            ),
            expected_changed=True,
        ),
        SettingsDigestTestCase(
            description="secret_added",
            change=lambda _mp, root: write_settings_file(
                root, f"{SETTINGS_SECRETS_DIR_NAME}/orders_api_token", "epsilon"
            ),
            expected_changed=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_settings_inputs_when_their_values_change_then_the_digest_moves(
    test_case: SettingsDigestTestCase, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_token(monkeypatch, "alpha")
    write_settings_file(tmp_path, SETTINGS_ENV_FILE_NAME, "ORDERS_API_TOKEN=alpha\n")
    inputs: tuple[SettingsEnvironmentInputs, ...] = (file_settings_inputs(root=tmp_path),)
    before: str = settings_inputs_digest(inputs=inputs)

    test_case.change(monkeypatch, tmp_path)

    assert (settings_inputs_digest(inputs=inputs) != before) is test_case.expected_changed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
