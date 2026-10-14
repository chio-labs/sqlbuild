//! Path selector endpoints: splitting a `start~end` core and resolving each name.

use crate::dbt_graph::constants::PATH_SELECTOR_SEPARATOR;
use crate::dbt_graph::errors::DbtSelectionError;
use crate::dbt_graph::models::DbtGraphKey;
use crate::dbt_graph::types::DbtSelectorResolver;
use crate::text::main::python_strip::python_strip;

/// The stripped endpoint names around the first separator of a path core.
pub(crate) fn endpoint_names<'a, E>(
    core: &'a str,
    raw_term: &str,
) -> Result<(&'a str, &'a str), DbtSelectionError<E>> {
    let (start, end) = core
        .split_once(PATH_SELECTOR_SEPARATOR)
        .unwrap_or((core, ""));
    let (start, end) = (python_strip(start), python_strip(end));
    if start.is_empty() || end.is_empty() {
        return Err(DbtSelectionError::PathSelector(format!(
            "path selector '{raw_term}' requires names on both sides of '~'"
        )));
    }
    Ok((start, end))
}

/// The graph key one endpoint names: a SQLBuild model first, else a unique dbt model.
pub(crate) fn endpoint_key<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    manifest_models: Option<&[(String, String)]>,
    (endpoint, raw_term): (&str, &str),
) -> Result<DbtGraphKey, DbtSelectionError<E>> {
    let (names, _translation) = resolver
        .model_names(endpoint)
        .map_err(DbtSelectionError::Resolver)?;
    if let Some(name) = names.first() {
        return Ok(DbtGraphKey::sqlbuild_model(name));
    }
    let Some(manifest_models) = manifest_models else {
        return Err(DbtSelectionError::PathSelector(format!(
            "path selector '{raw_term}' endpoint '{endpoint}' is not a SQLBuild model"
        )));
    };
    let matches: Vec<&String> = manifest_models
        .iter()
        .filter(|(_, name)| name == endpoint)
        .map(|(unique_id, _)| unique_id)
        .collect();
    match matches.as_slice() {
        [unique_id] => Ok(DbtGraphKey::dbt_model(unique_id)),
        [] => Err(DbtSelectionError::PathSelector(format!(
            "path selector '{raw_term}' endpoint '{endpoint}' is not a known SQLBuild or dbt model"
        ))),
        _ => Err(DbtSelectionError::PathSelector(format!(
            "path selector '{raw_term}' endpoint '{endpoint}' is ambiguous across dbt models"
        ))),
    }
}
