"""Walk a column rename from its owner model through every downstream reader."""

from __future__ import annotations

from collections import deque

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.refactoring._helpers.columns.column_references import (
    analyze_column,
    consumer_edits,
    output_edits,
    resource_columns,
)
from sqlbuild.compiler.refactoring._helpers.project.project_files import (
    authored_bodies,
    project_sql_files,
    python_string_locations,
    yaml_files,
)
from sqlbuild.compiler.refactoring._helpers.renames.model_planning import (
    find_model,
    needs_column_migration,
    validate_identifier,
)
from sqlbuild.compiler.refactoring._helpers.text.header_edits import (
    add_column_entry_edit,
    column_config_edits,
    column_entry_edits,
    consumer_column_header_edits,
    header_tokens,
    unhandled_word_offsets,
)
from sqlbuild.compiler.refactoring._helpers.text.schema_edits import schema_column_edits
from sqlbuild.compiler.refactoring._helpers.text.sql_sites import (
    analysis_sql,
    authored_offset,
    authored_span,
    model_body,
)
from sqlbuild.compiler.refactoring._helpers.text.text_edits import (
    manual_at,
    merge_parts,
    path_edits,
)
from sqlbuild.compiler.refactoring._helpers.text.yaml_edits import yaml_column_edits
from sqlbuild.compiler.refactoring.constants import (
    EXPECTED_FIXTURE_PREFIX,
    FIXTURE_ROLES,
    GENERIC_DIALECT,
    MIGRATE_FROM_KEY,
    REF_FIXTURE_PREFIX,
    REF_KIND,
    ROOT_SCOPE,
)
from sqlbuild.compiler.refactoring.exceptions import RefactorInputError
from sqlbuild.compiler.refactoring.models import (
    AnalysisSql,
    AuthoredBody,
    BodyContext,
    BodyEdits,
    ColumnFacts,
    ColumnQuery,
    ColumnRenameContext,
    HeaderToken,
    ManualLocation,
    MigrationDeclaration,
    ModelBody,
    ProjectSqlFile,
    RefactorParts,
    RefactorProject,
    RefactorRequest,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import SqlFileRole
from sqlbuild.spec.contracts.models import SchemaColumn

type _ModelContext = tuple[BodyContext | None, str, tuple[ManualLocation, ...]]


def column_rename_context(
    *, project: RefactorProject, request: RefactorRequest
) -> ColumnRenameContext:
    """Validate a column rename and collect everything its walk reads."""

    owner: CompiledModel = find_model(project=project.graph.project, name=request.model_name)
    old: str = request.column_name or ""
    new: str = request.new_name
    validate_identifier(name=new, noun="column")
    files: tuple[ProjectSqlFile, ...] = project_sql_files(discovered=project.discovered)
    context: ColumnRenameContext = ColumnRenameContext(
        project=project,
        owner=owner,
        dialect=project.graph.project.sql_analysis_dialect or GENERIC_DIALECT,
        columns=resource_columns(project=project.graph.project),
        contents={item.relative_path: item.contents for item in files},
        bodies=authored_bodies(discovered=project.discovered),
        yaml_files=yaml_files(discovered=project.discovered),
        schema_files=tuple(item for item in files if item.role == SqlFileRole.SCHEMA),
        old=old,
        new=new,
        cascade=request.cascade,
    )
    if old.lower() not in _output_names(context=context):
        raise RefactorInputError(
            f"model:{owner.name} has no output column '{old}'",
            code="C956",
            help="column names match case-insensitively; check the spelling",
        )
    if old.lower() == new.lower():
        raise RefactorInputError(f"column {old} already has that name", code="C953")
    return context


def column_rename_parts(*, context: ColumnRenameContext) -> RefactorParts:
    """Return every edit of the rename; `cascaded` lists each model whose column is renamed."""

    parts: list[RefactorParts] = [_collision(context=context), _owner_output(context=context)]
    queue: deque[CompiledModel] = deque([context.owner])
    seen: set[str] = set()
    while queue:
        model: CompiledModel = queue.popleft()
        if model.name in seen:
            continue
        seen.add(model.name)
        consumers: RefactorParts
        cascaded: tuple[CompiledModel, ...]
        consumers, cascaded = _consumers(context=context, model=model)
        parts.extend(
            (
                RefactorParts(cascaded=(model.name,)),
                _declarations(context=context, model=model),
                consumers,
                _authored_body_parts(context=context, model=model),
                RefactorParts(
                    edits=(
                        *yaml_column_edits(
                            files=context.yaml_files,
                            model=model.name,
                            old=context.old,
                            new=context.new,
                        ),
                        *_schema_edits(context=context, model=model),
                    )
                ),
            )
        )
        queue.extend(cascaded)
    merged: RefactorParts = merge_parts(parts=tuple(parts))
    return merge_parts(parts=(merged, _python_locations(context=context, merged=merged)))


def _schema_edits(
    *, context: ColumnRenameContext, model: CompiledModel
) -> tuple[tuple[str, TextEdit], ...]:
    edits: list[tuple[str, TextEdit]] = []
    item: ProjectSqlFile
    for item in context.schema_files:
        edits.extend(
            path_edits(
                path=item.relative_path,
                edits=schema_column_edits(
                    contents=item.contents,
                    upstream=model.name,
                    old=context.old,
                    new=context.new,
                ),
            )
        )
    return tuple(edits)


def _output_names(*, context: ColumnRenameContext) -> frozenset[str]:
    return frozenset(
        name.lower() for name in context.columns.get((REF_KIND, context.owner.name), ())
    )


def _collision(*, context: ColumnRenameContext) -> RefactorParts:
    if context.new.lower() not in _output_names(context=context):
        return RefactorParts()
    return RefactorParts(
        blocking=(
            ManualLocation(
                path=context.owner.relative_path.as_posix(),
                line=None,
                column=None,
                reason=f"model:{context.owner.name} already has a column named {context.new}",
            ),
        )
    )


def _owner_output(*, context: ColumnRenameContext) -> RefactorParts:
    body: BodyContext | None
    compiled_sql: str
    unmapped: tuple[ManualLocation, ...]
    body, compiled_sql, unmapped = _model_context(context=context, model=context.owner)
    if body is None:
        return RefactorParts(manual=unmapped)
    facts: ColumnFacts = analyze_column(
        analysis=analysis_sql(text=compiled_sql, dialect=context.dialect),
        dialect=context.dialect,
        columns=context.columns,
        query=ColumnQuery(
            column=context.old,
            target_tables=frozenset(),
            output_scopes=frozenset({ROOT_SCOPE}),
        ),
    )
    result: BodyEdits = output_edits(
        facts=facts,
        context=body,
        scopes=frozenset({ROOT_SCOPE}),
        old=context.old,
        new=context.new,
    )
    missing: tuple[ManualLocation, ...] = (
        ()
        if result.edits or result.manual
        else (
            ManualLocation(
                path=body.path,
                line=None,
                column=None,
                reason=f"cannot find where model:{context.owner.name} produces {context.old}",
            ),
        )
    )
    return RefactorParts(
        edits=path_edits(path=body.path, edits=result.edits), manual=(*result.manual, *missing)
    )


def _declarations(*, context: ColumnRenameContext, model: CompiledModel) -> RefactorParts:
    path: str = model.relative_path.as_posix()
    declared: SchemaColumn | None = next(
        (
            column
            for column in (model.schema_entry.columns if model.schema_entry is not None else ())
            if column.name.lower() == context.old.lower()
        ),
        None,
    )
    if declared is not None and declared.migrate_from is not None:
        return RefactorParts(
            blocking=(
                ManualLocation(
                    path=path,
                    line=None,
                    column=None,
                    reason=(
                        f"column {context.old} of model:{model.name} still declares "
                        "migrate_from; build it on every target and remove migrate_from before "
                        "renaming it again"
                    ),
                ),
            )
        )
    shared: tuple[ManualLocation, ...] = (
        (
            ManualLocation(
                path=declared.location.path.as_posix(),
                line=declared.location.line,
                column=declared.location.column,
                reason=(
                    f"column {context.old} of model:{model.name} is declared in a shared schema"
                ),
            ),
        )
        if declared is not None
        and declared.location is not None
        and declared.location.path.as_posix() != path
        else ()
    )
    return merge_parts(
        parts=(RefactorParts(manual=shared), _header_parts(context=context, model=model))
    )


def _header_parts(*, context: ColumnRenameContext, model: CompiledModel) -> RefactorParts:
    path: str = model.relative_path.as_posix()
    contents: str = context.contents.get(path, "")
    tokens: tuple[HeaderToken, ...] = header_tokens(contents=contents) or ()
    migrate: bool = needs_column_migration(model=model)
    entry_edits: tuple[TextEdit, ...] | None = column_entry_edits(
        contents=contents, tokens=tokens, old=context.old, new=context.new, migrate=migrate
    )
    added: TextEdit | None = (
        add_column_entry_edit(contents=contents, tokens=tokens, new=context.new, old=context.old)
        if entry_edits is None and migrate
        else None
    )
    edits: tuple[TextEdit, ...] = (
        *column_config_edits(contents=contents, tokens=tokens, old=context.old, new=context.new),
        *(entry_edits or ()),
        *((added,) if added is not None else ()),
    )
    handled: frozenset[int] = frozenset(edit.start for edit in edits)
    return RefactorParts(
        edits=path_edits(path=path, edits=edits),
        manual=tuple(
            manual_at(
                path=path,
                text=contents,
                offset=offset,
                reason=f"the MODEL header mentions {context.old} here; update it by hand",
            )
            for offset in unhandled_word_offsets(
                contents=contents, tokens=tokens, word=context.old, handled=handled
            )
        ),
        migrations=(
            MigrationDeclaration(
                model_name=model.name,
                declaration=f"{context.new} ({MIGRATE_FROM_KEY} {context.old})",
                reason="keeps the column's history in place",
            ),
        )
        if migrate
        else (),
    )


def _consumers(
    *, context: ColumnRenameContext, model: CompiledModel
) -> tuple[RefactorParts, tuple[CompiledModel, ...]]:
    parts: list[RefactorParts] = []
    cascaded: list[CompiledModel] = []
    consumer: CompiledModel
    for consumer in context.project.graph.project.models:
        if not any(
            dep.resource_type == CompiledResourceType.MODEL and dep.name == model.name
            for dep in consumer.deps
        ):
            continue
        consumer_parts: RefactorParts
        passes_through: bool
        consumer_parts, passes_through = _consumer(
            context=context, upstream=model, consumer=consumer
        )
        parts.append(consumer_parts)
        if passes_through:
            cascaded.append(consumer)
    return merge_parts(parts=tuple(parts)), tuple(cascaded)


def _consumer(
    *, context: ColumnRenameContext, upstream: CompiledModel, consumer: CompiledModel
) -> tuple[RefactorParts, bool]:
    body: BodyContext | None
    compiled_sql: str
    unmapped: tuple[ManualLocation, ...]
    body, compiled_sql, unmapped = _model_context(context=context, model=consumer)
    if body is None:
        return RefactorParts(manual=unmapped), False
    analysis: AnalysisSql = analysis_sql(text=compiled_sql, dialect=context.dialect)
    facts: ColumnFacts = analyze_column(
        analysis=analysis,
        dialect=context.dialect,
        columns=context.columns,
        query=ColumnQuery(
            column=context.old,
            target_tables=analysis.tables.get((REF_KIND, upstream.name), frozenset()),
        ),
    )
    result: BodyEdits = consumer_edits(
        facts=facts,
        context=body,
        old=context.old,
        new=context.new,
        cascade_root=context.cascade,
        root_stars_pass=context.cascade,
    )
    header: tuple[TextEdit, ...] = consumer_column_header_edits(
        contents=body.contents, upstream=upstream.name, old=context.old, new=context.new
    )
    return (
        RefactorParts(
            edits=path_edits(path=body.path, edits=(*result.edits, *header)),
            manual=result.manual,
        ),
        result.passes_through,
    )


def _authored_body_parts(*, context: ColumnRenameContext, model: CompiledModel) -> RefactorParts:
    return merge_parts(
        parts=tuple(
            _authored_body(context=context, model=model, body=body)
            for body in context.bodies
            if model.name.lower() in body.text.lower()
        )
    )


def _authored_body(
    *, context: ColumnRenameContext, model: CompiledModel, body: AuthoredBody
) -> RefactorParts:
    lowered: str = body.text.lower()
    analysis: AnalysisSql = analysis_sql(text=body.text, dialect=context.dialect)
    targets: frozenset[str] = analysis.tables.get((REF_KIND, model.name), frozenset())
    fixture_scopes: frozenset[str] = (
        frozenset(
            name
            for name in (
                f"{EXPECTED_FIXTURE_PREFIX}{model.name}",
                f"{REF_FIXTURE_PREFIX}{model.name}",
            )
            if name.lower() in lowered
        )
        if body.role in FIXTURE_ROLES
        else frozenset()
    )
    if not targets and not fixture_scopes:
        return RefactorParts()
    facts: ColumnFacts = analyze_column(
        analysis=analysis,
        dialect=context.dialect,
        columns=context.columns,
        query=ColumnQuery(
            column=context.old,
            target_tables=targets,
            target_ctes=frozenset(
                name for name in fixture_scopes if name.startswith(REF_FIXTURE_PREFIX)
            ),
            output_scopes=fixture_scopes,
        ),
    )
    located: BodyContext = BodyContext(
        path=body.path,
        contents=body.contents,
        map_span=lambda start, end: (body.start + start, body.start + end),
        locate=lambda offset: body.start + offset,
        fallback_offset=body.start,
    )
    outputs: BodyEdits = output_edits(
        facts=facts, context=located, scopes=fixture_scopes, old=context.old, new=context.new
    )
    consumers: BodyEdits = consumer_edits(
        facts=facts,
        context=located,
        old=context.old,
        new=context.new,
        cascade_root=False,
        root_stars_pass=True,
    )
    return RefactorParts(
        edits=path_edits(path=body.path, edits=(*outputs.edits, *consumers.edits)),
        manual=(*outputs.manual, *consumers.manual),
    )


def _python_locations(*, context: ColumnRenameContext, merged: RefactorParts) -> RefactorParts:
    edited: frozenset[str] = frozenset(path for path, _ in merged.edits)
    return RefactorParts(
        manual=tuple(
            location
            for location in python_string_locations(
                project_dir=context.project.project_dir,
                discovered=context.project.discovered,
                names=(context.old,),
                reason=(
                    f"Python SQL may read column {context.old} of {context.owner.name}; check it "
                    "by hand"
                ),
                context=context.owner.name,
            )
            if location.path not in edited
        )
    )


def _model_context(*, context: ColumnRenameContext, model: CompiledModel) -> _ModelContext:
    path: str = model.relative_path.as_posix()
    contents: str | None = context.contents.get(path)
    if contents is None:
        return None, "", ()
    body: ModelBody | None = model_body(
        project=context.project.graph.project,
        project_dir=context.project.project_dir,
        model=model,
        contents=contents,
    )
    if body is None:
        return (
            None,
            "",
            (
                ManualLocation(
                    path=path,
                    line=None,
                    column=None,
                    reason="the compiled SQL of this model cannot be mapped back to the file",
                ),
            ),
        )
    mapped: ModelBody = body
    return (
        BodyContext(
            path=path,
            contents=contents,
            map_span=lambda start, end: authored_span(body=mapped, start=start, end=end),
            locate=lambda offset: authored_offset(body=mapped, offset=offset)[0],
            fallback_offset=body.body_start,
        ),
        body.compiled_sql,
        (),
    )
