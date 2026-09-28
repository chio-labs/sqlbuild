"""Static import verification over the fingerprinted custom-rule closure."""

from pathlib import Path

import pytest

from sqlbuild.rule_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.rule_engine.exceptions import NonHermeticRuleError
from sqlbuild.rule_engine.models import Rule
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    CustomRuleImportTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import custom_rules_with_imports


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleImportTestCase(
            description="pure deterministic stdlib modules are allowed",
            module_import=(
                "import abc, bisect, copy, difflib, fnmatch, fractions, hashlib, heapq, json\n"
                "import operator, string, textwrap, types, unicodedata"
            ),
        ),
        CustomRuleImportTestCase(
            description="helper names shared with filesystem calls are not banned",
            module_import="from rules.order_paths import exists, glob",
            extra_files=(
                (
                    "rules/order_paths.py",
                    "import re\n\n\ndef exists(name: str) -> bool:\n"
                    "    return re.compile('^orders').match(name) is not None\n\n\n"
                    "def glob(names: tuple[str, ...]) -> tuple[str, ...]:\n"
                    "    return tuple(name for name in names if exists(name))\n",
                ),
            ),
        ),
        CustomRuleImportTestCase(
            description="rules file outside the import closure is not checked",
            module_import="",
            extra_files=(("rules/scratch/test_orders.py", "import subprocess\nimport time\n"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_closure_with_allowed_imports_when_verifying_then_accepts_rule(
    tmp_path: Path, test_case: CustomRuleImportTestCase
) -> None:
    rules: tuple[Rule, ...] = custom_rules_with_imports(
        project_dir=tmp_path,
        module_import=test_case.module_import,
        extra_files=test_case.extra_files,
    )

    verify_custom_rules(rules=rules, project_dir=tmp_path)

    assert tuple(rule.code for rule in rules) == test_case.expected_rule_codes


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleImportTestCase(
            description="time stays excluded",
            module_import="import time",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'time' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="datetime stays excluded",
            module_import="import datetime",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'datetime' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="random stays excluded",
            module_import="import random",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'random' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="uuid stays excluded",
            module_import="import uuid",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'uuid' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="secrets stays excluded",
            module_import="import secrets",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'secrets' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="os stays excluded",
            module_import="import os",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'os' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="sys stays excluded",
            module_import="import sys",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'sys' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="subprocess stays excluded",
            module_import="import subprocess",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'subprocess' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="socket stays excluded",
            module_import="import socket",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'socket' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="importlib stays excluded",
            module_import="import importlib",
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/custom.py:2: import 'importlib' is not allowed"
            ),
        ),
        CustomRuleImportTestCase(
            description="second name of a relative multi-name import is checked",
            module_import="from . import order_names, order_clock",
            extra_files=(
                ("rules/order_names.py", "NAMES = ('orders',)\n"),
                ("rules/order_clock.py", "import time\n"),
            ),
            expected_error_pattern=r"non-hermetic custom rule at .*rules/order_clock.py:1: import 'time' is not allowed",
        ),
        CustomRuleImportTestCase(
            description="relative submodule of a helper package is checked",
            module_import="from .order_pkg import clock",
            extra_files=(
                ("rules/order_pkg/__init__.py", ""),
                ("rules/order_pkg/clock.py", "import time\n"),
            ),
            expected_error_pattern=r"non-hermetic custom rule at .*rules/order_pkg/clock.py:1: import 'time' is not allowed",
        ),
        CustomRuleImportTestCase(
            description="helper package initializer is checked",
            module_import="from .order_pkg import clock",
            extra_files=(
                ("rules/order_pkg/__init__.py", "import random\n"),
                ("rules/order_pkg/clock.py", "VALUE = 1\n"),
            ),
            expected_error_pattern=r"non-hermetic custom rule at .*rules/order_pkg/__init__.py:1: import 'random' is not allowed",
        ),
        CustomRuleImportTestCase(
            description="second absolute module of a multi-name import is checked",
            module_import="import rules.order_names, rules.order_clock",
            extra_files=(
                ("rules/order_names.py", "NAMES = ('orders',)\n"),
                ("rules/order_clock.py", "import time\n"),
            ),
            expected_error_pattern=r"non-hermetic custom rule at .*rules/order_clock.py:1: import 'time' is not allowed",
        ),
        CustomRuleImportTestCase(
            description="function-local helper import is checked",
            module_import="from rules.order_names import names",
            extra_files=(
                (
                    "rules/order_names.py",
                    "def names() -> tuple[str, ...]:\n    from rules import order_clock\n\n    return order_clock.NAMES\n",
                ),
                ("rules/order_clock.py", "import uuid\n\nNAMES = ('orders',)\n"),
            ),
            expected_error_pattern=r"non-hermetic custom rule at .*rules/order_clock.py:1: import 'uuid' is not allowed",
        ),
        CustomRuleImportTestCase(
            description="imported helper in the closure is checked",
            module_import="from rules.order_clock import today",
            extra_files=(
                (
                    "rules/order_clock.py",
                    "def today() -> str:\n    import datetime\n\n"
                    "    return datetime.date.today().isoformat()\n",
                ),
            ),
            expected_error_pattern=(
                r"non-hermetic custom rule at .*rules/order_clock.py:2: "
                r"import 'datetime' is not allowed"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_closure_with_disallowed_import_when_verifying_then_raises_location(
    tmp_path: Path, test_case: CustomRuleImportTestCase
) -> None:
    rules: tuple[Rule, ...] = custom_rules_with_imports(
        project_dir=tmp_path,
        module_import=test_case.module_import,
        extra_files=test_case.extra_files,
    )

    with pytest.raises(NonHermeticRuleError, match=test_case.expected_error_pattern):
        verify_custom_rules(rules=rules, project_dir=tmp_path)
