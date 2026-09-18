"""Dynamic column-family configuration parsing for model headers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def parse_dynamic_column_families(
    *, raw_value: object | None, model_name: str, file_path: Path
) -> tuple[SchemaDynamicColumnFamily, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, dict) or not raw_value:
        raise CompileInputError(
            f"model '{model_name}' dynamic_columns must be a non-empty named block in {file_path}"
        )
    allowed_keys: frozenset[str] = frozenset(
        {"pivot_column", "value_column", "aggregate", "type", "name_pattern"}
    )
    families: list[SchemaDynamicColumnFamily] = []
    for family_name, raw_family in raw_value.items():
        if not isinstance(family_name, str) or not family_name:
            raise CompileInputError(
                f"model '{model_name}' dynamic column family names must be non-empty strings"
            )
        if not isinstance(raw_family, dict):
            raise CompileInputError(
                f"model '{model_name}' dynamic column family '{family_name}' must be a block"
            )
        family_values: dict[str, object] = {str(key): value for key, value in raw_family.items()}
        unknown_keys: set[str] = set(family_values) - allowed_keys
        if unknown_keys:
            raise CompileInputError(
                f"model '{model_name}' dynamic column family '{family_name}' has unsupported keys: "
                f"{', '.join(sorted(unknown_keys))}"
            )
        pivot_column: object = family_values.get("pivot_column")
        value_column: object = family_values.get("value_column")
        aggregate: object = family_values.get("aggregate")
        data_type: object = family_values.get("type")
        for key, value in (
            ("pivot_column", pivot_column),
            ("value_column", value_column),
            ("aggregate", aggregate),
            ("type", data_type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise CompileInputError(
                    f"model '{model_name}' dynamic column family '{family_name}' requires a "
                    f"non-empty {key}"
                )
        name_pattern: object = family_values.get("name_pattern")
        if name_pattern is not None and (
            not isinstance(name_pattern, str) or not name_pattern.strip()
        ):
            raise CompileInputError(
                f"model '{model_name}' dynamic column family '{family_name}' name_pattern must be "
                "a non-empty regular expression"
            )
        if isinstance(name_pattern, str):
            try:
                re.compile(name_pattern)
            except re.error as error:
                raise CompileInputError(
                    f"model '{model_name}' dynamic column family '{family_name}' has invalid "
                    f"name_pattern: {error}"
                ) from error
        families.append(
            SchemaDynamicColumnFamily(
                name=family_name,
                pivot_column=cast(str, pivot_column),
                value_column=cast(str, value_column),
                aggregate=cast(str, aggregate).upper(),
                type=cast(str, data_type),
                name_pattern=name_pattern,
            )
        )
    if len(families) > 1 and any(family.name_pattern is None for family in families):
        raise CompileInputError(
            f"model '{model_name}' declares multiple dynamic column families; each family requires "
            "name_pattern so runtime columns can be classified unambiguously"
        )
    return tuple(families)
