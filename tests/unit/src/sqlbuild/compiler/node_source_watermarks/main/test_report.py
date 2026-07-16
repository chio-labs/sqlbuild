from __future__ import annotations

import pytest

from sqlbuild.compiler.node_source_watermarks.main.build_report import (
    build_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.main.render_report import (
    format_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkStaleness,
    NodeSourceWatermarkStalenessReport,
    WatermarkGraphKey,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkStalenessStatus
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    NodeSourceWatermarkStalenessReportTestCase,
)

ROOT_A: WatermarkGraphKey = WatermarkGraphKey(node_type="model", node_name="a")
ROOT_B: WatermarkGraphKey = WatermarkGraphKey(node_type="model", node_name="b")
TABLE_OLD: WatermarkGraphKey = WatermarkGraphKey(node_type="model", node_name="old_table")
TABLE_UNKNOWN: WatermarkGraphKey = WatermarkGraphKey(node_type="model", node_name="unknown_table")
SOURCE_EVENTS_KEY: WatermarkGraphKey = WatermarkGraphKey(node_type="source", node_name="raw.events")
EVENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.events",
    target_database=None,
    target_schema="main",
    target_name="events",
)
PAYMENTS: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw.payments",
    target_database=None,
    target_schema="main",
    target_name="payments",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkStalenessReportTestCase(
            description="groups stale table frontier and changed source into one warning block",
            classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_A,
                    frontier_key=TABLE_OLD,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
            ),
            section_limit=5,
            expected_report=NodeSourceWatermarkStalenessReport(
                affected_root_names=("a",),
                stale_frontier_names=("old_table",),
                changed_source_names=("raw.events",),
            ),
            expected_output=(
                "Stale inputs detected\n"
                "\n"
                "  Affected selected models:\n"
                "    a\n"
                "\n"
                "  Stale frontier tables:\n"
                "    old_table\n"
                "\n"
                "  Changed sources:\n"
                "    raw.events\n"
                "\n"
                "  To refresh these inputs:\n"
                "    rebuild the upstream closure for the selected model(s)"
            ),
        ),
        NodeSourceWatermarkStalenessReportTestCase(
            description="groups unknown frontier proof separately from stale table proof",
            classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_A,
                    frontier_key=TABLE_UNKNOWN,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.UNKNOWN,
                    reason="missing_upstream_watermark",
                ),
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_B,
                    frontier_key=SOURCE_EVENTS_KEY,
                    source_identity=PAYMENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
            ),
            section_limit=5,
            expected_report=NodeSourceWatermarkStalenessReport(
                affected_root_names=("a", "b"),
                changed_source_names=("raw.payments",),
                unknown_frontier_names=("unknown_table (missing_upstream_watermark)",),
            ),
            expected_output=(
                "Stale inputs detected\n"
                "\n"
                "  Affected selected models:\n"
                "    a\n"
                "    b\n"
                "\n"
                "  Changed sources:\n"
                "    raw.payments\n"
                "\n"
                "  Unknown freshness proofs:\n"
                "    unknown_table (missing_upstream_watermark)\n"
                "\n"
                "  To refresh these inputs:\n"
                "    rebuild the upstream closure for the selected model(s)"
            ),
        ),
        NodeSourceWatermarkStalenessReportTestCase(
            description="omits output for all fresh classifications",
            classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_A,
                    frontier_key=TABLE_OLD,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.FRESH,
                ),
            ),
            section_limit=5,
            expected_report=NodeSourceWatermarkStalenessReport(),
            expected_output="",
        ),
        NodeSourceWatermarkStalenessReportTestCase(
            description="deduplicates shared stale frontier across selected roots",
            classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_A,
                    frontier_key=TABLE_OLD,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
                NodeSourceWatermarkStaleness(
                    root_key=ROOT_B,
                    frontier_key=TABLE_OLD,
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
            ),
            section_limit=5,
            expected_report=NodeSourceWatermarkStalenessReport(
                affected_root_names=("a", "b"),
                stale_frontier_names=("old_table",),
                changed_source_names=("raw.events",),
            ),
            expected_output=(
                "Stale inputs detected\n"
                "\n"
                "  Affected selected models:\n"
                "    a\n"
                "    b\n"
                "\n"
                "  Stale frontier tables:\n"
                "    old_table\n"
                "\n"
                "  Changed sources:\n"
                "    raw.events\n"
                "\n"
                "  To refresh these inputs:\n"
                "    rebuild the upstream closure for the selected model(s)"
            ),
        ),
        NodeSourceWatermarkStalenessReportTestCase(
            description="caps each report section independently",
            classifications=(
                NodeSourceWatermarkStaleness(
                    root_key=WatermarkGraphKey(node_type="model", node_name="a"),
                    frontier_key=WatermarkGraphKey(node_type="model", node_name="frontier_a"),
                    source_identity=EVENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
                NodeSourceWatermarkStaleness(
                    root_key=WatermarkGraphKey(node_type="model", node_name="b"),
                    frontier_key=WatermarkGraphKey(node_type="model", node_name="frontier_b"),
                    source_identity=PAYMENTS,
                    status=WatermarkStalenessStatus.STALE,
                ),
            ),
            section_limit=1,
            expected_report=NodeSourceWatermarkStalenessReport(
                affected_root_names=("a", "b"),
                stale_frontier_names=("frontier_a", "frontier_b"),
                changed_source_names=("raw.events", "raw.payments"),
            ),
            expected_output=(
                "Stale inputs detected\n"
                "\n"
                "  Affected selected models:\n"
                "    a\n"
                "    +1 more\n"
                "\n"
                "  Stale frontier tables:\n"
                "    frontier_a\n"
                "    +1 more\n"
                "\n"
                "  Changed sources:\n"
                "    raw.events\n"
                "    +1 more\n"
                "\n"
                "  To refresh these inputs:\n"
                "    rebuild the upstream closure for the selected model(s)"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_watermark_classifications_when_reporting_then_groups_warning_sections(
    test_case: NodeSourceWatermarkStalenessReportTestCase,
) -> None:
    report: NodeSourceWatermarkStalenessReport = build_node_source_watermark_staleness_report(
        classifications=test_case.classifications,
    )

    result: str = format_node_source_watermark_staleness_report(
        report=report,
        section_limit=test_case.section_limit,
    )

    assert report == test_case.expected_report
    assert result == test_case.expected_output
