"""Natively rendered attached audits match Python's argument merge, SQL and policies."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    AttachedAuditParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    AuditParity,
    audit_parity,
    generated_audit,
    is_native,
    native_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        AttachedAuditParityTestCase(
            description="seeded parameters, argument values, overrides and policies",
            seed=20261008,
            count=5000,
            expected_minimum_native=800,
            expected_minimum_deferred=2000,
            expected_minimum_python_errors=1000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_attachments_when_rendering_natively_then_python_rendering_matches(
    test_case: AttachedAuditParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)

    parities: list[AuditParity] = [
        audit_parity(generated_audit(rng=rng)) for _ in range(test_case.count)
    ]

    answered: list[AuditParity] = list(filter(is_native, parities))
    assert (
        mismatches(
            inputs=[parity.audit for parity in answered],
            expected=[parity.python for parity in answered],
            actual=list(map(native_outcome, answered)),
        ),
        len(answered) >= test_case.expected_minimum_native,
        len(parities) - len(answered) >= test_case.expected_minimum_deferred,
        sum(isinstance(parity.python, str) for parity in parities)
        >= test_case.expected_minimum_python_errors,
    ) == ([], True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
