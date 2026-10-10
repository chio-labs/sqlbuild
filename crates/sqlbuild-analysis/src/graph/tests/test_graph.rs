use crate::graph::_helpers::close_matches::close_matches;
use crate::graph::_helpers::glob::fnmatch;
use crate::graph::tests::helpers::{expected, resolved};
use crate::graph::tests::test_types::{CloseMatchTestCase, GlobTestCase, SelectorTestCase};

#[test]
fn given_selectors_when_resolving_then_keys_or_errors_match_python() {
    let test_cases = [
        SelectorTestCase {
            description: "nothing selected",
            select: &[],
            exclude: &[],
            expected: Ok(&[
                ("model", "customer_orders"),
                ("model", "customers"),
                ("model", "order_items"),
                ("model", "orders"),
                ("seed", "countries"),
                ("source", "raw_orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "orders",
            select: &["orders"],
            exclude: &[],
            expected: Ok(&[("model", "orders"), ("udf", "tax")]),
        },
        SelectorTestCase {
            description: "+orders",
            select: &["+orders"],
            exclude: &[],
            expected: Ok(&[
                ("model", "orders"),
                ("source", "raw_orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "orders+",
            select: &["orders+"],
            exclude: &[],
            expected: Ok(&[
                ("model", "customer_orders"),
                ("model", "order_items"),
                ("model", "orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "tag:daily minus order_items",
            select: &["tag:daily"],
            exclude: &["order_items"],
            expected: Ok(&[("model", "orders"), ("udf", "tax")]),
        },
        SelectorTestCase {
            description: "models/mart",
            select: &["models/mart"],
            exclude: &[],
            expected: Ok(&[
                ("model", "order_items"),
                ("model", "orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "path:models/staging",
            select: &["path:models/staging"],
            exclude: &[],
            expected: Ok(&[("model", "customers")]),
        },
        SelectorTestCase {
            description: "models",
            select: &["models"],
            exclude: &[],
            expected: Err(("S007", "unknown selector name 'models'", None)),
        },
        SelectorTestCase {
            description: "order*",
            select: &["order*"],
            exclude: &[],
            expected: Ok(&[
                ("model", "order_items"),
                ("model", "orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "seed:countries+",
            select: &["seed:countries+"],
            exclude: &[],
            expected: Ok(&[
                ("model", "order_items"),
                ("seed", "countries"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "customers~customer_orders",
            select: &["customers~customer_orders"],
            exclude: &[],
            expected: Ok(&[
                ("model", "customer_orders"),
                ("model", "customers"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "+orders~order_items+",
            select: &["+orders~order_items+"],
            exclude: &[],
            expected: Ok(&[
                ("model", "order_items"),
                ("model", "orders"),
                ("source", "raw_orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "tag:daily,models/mart/items",
            select: &["tag:daily,models/mart/items"],
            exclude: &[],
            expected: Ok(&[("model", "order_items"), ("udf", "tax")]),
        },
        SelectorTestCase {
            description: "orders customers",
            select: &["orders customers"],
            exclude: &[],
            expected: Ok(&[("model", "customers"), ("model", "orders"), ("udf", "tax")]),
        },
        SelectorTestCase {
            description: " minus orders",
            select: &[],
            exclude: &["orders"],
            expected: Ok(&[
                ("model", "customer_orders"),
                ("model", "customers"),
                ("model", "order_items"),
                ("seed", "countries"),
                ("source", "raw_orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "ordrs",
            select: &["ordrs"],
            exclude: &[],
            expected: Err((
                "S007",
                "unknown selector name 'ordrs'",
                Some("did you mean 'orders'?"),
            )),
        },
        SelectorTestCase {
            description: "ord*x",
            select: &["ord*x"],
            exclude: &[],
            expected: Err(("S007", "unknown selector pattern 'ord*x'", None)),
        },
        SelectorTestCase {
            description: "a+b",
            select: &["a+b"],
            exclude: &[],
            expected: Err((
                "S002",
                "selector 'a+b' contains '+' in an unsupported position",
                None,
            )),
        },
        SelectorTestCase {
            description: "+",
            select: &["+"],
            exclude: &[],
            expected: Err((
                "S004",
                "selector '+' has no name after removing '+' markers",
                None,
            )),
        },
        SelectorTestCase {
            description: "a,,b",
            select: &["a,,b"],
            exclude: &[],
            expected: Err(("S007", "unknown selector name 'a'", None)),
        },
        SelectorTestCase {
            description: "x~",
            select: &["x~"],
            exclude: &[],
            expected: Err((
                "S003",
                "path selector 'x~' requires names on both sides of '~'",
                None,
            )),
        },
        SelectorTestCase {
            description: "foo:bar",
            select: &["foo:bar"],
            exclude: &[],
            expected: Err(("S005", "unknown selector type 'foo' in 'foo:bar'", None)),
        },
        SelectorTestCase {
            description: "seed:",
            select: &["seed:"],
            exclude: &[],
            expected: Err(("S006", "selector 'seed:' has empty value after ':'", None)),
        },
        SelectorTestCase {
            description: "tag:none",
            select: &["tag:none"],
            exclude: &[],
            expected: Err(("S008", "no models found with tag 'none'", None)),
        },
        SelectorTestCase {
            description: "staging/crm.sql",
            select: &["staging/crm.sql"],
            exclude: &[],
            expected: Err((
                "S012",
                "path selectors require an explicit root: use 'models/' or 'python/'",
                None,
            )),
        },
        SelectorTestCase {
            description: "mart",
            select: &["mart"],
            exclude: &[],
            expected: Err(("S007", "unknown selector name 'mart'", None)),
        },
        SelectorTestCase {
            description: "test:abc",
            select: &["test:abc"],
            exclude: &[],
            expected: Err((
                "S013",
                "selector 'test:abc' selects a unit test; only `sqb test` and `sqb build` accept unit-test selectors",
                None,
            )),
        },
        SelectorTestCase {
            description: "task:abc",
            select: &["task:abc"],
            exclude: &[],
            expected: Err((
                "S010",
                "selector type 'task' does not map to a resource type yet",
                None,
            )),
        },
        SelectorTestCase {
            description: "order_items~orders",
            select: &["order_items~orders"],
            exclude: &[],
            expected: Err((
                "S000",
                "'model:orders' is not downstream of 'model:order_items'",
                None,
            )),
        },
        SelectorTestCase {
            description: "source:raw_*",
            select: &["source:raw_*"],
            exclude: &[],
            expected: Ok(&[("source", "raw_orders")]),
        },
        SelectorTestCase {
            description: "[!o]*",
            select: &["[!o]*"],
            exclude: &[],
            expected: Ok(&[
                ("model", "customer_orders"),
                ("model", "customers"),
                ("seed", "countries"),
                ("source", "raw_orders"),
                ("udf", "tax"),
            ]),
        },
        SelectorTestCase {
            description: "customer",
            select: &["customer"],
            exclude: &[],
            expected: Err((
                "S007",
                "unknown selector name 'customer'",
                Some("did you mean 'customers'?"),
            )),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            resolved(test_case.select, test_case.exclude),
            expected(&test_case.expected),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_glob_patterns_when_matching_then_results_match_fnmatchcase() {
    let test_cases = [
        GlobTestCase {
            pattern: "ord*",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "o?ders",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[a-c]*",
            name: "customers",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[!a-c]*",
            name: "customers",
            expected_match: false,
        },
        GlobTestCase {
            pattern: "[z-a]x",
            name: "x",
            expected_match: false,
        },
        GlobTestCase {
            pattern: "[]]",
            name: "]",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[!]",
            name: "!",
            expected_match: false,
        },
        GlobTestCase {
            pattern: "[a-]",
            name: "-",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[",
            name: "[",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "a[b",
            name: "a[b",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "**s",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[^o]*",
            name: "orders",
            expected_match: true,
        },
        GlobTestCase {
            pattern: "[\\]x",
            name: "\\x",
            expected_match: true,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            fnmatch(test_case.pattern, test_case.name),
            test_case.expected_match,
            "{} {}",
            test_case.pattern,
            test_case.name
        );
    }
}

#[test]
fn given_unknown_name_when_suggesting_then_matches_get_close_matches() {
    let test_cases = [
        CloseMatchTestCase {
            word: "ordrs",
            candidates: &[
                "customer_orders",
                "customers",
                "order_items",
                "orders",
                "raw_orders",
            ],
            cutoff: 0.8,
            expected: &["orders"],
        },
        CloseMatchTestCase {
            word: "custmer",
            candidates: &["costumer", "custom", "customer", "customers"],
            cutoff: 0.6,
            expected: &["customer", "customers", "costumer"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            close_matches(test_case.word, test_case.candidates, 3, test_case.cutoff),
            test_case.expected,
            "{}",
            test_case.word
        );
    }
}
