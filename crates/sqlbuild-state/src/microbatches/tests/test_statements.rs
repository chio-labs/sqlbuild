use crate::events::main::microbatch_event_id::microbatch_event_id;
use crate::microbatches::main::insert_many_sql::insert_many_sql;
use crate::microbatches::tests::helpers::completion_identity;
use crate::microbatches::tests::test_types::{EventIdTestCase, InsertManyTestCase};

#[test]
fn given_event_identity_when_hashing_then_matches_python_json_digest() {
    let test_cases = [EventIdTestCase {
        description: "ordinary completion",
        identity: completion_identity(),
        expected_id: "86cf4c901147bf7e0bde6673b0725aed47d013211f9ccef8bb84f77fca1454ae",
    }];

    for test_case in test_cases {
        assert_eq!(
            microbatch_event_id(&test_case.identity).ok().as_deref(),
            Some(test_case.expected_id),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rows_when_rendering_bulk_insert_then_first_row_carries_aliases() {
    let test_cases = [InsertManyTestCase {
        description: "two rows",
        rows: vec![
            vec!["'a'".to_owned(), "1".to_owned()],
            vec!["'b'".to_owned(), "2".to_owned()],
        ],
        expected_sql: "INSERT INTO s.t (event_id, n) SELECT event_id, n FROM (SELECT 'a' AS event_id, 1 AS n UNION ALL SELECT 'b', 2) AS incoming WHERE NOT EXISTS (SELECT 1 FROM s.t AS existing WHERE existing.event_id = incoming.event_id)",
    }];

    for test_case in test_cases {
        assert_eq!(
            insert_many_sql(
                "s.t",
                &["event_id".to_owned(), "n".to_owned()],
                &test_case.rows
            ),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
