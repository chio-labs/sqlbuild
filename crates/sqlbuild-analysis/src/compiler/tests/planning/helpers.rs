use serde_json::{Value, json};

use crate::compiler::tests::helpers::{generic_lexical_syntax, plan_json};

/// The rendered SQL of a model test whose real model calls a UDF in its projection.
pub(crate) fn projected_udf_call_sql(dialect: &str) -> String {
    let request = json!({
        "lexicalSyntax": generic_lexical_syntax(),
        "models": [
            {"name": "orders", "querySql": "SELECT o.order_id, __udf(\"is_open\")(o.status) AS is_open FROM __source(\"raw_orders\") AS o"}
        ],
        "functions": [{"name": "is_open", "udfPrefix": "analytics__is_open", "udfSuffix": ""}],
        "tests": [{
            "name": "orders_case", "fileLabel": "tests/orders.sql",
            "payload": {
                "kind": "model",
                "authoredCtes": [{"name": "__source__raw_orders", "sqlBody": "SELECT 1 AS order_id, 'open' AS status"}],
                "expectedCtes": [{"name": "__expected__orders", "sqlBody": "SELECT 1 AS order_id, TRUE AS is_open"}],
                "expectedModelNames": ["orders"]
            }
        }],
        "sqlAnalysisEnabled": true, "sqlAnalysisDialect": dialect
    });
    let response: Value =
        serde_json::from_str(&plan_json(&request.to_string()).expect("planning succeeds"))
            .expect("valid JSON");
    response["artifacts"][0]["sql"]
        .as_str()
        .expect("rendered SQL")
        .to_owned()
}
