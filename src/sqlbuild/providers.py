"""Public provider API for runtime services."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict

from sqlbuild.provider.exceptions import ProviderInputError


class Provider(BaseSettings):
    """Base class for SQLBuild runtime providers."""

    provider_name: ClassVar[str | None] = None

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="forbid", arbitrary_types_allowed=True
    )

    @classmethod
    def name(cls) -> str:
        """Return the runtime provider name for this provider class."""

        raw_name: str | None = cls.provider_name
        if raw_name is None:
            class_name: str = cls.__name__
            if class_name.endswith("Provider"):
                class_name = class_name[: -len("Provider")]
            raw_name = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()

        if not raw_name:
            raise ProviderInputError(f"provider {cls.__name__} resolved to an empty name")
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", raw_name):
            raise ProviderInputError(
                f"provider {cls.__name__} has invalid provider name '{raw_name}'; "
                "provider names must be lower snake_case Python identifiers"
            )
        return raw_name

    def setup(self, ctx: Any) -> None:
        """Prepare the provider for runtime use."""

    def teardown(self) -> None:
        """Release runtime resources held by the provider."""
