use crate::event_export::main::export_snapshot::export_snapshot;
use crate::event_export::main::route_lifecycle_event::route_lifecycle_event;
use crate::event_export::models::{
    ExportPolicy, ExportSeverity, ExporterCounts, ExporterFilter, SnapshotInputs,
};
use crate::event_export::tests::test_types::{RoutingTestCase, SnapshotTestCase};

#[test]
fn given_sink_filters_when_routing_then_kind_and_severity_select_eligible_sinks() {
    let test_cases = [
        RoutingTestCase {
            description: "kind and minimum severity both apply",
            policy: ("run", ExportSeverity::Info),
            filters: &[
                (&["run"], ExportSeverity::Debug),
                (&["run"], ExportSeverity::Error),
                (&["statement"], ExportSeverity::Debug),
            ],
            expected_eligible: &[0],
            expected_filtered: 2,
        },
        RoutingTestCase {
            description: "every matching sink is eligible in order",
            policy: ("invocation", ExportSeverity::Error),
            filters: &[
                (&["invocation"], ExportSeverity::Warning),
                (&["run", "invocation"], ExportSeverity::Error),
            ],
            expected_eligible: &[0, 1],
            expected_filtered: 0,
        },
    ];

    for test_case in test_cases {
        let (kind, severity) = test_case.policy;
        let policy = ExportPolicy {
            kind: kind.to_owned(),
            severity,
            priority: 0,
        };
        let filters: Vec<ExporterFilter> = test_case
            .filters
            .iter()
            .map(|(kinds, min_severity)| ExporterFilter {
                event_kinds: kinds.iter().map(|kind| (*kind).to_owned()).collect(),
                min_severity: *min_severity,
            })
            .collect();
        let (counts, eligible) = route_lifecycle_event(
            &policy,
            &filters,
            vec![ExporterCounts::default(); filters.len()],
        );
        let filtered: u64 = counts.iter().map(|counts| counts.filtered).sum();
        assert_eq!(
            (eligible.as_slice(), filtered),
            (test_case.expected_eligible, test_case.expected_filtered),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_exporter_counts_when_snapshotting_then_flush_completes_only_when_settled_and_drained() {
    let test_cases = [
        SnapshotTestCase {
            description: "settled drained accounting is complete",
            counts: &[(3, 2, 1, 0), (2, 1, 0, 1)],
            queue_depth: 0,
            drained: true,
            expected_accepted: 5,
            expected_flush_complete: true,
        },
        SnapshotTestCase {
            description: "a point-in-time snapshot is never complete",
            counts: &[(1, 1, 0, 0)],
            queue_depth: 0,
            drained: false,
            expected_accepted: 1,
            expected_flush_complete: false,
        },
        SnapshotTestCase {
            description: "unsettled attempts are incomplete",
            counts: &[(2, 1, 0, 0)],
            queue_depth: 0,
            drained: true,
            expected_accepted: 2,
            expected_flush_complete: false,
        },
    ];

    for test_case in test_cases {
        let exporters: Vec<(String, ExporterCounts)> = test_case
            .counts
            .iter()
            .map(|(accepted, delivered, failed, dropped)| {
                (
                    "sink".to_owned(),
                    ExporterCounts {
                        accepted: *accepted,
                        filtered: 0,
                        delivered: *delivered,
                        failed: *failed,
                        dropped: *dropped,
                    },
                )
            })
            .collect();
        let snapshot = export_snapshot(SnapshotInputs {
            exporters: &exporters,
            queue_depth: test_case.queue_depth,
            queue_capacity: 8,
            drained: test_case.drained,
        });
        assert_eq!(
            (snapshot.aggregate.accepted, snapshot.flush_complete),
            (
                test_case.expected_accepted,
                test_case.expected_flush_complete
            ),
            "{}",
            test_case.description
        );
    }
}
