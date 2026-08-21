"""Unit tests for sqlbuild interpolation neutralization and restoration."""

from __future__ import annotations

import pytest

from sqlbuild.lint._helpers.sqlbuild_tokens import (
    map_neutralized_offset,
    neutralize_interpolation,
    restore_interpolation,
)
from sqlbuild.lint.exceptions import InterpolationRestorationError
from sqlbuild.lint.models import InterpolationSite
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    MapOffsetTestCase,
    NeutralizeInterpolationTestCase,
    RestoreFailureTestCase,
    RestoreInterpolationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NeutralizeInterpolationTestCase(
            description="bare audit parameter becomes a sentinel",
            body="SELECT * FROM t WHERE NOT (@expression)",
            expected_neutralized="SELECT * FROM t WHERE NOT (__sqb_lint_0__)",
            expected_original_texts=("@expression",),
        ),
        NeutralizeInterpolationTestCase(
            description="macro call including arguments becomes one sentinel",
            body="SELECT @cents_to_dollars(amount_cents) AS amount",
            expected_neutralized="SELECT __sqb_lint_0__ AS amount",
            expected_original_texts=("@cents_to_dollars(amount_cents)",),
        ),
        NeutralizeInterpolationTestCase(
            description="macro call with python valued arguments becomes one sentinel",
            body="SELECT @pick(columns=['a', 'b']) AS chosen",
            expected_neutralized="SELECT __sqb_lint_0__ AS chosen",
            expected_original_texts=("@pick(columns=['a', 'b'])",),
        ),
        NeutralizeInterpolationTestCase(
            description="nested macro parentheses are matched",
            body="SELECT @outer(@inner(x), y) AS v",
            expected_neutralized="SELECT __sqb_lint_0__ AS v",
            expected_original_texts=("@outer(@inner(x), y)",),
        ),
        NeutralizeInterpolationTestCase(
            description="quoted audit parameter becomes a sentinel",
            body="SELECT @'column_name' AS c",
            expected_neutralized="SELECT __sqb_lint_0__ AS c",
            expected_original_texts=("@'column_name'",),
        ),
        NeutralizeInterpolationTestCase(
            description="project variable interpolation becomes a sentinel",
            body="SELECT * FROM @@source_table",
            expected_neutralized="SELECT * FROM __sqb_lint_0__",
            expected_original_texts=("@@source_table",),
        ),
        NeutralizeInterpolationTestCase(
            description="environment interpolation becomes a sentinel",
            body="SELECT * FROM @@ENV:TARGET_TABLE",
            expected_neutralized="SELECT * FROM __sqb_lint_0__",
            expected_original_texts=("@@ENV:TARGET_TABLE",),
        ),
        NeutralizeInterpolationTestCase(
            description="context interpolation becomes a sentinel",
            body="SELECT @@CTX:run_id AS run",
            expected_neutralized="SELECT __sqb_lint_0__ AS run",
            expected_original_texts=("@@CTX:run_id",),
        ),
        NeutralizeInterpolationTestCase(
            description="template expression becomes a sentinel",
            body="SELECT ${if(eq(a, b), x, y)} AS v",
            expected_neutralized="SELECT __sqb_lint_0__ AS v",
            expected_original_texts=("${if(eq(a, b), x, y)}",),
        ),
        NeutralizeInterpolationTestCase(
            description="each site receives a distinct sentinel",
            body="SELECT @a, @a FROM t",
            expected_neutralized="SELECT __sqb_lint_0__, __sqb_lint_1__ FROM t",
            expected_original_texts=("@a", "@a"),
        ),
        NeutralizeInterpolationTestCase(
            description="interpolation inside a string literal is left alone",
            body="SELECT '@not_a_macro' AS c",
            expected_neutralized="SELECT '@not_a_macro' AS c",
            expected_original_texts=(),
        ),
        NeutralizeInterpolationTestCase(
            description="quoted reference marker is left alone",
            body='SELECT * FROM __ref("@model")',
            expected_neutralized='SELECT * FROM __ref("@model")',
            expected_original_texts=(),
        ),
        NeutralizeInterpolationTestCase(
            description="body without interpolation is unchanged",
            body="SELECT 1 AS x FROM t",
            expected_neutralized="SELECT 1 AS x FROM t",
            expected_original_texts=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_body_when_neutralizing_then_sentinels_replace_interpolation(
    test_case: NeutralizeInterpolationTestCase,
) -> None:
    neutralized: str
    sites: tuple[InterpolationSite, ...]
    neutralized, sites = neutralize_interpolation(body=test_case.body)
    assert neutralized == test_case.expected_neutralized
    assert tuple(site.original_text for site in sites) == test_case.expected_original_texts


@pytest.mark.parametrize(
    "test_case",
    [
        NeutralizeInterpolationTestCase(
            description="sentinels are unique across sites",
            body="SELECT @a, @b, @@c, ${d} FROM t",
            expected_neutralized=(
                "SELECT __sqb_lint_0__, __sqb_lint_1__, __sqb_lint_2__, __sqb_lint_3__ FROM t"
            ),
            expected_original_texts=("@a", "@b", "@@c", "${d}"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_many_sites_when_neutralizing_then_every_sentinel_is_distinct(
    test_case: NeutralizeInterpolationTestCase,
) -> None:
    neutralized: str
    sites: tuple[InterpolationSite, ...]
    neutralized, sites = neutralize_interpolation(body=test_case.body)
    assert neutralized == test_case.expected_neutralized
    sentinels: tuple[str, ...] = tuple(site.sentinel for site in sites)
    assert len(set(sentinels)) == len(test_case.expected_original_texts)


@pytest.mark.parametrize(
    "test_case",
    [
        MapOffsetTestCase(
            description="offset before any site is unchanged",
            body="SELECT @a FROM t",
            neutralized_offset=0,
            expected_original_offset=0,
        ),
        MapOffsetTestCase(
            description="offset at a sentinel start maps to the interpolation start",
            body="SELECT @a FROM t",
            neutralized_offset=7,
            expected_original_offset=7,
        ),
        MapOffsetTestCase(
            description="offset inside a sentinel clamps to the interpolation start",
            body="SELECT @a FROM t",
            neutralized_offset=12,
            expected_original_offset=7,
        ),
        MapOffsetTestCase(
            description="offset after a sentinel is shifted back by the length delta",
            body="SELECT @a FROM t",
            neutralized_offset=22,
            expected_original_offset=10,
        ),
        MapOffsetTestCase(
            description="offset after two sentinels accumulates both deltas",
            body="SELECT @a, @b FROM t",
            neutralized_offset=39,
            expected_original_offset=15,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_neutralized_offset_when_mapping_then_authored_offset_matches(
    test_case: MapOffsetTestCase,
) -> None:
    sites: tuple[InterpolationSite, ...]
    _neutralized, sites = neutralize_interpolation(body=test_case.body)
    mapped: int = map_neutralized_offset(offset=test_case.neutralized_offset, sites=sites)
    assert mapped == test_case.expected_original_offset


@pytest.mark.parametrize(
    "test_case",
    [
        RestoreInterpolationTestCase(
            description="unchanged neutralized text round-trips to the original body",
            body="SELECT @cents_to_dollars(amount) AS a FROM t",
            fixed_neutralized="SELECT __sqb_lint_0__ AS a FROM t",
            expected_restored="SELECT @cents_to_dollars(amount) AS a FROM t",
        ),
        RestoreInterpolationTestCase(
            description="reformatted layout keeps interpolation intact",
            body="select @a as x,\n  @b from t",
            fixed_neutralized="SELECT\n    __sqb_lint_0__ AS x,\n    __sqb_lint_1__\nFROM t",
            expected_restored="SELECT\n    @a AS x,\n    @b\nFROM t",
        ),
        RestoreInterpolationTestCase(
            description="body without interpolation is returned unchanged",
            body="SELECT 1 AS x",
            fixed_neutralized="SELECT 1 AS x",
            expected_restored="SELECT 1 AS x",
        ),
        RestoreInterpolationTestCase(
            description="repeated identical interpolation restores both sites",
            body="SELECT @a, @a FROM t",
            fixed_neutralized="SELECT __sqb_lint_0__, __sqb_lint_1__ FROM t",
            expected_restored="SELECT @a, @a FROM t",
        ),
        RestoreInterpolationTestCase(
            description="real identifier matching the interpolation name is untouched",
            body="SELECT expression, @expression FROM t",
            fixed_neutralized="SELECT expression, __sqb_lint_0__ FROM t",
            expected_restored="SELECT expression, @expression FROM t",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fixed_text_when_restoring_then_original_interpolation_returns(
    test_case: RestoreInterpolationTestCase,
) -> None:
    sites: tuple[InterpolationSite, ...]
    _neutralized, sites = neutralize_interpolation(body=test_case.body)
    restored: str = restore_interpolation(fixed=test_case.fixed_neutralized, sites=sites)
    assert restored == test_case.expected_restored


@pytest.mark.parametrize(
    "test_case",
    [
        RestoreFailureTestCase(
            description="dropped sentinel fails instead of silently losing interpolation",
            body="SELECT @a FROM t",
            fixed_neutralized="SELECT FROM t",
            expected_message_fragment="contains 0 occurrences",
        ),
        RestoreFailureTestCase(
            description="duplicated sentinel fails instead of duplicating interpolation",
            body="SELECT @a FROM t",
            fixed_neutralized="SELECT __sqb_lint_0__, __sqb_lint_0__ FROM t",
            expected_message_fragment="contains 2 occurrences",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mangled_sentinels_when_restoring_then_error_is_raised(
    test_case: RestoreFailureTestCase,
) -> None:
    sites: tuple[InterpolationSite, ...]
    _neutralized, sites = neutralize_interpolation(body=test_case.body)
    with pytest.raises(InterpolationRestorationError) as error:
        _ = restore_interpolation(fixed=test_case.fixed_neutralized, sites=sites)
    assert test_case.expected_message_fragment in str(error.value)
