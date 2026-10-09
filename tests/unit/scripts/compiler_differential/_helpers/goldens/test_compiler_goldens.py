"""Golden compile outputs are masked, located per corpus project, checked and rewritten."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.goldens.goldens import (
    golden_differences,
    golden_path,
    golden_payload,
)
from scripts.compiler_differential.models import CorpusProject, Difference, ExpectedOutcome
from tests.unit.scripts.compiler_differential._helpers.goldens._test_types import (
    GoldenCheckTestCase,
    GoldenPathTestCase,
    GoldenPayloadTestCase,
)
from tests.unit.scripts.compiler_differential._helpers.goldens.helpers import (
    PROJECT_PATH,
    engine_run,
)

_SQL: str = "SELECT customer_id\nFROM orders -- 20261009T010203Z_0123456789ab\n"
_MESSAGE: str = f"model references unknown model 'ghost' in '{PROJECT_PATH}/models/a.sql'"


@pytest.mark.parametrize(
    "test_case",
    [
        GoldenPathTestCase(
            description="seed", project="seed/3", expected_path=Path("goldens/seed/3.json")
        ),
        GoldenPathTestCase(
            description="dialect_seed",
            project="seed/0-snowflake",
            expected_path=Path("goldens/seed/0-snowflake.json"),
        ),
        GoldenPathTestCase(
            description="failure_case",
            project="failure/unknown-ref",
            expected_path=Path("goldens/failure/unknown-ref.json"),
        ),
        GoldenPathTestCase(description="dense_has_none", project="dense/3000", expected_path=None),
    ],
    ids=lambda case: case.description,
)
def test_given_corpus_project_when_locating_its_golden_then_only_golden_corpora_have_one(
    test_case: GoldenPathTestCase,
) -> None:
    path: Path | None = golden_path(golden_dir=Path("goldens"), project=test_case.project)

    assert path == test_case.expected_path


@pytest.mark.parametrize(
    "test_case",
    [
        GoldenPayloadTestCase(
            description="paths_ids_timings_and_repeated_sql_masked",
            run=engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),
            masked_paths=(PROJECT_PATH,),
            expected_payload={
                "commands": [
                    {
                        "label": "compile",
                        "exit_code": 1,
                        "diagnostics": [
                            {
                                "code": "P001",
                                "message": (
                                    "model references unknown model 'ghost' in "
                                    "'<project>/models/a.sql'"
                                ),
                                "severity": "error",
                            }
                        ],
                    }
                ],
                "compiled": {
                    "marts/customer_totals.sql": [
                        "SELECT customer_id",
                        "FROM orders -- <invocation-id>",
                        "",
                    ]
                },
                "manifest": {
                    "nodes": {
                        "model.orders.customer_totals": {
                            "name": "customer_totals",
                            "config": {"materialized": "table"},
                        }
                    },
                    "sources": {},
                    "macros": {},
                    "parent_map": {"model.orders.customer_totals": []},
                },
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_engine_run_when_building_golden_then_run_specific_noise_is_masked(
    test_case: GoldenPayloadTestCase,
) -> None:
    payload: dict[str, object] = golden_payload(
        run=test_case.run, masked_paths=test_case.masked_paths
    )

    assert payload == test_case.expected_payload


@pytest.mark.parametrize(
    "test_case",
    [
        GoldenCheckTestCase(
            description="identical_engines_match",
            project="failure/unknown-ref",
            recorded=(engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),),
            checked=(
                engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),
                engine_run(engine="native", message=_MESSAGE, compiled_sql=_SQL),
            ),
            expected_differences=(),
        ),
        GoldenCheckTestCase(
            description="changed_sql_names_the_engine",
            project="failure/unknown-ref",
            recorded=(engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),),
            checked=(
                engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),
                engine_run(engine="native", message=_MESSAGE, compiled_sql="SELECT 2\n"),
            ),
            expected_differences=(("golden (native)", ("golden", "native")),),
        ),
        GoldenCheckTestCase(
            description="missing_failure_golden_fails",
            project="failure/unknown-ref",
            recorded=(),
            checked=(engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),),
            expected_differences=(("golden unknown-ref.json", ("golden", "hint")),),
        ),
        GoldenCheckTestCase(
            description="missing_seed_golden_is_skipped",
            project="seed/40",
            recorded=(),
            checked=(engine_run(engine="python", message=_MESSAGE, compiled_sql=_SQL),),
            expected_differences=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_golden_when_checking_runs_then_each_differing_engine_is_reported(
    test_case: GoldenCheckTestCase, tmp_path: Path
) -> None:
    project: CorpusProject = CorpusProject(
        name=test_case.project, commands=(), expected=ExpectedOutcome()
    )
    for recorded in test_case.recorded:
        _ = golden_differences(
            project=project,
            runs=(recorded,),
            golden_dir=tmp_path,
            mode="update",
            masked_paths=(PROJECT_PATH,),
        )

    differences: list[Difference] = golden_differences(
        project=project,
        runs=test_case.checked,
        golden_dir=tmp_path,
        mode="check",
        masked_paths=(PROJECT_PATH,),
    )

    assert [(difference.artifact, difference.labels) for difference in differences] == list(
        test_case.expected_differences
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
