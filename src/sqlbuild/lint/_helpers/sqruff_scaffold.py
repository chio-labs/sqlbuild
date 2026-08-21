"""Scaffold and inspect the user-owned sqruff configuration file."""

from __future__ import annotations

import configparser
import tomllib
from pathlib import Path

from sqlbuild.lint.constants import (
    ADAPTER_CONFIG_KEY,
    ADAPTER_DIALECT_TRANSLATIONS,
    CONFIG_QUOTE_CHARACTERS,
    DEFAULT_SQRUFF_CONFIG_TEMPLATE,
    FALLBACK_SQRUFF_DIALECT,
    MINIMUM_QUOTED_LENGTH,
    PROJECT_CONFIG_FILENAME_KEY,
    SQRUFF_CONFIG_DIALECT_KEY,
    SQRUFF_CONFIG_SECTION,
)


def translate_adapter_dialect(*, adapter: str) -> str | None:
    """Translate a sqlbuild adapter name into a sqruff dialect name."""

    return ADAPTER_DIALECT_TRANSLATIONS.get(adapter.lower())


def ensure_sqruff_config(
    *, project_dir: Path, config_path: str, sqruff_enabled: bool
) -> str | None:
    """Create the sqruff config when missing; return a drift warning when present."""

    if not sqruff_enabled:
        return None
    config_file: Path = project_dir / config_path
    adapter: str | None = _read_project_adapter(project_dir=project_dir)
    translated: str | None = None if adapter is None else translate_adapter_dialect(adapter=adapter)
    if not config_file.exists():
        dialect: str = translated if translated is not None else FALLBACK_SQRUFF_DIALECT
        _ = config_file.write_text(
            DEFAULT_SQRUFF_CONFIG_TEMPLATE.format(dialect=dialect), encoding="utf-8"
        )
        return None
    if translated is None:
        return None
    configured: str | None = _read_configured_dialect(config_file=config_file)
    if configured is None or configured == translated:
        return None
    return (
        f"{config_path} dialect '{configured}' differs from project adapter "
        f"'{adapter}' ('{translated}'); using {config_path} as-is"
    )


def _read_project_adapter(*, project_dir: Path) -> str | None:
    config_file: Path = project_dir / PROJECT_CONFIG_FILENAME_KEY
    if not config_file.is_file():
        return None
    with config_file.open("rb") as handle:
        payload: dict[str, object] = tomllib.load(handle)
    adapter: object = payload.get(ADAPTER_CONFIG_KEY)
    if isinstance(adapter, str):
        return adapter
    return None


def read_configured_dialect(*, config_file: Path) -> str | None:
    """Read the dialect declared in a sqruff config, if any."""

    return _read_configured_dialect(config_file=config_file)


def _read_configured_dialect(*, config_file: Path) -> str | None:
    parser: configparser.ConfigParser = configparser.ConfigParser()
    _ = parser.read(config_file, encoding="utf-8")
    if not parser.has_section(SQRUFF_CONFIG_SECTION):
        return None
    if not parser.has_option(SQRUFF_CONFIG_SECTION, SQRUFF_CONFIG_DIALECT_KEY):
        return None
    raw_value: str = parser.get(SQRUFF_CONFIG_SECTION, SQRUFF_CONFIG_DIALECT_KEY)
    return _strip_quotes(raw_value.strip())


def _strip_quotes(value: str) -> str:
    if (
        len(value) >= MINIMUM_QUOTED_LENGTH
        and value[0] == value[-1]
        and value[0] in CONFIG_QUOTE_CHARACTERS
    ):
        return value[1:-1]
    return value
