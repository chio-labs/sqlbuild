"""Read the debug records one engine's processes wrote: wheel sites, deferrals and fallbacks."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential.constants import (
    ANALYSIS_DEFERRAL_RECORD_PREFIX,
    NATIVE_FALLBACK_RECORD_PREFIX,
    WHEEL_SITE_RECORD_PREFIX,
)
from scripts.compiler_differential.models import AnalysisRecords, ProjectComparison


def read_analysis_records(root: Path) -> AnalysisRecords:
    """Sum every process's wheel-site, deferral and native-fallback records below `root`."""

    sites: Counter[tuple[str, str]] = Counter()
    deferrals: Counter[tuple[str, str]] = Counter()
    fallbacks: Counter[tuple[str, str]] = Counter()
    for path in sorted(root.rglob(f"{WHEEL_SITE_RECORD_PREFIX}*.json")) if root.is_dir() else ():
        payload: dict[str, object] = as_json_object(json.loads(path.read_text("utf-8"))) or {}
        rows: object = payload.get("calls")
        for row in rows if isinstance(rows, list) else ():
            site, api, count = cast(list[object], row)
            sites[(str(site), str(api))] += int(str(count))
    for path in (
        sorted(root.rglob(f"{ANALYSIS_DEFERRAL_RECORD_PREFIX}*.jsonl")) if root.is_dir() else ()
    ):
        for line in path.read_text("utf-8").splitlines():
            record: dict[str, object] = as_json_object(json.loads(line)) or {}
            deferrals[(str(record.get("kind")), str(record.get("site")))] += 1
    for path in (
        sorted(root.rglob(f"{NATIVE_FALLBACK_RECORD_PREFIX}*.json")) if root.is_dir() else ()
    ):
        payload = as_json_object(json.loads(path.read_text("utf-8"))) or {}
        rows = payload.get("fallbacks")
        for row in rows if isinstance(rows, list) else ():
            site, kind, count = cast(list[object], row)
            fallbacks[(str(site), str(kind))] += int(str(count))
    return AnalysisRecords(
        wheel_sites=dict(sites), deferrals=dict(deferrals), fallbacks=dict(fallbacks)
    )


def wheel_site_report(
    *, comparisons: list[ProjectComparison], engines: tuple[str, str]
) -> dict[str, object]:
    """Return wheel calls, deferrals and native fallbacks per engine, split by corpus."""

    report: dict[str, object] = {}
    for side, engine in enumerate(engines):
        sites: dict[str, dict[str, int]] = {}
        deferrals: dict[str, dict[str, int]] = {}
        fallbacks: dict[str, dict[str, int]] = {}
        for comparison in comparisons:
            records: AnalysisRecords | None = (
                comparison.records[side] if comparison.records else None
            )
            if records is None:
                continue
            corpus: str = comparison.project.split("/", 1)[0]
            for (site, api), count in records.wheel_sites.items():
                by_corpus: dict[str, int] = sites.setdefault(f"{site} {api}", {})
                by_corpus[corpus] = by_corpus.get(corpus, 0) + count
            for (kind, site), count in records.deferrals.items():
                by_corpus = deferrals.setdefault(f"{kind} {site}", {})
                by_corpus[corpus] = by_corpus.get(corpus, 0) + count
            for (site, kind), count in records.fallbacks.items():
                by_corpus = fallbacks.setdefault(f"{site} {kind}", {})
                by_corpus[corpus] = by_corpus.get(corpus, 0) + count
        report[engine] = {
            "wheel_sites": dict(sorted(sites.items())),
            "deferrals": dict(sorted(deferrals.items())),
            "native_fallbacks": dict(sorted(fallbacks.items())),
        }
    return report


def format_wheel_site_report(report: dict[str, object]) -> str:
    """Render the wheel-site, deferral and fallback counts for the run log; nothing here gates."""

    lines: list[str] = []
    for engine, raw in report.items():
        entry: dict[str, object] = as_json_object(raw) or {}
        for label, key in (
            ("Polyglot wheel calls", "wheel_sites"),
            ("Analysis deferrals", "deferrals"),
            ("Native-to-Python fallbacks", "native_fallbacks"),
        ):
            counts: dict[str, object] = as_json_object(entry.get(key)) or {}
            lines.append(f"{label} ({engine}): {'none recorded' if not counts else ''}".rstrip())
            for name, by_corpus in counts.items():
                corpora: dict[str, object] = as_json_object(by_corpus) or {}
                split: str = ", ".join(f"{corpus} {count}" for corpus, count in corpora.items())
                total: int = sum(int(str(count)) for count in corpora.values())
                lines.append(f"  {total:>7} {name} ({split})")
    return "\n".join(lines)


def write_wheel_site_report(
    *, path: Path, comparisons: list[ProjectComparison], engines: tuple[str, str]
) -> None:
    """Write the wheel-site, deferral and fallback counts to `path` as JSON and print them."""

    report: dict[str, object] = wheel_site_report(comparisons=comparisons, engines=engines)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(format_wheel_site_report(report))
