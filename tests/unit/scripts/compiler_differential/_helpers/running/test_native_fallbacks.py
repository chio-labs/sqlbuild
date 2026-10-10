"""The fallback allow-list fails on new, changed and vanished entries and records new counts."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.running import native_fallbacks
from scripts.compiler_differential._helpers.running.native_fallbacks import (
    fallback_problems,
    observed_fallbacks,
    read_allow_list,
    write_allow_list,
)
from scripts.compiler_differential.models import (
    AllowList,
    AnalysisRecords,
    ProjectComparison,
    RecordedRun,
)
from scripts.compiler_differential.types import FallbackKey
from tests.unit.scripts.compiler_differential._helpers.running._test_types import (
    FallbackGateTestCase,
    FallbackRecordsTestCase,
    FallbackRewriteTestCase,
)

_VARIABLES: FallbackKey = ("native", "model_loop", "model_loop.sql_variables", "deferred")
_ANSWER: FallbackKey = (
    "native",
    "reference_extraction",
    "reference_extraction.native",
    "reference_scans",
)
_ANSWER_ENTRY: str = (
    '\n[[entry]]\nengine = "native"\nstage = "reference_extraction"\n'
    'site = "reference_extraction.native"\nkind = "reference_scans"\n'
)
_LOOP_ANSWER: FallbackKey = ("native", "model_loop", "model_loop.native", "models")
_LOOP_VARIABLE_ANSWER: FallbackKey = (
    "native",
    "model_loop",
    "model_loop.native",
    "sql_variables",
)
_LOOP_ANSWER_ENTRY: str = (
    '\n[[entry]]\nengine = "native"\nstage = "model_loop"\n'
    'site = "model_loop.native"\nkind = "models"\n'
)
_SESSION: FallbackKey = ("native-preview", "model_analysis", "analysis_session", "session")
_SHIPPED_RUN: RecordedRun = RecordedRun(
    engines=("native",), corpora=("seeds", "failures"), seed_start=0, seeds=12
)
_LIST_HEAD: str = "seed_start = 0\nseeds = 12\n"
_REFERENCES: FallbackKey = (
    "native",
    "reference_extraction",
    "reference_extraction.sql_scan",
    "deferred",
)
_REFERENCES_ENTRY: str = (
    '\n[[entry]]\nengine = "native"\nstage = "reference_extraction"\n'
    'site = "reference_extraction.sql_scan"\nkind = "deferred"\n'
)


class _SwitchableStage(StrEnum):
    """Stand-in preview stages: `model_loop` can be switched off, `reference_extraction` cannot."""

    MODEL_LOOP = "model_loop"


_VARIABLES_ENTRY: str = (
    '\n[[entry]]\nengine = "native"\nstage = "model_loop"\n'
    'site = "model_loop.sql_variables"\nkind = "deferred"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        FallbackRecordsTestCase(
            description="fallbacks_and_deferrals_keyed_by_engine_stage_site_kind",
            project="seed/3",
            records=(
                AnalysisRecords(),
                AnalysisRecords(
                    fallbacks={("model_loop.sql_variables", "deferred"): 2},
                    deferrals={("session", "analysis_session"): 1},
                ),
            ),
            expected_observed={
                ("native-preview", "model_loop", "model_loop.sql_variables", "deferred"): {
                    "seed": 2
                },
                _SESSION: {"seed": 1},
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_engine_records_when_observing_then_entries_are_summed_per_corpus(
    test_case: FallbackRecordsTestCase,
) -> None:
    comparison: ProjectComparison = ProjectComparison(
        project=test_case.project, differences=(), seconds=1.0, records=test_case.records
    )

    observed: dict[FallbackKey, dict[str, int]] = observed_fallbacks(
        comparisons=[comparison], engines=("native", "native-preview")
    )

    assert observed == test_case.expected_observed


@pytest.mark.parametrize(
    "test_case",
    [
        FallbackGateTestCase(
            description="exact_counts_pass",
            allow_list=_LIST_HEAD + _VARIABLES_ENTRY + "counts = { failure = 3, seed = 195 }\n",
            observed={_VARIABLES: {"failure": 3, "seed": 195}},
            run=_SHIPPED_RUN,
            expected_problems=[],
        ),
        FallbackGateTestCase(
            description="unlisted_entry_fails",
            allow_list=_LIST_HEAD,
            observed={_VARIABLES: {"seed": 195}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native model_loop model_loop.sql_variables deferred (seed): 195 not on the "
                "allow-list; port it or list it with a reason"
            ],
        ),
        FallbackGateTestCase(
            description="vanished_entry_with_more_native_answers_fails_until_removed",
            allow_list=_LIST_HEAD
            + _VARIABLES_ENTRY
            + "counts = { seed = 195 }\n"
            + _LOOP_ANSWER_ENTRY
            + "counts = { seed = 10 }\n",
            observed={_LOOP_ANSWER: {"seed": 10}, _LOOP_VARIABLE_ANSWER: {"seed": 195}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native model_loop model_loop.native sql_variables (seed): native answered 195, "
                "not on the allow-list; record it",
                "native model_loop model_loop.sql_variables deferred (seed): listed but no "
                "longer occurs; remove it from the allow-list",
            ],
        ),
        FallbackGateTestCase(
            description="vanished_entry_without_more_native_answers_means_the_stage_is_off",
            allow_list=_LIST_HEAD
            + _VARIABLES_ENTRY
            + "counts = { seed = 195 }\n"
            + _LOOP_ANSWER_ENTRY
            + "counts = { seed = 10 }\n",
            observed={_LOOP_ANSWER: {"seed": 10}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native model_loop model_loop.sql_variables deferred (seed): fallback disappeared "
                "but native answers did not appear; the stage may be switched off. A port that "
                "removes a fallback must report native answers for the work it now does"
            ],
        ),
        FallbackGateTestCase(
            description="vanished_entry_of_a_shipped_stage_only_asks_for_removal",
            allow_list=_LIST_HEAD + _REFERENCES_ENTRY + "counts = { seed = 3 }\n",
            observed={},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native reference_extraction reference_extraction.sql_scan deferred (seed): "
                "listed but no longer occurs; remove it from the allow-list"
            ],
        ),
        FallbackGateTestCase(
            description="changed_count_fails",
            allow_list=_LIST_HEAD + _VARIABLES_ENTRY + "counts = { seed = 195 }\n",
            observed={_VARIABLES: {"seed": 196}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native model_loop model_loop.sql_variables deferred (seed): 196 where the "
                "allow-list expects 195; update the count"
            ],
        ),
        FallbackGateTestCase(
            description="upper_bound_allows_fewer_but_not_more",
            allow_list=_LIST_HEAD + _VARIABLES_ENTRY + "max_counts = { failure = 5, seed = 200 }\n",
            observed={_VARIABLES: {"failure": 6, "seed": 150}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native model_loop model_loop.sql_variables deferred (failure): 6 exceeds the "
                "allowed 5"
            ],
        ),
        FallbackGateTestCase(
            description="engines_and_corpora_outside_the_run_are_not_checked",
            allow_list=_LIST_HEAD
            + _VARIABLES_ENTRY
            + "counts = { fixture = 4, seed = 195 }\n"
            + '\n[[entry]]\nengine = "native-preview"\nstage = "model_analysis"\n'
            + 'site = "analysis_session"\nkind = "session"\ncounts = { seed = 1 }\n',
            observed={_VARIABLES: {"seed": 195}},
            run=_SHIPPED_RUN,
            expected_problems=[],
        ),
        FallbackGateTestCase(
            description="vanished_native_answer_means_the_stage_runs_in_python",
            allow_list=_LIST_HEAD + _ANSWER_ENTRY + "counts = { seed = 40 }\n",
            observed={},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native reference_extraction reference_extraction.native reference_scans (seed): "
                "native no longer answers here, so this work now runs in Python; restore the "
                "native path, or record the change with a reason"
            ],
        ),
        FallbackGateTestCase(
            description="unlisted_native_answer_must_be_recorded",
            allow_list=_LIST_HEAD,
            observed={_ANSWER: {"seed": 40}},
            run=_SHIPPED_RUN,
            expected_problems=[
                "native reference_extraction reference_extraction.native reference_scans (seed): "
                "native answered 40, not on the allow-list; record it"
            ],
        ),
        FallbackGateTestCase(
            description="other_seed_range_is_refused",
            allow_list=_LIST_HEAD,
            observed={},
            run=RecordedRun(engines=("native",), corpora=("seeds",), seed_start=0, seeds=60),
            expected_problems=[
                "the allow-list holds counts for --seed-start 0 --seeds 12; this run used "
                "--seed-start 0 --seeds 60"
            ],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_allow_list_when_checking_a_run_then_every_difference_is_a_problem(
    test_case: FallbackGateTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_fallbacks, "NativeStage", _SwitchableStage)
    path: Path = tmp_path / "native_fallbacks.toml"
    _ = path.write_text(test_case.allow_list, encoding="utf-8")

    problems: list[str] = fallback_problems(
        observed=test_case.observed, allowed=read_allow_list(path), run=test_case.run
    )

    assert problems == test_case.expected_problems


@pytest.mark.parametrize(
    "test_case",
    [
        FallbackRewriteTestCase(
            description="other_engines_kept_and_the_run_recounted",
            allow_list=_LIST_HEAD
            + '\n[[entry]]\nengine = "native-preview"\nstage = "model_analysis"\n'
            + 'site = "analysis_session"\nkind = "session"\ncounts = { seed = 1 }\n'
            + _VARIABLES_ENTRY
            + "counts = { seed = 9 }\n",
            observed={_VARIABLES: {"failure": 3, "seed": 195}},
            run=_SHIPPED_RUN,
            expected_counts={_SESSION: {"seed": 1}, _VARIABLES: {"failure": 3, "seed": 195}},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_run_when_rewriting_then_other_engines_are_kept_and_the_run_passes(
    test_case: FallbackRewriteTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "native_fallbacks.toml"
    _ = path.write_text(test_case.allow_list, encoding="utf-8")

    write_allow_list(path=path, observed=test_case.observed, run=test_case.run)

    rewritten: AllowList = read_allow_list(path)
    assert rewritten.counts == test_case.expected_counts
    assert (
        fallback_problems(observed=test_case.observed, allowed=rewritten, run=test_case.run) == []
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
