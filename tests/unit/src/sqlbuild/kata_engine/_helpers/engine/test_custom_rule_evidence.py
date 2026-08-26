"""Custom-rule evidence association and fingerprint tests."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue
from sqlbuild.kata_engine._helpers.engine.custom_rule_evidence import (
    _RuleTestEvidence,
    custom_rule_implementation_fingerprint,
    custom_rule_test_evidence,
)
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataConfig, KataResult, KataRule
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    CustomRuleEvidenceTestCase,
    CustomRuleTestCase,
)
from tests.unit.src.sqlbuild.kata_engine._helpers.engine.helpers import (
    custom_rule_inputs,
    load_custom_rule,
    write_rule,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleEvidenceTestCase(
            description="exact imported rule with static parametrized wrappers",
            test_source="""from dataclasses import dataclass

import pytest as pt

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check


@dataclass(frozen=True)
class Wrapper:
    rule_case: RuleCase


CASES = [
    Wrapper(rule_case=RuleCase(description="one", source="", expected_fault_count=0)),
    Wrapper(rule_case=RuleCase(description="two", source="", expected_fault_count=0)),
]

@pt.mark.parametrize("test_case", CASES)
def test_exact(test_case):
    evaluate_rule(rule=check, test_case=test_case.rule_case)
""",
            expected_count=2,
        ),
        CustomRuleEvidenceTestCase(
            description="undefined wrapper constructor is rejected",
            test_source="""import pytest

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

CASES = [
    MissingWrapper(
        rule_case=RuleCase(description="missing", source="", expected_fault_count=0)
    )
]

@pytest.mark.parametrize("test_case", CASES)
def test_exact(test_case):
    evaluate_rule(rule=check, test_case=test_case.rule_case)
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="unimported pytest spelling is rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

CASES = [RuleCase(description="one", source="", expected_fault_count=0)]

@pytest.mark.parametrize("test_case", CASES)
def test_exact(test_case):
    evaluate_rule(rule=check, test_case=test_case)
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="method directly under Test class counts",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

class TestEvidence:
    def test_exact(self):
        evaluate_rule(
            rule=check,
            test_case=RuleCase(description="method", source="", expected_fault_count=0),
        )
""",
            expected_count=1,
        ),
        CustomRuleEvidenceTestCase(
            description="method under non-Test class is rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

class Evidence:
    def test_exact(self):
        evaluate_rule(
            rule=check,
            test_case=RuleCase(description="method", source="", expected_fault_count=0),
        )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="nested test function is rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

def outer():
    def test_exact():
        evaluate_rule(
            rule=check,
            test_case=RuleCase(description="nested", source="", expected_fault_count=0),
        )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="statically skipped function is rejected",
            test_source="""import pytest as pt

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

@pt.mark.skip(reason="not evidence")
def test_exact():
    evaluate_rule(
        rule=check,
        test_case=RuleCase(description="skipped", source="", expected_fault_count=0),
    )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="statically skipped Test class is rejected",
            test_source="""import pytest

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

@pytest.mark.skip(reason="not evidence")
class TestEvidence:
    def test_exact(self):
        evaluate_rule(
            rule=check,
            test_case=RuleCase(description="skipped", source="", expected_fault_count=0),
        )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="statically true skipif is rejected",
            test_source="""import pytest

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

@pytest.mark.skipif(True, reason="not evidence")
def test_exact():
    evaluate_rule(
        rule=check,
        test_case=RuleCase(description="skipped", source="", expected_fault_count=0),
    )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="statically false skipif remains evidence",
            test_source="""import pytest

from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

@pytest.mark.skipif(False, reason="still evidence")
def test_exact():
    evaluate_rule(
        rule=check,
        test_case=RuleCase(description="active", source="", expected_fault_count=0),
    )
""",
            expected_count=1,
        ),
        CustomRuleEvidenceTestCase(
            description="runtime aliases are not static associations",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

def test_dynamic():
    selected_rule = check
    selected_case = RuleCase(description="dynamic", files=())
    evaluate_rule(rule=selected_rule, test_case=selected_case)
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="same check name from unrelated module is rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from other.rules import check

def test_unrelated():
    evaluate_rule(rule=check, test_case=RuleCase(description="unrelated", files=()))
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="standalone and statically dead cases are rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

UNUSED = RuleCase(description="unused", files=())
evaluate_rule(rule=check, test_case=UNUSED)

def test_dead():
    if False:
        evaluate_rule(
            rule=check,
            test_case=RuleCase(description="dead", files=()),
        )
""",
            expected_count=0,
        ),
        CustomRuleEvidenceTestCase(
            description="test function in non-test module is rejected",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

def test_not_collected():
    evaluate_rule(rule=check, test_case=RuleCase(description="hidden", files=()))
""",
            expected_count=0,
            test_path="tests/helper.py",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rule_and_test_source_when_collecting_evidence_then_only_exact_static_cases_count(
    tmp_path: Path,
    test_case: CustomRuleEvidenceTestCase,
) -> None:
    configured_path: Path = write_rule(root=tmp_path, body="del model\n    return []")
    test_path: Path = tmp_path / test_case.test_path
    test_path.parent.mkdir(parents=True)
    test_path.write_text(test_case.test_source, encoding="utf-8")
    rule: KataRule = load_custom_rule(root=tmp_path, configured_path=configured_path)

    evidence: tuple[_RuleTestEvidence, ...] = custom_rule_test_evidence(
        rule=rule, project_dir=tmp_path
    )

    assert len(evidence) == test_case.expected_count
    assert all(item.owner == "tests/test_custom.py:test_exact" for item in evidence)
    assert all(item.line > 0 and item.column > 0 for item in evidence)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleEvidenceTestCase(
            description="collectable evidence satisfies the custom-rule threshold",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

def test_exact():
    evaluate_rule(
        rule=check,
        test_case=RuleCase(description="exact", source="", expected_fault_count=0),
    )
""",
            expected_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_collectable_rule_evidence_when_evaluating_then_coverage_fault_clears(
    tmp_path: Path,
    test_case: CustomRuleEvidenceTestCase,
) -> None:
    project: CompiledProject
    config: KataConfig
    project, config = custom_rule_inputs(
        tmp_path=tmp_path,
        test_case=CustomRuleTestCase(
            description=test_case.description,
            body="del model\n    return []",
            require_cacheable=False,
            minimum_custom_rule_cases=1,
        ),
    )
    test_path: Path = tmp_path / "tests" / "test_custom.py"
    test_path.parent.mkdir()
    test_path.write_text(test_case.test_source, encoding="utf-8")

    result: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert len(result.faults) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleEvidenceTestCase(
            description="second load uses the new decorated owner",
            test_source="""from sqlbuild.kata import RuleCase, evaluate_rule
from kata.rules.custom import check

def test_exact():
    evaluate_rule(rule=check, test_case=RuleCase(description="exact", files=()))
""",
            expected_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rewritten_rule_when_loading_again_then_evidence_does_not_leak_between_loads(
    tmp_path: Path,
    test_case: CustomRuleEvidenceTestCase,
) -> None:
    configured_path: Path = write_rule(root=tmp_path, body="del model\n    return []")
    test_path: Path = tmp_path / "tests" / "test_custom.py"
    test_path.parent.mkdir()
    test_path.write_text(test_case.test_source, encoding="utf-8")
    first_rule: KataRule = load_custom_rule(root=tmp_path, configured_path=configured_path)
    assert len(custom_rule_test_evidence(rule=first_rule, project_dir=tmp_path)) == 1
    _ = write_rule(
        root=tmp_path,
        body="del model\n    return []",
        check_name="replacement_check",
    )

    second_rule: KataRule = load_custom_rule(root=tmp_path, configured_path=configured_path)

    assert len(custom_rule_test_evidence(rule=second_rule, project_dir=tmp_path)) == (
        test_case.expected_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleEvidenceTestCase(
            description="repository-owned helper content participates in fingerprint",
            test_source="VALUE = 1\n",
            expected_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_imported_helper_change_when_fingerprinting_then_fingerprint_changes(
    tmp_path: Path,
    test_case: CustomRuleEvidenceTestCase,
) -> None:
    configured_path: Path = write_rule(
        root=tmp_path,
        body="del model\n    return []",
        module_import="from kata.helpers import VALUE",
    )
    helper: Path = tmp_path / "kata" / "helpers.py"
    helper.write_text(test_case.test_source, encoding="utf-8")
    rule: KataRule = load_custom_rule(root=tmp_path, configured_path=configured_path)
    before: str = custom_rule_implementation_fingerprint(rule=rule, project_dir=tmp_path)
    helper.write_text("VALUE = 2\n", encoding="utf-8")

    after: str = custom_rule_implementation_fingerprint(rule=rule, project_dir=tmp_path)

    assert int(before != after) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleEvidenceTestCase(
            description="duplicate code from separate source files",
            test_source="duplicate kata rule codes: XSQBKT001",
            expected_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_source_codes_when_building_catalogue_then_rejects_duplicates(
    tmp_path: Path,
    test_case: CustomRuleEvidenceTestCase,
) -> None:
    _ = write_rule(root=tmp_path, body="del model\n    return []", filename="first.py")
    _ = write_rule(
        root=tmp_path,
        body="del model\n    return []",
        filename="second.py",
        check_name="second_check",
    )
    config: KataConfig = KataConfig(rule_paths=("kata/rules",))

    with pytest.raises(KataError, match=test_case.test_source) as raised:
        build_catalogue(config=config, project_dir=tmp_path)
    assert str(raised.value).count("XSQBKT001") == test_case.expected_count
