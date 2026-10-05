"""Enumerate where provider settings classes read values outside the project files."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import TYPE_CHECKING, cast

from sqlbuild.cli.compile_reuse.models import SettingsEnvironmentInputs, SettingsInputsResult

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings

_CLI_CONFIG_KEYS: tuple[str, ...] = ("cli_parse_args", "cli_settings_source")


def provider_settings_inputs(*, settings_classes: tuple[type, ...]) -> SettingsInputsResult:
    """Return every environment name, env file, and secrets dir the settings classes read."""

    if not settings_classes:
        return SettingsInputsResult(inputs=())
    from pydantic_settings import BaseSettings

    inputs: list[SettingsEnvironmentInputs] = []
    for settings_class in settings_classes:
        if not issubclass(settings_class, BaseSettings):
            continue
        reason: str | None = _unsupported_reason(settings_class=settings_class)
        if reason is not None:
            return SettingsInputsResult(inputs=(), unsupported_reason=reason)
        try:
            inputs.append(_settings_inputs(settings_class=settings_class))
        except (AttributeError, TypeError, ValueError) as error:
            return SettingsInputsResult(
                inputs=(),
                unsupported_reason=(
                    f"settings of {settings_class.__qualname__} could not be enumerated: {error}"
                ),
            )
    return SettingsInputsResult(inputs=tuple(inputs))


def _unsupported_reason(*, settings_class: type[BaseSettings]) -> str | None:
    from pydantic_settings import BaseSettings

    if (
        settings_class.settings_customise_sources.__func__  # type: ignore[attr-defined]
        is not BaseSettings.settings_customise_sources.__func__  # type: ignore[attr-defined]
    ):
        return f"{settings_class.__qualname__} customizes its settings sources"
    for key in _CLI_CONFIG_KEYS:
        if settings_class.model_config.get(key) is not None:
            return f"{settings_class.__qualname__} reads settings from command-line arguments"
    return None


def _settings_inputs(*, settings_class: type[BaseSettings]) -> SettingsEnvironmentInputs:
    from pydantic_settings import EnvSettingsSource

    source: EnvSettingsSource = EnvSettingsSource(settings_class)
    nested_delimiter: str | None = source.env_nested_delimiter or None
    names: set[str] = set()
    for field_name, field in settings_class.model_fields.items():
        names.update(env_name for _, env_name, _ in source._extract_field_info(field, field_name))
    return SettingsEnvironmentInputs(
        case_sensitive=bool(source.case_sensitive),
        names=tuple(sorted(names)),
        prefixes=()
        if nested_delimiter is None
        else tuple(sorted(f"{name}{nested_delimiter}" for name in names)),
        env_files=_absolute_paths(settings_class.model_config.get("env_file")),
        secrets_dirs=_absolute_paths(settings_class.model_config.get("secrets_dir")),
    )


def _absolute_paths(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    items: tuple[object, ...] = (
        (value,) if isinstance(value, (str, os.PathLike)) else tuple(cast(Iterable[object], value))
    )
    return tuple(
        os.path.abspath(os.path.expanduser(os.fspath(item)))
        for item in items
        if isinstance(item, (str, os.PathLike))
    )
