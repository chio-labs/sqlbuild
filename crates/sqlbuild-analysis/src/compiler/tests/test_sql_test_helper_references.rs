use serde_json::{Value, json};

use crate::compiler::tests::helpers::{
    chain_helper_reference_case, defined_before, plan_helper_reference_case,
    plan_helper_reference_response,
};
use crate::compiler::tests::test_types::{
    HelperReferenceTestCase, UnresolvedReaderReferenceTestCase,
};

const HELPER_READS_MODEL: (&str, &str) = (
    "doubled",
    "SELECT order_id, amount_doubled FROM __ref(\"orders\")",
);
const MOCK_STG_ORDERS: (&str, &str) = (
    "__ref__stg_orders",
    "SELECT 5 AS order_id, 10 AS amount, 7 AS region_id",
);
const REAL_STG_ORDERS_BODY: &str = "SELECT order_id, amount, region_id FROM __source__raw_orders";
const ASSERT_MOCK_ROWS: (&str, &str) = (
    "__assert__mock_rows",
    "SELECT order_id FROM __ref(\"stg_orders\") WHERE order_id <> 5",
);
const EXPECTED_FROM_MOCK: (&str, &str) = (
    "__expected__orders",
    "SELECT order_id, amount * 2 AS amount_doubled FROM __ref(\"stg_orders\")",
);
const ASSERT_DOUBLED: (&str, &str) = (
    "__assert__doubles_amount",
    "SELECT order_id FROM doubled WHERE amount_doubled <> 20",
);

#[test]
fn given_helper_cte_references_when_planning_then_references_resolve_in_dependency_order() {
    let test_cases = [
        HelperReferenceTestCase {
            description: "helper reading a model is emitted after the model and its mocks",
            sql_analysis_enabled: true,
            helpers: &[HELPER_READS_MODEL],
            expected: &[],
            assertions: &[ASSERT_DOUBLED],
            read_helpers: &["doubled"],
            reference_targets: &["orders"],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__source__raw_orders", "__ref__stg_orders"),
                ("__ref__stg_orders", "__ref__orders"),
                ("__ref__orders", "__helper__doubled"),
                ("__helper__doubled", "__assert__doubles_amount"),
            ],
            expected_fragments: &[
                "__helper__doubled AS (SELECT order_id, amount_doubled FROM __ref__orders)",
            ],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "helper inlined without sql analysis reads the model CTE",
            sql_analysis_enabled: false,
            helpers: &[HELPER_READS_MODEL],
            expected: &[],
            assertions: &[ASSERT_DOUBLED],
            read_helpers: &["doubled"],
            reference_targets: &["orders"],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__source__raw_orders", "__ref__orders"),
                ("__ref__orders", "__assert__doubles_amount"),
            ],
            expected_fragments: &[
                "WITH doubled AS (SELECT order_id, amount_doubled FROM __ref__orders)",
            ],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "helper reading another helper, a model and a seed is ordered after all three",
            sql_analysis_enabled: true,
            helpers: &[
                (
                    "with_region",
                    "SELECT b.order_id, r.region_name FROM base AS b \
                     JOIN __ref(\"stg_orders\") AS s USING (order_id) \
                     JOIN __seed(\"regions\") AS r USING (region_id)",
                ),
                (
                    "base",
                    "SELECT order_id, amount_doubled FROM __ref(\"orders\")",
                ),
            ],
            expected: &[],
            assertions: &[(
                "__assert__has_region",
                "SELECT order_id FROM with_region WHERE region_name IS NULL",
            )],
            read_helpers: &["with_region", "base"],
            reference_targets: &["stg_orders", "orders"],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__ref__orders", "__helper__base"),
                ("__helper__base", "__helper__with_region"),
                ("__ref__stg_orders", "__helper__with_region"),
                ("__seed__regions", "__helper__with_region"),
                ("__helper__with_region", "__assert__has_region"),
            ],
            expected_fragments: &[
                "FROM __helper__base AS b JOIN __ref__stg_orders AS s USING (order_id) \
                 JOIN __seed__regions AS r USING (region_id)",
            ],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "helper read by expected rows resolves sources and seeds to their mocks",
            sql_analysis_enabled: true,
            helpers: &[(
                "expected_rows",
                "SELECT s.order_id, s.amount * 2 AS amount_doubled FROM __source(\"raw_orders\") AS s \
                 JOIN __seed(\"regions\") AS r USING (region_id)",
            )],
            expected: &[(
                "__expected__orders",
                "SELECT order_id, amount_doubled FROM expected_rows",
            )],
            assertions: &[],
            read_helpers: &["expected_rows"],
            reference_targets: &[],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__source__raw_orders", "__helper__expected_rows"),
                ("__seed__regions", "__helper__expected_rows"),
                ("__helper__expected_rows", "__expected__orders"),
            ],
            expected_fragments: &[
                "FROM __source__raw_orders AS s JOIN __seed__regions AS r USING (region_id)",
            ],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "inlined helper read by expected rows reads the model CTE",
            sql_analysis_enabled: false,
            helpers: &[HELPER_READS_MODEL],
            expected: &[(
                "__expected__orders",
                "SELECT order_id, amount_doubled FROM doubled",
            )],
            assertions: &[],
            read_helpers: &["doubled"],
            reference_targets: &["orders"],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[("__ref__orders", "__expected__orders")],
            expected_fragments: &[
                "__expected__orders AS (WITH doubled AS (SELECT order_id, amount_doubled FROM __ref__orders)",
            ],
            expected_absent_fragments: &["__helper__"],
        },
        HelperReferenceTestCase {
            description: "helper and assertion reading a mocked model through different paths share one mock CTE",
            sql_analysis_enabled: true,
            helpers: &[
                (
                    "__ref__stg_orders",
                    "SELECT order_id, 10 AS amount FROM base_ids",
                ),
                ("base_ids", "SELECT 1 AS order_id"),
                (
                    "doubled",
                    "SELECT o.order_id, o.amount_doubled FROM __ref(\"orders\") AS o",
                ),
            ],
            expected: &[],
            assertions: &[(
                "__assert__doubles_amount",
                "SELECT order_id FROM doubled JOIN __ref(\"stg_orders\") USING (order_id) \
                 WHERE amount_doubled <> 20",
            )],
            read_helpers: &["doubled"],
            reference_targets: &["orders"],
            expected_chain: &["orders"],
            expected_order: &[
                ("__helper__base_ids", "__ref__orders"),
                ("__ref__orders", "__helper__doubled"),
                ("__helper__doubled", "__assert__doubles_amount"),
            ],
            expected_fragments: &[],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "helper nothing reads is neither resolved nor emitted",
            sql_analysis_enabled: true,
            helpers: &[("unused_rows", "SELECT order_id FROM __ref(\"orders\")")],
            expected: &[(
                "__expected__stg_orders",
                "SELECT 1 AS order_id, 10 AS amount, 7 AS region_id",
            )],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["stg_orders"],
            expected_order: &[("__source__raw_orders", "__expected__stg_orders")],
            expected_fragments: &[],
            expected_absent_fragments: &["unused_rows", "__ref__orders"],
        },
        HelperReferenceTestCase {
            description: "assertion reading a mocked model reads the mock, not the model",
            sql_analysis_enabled: true,
            helpers: &[MOCK_STG_ORDERS],
            expected: &[(
                "__expected__orders",
                "SELECT 5 AS order_id, 20 AS amount_doubled",
            )],
            assertions: &[ASSERT_MOCK_ROWS],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["orders"],
            expected_order: &[("__ref__stg_orders", "__assert__mock_rows")],
            expected_fragments: &["FROM __ref__stg_orders WHERE order_id <> 5"],
            expected_absent_fragments: &[REAL_STG_ORDERS_BODY, "__sqb_cte_"],
        },
        HelperReferenceTestCase {
            description: "assertion reading a mocked model reads the mock without sql analysis",
            sql_analysis_enabled: false,
            helpers: &[MOCK_STG_ORDERS],
            expected: &[],
            assertions: &[
                ASSERT_MOCK_ROWS,
                (
                    "__assert__doubled",
                    "SELECT order_id FROM __ref(\"orders\") WHERE amount_doubled <> 20",
                ),
            ],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["orders"],
            expected_order: &[
                ("__ref__stg_orders", "__ref__orders"),
                ("__ref__orders", "__assert__doubled"),
            ],
            expected_fragments: &["FROM __ref__stg_orders WHERE order_id <> 5"],
            expected_absent_fragments: &[REAL_STG_ORDERS_BODY, "__sqb_cte_"],
        },
        HelperReferenceTestCase {
            description: "expected rows reading a mocked model resolve to the mock",
            sql_analysis_enabled: true,
            helpers: &[MOCK_STG_ORDERS],
            expected: &[EXPECTED_FROM_MOCK],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["orders"],
            expected_order: &[("__ref__stg_orders", "__expected__orders")],
            expected_fragments: &[
                "__expected__orders AS (SELECT order_id, amount * 2 AS amount_doubled FROM __ref__stg_orders)",
            ],
            expected_absent_fragments: &[REAL_STG_ORDERS_BODY, "__sqb_cte_"],
        },
        HelperReferenceTestCase {
            description: "expected rows reading a mocked model resolve to the mock without sql analysis",
            sql_analysis_enabled: false,
            helpers: &[MOCK_STG_ORDERS],
            expected: &[EXPECTED_FROM_MOCK],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["orders"],
            expected_order: &[("__ref__stg_orders", "__expected__orders")],
            expected_fragments: &[
                "__expected__orders AS (SELECT order_id, amount * 2 AS amount_doubled FROM __ref__stg_orders)",
            ],
            expected_absent_fragments: &[REAL_STG_ORDERS_BODY, "__sqb_cte_"],
        },
        HelperReferenceTestCase {
            description: "expected rows reading an unmocked model run that model",
            sql_analysis_enabled: true,
            helpers: &[],
            expected: &[EXPECTED_FROM_MOCK],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &["stg_orders"],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[("__ref__stg_orders", "__expected__orders")],
            expected_fragments: &["amount * 2 AS amount_doubled FROM __ref__stg_orders)"],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "expected rows reading a source and a seed resolve to their mocks without sql analysis",
            sql_analysis_enabled: false,
            helpers: &[],
            expected: &[(
                "__expected__stg_orders",
                "SELECT s.order_id, s.amount, r.region_id FROM __source(\"raw_orders\") AS s \
                 JOIN __seed(\"regions\") AS r USING (region_id)",
            )],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["stg_orders"],
            expected_order: &[
                ("__source__raw_orders", "__expected__stg_orders"),
                ("__seed__regions", "__expected__stg_orders"),
            ],
            expected_fragments: &[
                "FROM __source__raw_orders AS s JOIN __seed__regions AS r USING (region_id)",
            ],
            expected_absent_fragments: &[],
        },
        HelperReferenceTestCase {
            description: "helper sharing a column name in expected rows is not read",
            sql_analysis_enabled: true,
            helpers: &[(
                "amount_doubled",
                "SELECT order_id FROM __ref(\"archived_orders\")",
            )],
            expected: &[(
                "__expected__orders",
                "SELECT 1 AS order_id, 20 AS amount_doubled",
            )],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[("__ref__orders", "__expected__orders")],
            expected_fragments: &["SELECT 1 AS order_id, 20 AS amount_doubled"],
            expected_absent_fragments: &["__ref__archived_orders"],
        },
        HelperReferenceTestCase {
            description: "helper sharing a column name in expected rows is not read without sql analysis",
            sql_analysis_enabled: false,
            helpers: &[(
                "amount_doubled",
                "SELECT order_id FROM __ref(\"archived_orders\")",
            )],
            expected: &[(
                "__expected__orders",
                "SELECT 1 AS order_id, 20 AS amount_doubled",
            )],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[("__ref__orders", "__expected__orders")],
            expected_fragments: &["SELECT 1 AS order_id, 20 AS amount_doubled"],
            expected_absent_fragments: &["__ref__archived_orders"],
        },
    ];
    for test_case in test_cases {
        let artifact: Value = plan_helper_reference_case(&test_case);
        let chain: Value = chain_helper_reference_case(&test_case);
        let sql = artifact["sql"].as_str().expect("test assumption must hold");
        let errors: Vec<&Value> = artifact["warnings"]
            .as_array()
            .expect("test assumption must hold")
            .iter()
            .filter(|warning| warning["severity"] == json!("error"))
            .collect();

        assert_eq!(
            chain,
            json!(test_case.expected_chain),
            "{}",
            test_case.description
        );
        for (first, second) in test_case.expected_order {
            assert!(
                defined_before(sql, first, second),
                "{}: {first} before {second}: {sql}",
                test_case.description
            );
        }
        for fragment in test_case.expected_absent_fragments {
            assert!(
                !sql.contains(fragment),
                "{}: {fragment}: {sql}",
                test_case.description
            );
        }
        for fragment in test_case.expected_fragments {
            assert!(
                sql.contains(fragment),
                "{}: {fragment}: {sql}",
                test_case.description
            );
        }
        for marker in ["__ref(", "__source(", "__seed(", "__dbt_ref("] {
            assert!(!sql.contains(marker), "{}: {sql}", test_case.description);
        }
        assert!(errors.is_empty(), "{}: {errors:?}", test_case.description);
    }
}

#[test]
fn given_unresolvable_reader_references_when_planning_directly_then_planner_rejects_test() {
    let test_cases = [
        UnresolvedReaderReferenceTestCase {
            description: "assertion calling an unmocked source",
            sql_analysis_enabled: true,
            helpers: &[],
            expected: &[(
                "__expected__stg_orders",
                "SELECT 1 AS order_id, 10 AS amount, 7 AS region_id",
            )],
            assertions: &[(
                "__assert__no_returns",
                "SELECT order_id FROM __source(\"returns\")",
            )],
            read_helpers: &[],
            reference_targets: &[],
            sends_compiler_reads: true,
            expected_error_fragments: &[
                "sql_test_reference:",
                "\"cteName\":\"__assert__no_returns\"",
                "\"call\":\"__source(\\\"returns\\\")\"",
                "\"mockCte\":\"__source__returns\"",
            ],
        },
        UnresolvedReaderReferenceTestCase {
            description: "expected rows calling an unmocked seed without sql analysis",
            sql_analysis_enabled: false,
            helpers: &[],
            expected: &[(
                "__expected__stg_orders",
                "SELECT order_id, amount, region_id FROM __seed(\"returns\")",
            )],
            assertions: &[],
            read_helpers: &[],
            reference_targets: &[],
            sends_compiler_reads: true,
            expected_error_fragments: &[
                "\"cteName\":\"__expected__stg_orders\"",
                "\"mockCte\":\"__seed__returns\"",
            ],
        },
        UnresolvedReaderReferenceTestCase {
            description: "helper read by an assertion calling an unmocked dbt model",
            sql_analysis_enabled: true,
            helpers: &[(
                "legacy_orders",
                "SELECT order_id FROM __dbt_ref(\"warehouse\", \"orders\")",
            )],
            expected: &[(
                "__expected__stg_orders",
                "SELECT 1 AS order_id, 10 AS amount, 7 AS region_id",
            )],
            assertions: &[("__assert__no_legacy", "SELECT order_id FROM legacy_orders")],
            read_helpers: &["legacy_orders"],
            reference_targets: &[],
            sends_compiler_reads: true,
            expected_error_fragments: &[
                "\"cteName\":\"legacy_orders\"",
                "\"mockCte\":\"__dbt_ref__warehouse__orders\"",
            ],
        },
        UnresolvedReaderReferenceTestCase {
            description: "request without the compiler's reads",
            sql_analysis_enabled: true,
            helpers: &[HELPER_READS_MODEL],
            expected: &[],
            assertions: &[ASSERT_DOUBLED],
            read_helpers: &[],
            reference_targets: &[],
            sends_compiler_reads: false,
            expected_error_fragments: &[
                "planner_input:",
                "omits readHelperNames or referenceTargetModelNames",
            ],
        },
    ];
    for test_case in test_cases {
        let error = plan_helper_reference_response(
            &HelperReferenceTestCase {
                description: test_case.description,
                sql_analysis_enabled: test_case.sql_analysis_enabled,
                helpers: test_case.helpers,
                expected: test_case.expected,
                assertions: test_case.assertions,
                read_helpers: test_case.read_helpers,
                reference_targets: test_case.reference_targets,
                expected_chain: &[],
                expected_order: &[],
                expected_fragments: &[],
                expected_absent_fragments: &[],
            },
            test_case.sends_compiler_reads,
        )
        .expect_err(test_case.description);

        assert!(
            test_case
                .expected_error_fragments
                .iter()
                .all(|fragment| error.contains(fragment)),
            "{}: {error}",
            test_case.description
        );
    }
}
