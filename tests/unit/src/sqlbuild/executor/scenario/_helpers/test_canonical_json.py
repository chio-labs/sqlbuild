"""Tests for the canonical JSON text scenario comparisons use for VARIANT and JSON values."""

from __future__ import annotations

import pytest

from sqlbuild.executor.scenario._helpers.lifecycle.canonical_json import canonical_json
from tests.unit.src.sqlbuild.executor.scenario._helpers._test_types import CanonicalJsonTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CanonicalJsonTestCase(
            description="pretty-printed keys in another order",
            text='{\n  "qty": 2,\n  "note": "x"\n}',
            expected_canonical='{"note":"x","qty":2}',
        ),
        CanonicalJsonTestCase(
            description="nested objects are sorted and arrays keep their order",
            text='{"b": [3, {"z": 1, "a": null}], "a": true}',
            expected_canonical='{"a":true,"b":[3,{"a":null,"z":1}]}',
        ),
        CanonicalJsonTestCase(
            description="integral numbers lose trailing zeros",
            text='{"a": 2.0, "b": 1E1}',
            expected_canonical='{"a":2,"b":10}',
        ),
        CanonicalJsonTestCase(
            description="fractional numbers keep exact digits",
            text="[2.50, 0.0000001]",
            expected_canonical="[2.5,0.0000001]",
        ),
        CanonicalJsonTestCase(
            description="strings stay strings and keep non-ASCII text",
            text='["2", "caf\\u00e9"]',
            expected_canonical='["2","café"]',
        ),
        CanonicalJsonTestCase(description="NULL stays NULL", text=None, expected_canonical=None),
    ],
    ids=lambda case: case.description,
)
def test_given_json_text_when_canonicalising_then_equal_values_share_one_text(
    test_case: CanonicalJsonTestCase,
) -> None:
    assert canonical_json(test_case.text) == test_case.expected_canonical
