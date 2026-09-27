from __future__ import annotations

import pytest

from sqlbuild.rule_engine.main.render_skipped_rules import format_skipped_type_proof_rules
from tests.unit.src.sqlbuild.rule_engine.main.render_skipped_rules._test_types import (
    SkippedTypeProofRulesNoteTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SkippedTypeProofRulesNoteTestCase(
            description="skipped rules produce one note",
            codes=("SQBRCONTRACT105",),
            expected_note=(
                "skipped type-proof rules (SQBRCONTRACT105) because SQL analysis is disabled"
            ),
        ),
        SkippedTypeProofRulesNoteTestCase(
            description="no skipped rules produce no note",
            codes=(),
            expected_note=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_skipped_type_proof_rules_when_formatting_note_then_names_skipped_codes(
    test_case: SkippedTypeProofRulesNoteTestCase,
) -> None:
    assert format_skipped_type_proof_rules(codes=test_case.codes) == test_case.expected_note
