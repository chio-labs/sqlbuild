"""Run planned custom-rule invocations across isolated host processes and merge their results."""

from __future__ import annotations

import os
import pickle
import sys
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_LAUNCH_MODULE,
    CUSTOM_HOST_MAX_TRACKED_READS,
    CUSTOM_HOST_RUNTIME_VERSION,
    CUSTOM_RULE_PROJECT_SUBJECT,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    CustomHostEvaluation,
    CustomHostRun,
    CustomHostSlice,
    Rule,
    RulesConfig,
)
from sqlbuild.rule_engine.types import CustomHostPlan, FactKey, RuleSubject

_HOST_TIMEOUT_MILLIS: int = 120_000
_MIN_INVOCATIONS_PER_HOST: int = 64


def run_custom_hosts(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    rules: tuple[Rule, ...],
    model_paths: tuple[str, ...],
    plan: CustomHostPlan,
    track_reads: bool,
    verify_determinism: bool,
) -> CustomHostRun:
    """Evaluate the plan across host processes and merge their results in single-host order."""

    invocations: tuple[tuple[str, str], ...] = planned_invocations(
        plan=plan, rules=rules, model_paths=model_paths
    )
    plans: tuple[CustomHostPlan, ...] = (
        (plan,)
        if verify_determinism
        else partition_host_plan(
            plan=plan, invocations=invocations, hosts=_host_count(len(invocations))
        )
    )
    input_dir: Path = project_dir / "target" / "rules-cache" / "host-inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=input_dir, prefix="project-", suffix=".pickle", delete=False
        ) as handle:
            input_path = Path(handle.name)
            pickle.dump((project, config), handle)
        payload: dict[str, object] = {
            "project_pickle_path": str(input_path.resolve()),
            "project_dir": str(project_dir.resolve()),
            "dialect": dialect,
            "verify_determinism": verify_determinism,
            "track_reads": track_reads,
        }
        responses: list[CustomHostSlice] = (
            [_run_host(payload={**payload, "plan": plan})]
            if len(plans) == 1
            else _run_partitions(payload=payload, plan=plan, plans=plans)
        )
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)
    return _merge(
        responses=responses,
        order={invocation: index for index, invocation in enumerate(invocations)},
    )


def _run_partitions(
    *, payload: dict[str, object], plan: CustomHostPlan, plans: tuple[CustomHostPlan, ...]
) -> list[CustomHostSlice]:
    """Run every partition; after any failure, one host reruns the whole plan to report it."""

    with ThreadPoolExecutor(
        max_workers=len(plans), thread_name_prefix="sqlbuild-custom-host"
    ) as pool:
        futures: list[Future[CustomHostSlice]] = [
            pool.submit(_run_host, payload={**payload, "plan": partition}) for partition in plans
        ]
        failed: bool = any(future.exception() is not None for future in futures)
    if failed:
        return [_run_host(payload={**payload, "plan": plan})]
    return [future.result() for future in futures]


def planned_invocations(
    *, plan: CustomHostPlan, rules: tuple[Rule, ...], model_paths: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """List planned (rule, subject) invocations in the order one host evaluates them."""

    planned: tuple[Rule, ...] = tuple(
        sorted((rule for rule in rules if rule.code in plan), key=lambda rule: rule.code)
    )
    invocations: list[tuple[str, str]] = [
        (rule.code, CUSTOM_RULE_PROJECT_SUBJECT)
        for rule in planned
        if rule.subject is RuleSubject.PROJECT
    ]
    model_rules: tuple[tuple[str, frozenset[str] | None], ...] = tuple(
        (rule.code, None if plan[rule.code] is None else frozenset(plan[rule.code] or ()))
        for rule in planned
        if rule.subject is RuleSubject.MODEL
    )
    for path in model_paths if model_rules else ():
        invocations.extend(
            (code, path) for code, selected in model_rules if selected is None or path in selected
        )
    return tuple(invocations)


def partition_host_plan(
    *, plan: CustomHostPlan, invocations: tuple[tuple[str, str], ...], hosts: int
) -> tuple[CustomHostPlan, ...]:
    """Deal project invocations and whole model subjects round-robin across at most `hosts`."""

    units: list[list[tuple[str, str]]] = []
    for code, subject in invocations:
        if subject == CUSTOM_RULE_PROJECT_SUBJECT or not units or units[-1][0][1] != subject:
            units.append([])
        units[-1].append((code, subject))
    count: int = max(1, min(hosts, len(units)))
    if count == 1:
        return (plan,)
    partitions: list[dict[str, list[str]]] = []
    for _ in range(count):
        partitions.append({code: [] for code in plan})
    for index, unit in enumerate(units):
        for code, subject in unit:
            partitions[index % count][code].append(subject)
    return tuple(cast(CustomHostPlan, partition) for partition in partitions)


def _host_count(invocations: int) -> int:
    return max(1, min(_available_cores(), invocations // _MIN_INVOCATIONS_PER_HOST))


def _available_cores() -> int:
    affinity: Any = getattr(os, "sched_getaffinity", None)
    return len(affinity(0)) if affinity is not None else os.cpu_count() or 1


def _run_host(*, payload: dict[str, object]) -> CustomHostSlice:
    try:
        response_json: str = _native.run_custom_host_json(
            orjson.dumps(
                {
                    "program": sys.executable,
                    "arguments": ["-m", CUSTOM_HOST_LAUNCH_MODULE],
                    "timeout_millis": _HOST_TIMEOUT_MILLIS,
                    "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
                    "payload": payload,
                }
            ).decode()
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return _decode_host_response(orjson.loads(response_json))


def _decode_host_response(response: object) -> CustomHostSlice:
    if not isinstance(response, dict):
        raise RulesError("custom rule host returned an invalid payload")
    payload: dict[str, Any] = cast(dict[str, Any], response)
    raw_readsets: Any = payload.get("readsets")
    raw_evaluations: Any = payload.get("evaluations")
    raw_untracked: Any = payload.get("untracked")
    raw_uncacheable: Any = payload.get("uncacheable")
    raw_observed: Any = payload.get("observed")
    if (
        not isinstance(raw_readsets, list)
        or not isinstance(raw_evaluations, list)
        or not isinstance(raw_untracked, dict)
        or not isinstance(raw_uncacheable, list)
        or not isinstance(raw_observed, list)
    ):
        raise RulesError("custom rule host returned an invalid payload")
    readsets: list[tuple[FactKey, ...]] = list(map(decode_readset, raw_readsets))
    untracked: dict[str, tuple[FactKey, ...]] = {
        str(code): decode_readset(reads) for code, reads in raw_untracked.items()
    }
    evaluations: list[tuple[str, str, CustomHostEvaluation]] = []
    for raw_item in raw_evaluations:
        if not isinstance(raw_item, dict):
            raise RulesError("custom rule host returned an invalid evaluation")
        item: dict[str, Any] = cast(dict[str, Any], raw_item)
        code: str = str(item["code"])
        subject: object = item.get("subject")
        findings: Any = item.get("findings")
        reads: object = item.get("reads")
        if not isinstance(findings, list):
            raise RulesError("custom rule host returned invalid findings")
        tracked: bool = isinstance(reads, int) and code not in untracked
        evaluations.append(
            (
                code,
                CUSTOM_RULE_PROJECT_SUBJECT if subject is None else str(subject),
                CustomHostEvaluation(
                    findings=tuple(map(finding_payload, findings)),
                    reads=readsets[cast(int, reads)] if tracked else None,
                ),
            )
        )
    return CustomHostSlice(
        evaluations=tuple(evaluations),
        untracked_reads=untracked,
        uncacheable=frozenset(str(code) for code in raw_uncacheable),
        observed={
            tuple(map(str, key)): None if digest is None else str(digest)
            for key, digest in raw_observed
        },
        bounded=payload.get("bounded") is True,
    )


def _merge(*, responses: list[CustomHostSlice], order: dict[tuple[str, str], int]) -> CustomHostRun:
    """Combine host slices exactly as one host would have reported every invocation."""

    evaluations: list[tuple[str, str, CustomHostEvaluation]] = []
    untracked: set[str] = set()
    for response in responses:
        evaluations.extend(response.evaluations)
        untracked.update(response.untracked_reads)
    if len(responses) > 1:
        evaluations.sort(key=lambda item: order.get((item[0], item[1]), len(order)))
    tracked_readsets: set[tuple[FactKey, ...]] = {
        result.reads
        for code, _subject, result in evaluations
        if result.reads is not None and code not in untracked
    }
    if any(response.bounded for response in responses) or (
        sum(map(len, tracked_readsets)) > CUSTOM_HOST_MAX_TRACKED_READS
    ):
        untracked.update(code for code, _subject, result in evaluations if result.reads is not None)
    untracked_reads: dict[str, set[FactKey]] = {code: set() for code in untracked}
    for response in responses:
        for code, reads in response.untracked_reads.items():
            untracked_reads[code].update(reads)
    evaluated: dict[tuple[str, str], CustomHostEvaluation] = {}
    for code, subject, result in evaluations:
        merged: CustomHostEvaluation = result
        if code in untracked and result.reads is not None:
            untracked_reads[code].update(result.reads)
            merged = CustomHostEvaluation(findings=result.findings, reads=None)
        evaluated[(code, subject)] = merged
    return CustomHostRun(
        evaluated=evaluated,
        untracked_reads={code: tuple(sorted(reads)) for code, reads in untracked_reads.items()},
        uncacheable=frozenset().union(*(response.uncacheable for response in responses)),
        observed=_merged_observations(responses),
    )


def _merged_observations(responses: list[CustomHostSlice]) -> dict[FactKey, str | None]:
    """Keep each observed digest, forgetting any that two hosts observed differently."""

    observed: dict[FactKey, str | None] = {}
    for response in responses:
        for key, digest in response.observed.items():
            if key in observed and observed[key] != digest:
                observed[key] = None
            else:
                observed.setdefault(key, digest)
    return observed


def decode_readset(value: Any) -> tuple[FactKey, ...]:
    return tuple(tuple(map(str, key)) for key in value)


def finding_payload(value: Any) -> dict[str, object]:
    return {str(key): item for key, item in value.items()}
