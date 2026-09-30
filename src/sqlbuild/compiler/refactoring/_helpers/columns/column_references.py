"""Native column-reference facts for one SQL body, and the edits they imply."""

from __future__ import annotations

import json
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.refactoring._helpers.text.text_edits import manual_at, text_edit
from sqlbuild.compiler.refactoring.constants import (
    CTE_SCOPE_PREFIX,
    QUOTE_CHARACTERS,
    REF_KIND,
    ROOT_SCOPE,
    SEED_KIND,
    SOURCE_KIND,
    UNKNOWN_COLUMN_TYPE,
)
from sqlbuild.compiler.refactoring.models import (
    AnalysisSql,
    BodyContext,
    BodyEdits,
    ColumnFacts,
    ColumnQuery,
    ColumnReference,
    ColumnSite,
    ManualLocation,
    OutputColumn,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import EditKind, NativeColumnReferences, ResourceColumns


def resource_columns(*, project: CompiledProject) -> ResourceColumns:
    """Return the known output columns of every model, source, and seed."""

    columns: ResourceColumns = {}
    for model in project.models:
        names: list[str] = [column.name for column in model.inferred_columns or ()]
        names.extend(
            column.name
            for column in (model.schema_entry.columns if model.schema_entry is not None else ())
            if column.name not in names
        )
        columns[(REF_KIND, model.name)] = tuple(names)
    for source in project.sources:
        columns[(SOURCE_KIND, source.name)] = tuple(
            column.name for column in source.source_entry.columns
        )
    for seed in project.seeds:
        columns[(SEED_KIND, seed.name)] = tuple(column.name for column in seed.schema_entry.columns)
    return columns


def analyze_column(
    *, analysis: AnalysisSql, dialect: str, columns: ResourceColumns, query: ColumnQuery
) -> ColumnFacts:
    """Resolve every use of one column of the target relations in one SQL body."""

    request: dict[str, object] = {
        "sql": analysis.sql,
        "dialect": dialect,
        "column": query.column,
        "schema": {"strict": False, "tables": _schema_tables(analysis=analysis, columns=columns)},
        "target_tables": sorted(query.target_tables),
        "target_ctes": sorted(query.target_ctes),
        "output_ctes": sorted(query.output_scopes),
    }
    payload: dict[str, Any] = json.loads(
        cast(NativeColumnReferences, _native).analyze_column_references_json(json.dumps(request))
    )
    return ColumnFacts(
        parsed=bool(payload.get("parsed")),
        references=tuple(_reference(item) for item in payload.get("references", ())),
        stars=tuple(_site(item) for item in payload.get("stars", ())),
        joins=tuple(_site(item) for item in payload.get("joins", ())),
        unresolved=tuple(_site(item) for item in payload.get("unresolved", ())),
        outputs=tuple(_output(item) for item in payload.get("outputs", ())),
        star_outputs=tuple(str(item) for item in payload.get("starOutputs", ())),
    )


def _schema_tables(*, analysis: AnalysisSql, columns: ResourceColumns) -> list[dict[str, object]]:
    tables: list[dict[str, object]] = []
    key: tuple[str, str]
    placeholders: frozenset[str]
    for key, placeholders in analysis.tables.items():
        known: list[dict[str, str]] = [
            {"name": name, "type": UNKNOWN_COLUMN_TYPE} for name in columns.get(key, ())
        ]
        name: str
        for name in sorted(placeholders):
            table: dict[str, object] = {"name": name, "columns": known}
            tables.append(table)
    return tables


def _reference(item: dict[str, Any]) -> ColumnReference:
    projection: dict[str, Any] | None = item.get("projection")
    return ColumnReference(
        start=int(item["start"]),
        end=int(item["end"]),
        name_start=int(item["nameStart"]),
        name_end=int(item["nameEnd"]),
        scope=str(item["scope"]),
        projected=projection is not None,
        alias=projection.get("alias") if projection is not None else None,
        alias_start=projection.get("aliasStart") if projection is not None else None,
        alias_end=projection.get("aliasEnd") if projection is not None else None,
    )


def _site(item: dict[str, Any]) -> ColumnSite:
    return ColumnSite(scope=str(item["scope"]), start=item.get("start"), end=item.get("end"))


def _output(item: dict[str, Any]) -> OutputColumn:
    return OutputColumn(
        scope=str(item["scope"]),
        start=item.get("start"),
        end=item.get("end"),
        alias_start=item.get("aliasStart"),
        alias_end=item.get("aliasEnd"),
    )


def consumer_edits(
    *,
    facts: ColumnFacts,
    context: BodyContext,
    old: str,
    new: str,
    cascade_root: bool,
    root_stars_pass: bool,
) -> BodyEdits:
    """Rename every reference; keep consumer output names unless the root passes it on."""

    if not facts.parsed:
        return BodyEdits(
            manual=(_manual(context=context, offset=None, reason="SQL could not be analysed"),)
        )
    return combine_body_edits(
        results=(
            *(
                _reference_edits(
                    reference=reference,
                    context=context,
                    old=old,
                    new=new,
                    cascade_root=cascade_root,
                )
                for reference in facts.references
            ),
            *(
                _star_edits(star=star, context=context, old=old, root_stars_pass=root_stars_pass)
                for star in facts.stars
            ),
            *(
                _finding(
                    context=context,
                    site=site,
                    reason=f"USING or NATURAL join on {old}; rewrite it as an ON condition",
                )
                for site in facts.joins
            ),
            *(
                _finding(
                    context=context,
                    site=site,
                    reason=f"cannot tell whether {old} here is the renamed column; qualify it",
                )
                for site in facts.unresolved
            ),
        )
    )


def combine_body_edits(*, results: tuple[BodyEdits, ...]) -> BodyEdits:
    """Concatenate the edits of several analyses of one body."""

    edits: list[TextEdit] = []
    manual: list[ManualLocation] = []
    result: BodyEdits
    for result in results:
        edits.extend(result.edits)
        manual.extend(result.manual)
    return BodyEdits(
        edits=tuple(edits),
        manual=tuple(manual),
        passes_through=any(result.passes_through for result in results),
    )


def _reference_edits(
    *, reference: ColumnReference, context: BodyContext, old: str, new: str, cascade_root: bool
) -> BodyEdits:
    name_span: tuple[int, int] | None = context.map_span(reference.name_start, reference.name_end)
    if name_span is None:
        return BodyEdits(
            manual=(
                _manual(
                    context=context,
                    offset=context.locate(reference.name_start),
                    reason=f"column {old} is referenced in SQL a macro generates; update the "
                    "macro call by hand",
                ),
            )
        )
    authored_name: str = context.contents[name_span[0] : name_span[1]]
    renamed: TextEdit = _rename_span(context=context, span=name_span, new=new)
    if not reference.projected:
        return BodyEdits(edits=(renamed,))
    same_name_alias: bool = reference.alias is not None and reference.alias.lower() == old.lower()
    if (
        reference.scope == ROOT_SCOPE
        and cascade_root
        and (reference.alias is None or same_name_alias)
    ):
        alias_span: tuple[int, int] | None = (
            context.map_span(reference.alias_start, reference.alias_end)
            if same_name_alias
            and reference.alias_start is not None
            and reference.alias_end is not None
            else None
        )
        alias_edits: tuple[TextEdit, ...] = (
            (_rename_span(context=context, span=alias_span, new=new),)
            if alias_span is not None
            else ()
        )
        return BodyEdits(edits=(renamed, *alias_edits), passes_through=True)
    if reference.alias is not None:
        return BodyEdits(edits=(renamed,))
    end_span: tuple[int, int] | None = context.map_span(reference.start, reference.end)
    if end_span is None:
        return BodyEdits(
            manual=(
                _manual(
                    context=context,
                    offset=name_span[0],
                    reason=f"column {old} is projected inside a macro call",
                ),
            )
        )
    return BodyEdits(
        edits=(
            renamed,
            text_edit(
                text=context.contents,
                start=end_span[1],
                end=end_span[1],
                replacement=f" AS {authored_name}",
                kind=EditKind.COLUMN,
                before="",
                after=f"AS {authored_name}",
            ),
        )
    )


def _star_edits(
    *, star: ColumnSite, context: BodyContext, old: str, root_stars_pass: bool
) -> BodyEdits:
    if star.scope.startswith(CTE_SCOPE_PREFIX):
        return BodyEdits()
    if star.scope == ROOT_SCOPE and root_stars_pass:
        return BodyEdits(passes_through=True)
    return _finding(
        context=context,
        site=star,
        reason=(
            f"SELECT * passes {old} through, so this model's output column would be renamed "
            "too; rerun with --cascade or list the columns"
            if star.scope == ROOT_SCOPE
            else f"SELECT * in a subquery passes {old} through; list the columns"
        ),
    )


def _finding(*, context: BodyContext, site: ColumnSite, reason: str) -> BodyEdits:
    return BodyEdits(
        manual=(
            _manual(
                context=context, offset=_site_offset(context=context, site=site), reason=reason
            ),
        )
    )


def _rename_span(*, context: BodyContext, span: tuple[int, int], new: str) -> TextEdit:
    return text_edit(
        text=context.contents,
        start=span[0],
        end=span[1],
        replacement=_respell(authored=context.contents[span[0] : span[1]], name=new),
        kind=EditKind.COLUMN,
    )


def output_edits(
    *, facts: ColumnFacts, context: BodyContext, scopes: frozenset[str], old: str, new: str
) -> BodyEdits:
    """Rename the projection that names the column in the given output scopes."""

    edits: list[TextEdit] = []
    manual: list[ManualLocation] = []
    found: set[str] = set()
    output: OutputColumn
    for output in facts.outputs:
        found.add(output.scope)
        if output.alias_start is not None and output.alias_end is not None:
            alias_span: tuple[int, int] | None = context.map_span(
                output.alias_start, output.alias_end
            )
            if alias_span is None:
                manual.append(
                    _manual(
                        context=context,
                        offset=context.locate(output.alias_start),
                        reason=f"column {old} is named inside a macro call",
                    )
                )
                continue
            edits.append(
                text_edit(
                    text=context.contents,
                    start=alias_span[0],
                    end=alias_span[1],
                    replacement=_respell(
                        authored=context.contents[alias_span[0] : alias_span[1]], name=new
                    ),
                    kind=EditKind.COLUMN,
                )
            )
            continue
        if output.start is None or output.end is None:
            continue
        column_span: tuple[int, int] | None = context.map_span(output.start, output.end)
        if column_span is None:
            manual.append(
                _manual(
                    context=context,
                    offset=context.locate(output.start),
                    reason=f"column {old} is produced inside a macro call",
                )
            )
            continue
        edits.append(
            text_edit(
                text=context.contents,
                start=column_span[1],
                end=column_span[1],
                replacement=f" AS {new}",
                kind=EditKind.COLUMN,
                before="",
                after=f"AS {new}",
            )
        )
    missing: frozenset[str] = frozenset(
        scope for scope in scopes if _scope_role(scope) not in found
    )
    scope: str
    for scope in sorted(missing):
        if _scope_role(scope) in facts.star_outputs:
            manual.append(
                _manual(
                    context=context,
                    offset=None,
                    reason=f"{old} comes from SELECT * in {scope}; list the columns explicitly",
                )
            )
    return BodyEdits(edits=tuple(edits), manual=tuple(manual))


def _scope_role(scope: str) -> str:
    return scope if scope == ROOT_SCOPE else f"{CTE_SCOPE_PREFIX}{scope}"


def _respell(*, authored: str, name: str) -> str:
    if authored and authored[0] in QUOTE_CHARACTERS:
        return f"{authored[0]}{name}{QUOTE_CHARACTERS[authored[0]]}"
    return name


def _site_offset(*, context: BodyContext, site: ColumnSite) -> int | None:
    if site.start is None:
        return None
    return context.locate(site.start)


def _manual(*, context: BodyContext, offset: int | None, reason: str) -> ManualLocation:
    return manual_at(
        path=context.path,
        text=context.contents,
        offset=context.fallback_offset if offset is None else offset,
        reason=reason,
    )
