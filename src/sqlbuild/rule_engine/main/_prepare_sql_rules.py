"""Start reusable SQL lint work after all compiler inputs have been expanded."""

from __future__ import annotations

from concurrent.futures import Executor

from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.rule_engine._helpers.run.rules import prepare_sql_rules as prepare
from sqlbuild.rule_engine.models import PreparedSqlLint


def prepare_sql_rules(
    *, inputs: CompileProjectInputs, executor: Executor, dialect: str
) -> PreparedSqlLint | None:
    """Prepare configured SQL checks without publishing findings before compilation finishes."""

    return prepare(inputs=inputs, executor=executor, dialect=dialect)
