//! Addressing, exclusion, origin and request rules decide which relations the janitor touches.

use crate::janitor_planning::constants::{CASE_COLLISION_REASON, UNQUOTED_ADDRESSING_REASON};
use crate::janitor_planning::main::case_colliding_names::case_colliding_names;
use crate::janitor_planning::main::matching_exclude_pattern::matching_exclude_pattern;
use crate::janitor_planning::main::migration_origin_keys::migration_origin_keys;
use crate::janitor_planning::main::old_name_request_matches::old_name_request_matches;
use crate::janitor_planning::main::resolve_retention_days::resolve_retention_days;
use crate::janitor_planning::main::unaddressable_relation_reason::unaddressable_relation_reason;
use crate::janitor_planning::tests::helpers::key;
use crate::janitor_planning::tests::test_types::{
    AddressingTestCase, ExcludePatternTestCase, OriginKeysTestCase, RequestMatchTestCase,
    RetentionTestCase,
};

#[test]
fn given_listing_when_checking_addressing_then_returns_reason() {
    let test_cases = [
        AddressingTestCase {
            description: "plain lowercase name",
            names: vec!["orders", "customers"],
            name: "orders",
            expected_reason: None,
        },
        AddressingTestCase {
            description: "mixed case name needs quoting",
            names: vec!["Orders"],
            name: "Orders",
            expected_reason: Some(UNQUOTED_ADDRESSING_REASON),
        },
        AddressingTestCase {
            description: "digits dollar and leading underscore",
            names: vec!["_orders$2026"],
            name: "_orders$2026",
            expected_reason: None,
        },
        AddressingTestCase {
            description: "punctuation needs quoting",
            names: vec!["old-orders;drop"],
            name: "old-orders;drop",
            expected_reason: Some(UNQUOTED_ADDRESSING_REASON),
        },
        AddressingTestCase {
            description: "leading digit needs quoting",
            names: vec!["2026_orders"],
            name: "2026_orders",
            expected_reason: Some(UNQUOTED_ADDRESSING_REASON),
        },
        AddressingTestCase {
            description: "uppercase side of a collision needs quoting",
            names: vec!["old_orders", "OLD_ORDERS"],
            name: "OLD_ORDERS",
            expected_reason: Some(UNQUOTED_ADDRESSING_REASON),
        },
        AddressingTestCase {
            description: "folded collision",
            names: vec!["orders", "ORDERS"],
            name: "orders",
            expected_reason: Some(CASE_COLLISION_REASON),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            unaddressable_relation_reason(
                test_case.name,
                &case_colliding_names(test_case.names.iter().copied())
            ),
            test_case.expected_reason,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_patterns_when_matching_relation_then_returns_first_folded_match() {
    let test_cases = [
        ExcludePatternTestCase {
            description: "name pattern ignores case",
            name: "PARTITION_state",
            display_name: "main.PARTITION_state",
            patterns: vec!["other".to_owned(), "partition_*".to_owned()],
            expected_pattern: Some("partition_*"),
        },
        ExcludePatternTestCase {
            description: "qualified pattern",
            name: "orders",
            display_name: "analytics.orders",
            patterns: vec!["ANALYTICS.*".to_owned()],
            expected_pattern: Some("ANALYTICS.*"),
        },
        ExcludePatternTestCase {
            description: "no match",
            name: "orders",
            display_name: "main.orders",
            patterns: vec!["customers".to_owned()],
            expected_pattern: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            matching_exclude_pattern(
                (test_case.name, test_case.display_name),
                &test_case.patterns
            ),
            test_case.expected_pattern,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_migrate_from_value_when_resolving_origins_then_returns_keys() {
    let schemas: Vec<(Option<String>, Option<String>)> = vec![
        (None, Some("main".to_owned())),
        (None, Some("staging".to_owned())),
    ];
    let test_cases = [
        OriginKeysTestCase {
            description: "bare name in every schema",
            raw: "old_orders",
            schemas: schemas.clone(),
            expected_keys: vec![
                key(None, "main", "old_orders"),
                key(None, "staging", "old_orders"),
            ],
        },
        OriginKeysTestCase {
            description: "schema-qualified name inherits destination database",
            raw: " legacy . \"old_orders\" ",
            schemas: schemas.clone(),
            expected_keys: vec![key(Some("warehouse"), "legacy", "old_orders")],
        },
        OriginKeysTestCase {
            description: "fully qualified name",
            raw: "archive.legacy.`old_orders`",
            schemas,
            expected_keys: vec![key(Some("archive"), "legacy", "old_orders")],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            migration_origin_keys(test_case.raw, Some("warehouse"), &test_case.schemas),
            test_case.expected_keys,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_drop_request_when_matching_old_name_then_compares_trailing_parts() {
    let test_cases = [
        RequestMatchTestCase {
            description: "bare name",
            request: "OLD_ORDERS",
            expected_matches: true,
        },
        RequestMatchTestCase {
            description: "schema-qualified quoted name",
            request: "main.\"old_orders\"",
            expected_matches: true,
        },
        RequestMatchTestCase {
            description: "longer than the recorded name",
            request: "db.extra.main.old_orders",
            expected_matches: false,
        },
        RequestMatchTestCase {
            description: "other schema",
            request: "staging.old_orders",
            expected_matches: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            old_name_request_matches(test_case.request, (None, Some("main"), "old_orders")),
            test_case.expected_matches,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_retention_inputs_when_resolving_then_override_wins_over_config_and_default() {
    let test_cases = [
        RetentionTestCase {
            description: "unset retention defaults to 14",
            override_days: None,
            configured: None,
            expected_days: 14,
        },
        RetentionTestCase {
            description: "configured retention applies",
            override_days: None,
            configured: Some(7),
            expected_days: 7,
        },
        RetentionTestCase {
            description: "override wins over configuration",
            override_days: Some(3),
            configured: Some(7),
            expected_days: 3,
        },
        RetentionTestCase {
            description: "zero override wins over the default",
            override_days: Some(0),
            configured: None,
            expected_days: 0,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            resolve_retention_days(test_case.override_days, test_case.configured),
            test_case.expected_days,
            "{}",
            test_case.description
        );
    }
}
