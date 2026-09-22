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
