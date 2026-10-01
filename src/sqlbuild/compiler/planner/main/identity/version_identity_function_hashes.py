"""Build function hashes that participate in model version identity."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.compile.models import CompiledFunction
from sqlbuild.compiler.planner._helpers.identity.hashing import function_definition_hash


def build_function_local_hashes(
    *,
    functions: tuple[CompiledFunction, ...],
    dialect: str | None,
) -> dict[str, str]:
    """Derive local-only semantic hashes for functions; SQL bodies ignore layout and comments."""

    hashes: dict[str, str] = {}
    for function in functions:
        arguments: list[tuple[str, str]] = []
        for argument in function.arguments:
            arguments.append((argument.name, argument.type))
        return_columns: list[tuple[str, str]] = []
        for column in function.return_columns:
            return_columns.append((column.name, column.type))
        hashes[function.name] = _stable_hash(
            json.dumps(
                {
                    "arguments": arguments,
                    "returns": function.returns,
                    "return_columns": return_columns,
                    "body_sql": function_definition_hash(
                        function_name=function.name,
                        fingerprint_sql=function.body_sql,
                        language=function.language.value,
                        dialect=dialect,
                    ),
                    "language": function.language.value,
                    "runtime_version": function.runtime_version,
                    "entry_point": function.entry_point,
                    "packages": function.packages,
                },
                sort_keys=True,
                default=str,
            )
        )
    return hashes


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
