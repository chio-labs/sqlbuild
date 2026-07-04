"""Unit tests for the public provider API."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import Field

from sqlbuild.provider.exceptions import ProviderInputError
from sqlbuild.providers import Provider
from tests.unit.src.sqlbuild.providers._test_types import (
    ExplicitProviderNameTestCase,
    InvalidExplicitProviderNameTestCase,
    ProviderLifecycleTestCase,
    ProviderNameTestCase,
    ProviderSettingsErrorTestCase,
    ProviderSettingsTestCase,
)
from tests.unit.src.sqlbuild.providers.helpers import construct_provider


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderSettingsTestCase(
            description="provider reads pydantic settings from environment",
            env_name="SQLBUILD_TEST_TOKEN",
            env_value="secret-token",
            expected_token="secret-token",
            expected_channel="#data-alerts",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_with_settings_when_constructing_then_fields_are_resolved(
    test_case: ProviderSettingsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlertProvider(Provider):
        token: str = Field(validation_alias=test_case.env_name)
        channel: str = "#data-alerts"

    monkeypatch.setenv(test_case.env_name, test_case.env_value)

    provider: Provider = construct_provider(AlertProvider)
    token_field: str = "token"
    channel_field: str = "channel"

    assert getattr(provider, token_field) == test_case.expected_token
    assert getattr(provider, channel_field) == test_case.expected_channel


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderSettingsErrorTestCase(
            description="forbids unknown provider settings fields",
            extra_field_name="unknown",
            extra_field_value="value",
            expected_error_fragment="Extra inputs are not permitted",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_with_unknown_setting_when_constructing_then_it_fails(
    test_case: ProviderSettingsErrorTestCase,
) -> None:
    class AlertProvider(Provider):
        channel: str = "#data-alerts"

    provider_cls: type[Provider] = AlertProvider

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        provider_cls(**{test_case.extra_field_name: test_case.extra_field_value})


@pytest.mark.parametrize(
    "test_case",
    (
        ProviderNameTestCase(
            description="normalizes provider suffix as class name text",
            provider_class_name="SlackProvider",
            expected_name="slack_provider",
        ),
        ProviderNameTestCase(
            description="normalizes compound provider suffix as class name text",
            provider_class_name="DataSlackProvider",
            expected_name="data_slack_provider",
        ),
        ProviderNameTestCase(
            description="normalizes acronym provider suffix as class name text",
            provider_class_name="AnalyticsApiProvider",
            expected_name="analytics_api_provider",
        ),
        ProviderNameTestCase(
            description="normalizes class without provider suffix",
            provider_class_name="Clock",
            expected_name="clock",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_provider_class_when_resolving_name_then_default_name_is_normalized(
    test_case: ProviderNameTestCase,
) -> None:
    provider_cls: type[Provider] = type(test_case.provider_class_name, (Provider,), {})

    assert provider_cls.name() == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        ExplicitProviderNameTestCase(
            description="explicit provider name wins",
            provider_name="alerts",
            expected_name="alerts",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_name_override_when_resolving_name_then_explicit_name_wins(
    test_case: ExplicitProviderNameTestCase,
) -> None:
    class SlackProvider(Provider):
        provider_name: ClassVar[str] = test_case.provider_name

    assert SlackProvider.name() == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidExplicitProviderNameTestCase(
            description="rejects empty explicit name",
            provider_class_name="SlackProvider",
            provider_name="",
            expected_error_fragment="empty name",
        ),
        InvalidExplicitProviderNameTestCase(
            description="rejects non snake case explicit name",
            provider_class_name="SlackProvider",
            provider_name="DataSlack",
            expected_error_fragment="lower snake_case",
        ),
        InvalidExplicitProviderNameTestCase(
            description="rejects explicit name starting with digit",
            provider_class_name="SlackProvider",
            provider_name="1_slack",
            expected_error_fragment="lower snake_case",
        ),
        InvalidExplicitProviderNameTestCase(
            description="rejects explicit name containing dash",
            provider_class_name="SlackProvider",
            provider_name="data-slack",
            expected_error_fragment="lower snake_case",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_explicit_provider_name_when_resolving_name_then_it_fails_clearly(
    test_case: InvalidExplicitProviderNameTestCase,
) -> None:
    provider_cls: type[Provider] = type(
        test_case.provider_class_name,
        (Provider,),
        {
            "provider_name": test_case.provider_name,
            "__annotations__": {"provider_name": ClassVar[str]},
        },
    )

    with pytest.raises(ProviderInputError, match=test_case.expected_error_fragment):
        provider_cls.name()


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderLifecycleTestCase(
            description="default lifecycle methods are noops",
            expected_setup_calls=0,
            expected_teardown_calls=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_when_constructing_then_setup_is_not_called(
    test_case: ProviderLifecycleTestCase,
) -> None:
    calls: dict[str, int] = {"setup": 0, "teardown": 0}

    class CountingProvider(Provider):
        def setup(self, ctx: Any) -> None:
            calls["setup"] += 1

        def teardown(self) -> None:
            calls["teardown"] += 1

    provider: CountingProvider = CountingProvider()
    client_attr: str = "_client"
    setattr(provider, client_attr, object())

    assert calls["setup"] == test_case.expected_setup_calls
    assert calls["teardown"] == test_case.expected_teardown_calls
    assert getattr(provider, client_attr) is not None
