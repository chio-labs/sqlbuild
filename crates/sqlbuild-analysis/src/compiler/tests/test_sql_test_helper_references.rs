use serde_json::{Value, json};

use crate::compiler::tests::helpers::{
    chain_helper_reference_case, defined_before, plan_helper_reference_case,
};
use crate::compiler::tests::test_types::HelperReferenceTestCase;

const HELPER_READS_MODEL: (&str, &str) = (
    "doubled",
    "SELECT order_id, amount_doubled FROM __ref(\"orders\")",
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
        },
        HelperReferenceTestCase {
            description: "helper inlined without sql analysis reads the model CTE",
            sql_analysis_enabled: false,
            helpers: &[HELPER_READS_MODEL],
            expected: &[],
            assertions: &[ASSERT_DOUBLED],
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__source__raw_orders", "__ref__orders"),
                ("__ref__orders", "__assert__doubles_amount"),
            ],
            expected_fragments: &[
                "WITH doubled AS (SELECT order_id, amount_doubled FROM __ref__orders)",
            ],
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
            expected_chain: &["stg_orders", "orders"],
            expected_order: &[
                ("__source__raw_orders", "__helper__expected_rows"),
                ("__seed__regions", "__helper__expected_rows"),
                ("__helper__expected_rows", "__expected__orders"),
            ],
            expected_fragments: &[
                "FROM __source__raw_orders AS s JOIN __seed__regions AS r USING (region_id)",
            ],
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
        for fragment in test_case.expected_fragments {
            assert!(
                sql.contains(fragment),
                "{}: {fragment}: {sql}",
                test_case.description
            );
        }
        for marker in ["__ref(", "__source(", "__seed("] {
            assert!(!sql.contains(marker), "{}: {sql}", test_case.description);
        }
        assert!(errors.is_empty(), "{}: {errors:?}", test_case.description);
    }
}
