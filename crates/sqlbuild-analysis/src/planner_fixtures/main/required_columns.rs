//! Required fixture columns derived from compiler read evidence.

use sqlbuild_core::text::main::python_casefold::python_casefold;
use std::collections::HashMap;

use crate::planner_fixtures::_helpers::resolved_reads::resolved_reads;
use crate::planner_fixtures::models::{
    FixtureReadCache, FixtureReadModel, FixtureReadRequirements, FixtureReadSchemas, RequiredColumn,
};
use crate::required_columns::errors::RequiredColumnsError;

/// Collect direct reads and authoritative star columns in model discovery order.
pub fn required_columns(
    mut cache: FixtureReadCache,
    models: &[FixtureReadModel],
    schemas: FixtureReadSchemas<'_>,
) -> (
    FixtureReadCache,
    Result<FixtureReadRequirements, RequiredColumnsError>,
) {
    let FixtureReadSchemas {
        keys: fixture_keys,
        authoritative,
        relations,
    } = schemas;
    let mut result = FixtureReadRequirements::default();
    for model in models {
        let mut reads = model.high_confidence.clone();
        if model.key.references.iter().any(|(kind, name, _, _)| {
            let resource_type = match kind.as_str() {
                "ref" => "model",
                "source" => "source",
                "seed" => "seed",
                _ => return false,
            };
            fixture_keys.contains(&(resource_type.to_owned(), name.clone()))
        }) {
            let (updated, resolved) = resolved_reads(cache, &model.key);
            cache = updated;
            match resolved {
                Ok(resolved) => reads.extend(resolved),
                Err(error) => return (cache, Err(error)),
            }
        }
        for read in reads {
            let key = (read.resource_type, read.resource_name);
            if !fixture_keys.contains(&key)
                || authoritative
                    .get(&key)
                    .is_some_and(|names| !names.contains(&python_casefold(&read.column_name)))
            {
                continue;
            }
            result = add_required(result, key, &read.column_name, &model.name);
        }
        for key in &model.stars {
            result.stars.insert(key.clone());
            if let Some(relation) = relations
                .iter()
                .find(|relation| &relation.key == key && relation.authoritative)
            {
                for column in &relation.columns {
                    result = add_required(result, key.clone(), &column.name, &model.name);
                }
            }
        }
    }
    (cache, Ok(result))
}

fn add_required(
    mut result: FixtureReadRequirements,
    key: (String, String),
    name: &str,
    model: &str,
) -> FixtureReadRequirements {
    let position = *result.indices.entry(key.clone()).or_insert_with(|| {
        result.columns.push((key, Vec::new()));
        result.column_indices.push(HashMap::new());
        result.columns.len() - 1
    });
    let columns = &mut result.columns[position].1;
    let folded_name = python_casefold(name);
    if let Some(index) = result.column_indices[position].get(&folded_name) {
        let column = &mut columns[*index];
        if column.readers.last().is_none_or(|reader| reader != model) {
            column.readers.push(model.to_owned());
        }
    } else {
        result.column_indices[position].insert(folded_name.clone(), columns.len());
        columns.push(RequiredColumn {
            name: name.to_owned(),
            folded_name,
            readers: vec![model.to_owned()],
        });
    }
    result
}
