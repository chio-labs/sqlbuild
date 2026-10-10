"""Project builders and filesystem changes for project input fingerprint tests."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from sqlbuild.cli.compile_reuse._helpers.runtime_identity import invocation_identity
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseRequest,
    SettingsEnvironmentInputs,
    SettingsInputsResult,
)
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR, STAGE_CAPTURE_DIR_ENV_VAR


def write_file(path: Path, contents: str) -> None:
    """Write one file, creating parent folders."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


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


def file_settings_inputs(*, root: Path) -> SettingsEnvironmentInputs:
    """Describe FileOrdersSettings as if read from root, the process working directory."""

    return SettingsEnvironmentInputs(
        case_sensitive=False,
        names=("orders_api_token",),
        prefixes=(),
        env_files=(str(root / SETTINGS_ENV_FILE_NAME),),
        secrets_dirs=(str(root / SETTINGS_SECRETS_DIR_NAME),),
    )


def set_token(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Set the tracked token variable."""

    monkeypatch.setenv(SETTINGS_TOKEN_ENV_VAR, value)


def write_settings_file(root: Path, relative_path: str, contents: str) -> None:
    """Write one env file or secrets file below root."""

    write_file(root / relative_path, contents)


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


def orders_reuse_request(project_dir: Path) -> CompileReuseRequest:
    """Return a plain JSON compile reuse request for a project."""

    return CompileReuseRequest(
        project_dir=project_dir,
        selected_target=None,
        json_output=True,
        no_color=True,
        manifest=False,
        dag_path=None,
        defer_to=None,
        no_cache=False,
        no_sql_validation=False,
        lineage_mode="fast",
        select=(),
        exclude=(),
        cli_vars=None,
        profiling=False,
        debug=False,
    )


def engine_reuse_key(
    *, environment: dict[str, str], project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> bytes:
    """Return the encoded invocation identity under one engine environment."""

    monkeypatch.delenv(COMPILER_ENGINE_ENV_VAR, raising=False)
    monkeypatch.delenv(STAGE_CAPTURE_DIR_ENV_VAR, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return invocation_identity(
        request=orders_reuse_request(project_dir), project_dir=str(project_dir), use_color=False
    )
