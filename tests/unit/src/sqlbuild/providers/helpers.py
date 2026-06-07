"""Helpers for provider API tests."""

from __future__ import annotations

from sqlbuild.providers import Provider


def construct_provider(provider_cls: type[Provider]) -> Provider:
    return provider_cls()
