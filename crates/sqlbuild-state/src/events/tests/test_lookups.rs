use crate::events::main::newest_fingerprint::newest_fingerprint;
use crate::events::main::recorded_renames::recorded_renames;
use crate::events::tests::helpers::{fingerprint, order, recorded, relation};
use crate::events::tests::test_types::{NewestFingerprintTestCase, RecordedRenamesTestCase};

#[test]
fn given_column_renames_when_reading_since_then_recorded_matches_return_oldest_first() {
    let test_cases = [
        RecordedRenamesTestCase {
            description: "renames at or after the cutoff sort by time then event ID",
            events: vec![
                recorded(order(5, "b"), relation(None, "main", "orders"), true),
                recorded(order(3, "z"), relation(Some("db"), "MAIN", "Orders"), true),
                recorded(order(5, "a"), relation(None, "main", "orders"), true),
                recorded(order(2, "c"), relation(None, "main", "orders"), true),
            ],
            relation: relation(None, "main", "orders"),
            since: order(3, "").created_at,
            expected_indexes: vec![1, 2, 0],
        },
        RecordedRenamesTestCase {
            description: "unrecorded decisions and other relations are skipped",
            events: vec![
                recorded(order(4, "a"), relation(None, "main", "orders"), false),
                recorded(order(4, "b"), relation(None, "main", "customers"), true),
                recorded(order(4, "c"), relation(Some("one"), "main", "orders"), true),
            ],
            relation: relation(Some("two"), "main", "orders"),
            since: order(1, "").created_at,
            expected_indexes: vec![],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            recorded_renames(&test_case.events, &test_case.relation, &test_case.since),
            test_case.expected_indexes,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_fingerprints_when_finding_newest_then_built_relation_wins_before_name() {
    let test_cases = [
        NewestFingerprintTestCase {
            description: "a fingerprint that built the relation wins over a newer named one",
            fingerprints: vec![
                fingerprint(("2026-01-03", "r3"), "orders", None),
                fingerprint(
                    ("2026-01-01", "r1"),
                    "legacy",
                    Some(relation(None, "MAIN", "ORDERS")),
                ),
            ],
            target: Some(relation(Some("db"), "main", "orders")),
            model_name: Some("orders"),
            expected_index: Some(1),
        },
        NewestFingerprintTestCase {
            description: "without a built match the newest named fingerprint wins",
            fingerprints: vec![
                fingerprint(("2026-01-01", "r1"), "orders", None),
                fingerprint(("2026-01-02", "r0"), "orders", None),
                fingerprint(("2026-01-02", "r0"), "orders", None),
            ],
            target: Some(relation(None, "main", "orders")),
            model_name: Some("orders"),
            expected_index: Some(1),
        },
        NewestFingerprintTestCase {
            description: "no built match and no model name",
            fingerprints: vec![fingerprint(("2026-01-01", "r1"), "orders", None)],
            target: Some(relation(None, "main", "orders")),
            model_name: None,
            expected_index: None,
        },
        NewestFingerprintTestCase {
            description: "a name lookup alone ignores built relations",
            fingerprints: vec![
                fingerprint(
                    ("2026-01-05", "r5"),
                    "customers",
                    Some(relation(None, "main", "orders")),
                ),
                fingerprint(("2026-01-01", "r1"), "orders", None),
            ],
            target: None,
            model_name: Some("orders"),
            expected_index: Some(1),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            newest_fingerprint(
                &test_case.fingerprints,
                test_case.target.as_ref(),
                test_case.model_name,
            ),
            test_case.expected_index,
            "{}",
            test_case.description
        );
    }
}
