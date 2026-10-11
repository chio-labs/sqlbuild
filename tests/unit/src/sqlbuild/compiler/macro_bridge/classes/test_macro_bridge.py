from __future__ import annotations

import sys
import time
import unicodedata

import pytest

import sqlbuild._native as _native
from tests.unit.src.sqlbuild.compiler.macro_bridge.classes._test_types import (
    DeepNestingScanTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeepNestingScanTestCase(
            description="one thousand levels",
            depth=1_000,
            expected_tree_names=(("m",),),
            expected_max_seconds=2.0,
        ),
        DeepNestingScanTestCase(
            description="twenty thousand levels",
            depth=20_000,
            expected_tree_names=(("m",),),
            expected_max_seconds=2.0,
        ),
        DeepNestingScanTestCase(
            description="one hundred thousand levels",
            depth=100_000,
            expected_tree_names=(("m",),),
            expected_max_seconds=2.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deeply_nested_calls_when_scanning_then_the_native_scan_returns_promptly(
    test_case: DeepNestingScanTestCase,
) -> None:
    sql: str = "@m(" * test_case.depth + "x" + ")" * test_case.depth
    started: float = time.perf_counter()

    rows, failure = _native.scan_macro_call_sites(
        sql, (sys.version_info[0], sys.version_info[1]), unicodedata.unidata_version
    )

    assert time.perf_counter() - started < test_case.expected_max_seconds
    assert (tuple(tuple(row[4] or ()) for row in rows), failure) == (
        test_case.expected_tree_names,
        None,
    )
