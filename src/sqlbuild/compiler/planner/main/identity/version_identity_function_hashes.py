"""Build function hashes that participate in model version identity."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.compile.models import CompiledFunction


def build_function_local_hashes(
    *,
    functions: tuple[CompiledFunction, ...],
) -> dict[str, str]:
    """Derive local-only semantic hashes for functions."""

    hashes: dict[str, str] = {}
    for function in functions:
        arguments: list[tuple[str, str]] = []
        for argument in function.arguments:
            arguments.append((argument.name, argument.type))
        hashes[function.name] = _stable_hash(
            json.dumps(
                {
                    "arguments": arguments,
                    "returns": function.returns,
                    "body_sql": function.body_sql,
                    "language": function.language.value,
                },
                sort_keys=True,
                default=str,
            )
        )
    return hashes


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
