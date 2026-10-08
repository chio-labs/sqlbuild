"""The native SQL-test extractor reads helper calls as Python's macro and reference scanners do.

Macro calls follow expansion's scanner, which decides what a helper would actually expand; a body
that scanner cannot read is left for expansion to reject. Reference calls follow the reference
scanner under each adapter's rules: only valid `__udf`/`__table_fn` calls count, the first in
text order names the kind, and malformed calls are reported as P012.
"""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    BodyCallParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    BODY_CALL_SYNTAXES,
    generated_macro_body,
    generated_reference_body,
    macro_scannable,
    native_macro_outcome,
    native_reference_outcome,
    python_macro_outcome,
    python_reference_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        BodyCallParityTestCase(
            description="macro calls, declaration calls and macro-like text",
            seed=20261008,
            count=4000,
            expected_minimum_calls=1000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_helper_bodies_when_detecting_macro_calls_then_expansion_scanner_matches(
    test_case: BodyCallParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    bodies: list[str] = [generated_macro_body(rng=rng) for _ in range(test_case.count)]
    python: list[object] = [python_macro_outcome(body=body) for body in bodies]
    scannable: list[str] = list(filter(macro_scannable, bodies))

    assert (
        mismatches(
            inputs=[*scannable],
            expected=[python_macro_outcome(body=body) for body in scannable],
            actual=[native_macro_outcome(body=body) for body in scannable],
        ),
        python.count("calls macros True") >= test_case.expected_minimum_calls,
    ) == ([], True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        BodyCallParityTestCase(
            description="valid, malformed and hidden reference calls under four adapters",
            seed=20261009,
            count=4000,
            expected_minimum_calls=1000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_helper_bodies_when_reading_reference_calls_then_reference_scanner_matches(
    test_case: BodyCallParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    cases: list[tuple[str, str]] = [
        (rng.choice(tuple(BODY_CALL_SYNTAXES)), generated_reference_body(rng=rng))
        for _ in range(test_case.count)
    ]
    python: list[object] = [
        python_reference_outcome(body=body, syntax=BODY_CALL_SYNTAXES[name]) for name, body in cases
    ]

    assert (
        mismatches(
            inputs=[*cases],
            expected=python,
            actual=[
                native_reference_outcome(body=body, syntax=BODY_CALL_SYNTAXES[name])
                for name, body in cases
            ],
        ),
        python.count("malformed calls True") >= test_case.expected_minimum_calls,
    ) == ([], True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
