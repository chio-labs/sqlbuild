"""Public wrapper for expected-vs-built model version staleness."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner._helpers.pruning.version_staleness import (
    build_stale_model_names_from_version_identities,
)


def build_version_identity_stale_model_names(
    *,
    model_names: tuple[str, ...],
    expected_version_hashes: Mapping[str, str],
    built_version_hashes: Mapping[str, str | None],
    forced_stale_model_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    return build_stale_model_names_from_version_identities(
        model_names=model_names,
        expected_version_hashes=expected_version_hashes,
        built_version_hashes=built_version_hashes,
        forced_stale_model_names=forced_stale_model_names,
    )
