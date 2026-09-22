use crate::query_analysis::main::analyze_project_compact::analyze_project_compact_json;
use serde_json::{Value, json};

pub(crate) fn borrowed_facts_preserve_named_outputs_and_terminal_sources() -> bool {
    let schema: polyglot_sql::ValidationSchema = serde_json::from_value(json!({
        "tables": [{"name": "orders", "columns": [
            {"name": "order_id", "type": "BIGINT", "nullable": false},
            {"name": "selected_id", "type": "BIGINT", "nullable": true}
        ]}]
    }))
    .expect("valid schema");
    let expression = polyglot_sql::parse_one(
        "WITH renamed AS (SELECT order_id AS selected_id FROM orders), nested AS (SELECT * FROM (SELECT selected_id FROM renamed) AS selected_orders(order_key)) SELECT order_key FROM nested",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let facts = crate::query_analysis::borrowed_facts::infer(
        &expression,
        Some(&schema),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(facts.len(), 1);
    assert_eq!(facts[0].name, "order_key");
    assert_eq!(
        *facts[0].upstream,
        std::collections::BTreeSet::from([("orders".to_string(), "order_id".to_string())])
    );
    assert_eq!(
        facts[0].nullability,
        polyglot_sql::ProjectionNullability::NonNull
    );
    let expression = polyglot_sql::parse_one(
        "WITH combined AS (SELECT order_id AS first_key FROM orders UNION ALL BY NAME SELECT order_id AS second_key FROM orders) SELECT first_key, second_key FROM combined",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let facts = crate::query_analysis::borrowed_facts::infer(
        &expression,
        Some(&schema),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(facts.len(), 2);
    assert!(
        facts
            .iter()
            .all(|fact| fact.nullability == polyglot_sql::ProjectionNullability::Nullable)
    );
    let types = crate::query_analysis::compatibility_types::infer(
        &expression,
        Some(&schema),
        &std::collections::HashMap::new(),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(types.get("first_key").map(String::as_str), Some("BIGINT"));
    assert_eq!(types.get("second_key").map(String::as_str), Some("BIGINT"));
    true
}

pub(crate) fn combined_queries_preserve_standalone_binding() -> bool {
    let schema = json!({"strict": true, "tables": [
        {"name": "orders", "columns": [{"name": "order_id", "type": "BIGINT"}]},
        {"name": "customers", "columns": [{"name": "customer_id", "type": "BIGINT"}]}
    ]});
    for sql in [
        "SELECT order_id FROM orders",
        "SELECT missing FROM orders",
        "WITH selected AS (SELECT order_id FROM orders) SELECT order_id > 0 AS result FROM selected",
        "WITH first_pass AS (SELECT CAST(order_id AS DOUBLE) AS amount, order_id AS unused FROM orders), second_pass AS (SELECT amount AS total FROM first_pass) SELECT total FROM second_pass",
        "WITH first_pass (selected_id, unused_id) AS (SELECT order_id, order_id + 1 FROM orders) SELECT selected_id FROM first_pass",
        "WITH first_pass AS (SELECT order_id FROM orders), combined AS (SELECT order_id FROM first_pass UNION ALL SELECT order_id FROM orders) SELECT order_id FROM combined",
        "WITH selected AS (SELECT order_id FROM orders) SELECT order_id FROM selected WHERE order_id IS NOT NULL",
        "WITH orders AS (SELECT * FROM orders), keys AS (SELECT order_id FROM orders WHERE order_id IS NOT NULL UNION ALL SELECT 0 AS order_id), selected AS (SELECT k.order_id FROM keys k), typed AS (SELECT CAST(s.order_id AS BIGINT) AS order_id FROM selected s) SELECT order_id FROM typed",
        "WITH orders AS (SELECT * FROM orders), typed AS (SELECT CAST(CAST(o.order_id AS INT) AS NUMBER(38, 0)) AS order_id FROM orders o) SELECT order_id FROM typed",
        "WITH combined AS (SELECT order_id FROM orders UNION ALL BY NAME SELECT customer_id AS order_id FROM customers), typed AS (SELECT CAST(order_id AS BIGINT) AS order_id FROM combined) SELECT order_id FROM typed",
        "SELECT order_id FROM orders QUALIFY missing > 0",
        "SELECT orders.order_id FROM orders JOIN customers USING (order_id)",
        "SELECT FROM",
        "SELECT order_id FROM orders; SELECT customer_id FROM customers",
    ] {
        let standalone: Value = serde_json::from_str(
            &crate::semantic_validation::main::validation_json(&json!({
                "sql": sql, "dialect": "snowflake", "schema": schema,
                "options": {"check_types": false, "check_references": true, "strict": true, "semantic": false, "strict_syntax": false}
            }).to_string()).expect("standalone binding should return evidence"),
        ).expect("standalone evidence should decode");
        let mut request = json!({
            "queries": [{"sql": sql, "dialect": "snowflake", "schema": schema}],
            "templates": [{"queryIndex": 0, "recoverCteFacts": true, "references": {
                "orders": {"resourceType": "model", "resourceName": "orders"},
                "customers": {"resourceType": "model", "resourceName": "customers"}
            }}],
            "projections": [{"templateIndex": 0}]
        });
        let separate: Value = serde_json::from_str(
            &analyze_project_compact_json(&request.to_string())
                .expect("separate analysis should return evidence"),
        )
        .expect("separate evidence should decode");
        request["queries"][0]["binding_schema"] = schema.clone();
        let mut combined: Value = serde_json::from_str(
            &analyze_project_compact_json(&request.to_string())
                .expect("combined analysis should return evidence"),
        )
        .expect("combined evidence should decode");
        assert_eq!(
            combined["validations"][0], standalone,
            "binding mismatch for {sql}"
        );
        combined
            .as_object_mut()
            .expect("response is an object")
            .remove("validations");
        assert_eq!(combined, separate, "analysis mismatch for {sql}");
    }
    true
}

pub(crate) fn widening_aggregates_require_compatibility_recovery() -> bool {
    for expression in [
        "AVG(order_id)",
        "SUM(order_id)",
        "MIN(order_id) > 0",
        "MIN(order_id) / 2.0",
    ] {
        for rich in [false, true] {
            let response: Value = serde_json::from_str(
                &analyze_project_compact_json(&json!({
                    "queries": [{"sql": format!("WITH selected AS (SELECT CAST(1 AS BIGINT) AS order_id) SELECT {expression} AS result FROM selected"), "dialect": "duckdb"}],
                    "templates": [{"queryIndex": 0, "recoverCteFacts": true, "richTypeInference": rich}],
                    "projections": [{"templateIndex": 0}]
                }).to_string()).expect("query should analyze"),
            ).expect("response should decode");
            assert_eq!(
                response["templates"][0],
                "native project type recovery requires legacy fallback"
            );
        }
    }
    true
}

pub(crate) fn compact_project_query_interns_repeated_lineage_strings() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [{
                    "sql": "SELECT order_id FROM orders",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                    }]}
                }],
                "templates": [{
                    "queryIndex": 0,
                    "references": {
                        "orders": {"resourceType": "model", "resourceName": "orders"}
                    },
                    "declaredColumnOrder": ["order_id"]
                }],
                "projections": [{
                    "templateIndex": 0,
                    "resourceNames": {"orders": "orders"}
                }]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        response["strings"],
        json!(["model", "orders", "order_id", "BIGINT"])
    );
    assert_eq!(response["facts"][0], json!([2, 3, 1, 0, 1, [[0, 1, 2]]]));
    assert_eq!(response["templates"][0], json!([[0], false]));
    assert_eq!(response["analyses"][0], json!([0, [[1, 1]]]));
    true
}

pub(crate) fn repeated_project_facts_intern_complete_facts() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [{"sql": "SELECT 1 AS order_id", "dialect": "duckdb"}],
                "templates": [
                    {"queryIndex": 0},
                    {"queryIndex": 0}
                ],
                "projections": [
                    {"templateIndex": 0},
                    {"templateIndex": 1}
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(response["facts"].as_array().map(Vec::len), Some(1));
    assert_eq!(response["templates"][0][0], json!([0]));
    assert_eq!(response["templates"][1][0], json!([0]));
    true
}

pub(crate) fn interleaved_query_templates_preserve_template_order() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [
                    {"sql": "SELECT 1 AS first_value", "dialect": "duckdb"},
                    {"sql": "SELECT 2 AS second_value", "dialect": "duckdb"}
                ],
                "templates": [
                    {"queryIndex": 1},
                    {"queryIndex": 0},
                    {"queryIndex": 1}
                ],
                "projections": [
                    {"templateIndex": 0},
                    {"templateIndex": 1},
                    {"templateIndex": 2}
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let strings = response["strings"]
        .as_array()
        .expect("compact strings should be an array");
    let facts = response["facts"]
        .as_array()
        .expect("compact facts should be an array");
    let templates = response["templates"]
        .as_array()
        .expect("compact templates should be an array");
    let names: Vec<&Value> = templates
        .iter()
        .map(|template| {
            let fact_index = template[0][0]
                .as_u64()
                .expect("template should use a fact index") as usize;
            let name_index = facts[fact_index][0]
                .as_u64()
                .expect("fact should use a name index") as usize;
            &strings[name_index]
        })
        .collect();
    names == vec!["second_value", "first_value", "second_value"]
}

pub(crate) fn canonical_queries_reuse_semantics_and_project_resources() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [
                    {
                        "sql": "SELECT order_id FROM __sqlbuild_project_input_0",
                        "dialect": "duckdb",
                        "schema": {"tables": [{
                            "name": "__sqlbuild_project_input_0",
                            "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                        }]}
                    }
                ],
                "templates": [{
                        "queryIndex": 0,
                        "references": {
                            "__sqlbuild_project_input_0": {
                                "resourceType": "model",
                                "resourceName": "__sqlbuild_project_input_0"
                            }
                        }
                }],
                "projections": [
                    {
                        "templateIndex": 0,
                        "resourceNames": {"__sqlbuild_project_input_0": "orders"}
                    },
                    {
                        "templateIndex": 0,
                        "resourceNames": {"__sqlbuild_project_input_0": "archived_orders"}
                    }
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(response["uniqueQueryCount"], 1);
    assert_eq!(response["uniqueProjectionCount"], 1);
    assert_eq!(response["analyses"].as_array().map(Vec::len), Some(2));
    let strings = response["strings"]
        .as_array()
        .expect("compact strings should be an array");
    let fact_index = response["templates"][0][0][0]
        .as_u64()
        .expect("template should use a fact index") as usize;
    let canonical_resource_index = response["facts"][fact_index][5][0][1]
        .as_u64()
        .expect("canonical resource should use a string index")
        as usize;
    let first_resource_index = response["analyses"][0][1][0][1]
        .as_u64()
        .expect("first resource should use a string index") as usize;
    let second_resource_index = response["analyses"][1][1][0][1]
        .as_u64()
        .expect("second resource should use a string index")
        as usize;
    assert_eq!(
        strings[canonical_resource_index],
        "__sqlbuild_project_input_0"
    );
    assert_eq!(strings[first_resource_index], "orders");
    assert_eq!(strings[second_resource_index], "archived_orders");
    true
}
pub(crate) fn native_compatibility_types_preserve_result_semantics() -> bool {
    let expression = polyglot_sql::parse_one(
        "WITH orders AS (SELECT CAST(1 AS INTEGER) AS order_id), values AS (SELECT CASE WHEN order_id > 0 THEN CAST(order_id AS BIGINT) ELSE NULL END AS result, order_id > 0 AS positive, SUM(order_id) AS total FROM orders GROUP BY order_id) SELECT result, positive, total FROM values",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let functions = std::collections::HashMap::from([("SUM".to_string(), "FLOAT".to_string())]);
    let types = crate::query_analysis::compatibility_types::infer(
        &expression,
        None,
        &functions,
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(types.get("result").map(String::as_str), Some("BIGINT"));
    assert_eq!(types.get("positive").map(String::as_str), Some("BOOLEAN"));
    assert_eq!(types.get("total").map(String::as_str), Some("FLOAT"));
    let expression = polyglot_sql::parse_one(
        "WITH renamed(unknown_value, order_id) AS (SELECT unknown_function() AS original_value, CAST(1 AS BIGINT) AS original_id) SELECT * FROM (SELECT order_id FROM renamed) AS nested_orders",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let types = crate::query_analysis::compatibility_types::infer(
        &expression,
        None,
        &functions,
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(types.get("order_id").map(String::as_str), Some("BIGINT"));
    true
}
pub(crate) fn borrowed_facts_preserve_union_dependencies_and_join_nullability() -> bool {
    let schema: polyglot_sql::ValidationSchema = serde_json::from_value(serde_json::json!({
        "tables": [
            {"name": "orders", "columns": [{"name": "order_id", "type": "INTEGER", "nullable": false}, {"name": "payload", "type": "VARIANT"}]},
            {"name": "customers", "columns": [{"name": "customer_id", "type": "INTEGER", "nullable": false}]}
        ]
    })).expect("valid schema");
    let expression = polyglot_sql::parse_one(
        "WITH combined AS (SELECT order_id FROM orders UNION ALL BY NAME SELECT customer_id AS order_id FROM customers), typed AS (SELECT CAST(order_id AS BIGINT) AS order_id FROM combined) SELECT order_id FROM typed",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let facts = crate::query_analysis::borrowed_facts::infer(
        &expression,
        Some(&schema),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(
        *facts[0].upstream,
        std::collections::BTreeSet::from([
            ("orders".to_string(), "order_id".to_string()),
            ("customers".to_string(), "customer_id".to_string()),
        ])
    );
    assert_eq!(
        facts[0].nullability,
        polyglot_sql::ProjectionNullability::NonNull
    );
    let expression = polyglot_sql::parse_one(
        "SELECT o.order_id, c.customer_id FROM orders o LEFT JOIN customers c ON o.order_id = c.customer_id",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let facts = crate::query_analysis::borrowed_facts::infer(
        &expression,
        Some(&schema),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(
        facts[0].nullability,
        polyglot_sql::ProjectionNullability::NonNull
    );
    assert_eq!(
        facts[1].nullability,
        polyglot_sql::ProjectionNullability::Nullable
    );
    let expression = polyglot_sql::parse_one(
        "WITH expanded AS (SELECT f.value AS item FROM orders o, LATERAL FLATTEN(INPUT => o.payload) f), renamed AS (SELECT item AS first_item, COALESCE(first_item, NULL) AS second_item FROM expanded) SELECT second_item FROM renamed",
        polyglot_sql::DialectType::Snowflake,
    ).expect("valid SQL");
    let facts = crate::query_analysis::borrowed_facts::infer(
        &expression,
        Some(&schema),
        polyglot_sql::DialectType::Snowflake,
    );
    assert_eq!(
        *facts[0].upstream,
        std::collections::BTreeSet::from([("orders".to_string(), "payload".to_string())])
    );
    assert_eq!(
        facts[0].nullability,
        polyglot_sql::ProjectionNullability::Unknown
    );
    true
}
