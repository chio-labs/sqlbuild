"""Compare the native JSON emitter with Python's serializers on seeded generated values."""

from __future__ import annotations

import random

import orjson
import pytest

from tests.integration.src.sqlbuild.compiler._test_types import (
    JsonOracleTestCase,
    OrjsonFloatLayoutTestCase,
)
from tests.integration.src.sqlbuild.compiler.helpers import (
    MAX_JSON_DEPTH,
    mismatches,
    native_json_text,
    python_json_text,
    random_json_value,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JsonOracleTestCase(
            description="json.dumps defaults", serializer="stdlib", seed=11, case_count=1500
        ),
        JsonOracleTestCase(
            description="json.dumps indent=2 for manifests and DAG output",
            serializer="stdlib",
            seed=12,
            case_count=1500,
            indent=2,
        ),
        JsonOracleTestCase(
            description="json.dumps compact sorted ASCII for identities and caches",
            serializer="stdlib",
            seed=13,
            case_count=1500,
            separators=(",", ":"),
            sort_keys=True,
        ),
        JsonOracleTestCase(
            description="json.dumps Unicode sorted with indent",
            serializer="stdlib",
            seed=14,
            case_count=1500,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        JsonOracleTestCase(
            description="json.dumps tab indent with custom separators",
            serializer="stdlib",
            seed=15,
            case_count=1500,
            indent="\t",
            separators=(", ", " = "),
        ),
        JsonOracleTestCase(
            description="json.dumps allow_nan=False rejects non-finite floats",
            serializer="stdlib",
            seed=16,
            case_count=1500,
            separators=(",", ":"),
            allow_nan=False,
        ),
        JsonOracleTestCase(
            description="orjson defaults", serializer="orjson", seed=21, case_count=1500
        ),
        JsonOracleTestCase(
            description="orjson OPT_INDENT_2 for the compile payload",
            serializer="orjson",
            seed=22,
            case_count=1500,
            orjson_option=orjson.OPT_INDENT_2,
        ),
        JsonOracleTestCase(
            description="orjson OPT_SORT_KEYS",
            serializer="orjson",
            seed=23,
            case_count=1500,
            orjson_option=orjson.OPT_SORT_KEYS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_values_when_dumping_natively_then_bytes_match_python_serializer(
    test_case: JsonOracleTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    values: list[object] = [
        random_json_value(rng=rng, depth=MAX_JSON_DEPTH) for _ in range(test_case.case_count)
    ]

    expected: list[object] = [
        python_json_text(value=value, test_case=test_case) for value in values
    ]
    actual: list[object] = [native_json_text(value=value, test_case=test_case) for value in values]

    assert mismatches(inputs=values, expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


@pytest.mark.parametrize(
    "test_case",
    [
        OrjsonFloatLayoutTestCase(
            description="positive exponents carry a plus sign from orjson 3.11.7",
            value=1e16,
            expected_text="1e+16",
        ),
        OrjsonFloatLayoutTestCase(
            description="large positive exponents carry a plus sign",
            value=1.5e300,
            expected_text="1.5e+300",
        ),
        OrjsonFloatLayoutTestCase(
            description="negative exponents keep their sign without padding",
            value=1e-6,
            expected_text="1e-6",
        ),
        OrjsonFloatLayoutTestCase(
            description="small floats stay fixed down to five decimal places",
            value=1e-5,
            expected_text="0.00001",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_installed_orjson_when_dumping_exponent_floats_then_text_matches_native_layout(
    test_case: OrjsonFloatLayoutTestCase,
) -> None:
    orjson_case: JsonOracleTestCase = JsonOracleTestCase(
        description=test_case.description, serializer="orjson", seed=0, case_count=1
    )

    installed: str = orjson.dumps(test_case.value).decode()
    native: str = native_json_text(value=test_case.value, test_case=orjson_case)

    assert (installed, native) == (test_case.expected_text, test_case.expected_text), (
        test_case.description
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
