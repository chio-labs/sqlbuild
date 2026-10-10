"""Python views of models the native model loop finished, for stages that still read them."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import (
    CompiledSqlExpansion,
    CompileModelInput,
    CompileSqlReference,
    ExpansionSpan,
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

    _report_native_steps(described=facts.schema is not None)
    interpolated_sql: str = str(interpolation.sql)
    macro_sql: str = (
        facts.declaration_sql if facts.macro_expansion is None else facts.macro_expansion.sql
    )
    macro_spans: tuple[ExpansionSpan, ...] = (
        () if facts.macro_expansion is None else facts.macro_expansion.spans
    )
    local_enums: tuple[EnumDeclaration, ...] = tuple(declarations[0].values())
    local_constants: tuple[ConstantDeclaration, ...] = tuple(declarations[1].values())
    model_input: CompileModelInput = CompileModelInput(
        sql_expansion=(
            CompiledSqlExpansion(
                authored_sql=model_file.query_sql,
                expanded_sql=macro_sql,
                passes=(facts.declaration_spans, macro_spans),
            )
            if interpolated_sql == model_file.query_sql
            else None
        ),
        model_file=model_file,
        config=replace(facts.config, values=facts.values),
        query_sql=facts.query_sql,
        macro_source_sql=facts.declaration_sql,
        references=tuple(
            CompileSqlReference(
                ref_kind=SqlReferenceKind(kind),
                ref_name=name,
                ref_package=package,
                call_argument_count=call_argument_count,
            )
            for kind, name, package, call_argument_count in facts.references
        ),
        schema_entry=_schema_entry(model_file=model_file, facts=facts),
        sql_validation_enabled=facts.sql_validation_enabled,
        rejected_sql_analysis_opt_out=facts.rejected_sql_analysis_opt_out,
        enum_declarations=local_enums,
        constant_declarations=local_constants,
        enum_columns=facts.enum_columns,
        macro_deps=(
            ()
            if facts.macro_expansion is None
            else tuple(item.name for item in facts.macro_expansion.dependencies)
        ),
        macro_usages=() if facts.macro_expansion is None else facts.macro_expansion.usages,
        declaration_usages=facts.declaration_usages,
        lint_expansion=CompiledSqlExpansion(
            authored_sql=model_file.query_sql,
            expanded_sql=macro_sql,
            passes=(interpolation.spans, facts.declaration_spans, macro_spans),
        ),
    )
    return model_input, declaration_rows(enums=local_enums, constants=local_constants)


def _schema_entry(
    *, model_file: DiscoveredSqlModelFile, facts: PlainModelFacts
) -> SchemaModelEntry | None:
    if facts.schema is None:
        return None
    columns, audits, typed, dynamic_columns, model_schema = facts.schema
    return SchemaModelEntry(
        name=model_file.file_path.stem,
        model_schema=model_schema,
        description=facts.description,
        type_enforcement=True if typed else None,
        columns=columns,
        dynamic_columns=dynamic_columns,
        audits=audits,
    )


def _report_native_steps(*, described: bool) -> None:
    """Report the native answers the attachment reports for the same model."""

    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="declaration_expansions")
    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="cursor_intrinsic_validations")
    report_native_answer(stage=NativeStage.MODEL_CONFIG, kind="validations")
    if described:
        report_native_answer(stage=NativeStage.MODEL_CONFIG, kind="header_metadata_parses")
