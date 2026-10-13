//! A dbt model or snapshot node.

use crate::dbt_manifest::_helpers::fields::{optional, relation_name, required};
use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::models::{ManifestNode, NodeChecksum, ParsedModel};

/// Every part when each is a non-empty string.
fn fqn_parts(parts: Vec<Option<String>>) -> Option<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for part in parts {
        names.push(part.filter(|part| !part.is_empty())?);
    }
    Some(names)
}

/// The model's identity, namespace, relation, checksum, fqn, query SQL and dependencies.
pub fn parse_manifest_model(node: &ManifestNode) -> Result<ParsedModel, ManifestError> {
    let package_name: String = required(node, "package_name")?;
    let name: String = required(node, "name")?;
    let database: Option<String> = optional(node, "database");
    let schema: Option<String> = optional(node, "schema");
    let alias: Option<String> = optional(node, "alias");
    let relation: String = relation_name(
        node,
        (&database, &schema),
        alias.as_deref().unwrap_or(&name),
    );
    let fqn: Vec<String> = node.fqn.clone().and_then(fqn_parts).unwrap_or_default();
    let query_sql: String = ["raw_code", "compiled_code", "raw_sql", "compiled_sql"]
        .into_iter()
        .find_map(|field| optional(node, field))
        .unwrap_or_default();
    let node_checksum: Option<String> = match &node.checksum {
        NodeChecksum::Text(text) | NodeChecksum::Nested(Some(text)) if !text.is_empty() => {
            Some(text.clone())
        }
        _ => None,
    };
    Ok(ParsedModel {
        package_name,
        name,
        database,
        schema,
        alias,
        node_checksum,
        relation_name: relation,
        fqn,
        query_sql,
        depends_on: node
            .depends_on
            .iter()
            .filter(|unique_id| !unique_id.is_empty())
            .cloned()
            .collect(),
    })
}
