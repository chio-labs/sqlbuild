from __future__ import annotations

import sys
import time
import unicodedata

import pytest

from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.models import MacroCallScan
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
def test_given_deeply_nested_calls_when_scanning_then_the_bridge_returns_promptly(
    test_case: DeepNestingScanTestCase,
) -> None:
    bridge: MacroBridge = MacroBridge(
        python_version=(sys.version_info[0], sys.version_info[1]),
        unicode_version=unicodedata.unidata_version,
    )
    sql: str = "@m(" * test_case.depth + "x" + ")" * test_case.depth
    started: float = time.perf_counter()

    scan: MacroCallScan = bridge.scan(sql)

    assert time.perf_counter() - started < test_case.expected_max_seconds
    assert (tuple(site.tree_names for site in scan.sites), scan.failure) == (
        test_case.expected_tree_names,
        None,
    )
