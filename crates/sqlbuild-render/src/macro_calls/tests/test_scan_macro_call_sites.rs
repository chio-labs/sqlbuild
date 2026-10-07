use crate::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites;
use crate::macro_calls::tests::helpers::python_312;
use std::time::Instant;

use crate::macro_calls::tests::test_types::{
    DeepNestingTestCase, ExpectedSite, ScanMacroCallSitesTestCase,
};

#[test]
fn given_authored_sql_when_scanning_macro_calls_then_sites_match_python_expansion() {
    let test_cases = [
        ScanMacroCallSitesTestCase {
            description: "one call",
            sql: "SELECT @a(1) FROM t",
            expected_sites: Some(&[(7, 12, "a", &["a"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "nested calls belong to the enclosing site",
            sql: "@outer(@inner(@leaf()), '@quoted()', @inner(2)) y",
            expected_sites: Some(&[(0, 47, "outer", &["outer", "inner", "leaf"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "quoted text and comments hide calls",
            sql: "'@a(1)' -- @b(2)\n/* @c(3) */ \"@d()\" `@e()` $$@f()$$ @g()",
            expected_sites: Some(&[(52, 56, "g", &["g"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "a one-letter name followed by whitespace is not a call",
            sql: "@a (1)",
            expected_sites: Some(&[]),
        },
        ScanMacroCallSitesTestCase {
            description: "a longer name may be separated from its parenthesis",
            sql: "@ab (1)",
            expected_sites: Some(&[(0, 7, "ab", &["ab"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "whitespace inside a name defers to Python's error",
            sql: "@ab c(1)",
            expected_sites: None,
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed quote after a call defers",
            sql: "@a(1) 'oops",
            expected_sites: None,
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed call defers",
            sql: "@a(1",
            expected_sites: None,
        },
        ScanMacroCallSitesTestCase {
            description: "offsets count code points",
            sql: "SELECT 'é', @a(1)",
            expected_sites: Some(&[(12, 17, "a", &["a"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "a non-ASCII character after @ defers",
            sql: "@é(1)",
            expected_sites: None,
        },
        ScanMacroCallSitesTestCase {
            description: "typed reference text is flagged",
            sql: "@m(__ref('x')) @n('__seed') @o(1)",
            expected_sites: Some(&[
                (0, 14, "m", &["m"], true),
                (15, 27, "n", &["n"], true),
                (28, 33, "o", &["o"], false),
            ]),
        },
        ScanMacroCallSitesTestCase {
            description: "a dollar sign continuing a word does not open a quote",
            sql: "a$$ @m()",
            expected_sites: Some(&[(4, 8, "m", &["m"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "interpolation markers are not calls",
            sql: "x @@var @m()",
            expected_sites: Some(&[(8, 12, "m", &["m"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "nested names follow source order across siblings and plain parentheses",
            sql: "@a((@b(@c(1)), (@d()) ), \"@x()\", @c())",
            expected_sites: Some(&[(0, 38, "a", &["a", "b", "c", "d"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "a quoted parenthesis inside a nested call does not close it",
            sql: "@a(@b(')'))",
            expected_sites: Some(&[(0, 11, "a", &["a", "b"], false)]),
        },
        ScanMacroCallSitesTestCase {
            description: "a nested name without its parenthesis defers",
            sql: "@a(@bb c(1))",
            expected_sites: None,
        },
        ScanMacroCallSitesTestCase {
            description: "parentheses inside quoted arguments do not close the call",
            sql: "@m(')', \"(\", `)`) z",
            expected_sites: Some(&[(0, 17, "m", &["m"], false)]),
        },
    ];

    for test_case in test_cases {
        let actual: Option<Vec<ExpectedSite>> = scan_macro_call_sites(python_312(), test_case.sql)
            .ok()
            .map(|sites| {
                sites
                    .into_iter()
                    .map(|site| {
                        let names: Vec<&'static str> = site
                            .tree_names
                            .iter()
                            .map(|name| &*Box::leak(name.clone().into_boxed_str()))
                            .collect();
                        (
                            site.start,
                            site.end,
                            &*Box::leak(site.name.into_boxed_str()),
                            &*Box::leak(names.into_boxed_slice()),
                            site.typed_reference_text,
                        )
                    })
                    .collect()
            });
        assert_eq!(
            actual,
            test_case.expected_sites.map(<[ExpectedSite]>::to_vec),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_deeply_nested_calls_when_scanning_then_time_is_linear_and_nothing_overflows() {
    let test_cases = [
        DeepNestingTestCase {
            description: "one thousand levels",
            depth: 1_000,
            expected_tree_names: &["m"],
            expected_max_seconds: 2.0,
        },
        DeepNestingTestCase {
            description: "twenty thousand levels",
            depth: 20_000,
            expected_tree_names: &["m"],
            expected_max_seconds: 2.0,
        },
        DeepNestingTestCase {
            description: "one hundred thousand levels",
            depth: 100_000,
            expected_tree_names: &["m"],
            expected_max_seconds: 2.0,
        },
    ];

    for test_case in test_cases {
        let sql = format!(
            "{}x{}",
            "@m(".repeat(test_case.depth),
            ")".repeat(test_case.depth)
        );
        let started = Instant::now();

        let sites = scan_macro_call_sites(python_312(), &sql).expect("scanned");

        assert!(
            started.elapsed().as_secs_f64() < test_case.expected_max_seconds,
            "{}",
            test_case.description
        );
        assert_eq!(
            sites
                .iter()
                .map(|site| site.tree_names.clone())
                .collect::<Vec<_>>(),
            vec![test_case.expected_tree_names.to_vec()],
            "{}",
            test_case.description
        );
    }
}
