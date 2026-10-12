use crate::relationship_names::main::expected_model_names::expected_model_names;
use crate::relationship_names::main::relationship_facts::relationship_facts;
use crate::relationship_names::main::stored_expected_names::stored_expected_names;
use crate::relationship_names::models::{
    ExpectedNames, RelationshipScan, RelationshipSource, ScenarioInput, TestBlockInput,
    TestFileInput,
};
use crate::relationship_names::tests::helpers::{fact_summary, generic_syntax, owned_names};
use crate::relationship_names::tests::test_types::{
    RelationshipFactsTestCase, ScanMessageTestCase, StoredNamesTestCase,
};

#[test]
fn given_tests_and_scenarios_when_reading_relationship_facts_then_python_order_and_faults_hold() {
    let test_cases = [
        RelationshipFactsTestCase {
            description: "model, macro and udf blocks with nested calls",
            files: &[(
                "tests/unit/orders.sql",
                &[
                    (
                        "orders_test",
                        "WITH __ref__a AS (SELECT @outer(@inner(1))), __expected__orders AS (SELECT @enum('s').A) SELECT 1",
                        "model",
                    ),
                    (
                        "macro_test",
                        "WITH __macro_actual__ AS (SELECT @cents(1), @const('c')), __macro_expected__ AS (SELECT 100)",
                        "macro",
                    ),
                    (
                        "udf_test",
                        "WITH __udf_actual__ AS (SELECT 1), __udf_expected__ AS (SELECT 1)",
                        "udf",
                    ),
                ],
                None,
            )],
            scenarios: &[(
                "orders__paid",
                "tests/scenarios/orders__paid.sql",
                "WITH __expected__orders AS (SELECT 1), __expected__customers AS (SELECT 2)",
            )],
            expected_facts: &[
                "test:orders_test expected=[orders] called=[outer, inner] tested=[]",
                "test:macro_test expected=[] called=[cents] tested=[cents]",
                "test:udf_test expected=[] called=[] tested=[]",
                "scenario:orders__paid expected=[orders, customers] called=[] tested=[]",
            ],
            expected_faults: &[],
            expected_stored: &[0],
        },
        RelationshipFactsTestCase {
            description: "stored names are reused and the file is not stored again",
            files: &[(
                "tests/unit/orders.sql",
                &[(
                    "orders_test",
                    "WITH __expected__orders AS (SELECT 1) SELECT 1",
                    "model",
                )],
                Some(&[&["stored_model"]]),
            )],
            scenarios: &[],
            expected_facts: &["test:orders_test expected=[stored_model] called=[] tested=[]"],
            expected_faults: &[],
            expected_stored: &[],
        },
        RelationshipFactsTestCase {
            description: "a failing block keeps its file unstored and the other blocks' facts",
            files: &[(
                "tests/unit/orders.sql",
                &[
                    ("broken", "WITH __expected__orders AS (SELECT 1", "model"),
                    (
                        "fine",
                        "WITH __expected__customers AS (SELECT 1) SELECT 1",
                        "model",
                    ),
                    (
                        "bad_call",
                        "WITH __macro_actual__ AS (SELECT @m(1, $$x) ), __macro_expected__ AS (SELECT 1)",
                        "macro",
                    ),
                ],
                None,
            )],
            scenarios: &[(
                "broken_scenario",
                "tests/scenarios/broken.sql",
                "WITH __expected__a AS (SELECT 1",
            )],
            expected_facts: &["test:fine expected=[customers] called=[] tested=[]"],
            expected_faults: &[
                (
                    "tests/unit/orders.sql",
                    "SQL test contains an unclosed parenthesis",
                ),
                (
                    "tests/unit/orders.sql",
                    "Macro expansion contains an unclosed quoted string",
                ),
                (
                    "tests/scenarios/broken.sql",
                    "SQL scenario contains an unclosed parenthesis",
                ),
            ],
            expected_stored: &[],
        },
    ];
    let syntax = generic_syntax();
    for test_case in test_cases {
        let files: Vec<TestFileInput<'_>> = test_case
            .files
            .iter()
            .map(|(relative_path, blocks, stored)| TestFileInput {
                relative_path,
                blocks: blocks
                    .iter()
                    .map(|(name, sql, mode)| TestBlockInput { name, sql, mode })
                    .collect(),
                stored: stored.map(owned_names),
            })
            .collect();
        let scenarios: Vec<ScenarioInput<'_>> = test_case
            .scenarios
            .iter()
            .map(|(name, relative_path, sql)| ScenarioInput {
                name,
                relative_path,
                sql,
            })
            .collect();

        let scan: RelationshipScan = relationship_facts(&files, &scenarios, &syntax);

        assert_eq!(
            (
                scan.facts.iter().map(fact_summary).collect::<Vec<_>>(),
                scan.faults
                    .iter()
                    .map(|(path, message)| (path.as_str(), message.as_str()))
                    .collect::<Vec<_>>(),
                scan.scanned_files
                    .iter()
                    .map(|(position, _)| *position)
                    .collect::<Vec<_>>(),
            ),
            (
                test_case
                    .expected_facts
                    .iter()
                    .map(|fact| (*fact).to_owned())
                    .collect::<Vec<_>>(),
                test_case.expected_faults.to_vec(),
                test_case.expected_stored.to_vec(),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_bytes_when_decoding_expected_names_then_only_exact_shapes_are_reused() {
    let test_cases = [
        StoredNamesTestCase {
            description: "one list per block",
            value: r#"[["orders"],[]]"#,
            block_count: 2,
            expected_names: Some(&[&["orders"], &[]]),
        },
        StoredNamesTestCase {
            description: "a different block count",
            value: r#"[["orders"]]"#,
            block_count: 2,
            expected_names: None,
        },
        StoredNamesTestCase {
            description: "undecodable bytes",
            value: "{]",
            block_count: 1,
            expected_names: None,
        },
        StoredNamesTestCase {
            description: "a misshapen entry",
            value: r#"[{"mode": "model"}]"#,
            block_count: 1,
            expected_names: None,
        },
        StoredNamesTestCase {
            description: "a non-string name",
            value: "[[1]]",
            block_count: 1,
            expected_names: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            stored_expected_names(test_case.value.as_bytes(), test_case.block_count),
            test_case.expected_names.map(owned_names),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_malformed_ctes_when_scanning_expected_models_then_messages_name_the_source() {
    let test_cases = [
        ScanMessageTestCase {
            description: "expected model scan without AS keeps sql test wording",
            source: RelationshipSource::Test,
            file_label: "tests/unit/orders.sql",
            sql: "WITH __source__raw_orders (SELECT 1 AS order_id) SELECT 1",
            expected_message: "SQL test 'tests/unit/orders.sql' expected keyword AS",
        },
        ScanMessageTestCase {
            description: "expected model scan without a target keeps sql test wording",
            source: RelationshipSource::Test,
            file_label: "tests/unit/orders.sql",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__ AS (SELECT 1 AS order_id) SELECT 1",
            expected_message: "SQL test 'tests/unit/orders.sql' must use __expected__<model> to identify a target",
        },
        ScanMessageTestCase {
            description: "expected model scan without AS uses scenario wording",
            source: RelationshipSource::Scenario,
            file_label: "tests/scenarios/orders.sql",
            sql: "WITH __source__raw_orders (SELECT 1 AS order_id) SELECT 1",
            expected_message: "SQL scenario 'tests/scenarios/orders.sql' expected keyword AS",
        },
        ScanMessageTestCase {
            description: "expected model scan unclosed comment uses scenario wording",
            source: RelationshipSource::Scenario,
            file_label: "tests/scenarios/orders.sql",
            sql: "WITH /* unfinished",
            expected_message: "SQL scenario contains an unclosed block comment",
        },
        ScanMessageTestCase {
            description: "expected model scan leading unclosed comment uses scenario wording",
            source: RelationshipSource::Scenario,
            file_label: "tests/scenarios/orders.sql",
            sql: "/* unfinished",
            expected_message: "SQL scenario contains an unclosed block comment",
        },
        ScanMessageTestCase {
            description: "expected model scan without a target uses scenario wording",
            source: RelationshipSource::Scenario,
            file_label: "tests/scenarios/orders.sql",
            sql: "WITH __source__raw_orders AS (SELECT 1 AS order_id), __expected__ AS (SELECT 1 AS order_id) SELECT 1",
            expected_message: "SQL scenario 'tests/scenarios/orders.sql' must use __expected__<model> to identify a target",
        },
    ];
    let syntax = generic_syntax();
    for test_case in test_cases {
        let texts: Vec<(String, String)> =
            vec![(test_case.sql.to_owned(), test_case.file_label.to_owned())];

        assert_eq!(
            expected_model_names(&texts, test_case.source, &syntax),
            vec![ExpectedNames::Failed(test_case.expected_message.to_owned())],
            "{}",
            test_case.description
        );
    }
}
