"""Render selected dbt profile output Jinja."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import ResolvedDbtProfileOutput, SelectedDbtProfileOutput

_DBT_FALSE_VALUES: frozenset[str] = frozenset({"false", "0", "no", "n", "off"})
_DBT_JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")
_DBT_NUMBER_DECIMAL_SEPARATOR: str = "."
_DBT_TRUE_VALUES: frozenset[str] = frozenset({"true", "1", "yes", "y", "on"})


class _Missing:
    pass


_MISSING: _Missing = _Missing()


@dataclass(frozen=True)
class _TargetContext:
    name: str
    schema: str | None = None
    database: str | None = None


def render_selected_dbt_profile_output(
    *,
    selected: SelectedDbtProfileOutput,
    project_dir: Path,
    profiles_dir: Path,
    cli_vars: Mapping[str, object] | None = None,
) -> ResolvedDbtProfileOutput:
    """Render the selected dbt profile output using a controlled Jinja context."""

    rendered: object = _render_value(
        value=selected.output,
        field_path=selected.target_name,
        target=_TargetContext(name=selected.target_name),
        cli_vars={} if cli_vars is None else cli_vars,
    )
    if not isinstance(rendered, dict):
        raise DbtProfileError(
            f"dbt target '{selected.target_name}' rendered to a non-mapping value"
        )
    return ResolvedDbtProfileOutput(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        profile_name=selected.profile_name,
        target_name=selected.target_name,
        output=cast(dict[str, object], rendered),
    )


def _render_value(
    *,
    value: object,
    field_path: str,
    target: _TargetContext,
    cli_vars: Mapping[str, object],
) -> object:
    if isinstance(value, str):
        return _render_string(value=value, field_path=field_path, target=target, cli_vars=cli_vars)
    if isinstance(value, list):
        return [
            _render_value(
                value=item,
                field_path=f"{field_path}[{index}]",
                target=target,
                cli_vars=cli_vars,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        rendered_dict: dict[str, object] = {}
        key: object
        item_value: object
        for key, item_value in value.items():
            if not isinstance(key, str):
                raise DbtProfileError(f"dbt profile field '{field_path}' contains a non-string key")
            rendered_dict[key] = _render_value(
                value=item_value,
                field_path=f"{field_path}.{key}",
                target=target,
                cli_vars=cli_vars,
            )
        return rendered_dict
    return value


def _render_string(
    *,
    value: str,
    field_path: str,
    target: _TargetContext,
    cli_vars: Mapping[str, object],
) -> object:
    if all(marker not in value for marker in _DBT_JINJA_MARKERS):
        return value
    try:
        from jinja2 import StrictUndefined
        from jinja2.nativetypes import NativeEnvironment
    except ImportError as error:
        raise DbtProfileError(
            "dbt profile rendering requires Jinja. Install SQLBuild's dbt extra with: "
            'pip install "sqlbuild[dbt]"'
        ) from error

    def env_var(name: str, default: object = _MISSING) -> object:
        raw: str | None = os.environ.get(name)
        if raw is not None:
            return raw
        if default is not _MISSING:
            return default
        raise DbtProfileError(
            f"dbt profile field '{field_path}' requires missing environment variable {name!r}"
        )

    def var(name: str, default: object = _MISSING) -> object:
        if name in cli_vars:
            return cli_vars[name]
        if default is not _MISSING:
            return default
        raise DbtProfileError(f"dbt profile field '{field_path}' requires missing var {name!r}")

    environment: NativeEnvironment = NativeEnvironment(undefined=StrictUndefined)
    globals_map: dict[str, Any] = cast(dict[str, Any], environment.globals)
    globals_map["env_var"] = env_var
    globals_map["var"] = var
    globals_map["target"] = target
    environment.filters.update(
        {
            "as_bool": _as_bool,
            "as_number": _as_number,
            "as_native": _as_native,
        }
    )
    try:
        return environment.from_string(value).render()
    except DbtProfileError:
        raise
    except Exception as error:
        raise DbtProfileError(
            f"Could not render dbt profile field '{field_path}': {error}"
        ) from error


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized: str = value.strip().lower()
        if normalized in _DBT_TRUE_VALUES:
            return True
        if normalized in _DBT_FALSE_VALUES:
            return False
    raise DbtProfileError(f"Cannot coerce {value!r} to bool")


def _as_number(value: object) -> int | float:
    if isinstance(value, bool):
        raise DbtProfileError(f"Cannot coerce {value!r} to number")
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped: str = value.strip()
        try:
            if _DBT_NUMBER_DECIMAL_SEPARATOR in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError as error:
            raise DbtProfileError(f"Cannot coerce {value!r} to number") from error
    raise DbtProfileError(f"Cannot coerce {value!r} to number")


def _as_native(value: object) -> object:
    return value
