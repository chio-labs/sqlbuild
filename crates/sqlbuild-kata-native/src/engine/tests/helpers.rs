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
