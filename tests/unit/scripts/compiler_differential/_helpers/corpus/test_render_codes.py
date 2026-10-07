"""Every inline diagnostic code in render-stage compile modules is required or documented."""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild.compiler.compile as compile_package
from scripts.compiler_differential._helpers.corpus.emitted_codes import (
    inline_compile_codes,
    render_error_codes,
    unaccounted_inline_codes,
)
from scripts.compiler_differential.constants import RENDER_UNREACHABLE_CODES
from tests.unit.scripts.compiler_differential._helpers.corpus._test_types import (
    InlineCompileCodesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        InlineCompileCodesTestCase(
            description="compile_package",
            compile_root=Path(compile_package.__file__).parent,
            accounted_codes=render_error_codes() | frozenset(RENDER_UNREACHABLE_CODES),
            expected_unaccounted={},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compile_modules_when_scanning_inline_codes_then_each_is_required_or_unreachable(
    test_case: InlineCompileCodesTestCase,
) -> None:
    unaccounted: dict[str, tuple[str, ...]] = unaccounted_inline_codes(
        compile_root=test_case.compile_root, accounted=test_case.accounted_codes
    )

    assert inline_compile_codes(test_case.compile_root)
    assert unaccounted == test_case.expected_unaccounted


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
