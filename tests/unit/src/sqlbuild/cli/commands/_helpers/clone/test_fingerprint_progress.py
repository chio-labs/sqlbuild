from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.clone.fingerprint_progress import (
    create_clone_fingerprint_progress_reporter,
)
from sqlbuild.executor.clone.types import CloneFingerprintProgressReporter
from tests.unit.src.sqlbuild.cli.commands._helpers.clone._test_types import (
    CloneFingerprintProgressReporterTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CloneFingerprintProgressReporterTestCase(
            description="reports completed batch and unconfirmed identities after interruption",
            completed=50,
            total=52,
            pending_identities=("model:orders_50", "model:orders_51"),
            expected_fragments=(
                "[50/52] propagated OK",
                "[50/52] FAIL not confirmed: model:orders_50, model:orders_51",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_partial_progress_when_interrupted_then_reporter_names_unconfirmed_fingerprints(
    test_case: CloneFingerprintProgressReporterTestCase,
) -> None:
    stream: StringIO = StringIO()
    reporter: CloneFingerprintProgressReporter = create_clone_fingerprint_progress_reporter(
        stream=stream,
        use_color=False,
    )

    reporter(
        completed=0,
        total=test_case.total,
        pending_identities=("model:orders_0", *test_case.pending_identities),
    )
    reporter(
        completed=test_case.completed,
        total=test_case.total,
        pending_identities=test_case.pending_identities,
    )
    reporter.write_interrupted()

    output: str = stream.getvalue()
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output
