use sqlbuild_core::plan_display::errors::UnknownCursorGrain;

use crate::planner_strategy::main::cursor_input_column::cursor_input_column_failure;
use crate::planner_strategy::main::microbatch_lookback::microbatch_lookback;
use crate::planner_strategy::main::table_type_ddl::table_type_ddl;
use crate::planner_strategy::models::CursorInputColumnOwner;
use crate::planner_strategy::tests::helpers::{column_check, lookback_config};
use crate::planner_strategy::tests::test_types::{
    CursorInputColumnTestCase, LookbackTestCase, TableTypeDdlTestCase,
};

#[test]
fn given_cursor_input_column_when_checking_exposure_then_reports_missing_columns() {
    let test_cases = [
        CursorInputColumnTestCase {
            description: "case-insensitive model contract match",
            check: column_check(CursorInputColumnOwner::ModelContract, &["updated_at"]),
            expected_failure: None,
        },
        CursorInputColumnTestCase {
            description: "model contract without the column",
            check: column_check(CursorInputColumnOwner::ModelContract, &["order_id"]),
            expected_failure: Some((
                "model 'daily_orders': cursor_inputs references model 'orders' column \
                 'Updated_At', but that model contract does not expose the column. Known output \
                 columns: order_id"
                    .to_owned(),
                "S302",
            )),
        },
        CursorInputColumnTestCase {
            description: "source contract without columns",
            check: column_check(CursorInputColumnOwner::SourceContract, &[]),
            expected_failure: Some((
                "model 'daily_orders': cursor_inputs references source 'orders' column \
                 'Updated_At', but that source contract does not expose the column. Declared \
                 contract columns: none"
                    .to_owned(),
                "S302",
            )),
        },
        CursorInputColumnTestCase {
            description: "warehouse source without the column",
            check: column_check(
                CursorInputColumnOwner::SourceWarehouse,
                &["order_id", "status"],
            ),
            expected_failure: Some((
                "model 'daily_orders': cursor_inputs references source 'orders' column \
                 'Updated_At', but that source does not expose the column. Known source \
                 columns: order_id, status"
                    .to_owned(),
                "S302",
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            cursor_input_column_failure(&test_case.check),
            test_case.expected_failure,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_microbatch_config_when_resolving_lookback_then_matches_python_default() {
    let test_cases = [
        LookbackTestCase {
            description: "explicit lookback wins",
            config: lookback_config(Some("2 days"), Some("append"), None),
            expected_lookback: Ok(Some("2 days".to_owned())),
        },
        LookbackTestCase {
            description: "append has no default",
            config: lookback_config(None, Some("append"), Some("day")),
            expected_lookback: Ok(None),
        },
        LookbackTestCase {
            description: "merge without grain keeps the batch size",
            config: lookback_config(None, Some("merge"), None),
            expected_lookback: Ok(Some("effective".to_owned())),
        },
        LookbackTestCase {
            description: "delete insert resolves the effective grain",
            config: lookback_config(None, Some("delete_insert"), Some("hour")),
            expected_lookback: Ok(Some("1h".to_owned())),
        },
        LookbackTestCase {
            description: "unknown grain",
            config: lookback_config(None, Some("merge"), Some("fortnight")),
            expected_lookback: Err(UnknownCursorGrain("fortnight".to_owned())),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            microbatch_lookback(&test_case.config),
            test_case.expected_lookback,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_table_type_when_rendering_ddl_then_rewrites_only_permanent_tables() {
    let test_cases = [
        TableTypeDdlTestCase {
            description: "permanent rewrites the first keyword",
            ddl: "CREATE TRANSIENT TABLE a AS SELECT 1; CREATE TRANSIENT TABLE b",
            table_type: "permanent",
            expected_ddl: "CREATE TABLE a AS SELECT 1; CREATE TRANSIENT TABLE b",
        },
        TableTypeDdlTestCase {
            description: "transient keeps the adapter DDL",
            ddl: "CREATE TRANSIENT TABLE a AS SELECT 1",
            table_type: "transient",
            expected_ddl: "CREATE TRANSIENT TABLE a AS SELECT 1",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            table_type_ddl(test_case.ddl, test_case.table_type),
            test_case.expected_ddl,
            "{}",
            test_case.description
        );
    }
}
