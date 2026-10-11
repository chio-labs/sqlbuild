"""Every discovered input kind is either checked by P010 or explicitly exempt."""

from __future__ import annotations

from dataclasses import fields

import pytest

from sqlbuild.compiler.compile.constants import (
    DESCRIPTION_EXEMPT_INPUTS,
    DESCRIPTION_REQUIRED_INPUT_KINDS,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    DescriptionInputClassificationCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DescriptionInputClassificationCase(
            description="every discovered input field is required or exempt",
            required=frozenset(DESCRIPTION_REQUIRED_INPUT_KINDS),
            exempt=frozenset(DESCRIPTION_EXEMPT_INPUTS),
            expected_fields=frozenset(item.name for item in fields(DiscoveredProjectInputs)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_input_fields_when_classifying_then_every_field_is_checked_or_exempt(
    test_case: DescriptionInputClassificationCase,
) -> None:
    assert not test_case.required & test_case.exempt
    assert test_case.required | test_case.exempt == test_case.expected_fields


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
