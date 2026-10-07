use crate::scope_index::_helpers::identities::python_str_repr;
use crate::scope_index::tests::helpers::{resource_groups, visibility_texts};
use crate::scope_index::tests::test_types::{LookupTestCase, ReprTestCase};

#[test]
fn given_identity_keys_when_grouping_then_groups_follow_python_repr_order() {
    let test_cases = [
        LookupTestCase {
            description: "ASCII keys order by repr, where quotes and punctuation sort first",
            resources: &[
                ("model", "ab", "models/ab.sql"),
                ("model", "ab!", "models/ab_bang.sql"),
                ("model", "it's", "models/its.sql"),
                ("function", "zz", "functions/sql/zz.sql"),
                ("seed", "a", "seeds/a.csv"),
            ],
            declarations: &[],
            expected_resource_groups: &[
                "function:zz",
                "model:it's",
                "model:ab!",
                "model:ab",
                "seed:a",
            ],
            expected_repr_ordered: true,
            expected_visibility: &["global []"],
        },
        LookupTestCase {
            description: "non-ASCII keys are left for Python to order",
            resources: &[("model", "caf\u{e9}", "models/cafe.sql")],
            declarations: &[],
            expected_resource_groups: &["model:caf\u{e9}"],
            expected_repr_ordered: false,
            expected_visibility: &["global []"],
        },
        LookupTestCase {
            description: "visibility positions group by scope over the canonical declarations",
            resources: &[("model", "orders", "models/sales/orders.sql")],
            declarations: &[
                ("macro", "g", "macros/g.py", 1, "global", None),
                (
                    "macro",
                    "l",
                    "models/sales/_macros/l.py",
                    1,
                    "local",
                    Some("models/sales"),
                ),
                (
                    "enum",
                    "i",
                    "models/_sqlbuild/enums/i.sql",
                    1,
                    "inherited",
                    Some("models"),
                ),
                (
                    "constant",
                    "_p",
                    "models/sales/orders.sql",
                    1,
                    "private",
                    Some("models/sales"),
                ),
            ],
            expected_resource_groups: &["model:orders"],
            expected_repr_ordered: true,
            expected_visibility: &[
                "global [2]",
                "private model:orders [0]",
                "local models/sales [3]",
                "inherited models [1]",
            ],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            resource_groups(&test_case),
            (
                test_case
                    .expected_resource_groups
                    .iter()
                    .map(|name| (*name).to_owned())
                    .collect(),
                test_case.expected_repr_ordered
            ),
            "{}",
            test_case.description
        );
        assert_eq!(
            visibility_texts(&test_case),
            test_case.expected_visibility,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_key_text_when_taking_repr_then_it_matches_python() {
    let test_cases = [
        ReprTestCase {
            description: "plain text uses single quotes",
            value: "plain",
            expected_repr: Some("'plain'"),
        },
        ReprTestCase {
            description: "a single quote alone switches to double quotes",
            value: "it's",
            expected_repr: Some("\"it's\""),
        },
        ReprTestCase {
            description: "both quotes keep single quotes and escape them",
            value: "both'\"",
            expected_repr: Some("'both\\'\"'"),
        },
        ReprTestCase {
            description: "whitespace controls and backslashes use short escapes",
            value: "tab\tnew\nline\r\\",
            expected_repr: Some("'tab\\tnew\\nline\\r\\\\'"),
        },
        ReprTestCase {
            description: "other controls use hex escapes",
            value: "bell\u{7}del\u{7f}",
            expected_repr: Some("'bell\\x07del\\x7f'"),
        },
        ReprTestCase {
            description: "non-ASCII text is left to Python",
            value: "caf\u{e9}",
            expected_repr: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            python_str_repr(test_case.value).as_deref(),
            test_case.expected_repr,
            "{}",
            test_case.description
        );
    }
}
