//! The relation an ingestr source run writes.

/// `schema.target_name` when the source declares a schema, otherwise `target_name`.
#[must_use]
pub fn ingestr_destination_table(schema: Option<&str>, target_name: &str) -> String {
    match schema {
        Some(schema) => format!("{schema}.{target_name}"),
        None => target_name.to_owned(),
    }
}
