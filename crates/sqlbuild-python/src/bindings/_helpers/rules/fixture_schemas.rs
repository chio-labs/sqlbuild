//! Discovered contract objects converted to authoritative fixture schemas.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyListMethods, PyStringMethods};
use sqlbuild_model_config::path_defaults::main::select_path_default::select_path_default;
use sqlbuild_model_config::path_defaults::models::PathDefaultChoice;
use sqlbuild_rules::lint_text::models::FixtureFormatRelation;
use sqlbuild_rules::lint_text::types::FixtureFormatColumn;
use std::collections::HashMap;

use crate::bindings::_helpers::model_config::header_columns::schema_columns;
use crate::bindings::_helpers::model_config::model_config_builder::raised_config_error;

pub(crate) fn columns(columns: &Bound<'_, PyAny>) -> PyResult<Vec<FixtureFormatColumn>> {
    columns
        .try_iter()?
        .map(|column| {
            let column = column?;
            Ok((
                column.getattr("name")?.extract()?,
                column.getattr("type")?.extract()?,
                column.getattr("nullable")?.extract()?,
            ))
        })
        .collect()
}

pub(crate) fn relations(
    inputs: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, FixtureFormatRelation>> {
    let py = inputs.py();
    let config = inputs.getattr("project_config")?;
    let default_contract: Option<String> =
        config.getattr("defaults")?.getattr("contract")?.extract()?;
    let defaults = config.getattr("path_defaults")?.cast_into::<PyDict>()?;
    let keys: Vec<String> = defaults
        .keys()
        .iter()
        .map(|key| key.extract())
        .collect::<PyResult<_>>()?;
    let mut result: HashMap<String, FixtureFormatRelation> = HashMap::new();
    for model in inputs.getattr("model_files")?.try_iter()? {
        let model = model?;
        let path = model.getattr("relative_path")?.str()?.to_str()?.to_owned();
        let mut contract = default_contract.clone();
        match select_path_default(&path, &keys) {
            PathDefaultChoice::Selected(Some(key)) => {
                let values = defaults
                    .get_item(key)?
                    .ok_or_else(|| {
                        pyo3::exceptions::PyKeyError::new_err("selected path default is absent")
                    })?
                    .cast_into::<PyDict>()?;
                if let Some(value) = values.get_item("contract")? {
                    contract = value.extract()?;
                }
            }
            PathDefaultChoice::Selected(None) => {}
            PathDefaultChoice::Conflict(error) => return Err(raised_config_error(py, error)),
        }
        let header = model.getattr("header_values")?.cast_into::<PyDict>()?;
        if let Some(value) = header.get_item("contract")? {
            contract = value.extract()?;
        }
        if contract.as_deref() != Some("enforced") {
            continue;
        }
        let file = model.getattr("file_path")?;
        let file_name = file.str()?.to_str()?.to_owned();
        let raw_columns = header
            .get_item("columns")?
            .unwrap_or_else(|| py.None().into_bound(py));
        let locations = model
            .getattr("header_column_locations")?
            .cast_into::<PyDict>()?;
        let parsed = schema_columns(
            &raw_columns,
            (&file_name, "model"),
            (false, true, false),
            &locations,
        )?;
        let columns = columns(parsed.as_any())?;
        if !columns.is_empty() {
            result.insert(
                format!("__ref__{}", file.getattr("stem")?.extract::<String>()?),
                FixtureFormatRelation { columns },
            );
        }
    }
    for source_file in inputs.getattr("source_files")?.try_iter()? {
        for source in source_file?.getattr("source_entries")?.try_iter()? {
            let source = source?;
            let contract: Option<String> = source.getattr("contract")?.extract()?;
            let contract = contract
                .filter(|value| !value.is_empty())
                .or_else(|| default_contract.clone());
            if contract.as_deref() != Some("enforced") {
                continue;
            }
            result.insert(
                format!("__source__{}", source.getattr("name")?.extract::<String>()?),
                FixtureFormatRelation {
                    columns: columns(&source.getattr("columns")?)?,
                },
            );
        }
    }
    for schema_file in inputs.getattr("schema_files")?.try_iter()? {
        for seed in schema_file?.getattr("seed_entries")?.try_iter()? {
            let seed = seed?;
            let columns = columns(&seed.getattr("columns")?)?;
            if !columns.is_empty() {
                result.insert(
                    format!("__seed__{}", seed.getattr("name")?.extract::<String>()?),
                    FixtureFormatRelation { columns },
                );
            }
        }
    }
    Ok(result)
}
