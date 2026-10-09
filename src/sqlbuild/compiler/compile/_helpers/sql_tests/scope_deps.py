"""Scope dependencies of macro, UDF and table-function SQL tests."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.render.macros import find_macro_call_names
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompileModelInput
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.references.types import SqlReferenceKind


def macro_sql_test_scope_deps(
    *, tested_macro_names: tuple[str, ...], model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompiledObjectKey, ...]:
    """Return the models whose macro calls include a tested macro."""

    tested_names: frozenset[str] = frozenset(tested_macro_names)
    scope_deps: list[CompiledObjectKey] = []
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_macro_deps: frozenset[str] = frozenset(
            model_input.macro_deps or find_macro_call_names(model_input.macro_source_sql)
        )
        if not tested_names.intersection(model_macro_deps):
            continue
        scope_deps.append(
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL,
                name=model_input.model_file.file_path.stem,
            )
        )
    return tuple(scope_deps)


def udf_sql_test_scope_deps(
    *, tested_udf_names: tuple[str, ...], model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompiledObjectKey, ...]:
    """Return the models that call a tested UDF."""

    tested_names: frozenset[str] = frozenset(tested_udf_names)
    scope_deps: list[CompiledObjectKey] = []
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_udf_deps: frozenset[str] = frozenset(
            reference.ref_name
            for reference in model_input.references
            if reference.ref_kind == SqlReferenceKind.UDF
        )
        if not tested_names.intersection(model_udf_deps):
            continue
        scope_deps.append(
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL,
                name=model_input.model_file.file_path.stem,
            )
        )
    return tuple(scope_deps)


def function_sql_test_scope_deps(
    *, tested_function_names: tuple[str, ...]
) -> tuple[CompiledObjectKey, ...]:
    """Return the tested table functions as scope dependencies."""

    return tuple(
        CompiledObjectKey(resource_type=CompiledResourceType.TABLE_FN, name=function_name)
        for function_name in tested_function_names
    )
