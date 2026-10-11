//! `model_schema_scope_usages`: parent schemas and enum column types each schema uses.

use std::collections::{HashMap, HashSet};

use crate::compile_usages::_helpers::schema_checks::{hidden_enum, hidden_parent, visible_from};
use crate::compile_usages::models::{
    NamedRecord, RejectedScopePath, SchemaDeclaration, SchemaUsages,
};

/// Each indexed schema's usages of its parent and enum column types, with S006 where hidden.
pub fn schema_scope_usages(
    schemas: &[SchemaDeclaration],
    schema_records: &HashMap<String, NamedRecord>,
    enum_records: &HashMap<String, NamedRecord>,
) -> Result<SchemaUsages, RejectedScopePath> {
    let mut scan: SchemaUsages = SchemaUsages::default();
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    for schema in schemas {
        let Some(record) = schema_records.get(&schema.name) else {
            continue;
        };
        let mut found: Vec<usize> = Vec::new();
        if let Some(parent_name) = &schema.extends
            && let Some(parent) = schema_records.get(parent_name)
        {
            if !visible_from(parent, record)? {
                scan.diagnostics
                    .push(hidden_parent(record, parent_name, parent));
            }
            found.push(parent.handle);
        }
        for (column, column_type) in &schema.columns {
            let Some(enum_name) = column_type else {
                continue;
            };
            let Some(enum_record) = enum_records.get(enum_name) else {
                continue;
            };
            if !visible_from(enum_record, record)? {
                scan.diagnostics.push(hidden_enum(
                    (record, &schema.name),
                    (column, enum_name),
                    enum_record,
                ));
            }
            found.push(enum_record.handle);
        }
        for declaration in found {
            if seen.insert((record.handle, declaration)) {
                scan.usages.push((record.handle, declaration));
            }
        }
    }
    Ok(scan)
}
