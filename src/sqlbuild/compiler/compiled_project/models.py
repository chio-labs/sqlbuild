"""Data the native model loop hands its Python callbacks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompileModelConfig


@dataclass(frozen=True)
class PlainModelFacts:
    """What the native loop finished for one model: config, references, query and description."""

    config: CompileModelConfig
    values: dict[str, object]
    references: list[tuple[str, str, str | None, int | None]]
    query_sql: str
    description: str | None
