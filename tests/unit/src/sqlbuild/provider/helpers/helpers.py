"""Helpers for provider helper tests."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.providers import Provider


class SlackProvider(Provider):
    provider_name: ClassVar[str] = "slack_provider"
    label: str = "slack"


class ClockProvider(Provider):
    provider_name: ClassVar[str] = "clock_provider"
    label: str = "clock"


def context_only(ctx: object) -> object:
    return ctx


def context_and_provider(ctx: object, slack_provider: SlackProvider) -> tuple[object, str]:
    return ctx, slack_provider.label


def provider_only(slack_provider: SlackProvider) -> str:
    return slack_provider.label


def unannotated_provider(slack_provider: object) -> object:
    return slack_provider


def missing_provider(alerts: SlackProvider) -> None:
    return None


def mismatched_provider(slack_provider: ClockProvider) -> None:
    return None


def reserved_context_conflict(ctx: object) -> object:
    return ctx
