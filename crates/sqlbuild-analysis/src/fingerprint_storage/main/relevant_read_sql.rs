//! The latest-row read narrowed to the relevant nodes.

use crate::fingerprint_storage::_helpers::literals::literal_list;
use crate::fingerprint_storage::models::RelevantRead;

/// The read limited to `node_names` plus unfiltered node types; `None` names keep every row.
pub fn relevant_read_sql(
    read_sql: &str,
    node_names: Option<&[String]>,
    filtered_node_types: &[String],
) -> RelevantRead {
    let Some(node_names) = node_names else {
        return RelevantRead::Sql(read_sql.to_owned());
    };
    if node_names.is_empty() && filtered_node_types.is_empty() {
        return RelevantRead::Empty;
    }
    let mut predicate = String::new();
    if !node_names.is_empty() {
        predicate = format!("node_name IN ({})", literal_list(node_names));
    }
    if !filtered_node_types.is_empty() {
        let identity_predicate: String =
            format!("node_type NOT IN ({})", literal_list(filtered_node_types));
        predicate = if predicate.is_empty() {
            identity_predicate
        } else {
            format!("{predicate} OR {identity_predicate}")
        };
    }
    RelevantRead::Sql(format!(
        "SELECT * FROM ({read_sql}) AS __sqlbuild_relevant WHERE {predicate}"
    ))
}
