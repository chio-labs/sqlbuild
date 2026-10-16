"""Collect destination models whose resolved table type is transient."""

from sqlbuild._native import TableType
from sqlbuild.compiler.compile.types import CompiledProjectView


def build_destination_transient_models(*, project: CompiledProjectView) -> frozenset[str]:
    """Return destination model names that clones should create as transient tables."""

    return frozenset(
        model.name
        for model in project.models
        if model.config.table_type.value == TableType.TRANSIENT
    )
