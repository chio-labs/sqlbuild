"""Recognize model queries whose only change is references rewritten for renamed models."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from itertools import islice, product

from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import ReferenceRename
from sqlbuild.lint.main.scan_interpolation_sites import scan_interpolation_sites
from sqlbuild.lint.models import InterpolationSite

_REF_CALL: re.Pattern[str] = re.compile(
    r"^__ref\s*\(\s*(?P<quote>['\"])(?P<name>[^'\"]+)(?P=quote)\s*\)$"
)
_GENERIC_DIALECT: str = "generic"
_MAX_CANDIDATE_MAPPINGS: int = 64

type _NameSpan = tuple[int, int, str]


def origin_reference_names(
    *,
    query_sql: str,
    recorded: Fingerprint,
    renames: tuple[ReferenceRename, ...],
    dialect: str | None,
) -> dict[str, str] | None:
    """Return the rename mapping under which the query hashes to its recorded definition."""

    origins: dict[str, list[str]] = {}
    rename: ReferenceRename
    for rename in renames:
        if rename.recorded_at is None or _utc(recorded.ts) < _utc(rename.recorded_at):
            origins.setdefault(rename.new_name, []).append(rename.origin_name)
    if not origins:
        return None
    spans: tuple[_NameSpan, ...] = _ref_name_spans(
        query_sql=query_sql, dialect=dialect or _GENERIC_DIALECT, names=frozenset(origins)
    )
    names: tuple[str, ...] = tuple(sorted({name for _, _, name in spans}))
    choices: tuple[tuple[str, ...], ...] = tuple(
        _lineage(name=name, origins=origins) for name in names
    )
    combination: tuple[str, ...]
    for combination in islice(product(*choices), _MAX_CANDIDATE_MAPPINGS):
        mapping: dict[str, str] = {
            name: origin for name, origin in zip(names, combination, strict=True) if origin != name
        }
        if mapping and compute_query_hash(
            query_sql=_substitute(query_sql=query_sql, spans=spans, mapping=mapping),
            dialect=dialect,
        ) == (recorded.definition_hash):
            return mapping
    return None


def _ref_name_spans(
    *, query_sql: str, dialect: str, names: frozenset[str]
) -> tuple[_NameSpan, ...]:
    spans: list[_NameSpan] = []
    site: InterpolationSite
    for site in scan_interpolation_sites(body=query_sql, dialect=dialect):
        match: re.Match[str] | None = _REF_CALL.match(site.original_text)
        if match is not None and match.group("name") in names:
            spans.append(
                (
                    site.original_start + match.start("name"),
                    site.original_start + match.end("name"),
                    match.group("name"),
                )
            )
    return tuple(spans)


def _lineage(*, name: str, origins: dict[str, list[str]]) -> tuple[str, ...]:
    seen: list[str] = [name]
    index: int = 0
    while index < len(seen):
        origin: str
        for origin in origins.get(seen[index], ()):
            if origin not in seen:
                seen.append(origin)
        index += 1
    return tuple(seen)


def _substitute(*, query_sql: str, spans: tuple[_NameSpan, ...], mapping: dict[str, str]) -> str:
    pieces: list[str] = []
    copied_to: int = 0
    start: int
    end: int
    name: str
    for start, end, name in spans:
        pieces.extend((query_sql[copied_to:start], mapping.get(name, name)))
        copied_to = end
    pieces.append(query_sql[copied_to:])
    return "".join(pieces)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
