"""Typed SQL reference graph key entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.sql_refs import sql_ref_key_impl
from sqlbuild.python_nodes.models import SqlResourceRef


def sql_ref_key(ref: SqlResourceRef) -> CompiledObjectKey:
    """Return the compiled graph key a typed model, source, or seed reference names."""

    return sql_ref_key_impl(ref)
