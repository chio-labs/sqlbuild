"""Collect destination models whose resolved table type is transient."""

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.spec.contracts.types import TableType


def build_destination_transient_models(*, project: CompiledProjectView) -> frozenset[str]:
    """Return destination model names that clones should create as transient tables."""

    return frozenset(
        model.name
        for model in project.models
        if model.config.table_type.value == TableType.TRANSIENT
    )
