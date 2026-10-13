//! Node field rules shared by models, sources and seeds.

use crate::dbt_manifest::constants::DBT_REF_FUNCTION;
use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::models::ManifestNode;

/// A non-empty string field.
pub(crate) fn optional(node: &ManifestNode, field: &str) -> Option<String> {
    node.text
        .iter()
        .find(|(key, value)| key == field && !value.is_empty())
        .map(|(_, value)| value.clone())
}

/// A non-empty string field, or the invalid-manifest error naming it.
pub(crate) fn required(node: &ManifestNode, field: &str) -> Result<String, ManifestError> {
    optional(node, field)
        .ok_or_else(|| ManifestError::invalid(&format!(": model {field} is required")))
}

/// The given relation name, or `database.schema.name` without empty parts.
pub(crate) fn relation_name(
    node: &ManifestNode,
    (database, schema): (&Option<String>, &Option<String>),
    name: &str,
) -> String {
    optional(node, "relation_name").unwrap_or_else(|| {
        [database.as_deref(), schema.as_deref(), Some(name)]
            .into_iter()
            .flatten()
            .filter(|part| !part.is_empty())
            .collect::<Vec<&str>>()
            .join(".")
    })
}

/// `SqlReferenceKind.DBT_REF.example_call(*args, quote='"')`.
pub(crate) fn quoted_dbt_ref(args: &[&str]) -> String {
    let quoted: Vec<String> = args
        .iter()
        .map(|arg| format!("\"{}\"", arg.replace('"', "\"\"")))
        .collect();
    format!("{DBT_REF_FUNCTION}({})", quoted.join(", "))
}
