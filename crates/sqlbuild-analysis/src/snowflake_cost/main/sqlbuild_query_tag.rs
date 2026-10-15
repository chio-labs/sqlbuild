//! `sqlbuild_query_tag`: the run attribution of a SQLBuild Snowflake `QUERY_TAG`.

use serde_json::Value;

use crate::snowflake_cost::constants::{QUERY_TAG_APP, QUERY_TAG_APP_KEY, QUERY_TAG_VERSION_KEY};
use crate::snowflake_cost::models::QueryTag;

/// Python's `value == 1` for a decoded JSON value.
fn equals_one(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number
            .as_i64()
            .map(|integer| integer == 1)
            .or_else(|| number.as_u64().map(|integer| integer == 1))
            .unwrap_or_else(|| number.as_f64() == Some(1.0)),
        _ => false,
    }
}

fn text(payload: &serde_json::Map<String, Value>, key: &str) -> Option<String> {
    match payload.get(key) {
        Some(Value::String(value)) if !value.is_empty() => Some(value.clone()),
        _ => None,
    }
}

/// The tag's attribution when it is a SQLBuild version-1 JSON object, else `None`.
pub fn sqlbuild_query_tag(value: &str) -> Option<QueryTag> {
    if value.is_empty() {
        return None;
    }
    let Ok(Value::Object(payload)) = serde_json::from_str::<Value>(value) else {
        return None;
    };
    let app_matches: bool =
        matches!(payload.get(QUERY_TAG_APP_KEY), Some(Value::String(app)) if app == QUERY_TAG_APP);
    if !app_matches || !equals_one(payload.get(QUERY_TAG_VERSION_KEY)) {
        return None;
    }
    Some(QueryTag {
        run_id: text(&payload, "run_id"),
        resource_type: text(&payload, "resource_type"),
        resource_name: text(&payload, "resource_name"),
    })
}
