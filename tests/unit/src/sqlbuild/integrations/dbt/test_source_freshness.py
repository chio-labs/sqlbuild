from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt._helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.main.runtime._source_freshness import (
    translate_dbt_manifest_sources_to_sqlbuild_sources,
)
from sqlbuild.integrations.dbt.models import DbtManifestIndex
from sqlbuild.spec.contracts.models import SourceEntry, SourceFreshnessConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtSourceFreshnessTranslationErrorTestCase,
    DbtSourceFreshnessTranslationTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_manifest_data,
    build_manifest_source_node,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DbtSourceFreshnessTranslationTestCase(
            description="plain loaded_at_field translates to column freshness with filter",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        database="warehouse",
                        schema="raw",
                        identifier="orders_table",
                        loaded_at_field="loaded_at",
                        freshness={
                            "warn_after": {"count": 12, "period": "hour"},
                            "error_after": {"count": 1, "period": "day"},
                        },
                        freshness_filter="loaded_at >= current_date - interval '7 days'",
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.orders",
            expected_strategy="column",
            expected_column="loaded_at",
            expected_filter="loaded_at >= current_date - interval '7 days'",
            expected_warn_after="12h",
            expected_error_after="1d",
            expected_table="orders_table",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="manifest freshness filter translates to column freshness filter",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.filtered_orders",
                        database="warehouse",
                        schema="raw",
                        identifier="filtered_orders_table",
                        loaded_at_field="loaded_at",
                        freshness={
                            "error_after": {"count": 1, "period": "day"},
                            "filter": "include_in_freshness",
                        },
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.filtered_orders",
            expected_strategy="column",
            expected_column="loaded_at",
            expected_filter="include_in_freshness",
            expected_error_after="1d",
            expected_table="filtered_orders_table",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="expression loaded_at_field translates to generated SQL with filter",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.events",
                        name="events",
                        relation_name='"warehouse"."raw"."events"',
                        loaded_at_field="coalesce(updated_at, created_at)",
                        freshness={"error_after": {"count": 30, "period": "minutes"}},
                        freshness_filter="created_at >= current_date - interval '1 day'",
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.events",
            expected_strategy="sql",
            expected_query=(
                "SELECT MAX(coalesce(updated_at, created_at)) AS data_version "
                'FROM "warehouse"."raw"."events" '
                "WHERE created_at >= current_date - interval '1 day'"
            ),
            expected_error_after="30m",
            expected_table="events",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="loaded_at_query translates to SQL freshness and ignores filter",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.payments",
                        name="payments",
                        loaded_at_query="SELECT MAX(_loaded_at) AS data_version FROM raw.payments",
                        freshness={"warn_after": {"count": 2, "period": "hours"}},
                        freshness_filter="_loaded_at > current_date",
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.payments",
            expected_strategy="sql",
            expected_query="SELECT MAX(_loaded_at) AS data_version FROM raw.payments",
            expected_warn_after="2h",
            expected_table="payments",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="freshness without loaded_at uses adapter metadata strategy",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.customers",
                        name="customers",
                        freshness={"error_after": {"count": 1, "period": "day"}},
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.customers",
            expected_strategy="adapter",
            expected_error_after="1d",
            expected_table="customers",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="plural day and minute durations translate to SQLBuild duration strings",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.shipments",
                        name="shipments",
                        loaded_at_field="loaded_at",
                        freshness={
                            "warn_after": {"count": 45, "period": "minutes"},
                            "error_after": {"count": 2, "period": "days"},
                        },
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.shipments",
            expected_strategy="column",
            expected_column="loaded_at",
            expected_warn_after="45m",
            expected_error_after="2d",
            expected_table="shipments",
        ),
        DbtSourceFreshnessTranslationTestCase(
            description="singular minute and plural hour durations translate to SQLBuild strings",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.invoices",
                        name="invoices",
                        loaded_at_field="loaded_at",
                        freshness={
                            "warn_after": {"count": 1, "period": "minute"},
                            "error_after": {"count": 3, "period": "hours"},
                        },
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.invoices",
            expected_strategy="column",
            expected_column="loaded_at",
            expected_warn_after="1m",
            expected_error_after="3h",
            expected_table="invoices",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dbt_manifest_sources_when_translating_then_returns_sqlbuild_sources(
    test_case: DbtSourceFreshnessTranslationTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    sources: tuple[SourceEntry, ...] = translate_dbt_manifest_sources_to_sqlbuild_sources(
        manifest=manifest
    )

    assert len(sources) == 1
    source: SourceEntry = sources[0]
    assert source.name == test_case.expected_source_name
    assert source.table == test_case.expected_table
    freshness: SourceFreshnessConfig | None = source.freshness
    assert freshness is not None
    assert freshness.strategy == test_case.expected_strategy
    assert freshness.value_kind == "timestamp"
    assert freshness.column == test_case.expected_column
    assert freshness.query == test_case.expected_query
    assert freshness.filter == test_case.expected_filter
    assert freshness.age_policy is not None
    assert freshness.age_policy.warn_after == test_case.expected_warn_after
    assert freshness.age_policy.error_after == test_case.expected_error_after


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSourceFreshnessTranslationTestCase(
            description="freshness null leaves source without SQLBuild freshness config",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.disabled_source",
                        name="disabled_source",
                        loaded_at_field="loaded_at",
                        freshness=None,
                    ),
                ),
            ),
            expected_source_name="source.analytics.raw.disabled_source",
            expected_strategy=None,
            expected_table="disabled_source",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_manifest_source_without_freshness_when_translating_then_returns_source(
    test_case: DbtSourceFreshnessTranslationTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    sources: tuple[SourceEntry, ...] = translate_dbt_manifest_sources_to_sqlbuild_sources(
        manifest=manifest
    )

    assert len(sources) == 1
    assert sources[0].name == test_case.expected_source_name
    assert sources[0].table == test_case.expected_table
    assert sources[0].freshness is None


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSourceFreshnessTranslationTestCase(
            description="multiple manifest sources translate in stable unique id order",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.z_orders",
                        name="z_orders",
                        freshness={"error_after": {"count": 1, "period": "day"}},
                    ),
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.a_orders",
                        name="a_orders",
                        freshness={"error_after": {"count": 1, "period": "day"}},
                    ),
                ),
            ),
            expected_source_name="",
            expected_strategy=None,
            expected_source_names=(
                "source.analytics.raw.a_orders",
                "source.analytics.raw.z_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_dbt_manifest_sources_when_translating_then_returns_stable_order(
    test_case: DbtSourceFreshnessTranslationTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    sources: tuple[SourceEntry, ...] = translate_dbt_manifest_sources_to_sqlbuild_sources(
        manifest=manifest
    )

    assert tuple(source.name for source in sources) == test_case.expected_source_names


@pytest.mark.parametrize(
    "test_case",
    (
        DbtSourceFreshnessTranslationErrorTestCase(
            description="missing duration count fails clearly",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        loaded_at_field="loaded_at",
                        freshness={"error_after": {"period": "day"}},
                    ),
                ),
            ),
            expected_error_fragment="must include positive count and period",
        ),
        DbtSourceFreshnessTranslationErrorTestCase(
            description="missing duration period fails clearly",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        loaded_at_field="loaded_at",
                        freshness={"error_after": {"count": 1}},
                    ),
                ),
            ),
            expected_error_fragment="must include positive count and period",
        ),
        DbtSourceFreshnessTranslationErrorTestCase(
            description="non-positive duration count fails clearly",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        loaded_at_field="loaded_at",
                        freshness={"error_after": {"count": 0, "period": "day"}},
                    ),
                ),
            ),
            expected_error_fragment="must include positive count and period",
        ),
        DbtSourceFreshnessTranslationErrorTestCase(
            description="non-string duration period fails clearly",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        loaded_at_field="loaded_at",
                        freshness={"error_after": {"count": 1, "period": 7}},
                    ),
                ),
            ),
            expected_error_fragment="must include positive count and period",
        ),
        DbtSourceFreshnessTranslationErrorTestCase(
            description="unsupported freshness duration period fails clearly",
            manifest_data=build_manifest_data(
                nodes=(),
                sources=(
                    build_manifest_source_node(
                        unique_id="source.analytics.raw.orders",
                        loaded_at_field="loaded_at",
                        freshness={"error_after": {"count": 1, "period": "week"}},
                    ),
                ),
            ),
            expected_error_fragment="unsupported period 'week'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dbt_manifest_source_freshness_error_when_translating_then_raises_error(
    test_case: DbtSourceFreshnessTranslationErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)

    with pytest.raises(DbtInteropConfigError, match=test_case.expected_error_fragment):
        translate_dbt_manifest_sources_to_sqlbuild_sources(manifest=manifest)
