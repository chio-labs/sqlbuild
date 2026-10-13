//! A dbt source node.

use crate::dbt_manifest::_helpers::fields::{optional, relation_name, required};
use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::models::{ManifestNode, ParsedSource};

/// The source's identity, namespace and relation.
pub fn parse_manifest_source(node: &ManifestNode) -> Result<ParsedSource, ManifestError> {
    let package_name: String = required(node, "package_name")?;
    let source_name: String = required(node, "source_name")?;
    let name: String = required(node, "name")?;
    let database: Option<String> = optional(node, "database");
    let schema: Option<String> = optional(node, "schema");
    let identifier: Option<String> = optional(node, "identifier");
    let relation: String = relation_name(
        node,
        (&database, &schema),
        identifier.as_deref().unwrap_or(&name),
    );
    Ok(ParsedSource {
        package_name,
        source_name,
        name,
        database,
        schema,
        identifier,
        relation_name: relation,
    })
}
