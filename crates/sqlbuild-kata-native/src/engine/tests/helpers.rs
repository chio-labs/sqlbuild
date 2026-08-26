use serde_json::{Value, json};
use tempfile::TempDir;

use crate::engine::main::evaluate::evaluate_json;

pub(crate) fn request(project_dir: &TempDir, config: &Value) -> String {
    json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "config": config,
        "models": [{
            "name": "market__mart__prices",
            "relative_path": "models/mart/market__mart__prices.sql",
            "query_sql": "SELECT * FROM prices",
            "authored_sql": "SELECT * FROM prices"
        }]
    })
    .to_string()
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
            "name": "market__mart__prices",
            "relative_path": "models/mart/market__mart__prices.sql",
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
        "schema_version": 1,
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

pub(crate) fn sql_test_policy_evaluation(
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
        .expect("base policy config is an object")
        .extend(
            extra_config
                .as_object()
                .expect("extra policy config is an object")
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

pub(crate) fn cached_sql_test_policy_request(project_dir: &TempDir, name: Option<&str>) -> String {
    json!({
        "version": 1,
        "project_dir": project_dir.path(),
        "project_fingerprint": "compiler-project-v1",
        "config": {"select": ["SQBKT004"], "cache": {"enabled": true}},
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
