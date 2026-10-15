use crate::lifecycle_events::main::hook_problem::hook_problem;
use crate::lifecycle_events::main::lifecycle_version_problem::lifecycle_version_problem;
use crate::lifecycle_events::main::run_bounds_problem::run_bounds_problem;
use crate::lifecycle_events::models::{HookFacts, SequenceFact};
use crate::lifecycle_events::tests::test_types::{
    HookTestCase, LifecycleVersionTestCase, RunBoundsTestCase,
};

const SEQUENCE_PROBLEM: &str = "invocation_sequence must be a non-negative integer excluding bool";
const VALID_HOOK: HookFacts<'static> = HookFacts {
    phase: Some("pre_hooks"),
    hook_type: Some("sql"),
    valid_index: true,
};

#[test]
fn given_schema_versions_and_metadata_when_validating_then_version_rules_apply() {
    let test_cases = [
        LifecycleVersionTestCase {
            description: "unknown version",
            schema_version: 3,
            sequence: SequenceFact::Valid,
            has_external_context: false,
            expected_problem: Some(
                "LifecycleEvent only represents known schema versions through 2; decode other versions as OpaqueLifecycleEvent",
            ),
        },
        LifecycleVersionTestCase {
            description: "version 1 without metadata",
            schema_version: 1,
            sequence: SequenceFact::Absent,
            has_external_context: false,
            expected_problem: None,
        },
        LifecycleVersionTestCase {
            description: "version 1 with external context",
            schema_version: 1,
            sequence: SequenceFact::Absent,
            has_external_context: true,
            expected_problem: Some(
                "schema version 1 lifecycle events cannot contain invocation metadata",
            ),
        },
        LifecycleVersionTestCase {
            description: "version 2 requires a sequence",
            schema_version: 2,
            sequence: SequenceFact::Absent,
            has_external_context: false,
            expected_problem: Some(SEQUENCE_PROBLEM),
        },
        LifecycleVersionTestCase {
            description: "version 2 with sequence and context",
            schema_version: 2,
            sequence: SequenceFact::Valid,
            has_external_context: true,
            expected_problem: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            lifecycle_version_problem(
                test_case.schema_version,
                test_case.sequence,
                test_case.has_external_context
            )
            .as_deref(),
            test_case.expected_problem,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_run_bounds_when_validating_then_worker_count_matches_capped_concurrency() {
    let test_cases = [
        RunBoundsTestCase {
            description: "empty selection",
            counts: (0, 1, 0),
            expected_problem: None,
        },
        RunBoundsTestCase {
            description: "concurrency caps workers",
            counts: (5, 2, 2),
            expected_problem: None,
        },
        RunBoundsTestCase {
            description: "negative selection",
            counts: (-1, 1, 0),
            expected_problem: Some("selected_count must be nonnegative"),
        },
        RunBoundsTestCase {
            description: "zero concurrency",
            counts: (1, 0, 0),
            expected_problem: Some("configured_concurrency must be positive"),
        },
        RunBoundsTestCase {
            description: "too many workers",
            counts: (5, 2, 5),
            expected_problem: Some(
                "worker_count must equal min(configured_concurrency, selected_count)",
            ),
        },
    ];

    for test_case in test_cases {
        let (selected, configured, workers) = test_case.counts;
        assert_eq!(
            run_bounds_problem(selected, configured, workers),
            test_case.expected_problem,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_hook_fields_when_validating_then_catalogue_rules_apply_in_order() {
    let test_cases = [
        HookTestCase {
            description: "catalogued hook",
            hook: VALID_HOOK,
            expected_problem: None,
        },
        HookTestCase {
            description: "missing phase",
            hook: HookFacts {
                phase: None,
                ..VALID_HOOK
            },
            expected_problem: Some("hook_phase must be a catalogued value"),
        },
        HookTestCase {
            description: "uncatalogued type",
            hook: HookFacts {
                hook_type: Some("shell"),
                ..VALID_HOOK
            },
            expected_problem: Some("hook_type must be a catalogued value"),
        },
        HookTestCase {
            description: "invalid index",
            hook: HookFacts {
                valid_index: false,
                ..VALID_HOOK
            },
            expected_problem: Some("hook_index must be a nonnegative integer"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            hook_problem(test_case.hook),
            test_case.expected_problem,
            "{}",
            test_case.description
        );
    }
}
