"""Python views of models the native model loop finished, for stages that still read them."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import (
    CompiledSqlExpansion,
    CompileModelInput,
    CompileSqlReference,
    SqlInterpolation,
)
from sqlbuild.compiler.compiled_project.main.declaration_rows import declaration_rows
from sqlbuild.compiler.compiled_project.models import PlainModelFacts
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredSqlModelFile,
    EnumDeclaration,
)
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SchemaModelEntry


def plain_model_input_impl(
    *,
    model_file: DiscoveredSqlModelFile,
    interpolation: SqlInterpolation,
    facts: PlainModelFacts,
    declarations: tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]],
) -> tuple[CompileModelInput, tuple[list[tuple[object, ...]], list[tuple[object, ...]]]]:
    """The model input the attachment would build, and its local declaration rows."""

    _report_native_steps(described=facts.description is not None)
    interpolated_sql: str = str(interpolation.sql)
    local_enums: tuple[EnumDeclaration, ...] = tuple(declarations[0].values())
    local_constants: tuple[ConstantDeclaration, ...] = tuple(declarations[1].values())
    model_input: CompileModelInput = CompileModelInput(
        sql_expansion=(
            CompiledSqlExpansion(
                authored_sql=model_file.query_sql, expanded_sql=interpolated_sql, passes=((), ())
            )
            if interpolated_sql == model_file.query_sql
            else None
        ),
        model_file=model_file,
        config=replace(facts.config, values=facts.values),
        query_sql=facts.query_sql,
        macro_source_sql=interpolated_sql,
        references=tuple(
            CompileSqlReference(
                ref_kind=SqlReferenceKind(kind),
                ref_name=name,
                ref_package=package,
                call_argument_count=call_argument_count,
            )
            for kind, name, package, call_argument_count in facts.references
        ),
        schema_entry=(
            None
            if facts.description is None
            else SchemaModelEntry(name=model_file.file_path.stem, description=facts.description)
        ),
        sql_validation_enabled=True,
        enum_declarations=local_enums,
        constant_declarations=local_constants,
        lint_expansion=CompiledSqlExpansion(
            authored_sql=model_file.query_sql,
            expanded_sql=interpolated_sql,
            passes=(interpolation.spans, (), ()),
        ),
    )
    return model_input, declaration_rows(enums=local_enums, constants=local_constants)


def _report_native_steps(*, described: bool) -> None:
    """Report the native answers the attachment reports for the same model."""

    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="declaration_expansions")
    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="cursor_intrinsic_validations")
    report_native_answer(stage=NativeStage.MODEL_CONFIG, kind="validations")
    if described:
        report_native_answer(stage=NativeStage.MODEL_CONFIG, kind="header_metadata_parses")
