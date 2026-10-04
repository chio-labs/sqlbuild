"""Custom-rule module-state detection classifies every rule exactly as full re-fingerprinting."""

from itertools import chain
from pathlib import Path

import pytest

from tests.unit.src.sqlbuild.rule_engine._helpers.host._test_types import (
    ModuleStateCase,
    RandomModuleStateCase,
    StateDetectorCostCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.host.helpers import (
    FOREIGN_MODULE_CLASS_LIBRARY,
    IMPORT_ORDER_HELPERS,
    RAISING_PROXY_LIBRARY,
    SIDE_EFFECT_PROPERTY_LIBRARY,
    STATEFUL_RULE_CODE,
    STATELESS_RULE_CODE,
    compare_state_detectors,
    monitor_detector,
    order_helpers_file,
    random_state_files,
    reference_detector,
    state_case_files,
    state_rule,
    stateless_rule_file,
    timed_state_history,
)

_STATEFUL: frozenset[str] = frozenset({STATEFUL_RULE_CODE})
_STATELESS: frozenset[str] = frozenset()
_ISOLATED_RULE: tuple[str, str] = (
    "rules/isolated.py",
    state_rule(code="XSQBRST902", body="_ = model.name"),
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModuleStateCase(
            description="stateless constant tables",
            files=state_case_files(
                header=IMPORT_ORDER_HELPERS + "SIZES = {'small': 1}\nNAMES = ('orders', 'items')\n",
                body="_ = helpers.is_known(model.name) or SIZES.get(model.name) or NAMES",
            ),
            model_count=4,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="dict mutation",
            files=state_case_files(
                header="SEEN: dict[str, bool] = {}\n", body="SEEN[model.name] = True"
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="list append",
            files=state_case_files(header="ITEMS: list[int] = []\n", body="ITEMS.append(1)"),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="set add",
            files=state_case_files(
                header="MARKS: set[str] = set()\n", body="MARKS.add(model.name)"
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="list element replaced in place",
            files=state_case_files(header="ITEMS = ['orders', 1]\n", body="ITEMS[0] = model.name"),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="dict value replaced without resizing",
            files=state_case_files(
                header="LABELS = {'orders': 'Orders', 'customers': 2}\n",
                body="LABELS['orders'] = model.name",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="set member swapped without resizing",
            files=state_case_files(
                header="MARKS = {'orders', 'customers'}\n",
                body="MARKS.discard('orders')\nMARKS.add(model.name)",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="attribute on module-level object",
            files=state_case_files(
                header=(
                    "class Box:\n    def __init__(self) -> None:\n        self.value = ''\n\n\n"
                    "BOX = Box()\n"
                ),
                body="BOX.value = model.name",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="class attribute",
            files=state_case_files(
                header="class Totals:\n    count = 0\n", body="Totals.count += 1"
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="global counter rebinding",
            files=state_case_files(header="COUNTER = 0\n", body="globals()['COUNTER'] += 1"),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="rebinding a table to an equal copy",
            files=state_case_files(
                header="TABLE = {'orders': 1}\n", body="globals()['TABLE'] = dict(TABLE)"
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="mutate and restore within one call",
            files=state_case_files(
                header="ITEMS: list[int] = []\n", body="ITEMS.append(1)\nITEMS.pop()"
            ),
            model_count=4,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="mutate on one call and restore on the next",
            files=state_case_files(
                header="TOGGLE: list[int] = []\n",
                body="if TOGGLE:\n    TOGGLE.pop()\nelse:\n    TOGGLE.append(1)",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="lazily initialised cache",
            files=state_case_files(
                header="CACHE: dict[str, int] | None = None\n",
                body="if CACHE is None:\n    globals()['CACHE'] = {'orders': 1}",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="nested containers",
            files=state_case_files(
                header="NESTED = {'groups': [{'names': ['orders']}]}\n",
                body="NESTED['groups'][0]['names'].append(model.name)",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="cycle without mutation",
            files=state_case_files(
                header="LOOP: list[object] = []\nLOOP.append(LOOP)\n", body="_ = LOOP[0] is LOOP"
            ),
            model_count=4,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="mutation inside a cycle",
            files=state_case_files(
                header="LOOP: list[object] = []\nLOOP.append(LOOP)\n",
                body="LOOP[0].append(model.name)",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="closure cell",
            files=state_case_files(
                header=(
                    "def _counter():\n    total = 0\n\n    def bump() -> int:\n"
                    "        nonlocal total\n        total += 1\n        return total\n\n"
                    "    return bump\n\n\nBUMP = _counter()\n"
                ),
                body="_ = BUMP()",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="opaque lock state",
            files=state_case_files(
                header="import threading\n\nLOCK = threading.Lock()\n", body="_ = model.name"
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="state too large to observe",
            files=state_case_files(header="LARGE = list(range(60_000))\n", body="_ = model.name"),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="dataclass instance from the rules module",
            files=state_case_files(
                header=(
                    "from dataclasses import dataclass, field\n\n\n@dataclass\nclass Seen:\n"
                    "    names: list[str] = field(default_factory=list)\n\n\nSEEN = Seen()\n"
                ),
                body="SEEN.names.append(model.name)",
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="mutation after several stateless calls",
            files=state_case_files(
                header="LATE: list[str] = []\n",
                body="if model.index == 3:\n    LATE.append(model.name)",
            ),
            model_count=5,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="bytearray mutated in place",
            files=state_case_files(
                header="BUFFER = bytearray(b'orders')\n", body="BUFFER[0] = model.index"
            ),
            model_count=3,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="float signed zero",
            files=state_case_files(header="RATIO = 0.0\n", body="globals()['RATIO'] = -0.0"),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="mutation in a shared helper reaches every importing rule",
            files=(
                *state_case_files(
                    header=IMPORT_ORDER_HELPERS, body="helpers.SHARED[model.name] = 1"
                ),
                _ISOLATED_RULE,
            ),
            model_count=3,
            expected_stateful=frozenset({STATEFUL_RULE_CODE, STATELESS_RULE_CODE}),
        ),
        ModuleStateCase(
            description="helper lru cache reaches every importing rule",
            files=(
                *state_case_files(
                    header=IMPORT_ORDER_HELPERS, body="_ = helpers.cached_length(model.name)"
                ),
                _ISOLATED_RULE,
            ),
            model_count=3,
            expected_stateful=frozenset({STATEFUL_RULE_CODE, STATELESS_RULE_CODE}),
        ),
        ModuleStateCase(
            description="helper class reached before its module is not observed",
            files=(
                order_helpers_file(),
                (
                    "rules/orders_state.py",
                    state_rule(
                        code=STATEFUL_RULE_CODE,
                        header=IMPORT_ORDER_HELPERS,
                        body="helpers.register(model.name)",
                    ),
                ),
                (
                    "rules/registry_reader.py",
                    state_rule(
                        code="XSQBRST903",
                        header="from rules.helpers import Registry\n" + IMPORT_ORDER_HELPERS,
                        body="_ = Registry.entries or helpers.REGION_CODES",
                    ),
                ),
            ),
            model_count=4,
            expected_stateful=_STATEFUL,
        ),
        ModuleStateCase(
            description="helper class with a raising proxy reached before its module",
            files=(
                ("rules/lib.py", RAISING_PROXY_LIBRARY),
                (
                    "rules/a.py",
                    state_rule(
                        code="XSQBRST905",
                        header="from rules.lib import Helper, helper_fn\n",
                        body="_ = helper_fn() and Helper",
                    ),
                ),
            ),
            model_count=3,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="side-effecting property in a class no fingerprint descends into",
            files=(
                ("rules/lazy.py", SIDE_EFFECT_PROPERTY_LIBRARY),
                (
                    "rules/a.py",
                    state_rule(
                        code="XSQBRST906",
                        header="from rules.lazy import Holder, lazy_fn\n",
                        body="_ = lazy_fn() or Holder",
                    ),
                ),
            ),
            model_count=3,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="class from another rule's module that its namespace does not hold",
            files=(
                ("rules/parts.py", FOREIGN_MODULE_CLASS_LIBRARY),
                (
                    "rules/cross_a.py",
                    state_rule(
                        code="XSQBRST907",
                        header="from rules.parts import Hidden\n",
                        body="_ = Hidden.__name__",
                    ),
                ),
                ("rules/cross_b.py", state_rule(code="XSQBRST908", body="_ = model.name")),
            ),
            model_count=3,
            expected_stateful=_STATELESS,
        ),
        ModuleStateCase(
            description="two rules in one module share their classification",
            files=(
                order_helpers_file(),
                (
                    "rules/orders_state.py",
                    state_rule(
                        code=STATEFUL_RULE_CODE,
                        header="SEEN: list[str] = []\n",
                        body="SEEN.append(model.name)",
                    )
                    + state_rule(code="XSQBRST904", body="_ = model.name", function="second"),
                ),
                stateless_rule_file(),
            ),
            model_count=3,
            expected_stateful=frozenset({STATEFUL_RULE_CODE, "XSQBRST904"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rule_module_state_when_monitoring_then_matches_full_refingerprinting(
    tmp_path: Path, test_case: ModuleStateCase
) -> None:
    expected, observed = compare_state_detectors(
        root=tmp_path, files=test_case.files, model_count=test_case.model_count
    )

    assert observed == expected
    assert frozenset(chain.from_iterable(observed)) == test_case.expected_stateful


@pytest.mark.parametrize(
    "test_case",
    [
        RandomModuleStateCase(description=f"seed {seed}", seed=seed, model_count=6)
        for seed in range(40)
    ],
    ids=lambda case: case.description,
)
def test_given_random_rule_mutations_when_monitoring_then_matches_full_refingerprinting(
    tmp_path: Path, test_case: RandomModuleStateCase
) -> None:
    expected, observed = compare_state_detectors(
        root=tmp_path,
        files=random_state_files(seed=test_case.seed, model_count=test_case.model_count),
        model_count=test_case.model_count,
    )

    assert (observed == expected) is test_case.expected_matches_reference


@pytest.mark.parametrize(
    "test_case",
    [
        StateDetectorCostCase(
            description="twelve stateless rules sharing helper tables",
            rule_count=12,
            model_count=25,
            expected_min_speedup=4.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rules_sharing_helper_tables_when_monitoring_then_cheaper_than_refingerprinting(
    tmp_path: Path, test_case: StateDetectorCostCase
) -> None:
    files: tuple[tuple[str, str], ...] = (
        order_helpers_file(),
        *(stateless_rule_file(code=f"XSQBRSP{index:03d}") for index in range(test_case.rule_count)),
    )

    reference_seconds, reference_history = timed_state_history(
        root=tmp_path / "reference",
        files=files,
        model_count=test_case.model_count,
        detector=reference_detector,
    )
    monitor_seconds, monitor_history = timed_state_history(
        root=tmp_path / "monitor",
        files=files,
        model_count=test_case.model_count,
        detector=monitor_detector,
    )

    assert monitor_history == reference_history
    assert not any(monitor_history)
    assert monitor_seconds * test_case.expected_min_speedup < reference_seconds
