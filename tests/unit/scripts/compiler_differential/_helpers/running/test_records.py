"""Wheel-site and deferral records are summed per engine, site and corpus, never gated."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.running.records import (
    format_wheel_site_report,
    read_analysis_records,
    wheel_site_report,
)
from scripts.compiler_differential.models import AnalysisRecords, ProjectComparison
from tests.unit.scripts.compiler_differential._helpers.running._test_types import (
    AnalysisRecordsTestCase,
)

_SITE: str = "compiler/compile/_helpers/analysis/columns.py:_infer_columns_with_polyglot"


@pytest.mark.parametrize(
    "test_case",
    [
        AnalysisRecordsTestCase(
            description="two_processes_and_one_deferral",
            files={
                "0-compile/polyglot-sites-11.json": json.dumps(
                    {"calls": [[_SITE, "parse_one", 2]]}
                ),
                "2-plan/polyglot-sites-12.json": json.dumps({"calls": [[_SITE, "parse_one", 3]]}),
                "2-plan/analysis-deferrals-12.jsonl": (
                    json.dumps({"kind": "legacy_fallback", "site": "compact.py"}) + "\n"
                ),
            },
            expected_wheel_sites={(_SITE, "parse_one"): 5},
            expected_deferrals={("legacy_fallback", "compact.py"): 1},
            expected_lines=(
                "Polyglot wheel calls (python):",
                f"        5 {_SITE} parse_one (seed 5)",
                "Analysis deferrals (python):",
                "        1 legacy_fallback compact.py (seed 1)",
                "Polyglot wheel calls (native-preview): none recorded",
                "Analysis deferrals (native-preview): none recorded",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_record_files_when_reporting_then_counts_are_summed_per_engine_and_corpus(
    test_case: AnalysisRecordsTestCase, tmp_path: Path
) -> None:
    for relative_path, contents in test_case.files.items():
        path: Path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")

    records: AnalysisRecords = read_analysis_records(tmp_path)
    report: str = format_wheel_site_report(
        wheel_site_report(
            comparisons=[
                ProjectComparison(
                    project="seed/3",
                    differences=(),
                    seconds=1.0,
                    records=(records, read_analysis_records(tmp_path / "missing")),
                )
            ],
            engines=("python", "native-preview"),
        )
    )

    assert (records.wheel_sites, records.deferrals) == (
        test_case.expected_wheel_sites,
        test_case.expected_deferrals,
    )
    assert report.splitlines() == list(test_case.expected_lines)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
