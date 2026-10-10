"""The analysis cache context and the model analysis cache metrics."""

from __future__ import annotations

import hashlib
import inspect
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import AnalysisCacheContext
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.sql_analysis.constants import TYPE_CHECKED_DIALECTS

_ANALYSIS_CACHE_VERSION: int = 13
_ANALYSIS_ALGORITHM_FINGERPRINT: str = "model-sql-analysis-v21-completed-star-shapes"
_LOCAL_QUALNAME_MARKER: str = "<locals>"


def build_analysis_cache_context(
    *,
    root: Path | None,
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    rich_type_inference: bool = True,
    signature_namespace: object = None,
) -> AnalysisCacheContext | None:
    """Build a reusable cache context, or bypass when profile identity is unstable."""

    if root is None:
        return None
    profile_payload: dict[str, object] | None = _inference_profile_payload(inference_profile)
    if profile_payload is None:
        return None
    shared_payload: dict[str, object] = {
        "algorithm": _ANALYSIS_ALGORITHM_FINGERPRINT,
        "cache_version": _ANALYSIS_CACHE_VERSION,
        "sqlbuild_version": _package_version("sqlbuild"),
        "polyglot_version": _package_version("polyglot-sql-chio"),
        "python_version": platform.python_version_tuple()[:2],
        "allow_compact_analysis": allow_compact_analysis,
        "rich_type_inference": rich_type_inference,
        "type_checked_dialects": sorted(TYPE_CHECKED_DIALECTS),
        "inference_profile": profile_payload,
    }
    try:
        return AnalysisCacheContext(
            root=root,
            shared_fingerprint=_payload_digest(shared_payload),
            signature_namespace=_payload_digest(signature_namespace),
        )
    except (TypeError, ValueError):
        return None


def record_analysis_cache_metrics(
    *, batch_hits: int, entry_hits: int, misses: int, bypasses: int
) -> None:
    """Record semantic analysis cache outcomes for one invocation."""

    record_compile_metric(metric="analysis_batch_cache_hits", value=batch_hits)
    record_compile_metric(metric="analysis_entry_cache_hits", value=entry_hits)
    record_compile_metric(metric="analysis_cache_misses", value=misses)
    record_compile_metric(metric="analysis_cache_bypasses", value=bypasses)


def _inference_profile_payload(
    profile: ExpressionInferenceProfile,
) -> dict[str, object] | None:
    rules: list[dict[str, str]] = []
    for name, rule in sorted(profile.function_nullability_rules.items()):
        if not inspect.isfunction(rule):
            return None
        module: str = rule.__module__
        qualname: str = rule.__qualname__
        if (
            not module.startswith("sqlbuild.")
            or _LOCAL_QUALNAME_MARKER in qualname
            or rule.__closure__ is not None
            or rule.__defaults__ is not None
            or rule.__kwdefaults__ is not None
        ):
            return None
        try:
            source: str = inspect.getsource(rule)
        except (OSError, TypeError):
            return None
        rules.append(
            {
                "name": name,
                "module": module,
                "qualname": qualname,
                "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "sql_analysis_dialect": profile.sql_analysis_dialect,
        "quoted_identifiers_ignore_case": profile.quoted_identifiers_ignore_case,
        "semantic_known_functions": profile.semantic_known_functions,
        "semantic_known_types": profile.semantic_known_types,
        "function_nullability_rules": rules,
        "function_return_types": dict(sorted(profile.function_return_types.items())),
    }


def _payload_digest(payload: object) -> str:
    encoded: bytes = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"
