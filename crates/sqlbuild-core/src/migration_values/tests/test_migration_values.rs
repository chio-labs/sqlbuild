use crate::migration_values::main::column_decision_traits::column_decision_traits;
use crate::migration_values::main::migration_decision_traits::migration_decision_traits;
use crate::migration_values::main::model_migration_blocks_build::model_migration_blocks_build;
use crate::migration_values::main::storage_transition::storage_transition;
use crate::migration_values::models::{ColumnDecisionTraits, DecisionTraits, ModelMigrationFacts};
use crate::migration_values::tests::test_types::{
    BlocksBuildTestCase, ColumnDecisionTestCase, DecisionTestCase, TransitionTestCase,
};

const MOVING: DecisionTraits = DecisionTraits {
    moves_data: true,
    blocks_build: false,
    checks_compatibility: true,
};

#[test]
fn given_model_decision_when_classifying_then_matches_python_properties() {
    let test_cases = [
        DecisionTestCase {
            description: "migrate moves data and checks compatibility",
            decision: "migrate",
            expected_traits: MOVING,
        },
        DecisionTestCase {
            description: "conflict blocks and checks compatibility",
            decision: "conflict",
            expected_traits: DecisionTraits {
                moves_data: false,
                blocks_build: true,
                checks_compatibility: true,
            },
        },
        DecisionTestCase {
            description: "done does nothing",
            decision: "done",
            expected_traits: DecisionTraits {
                moves_data: false,
                blocks_build: false,
                checks_compatibility: false,
            },
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            migration_decision_traits(test_case.decision),
            test_case.expected_traits,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_column_decision_when_classifying_then_matches_python_properties() {
    let test_cases = [
        ColumnDecisionTestCase {
            description: "rename renames and records",
            decision: "rename",
            expected_traits: ColumnDecisionTraits {
                renames: true,
                records_event: true,
                blocks_build: false,
                label: Some("rename in place"),
            },
        },
        ColumnDecisionTestCase {
            description: "a produced source blocks",
            decision: "still_produced",
            expected_traits: ColumnDecisionTraits {
                renames: false,
                records_event: false,
                blocks_build: true,
                label: Some("source still produced"),
            },
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            column_decision_traits(test_case.decision),
            test_case.expected_traits,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_migration_facts_when_checking_then_blocks_as_python_did() {
    let facts =
        |origin_missing, origin_tracked, deny_missing_origin, incompatible| ModelMigrationFacts {
            origin_missing,
            origin_tracked,
            deny_missing_origin,
            decision: MOVING,
            incompatible,
        };
    let test_cases = [
        BlocksBuildTestCase {
            description: "a tracked missing origin blocks",
            facts: facts(true, true, false, false),
            expected_blocks: true,
        },
        BlocksBuildTestCase {
            description: "an untracked allowed missing origin passes",
            facts: facts(true, false, false, true),
            expected_blocks: false,
        },
        BlocksBuildTestCase {
            description: "an incompatible move blocks",
            facts: facts(false, false, false, true),
            expected_blocks: true,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            model_migration_blocks_build(&test_case.facts),
            test_case.expected_blocks,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_table_types_when_labelling_then_shows_the_transition() {
    let test_cases = [
        TransitionTestCase {
            description: "a permanent origin staged as transient",
            types: (false, Some(true)),
            expected_transition: Some("permanent -> transient"),
        },
        TransitionTestCase {
            description: "an unknown stage type has no label",
            types: (true, None),
            expected_transition: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            storage_transition(test_case.types.0, test_case.types.1).as_deref(),
            test_case.expected_transition,
            "{}",
            test_case.description
        );
    }
}
