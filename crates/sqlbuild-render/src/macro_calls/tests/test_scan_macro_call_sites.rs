use crate::macro_calls::main::scan_macro_call_sites::scan_macro_call_sites;
use crate::macro_calls::models::ScanError;
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
            expected_sites: &[(7, 12, "a", Some(&["a"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "nested calls belong to the enclosing site",
            sql: "@outer(@inner(@leaf()), '@quoted()', @inner(2)) y",
            expected_sites: &[(0, 47, "outer", Some(&["outer", "inner", "leaf"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "quoted text and comments hide calls",
            sql: "'@a(1)' -- @b(2)\n/* @c(3) */ \"@d()\" `@e()` $$@f()$$ @g()",
            expected_sites: &[(52, 56, "g", Some(&["g"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a one-letter name followed by whitespace is not a call",
            sql: "@a (1)",
            expected_sites: &[],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a longer name may be separated from its parenthesis",
            sql: "@ab (1)",
            expected_sites: &[(0, 7, "ab", Some(&["ab"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "whitespace inside a name fails in that call, as Python's evaluation does",
            sql: "@ab c(1)",
            expected_sites: &[],
            expected_failure: Some((Some(0), ScanError::MissingParenthesis)),
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed quote after a call fails after it",
            sql: "@a(1) 'oops",
            expected_sites: &[(0, 5, "a", Some(&["a"]), false)],
            expected_failure: Some((None, ScanError::UnclosedQuote)),
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed call fails in that call",
            sql: "@a(1",
            expected_sites: &[],
            expected_failure: Some((Some(0), ScanError::UnclosedParenthesis)),
        },
        ScanMacroCallSitesTestCase {
            description: "offsets count code points",
            sql: "SELECT 'é', @a(1)",
            expected_sites: &[(12, 17, "a", Some(&["a"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a non-ASCII letter after @ starts a call as Python's isalpha says",
            sql: "@é(1)",
            expected_sites: &[(0, 5, "é", Some(&["é"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a non-letter non-ASCII character after @ is not a call",
            sql: "@€(1) @m()",
            expected_sites: &[(6, 10, "m", Some(&["m"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed block comment between calls fails there",
            sql: "@a() /* @b()",
            expected_sites: &[(0, 4, "a", Some(&["a"]), false)],
            expected_failure: Some((None, ScanError::UnclosedComment)),
        },
        ScanMacroCallSitesTestCase {
            description: "an unclosed dollar quote inside a call fails in that call",
            sql: "x @a() é @b($tag$ )",
            expected_sites: &[(2, 6, "a", Some(&["a"]), false)],
            expected_failure: Some((Some(9), ScanError::UnclosedQuote)),
        },
        ScanMacroCallSitesTestCase {
            description: "typed reference text is flagged",
            sql: "@m(__ref('x')) @n('__seed') @o(1)",
            expected_sites: &[
                (0, 14, "m", Some(&["m"]), true),
                (15, 27, "n", Some(&["n"]), true),
                (28, 33, "o", Some(&["o"]), false),
            ],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a dollar sign continuing a word does not open a quote",
            sql: "a$$ @m()",
            expected_sites: &[(4, 8, "m", Some(&["m"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "interpolation markers are not calls",
            sql: "x @@var @m()",
            expected_sites: &[(8, 12, "m", Some(&["m"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "nested names follow source order across siblings and plain parentheses",
            sql: "@a((@b(@c(1)), (@d()) ), \"@x()\", @c())",
            expected_sites: &[(0, 38, "a", Some(&["a", "b", "c", "d"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a quoted parenthesis inside a nested call does not close it",
            sql: "@a(@b(')'))",
            expected_sites: &[(0, 11, "a", Some(&["a", "b"]), false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "a nested name without its parenthesis leaves the tree unscanned",
            sql: "@a(@bb c(1))",
            expected_sites: &[(0, 12, "a", None, false)],
            expected_failure: None,
        },
        ScanMacroCallSitesTestCase {
            description: "parentheses inside quoted arguments do not close the call",
            sql: "@m(')', \"(\", `)`) z",
            expected_sites: &[(0, 17, "m", Some(&["m"]), false)],
            expected_failure: None,
        },
    ];

    for test_case in test_cases {
        let scan = scan_macro_call_sites(python_312(), test_case.sql);
        let actual: Vec<ExpectedSite> = scan
            .sites
            .into_iter()
            .map(|site| {
                let names: Option<&'static [&'static str]> = site.tree_names.map(|names| {
                    let names: Vec<&'static str> = names
                        .into_iter()
                        .map(|name| &*Box::leak(name.into_boxed_str()))
                        .collect();
                    &*Box::leak(names.into_boxed_slice())
                });
                (
                    site.start,
                    site.end,
                    &*Box::leak(site.name.into_boxed_str()),
                    names,
                    site.typed_reference_text,
                )
            })
            .collect();
        assert_eq!(
            (
                actual,
                scan.failure
                    .map(|failure| (failure.call_start, failure.error))
            ),
            (
                test_case.expected_sites.to_vec(),
                test_case.expected_failure
            ),
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

        let scan = scan_macro_call_sites(python_312(), &sql);

        assert!(
            started.elapsed().as_secs_f64() < test_case.expected_max_seconds,
            "{}",
            test_case.description
        );
        assert_eq!(
            (
                scan.sites
                    .iter()
                    .map(|site| site.tree_names.clone())
                    .collect::<Vec<_>>(),
                scan.failure,
            ),
            (
                vec![Some(
                    test_case
                        .expected_tree_names
                        .iter()
                        .map(|name| (*name).to_owned())
                        .collect()
                )],
                None
            ),
            "{}",
            test_case.description
        );
    }
}
