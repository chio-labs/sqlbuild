"""Generated authored SQL for the native attachment parity tests."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_result
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import AuthoredSqlExpansionResult, MacroContext
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.sql_values.types import CollectionRendering
from tests.integration.src.sqlbuild.compiler.model_loop.helpers import (
    DECLARATIONS,
    generated_reference_sql,
)

EFFECTIVE_VARS: dict[str, object] = {
    "region": "north",
    "limit_rows": 10,
    "ratio": 0.5,
    "enabled": True,
    "unset": None,
    "regions": ["north", "south"],
}
_VARIABLE_TOKENS: tuple[str, ...] = (
    "@@region",
    "@@limit_rows ",
    "'@@region'",
    "@@ratio",
    "@@enabled",
    "@@unset",
    "@@@window_start",
    "@@ENV:SQB_ORDERS_REGION",
    "@@ENV:SQB_MISSING_REGION",
    "@@regions",
    "@@missing",
    "@@CTX:run.target",
    "-- @@missing\n",
)
_MACRO_CONTEXT: MacroContext = MacroContext(
    adapter_name="duckdb", sql_analysis_enabled=True, target_name="dev"
)


def generated_authored_sql(*, rng: random.Random) -> str:
    """Return SQL mixing project variables with enum and constant references."""

    parts: list[str] = [
        generated_reference_sql(rng=rng),
        *rng.choices(_VARIABLE_TOKENS, k=rng.randint(0, 3)),
    ]
    rng.shuffle(parts)
    return " ".join(parts)


def authored_outcome(
    *, sql: str, engine: CompilerEngine, monkeypatch: pytest.MonkeyPatch
) -> AuthoredSqlExpansionResult | str:
    """Expand one string under `engine`, returning the result or Python's error text."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    monkeypatch.setenv("SQB_ORDERS_REGION", "south")
    try:
        return expand_authored_sql_result(
            sql=sql,
            file_path=Path("audits/orders.sql"),
            effective_vars=EFFECTIVE_VARS,
            loaded_macros={},
            macro_context=_MACRO_CONTEXT,
            value_renderer=DuckDbAdapter(),
            collection_rendering=CollectionRendering.VALUE_LIST,
            declarations=DECLARATIONS,
        )
    except CompileInputError as error:
        return str(error)
