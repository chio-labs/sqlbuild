"""Config text read as Python reads it: containers by `str()`, errors raised as Python raises them."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.model_config._test_types import (
    OpaqueReadsTestCase,
    TemplateTextTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_config.helpers import (
    MARKER,
    Exploding,
    ExplodingText,
    opaque_reads,
    templated_alias,
)

_SAME_ALIAS: str = "${if(eq(given, expected), 'same', 'different')}"


@pytest.mark.parametrize(
    "test_case",
    [
        TemplateTextTestCase(
            description="a list holding a format character compares as Python prints it",
            header={"alias": _SAME_ALIAS},
            cli_vars={"given": ["\u200b\u00ad"], "expected": "['\\u200b\\xad']"},
            expected_outcome=("alias", "same"),
        ),
        TemplateTextTestCase(
            description="a list holding an opaque object compares by the object's repr",
            header={"alias": _SAME_ALIAS},
            cli_vars={"given": [MARKER], "expected": "[Marker()]"},
            expected_outcome=("alias", "same"),
        ),
        TemplateTextTestCase(
            description="a list whose item cannot be printed raises the item's error",
            header={"alias": _SAME_ALIAS},
            cli_vars={"given": [Exploding()], "expected": "x"},
            expected_outcome=("ValueError", "no repr"),
        ),
        TemplateTextTestCase(
            description="a tag union over an item that cannot be printed raises its error",
            header={"tags": ["daily", ExplodingText("weekly")]},
            cli_vars={},
            expected_outcome=("ValueError", "no str"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_scalar_values_when_building_config_then_text_and_errors_match_python(
    test_case: TemplateTextTestCase, tmp_path: Path
) -> None:
    outcome: tuple[str, str] = templated_alias(
        project_dir=tmp_path / "orders", header=test_case.header, cli_vars=test_case.cli_vars
    )

    assert outcome == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        OpaqueReadsTestCase(
            description="an opaque value under a str-enum key beside a templated alias",
            expected_reads=(True, ("str",)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_value_when_building_config_then_only_the_config_facts_read_its_text(
    test_case: OpaqueReadsTestCase, tmp_path: Path
) -> None:
    reads: tuple[bool, tuple[str, ...]] = opaque_reads(project_dir=tmp_path / "orders")

    assert reads == test_case.expected_reads
