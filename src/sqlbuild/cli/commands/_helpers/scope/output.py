"""Deterministic, value-safe text presentation for compiler scope results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
from sqlbuild.compiler.scopes.types import DiagnosticSeverity
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.count_noun import format_count_noun

_USED_MARKER: str = "●"
_UNUSED_MARKER: str = "○"
_LEGEND_MARKERS: str = (
    f"{_USED_MARKER} used by this resource   {_UNUSED_MARKER} available but unused"
)
_LEGEND_VERBOSE_HINT: str = "--verbose for scope details"


@dataclass(frozen=True)
class _ScopeText:
    """Styling and detail options shared by one scope text rendering."""

    request: ScopeCommandRequest
    style: CliStyle

    @property
    def verbose(self) -> bool:
        return self.request.verbose


def render_scope_result(
    *,
    result: ScopeReport | ScopeBrowseResult | ScopeListResult,
    request: ScopeCommandRequest,
    use_color: bool = False,
) -> str:
    """Render one compiler-owned scope result without deriving scope facts."""

    text: _ScopeText = _ScopeText(request=request, style=CliStyle(use_color=use_color))
    if isinstance(result, ScopeBrowseResult):
        return _render_browse(result=result, text=text)
    if isinstance(result, ScopeListResult):
        return _render_list(result=result, text=text)
    return _render_report(report=result, text=text)


def _render_report(*, report: ScopeReport, text: _ScopeText) -> str:
    request: ScopeCommandRequest = text.request
    style: CliStyle = text.style
    resource: ScopeResourceReport = report.resource
    lines: list[str] = [
        style.section("Scope"),
        _field(label="Target", value=resource.target, text=text),
    ]
    if resource.identity is not None:
        lines.append(_field(label="Resource", value=resource.identity, text=text))
    if resource.path is not None:
        lines.append(
            _field(label="Path", value=_path(value=resource.path, mode=request.paths), text=text)
        )
    labels: list[str] = []
    if resource.prospective:
        labels.append("prospective")
    if resource.directory:
        labels.append("directory")
    if resource.duplicate_count:
        labels.append(
            format_count_noun(count=resource.duplicate_count, singular="match", plural="matches")
        )
    if labels:
        lines.append(_field(label="Status", value=", ".join(labels), text=text))
    used: frozenset[str] = frozenset(item.identity for item in report.used)
    lines.extend(["", _header(title="Used", count=f"({len(report.used)})", text=text)])
    lines.extend(_declaration_lines(declarations=report.used, text=text, used=used))
    lines.extend(["", style.section("Scope chain")])
    if report.scope_chain:
        for index, entry in enumerate(report.scope_chain):
            chain_path: str = _path(value=entry.path, mode=request.paths)
            lines.append(
                f"  {_connector(last=index == len(report.scope_chain) - 1, text=text)} "
                f"{_scope_label(entry.kind)} "
                f"{style.muted(f'{chain_path} ({entry.declaration_count})')}"
            )
    else:
        lines.append(f"  {style.muted('(none)')}")
    for title, declarations, section, optional in (
        ("Available", report.available, _section(report=report, name="available"), False),
        (
            "Relationship grants",
            report.relationship_scope,
            _section(report=report, name="relationship_scope"),
            True,
        ),
        (
            "Nearby unavailable",
            report.nearby_unavailable,
            _section(report=report, name="nearby_unavailable"),
            True,
        ),
    ):
        collapsed_count: int = section.collapsed_count if section is not None else 0
        if optional and not text.verbose and not declarations and not collapsed_count:
            continue
        lines.extend(
            [
                "",
                _header(
                    title=title,
                    count=_section_count(section=section, count=len(declarations)),
                    text=text,
                ),
            ]
        )
        lines.extend(_declaration_lines(declarations=declarations, text=text, used=used))
        if collapsed_count:
            global_count: str = format_count_noun(count=collapsed_count, singular="global")
            lines.append(
                "  "
                + style.muted(
                    f"… {global_count} collapsed; run "
                    f"{_follow_up(request=request, globals_all=True)}"
                )
            )
    if report.explanation is not None:
        lines.extend(["", style.section("Explanation")])
        if report.explanation.declaration is None:
            lines.append(f"  {style.muted('(declaration not resolved)')}")
        else:
            lines.extend(
                _explanation_lines(declaration=report.explanation.declaration, text=text, used=used)
            )
    if report.move_preview is not None:
        lines.extend(["", *_move_lines(move=report.move_preview, text=text, used=used)])
    if not text.verbose:
        lines.extend(["", style.muted(f"{_LEGEND_MARKERS}   {_LEGEND_VERBOSE_HINT}")])
    lines.extend(
        [
            "",
            *_diagnostic_lines(diagnostics=report.diagnostics, text=text),
            _completeness_line(complete=report.complete, text=text),
        ]
    )
    return "\n".join(lines) + "\n"


def _render_browse(*, result: ScopeBrowseResult, text: _ScopeText) -> str:
    request: ScopeCommandRequest = text.request
    style: CliStyle = text.style
    lines: list[str] = [
        style.section("Scope folders"),
        _field(label="Path", value=_path(value=result.folder, mode=request.paths), text=text),
        "",
    ]
    if not result.folders:
        lines.append(f"  {style.muted('(none)')}")
    for index, folder in enumerate(result.folders):
        kinds: str = (
            ", ".join(f"{kind} {count}" for kind, count in folder.kind_counts) or "no declarations"
        )
        counts: str = (
            f"{format_count_noun(count=folder.descendant_count, singular='declaration')}, "
            f"{folder.used_count} used, "
            f"{format_count_noun(count=folder.child_count, singular='child', plural='children')}; "
            f"{kinds}"
        )
        lines.append(
            f"  {_connector(last=index == len(result.folders) - 1, text=text)} "
            f"{folder.name}/  {style.muted(counts)}"
        )
        lines.append(f"     {style.muted(_follow_up(request=request, browse=folder.path))}")
        lines.append(f"     {style.muted(_follow_up(request=request, list_path=folder.path))}")
    lines.extend(
        [
            "",
            *_diagnostic_lines(diagnostics=result.diagnostics, text=text),
            _completeness_line(complete=result.complete, text=text),
        ]
    )
    return "\n".join(lines) + "\n"


def _render_list(*, result: ScopeListResult, text: _ScopeText) -> str:
    request: ScopeCommandRequest = text.request
    style: CliStyle = text.style
    section: ScopeSection = result.section
    lines: list[str] = [
        style.section("Scope declarations"),
        _field(label="Path", value=_path(value=result.folder, mode=request.paths), text=text),
        _field(label="Showing", value=f"{section.returned} of {section.total}", text=text),
        "",
    ]
    lines.extend(_declaration_lines(declarations=result.declarations, text=text, used=frozenset()))
    if section.next_cursor is not None:
        lines.extend(
            [
                "",
                style.muted("Continue:")
                + " "
                + _follow_up(
                    request=request,
                    list_path=result.folder,
                    after=section.next_cursor,
                ),
            ]
        )
    if not text.verbose and result.declarations:
        lines.extend(["", style.muted(_LEGEND_VERBOSE_HINT)])
    lines.extend(
        [
            "",
            *_diagnostic_lines(diagnostics=result.diagnostics, text=text),
            _completeness_line(complete=section.complete, text=text),
        ]
    )
    return "\n".join(lines) + "\n"


def _declaration_lines(
    *,
    declarations: tuple[DeclarationReport, ...],
    text: _ScopeText,
    used: frozenset[str],
    used_marker_style: Callable[[str], str] | None = None,
    name_style: Callable[[str], str] | None = None,
    detailed: bool | None = None,
) -> list[str]:
    style: CliStyle = text.style
    if not declarations:
        return [f"  {style.muted('(none)')}"]
    show_details: bool = text.verbose if detailed is None else detailed
    resolved_used_marker_style: Callable[[str], str] = used_marker_style or style.success
    resolved_name_style: Callable[[str], str] = name_style or style.object_name
    lines: list[str] = []
    for index, declaration in enumerate(declarations):
        marker: str = (
            resolved_used_marker_style(_USED_MARKER)
            if declaration.identity in used
            else style.muted(_UNUSED_MARKER)
        )
        line: str = (
            f"  {_connector(last=index == len(declarations) - 1, text=text)} {marker} "
            f"{resolved_name_style(declaration.identity)}"
        )
        if show_details:
            line += f"  {style.muted(f'[{"; ".join(_declaration_details(declaration))}]')}"
        if text.request.paths != SCOPE_PATH_NONE:
            location: SourceLocation = declaration.definition
            position: str = (
                f"{location.line}:{location.column}" if show_details else f"{location.line}"
            )
            line += "  " + style.muted(
                f"{_path(value=location.path, mode=text.request.paths)}:{position}"
            )
        lines.append(line)
    return lines


def _declaration_details(declaration: DeclarationReport) -> list[str]:
    details: list[str] = [declaration.kind, _scope_label(declaration.scope)]
    if declaration.visibility is not None:
        provenance: str = declaration.visibility.reason
        if declaration.visibility.through is not None:
            provenance += f" through {declaration.visibility.through}"
        details.append(provenance)
    if declaration.inaccessible_reason is not None:
        details.append(declaration.inaccessible_reason)
    details.extend(_metadata_parts(declaration))
    return details


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
    *, declaration: DeclarationReport, text: _ScopeText, used: frozenset[str]
) -> list[str]:
    style: CliStyle = text.style
    lines: list[str] = _declaration_lines(
        declarations=(declaration,), text=text, used=used, detailed=True
    )
    required_scope: str | None = (
        _scope_label(declaration.required_scope) if declaration.required_scope is not None else None
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
        rendered: str
        if isinstance(value, tuple):
            rendered = ", ".join(value) if value else style.muted("(none)")
        else:
            rendered = str(value) if value is not None else style.muted("(none)")
        lines.append(f"     {style.muted(f'{label}:')} {rendered}")
    return lines


def _move_lines(*, move: MovePreview, text: _ScopeText, used: frozenset[str]) -> list[str]:
    request: ScopeCommandRequest = text.request
    style: CliStyle = text.style
    lines: list[str] = [
        style.section("Move preview"),
        _field(label="Resource", value=move.resource, text=text),
        _field(
            label="Destination", value=_path(value=move.destination, mode=request.paths), text=text
        ),
        _field(
            label="Ownership root",
            value=_path(value=move.new_ownership_root, mode=request.paths),
            text=text,
        ),
    ]
    lost_warning: bool = bool(move.lost)
    sections: tuple[
        tuple[
            str,
            tuple[DeclarationReport, ...],
            bool,
            Callable[[str], str] | None,
            Callable[[str], str] | None,
            Callable[[str], str] | None,
        ],
        ...,
    ] = (
        ("Retained", move.retained, False, None, None, None),
        ("Gained", move.gained, False, None, None, style.success),
        (
            "Lost",
            move.lost,
            False,
            style.warning_strong if lost_warning else None,
            style.error,
            None,
        ),
        ("Private retained", move.private_retained, True, None, None, None),
        ("Relationship retained", move.relationship_retained, True, None, None, None),
    )
    for title, values, optional, title_style, used_marker_style, name_style in sections:
        if optional and not text.verbose and not values:
            continue
        header: str = _header(
            title=title,
            count=f"({len(values)})",
            text=text,
            title_style=title_style,
            count_style=style.warning if title_style is not None else None,
        )
        lines.append(f"  {header}")
        lines.extend(
            "  " + line
            for line in _declaration_lines(
                declarations=values,
                text=text,
                used=used,
                used_marker_style=used_marker_style,
                name_style=name_style,
            )
        )
    invalidated: tuple[str, ...] = move.invalidated_usages
    invalidated_header: str = _header(
        title="Invalidated usages",
        count=f"({len(invalidated)})",
        text=text,
        title_style=style.error_strong if invalidated else None,
        count_style=style.error if invalidated else None,
    )
    lines.append(f"  {invalidated_header}")
    lines.extend(f"    {style.error(f'- {identity}')}" for identity in invalidated)
    if not invalidated:
        lines.append(f"    {style.muted('(none)')}")
    return lines


def _diagnostic_lines(*, diagnostics: tuple[ScopeDiagnostic, ...], text: _ScopeText) -> list[str]:
    style: CliStyle = text.style
    if not diagnostics and not text.verbose:
        return []
    lines: list[str] = [
        _header(
            title="Diagnostics",
            count=f"({len(diagnostics)})",
            text=text,
            title_style=style.error_strong if diagnostics else None,
            count_style=style.error if diagnostics else None,
        )
    ]
    if not diagnostics:
        lines.append(f"  {style.muted('(none)')}")
    for diagnostic in diagnostics:
        severity: str = diagnostic.severity.value.upper()
        severity_text: str = (
            style.error_strong(severity)
            if diagnostic.severity is DiagnosticSeverity.ERROR
            else style.warning_strong(severity)
        )
        location: str = f" {style.muted(diagnostic.path)}" if diagnostic.path is not None else ""
        lines.append(f"  {severity_text} {diagnostic.code.value}{location}: {diagnostic.message}")
    return lines


def _section(*, report: ScopeReport, name: str) -> ScopeSection | None:
    return next((section for section in report.sections if section.name == name), None)


def _section_count(*, section: ScopeSection | None, count: int) -> str:
    if section is None:
        return f"({count})"
    suffix: str = f", {section.collapsed_count} collapsed" if section.collapsed_count else ""
    return f"({section.returned} of {section.total}{suffix})"


def _header(
    *,
    title: str,
    count: str,
    text: _ScopeText,
    title_style: Callable[[str], str] | None = None,
    count_style: Callable[[str], str] | None = None,
) -> str:
    style: CliStyle = text.style
    return f"{(title_style or style.section)(title)} {(count_style or style.muted)(count)}"


def _field(*, label: str, value: str, text: _ScopeText) -> str:
    return f"  {text.style.muted(f'{label}:')} {value}"


def _connector(*, last: bool, text: _ScopeText) -> str:
    return text.style.muted("└─" if last else "├─")


def _completeness_line(*, complete: bool, text: _ScopeText) -> str:
    style: CliStyle = text.style
    state: str = style.success("complete") if complete else style.warning("partial")
    return f"{style.muted('Completeness:')} {state}"


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
    if request.verbose:
        args.append("--verbose")
    if request.no_cache:
        args.append("--no-cache")
    return " ".join(quote(item) for item in args)
