"""Build function hashes that participate in model version identity."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.compile.models.core import CompiledFunction


def build_function_local_hashes(
    *,
    functions: tuple[CompiledFunction, ...],
) -> dict[str, str]:
    """Derive local-only semantic hashes for functions."""

    return {
        function.name: _stable_hash(
            json.dumps(
                {
                    "arguments": [
                        (argument.name, argument.type) for argument in function.arguments
                    ],
                    "returns": function.returns,
                    "body_sql": function.body_sql,
                    "language": function.language.value,
                },
                sort_keys=True,
                default=str,
            )
        )
        for function in functions
    }


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
