use crate::events::constants::OLD_NAME_VIEW_COLUMNS;
use crate::events::main::column_aliases_json::column_aliases_json;
use crate::events::main::decoded_column_aliases::decoded_column_aliases;
use crate::events::main::decoded_grants::decoded_grants;
use crate::events::main::event_read_sql::event_read_sql;
use crate::events::main::grants_json::grants_json;
use crate::events::main::readable_columns::readable_columns;
use crate::events::tests::helpers::pairs;
use crate::events::tests::test_types::{
    AliasesTestCase, DecodedAliasesTestCase, DecodedGrantsTestCase, GrantsTestCase, ReadSqlTestCase,
};

#[test]
fn given_aliases_when_encoding_then_matches_python_compact_sorted_json() {
    let test_cases = [
        AliasesTestCase {
            description: "sorted keys, last duplicate wins and non-ASCII is escaped",
            aliases: pairs(&[("z", "\u{e4}"), ("a", "b"), ("a", "c")]),
            expected_json: Some("{\"a\":\"c\",\"z\":\"\\u00e4\"}".to_owned()),
        },
        AliasesTestCase {
            description: "no aliases store null",
            aliases: vec![],
            expected_json: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            column_aliases_json(&test_case.aliases).ok(),
            Some(test_case.expected_json),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_grants_when_encoding_then_matches_python_default_json() {
    let test_cases = [
        GrantsTestCase {
            description: "quotes kept and non-ASCII escaped with default separators",
            grants: Some(vec!["GRANT 'x'".to_owned(), "\u{e9}".to_owned()]),
            expected_json: Some("[\"GRANT 'x'\", \"\\u00e9\"]".to_owned()),
        },
        GrantsTestCase {
            description: "unrecorded grants store null",
            grants: None,
            expected_json: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            grants_json(test_case.grants.as_deref()).ok(),
            Some(test_case.expected_json),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_alias_text_when_decoding_then_reads_sorted_pairs_or_none() {
    let test_cases = [
        DecodedAliasesTestCase {
            description: "object values are printed as Python would",
            raw: Some("{\"k\": 1, \"j\": true, \"i\": null, \"h\": 1.5, \"g\": \"x\"}"),
            expected_aliases: pairs(&[
                ("g", "x"),
                ("h", "1.5"),
                ("i", "None"),
                ("j", "True"),
                ("k", "1"),
            ]),
        },
        DecodedAliasesTestCase {
            description: "invalid JSON",
            raw: Some("{not json"),
            expected_aliases: vec![],
        },
        DecodedAliasesTestCase {
            description: "array is not a mapping",
            raw: Some("[\"a\"]"),
            expected_aliases: vec![],
        },
        DecodedAliasesTestCase {
            description: "empty text",
            raw: Some(""),
            expected_aliases: vec![],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            decoded_column_aliases(test_case.raw),
            test_case.expected_aliases,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_grant_text_when_decoding_then_reads_statements_or_unknown() {
    let test_cases = [
        DecodedGrantsTestCase {
            description: "array items are printed as Python would",
            raw: Some("[\"GRANT\", 3, null]"),
            expected_grants: Some(vec!["GRANT".to_owned(), "3".to_owned(), "None".to_owned()]),
        },
        DecodedGrantsTestCase {
            description: "object is not a statement list",
            raw: Some("{\"a\": 1}"),
            expected_grants: None,
        },
        DecodedGrantsTestCase {
            description: "absent column",
            raw: None,
            expected_grants: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            decoded_grants(test_case.raw),
            test_case.expected_grants,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_columns_when_reading_old_name_facts_then_selects_known_columns_in_order() {
    let test_cases = [ReadSqlTestCase {
        description: "unknown and missing columns are left out",
        stored: vec![
            "EVENT_ID".to_owned(),
            "zzz".to_owned(),
            "created_at".to_owned(),
            "event_type".to_owned(),
            "view_sql".to_owned(),
        ],
        expected_sql: "SELECT event_id, event_type, view_sql, created_at FROM s.t ORDER BY created_at, event_id".to_owned(),
    }];

    for test_case in test_cases {
        assert_eq!(
            event_read_sql(
                "s.t",
                &readable_columns(&OLD_NAME_VIEW_COLUMNS, &test_case.stored)
            ),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
