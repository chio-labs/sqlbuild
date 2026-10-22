"""Project builders and filesystem changes for project input fingerprint tests."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from sqlbuild.cli.compile_reuse.models import (
    SettingsInputsResult,
)

SETTINGS_TOKEN_ENV_VAR: str = "ORDERS_API_TOKEN"
SETTINGS_ENV_FILE_NAME: str = "orders_api.env"
SETTINGS_SECRETS_DIR_NAME: str = "orders_secrets"


class OrdersApiSettings(BaseSettings):
    """Plain provider settings read from one environment variable per field."""

    orders_api_token: str = ""


class PrefixedOrdersSettings(BaseSettings):
    """Provider settings read through an environment prefix."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="ORDERS_")

    token: str = ""


class AliasedOrdersSettings(BaseSettings):
    """Provider settings read through alias choices."""

    token: str = Field(default="", validation_alias=AliasChoices("ORDERS_KEY", "LEGACY_KEY"))


class OrdersEndpoint(BaseModel):
    """Nested endpoint settings."""

    host: str = "localhost"


class NestedOrdersSettings(BaseSettings):
    """Provider settings with nested values split by a delimiter."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_nested_delimiter="__")

    endpoint: OrdersEndpoint = OrdersEndpoint()


class CaseSensitiveOrdersSettings(BaseSettings):
    """Provider settings matched case-sensitively."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(case_sensitive=True)

    OrdersToken: str = ""


class FileOrdersSettings(BaseSettings):
    """Provider settings that also read an env file and a secrets directory."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=SETTINGS_ENV_FILE_NAME, secrets_dir=SETTINGS_SECRETS_DIR_NAME
    )

    orders_api_token: str = ""


class CustomSourceOrdersSettings(BaseSettings):
    """Provider settings whose sources cannot be enumerated."""

    orders_api_token: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read only the environment."""

        return (env_settings,)


class CommandLineOrdersSettings(BaseSettings):
    """Provider settings that would parse command-line arguments."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(cli_parse_args=False)

    orders_api_token: str = ""


def described_settings_inputs(
    *, result: SettingsInputsResult
) -> tuple[tuple[bool, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...]:
    """Describe enumerated settings inputs with file and directory paths reduced to names."""

    return tuple(
        (
            item.case_sensitive,
            item.names,
            item.prefixes,
            _path_names(item.env_files),
            _path_names(item.secrets_dirs),
        )
        for item in result.inputs
    )


def _path_names(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(Path(path).name for path in paths)
