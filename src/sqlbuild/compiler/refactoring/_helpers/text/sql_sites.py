"""Reference call sites, offset-preserving analysis SQL, and compiled-to-authored offsets."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.compile.main.map_expanded_offset import map_expanded_offset
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSqlExpansion,
    ExpansionSpan,
    MappedOffset,
)
from sqlbuild.compiler.refactoring.constants import (
    EMBEDDED_REF_PATTERN,
    GENERIC_PLACEHOLDER_KIND,
    PLACEHOLDER_BASE,
    PLACEHOLDER_PAD,
    RESOURCE_CALL_PATTERN,
)
from sqlbuild.compiler.refactoring.models import AnalysisSql, ModelBody, ResourceSite
from sqlbuild.lint.main.scan_interpolation_sites import scan_interpolation_sites
from sqlbuild.lint.models import InterpolationSite


def resource_sites(*, text: str, dialect: str) -> tuple[ResourceSite, ...]:
    """Return resource calls outside comments and strings, with their name spans."""

    sites: list[ResourceSite] = []
    site: InterpolationSite
    for site in scan_interpolation_sites(body=text, dialect=dialect):
        match: re.Match[str] | None = RESOURCE_CALL_PATTERN.match(site.original_text)
        if match is None:
            continue
        sites.append(
            ResourceSite(
                kind=match.group("kind"),
                name=match.group("name"),
                start=site.original_start,
                end=site.original_end,
                name_start=site.original_start + match.start("name"),
                name_end=site.original_start + match.end("name"),
            )
        )
    return tuple(sites)


def embedded_ref_spans(*, text: str, name: str) -> tuple[tuple[int, int], ...]:
    """Return the name spans of `__ref` calls to a model inside a quoted string's raw text."""

    return tuple(
        (match.start("name"), match.end("name"))
        for match in EMBEDDED_REF_PATTERN.finditer(text)
        if match.group("name") == name
    )


def analysis_sql(*, text: str, dialect: str) -> AnalysisSql:
    """Replace every interpolation site with an identifier of the same length."""

    pieces: list[str] = []
    tables: dict[tuple[str, str], set[str]] = {}
    copied_to: int = 0
    index: int
    site: InterpolationSite
    for index, site in enumerate(scan_interpolation_sites(body=text, dialect=dialect)):
        match: re.Match[str] | None = RESOURCE_CALL_PATTERN.match(site.original_text)
        kind: str = match.group("kind")[0] if match is not None else GENERIC_PLACEHOLDER_KIND
        placeholder: str = _placeholder(
            kind=kind, index=index, length=site.original_end - site.original_start
        )
        if match is not None:
            tables.setdefault((match.group("kind"), match.group("name")), set()).add(placeholder)
        pieces.extend((text[copied_to : site.original_start], placeholder))
        copied_to = site.original_end
    pieces.append(text[copied_to:])
    return AnalysisSql(
        sql="".join(pieces),
        tables={key: frozenset(value) for key, value in tables.items()},
    )


def model_body(
    *, project: CompiledProject, project_dir: Path, model: CompiledModel, contents: str
) -> ModelBody | None:
    """Return the mappable compiled body of a model, or None when it cannot be mapped."""

    body_start: int = contents.rfind(model.authored_query_sql) if model.authored_query_sql else -1
    if body_start < 0:
        return None
    expansion: CompiledSqlExpansion | None = _expansion(
        project=project, project_dir=project_dir, model=model
    )
    passes: tuple[tuple[ExpansionSpan, ...], ...] = ()
    if expansion is not None:
        if expansion.expanded_sql != model.query_sql:
            return None
        passes = expansion.passes
    elif model.query_sql != model.authored_query_sql:
        return None
    return ModelBody(
        relative_path=model.relative_path.as_posix(),
        contents=contents,
        body_start=body_start,
        compiled_sql=model.query_sql,
        passes=passes,
    )


def authored_offset(*, body: ModelBody, offset: int) -> tuple[int, bool]:
    """Return the file offset of a compiled offset and whether a macro generated it."""

    mapped: MappedOffset = map_expanded_offset(offset=offset, passes=body.passes)
    return body.body_start + mapped.offset, mapped.generated


def authored_span(*, body: ModelBody, start: int, end: int) -> tuple[int, int] | None:
    """Return the file span of compiled text written by the author, or None if generated."""

    mapped_start: int
    start_generated: bool
    mapped_start, start_generated = authored_offset(body=body, offset=start)
    if start_generated:
        return None
    if end <= start:
        return mapped_start, mapped_start
    mapped_last: int
    last_generated: bool
    mapped_last, last_generated = authored_offset(body=body, offset=end - 1)
    if last_generated or mapped_last - mapped_start != end - 1 - start:
        return None
    return mapped_start, mapped_last + 1


def _expansion(
    *, project: CompiledProject, project_dir: Path, model: CompiledModel
) -> CompiledSqlExpansion | None:
    target: Path = (project_dir / model.relative_path).resolve()
    path: Path
    expansion: CompiledSqlExpansion
    for path, expansion in project.sql_expansions.items():
        if path.resolve() == target:
            return expansion
    return None


def _placeholder(*, kind: str, index: int, length: int) -> str:
    base: str = PLACEHOLDER_BASE.format(kind=kind, index=index)
    if len(base) > length:
        return PLACEHOLDER_PAD * (length - 1) + kind
    return base + PLACEHOLDER_PAD * (length - len(base))
