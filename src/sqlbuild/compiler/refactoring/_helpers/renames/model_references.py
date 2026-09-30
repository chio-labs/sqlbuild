"""Every authored reference to a model by name, and the ones a rename cannot rewrite."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.refactoring._helpers.text.header_edits import model_name_header_edits
from sqlbuild.compiler.refactoring._helpers.text.schema_edits import schema_model_name_edits
from sqlbuild.compiler.refactoring._helpers.text.sql_sites import (
    authored_offset,
    model_body,
    resource_sites,
)
from sqlbuild.compiler.refactoring._helpers.text.text_edits import (
    identifier_sites,
    manual_at,
    path_edits,
    text_edit,
)
from sqlbuild.compiler.refactoring.constants import (
    EXPECTED_FIXTURE_PREFIX,
    FIXTURE_ROLES,
    REF_FIXTURE_PREFIX,
    REF_KIND,
)
from sqlbuild.compiler.refactoring.models import (
    ManualLocation,
    ModelBody,
    ProjectSqlFile,
    RefactorProject,
    ResourceSite,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import EditKind, SqlFileRole


def model_reference_edits(
    *, files: tuple[ProjectSqlFile, ...], old: str, new: str, dialect: str
) -> tuple[tuple[str, TextEdit], ...]:
    """Rewrite `__ref`, fixture CTE names, and header references to a renamed model."""

    edits: list[tuple[str, TextEdit]] = []
    item: ProjectSqlFile
    for item in files:
        edits.extend(
            path_edits(
                path=item.relative_path,
                edits=_ref_edits(item=item, old=old, new=new, dialect=dialect),
            )
        )
        if item.role in FIXTURE_ROLES:
            edits.extend(
                path_edits(
                    path=item.relative_path, edits=_fixture_edits(item=item, old=old, new=new)
                )
            )
        if item.role == SqlFileRole.MODEL:
            edits.extend(
                path_edits(
                    path=item.relative_path,
                    edits=model_name_header_edits(contents=item.contents, old=old, new=new),
                )
            )
        if item.role == SqlFileRole.SCHEMA:
            edits.extend(
                path_edits(
                    path=item.relative_path,
                    edits=schema_model_name_edits(contents=item.contents, old=old, new=new),
                )
            )
    return tuple(edits)


def macro_reference_locations(
    *, project: RefactorProject, files: tuple[ProjectSqlFile, ...], old: str, dialect: str
) -> tuple[ManualLocation, ...]:
    """Locate `__ref` calls to the model that macros produce, which no edit can reach."""

    compiled: CompiledProject = project.graph.project
    contents: dict[str, str] = {item.relative_path: item.contents for item in files}
    locations: list[ManualLocation] = []
    model: CompiledModel
    for model in compiled.models:
        text: str | None = contents.get(model.relative_path.as_posix())
        if text is None or not _depends_on(model=model, name=old):
            continue
        locations.extend(
            _generated_references(
                compiled=compiled, project=project, model=model, text=text, old=old, dialect=dialect
            )
        )
    return tuple(locations)


def _ref_edits(*, item: ProjectSqlFile, old: str, new: str, dialect: str) -> tuple[TextEdit, ...]:
    return tuple(
        text_edit(
            text=item.contents,
            start=site.name_start,
            end=site.name_end,
            replacement=new,
            kind=EditKind.REFERENCE,
            before=item.contents[site.start : site.end],
            after=(
                item.contents[site.start : site.name_start]
                + new
                + item.contents[site.name_end : site.end]
            ),
        )
        for site in _ref_sites(text=item.contents, name=old, dialect=dialect)
    )


def _fixture_edits(*, item: ProjectSqlFile, old: str, new: str) -> tuple[TextEdit, ...]:
    fixture_names: dict[str, str] = {
        f"{REF_FIXTURE_PREFIX}{old}": f"{REF_FIXTURE_PREFIX}{new}",
        f"{EXPECTED_FIXTURE_PREFIX}{old}": f"{EXPECTED_FIXTURE_PREFIX}{new}",
    }
    return tuple(
        text_edit(
            text=item.contents,
            start=start,
            end=end,
            replacement=fixture_names[name],
            kind=EditKind.FIXTURE,
        )
        for start, end, name in identifier_sites(text=item.contents, names=frozenset(fixture_names))
    )


def _generated_references(
    *,
    compiled: CompiledProject,
    project: RefactorProject,
    model: CompiledModel,
    text: str,
    old: str,
    dialect: str,
) -> tuple[ManualLocation, ...]:
    relative: str = model.relative_path.as_posix()
    compiled_sites: tuple[ResourceSite, ...] = _ref_sites(
        text=model.query_sql, name=old, dialect=dialect
    )
    authored_sites: tuple[ResourceSite, ...] = _ref_sites(
        text=model.authored_query_sql, name=old, dialect=dialect
    )
    if len(compiled_sites) <= len(authored_sites):
        return ()
    body: ModelBody | None = model_body(
        project=compiled, project_dir=project.project_dir, model=model, contents=text
    )
    if body is None:
        return (
            manual_at(
                path=relative,
                text=text,
                offset=None,
                reason=f"reference to {old} produced by a macro",
            ),
        )
    offsets: tuple[tuple[int, bool], ...] = tuple(
        authored_offset(body=body, offset=site.start) for site in compiled_sites
    )
    return tuple(
        manual_at(
            path=relative,
            text=text,
            offset=offset,
            reason=f"reference to {old} produced by a macro; pass the model to the macro as an "
            "argument",
        )
        for offset, generated in offsets
        if generated
    )


def _ref_sites(*, text: str, name: str, dialect: str) -> tuple[ResourceSite, ...]:
    return tuple(
        site
        for site in resource_sites(text=text, dialect=dialect)
        if site.kind == REF_KIND and site.name == name
    )


def _depends_on(*, model: CompiledModel, name: str) -> bool:
    return any(
        dep.resource_type == CompiledResourceType.MODEL and dep.name == name for dep in model.deps
    )
