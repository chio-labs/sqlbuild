//! Relations a `migrate_from` value may name.

use crate::janitor_planning::constants::QUALIFIED_ORIGIN_PARTS;
use crate::janitor_planning::models::OriginKey;

/// Origin keys for `raw`: a bare name in each sorted schema, else the one qualified relation.
#[must_use]
pub fn migration_origin_keys(
    raw: &str,
    destination_database: Option<&str>,
    sorted_schemas: &[(Option<String>, Option<String>)],
) -> Vec<OriginKey> {
    let parts: Vec<String> = raw
        .split('.')
        .map(|part| {
            part.trim()
                .trim_matches(|c| c == '"' || c == '`')
                .to_owned()
        })
        .collect();
    if let [name] = parts.as_slice() {
        return sorted_schemas
            .iter()
            .map(|(database, schema)| OriginKey {
                database: database.clone(),
                schema: schema.clone(),
                name: name.clone(),
            })
            .collect();
    }
    let count: usize = parts.len();
    vec![OriginKey {
        database: if count == QUALIFIED_ORIGIN_PARTS {
            Some(parts[0].clone())
        } else {
            destination_database.map(str::to_owned)
        },
        schema: Some(parts[count - 2].clone()),
        name: parts[count - 1].clone(),
    }]
}
