"""Incremental custom-rule evaluation keyed on the compiler facts each invocation read."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import orjson

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.fact_cache.main.code_identity import compiled_code_identity
from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
)
from sqlbuild.rule_engine._helpers.engine.fact_replay import full_fact_keys, is_tree_fact
from sqlbuild.rule_engine._helpers.host.custom_host_pool import (
    decode_readset,
    finding_payload,
    run_custom_hosts,
)
from sqlbuild.rule_engine.classes.fact_digests import FactDigests
from sqlbuild.rule_engine.classes.rule_context import RuleFactViews, build_rule_fact_views
from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_RUNTIME_VERSION,
    CUSTOM_RULE_PROJECT_SUBJECT,
    CUSTOM_RULES_CACHE_FILE,
    CUSTOM_RULES_CACHE_VERSION,
)
from sqlbuild.rule_engine.exceptions import FactDigestError, RulesError
from sqlbuild.rule_engine.models import (
    CustomHostEvaluation,
    CustomHostRun,
    CustomRulesOutcome,
    Rule,
    RulesConfig,
)
from sqlbuild.rule_engine.types import FactKey, RuleSubject


@dataclass(frozen=True)
class _Subject:
    key: str
    identity: str


@dataclass(frozen=True)
class _CachedEntry:
    subject_identity: str
    readset: int
    reads_digest: str
    findings: tuple[dict[str, object], ...]


@dataclass
class _RuleCache:
    identity: str
    readsets: list[tuple[FactKey, ...]]
    entries: dict[str, _CachedEntry]


def evaluate_custom_rules_cached(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    rules: tuple[Rule, ...],
    dialect: str,
    verify_determinism: bool = False,
    implementation_fingerprints: dict[str, str] | None = None,
) -> CustomRulesOutcome:
    """Reuse results whose recorded fact reads are unchanged and evaluate only the rest."""

    started: float = time.monotonic()
    custom: tuple[Rule, ...] = tuple(sorted(rules, key=lambda rule: rule.code))
    if not custom:
        return CustomRulesOutcome(findings=(), cache_hits=0, cache_misses=0, custom_ms=0)
    if not config.cache.enabled:
        uncached: CustomHostRun = run_custom_hosts(
            project=_host_project(project),
            config=config,
            project_dir=project_dir,
            dialect=dialect,
            rules=custom,
            model_paths=_model_paths(project),
            plan={rule.code: None for rule in custom},
            track_reads=False,
            verify_determinism=verify_determinism,
        )
        return CustomRulesOutcome(
            findings=_ordered_findings(
                rules=custom,
                subjects=_subjects(project=project, rules=custom),
                results={key: value.findings for key, value in uncached.evaluated.items()},
            ),
            cache_hits=0,
            cache_misses=len(custom),
            custom_ms=_elapsed_ms(started),
        )
    digests: FactDigests = FactDigests(
        views=_views_factory(project=project, project_dir=project_dir, dialect=dialect)
    )
    subjects: dict[str, tuple[_Subject, ...]] = _subjects(project=project, rules=custom)
    identities: dict[str, str] = {
        rule.code: _rule_identity(
            rule=rule,
            config=config,
            project_dir=project_dir,
            dialect=dialect,
            fingerprint=(implementation_fingerprints or {}).get(rule.code),
        )
        for rule in custom
    }
    cache_path: Path = project_dir / CUSTOM_RULES_CACHE_FILE
    stored: dict[str, _RuleCache] = _read_cache(cache_path)
    results: dict[tuple[str, str], tuple[dict[str, object], ...]] = {}
    plan: dict[str, list[str] | None] = {}
    hits: int = 0
    for rule in custom:
        cached: _RuleCache | None = stored.get(rule.code)
        if cached is not None and cached.identity != identities[rule.code]:
            cached = None
        current_digests: dict[int, str | None] = {}
        missing: list[str] = []
        for subject in subjects[rule.code]:
            entry: _CachedEntry | None = None if cached is None else cached.entries.get(subject.key)
            if (
                entry is not None
                and cached is not None
                and entry.subject_identity == subject.identity
                and _readset_digest(
                    cached=cached, index=entry.readset, digests=digests, memo=current_digests
                )
                == entry.reads_digest
            ):
                results[(rule.code, subject.key)] = entry.findings
                hits += 1
            else:
                missing.append(subject.key)
        if missing:
            plan[rule.code] = None if len(missing) == len(subjects[rule.code]) else sorted(missing)
    misses: int = sum(
        len(subjects[code]) if planned is None else len(planned) for code, planned in plan.items()
    )
    if plan:
        run: CustomHostRun = run_custom_hosts(
            project=_host_project(project),
            config=config,
            project_dir=project_dir,
            dialect=dialect,
            rules=custom,
            model_paths=_model_paths(project),
            plan=plan,
            track_reads=True,
            verify_determinism=verify_determinism,
        )
        _validate_paths(project=project, rules=custom, evaluated=run.evaluated)
        stored = _store(
            stored=stored,
            identities=identities,
            subjects=subjects,
            run=run,
            digests=digests,
        )
        for key, value in run.evaluated.items():
            results[key] = value.findings
        _write_cache(path=cache_path, stored=stored, subjects=subjects)
    return CustomRulesOutcome(
        findings=_ordered_findings(
            rules=custom,
            subjects=subjects,
            results=results,
        ),
        cache_hits=hits,
        cache_misses=misses,
        custom_ms=_elapsed_ms(started),
    )


def _views_factory(
    *, project: CompiledProject, project_dir: Path, dialect: str
) -> Callable[[], RuleFactViews]:
    def build() -> RuleFactViews:
        return build_rule_fact_views(
            project=_host_project(project), project_dir=project_dir, dialect=dialect
        )

    return build


def _subjects(
    *, project: CompiledProject, rules: tuple[Rule, ...]
) -> dict[str, tuple[_Subject, ...]]:
    project_subject: tuple[_Subject, ...] = (
        _Subject(
            key=CUSTOM_RULE_PROJECT_SUBJECT,
            identity=_digest([len(project.models), project.effective_target_name]),
        ),
    )
    model_subjects: tuple[_Subject, ...] = tuple(
        _Subject(
            key=model.relative_path.as_posix(),
            identity=_digest([model.name, model.relative_path.as_posix(), _materialization(model)]),
        )
        for model in sorted(project.models, key=lambda item: item.relative_path.as_posix())
    )
    return {
        rule.code: project_subject if rule.subject is RuleSubject.PROJECT else model_subjects
        for rule in rules
    }


def _model_paths(project: CompiledProject) -> tuple[str, ...]:
    return tuple(sorted(model.relative_path.as_posix() for model in project.models))


def _materialization(model: Any) -> str | None:
    value: object = model.config.values.get("materialized")
    return value if isinstance(value, str) else None


def _rule_identity(
    *, rule: Rule, config: RulesConfig, project_dir: Path, dialect: str, fingerprint: str | None
) -> str:
    return _digest(
        [
            CUSTOM_RULES_CACHE_VERSION,
            CUSTOM_HOST_RUNTIME_VERSION,
            compiled_code_identity(),
            rule.code,
            rule.family,
            rule.slug,
            rule.message,
            rule.remediation,
            None if rule.subject is None else rule.subject.value,
            fingerprint
            if fingerprint is not None
            else custom_rule_implementation_fingerprint(
                rule=rule,
                project_dir=project_dir,
                import_closure=custom_rule_import_closure(rule=rule, project_dir=project_dir),
            ),
            asdict(config),
            dialect,
            str(project_dir.resolve()),
        ]
    )


def _readset_digest(
    *, cached: _RuleCache, index: int, digests: FactDigests, memo: dict[int, str | None]
) -> str | None:
    if index not in memo:
        try:
            memo[index] = (
                digests.combined(cached.readsets[index])
                if 0 <= index < len(cached.readsets)
                else None
            )
        except FactDigestError:
            memo[index] = None
    return memo[index]


def _host_project(project: CompiledProject) -> CompiledProject:
    return replace(
        project,
        binding_catalog=None,
        sql_expansions={},
        loaded_macros={},
        loader_functions=(),
        hook_functions=(),
        materialization_files=(),
        external_sql_reference_resolver=None,
    )


def _validate_paths(
    *,
    project: CompiledProject,
    rules: tuple[Rule, ...],
    evaluated: dict[tuple[str, str], CustomHostEvaluation],
) -> None:
    codes: frozenset[str] = frozenset(rule.code for rule in rules)
    model_rules: frozenset[str] = frozenset(
        rule.code for rule in rules if rule.subject is RuleSubject.MODEL
    )
    model_paths: frozenset[str] = frozenset(
        model.relative_path.as_posix() for model in project.models
    )
    for (code, _subject), result in evaluated.items():
        for finding in result.findings:
            if finding.get("code") not in codes:
                raise RulesError(
                    f"custom rule host returned a finding for unselected rule {finding.get('code')}"
                )
            if code in model_rules and finding.get("path") not in model_paths:
                raise RulesError(
                    "model-subject custom rule returned a finding for unrelated path "
                    f"{finding.get('path')}"
                )


def _store(
    *,
    stored: dict[str, _RuleCache],
    identities: dict[str, str],
    subjects: dict[str, tuple[_Subject, ...]],
    run: CustomHostRun,
    digests: FactDigests,
) -> dict[str, _RuleCache]:
    updated: dict[str, _RuleCache] = {}
    full_keys: tuple[FactKey, ...] | None = None
    for code, identity in identities.items():
        previous: _RuleCache | None = stored.get(code)
        current: _RuleCache = (
            _RuleCache(identity=identity, readsets=[], entries={})
            if previous is None or previous.identity != identity
            else _RuleCache(
                identity=identity,
                readsets=list(previous.readsets),
                entries=dict(previous.entries),
            )
        )
        updated[code] = current
        by_subject: dict[str, _Subject] = {subject.key: subject for subject in subjects[code]}
        positions: dict[tuple[FactKey, ...], int] = {
            readset: index for index, readset in enumerate(current.readsets)
        }
        combined_by_readset: dict[tuple[FactKey, ...], str | None] = {}
        for (evaluated_code, subject_key), result in run.evaluated.items():
            if evaluated_code != code:
                continue
            if code in run.uncacheable:
                current.entries.pop(subject_key, None)
                continue
            reads: tuple[FactKey, ...] | None = result.reads
            if reads is None:
                if full_keys is None:
                    full_keys = full_fact_keys(digests.views)
                reads = (*run.untracked_reads.get(code, ()), *full_keys)
            readset: tuple[FactKey, ...] = tuple(sorted(set(reads)))
            if readset not in combined_by_readset:
                combined_by_readset[readset] = _observed_digest(
                    readset=readset, observed=run.observed, digests=digests
                )
            combined: str | None = combined_by_readset[readset]
            if combined is None:
                current.entries.pop(subject_key, None)
                continue
            index: int | None = positions.get(readset)
            if index is None:
                index = len(current.readsets)
                current.readsets.append(readset)
                positions[readset] = index
            current.entries[subject_key] = _CachedEntry(
                subject_identity=by_subject[subject_key].identity,
                readset=index,
                reads_digest=combined,
                findings=result.findings,
            )
    return updated


def _observed_digest(
    *, readset: tuple[FactKey, ...], observed: dict[FactKey, str | None], digests: FactDigests
) -> str | None:
    """Digest a read set only when its filesystem facts still match what the rule observed."""

    try:
        for key in readset:
            if is_tree_fact(key) and key in observed and observed[key] != digests.digest(key):
                return None
        return digests.combined(readset)
    except FactDigestError:
        return None


def _ordered_findings(
    *,
    rules: tuple[Rule, ...],
    subjects: dict[str, tuple[_Subject, ...]],
    results: dict[tuple[str, str], tuple[dict[str, object], ...]],
) -> tuple[dict[str, object], ...]:
    findings: list[dict[str, object]] = []
    for rule in rules:
        for subject in subjects[rule.code]:
            findings.extend(results.get((rule.code, subject.key), ()))
    return tuple(findings)


def _read_cache(path: Path) -> dict[str, _RuleCache]:
    try:
        payload: object = orjson.loads(path.read_bytes())
    except (OSError, orjson.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != CUSTOM_RULES_CACHE_VERSION:
        return {}
    rules: object = payload.get("rules")
    if not isinstance(rules, dict):
        return {}
    stored: dict[str, _RuleCache] = {}
    for code, value in rules.items():
        try:
            stored[str(code)] = _RuleCache(
                identity=str(value["identity"]),
                readsets=list(map(decode_readset, value["readsets"])),
                entries={
                    str(subject): _decode_entry(entry)
                    for subject, entry in value["entries"].items()
                },
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return stored


def _write_cache(
    *, path: Path, stored: dict[str, _RuleCache], subjects: dict[str, tuple[_Subject, ...]]
) -> None:
    rules: dict[str, object] = {}
    for code, cached in stored.items():
        if code not in subjects:
            continue
        live: frozenset[str] = frozenset(subject.key for subject in subjects[code])
        entries: dict[str, _CachedEntry] = {
            key: entry for key, entry in cached.entries.items() if key in live
        }
        used: list[int] = sorted({entry.readset for entry in entries.values()})
        remap: dict[int, int] = {old: new for new, old in enumerate(used)}
        rules[code] = {
            "identity": cached.identity,
            "readsets": [list(map(list, cached.readsets[index])) for index in used],
            "entries": {
                key: [
                    entry.subject_identity,
                    remap[entry.readset],
                    entry.reads_digest,
                    list(entry.findings),
                ]
                for key, entry in entries.items()
            },
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(f".tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.write_bytes(orjson.dumps({"version": CUSTOM_RULES_CACHE_VERSION, "rules": rules}))
    temporary.replace(path)


def _decode_entry(value: Any) -> _CachedEntry:
    return _CachedEntry(
        subject_identity=str(value[0]),
        readset=int(value[1]),
        reads_digest=str(value[2]),
        findings=tuple(map(finding_payload, value[3])),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(orjson.dumps(value, default=str)).hexdigest()


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
