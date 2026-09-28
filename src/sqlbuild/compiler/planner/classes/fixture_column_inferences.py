"""Fixture column inference computed once per fixture body and inference profile."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.main._infer_fixture_columns import infer_fixture_column_facts
from sqlbuild.compiler.compile.models import FixtureColumnInference


class FixtureColumnInferences:
    """Reuse inference for identical fixture SQL under an equal, catalog-free profile."""

    def __init__(self) -> None:
        self._by_profile: list[
            tuple[ExpressionInferenceProfile, dict[str, FixtureColumnInference | None]]
        ] = []

    def infer(
        self, *, query_sql: str, inference_profile: ExpressionInferenceProfile
    ) -> FixtureColumnInference | None:
        """Return the inference for one fixture query, computing each distinct query once."""

        if inference_profile.binding_catalog is not None:
            return infer_fixture_column_facts(
                query_sql=query_sql, inference_profile=inference_profile
            )
        inferred: dict[str, FixtureColumnInference | None] = self._profile_results(
            inference_profile
        )
        if query_sql not in inferred:
            inferred[query_sql] = infer_fixture_column_facts(
                query_sql=query_sql, inference_profile=inference_profile
            )
        return inferred[query_sql]

    def _profile_results(
        self, inference_profile: ExpressionInferenceProfile
    ) -> dict[str, FixtureColumnInference | None]:
        profile: ExpressionInferenceProfile
        results: dict[str, FixtureColumnInference | None]
        for profile, results in self._by_profile:
            if profile == inference_profile:
                return results
        results = {}
        self._by_profile.append((inference_profile, results))
        return results
