use serde_json::{Value, json};
use tempfile::TempDir;

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
