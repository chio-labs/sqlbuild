//! The outputs and default target one `profiles.yml` profile defines.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{DbtProfileOutputs, DbtYamlValue, LoadedDbtProfile};

/// Validate one loaded profile: a mapping with non-empty named mapping outputs and a text target.
pub fn dbt_profile_outputs(
    profiles_file: &str,
    profile_name: &str,
    loaded: &LoadedDbtProfile,
) -> Result<DbtProfileOutputs, DbtProfileError> {
    if !matches!(loaded.profile, DbtYamlValue::Mapping { .. }) {
        return Err(DbtProfileError(format!(
            "{profiles_file} does not define dbt profile '{profile_name}'"
        )));
    }
    if !matches!(loaded.outputs, DbtYamlValue::Mapping { empty: false }) {
        return Err(DbtProfileError(format!(
            "dbt profile '{profile_name}' must define non-empty outputs"
        )));
    }
    let mut outputs: Vec<(String, usize)> = Vec::new();
    for (index, (name, output)) in loaded.output_entries.iter().enumerate() {
        let DbtYamlValue::Text(name) = name else {
            return Err(invalid_output_name(profile_name));
        };
        let stripped: &str = python_strip(name);
        if stripped.is_empty() {
            return Err(invalid_output_name(profile_name));
        }
        if !matches!(output, DbtYamlValue::Mapping { .. }) {
            return Err(DbtProfileError(format!(
                "dbt profile '{profile_name}' output '{name}' must be a mapping"
            )));
        }
        match outputs.iter_mut().find(|(seen, _)| seen == stripped) {
            Some(seen) => seen.1 = index,
            None => outputs.push((stripped.to_owned(), index)),
        }
    }
    let default_target: Option<String> = match &loaded.target {
        DbtYamlValue::Null => None,
        DbtYamlValue::Text(text) if !python_strip(text).is_empty() => {
            Some(python_strip(text).to_owned())
        }
        DbtYamlValue::Text(_) | DbtYamlValue::Mapping { .. } | DbtYamlValue::Other => {
            return Err(DbtProfileError(format!(
                "dbt profile '{profile_name}' target must be a non-empty string"
            )));
        }
    };
    Ok(DbtProfileOutputs {
        name: profile_name.to_owned(),
        default_target,
        outputs,
    })
}

fn invalid_output_name(profile_name: &str) -> DbtProfileError {
    DbtProfileError(format!(
        "dbt profile '{profile_name}' contains an invalid output name"
    ))
}
