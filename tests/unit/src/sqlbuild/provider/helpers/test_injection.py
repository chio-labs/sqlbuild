from __future__ import annotations

import pytest

from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.exceptions import ProviderInjectionError
from sqlbuild.provider.helpers.injection import call_with_provider_injection
from tests.unit.src.sqlbuild.provider.helpers._test_types import (
    ProviderInjectionErrorTestCase,
    ProviderInjectionLabelTestCase,
    ProviderInjectionTestCase,
)
from tests.unit.src.sqlbuild.provider.helpers.helpers import (
    SlackProvider,
    context_and_provider,
    context_only,
    mismatched_provider,
    missing_provider,
    provider_only,
    reserved_context_conflict,
    unannotated_provider,
)

PROVIDER_INJECTION_TEST_CASES: tuple[ProviderInjectionTestCase, ...] = (
    ProviderInjectionTestCase(
        description="provider is injected by parameter name with context",
        function=context_and_provider,
        expected_result=("runtime-context", "slack"),
    ),
    ProviderInjectionTestCase(
        description="provider-only function receives provider by name",
        function=provider_only,
        expected_result="slack",
    ),
)

PROVIDER_INJECTION_ERROR_TEST_CASES: tuple[ProviderInjectionErrorTestCase, ...] = (
    ProviderInjectionErrorTestCase(
        description="missing provider parameter errors clearly",
        function=missing_provider,
        expected_error_fragment=(
            "Provider parameter 'alerts' requires provider 'alerts', but it was not found"
        ),
    ),
    ProviderInjectionErrorTestCase(
        description="annotation mismatch errors clearly",
        function=mismatched_provider,
        expected_error_fragment=(
            "Provider parameter 'slack_provider' expected ClockProvider, "
            "but provider 'slack_provider' is SlackProvider"
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderInjectionTestCase(
            description="context-only function still receives context",
            function=context_only,
            expected_result="runtime-context",
        )
    ],
    ids=["context-only function still receives context"],
)
def test_given_context_only_function_when_calling_with_provider_injection_then_context_is_preserved(
    test_case: ProviderInjectionTestCase,
) -> None:
    result: object = call_with_provider_injection(
        function=test_case.function,
        context="runtime-context",
        providers=ProviderSession({}).providers,
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    PROVIDER_INJECTION_TEST_CASES,
    ids=[case.description for case in PROVIDER_INJECTION_TEST_CASES],
)
def test_given_provider_parameter_when_calling_with_provider_injection_then_provider_is_injected(
    test_case: ProviderInjectionTestCase,
) -> None:
    providers: ProviderContainer = ProviderSession({"slack_provider": SlackProvider()}).providers

    result: object = call_with_provider_injection(
        function=test_case.function,
        context="runtime-context",
        providers=providers,
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderInjectionLabelTestCase(
            description="unannotated provider parameter uses name-based injection",
            function=unannotated_provider,
            expected_label="slack",
        )
    ],
    ids=["unannotated provider parameter uses name-based injection"],
)
def test_given_unannotated_provider_parameter_when_name_matches_then_provider_is_injected(
    test_case: ProviderInjectionLabelTestCase,
) -> None:
    providers: ProviderContainer = ProviderSession({"slack_provider": SlackProvider()}).providers

    result: object = call_with_provider_injection(
        function=test_case.function,
        context="runtime-context",
        providers=providers,
    )

    assert isinstance(result, SlackProvider)
    assert result.label == test_case.expected_label


@pytest.mark.parametrize(
    "test_case",
    PROVIDER_INJECTION_ERROR_TEST_CASES,
    ids=[case.description for case in PROVIDER_INJECTION_ERROR_TEST_CASES],
)
def test_given_invalid_provider_parameter_when_calling_then_errors_clearly(
    test_case: ProviderInjectionErrorTestCase,
) -> None:
    providers: ProviderContainer = ProviderSession({"slack_provider": SlackProvider()}).providers

    with pytest.raises(ProviderInjectionError, match=test_case.expected_error_fragment):
        call_with_provider_injection(
            function=test_case.function,
            context="runtime-context",
            providers=providers,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderInjectionErrorTestCase(
            description="provider cannot shadow reserved context parameter",
            function=reserved_context_conflict,
            expected_error_fragment=(
                "Provider name 'ctx' conflicts with reserved context parameter 'ctx'"
            ),
        )
    ],
    ids=["provider cannot shadow reserved context parameter"],
)
def test_given_provider_name_conflicts_with_context_parameter_when_calling_then_errors_clearly(
    test_case: ProviderInjectionErrorTestCase,
) -> None:
    providers: ProviderContainer = ProviderSession({"ctx": SlackProvider()}).providers

    with pytest.raises(ProviderInjectionError, match=test_case.expected_error_fragment):
        call_with_provider_injection(
            function=test_case.function,
            context="runtime-context",
            providers=providers,
        )
