"""The one allow-list of native-to-Python fallbacks and analysis deferrals, checked or rewritten."""

from __future__ import annotations

import tomllib
from collections import Counter
from pathlib import Path

from scripts.compiler_differential.constants import (
    CORPUS_SEEDS,
    NATIVE_FALLBACK_ANSWER_SUFFIX,
    NATIVE_FALLBACK_COUNTS_FIELD,
    NATIVE_FALLBACK_DEFERRAL_STAGES,
    NATIVE_FALLBACK_DEFERRAL_UNKNOWN_STAGE,
    NATIVE_FALLBACK_LIST_HEADER,
    NATIVE_FALLBACK_MAX_COUNTS_FIELD,
    NATIVE_FALLBACK_MODE_UPDATE,
    NATIVE_FALLBACK_PROJECT_CORPUS,
    NATIVE_FALLBACK_SITE_SEPARATOR,
)
from scripts.compiler_differential.models import (
    AllowList,
    FallbackGateRequest,
    ProjectComparison,
    RecordedRun,
)
from scripts.compiler_differential.types import FallbackKey


def native_fallback_gate(
    *, request: FallbackGateRequest | None, comparisons: list[ProjectComparison]
) -> tuple[str, ...]:
    """Check the run against the allow-list, or rewrite it; print and return every problem."""

    if request is None:
        return ()
    observed: dict[FallbackKey, dict[str, int]] = observed_fallbacks(
        comparisons=comparisons, engines=request.run.engines
    )
    if request.mode == NATIVE_FALLBACK_MODE_UPDATE:
        write_allow_list(path=request.allow_list, observed=observed, run=request.run)
        print(f"Native fallback allow-list rewritten: {request.allow_list}")
        return ()
    problems: list[str] = fallback_problems(
        observed=observed, allowed=read_allow_list(request.allow_list), run=request.run
    )
    for problem in problems:
        print(f"Native fallback allow-list: {problem}")
    return tuple(problems)


def observed_fallbacks(
    *, comparisons: list[ProjectComparison], engines: tuple[str, ...]
) -> dict[FallbackKey, dict[str, int]]:
    """Sum every engine's fallback and analysis deferral records by entry and corpus."""

    counts: Counter[tuple[FallbackKey, str]] = Counter()
    for comparison in comparisons:
        corpus: str = comparison.project.split("/", 1)[0]
        for engine, records in zip(engines, comparison.records or (), strict=False):
            for (site, kind), count in records.fallbacks.items():
                stage: str = site.split(NATIVE_FALLBACK_SITE_SEPARATOR, 1)[0]
                counts[((engine, stage, site, kind), corpus)] += count
            for (kind, site), count in records.deferrals.items():
                stage = NATIVE_FALLBACK_DEFERRAL_STAGES.get(
                    site, NATIVE_FALLBACK_DEFERRAL_UNKNOWN_STAGE
                )
                counts[((engine, stage, site, kind), corpus)] += count
    observed: dict[FallbackKey, dict[str, int]] = {}
    for (key, corpus), count in sorted(counts.items()):
        observed.setdefault(key, {})[corpus] = count
    return observed


def read_allow_list(path: Path) -> AllowList:
    """Parse the allow-list file; a missing file allows nothing."""

    if not path.is_file():
        return AllowList(seed_start=0, seeds=0, counts={}, max_counts={})
    document: dict[str, object] = tomllib.loads(path.read_text(encoding="utf-8"))
    counts: dict[FallbackKey, dict[str, int]] = {}
    max_counts: dict[FallbackKey, dict[str, int]] = {}
    entries: object = document.get("entry", [])
    for entry in entries if isinstance(entries, list) else []:
        key: FallbackKey = (
            str(entry["engine"]),
            str(entry["stage"]),
            str(entry["site"]),
            str(entry["kind"]),
        )
        bounded: bool = NATIVE_FALLBACK_MAX_COUNTS_FIELD in entry
        field: str = NATIVE_FALLBACK_MAX_COUNTS_FIELD if bounded else NATIVE_FALLBACK_COUNTS_FIELD
        target: dict[FallbackKey, dict[str, int]] = max_counts if bounded else counts
        target[key] = {str(name): int(value) for name, value in entry[field].items()}
    return AllowList(
        seed_start=int(str(document.get("seed_start", 0))),
        seeds=int(str(document.get("seeds", 0))),
        counts=counts,
        max_counts=max_counts,
    )


def fallback_problems(
    *, observed: dict[FallbackKey, dict[str, int]], allowed: AllowList, run: RecordedRun
) -> list[str]:
    """Every way the run's records differ from the allow-list, as instructions to the author."""

    if CORPUS_SEEDS in run.corpora and (run.seed_start, run.seeds) != (
        allowed.seed_start,
        allowed.seeds,
    ):
        return [
            f"the allow-list holds counts for --seed-start {allowed.seed_start} --seeds "
            f"{allowed.seeds}; this run used --seed-start {run.seed_start} --seeds {run.seeds}"
        ]
    corpora: frozenset[str] = _corpus_prefixes(run.corpora)
    problems: list[str] = []
    for key in sorted({*allowed.counts, *allowed.max_counts, *observed}):
        if key[0] not in run.engines:
            continue
        actual: dict[str, int] = observed.get(key, {})
        exact: dict[str, int] | None = allowed.counts.get(key)
        bound: dict[str, int] | None = allowed.max_counts.get(key)
        for corpus in sorted({*actual, *(exact or {}), *(bound or {})} & corpora):
            problem: str | None = _corpus_problem(
                label=_label(key=key, corpus=corpus),
                answer=key[2].endswith(NATIVE_FALLBACK_ANSWER_SUFFIX),
                actual=actual.get(corpus, 0),
                exact=None if exact is None else exact.get(corpus, 0),
                bound=None if bound is None else bound.get(corpus, 0),
            )
            if problem is not None:
                problems.append(problem)
    return problems


def write_allow_list(
    *, path: Path, observed: dict[FallbackKey, dict[str, int]], run: RecordedRun
) -> None:
    """Record the run's counts, keeping entries for engines and corpora this run did not cover."""

    previous: AllowList = read_allow_list(path)
    covered: frozenset[str] = _corpus_prefixes(run.corpora)
    counts: dict[FallbackKey, dict[str, int]] = {}
    for key, by_corpus in previous.counts.items():
        kept: dict[str, int] = {
            corpus: count
            for corpus, count in by_corpus.items()
            if key[0] not in run.engines or corpus not in covered
        }
        if kept:
            counts[key] = kept
    for key, by_corpus in observed.items():
        if key[0] in run.engines and key not in previous.max_counts:
            counts[key] = {**counts.get(key, {}), **by_corpus}
    entries: list[tuple[FallbackKey, str, dict[str, int]]] = [
        *((key, NATIVE_FALLBACK_COUNTS_FIELD, values) for key, values in counts.items()),
        *(
            (key, NATIVE_FALLBACK_MAX_COUNTS_FIELD, values)
            for key, values in previous.max_counts.items()
        ),
    ]
    seeded: bool = CORPUS_SEEDS in run.corpora
    lines: list[str] = [
        NATIVE_FALLBACK_LIST_HEADER,
        f"seed_start = {run.seed_start if seeded else previous.seed_start}",
        f"seeds = {run.seeds if seeded else previous.seeds}",
    ]
    for (engine, stage, site, kind), field, values in sorted(entries):
        inline: str = ", ".join(f"{corpus} = {count}" for corpus, count in sorted(values.items()))
        lines.extend(
            (
                "",
                "[[entry]]",
                f'engine = "{engine}"',
                f'stage = "{stage}"',
                f'site = "{site}"',
                f'kind = "{kind}"',
                f"{field} = {{ {inline} }}",
            )
        )
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _corpus_problem(
    *, label: str, answer: bool, actual: int, exact: int | None, bound: int | None
) -> str | None:
    if answer and exact is None and bound is None:
        return f"{label}: native answered {actual}, not on the allow-list; record it"
    if answer and actual == 0:
        return (
            f"{label}: native no longer answers here, so this work now runs in Python; "
            "restore the native path, or record the change with a reason"
        )
    if exact is None and bound is None:
        return f"{label}: {actual} not on the allow-list; port it or list it with a reason"
    if actual == 0:
        return f"{label}: listed but no longer occurs; remove it from the allow-list"
    if bound is not None:
        return None if actual <= bound else f"{label}: {actual} exceeds the allowed {bound}"
    if actual != exact:
        return f"{label}: {actual} where the allow-list expects {exact}; update the count"
    return None


def _label(*, key: FallbackKey, corpus: str) -> str:
    engine, stage, site, kind = key
    return f"{engine} {stage} {site} {kind} ({corpus})"


def _corpus_prefixes(corpora: tuple[str, ...]) -> frozenset[str]:
    """Project-name prefixes of the selected corpora (`seeds` names projects `seed/...`)."""

    return frozenset(
        {*(corpus.removesuffix("s") for corpus in corpora), NATIVE_FALLBACK_PROJECT_CORPUS}
    )
