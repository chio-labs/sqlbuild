//! A dbt seed node.

use crate::dbt_manifest::_helpers::fields::{optional, relation_name, required};
use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::models::{ManifestNode, ParsedSeed};

/// The seed's identity, namespace and relation.
pub fn parse_manifest_seed(node: &ManifestNode) -> Result<ParsedSeed, ManifestError> {
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
    Ok(ParsedSeed {
        package_name,
        name,
        database,
        schema,
        alias,
        relation_name: relation,
    })
}
