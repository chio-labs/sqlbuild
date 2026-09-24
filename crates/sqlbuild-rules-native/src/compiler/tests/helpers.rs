use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Barrier, Mutex};

use serde_json::{Value, json};

use crate::compiler::_helpers::model_headers::tokenization::{
    MAX_TOKENIZER_WORKERS, TOKENIZER_WORKER_STACK_BYTES, build_tokenizer_pool, parse_batch,
};
use crate::compiler::_helpers::sql_interpolation::substitution::{
    FALLBACK, SUBSTITUTED, UNCHANGED, substitute_batch,
};
use crate::compiler::_helpers::sql_references::extraction::extract;
use crate::compiler::main::sql_test_extraction::extract_batch_json;
use crate::compiler::models::AuthoredValue;

pub(crate) fn scalar_variables_preserve_lexical_boundaries() -> bool {
    let sqls = vec![
        "SELECT @@revision, '@@status', @@@window_start".to_owned(),
        "-- @@revision\nSELECT /* @@status */ 1".to_owned(),
        "SELECT '@@revision''s'".to_owned(),
    ];
    substitute_batch(
        &sqls,
        &[
            ("revision".to_owned(), "7".to_owned()),
            ("status".to_owned(), "ready".to_owned()),
        ],
    ) == vec![
        (
            SUBSTITUTED,
            Some("SELECT 7, 'ready', @@@window_start".to_owned()),
        ),
        (UNCHANGED, None),
        (SUBSTITUTED, Some("SELECT '7''s'".to_owned())),
    ]
}

pub(crate) fn dynamic_or_malformed_sql_requests_fallback() -> bool {
    let sqls = vec![
        "SELECT @@ENV:USER".to_owned(),
        "SELECT @@missing".to_owned(),
        "SELECT @@revision, 'unterminated".to_owned(),
        "SELECT @@revision /* unterminated".to_owned(),
        "SELECT @@révision".to_owned(),
    ];
    substitute_batch(&sqls, &[("revision".to_owned(), "7".to_owned())])
        == vec![(FALLBACK, None); sqls.len()]
}

pub(crate) fn simple_references_preserve_authored_order() -> bool {
    extract(
        "SELECT * FROM __source('orders') UNION ALL SELECT * FROM __dbt_ref(\"shop\", \"customers\")",
    ) == Some(vec![
        ("source".to_owned(), "orders".to_owned(), None, None),
        (
            "dbt_ref".to_owned(),
            "customers".to_owned(),
            Some("shop".to_owned()),
            None,
        ),
    ])
}

pub(crate) fn comments_and_quoted_text_hide_references() -> bool {
    extract("-- __ref(\"ignored\")\nSELECT '__seed(\"also_ignored\")' FROM __ref(orders)")
        == Some(vec![("ref".to_owned(), "orders".to_owned(), None, None)])
}

pub(crate) fn complex_or_malformed_sql_requests_fallback() -> bool {
    [
        "SELECT * FROM __table_fn(\"orders\")(1)",
        "SELECT * FROM __ref(concat('ord', 'ers'))",
        "SELECT * FROM __ref(\"orders\"",
        "SELECT * FROM __ref(\"orders\") /* unterminated",
        "SELECT * FROM __ref(\"orders\") WHERE note = 'unterminated",
        "SELECT * FROM __ref(örders)",
    ]
    .into_iter()
    .all(|sql| extract(sql).is_none())
}

pub(crate) fn nested_authored_headers_preserve_values_and_offsets() -> bool {
    let headers = vec![
        " columns (café (type DECIMAL(10,2))), enabled true".to_owned(),
        "constants (_countries {FR, GB}, _size constant(value 2))".to_owned(),
    ];
    let results = parse_batch(&headers).expect("worker pool builds");
    assert_eq!(results[0].2, None);
    assert_eq!(
        results[0].1.as_ref().expect("column offsets"),
        &vec![("café".to_owned(), 10, 4)]
    );
    assert_eq!(
        results[0].0,
        Some(AuthoredValue::Map(vec![
            (
                "columns".to_owned(),
                AuthoredValue::Map(vec![(
                    "café".to_owned(),
                    AuthoredValue::Map(vec![(
                        "type".to_owned(),
                        AuthoredValue::String("DECIMAL(10,2)".to_owned()),
                    )]),
                )]),
            ),
            ("enabled".to_owned(), AuthoredValue::Boolean(true)),
        ]))
    );
    assert!(matches!(
        results[1].0,
        Some(AuthoredValue::Map(ref values)) if values.len() == 1
    ));
    true
}

pub(crate) fn invalid_headers_return_each_exact_error_in_order() -> bool {
    let headers = vec![
        "schema \"analytics".to_owned(),
        "schema analytics\"mart".to_owned(),
        "schema ${ENV".to_owned(),
    ];
    let results = parse_batch(&headers).expect("worker pool builds");
    assert_eq!(
        results
            .iter()
            .map(|result| result.2.as_deref())
            .collect::<Vec<_>>(),
        vec![
            Some("unterminated double-quoted string at position 7"),
            Some("unexpected double quote inside bare value at position 16; quote the whole value"),
            Some("unterminated template value at position 7"),
        ]
    );
    true
}

pub(crate) fn nested_and_root_columns_return_only_root_offsets() -> bool {
    let headers = vec![
        "config (columns (nested (type INTEGER))), columns (top (type INTEGER))".to_owned(),
        "config (columns (nested (type INTEGER)))".to_owned(),
    ];

    let results = parse_batch(&headers).expect("worker pool builds");

    assert_eq!(
        results[0].1.as_ref().expect("column offsets"),
        &vec![("top".to_owned(), 51, 3)]
    );
    assert_eq!(
        results[1].1.as_ref().expect("column offsets"),
        &Vec::<(String, usize, usize)>::new()
    );
    true
}

pub(crate) fn batch_sizes_bound_workers_by_contract() -> bool {
    for (header_count, expected_workers) in [(0, 1), (1, 1), (3, 3), (5, MAX_TOKENIZER_WORKERS)] {
        let pool = build_tokenizer_pool(header_count).expect("worker pool builds");
        assert_eq!(pool.current_num_threads(), expected_workers);
    }
    assert_eq!(TOKENIZER_WORKER_STACK_BYTES, 16 * 1024 * 1024);
    true
}

pub(crate) fn mixed_expanded_tests_preserve_order_and_payloads() -> bool {
    let response = extract_batch_json(r#"{"tests":[{"sql":"WITH helper AS (SELECT 1 AS id), __source__raw_orders AS (SELECT id FROM helper), __expected__orders AS (SELECT id FROM helper), __assert__positive AS (SELECT id FROM helper WHERE id < 0) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"},{"sql":"WITH input AS (SELECT 1 AS value), __udf_actual__ AS (SELECT __udf(\"increment\")(value) AS value FROM input), __udf_expected__ AS (SELECT 2 AS value) SELECT 1","fileLabel":"tests/increment.sql","mode":"udf"}]}"#).expect("batch succeeds");
    let payload: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");
    assert_eq!(payload[0]["kind"], "model");
    assert_eq!(payload[0]["authored"][0][0], "helper");
    assert_eq!(payload[0]["expectedModels"][0], "orders");
    assert_eq!(payload[0]["assertionNames"][0], "positive");
    assert_eq!(payload[1]["kind"], "direct");
    assert_eq!(payload[1]["mode"], "udf");
    assert_eq!(payload[1]["actual"][0], "__udf_actual__");
    true
}

pub(crate) fn dependent_assertion_returns_authoritative_error() -> bool {
    let error = extract_batch_json(r#"{"tests":[{"sql":"WITH __source__raw_orders AS (SELECT 1 AS id), __expected__orders AS (SELECT 1 AS id), __assert__same AS (SELECT id FROM __expected__orders) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"}]}"#).expect_err("dependency is rejected");
    assert!(error.contains("'__assert__same' must not depend on '__expected__orders'"));
    true
}

pub(crate) fn quoted_ctes_and_implicit_alias_preserve_payload() -> bool {
    let response = extract_batch_json(r#"{"tests":[{"sql":"WITH \"__source__raw_orders\" AS (SELECT 1 AS id), \"__expected__orders\" AS (SELECT CAST(1 AS INTEGER) id) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"}]}"#).expect("batch succeeds");
    let payload: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");
    assert_eq!(payload[0]["authored"][0][0], "__source__raw_orders");
    assert_eq!(payload[0]["expected"][0][1], "SELECT CAST(1 AS INTEGER) id");
    true
}

pub(crate) fn empty_model_fixture_marker_preserves_direct_mode_validation() -> bool {
    let response = extract_batch_json(r#"{"tests":[{"sql":"WITH __source__raw_orders AS (SELECT * FROM __empty_fixture()), __expected__orders AS (SELECT * FROM __empty_fixture()) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"}]}"#).expect("model marker succeeds");
    let payload: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");
    assert_eq!(payload[0]["expectedModels"][0], "orders");

    let error = extract_batch_json(r#"{"tests":[{"sql":"WITH __udf_actual__ AS (SELECT 1 AS value), __udf_expected__ AS (SELECT * FROM __empty_fixture()) SELECT 1","fileLabel":"tests/function.sql","mode":"udf"}]}"#).expect_err("direct marker is rejected");
    assert!(error.contains("must not use SELECT * in __udf_expected__ CTEs"));
    true
}

pub(crate) fn concurrent_requests_initialize_shared_template_once() -> bool {
    let templates = Arc::new(Mutex::new(HashMap::new()));
    let starts = Arc::new(Barrier::new(4));
    let initializations = Arc::new(AtomicUsize::new(0));
    let threads = (0..4)
        .map(|_| {
            let templates = Arc::clone(&templates);
            let starts = Arc::clone(&starts);
            let initializations = Arc::clone(&initializations);
            std::thread::spawn(move || {
                starts.wait();
                crate::compiler::_helpers::sql_tests::planning::cached_analysis_template(
                    "SELECT 1",
                    &templates,
                    || {
                        initializations.fetch_add(1, Ordering::Relaxed);
                        None
                    },
                )
                .expect("test assumption must hold")
            })
        })
        .collect::<Vec<_>>();

    for thread in threads {
        assert!(thread.join().expect("test assumption must hold").is_none());
    }
    assert_eq!(initializations.load(Ordering::Relaxed), 1);
    true
}

pub(crate) fn model_test_batch_returns_ordered_artifact() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": [
                    {
                        "name": "stg_orders",
                        "querySql": "SELECT * FROM __source(\"raw_orders\")",
                        "modelDependencies": []
                    },
                    {
                        "name": "orders",
                        "querySql": "SELECT * FROM __ref(\"stg_orders\")",
                        "modelDependencies": ["stg_orders"]
                    }
                ],
                "functions": [],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedModelNames": ["orders"],
                        "assertionCtes": []
                    }
                }],
                "sqlAnalysisEnabled": true,
                "sqlAnalysisDialect": "duckdb",
                "setDifferenceOperator": "EXCEPT",
                "workers": 2
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        response["artifacts"][0]["modelNames"],
        json!(["stg_orders", "orders"])
    );
    let sql = response["artifacts"][0]["sql"]
        .as_str()
        .expect("test assumption must hold");
    assert!(sql.contains("__source__raw_orders AS (SELECT 1 AS order_id)"));
    assert!(sql.contains("__ref__stg_orders AS"));
    assert!(sql.contains("__actual__orders AS"));
    assert!(sql.contains("__expected__orders AS"));
    assert_eq!(response["artifacts"][0]["warnings"], json!([]));
    assert!(response["planningNs"].as_u64().is_some());
    assert!(response["renderingNs"].as_u64().is_some());
    true
}

pub(crate) fn unicode_cte_after_leading_with_preserves_identifier() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": [{
                    "name": "orders",
                    "querySql": "WITH \"订单行\" AS (SELECT order_id FROM __source(\"raw_orders\")) SELECT order_id FROM \"订单行\"",
                    "modelDependencies": []
                }],
                "functions": [],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedModelNames": ["orders"],
                        "assertionCtes": []
                    }
                }],
                "sqlAnalysisEnabled": true,
                "sqlAnalysisDialect": "duckdb"
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let sql = response["artifacts"][0]["sql"]
        .as_str()
        .expect("test assumption must hold");
    assert!(sql.contains("WITH __source__raw_orders AS"));
    assert!(sql.contains("订单行"), "{sql}");
    true
}

pub(crate) fn unresolved_reference_fast_rejection_preserves_warning() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": [{
                    "name": "orders",
                    "querySql": "SELECT * FROM __SOURCE(\"missing_orders\")",
                    "modelDependencies": []
                }],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "expectedModelNames": ["orders"]
                    }
                }],
                "sqlAnalysisEnabled": true,
                "sqlAnalysisDialect": "duckdb"
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        response["artifacts"][0]["warnings"],
        json!([{
            "modelName": "orders",
            "severity": "error",
            "message": "test 'orders_case': model 'orders' references __source('missing_orders') which has no mock"
        }])
    );
    true
}

pub(crate) fn ordered_comparison_batch_preserves_order() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_rendering::render_json(
            &json!({
                "workers": 2,
                "requests": [{
                    "chain": [{
                        "modelName": "orders",
                        "resolvedSql": "SELECT 1 AS id",
                        "expectedCteSql": "SELECT 1 AS id"
                    }],
                    "assertions": [],
                    "sqlAnalysisEnabled": true,
                    "setDifferenceOperator": "EXCEPT",
                    "sqlAnalysisDialect": "duckdb"
                }]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let sql = response[0]["sql"]
        .as_str()
        .expect("test assumption must hold");
    assert!(
        sql.contains("__actual__orders AS (SELECT 1 AS id)"),
        "{sql}"
    );
    assert!(sql.contains("__expected__orders AS (SELECT 1 AS id)"));
    assert!(sql.contains("EXCEPT"));
    true
}

pub(crate) fn shared_textual_chain_renders_each_model_once() -> bool {
    const LAYERS: usize = 16;
    let mut models: Vec<Value> = vec![json!({
        "name": "orders_00",
        "querySql": "SELECT order_id, amount FROM __source(\"raw_orders\")",
        "modelDependencies": []
    })];
    for side in ["left", "right"] {
        models.push(diamond_model(1, side, "orders_00", "orders_00"));
    }
    for layer in 2..=LAYERS {
        let previous: String = format!("orders_{:02}_left", layer - 1);
        let other: String = format!("orders_{:02}_right", layer - 1);
        for side in ["left", "right"] {
            models.push(diamond_model(layer, side, &previous, &other));
        }
    }
    let top: String = format!("orders_{LAYERS:02}_left");
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": models,
                "functions": [],
                "tests": [{
                    "name": "orders_totals",
                    "fileLabel": "tests/orders_totals.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id, 1 AS amount"
                        }],
                        "expectedCtes": [{
                            "name": format!("__expected__{top}"),
                            "sqlBody": "SELECT 1 AS order_id, 65536 AS amount"
                        }],
                        "expectedModelNames": [top],
                        "assertionCtes": []
                    }
                }],
                "sqlAnalysisEnabled": false,
                "sqlAnalysisDialect": "duckdb",
                "setDifferenceOperator": "EXCEPT",
                "workers": 1
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let sql = response["artifacts"][0]["sql"]
        .as_str()
        .expect("test assumption must hold");
    assert!(sql.len() < 50_000, "rendered {} bytes", sql.len());
    for layer in 1..LAYERS {
        for side in ["left", "right"] {
            let definition = format!("__ref__orders_{layer:02}_{side} AS (");
            assert_eq!(sql.matches(&definition).count(), 1, "{definition}");
        }
    }
    assert_eq!(sql.matches("__ref__orders_00 AS (").count(), 1);
    true
}

fn diamond_model(layer: usize, side: &str, previous: &str, other: &str) -> Value {
    json!({
        "name": format!("orders_{layer:02}_{side}"),
        "querySql": format!(
            "SELECT a.order_id, a.amount + b.amount AS amount \
             FROM __ref(\"{previous}\") AS a \
             INNER JOIN __ref(\"{other}\") AS b ON a.order_id = b.order_id"
        ),
        "modelDependencies": [previous, other]
    })
}

fn deep_diamond_models(layers: usize) -> Vec<Value> {
    let mut models: Vec<Value> = vec![json!({
        "name": "orders_00",
        "querySql": "SELECT o.order_id, o.amount FROM __source(\"raw_orders\") AS o \
                     INNER JOIN __source(\"raw_customers\") AS c ON o.customer_id = c.customer_id",
        "modelDependencies": []
    })];
    for side in ["left", "right"] {
        models.push(diamond_model(1, side, "orders_00", "orders_00"));
    }
    for layer in 2..=layers {
        let previous: String = format!("orders_{:02}_left", layer - 1);
        let other: String = format!("orders_{:02}_right", layer - 1);
        for side in ["left", "right"] {
            models.push(diamond_model(layer, side, &previous, &other));
        }
    }
    models
}

fn plan_deep_diamond_with_missing_mock(sql_analysis_enabled: bool) -> Value {
    const LAYERS: usize = 12;
    let top: String = format!("orders_{LAYERS:02}_left");
    serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": deep_diamond_models(LAYERS),
                "tests": [{
                    "name": "orders_totals",
                    "fileLabel": "tests/orders_totals.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_customers",
                            "sqlBody": "SELECT 1 AS customer_id"
                        }],
                        "expectedCtes": [{
                            "name": format!("__expected__{top}"),
                            "sqlBody": "SELECT 1 AS order_id, 1 AS amount"
                        }],
                        "expectedModelNames": [top],
                    }
                }],
                "sqlAnalysisEnabled": sql_analysis_enabled,
                "sqlAnalysisDialect": "duckdb",
                "renderSql": false
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold")
}

pub(crate) fn deep_shared_graph_reports_missing_mock_once() -> bool {
    for sql_analysis_enabled in [true, false] {
        let response = plan_deep_diamond_with_missing_mock(sql_analysis_enabled);
        assert_eq!(
            response["artifacts"][0]["warnings"],
            json!([{
                "modelName": "orders_00",
                "severity": "error",
                "message": "test 'orders_totals': model 'orders_00' references __source('raw_orders') which has no mock"
            }]),
            "sql_analysis_enabled={sql_analysis_enabled}"
        );
    }
    true
}

pub(crate) fn plan_without_rendering_returns_executable_steps() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": [
                    {
                        "name": "stg_orders",
                        "querySql": "SELECT * FROM __source(\"raw_orders\")",
                        "modelDependencies": []
                    },
                    {
                        "name": "orders",
                        "querySql": "SELECT * FROM __ref(\"stg_orders\")",
                        "modelDependencies": ["stg_orders"]
                    }
                ],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedModelNames": ["orders"],
                        "assertionCtes": [{
                            "name": "__assert__positive",
                            "sqlBody": "SELECT * FROM __ref(\"orders\") WHERE order_id < 0"
                        }]
                    }
                }],
                "sqlAnalysisEnabled": false,
                "sqlAnalysisDialect": "duckdb",
                "renderSql": false
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let artifact = &response["artifacts"][0];
    assert_eq!(artifact["sql"], Value::Null);
    assert_eq!(artifact["chain"][0]["modelName"], json!("stg_orders"));
    assert_eq!(artifact["chain"][0]["expectedCteSql"], Value::Null);
    assert_eq!(
        artifact["chain"][1]["liftedCtes"],
        json!([["__ref__stg_orders", "SELECT * FROM (SELECT 1 AS order_id)"]])
    );
    assert_eq!(
        artifact["chain"][1]["comparisonBodySql"],
        json!("SELECT * FROM __ref__stg_orders")
    );
    assert_eq!(
        artifact["chain"][1]["expectedCteSql"],
        json!("SELECT 1 AS order_id")
    );
    assert_eq!(artifact["assertions"][0]["name"], json!("positive"));
    assert_eq!(
        artifact["assertions"][0]["comparisonBodySql"],
        json!("SELECT * FROM __ref__orders WHERE order_id < 0")
    );
    assert_eq!(
        artifact["assertions"][0]["liftedCtes"][1],
        json!(["__ref__orders", "SELECT * FROM __ref__stg_orders"])
    );
    assert!(
        artifact["assertions"][0]["resolvedSql"]
            .as_str()
            .is_some_and(|sql| sql.contains("__ref__orders AS (SELECT * FROM __ref__stg_orders)"))
    );
    true
}

pub(crate) fn upstream_fallback_resolves() -> bool {
    let request = json!({
        "models": [
            {"name": "stg_orders", "querySql": "SELECT __udf(\"identity_value\")(order_id) AS order_id FROM __source(\"raw_orders\")"},
            {"name": "orders", "querySql": "SELECT * FROM __ref(\"stg_orders\")", "modelDependencies": ["stg_orders"]}
        ],
        "functions": [{"name": "identity_value", "udfPrefix": "identity_value(", "udfSuffix": ")"}],
        "tests": [{
            "name": "orders_case", "fileLabel": "tests/orders.sql",
            "payload": {
                "kind": "model",
                "authoredCtes": [{"name": "__source__raw_orders", "sqlBody": "SELECT 1 AS order_id"}],
                "expectedCtes": [{"name": "__expected__orders", "sqlBody": "SELECT 1 AS order_id"}],
                "expectedModelNames": ["orders"],
                "assertionCtes": [{"name": "__assert__positive", "sqlBody": "SELECT * FROM __ref(\"orders\") WHERE order_id < 0"}]
            }
        }],
        "sqlAnalysisEnabled": true, "sqlAnalysisDialect": "duckdb"
    });
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(&request.to_string())
            .expect("planning succeeds"),
    )
    .expect("valid JSON");
    let artifact = &response["artifacts"][0];
    assert_eq!(artifact["warnings"], json!([]));
    let sql = artifact["sql"].as_str().expect("rendered SQL");
    assert!(!sql.contains("__ref(\""));
    assert!(sql.contains("identity_value((order_id))"), "{sql}");
    assert!(sql.contains("__ref__stg_orders"));
    true
}

pub(crate) fn chain_resolution_orders_unmocked_models() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_chain_resolution::resolve_chains_json(
            &json!({
                "models": deep_diamond_models(2),
                "tests": [
                    {
                        "name": "orders_totals",
                        "fileLabel": "tests/orders_totals.sql",
                        "payload": {
                            "kind": "model",
                            "authoredCtes": [{
                                "name": "__ref__orders_01_right",
                                "sqlBody": "SELECT 1 AS order_id, 1 AS amount"
                            }],
                            "expectedModelNames": ["orders_02_left"]
                        }
                    },
                    {
                        "name": "direct_case",
                        "fileLabel": "tests/direct.sql",
                        "payload": {
                            "kind": "direct",
                            "mode": "macro",
                            "actualCte": {"name": "__macro_actual__", "sqlBody": "SELECT 1"},
                            "expectedCte": {"name": "__macro_expected__", "sqlBody": "SELECT 1"}
                        }
                    }
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        response["chains"],
        json!([["orders_00", "orders_01_left", "orders_02_left"], []])
    );
    true
}

pub(crate) fn difference_sample_lifts_generated_ctes_and_bounds_rows() -> bool {
    let request = |use_top_clause: bool| {
        json!({
            "step": {
                "modelName": "orders",
                "resolvedSql": "WITH __ref__stg_orders AS (SELECT 1 AS order_id) SELECT * FROM __ref__stg_orders",
                "expectedCteSql": "SELECT 2 AS order_id",
                "liftedCtes": [["__ref__stg_orders", "SELECT 1 AS order_id"]],
                "comparisonBodySql": "SELECT * FROM __ref__stg_orders"
            },
            "sqlAnalysisEnabled": false,
            "setDifferenceOperator": "EXCEPT",
            "sqlAnalysisDialect": "duckdb",
            "direction": "missing",
            "sampleLimit": 3,
            "useTopClause": use_top_clause
        })
        .to_string()
    };
    let limited: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            &request(false),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    let top: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            &request(true),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        limited["sql"],
        json!(
            "WITH __ref__stg_orders AS (SELECT 1 AS order_id),\n\
             __actual AS (SELECT * FROM __ref__stg_orders),\n\
             __expected AS (SELECT 2 AS order_id)\n\
             SELECT * FROM (SELECT * FROM __expected EXCEPT SELECT * FROM __actual) \
             AS __sqlbuild_difference LIMIT 3"
        )
    );
    assert!(
        top["sql"]
            .as_str()
            .is_some_and(|sql| sql.contains("SELECT TOP 3 * FROM (") && !sql.contains("LIMIT"))
    );
    true
}

fn step_sql_bytes(step: &Value) -> usize {
    let text_len = |value: &Value| value.as_str().map_or(0, str::len);
    let lifted: usize = step["liftedCtes"].as_array().map_or(0, |ctes| {
        ctes.iter()
            .map(|cte| text_len(&cte[0]) + text_len(&cte[1]))
            .sum()
    });
    text_len(&step["resolvedSql"]) + text_len(&step["comparisonBodySql"]) + lifted
}

pub(crate) fn long_chain_plan_output_stays_linear() -> bool {
    const MODELS: usize = 200;
    let mut models: Vec<Value> = vec![json!({
        "name": "orders_000",
        "querySql": "SELECT order_id, amount FROM __source(\"raw_orders\")",
        "modelDependencies": []
    })];
    for index in 1..MODELS {
        let previous: String = format!("orders_{:03}", index - 1);
        models.push(json!({
            "name": format!("orders_{index:03}"),
            "querySql": format!(
                "SELECT order_id, amount + 1 AS amount FROM __ref(\"{previous}\")"
            ),
            "modelDependencies": [previous]
        }));
    }
    let tip: String = format!("orders_{:03}", MODELS - 1);
    for sql_analysis_enabled in [true, false] {
        let response: Value = serde_json::from_str(
            &crate::compiler::main::sql_test_planning::plan_and_render_json(
                &json!({
                    "models": models,
                    "tests": [{
                        "name": "orders_tip",
                        "fileLabel": "tests/orders_tip.sql",
                        "payload": {
                            "kind": "model",
                            "authoredCtes": [{
                                "name": "__source__raw_orders",
                                "sqlBody": "SELECT 1 AS order_id, 0 AS amount"
                            }],
                            "expectedCtes": [{
                                "name": format!("__expected__{tip}"),
                                "sqlBody": "SELECT 1 AS order_id, 199 AS amount"
                            }],
                            "expectedModelNames": [tip],
                        }
                    }],
                    "sqlAnalysisEnabled": sql_analysis_enabled,
                    "sqlAnalysisDialect": "duckdb"
                })
                .to_string(),
            )
            .expect("test assumption must hold"),
        )
        .expect("test assumption must hold");
        let artifact = &response["artifacts"][0];
        let sql = artifact["sql"].as_str().expect("test assumption must hold");
        let chain = artifact["chain"]
            .as_array()
            .expect("test assumption must hold");
        assert_eq!(chain.len(), MODELS);
        let step_bytes: usize = chain.iter().map(step_sql_bytes).sum();
        assert!(
            step_bytes <= 3 * sql.len(),
            "step SQL {step_bytes} bytes for {} rendered bytes",
            sql.len()
        );
        assert!(
            chain[..MODELS - 1]
                .iter()
                .all(|step| step_sql_bytes(step) == 0)
        );

        let mut padded_chain: Vec<Value> = chain.clone();
        for step in &mut padded_chain[..MODELS - 1] {
            step["resolvedSql"] = json!("SELECT unrendered_column FROM unrendered_relation");
            step["liftedCtes"] = json!([["unrendered_cte", "SELECT 1"]]);
            step["comparisonBodySql"] = json!("SELECT unrendered_column");
        }
        let rendered: Value = serde_json::from_str(
            &crate::compiler::main::sql_test_rendering::render_json(
                &json!({
                    "requests": [{
                        "chain": padded_chain,
                        "assertions": [],
                        "sqlAnalysisEnabled": sql_analysis_enabled,
                        "setDifferenceOperator": "EXCEPT",
                        "sqlAnalysisDialect": "duckdb"
                    }]
                })
                .to_string(),
            )
            .expect("test assumption must hold"),
        )
        .expect("test assumption must hold");
        assert_eq!(rendered[0]["sql"].as_str(), Some(sql));
    }
    true
}

fn render_single(request: Value) -> String {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_rendering::render_json(
            &json!({"requests": [request]}).to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    response[0]["sql"]
        .as_str()
        .expect("test assumption must hold")
        .to_string()
}

fn partial_expected_step() -> Value {
    json!({
        "modelName": "orders",
        "resolvedSql": "SELECT 1 AS order_id, 'paid' AS status, 10 AS amount",
        "expectedCteSql": "SELECT 'paid' AS status, 1 AS order_id",
        "expectedColumns": ["status", "order_id"]
    })
}

pub(crate) fn partial_expected_columns_project_both_sides() -> bool {
    let sql = render_single(json!({
        "chain": [partial_expected_step()],
        "sqlAnalysisEnabled": false,
        "sqlAnalysisDialect": "duckdb"
    }));
    assert!(sql.contains("(SELECT COUNT(*) FROM __actual__orders) AS actual_count"));
    assert!(sql.contains(
        "(SELECT status, order_id FROM __actual__orders EXCEPT SELECT status, order_id FROM __expected__orders) AS __sqlbuild_mismatch"
    ), "{sql}");
    assert!(sql.contains(
        "(SELECT status, order_id FROM __expected__orders EXCEPT SELECT status, order_id FROM __actual__orders) AS __sqlbuild_missing"
    ), "{sql}");
    assert!(!sql.contains("SELECT * FROM __actual__orders"));
    true
}

pub(crate) fn actual_probe_selects_zero_rows_from_step() -> bool {
    let sql = render_single(json!({
        "chain": [partial_expected_step()],
        "sqlAnalysisEnabled": false,
        "sqlAnalysisDialect": "duckdb",
        "probeStepIndex": 0
    }));
    assert!(sql.starts_with("WITH __actual__orders AS ("), "{sql}");
    assert!(
        sql.ends_with("\nSELECT * FROM __actual__orders WHERE 1 = 0"),
        "{sql}"
    );
    assert!(!sql.contains("UNION ALL"));
    true
}

pub(crate) fn sqlserver_difference_sample_projects_bracketed_columns() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            &json!({
                "step": {
                    "modelName": "orders",
                    "resolvedSql": "SELECT 1 AS [Order Id], 10 AS amount, 'paid' AS status",
                    "expectedCteSql": "SELECT 1 AS [Order Id], 10 AS amount",
                    "expectedColumns": ["[Order Id]", "amount"]
                },
                "sqlAnalysisEnabled": true,
                "setDifferenceOperator": "EXCEPT",
                "sqlAnalysisDialect": "tsql",
                "direction": "unexpected",
                "sampleLimit": 3,
                "useTopClause": true
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    let sql = response["sql"].as_str().expect("test assumption must hold");
    assert!(sql.contains(
        "SELECT TOP 3 * FROM (SELECT [Order Id], amount FROM __actual EXCEPT SELECT [Order Id], amount FROM __expected) AS __sqlbuild_difference"
    ), "{sql}");
    true
}

pub(crate) fn snowflake_plan_keeps_quoted_expected_columns() -> bool {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_planning::plan_and_render_json(
            &json!({
                "models": [{
                    "name": "orders",
                    "querySql": "SELECT order_id AS \"Order Id\", status, amount FROM __source(\"raw_orders\")",
                    "modelDependencies": []
                }],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id, 'paid' AS status, 10 AS amount"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 'paid' AS status, 1 AS \"Order Id\""
                        }],
                        "expectedModelNames": ["orders"]
                    }
                }],
                "sqlAnalysisEnabled": false,
                "sqlAnalysisDialect": "snowflake"
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    let artifact = &response["artifacts"][0];
    assert_eq!(
        artifact["chain"][0]["expectedColumns"],
        json!(["status", "\"Order Id\""])
    );
    let sql = artifact["sql"].as_str().expect("test assumption must hold");
    assert!(sql.contains(
        "SELECT status, \"Order Id\" FROM __actual__orders EXCEPT SELECT status, \"Order Id\" FROM __expected__orders"
    ), "{sql}");
    true
}
