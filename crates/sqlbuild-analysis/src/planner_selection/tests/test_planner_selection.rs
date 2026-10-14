use crate::planner_selection::main::split_selector_expansion::split_selector_expansion;
use crate::planner_selection::main::split_unit_test_selectors::split_unit_test_selectors;
use crate::planner_selection::main::sqlbuild_model_selector_names::sqlbuild_model_selector_names;
use crate::planner_selection::models::{ModelSelectorNames, SelectorExpansion, SelectorGroups};
use crate::planner_selection::tests::helpers::{failure, models, selector_names, split, texts};
use crate::planner_selection::tests::test_types::{
    ExpansionTestCase, ModelSelectorTestCase, UnitTestSplitTestCase,
};

#[test]
fn given_selector_groups_when_splitting_unit_tests_then_moves_or_rejects_them() {
    let test_cases = [
        UnitTestSplitTestCase {
            description: "unit test token leaves the resource token in its group",
            select: texts(&["test_orders  customers"]),
            exclude: Vec::new(),
            accepts_unit_tests: true,
            expected_split: Ok(split(&["customers"], &["test_orders"], true)),
        },
        UnitTestSplitTestCase {
            description: "pattern selects every matching unit test and no model",
            select: texts(&["test_*"]),
            exclude: Vec::new(),
            accepts_unit_tests: true,
            expected_split: Ok(split(&[], &["test_customers", "test_orders"], false)),
        },
        UnitTestSplitTestCase {
            description: "resource names win over unit tests",
            select: texts(&["orders"]),
            exclude: Vec::new(),
            accepts_unit_tests: false,
            expected_split: Ok(split(&["orders"], &[], true)),
        },
        UnitTestSplitTestCase {
            description: "commands without unit tests reject them",
            select: texts(&["test_orders"]),
            exclude: Vec::new(),
            accepts_unit_tests: false,
            expected_split: Err(failure(
                "S013",
                "selector 'test_orders' selects a unit test; only `sqb test` and `sqb build` accept unit-test selectors",
                None,
            )),
        },
        UnitTestSplitTestCase {
            description: "intersections cannot include unit tests",
            select: texts(&["test_orders,orders"]),
            exclude: Vec::new(),
            accepts_unit_tests: true,
            expected_split: Err(failure(
                "S013",
                "selector 'test_orders,orders' intersects a unit test with ','; unit tests can only be selected whole, by name",
                None,
            )),
        },
        UnitTestSplitTestCase {
            description: "unit tests have no lineage",
            select: texts(&["+test_orders"]),
            exclude: Vec::new(),
            accepts_unit_tests: true,
            expected_split: Err(failure(
                "S013",
                "selector '+test_orders' expands a unit test with '+'; unit tests have no lineage, so select them by name without '+'",
                None,
            )),
        },
        UnitTestSplitTestCase {
            description: "unknown unit test suggests the closest name",
            select: Vec::new(),
            exclude: texts(&["test:test_order"]),
            accepts_unit_tests: false,
            expected_split: Err(failure(
                "S007",
                "unknown unit test name 'test_order'",
                Some("did you mean 'test_orders'?"),
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            split_unit_test_selectors(
                SelectorGroups {
                    select: &test_case.select,
                    exclude: &test_case.exclude,
                },
                &selector_names(),
                test_case.accepts_unit_tests,
            ),
            test_case.expected_split,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_raw_selector_when_splitting_expansion_then_returns_core_and_flags() {
    let test_cases = [
        ExpansionTestCase {
            description: "both markers",
            raw: " +orders+ ",
            expected_expansion: Ok(SelectorExpansion {
                core: "orders".to_owned(),
                upstream: true,
                downstream: true,
            }),
        },
        ExpansionTestCase {
            description: "markers only",
            raw: "++",
            expected_expansion: Err(
                "selector '++' has no name after removing '+' markers".to_owned()
            ),
        },
        ExpansionTestCase {
            description: "inner marker",
            raw: "a+b",
            expected_expansion: Err(
                "selector 'a+b' contains '+' in an unsupported position".to_owned()
            ),
        },
        ExpansionTestCase {
            description: "blank",
            raw: "  ",
            expected_expansion: Err("empty selector".to_owned()),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            split_selector_expansion(test_case.raw),
            test_case.expected_expansion,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_selector_term_when_resolving_then_returns_model_names() {
    let names = |values: &[&str], translated: Option<&str>| ModelSelectorNames {
        names: texts(values),
        translated: translated.map(str::to_owned),
    };
    let test_cases = [
        ModelSelectorTestCase {
            description: "model name",
            term: "report",
            expected_names: names(&["report"], None),
        },
        ModelSelectorTestCase {
            description: "tag in model order",
            term: "tag:daily",
            expected_names: names(&["orders", "report"], None),
        },
        ModelSelectorTestCase {
            description: "windows path is translated and matches nested folders",
            term: "path:models\\staging",
            expected_names: names(&["orders", "customers"], Some("path:models/staging")),
        },
        ModelSelectorTestCase {
            description: "other terms",
            term: "source:raw",
            expected_names: names(&[], None),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            sqlbuild_model_selector_names(&models(), test_case.term),
            test_case.expected_names,
            "{}",
            test_case.description
        );
    }
}
