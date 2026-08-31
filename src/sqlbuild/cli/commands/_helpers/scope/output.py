"""Deterministic, value-safe text presentation for compiler scope results."""

from __future__ import annotations

from pathlib import PurePosixPath
from shlex import quote

from sqlbuild.cli.commands.constants import (
    SCOPE_DEFAULT_PAGE_SIZE,
    SCOPE_GLOBAL_ALL,
    SCOPE_GLOBAL_SUMMARY,
    SCOPE_PATH_COMPACT,
    SCOPE_PATH_NONE,
    SCOPE_PATH_RELATIVE,
)
from sqlbuild.cli.commands.models import ScopeCommandRequest
from sqlbuild.compiler.scopes.models import (
    DeclarationReport,
    MovePreview,
    ScopeBrowseResult,
    ScopeDiagnostic,
    ScopeListResult,
    ScopeReport,
    ScopeResourceReport,
    ScopeSection,
    SourceLocation,
)


def render_scope_result(
    *, result: ScopeReport | ScopeBrowseResult | ScopeListResult, request: ScopeCommandRequest
) -> str:
    """Render one compiler-owned scope result without deriving scope facts."""

    if isinstance(result, ScopeBrowseResult):
        return _render_browse(result=result, request=request)
    if isinstance(result, ScopeListResult):
        return _render_list(result=result, request=request)
    return _render_report(report=result, request=request)


def _render_report(*, report: ScopeReport, request: ScopeCommandRequest) -> str:
    resource: ScopeResourceReport = report.resource
    lines: list[str] = ["Scope", f"  Target: {resource.target}"]
    if resource.identity is not None:
        lines.append(f"  Resource: {resource.identity}")
    if resource.path is not None:
        lines.append(f"  Path: {_path(value=resource.path, mode=request.paths)}")
    labels: list[str] = []
    if resource.prospective:
        labels.append("prospective")
    if resource.directory:
        labels.append("directory")
    if resource.duplicate_count:
        labels.append(f"{resource.duplicate_count} matches")
    if labels:
        lines.append(f"  Status: {', '.join(labels)}")
    lines.extend(["", f"Used ({len(report.used)})"])
    lines.extend(
        _declaration_lines(
            declarations=report.used,
            request=request,
            used=frozenset(item.identity for item in report.used),
        )
    )
    lines.extend(["", "Scope chain"])
    if report.scope_chain:
        for index, entry in enumerate(report.scope_chain):
            connector: str = "└─" if index == len(report.scope_chain) - 1 else "├─"
            lines.append(
                f"  {connector} {_scope_label(entry.kind)} "
                f"{_path(value=entry.path, mode=request.paths)} "
                f"({entry.declaration_count})"
            )
    else:
        lines.append("  (none)")
    used: frozenset[str] = frozenset(item.identity for item in report.used)
    for title, declarations, section in (
        ("Available", report.available, _section(report=report, name="available")),
        (
            "Relationship grants",
            report.relationship_scope,
            _section(report=report, name="relationship_scope"),
        ),
        (
            "Nearby unavailable",
            report.nearby_unavailable,
            _section(report=report, name="nearby_unavailable"),
        ),
    ):
        lines.extend(["", _section_title(title=title, section=section, count=len(declarations))])
        lines.extend(_declaration_lines(declarations=declarations, request=request, used=used))
        if section is not None and section.collapsed_count:
            lines.append(
                f"  … {section.collapsed_count} globals collapsed; run "
                f"{_follow_up(request=request, globals_all=True)}"
            )
    if report.explanation is not None:
        lines.extend(["", "Explanation"])
        if report.explanation.declaration is None:
            lines.append("  (declaration not resolved)")
        else:
            lines.extend(
                _explanation_lines(
                    declaration=report.explanation.declaration,
                    request=request,
                    used=used,
                )
            )
    if report.move_preview is not None:
        lines.extend(["", *_move_lines(move=report.move_preview, request=request, used=used)])
    lines.extend(["", *_diagnostic_lines(report.diagnostics), _completeness_line(report.complete)])
    return "\n".join(lines) + "\n"


def _render_browse(*, result: ScopeBrowseResult, request: ScopeCommandRequest) -> str:
    lines: list[str] = [
        "Scope folders",
        f"  Path: {_path(value=result.folder, mode=request.paths)}",
        "",
    ]
    if not result.folders:
        lines.append("  (none)")
    for index, folder in enumerate(result.folders):
        connector: str = "└─" if index == len(result.folders) - 1 else "├─"
        kinds: str = (
            ", ".join(f"{kind} {count}" for kind, count in folder.kind_counts) or "no declarations"
        )
        lines.append(
            f"  {connector} {folder.name}/  {folder.descendant_count} declarations, "
            f"{folder.used_count} used, {folder.child_count} children; {kinds}"
        )
        lines.append(f"     {_follow_up(request=request, browse=folder.path)}")
        lines.append(f"     {_follow_up(request=request, list_path=folder.path)}")
    lines.extend(["", *_diagnostic_lines(result.diagnostics), _completeness_line(result.complete)])
    return "\n".join(lines) + "\n"


def _render_list(*, result: ScopeListResult, request: ScopeCommandRequest) -> str:
    section: ScopeSection = result.section
    lines: list[str] = [
        "Scope declarations",
        f"  Path: {_path(value=result.folder, mode=request.paths)}",
        f"  Showing: {section.returned} of {section.total}",
        "",
    ]
    lines.extend(
        _declaration_lines(declarations=result.declarations, request=request, used=frozenset())
    )
    if section.next_cursor is not None:
        lines.extend(
            [
                "",
                "Continue: "
                + _follow_up(
                    request=request,
                    list_path=result.folder,
                    after=section.next_cursor,
                ),
            ]
        )
    lines.extend(["", *_diagnostic_lines(result.diagnostics), _completeness_line(section.complete)])
    return "\n".join(lines) + "\n"


def _declaration_lines(
    *,
    declarations: tuple[DeclarationReport, ...],
    request: ScopeCommandRequest,
    used: frozenset[str],
) -> list[str]:
    if not declarations:
        return ["  (none)"]
    lines: list[str] = []
    for index, declaration in enumerate(declarations):
        connector: str = "└─" if index == len(declarations) - 1 else "├─"
        marker: str = "●" if declaration.identity in used else "○"
        details: list[str] = [declaration.kind, _scope_label(declaration.scope)]
        if declaration.visibility is not None:
            provenance: str = declaration.visibility.reason
            if declaration.visibility.through is not None:
                provenance += f" through {declaration.visibility.through}"
            details.append(provenance)
        if declaration.inaccessible_reason is not None:
            details.append(declaration.inaccessible_reason)
        details.extend(_metadata_parts(declaration))
        line = f"  {connector} {marker} {declaration.identity}  [{'; '.join(details)}]"
        if request.paths != SCOPE_PATH_NONE:
            location: SourceLocation = declaration.definition
            line += (
                f"  {_path(value=location.path, mode=request.paths)}:"
                f"{location.line}:{location.column}"
            )
        lines.append(line)
    return lines


def _scope_label(scope: str) -> str:
    return {
        "global": "project",
        "inherited": "descendant-public",
        "local": "exact-owner-private",
        "private": "model-private",
    }.get(scope, scope)


def _metadata_parts(declaration: DeclarationReport) -> list[str]:
    metadata: dict[str, object] = dict(declaration.metadata)
    parts: list[str] = []
    parameters: object = metadata.get("parameters")
    if isinstance(parameters, tuple | list):
        parts.append(f"params {len(parameters)}")
    members: object = metadata.get("member_count")
    if isinstance(members, int):
        parts.append(f"members {members}")
    scalar_type: object = metadata.get("scalar_type")
    if isinstance(scalar_type, str):
        parts.append(f"type {scalar_type}")
    logical_type: object = metadata.get("logical_type")
    if isinstance(logical_type, str):
        parts.append(f"type {logical_type}")
    collection: object = metadata.get("collection_kind")
    if isinstance(collection, str):
        item_count: object = metadata.get("item_count")
        parts.append(f"{collection} {item_count}" if isinstance(item_count, int) else collection)
    role_root: object = metadata.get("role_root")
    if isinstance(role_root, str):
        parts.append(f"role {role_root}")
    bucket_path: object = metadata.get("bucket_path")
    if isinstance(bucket_path, str):
        parts.append(f"bucket {bucket_path} (navigation only)")
    return parts


def _explanation_lines(
    *, declaration: DeclarationReport, request: ScopeCommandRequest, used: frozenset[str]
) -> list[str]:
    lines: list[str] = _declaration_lines(declarations=(declaration,), request=request, used=used)
    required_scope: str | None = (
        _scope_label(declaration.required_scope)
        if declaration.required_scope is not None
        else None
    )
    facts: tuple[tuple[str, object], ...] = (
        ("Owner", declaration.owner),
        ("Owning path", declaration.owning_path),
        ("Consumers", declaration.consumers),
        ("Dependencies", declaration.dependencies),
        ("Grants", declaration.grants),
        ("Required scope", required_scope),
        ("Required path", declaration.required_path),
        ("Promotion impact", declaration.promotion_impact),
    )
    for label, value in facts:
        if isinstance(value, tuple):
            rendered: str = ", ".join(value) if value else "(none)"
        else:
            rendered = str(value) if value is not None else "(none)"
        lines.append(f"     {label}: {rendered}")
    return lines


def _move_lines(
    *, move: MovePreview, request: ScopeCommandRequest, used: frozenset[str]
) -> list[str]:
    lines: list[str] = [
        "Move preview",
        f"  Resource: {move.resource}",
        f"  Destination: {_path(value=move.destination, mode=request.paths)}",
        f"  Ownership root: {_path(value=move.new_ownership_root, mode=request.paths)}",
    ]
    for title, values in (
        ("Retained", move.retained),
        ("Gained", move.gained),
        ("Lost", move.lost),
        ("Private retained", move.private_retained),
        ("Relationship retained", move.relationship_retained),
    ):
        lines.append(f"  {title} ({len(values)})")
        lines.extend(
            "  " + line
            for line in _declaration_lines(declarations=values, request=request, used=used)
        )
    lines.append(f"  Invalidated usages ({len(move.invalidated_usages)})")
    lines.extend(f"    - {identity}" for identity in move.invalidated_usages)
    if not move.invalidated_usages:
        lines.append("    (none)")
    return lines


def _diagnostic_lines(diagnostics: tuple[ScopeDiagnostic, ...]) -> list[str]:
    lines: list[str] = [f"Diagnostics ({len(diagnostics)})"]
    if not diagnostics:
        lines.append("  (none)")
    for diagnostic in diagnostics:
        location: str = f" {diagnostic.path}" if diagnostic.path is not None else ""
        lines.append(
            f"  {diagnostic.severity.value.upper()} {diagnostic.code.value}{location}: "
            f"{diagnostic.message}"
        )
    return lines


def _section(*, report: ScopeReport, name: str) -> ScopeSection | None:
    return next((section for section in report.sections if section.name == name), None)


def _section_title(*, title: str, section: ScopeSection | None, count: int) -> str:
    if section is None:
        return f"{title} ({count})"
    suffix: str = f", {section.collapsed_count} collapsed" if section.collapsed_count else ""
    return f"{title} ({section.returned} of {section.total}{suffix})"


def _completeness_line(complete: bool) -> str:
    return f"Completeness: {'complete' if complete else 'partial'}"


def _path(*, value: str | None, mode: str) -> str:
    if value is None:
        return "(none)"
    if mode == SCOPE_PATH_NONE:
        return "(hidden)"
    if mode == SCOPE_PATH_COMPACT:
        return PurePosixPath(value).name
    return value


def _follow_up(
    *,
    request: ScopeCommandRequest,
    browse: str | None = None,
    list_path: str | None = None,
    after: str | None = None,
    globals_all: bool = False,
) -> str:
    args: list[str] = ["sqb", "scope"]
    if request.target is not None:
        args.append(request.target)
    else:
        args.extend(("--at", request.at or ""))
    if browse is not None:
        args.extend(("--browse", browse))
    if list_path is not None:
        args.extend(("--list", list_path))
    if request.defined_under is not None:
        args.extend(("--defined-under", request.defined_under))
    for kind in request.kinds:
        args.extend(("--kind", kind))
    if request.match is not None:
        args.extend(("--match", request.match))
    if request.used_only:
        args.append("--used-only")
    if globals_all:
        if request.as_path is not None:
            args.extend(("--as-path", request.as_path))
        if request.include_nearby:
            args.append("--include-nearby")
        if request.nearby_depth != 1:
            args.extend(("--nearby-depth", str(request.nearby_depth)))
        if request.dependency_depth:
            args.extend(("--dependency-depth", str(request.dependency_depth)))
        if request.explain is not None:
            args.extend(("--explain", request.explain))
    if request.page_size != SCOPE_DEFAULT_PAGE_SIZE:
        args.extend(("--page-size", str(request.page_size)))
    if after is not None:
        args.extend(("--after", after))
    if globals_all:
        args.extend(("--globals", SCOPE_GLOBAL_ALL))
    elif request.globals != SCOPE_GLOBAL_SUMMARY:
        args.extend(("--globals", request.globals))
    if request.paths != SCOPE_PATH_RELATIVE:
        args.extend(("--paths", request.paths))
    if request.no_cache:
        args.append("--no-cache")
    return " ".join(quote(item) for item in args)
