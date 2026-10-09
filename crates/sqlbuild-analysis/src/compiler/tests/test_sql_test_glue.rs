use serde_json::{Value, json};

use crate::compiler::main::sql_test_chain_resolution::resolve_chains_json;
use crate::compiler::main::sql_test_chains::resolve_sql_test_chains;
use crate::compiler::main::sql_test_glue::plan_sql_test_batch;
use crate::compiler::main::sql_test_plan_errors::sql_test_plan_error_messages;
use crate::compiler::main::sql_test_planning::plan_and_render_json;
use crate::compiler::models::{SqlTestPlan, SqlTestPlanWarning};
use crate::compiler::tests::test_types::{
    GlueErrorProjectionTestCase, GluePlanParityTestCase, GluePlannerErrorTestCase,
};

/// A mocked model test, a test missing its source mock and a UDF test over two models.
const GLUE_REQUEST: &str = r#"{
  "lexicalSyntax": {
    "backslashEscapeQuotes": [], "escapeStringPrefix": false, "rawStringPrefix": false,
    "tripleQuotedStrings": false, "nestedBlockComments": false, "lineCommentPrefixes": ["--"]
  },
  "models": [
    {"name": "stg_orders", "querySql": "SELECT order_id, amount FROM __source(\"raw_orders\")"},
    {
      "name": "orders",
      "querySql": "WITH big AS (SELECT * FROM __ref(\"stg_orders\") WHERE __udf(\"udf__is_big\")(amount)) SELECT order_id FROM big",
      "modelDependencies": ["stg_orders"]
    }
  ],
  "functions": [{
    "name": "udf__is_big", "udfPrefix": "main.udf__is_big(", "udfSuffix": ")",
    "tableFunctionPrefix": "main.udf__is_big(", "tableFunctionSuffix": ")"
  }],
  "tests": [
    {
      "name": "mocked", "fileLabel": "tests/mocked.sql",
      "payload": {
        "kind": "model",
        "authoredCtes": [
          {"name": "__source__raw_orders", "sqlBody": "SELECT 1 AS order_id, 5 AS amount"},
          {"name": "__seed__unused", "sqlBody": "SELECT 1 AS id"}
        ],
        "expectedCtes": [{"name": "__expected__orders", "sqlBody": "SELECT 1 AS order_id"}],
        "expectedModelNames": ["orders"],
        "assertionCtes": [{
          "name": "__assert__orders_exist",
          "sqlBody": "SELECT * FROM __ref(\"orders\") WHERE 1 = 0"
        }],
        "readHelperNames": [], "referenceTargetModelNames": []
      }
    },
    {
      "name": "missing_mock", "fileLabel": "tests/missing_mock.sql",
      "payload": {
        "kind": "model",
        "authoredCtes": [{"name": "__seed__unused", "sqlBody": "SELECT 1 AS id"}],
        "expectedCtes": [{"name": "__expected__orders", "sqlBody": "SELECT 1 AS order_id"}],
        "expectedModelNames": ["orders"],
        "readHelperNames": [], "referenceTargetModelNames": []
      }
    },
    {
      "name": "udf_case", "fileLabel": "tests/udf_case.sql",
      "payload": {
        "kind": "direct", "mode": "udf",
        "actualCte": {
          "name": "__udf_actual__", "sqlBody": "SELECT __udf(\"udf__is_big\")(150) AS is_big"
        },
        "expectedCte": {"name": "__udf_expected__", "sqlBody": "SELECT TRUE AS is_big"}
      }
    }
  ]
}"#;

#[test]
fn given_typed_requests_when_planning_then_plans_and_chains_equal_the_json_entry_points() {
    let test_cases = [
        GluePlanParityTestCase {
            description: "generic SQL, planned without rendering",
            dialect: None,
            render_sql: false,
            expected_plan_count: 3,
            expected_missing_mock_severity: "error",
        },
        GluePlanParityTestCase {
            description: "DuckDB, rendered",
            dialect: Some("duckdb"),
            render_sql: true,
            expected_plan_count: 3,
            expected_missing_mock_severity: "error",
        },
        GluePlanParityTestCase {
            description: "Snowflake, rendered",
            dialect: Some("snowflake"),
            render_sql: true,
            expected_plan_count: 3,
            expected_missing_mock_severity: "error",
        },
        GluePlanParityTestCase {
            description: "SQL Server rejects nested WITH and renders anyway",
            dialect: Some("tsql"),
            render_sql: true,
            expected_plan_count: 3,
            expected_missing_mock_severity: "error",
        },
    ];
    let without_timings = |mut value: Value| {
        for key in ["planningNs", "renderingNs"] {
            let _ = value.as_object_mut().map(|object| object.remove(key));
        }
        value
    };
    for test_case in test_cases {
        let mut request: Value = serde_json::from_str(GLUE_REQUEST).expect("valid request");
        request["sqlAnalysisDialect"] = json!(test_case.dialect);
        request["renderSql"] = json!(test_case.render_sql);
        request["includePlan"] = json!(!test_case.render_sql);
        let typed = plan_sql_test_batch(serde_json::from_value(request.clone()).expect("typed"))
            .expect("typed plans");
        let typed: Value = without_timings(serde_json::to_value(&typed).expect("serializable"));
        let json: Value = without_timings(
            serde_json::from_str(&plan_and_render_json(&request.to_string()).expect("plans"))
                .expect("JSON plans"),
        );
        let typed_chains = resolve_sql_test_chains(
            serde_json::from_value(request.clone()).expect("typed chains request"),
        )
        .expect("typed chains");
        let json_chains: Value =
            serde_json::from_str(&resolve_chains_json(&request.to_string()).expect("chains"))
                .expect("JSON chains");
        assert_eq!(
            (
                typed["artifacts"].as_array().map(Vec::len),
                typed["artifacts"][1]["warnings"][0]["severity"].clone(),
                typed == json,
                json!({"chains": typed_chains}) == json_chains,
            ),
            (
                Some(test_case.expected_plan_count),
                json!(test_case.expected_missing_mock_severity),
                true,
                true,
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_test_without_compiler_reads_when_planning_then_the_typed_batch_returns_its_error() {
    let test_cases = [
        GluePlannerErrorTestCase {
            description: "helper reads are required for model tests",
            payload_field: "readHelperNames",
            expected_error_prefix: "planner_input:",
        },
        GluePlannerErrorTestCase {
            description: "reference targets are required for model tests",
            payload_field: "referenceTargetModelNames",
            expected_error_prefix: "planner_input:",
        },
    ];
    for test_case in test_cases {
        let mut request: Value = serde_json::from_str(GLUE_REQUEST).expect("valid request");
        request["tests"][0]["payload"][test_case.payload_field] = json!(null);
        let error = plan_sql_test_batch(serde_json::from_value(request).expect("typed")).err();
        assert_eq!(
            error.map(|message| message.starts_with(test_case.expected_error_prefix)),
            Some(true),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_plan_warnings_when_projecting_errors_then_each_distinct_error_message_is_kept_in_order() {
    let test_cases = [
        GlueErrorProjectionTestCase {
            description: "warnings are not errors",
            warnings: &[("warning", "mock is unreachable"), ("info", "note")],
            expected_messages: &[],
        },
        GlueErrorProjectionTestCase {
            description: "repeated errors are reported once, in first-seen order",
            warnings: &[
                ("error", "b has no mock"),
                ("warning", "a is unreachable"),
                ("error", "a has no mock"),
                ("error", "b has no mock"),
            ],
            expected_messages: &["b has no mock", "a has no mock"],
        },
    ];
    for test_case in test_cases {
        let plan = SqlTestPlan {
            sql: None,
            chain: Vec::new(),
            assertions: Vec::new(),
            model_names: Vec::new(),
            warnings: test_case
                .warnings
                .iter()
                .map(|(severity, message)| SqlTestPlanWarning {
                    model_name: None,
                    severity,
                    message: (*message).to_owned(),
                })
                .collect(),
        };
        assert_eq!(
            sql_test_plan_error_messages(&plan),
            test_case.expected_messages.to_vec(),
            "{}",
            test_case.description
        );
    }
}
