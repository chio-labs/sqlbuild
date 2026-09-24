use serde_json::{Value, json};
use tempfile::TempDir;

use crate::engine::main::evaluate::evaluate_json;

pub(crate) fn request(project_dir: &TempDir, config: &Value) -> String {
    json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "config": config,
        "models": [{
            "name": "commerce__mart__orders",
            "relative_path": "models/mart/commerce__mart__orders.sql",
            "query_sql": "SELECT * FROM orders",
            "authored_sql": "SELECT * FROM orders"
        }]
    })
    .to_string()
}

pub(crate) fn model(path: &str) -> Value {
    json!({
        "name": "commerce__mart__example",
        "relative_path": path,
        "query_sql": "SELECT 1",
        "authored_sql": "SELECT 1"
    })
}

pub(crate) fn domain_layout_evaluation(
    project_dir: &TempDir,
    code: &str,
    models: Value,
    thresholds: Value,
    layout: Value,
    scope_index: Value,
) -> Result<Value, String> {
    let request = json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "config": {
            "select": [code],
            "thresholds": thresholds,
            "layout": layout,
            "cache": {"enabled": false}
        },
        "models": models,
        "scope_index": scope_index
    });
    serde_json::from_str(&evaluate_json(&request.to_string())?).map_err(|error| error.to_string())
}

pub(crate) fn scope_with_macros(paths: &[String]) -> Value {
    let mut scope = scope_index();
    scope["declarations"] = Value::Array(
        paths
            .iter()
            .enumerate()
            .map(|(index, path)| {
                let relative = path.trim_start_matches("models/commerce/_macros/");
                let bucket_path = std::path::Path::new(relative)
                    .parent()
                    .and_then(std::path::Path::to_str)
                    .filter(|value| !value.is_empty());
                json!({
                    "identity": format!("macro:item_{index}"),
                    "kind": "macro",
                    "name": format!("item_{index}"),
                    "owner": null,
                    "path": path,
                    "line": 1,
                    "column": 1,
                    "scope": "local",
                    "role": "macros",
                    "visibility": "exact_owner_private",
                    "role_root": "models/commerce/_macros",
                    "bucket_path": bucket_path,
                    "ownership_root": "models",
                    "owning_path": "models/race",
                    "metadata": {"macro": {
                        "parameters": [],
                        "dependencies": [],
                        "source_digest": format!("digest_{index}")
                    }}
                })
            })
            .collect(),
    );
    scope["usages"] = json!([]);
    scope["visibility"] = json!([]);
    scope
}

pub(crate) fn threshold_request(
    project_dir: &TempDir,
    config: &Value,
    query_sql: &str,
    references: &Value,
) -> String {
    json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "config": config,
        "models": [{
            "name": "commerce__mart__orders",
            "relative_path": "models/mart/commerce__mart__orders.sql",
            "query_sql": query_sql,
            "authored_sql": query_sql,
            "references": references,
            "declared_audit_count": 1,
            "targeting_test_count": 1
        }]
    })
    .to_string()
}

pub(crate) fn scope_index() -> Value {
    json!({
        "schema_version": 2,
        "ownership_roots": [{"path": "models", "resource_kind": "model"}],
        "resources": [{
            "identity": "model:orders",
            "kind": "model",
            "name": "orders",
            "path": "models/orders.sql",
            "ownership_root": "models",
            "ownership_root_kind": "model"
        }],
        "declarations": [{
            "identity": "enum:status",
            "kind": "enum",
            "name": "status",
            "owner": null,
            "path": "enums/status.sql",
            "line": 1,
            "column": 1,
            "scope": "global",
            "role": "enums",
            "visibility": "project",
            "role_root": "enums",
            "bucket_path": null,
            "ownership_root": "enums",
            "owning_path": null,
            "metadata": {"enum": {
                "members": [{"name": "OPEN"}],
                "scalar_type": "VARCHAR"
            }}
        }, {
            "identity": "macro:normalize_status",
            "kind": "macro",
            "name": "normalize_status",
            "owner": null,
            "path": "macros/normalize_status.py",
            "line": 1,
            "column": 1,
            "scope": "global",
            "role": "macros",
            "visibility": "project",
            "role_root": "macros",
            "bucket_path": null,
            "ownership_root": "macros",
            "owning_path": null,
            "metadata": {"macro": {
                "parameters": ["status"],
                "dependencies": ["enum:status"],
                "source_digest": "digest"
            }}
        }],
        "usages": [{
            "consumer": "model:orders",
            "declaration": "enum:status",
            "kind": "runtime",
            "through": null,
            "enum_member": "OPEN"
        }],
        "grants": [{
            "resource": "model:orders",
            "declaration": "enum:status",
            "through": "model:expected_orders",
            "kind": "expected_model"
        }],
        "visibility": [{
            "resource": "model:orders",
            "declaration": "enum:status",
            "reason": "global",
            "through": null
        }],
        "inaccessible": [{
            "resource": "model:orders",
            "declaration": "constant:private_limit",
            "reason": "private_owner"
        }],
        "diagnostics": [],
        "complete": true,
        "completeness": {
            "discovery": true,
            "static_visibility": true,
            "runtime_usage": true,
            "relationships": true,
            "placement": true,
            "promotion_impact": true
        }
    })
}

pub(crate) fn request_with_scope(scope: Value) -> Value {
    json!({
        "version": 1,
        "project_dir": ".",
        "config": {},
        "models": [],
        "public_enums": [],
        "public_constants": [],
        "custom_rules": [],
        "custom_host": null,
        "project_fingerprint": null,
        "scope_index": scope
    })
}

pub(crate) fn sql_test_rules_evaluation(
    project_dir: &TempDir,
    code: &str,
    tests: Value,
    scenarios: Value,
    scope_index: Value,
    extra_config: Value,
) -> Result<Value, String> {
    let mut config = json!({
        "select": [code],
        "cache": {"enabled": false}
    });
    config
        .as_object_mut()
        .expect("base rules config is an object")
        .extend(
            extra_config
                .as_object()
                .expect("extra rules config is an object")
                .clone(),
        );
    let request = json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "config": config,
        "models": [],
        "sql_tests": tests,
        "sql_scenarios": scenarios,
        "scope_index": scope_index
    });
    serde_json::from_str(&evaluate_json(&request.to_string())?).map_err(|error| error.to_string())
}

pub(crate) fn sql_test_fact(path: &str, name: Option<&str>, targets: Value) -> Value {
    json!({
        "source_path": path,
        "ownership_root": "tests/unit",
        "block_index": 1,
        "name": name.unwrap_or("test_orders"),
        "explicit_name": name,
        "mode": "model",
        "expected_model_names": targets,
        "assertion_names": [],
        "assertion_target_model_names": [],
        "target_model_names": targets,
        "tested_resources": []
    })
}

pub(crate) fn cached_sql_test_rules_request(project_dir: &TempDir, name: Option<&str>) -> String {
    json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "project_fingerprint": "compiler-project-v1",
        "config": {"select": ["SQBRTEST104"], "cache": {"enabled": true}},
        "models": [{
            "name": "orders", "relative_path": "models/orders.sql",
            "query_sql": "SELECT 1", "authored_sql": "SELECT 1"
        }],
        "sql_tests": [sql_test_fact(
            "tests/unit/test_orders__paid.sql", name, json!(["orders"])
        )],
        "sql_scenarios": [],
        "scope_index": scope_index()
    })
    .to_string()
}

pub(crate) fn empty_input_test_fact(
    name: &str,
    mocks: &[(&str, &str)],
    expected: &[(&str, &str)],
    assertions: &[(&str, &str)],
) -> Value {
    let ctes = |items: &[(&str, &str)]| -> Value {
        Value::Array(
            items
                .iter()
                .map(|(cte_name, sql)| json!({"name": cte_name, "sql": sql}))
                .collect(),
        )
    };
    let mut fact = sql_test_fact(
        &format!("tests/unit/test_{name}.sql"),
        Some(name),
        json!(["orders"]),
    );
    fact["authored_ctes"] = ctes(mocks);
    fact["expected_ctes"] = ctes(expected);
    fact["assertion_ctes"] = ctes(assertions);
    fact
}

pub(crate) fn empty_input_rule_evaluation(
    project_dir: &TempDir,
    select: Value,
    tests: Value,
    allowed_tests: Value,
    cache_enabled: bool,
) -> Result<Vec<String>, String> {
    let request = json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "dialect": "duckdb",
        "config": {
            "select": select,
            "thresholds": {"min_tests_per_model": 1},
            "rule_options": {"SQBRTEST203": {"allowed_tests": allowed_tests}},
            "cache": {"enabled": cache_enabled}
        },
        "models": [{
            "name": "orders",
            "relative_path": "models/orders.sql",
            "query_sql": "SELECT order_id, amount * 2 AS doubled_amount FROM raw_orders",
            "authored_sql": "SELECT order_id, amount * 2 AS doubled_amount FROM raw_orders",
            "targeting_test_count": tests.as_array().map_or(0, Vec::len)
        }],
        "sql_tests": tests,
        "sql_scenarios": [],
        "scope_index": scope_index()
    });
    let result: Value = serde_json::from_str(&evaluate_json(&request.to_string())?)
        .map_err(|error| error.to_string())?;
    Ok(result["faults"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|fault| {
            format!(
                "{} {}: {}",
                fault["code"].as_str().unwrap_or_default(),
                fault["path"].as_str().unwrap_or_default(),
                fault["message"].as_str().unwrap_or_default()
            )
        })
        .collect())
}

pub(crate) fn filler_test() -> Value {
    empty_input_test_fact(
        "orders__empty_inputs_produce_no_rows",
        &[
            (
                "__source__raw_orders",
                "SELECT NULL AS order_id, NULL AS amount WHERE FALSE",
            ),
            ("__ref__customers", "SELECT NULL AS customer_id WHERE 1 = 0"),
        ],
        &[],
        &[(
            "__assert__empty_inputs_produce_no_rows",
            "SELECT 1 AS unexpected_row FROM __ref(\"orders\")",
        )],
    )
}

pub(crate) fn with_field(mut fact: Value, field: &str, value: Value) -> Value {
    fact[field] = value;
    fact
}
