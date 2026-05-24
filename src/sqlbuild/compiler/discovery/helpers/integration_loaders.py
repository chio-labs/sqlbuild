"""Discovery helpers for declarative integration loaders."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery.exceptions import SourceParseError
from sqlbuild.compiler.discovery.helpers.yml_primitives import (
    optional_non_empty_string,
    require_non_empty_string,
)
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.models.source import IntegrationLoaderConfig

_ingestr_strategies: frozenset[str] = frozenset(
    {"replace", "append", "merge", "delete+insert", "truncate+insert"}
)


def integration_loader_name(*, kind: str, source_name: str) -> str:
    """Return the generated loader name for a declarative integration loader."""

    return f"{kind}__{source_name}"


def build_integration_loader_functions(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Build synthetic loader functions for declarative integration loaders."""

    from sqlbuild.integrations.ingestr.main.loaders import build_ingestr_loader_functions

    return build_ingestr_loader_functions(source_files)


def parse_source_integration_loader(
    *, entry: dict[str, object], file_path: Path
) -> IntegrationLoaderConfig | None:
    """Parse any source-level integration loader declaration."""

    raw_ingestr: object | None = entry.get("ingestr")
    if raw_ingestr is not None:
        return IntegrationLoaderConfig(
            kind="ingestr",
            config=_parse_ingestr_source_config(raw_config=raw_ingestr, file_path=file_path),
        )
    return None


def _parse_ingestr_source_config(*, raw_config: object, file_path: Path) -> IngestrSourceConfig:
    if not isinstance(raw_config, dict):
        raise SourceParseError(f"{file_path} source 'ingestr' must be a mapping")
    config: dict[str, object] = cast(dict[str, object], raw_config)
    parsed: IngestrSourceConfig = IngestrSourceConfig(
        source_uri=require_non_empty_string(
            entry=config,
            key="source_uri",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        source_table=require_non_empty_string(
            entry=config,
            key="source_table",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        strategy=optional_non_empty_string(
            entry=config,
            key="strategy",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        incremental_key=optional_non_empty_string(
            entry=config,
            key="incremental_key",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        primary_key=_optional_ingestr_primary_key(entry=config, file_path=file_path),
        columns=optional_non_empty_string(
            entry=config,
            key="columns",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        extra_args=_optional_ingestr_string_tuple(
            entry=config, key="extra_args", file_path=file_path
        ),
    )
    if parsed.strategy is not None and parsed.strategy not in _ingestr_strategies:
        strategies: str = ", ".join(sorted(_ingestr_strategies))
        raise SourceParseError(f"{file_path} source ingestr strategy must be one of: {strategies}")
    return parsed


def _optional_ingestr_primary_key(*, entry: dict[str, object], file_path: Path) -> tuple[str, ...]:
    primary_key: tuple[str, ...] = _optional_ingestr_string_tuple(
        entry=entry, key="primary_key", file_path=file_path
    )
    unique_key: tuple[str, ...] = _optional_ingestr_string_tuple(
        entry=entry, key="unique_key", file_path=file_path
    )
    if primary_key and unique_key:
        raise SourceParseError(
            f"{file_path} source ingestr cannot define both primary_key and unique_key"
        )
    return primary_key or unique_key


def _optional_ingestr_string_tuple(
    *, entry: dict[str, object], key: str, file_path: Path
) -> tuple[str, ...]:
    value: object | None = entry.get(key)
    if value is None:
        return ()
    if isinstance(value, str):
        stripped: str = value.strip()
        if not stripped:
            raise SourceParseError(f"{file_path} source ingestr '{key}' must be non-empty")
        return (stripped,)
    if isinstance(value, list):
        items: list[str] = []
        item: object
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise SourceParseError(
                    f"{file_path} source ingestr '{key}' must contain only non-empty strings"
                )
            items.append(item.strip())
        return tuple(items)
    raise SourceParseError(f"{file_path} source ingestr '{key}' must be a string or list")
