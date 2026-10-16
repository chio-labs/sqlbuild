//! The default Dagster description of a node that has none.

/// `SQLBuild <kind> `<name>`[ materialized as `<m>`][ at `<relation>`].`, kind `_` as spaces.
#[must_use]
pub fn fallback_asset_description(
    kind: &str,
    name: &str,
    qualified_name: &str,
    materialization: Option<&str>,
) -> String {
    let kind: String = kind.replace('_', " ");
    let relation: String = if qualified_name.is_empty() {
        String::new()
    } else {
        format!(" at `{qualified_name}`")
    };
    match materialization {
        Some(materialization) => {
            format!("SQLBuild {kind} `{name}` materialized as `{materialization}`{relation}.")
        }
        None => format!("SQLBuild {kind} `{name}`{relation}."),
    }
}
