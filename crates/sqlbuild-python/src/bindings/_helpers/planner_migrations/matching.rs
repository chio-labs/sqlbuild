//! Fingerprint cache callbacks around native one-to-one migration matching.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::match_migrations::match_migrations;
use sqlbuild_analysis::planner_migrations::models::MigrationCandidate;
use std::collections::{BTreeMap, BTreeSet};

fn variants<'py>(
    py: Python<'py>,
    arguments: &KeywordArguments<'py>,
    model: &Bound<'py, PyAny>,
    maps: Bound<'py, PyAny>,
) -> PyResult<Vec<String>> {
    let name = model_reads::name_object(model)?;
    let metadata = arguments.value("metadata_jsons")?.get_item(name)?;
    let cache = arguments.value("fingerprints")?.getattr("fingerprint")?;
    let mut hashes: Vec<String> = Vec::new();
    for map in maps.try_iter()? {
        let hash: Option<String> = call_with(
            &cache,
            &[
                ("query_sql", model_reads::query_sql(model)?),
                ("metadata_json", metadata.clone()),
                ("ref_identities", map?),
                ("dialect", arguments.value("dialect")?),
            ],
        )?
        .extract()?;
        if let Some(hash) = hash
            && !hashes.contains(&hash)
        {
            hashes.push(hash);
        }
    }
    let _ = py;
    Ok(hashes)
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn match_migration_fingerprints<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments = KeywordArguments::read(
        py,
        "match_migration_fingerprints",
        options,
        (
            &[
                "models",
                "new_names",
                "seed_variants",
                "candidates",
                "metadata_jsons",
                "dialect",
                "fingerprints",
            ],
            &[],
        ),
    )?;
    let new_names: BTreeSet<String> = arguments.value("new_names")?.extract()?;
    let mut models: BTreeMap<String, Bound<'py, PyAny>> = BTreeMap::new();
    let mut names: Vec<String> = Vec::new();
    for model in arguments.value("models")?.try_iter()? {
        let model = model?;
        let name: String = model_reads::model_name(&model)?;
        if new_names.contains(&name) {
            names.push(name.clone());
        }
        models.insert(name, model);
    }
    let original: Vec<Bound<'py, PyAny>> = arguments
        .value("candidates")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut candidates: Vec<MigrationCandidate> = Vec::new();
    for candidate in &original {
        candidates.push(MigrationCandidate {
            name: candidate.getattr("node_name")?.extract()?,
            fingerprint: stored_migration_fingerprint(candidate)?.unwrap_or_default(),
        });
    }
    let seeds: Vec<BTreeMap<String, String>> = arguments.value("seed_variants")?.extract()?;
    let matched = match_migrations(&names, &seeds, &candidates, |name, maps| {
        variants(
            py,
            &arguments,
            &models[name],
            PyTuple::new(py, maps)?.into_any(),
        )
    })?;
    let matches = PyDict::new(py);
    for (name, index) in matched.matches {
        matches.set_item(name, &original[index])?;
    }
    PyTuple::new(
        py,
        [
            PyTuple::new(py, matched.variants)?.into_any(),
            matches.into_any(),
            matched.ambiguous.into_pyobject(py)?.into_any(),
        ],
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn migration_destination_fingerprints<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyDict>> {
    let arguments = KeywordArguments::read(
        py,
        "migration_destination_fingerprints",
        options,
        (
            &[
                "requests",
                "variants",
                "metadata_jsons",
                "dialect",
                "fingerprints",
            ],
            &[],
        ),
    )?;
    let result = PyDict::new(py);
    for request in arguments.value("requests")?.try_iter()? {
        let model = request?.getattr("model")?;
        let name = model_reads::name_object(&model)?;
        if arguments
            .value("metadata_jsons")?
            .call_method1("get", (&name,))?
            .is_none()
        {
            continue;
        }
        result.set_item(
            name,
            PyTuple::new(
                py,
                variants(py, &arguments, &model, arguments.value("variants")?)?,
            )?,
        )?;
    }
    Ok(result)
}

#[pyfunction]
fn stored_migration_fingerprint(fingerprint: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let metadata: String = fingerprint.getattr("metadata_json")?.extract()?;
    Ok(sqlbuild_analysis::planner_migrations::main::stored_migration_fingerprint::stored_migration_fingerprint(&metadata))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(match_migration_fingerprints, module)?)?;
    module.add_function(wrap_pyfunction!(
        migration_destination_fingerprints,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(stored_migration_fingerprint, module)?)
}
