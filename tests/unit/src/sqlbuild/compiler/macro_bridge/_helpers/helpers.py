from __future__ import annotations

import datetime
import decimal
import json
import os
from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.models import DeclarationResolutionContext, LoadedMacro, MacroContext
from sqlbuild.compiler.discovery.models import ConstantDeclaration
from sqlbuild.sql_values.models import SqlLogicalType, SqlValue
from sqlbuild.sql_values.types import SqlValueKind

BASE_CONTEXT: MacroContext = MacroContext(
    adapter_name="duckdb",
    sql_analysis_enabled=False,
    target_name="dev",
    vars={
        "region": "north",
        "limits": [1, 2.5, decimal.Decimal("3.10")],
        "since": datetime.date(2026, 1, 1),
    },
)


def with_vars(**values: object) -> MacroContext:
    """The base context with some vars replaced."""

    return replace(BASE_CONTEXT, vars={**BASE_CONTEXT.vars, **values})


def constant_declarations(value: int) -> DeclarationResolutionContext:
    """Declarations holding one integer constant."""

    return DeclarationResolutionContext(
        constants={
            "base_rate": ConstantDeclaration(
                name="base_rate",
                value=SqlValue(logical_type=SqlLogicalType(kind=SqlValueKind.INTEGER), value=value),
                relative_path=Path("constants/base_rate.sql"),
            )
        }
    )


def loaded_macro(*, relative_path: Path, raw_source: str) -> LoadedMacro:
    """A loaded `cents` macro from the given file."""

    return LoadedMacro(
        name="cents",
        file_path=Path("/project") / relative_path,
        relative_path=relative_path,
        raw_source=raw_source,
        function=lambda column: column,
    )


def write_module(path: Path, text: str) -> bytes:
    """Write a module file and return metadata stamping its current state."""

    _ = path.write_text(text, encoding="utf-8")
    status: os.stat_result = path.stat()
    return json.dumps([[str(path), status.st_mtime_ns, status.st_size]]).encode()


def rewritten_module(path: Path) -> bytes:
    """Stamp a module, then rewrite it with the same size and a later modification time."""

    metadata: bytes = write_module(path, "VALUE = 1\n")
    _ = path.write_text("VALUE = 2\n", encoding="utf-8")
    status: os.stat_result = path.stat()
    os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000))
    return metadata


def removed_module(path: Path) -> bytes:
    """Stamp a module, then remove it."""

    metadata: bytes = write_module(path, "VALUE = 1\n")
    path.unlink()
    return metadata


def write_environment_project(root: Path) -> None:
    """Write a model and a macro for store environment checks."""

    (root / "models").mkdir()
    (root / "macros").mkdir()
    _ = (root / "models/orders.sql").write_text("SELECT 1\n", encoding="utf-8")
    _ = (root / "macros/common.py").write_text("X = 1\n", encoding="utf-8")


EXCLUDED_MODEL_PATHS: list[str] = ["models/orders.sql"]
