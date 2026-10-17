//! Which models `[defaults]`, `[path_defaults]` or a reusable model schema describe.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyListMethods, PyString};
use sqlbuild_model_config::path_defaults::main::select_path_default::select_path_default;
use sqlbuild_model_config::path_defaults::models::PathDefaultChoice;

use crate::bindings::_helpers::model_config::model_config_builder::{
    layered_values, raised_config_error,
};
use crate::bindings::_helpers::model_config::project_defaults::project_defaults_mapping;
use crate::bindings::_helpers::records::fields::field as native_field;

const DESCRIPTION_KEY: &str = "description";
const MODEL_SCHEMA_KEY: &str = "model_schema";

/// Whether `value` is a string with non-whitespace text.
fn non_empty_text(value: Option<Bound<'_, PyAny>>) -> PyResult<bool> {
    let Some(value) = value.filter(|value| value.is_instance_of::<PyString>()) else {
        return Ok(false);
    };
    value.call_method0("strip")?.is_truthy()
}

/// The file path of each model whose layered config or model schema gives it a description.
pub(crate) fn externally_described_models<'py>(
    inputs: Bound<'py, PyAny>,
    model_schemas: Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = inputs.py();
    let project_config: Bound<'py, PyAny> = native_field(&inputs, "project_config")?;
    let defaults: Bound<'py, PyDict> =
        project_defaults_mapping(&native_field(&project_config, "defaults")?)?;
    let path_defaults: Bound<'py, PyDict> =
        native_field(&project_config, "path_defaults")?.downcast_into()?;
    let path_keys: Vec<String> = path_defaults
        .keys()
        .iter()
        .map(|key| key.extract::<String>())
        .collect::<PyResult<_>>()?;
    let mut described: Vec<Bound<'py, PyAny>> = Vec::new();
    for model_file in native_field(&inputs, "model_files")?.try_iter()? {
        let model_file: Bound<'py, PyAny> = model_file?;
        let relative_path: String = native_field(&model_file, "relative_path")?
            .str()?
            .extract()?;
        let mut values: Bound<'py, PyDict> = defaults.copy()?;
        match select_path_default(&relative_path, &path_keys) {
            PathDefaultChoice::Selected(Some(key)) => {
                let layer: Bound<'py, PyDict> =
                    path_defaults.as_any().get_item(&key)?.downcast_into()?;
                values = layered_values(py, &values, &layer)?;
            }
            PathDefaultChoice::Selected(None) => {}
            PathDefaultChoice::Conflict(error) => return Err(raised_config_error(py, error)),
        }
        let header: Bound<'py, PyDict> =
            native_field(&model_file, "header_values")?.downcast_into()?;
        values = layered_values(py, &values, &header)?;
        let schema_description: Option<Bound<'py, PyAny>> =
            match values.get_item(MODEL_SCHEMA_KEY)? {
                Some(name) if name.is_instance_of::<PyString>() => model_schemas
                    .get_item(name)?
                    .map(|schema| schema.getattr(DESCRIPTION_KEY))
                    .transpose()?,
                _ => None,
            };
        if non_empty_text(values.get_item(DESCRIPTION_KEY)?)? || non_empty_text(schema_description)?
        {
            described.push(native_field(&model_file, "file_path")?);
        }
    }
    Ok(described)
}
