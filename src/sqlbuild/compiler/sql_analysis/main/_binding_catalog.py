"""Create one native catalog for a compiled project's binding lifetime."""

from collections.abc import Mapping

from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog


def create_binding_catalog(
    *,
    dialect: str,
    quoted_ignore_case: bool,
    known_functions: tuple[str, ...],
    known_types: tuple[str, ...],
    relations: Mapping[str, Mapping[str, str]],
) -> BindingCatalog:
    return BindingCatalog(
        dialect=dialect,
        quoted_ignore_case=quoted_ignore_case,
        known_functions=known_functions,
        known_types=known_types,
        relations=relations,
    )
