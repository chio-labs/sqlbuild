use crate::string_literals::main::string_literal_locations::string_literal_locations;
use crate::string_literals::models::StringQuery;
use crate::string_literals::tests::test_types::StringLocationTestCase;

/// Expectations recorded from the CPython 3.12 `ast` and `re` implementation this replaces.
#[test]
fn given_module_when_finding_named_strings_then_matches_cpython_constants() {
    let test_cases = [
        StringLocationTestCase {
            description: "an exact name, a SQL word and a docstring",
            contents: "\"\"\"orders\"\"\"\nquery = \"SELECT * FROM orders o\"\nother = \"orders_archive\"\nname = \"  ORDERS  \"\n",
            names: &["orders"],
            context: None,
            expected_locations: &[(1, 1), (2, 9), (4, 8)],
        },
        StringLocationTestCase {
            description: "f-string constants are merged and located at their first piece",
            contents: "sql = f\"select {cols} from orders\" \"  where\"\nlabel = f\"{orders=}\"\n",
            names: &["orders"],
            context: None,
            expected_locations: &[(1, 22)],
        },
        StringLocationTestCase {
            description: "a context must appear in SQL-like text",
            contents: "a = \"select id from orders\"\nb = \"select id from customers\"\nc = \"id\"\n",
            names: &["id"],
            context: Some("orders"),
            expected_locations: &[(1, 5)],
        },
        StringLocationTestCase {
            description: "Python ignore-case folds the long s and dotted capital I",
            contents: "a = \"ſelect x from t\"\nb = \"SELECT İd FROM t\"\nc = \"select $id from t\"\n",
            names: &["id", "x"],
            context: None,
            expected_locations: &[(1, 5), (2, 5)],
        },
        StringLocationTestCase {
            description: "an unparsable file",
            contents: "x = \"orders\"\ndef f(:\n",
            names: &["orders"],
            context: None,
            expected_locations: &[],
        },
        StringLocationTestCase {
            description: "match patterns and annotations",
            contents: "match x:\n    case {\"orders\": 1}:\n        pass\ndef f(a: \"orders\"): pass\n",
            names: &["orders"],
            context: None,
            expected_locations: &[(2, 11), (4, 10)],
        },
    ];
    for test_case in test_cases {
        let names: Vec<String> = test_case
            .names
            .iter()
            .map(|name| (*name).to_owned())
            .collect();
        let query: StringQuery<'_> = StringQuery {
            names: &names,
            context: test_case.context,
        };
        assert_eq!(
            string_literal_locations(test_case.contents, &query, (3, 12)),
            test_case.expected_locations,
            "{}",
            test_case.description
        );
    }
}
