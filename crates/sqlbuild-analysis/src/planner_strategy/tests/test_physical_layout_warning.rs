use crate::planner_strategy::main::physical_layout_warning::physical_layout_warning;
use crate::planner_strategy::models::MaterializationType;
use crate::planner_strategy::tests::test_types::PhysicalLayoutWarningTestCase;

const MONTHLY: &str =
    r#"{"config": {"materialized": "incremental", "partition_by": "toYYYYMM(ordered_at)"}}"#;
const WEEKLY_SORTED: &str = r#"{"config": {"materialized": "incremental", "order_by": ["order_id"], "partition_by": "toMonday(ordered_at)"}}"#;
const MONTHLY_RETAGGED: &str = r#"{"config": {"materialized": "incremental", "partition_by": "toYYYYMM(ordered_at)", "tags": ["daily"]}}"#;

#[test]
fn given_changed_layout_when_planning_then_only_kept_incremental_tables_warn() {
    let test_cases = [
        PhysicalLayoutWarningTestCase {
            description: "incremental run keeps the old layout",
            materialization: MaterializationType::Incremental,
            table_recreated: false,
            previous_metadata_json: Some(MONTHLY),
            current_metadata_json: WEEKLY_SORTED,
            expected_message: Some(
                "orders: order_by, partition_by changed, but the existing table keeps its old \
                 physical layout; a full refresh (`sqb build orders --full-refresh`) rebuilds it \
                 with the new layout",
            ),
        },
        PhysicalLayoutWarningTestCase {
            description: "a rebuilt incremental table takes the new layout",
            materialization: MaterializationType::Incremental,
            table_recreated: true,
            previous_metadata_json: Some(MONTHLY),
            current_metadata_json: WEEKLY_SORTED,
            expected_message: None,
        },
        PhysicalLayoutWarningTestCase {
            description: "a table model is always rebuilt",
            materialization: MaterializationType::Table,
            table_recreated: true,
            previous_metadata_json: Some(MONTHLY),
            current_metadata_json: WEEKLY_SORTED,
            expected_message: None,
        },
        PhysicalLayoutWarningTestCase {
            description: "other config changes",
            materialization: MaterializationType::Incremental,
            table_recreated: false,
            previous_metadata_json: Some(MONTHLY),
            current_metadata_json: MONTHLY_RETAGGED,
            expected_message: None,
        },
        PhysicalLayoutWarningTestCase {
            description: "no recorded build",
            materialization: MaterializationType::Incremental,
            table_recreated: false,
            previous_metadata_json: None,
            current_metadata_json: WEEKLY_SORTED,
            expected_message: None,
        },
    ];

    for test_case in test_cases {
        let warning = physical_layout_warning(
            "orders",
            (test_case.materialization, test_case.table_recreated),
            (
                test_case.previous_metadata_json,
                Some(test_case.current_metadata_json),
            ),
        );

        assert_eq!(
            warning.as_ref().map(|row| row.message.as_str()),
            test_case.expected_message,
            "{}",
            test_case.description
        );
    }
}
