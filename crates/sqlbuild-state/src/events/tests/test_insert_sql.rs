use sqlbuild_cursor::algebra::models::{CivilDate, LocalDateTime};

use crate::events::errors::StateSqlError;
use crate::events::main::event_insert_sql::event_insert_sql;
use crate::events::models::{StateColumnType, StateValue};
use crate::events::tests::helpers::cell;
use crate::events::tests::test_types::InsertTestCase;

#[test]
fn given_event_row_when_rendering_insert_then_matches_python_literals() {
    let created = LocalDateTime {
        date: CivilDate {
            year: 2024,
            month: 2,
            day: 29,
        },
        hour: 1,
        minute: 2,
        second: 3,
        microsecond: 40,
    };
    let test_cases = [
        InsertTestCase {
            description: "quoted text, a null and a UTC timestamp",
            cells: vec![
                cell("event_id", StateColumnType::String, StateValue::Text("o'k".to_owned())),
                cell("target_name", StateColumnType::String, StateValue::Null),
                cell("created_at", StateColumnType::TextTimestamp, StateValue::UtcTimestamp(created)),
            ],
            expected_sql: Ok("INSERT INTO s.t (event_id, target_name, created_at) VALUES ('o''k', NULL, '2024-02-29T01:02:03.000040+00:00')".to_owned()),
        },
        InsertTestCase {
            description: "a non-text value in a string column",
            cells: vec![cell("event_id", StateColumnType::String, StateValue::Other)],
            expected_sql: Err(StateSqlError("state string columns require str values".to_owned())),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            event_insert_sql("s.t", &test_case.cells),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
