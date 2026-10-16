//! Project fixture context materialization and schema conversions.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::fixture_schema::fixture_schema;

use crate::bindings::_helpers::planner_strategy::fixture_metadata::model_fixture_metadata;
use crate::bindings::_helpers::planner_strategy::fixture_values::{columns, metadata, record};
use crate::bindings::_helpers::records::ids::RecordId;

#[pyfunction]
#[pyo3(signature = (*, project, models_by_name = None))]
pub(crate) fn build_relation_fixture_context<'py>(
    project: &Bound<'py, PyAny>,
    models_by_name: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let model_map = match models_by_name {
        Some(models) => models,
        None => {
            let models = PyDict::new(py);
            for model in project.getattr("models")?.try_iter()? {
                let model = model?;
                models.set_item(model.getattr("name")?, &model)?;
            }
            models
        }
    };
    let relations = relation_metadata(project, &model_map)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("models_by_name", model_map)?;
    kwargs.set_item(
        "authoritative_columns",
        authoritative_fixture_columns(&relations)?,
    )?;
    kwargs.set_item("expected_types", base_expected_fixture_types(&relations)?)?;
    kwargs.set_item("relations", relations)?;
    record(py, RecordId::RelationFixturePlanningContext, &kwargs)
}

fn relation_metadata<'py>(
    project: &Bound<'py, PyAny>,
    models: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = project.py();
    let kinds = py
        .import("sqlbuild.compiler.compile.types")?
        .getattr("CompiledResourceType")?;
    let relations = PyDict::new(py);
    for (name, model) in models.iter() {
        relations.set_item(
            (kinds.getattr("MODEL")?, name),
            model_fixture_metadata(&model)?,
        )?;
    }
    for (collection, entry, kind, source) in [
        ("sources", "source_entry", "SOURCE", true),
        ("seeds", "schema_entry", "SEED", false),
    ] {
        for resource in project.getattr(collection)?.try_iter()? {
            let resource = resource?;
            let entry = resource.getattr(entry)?;
            let columns = columns(&entry.getattr("columns")?, false)?;
            let authoritative = if source {
                entry.getattr("contract")?.eq("enforced")?
            } else {
                !columns.is_empty()
            };
            relations.set_item(
                (kinds.getattr(kind)?, resource.getattr("name")?),
                metadata(py, &columns, authoritative)?,
            )?;
        }
    }
    Ok(relations)
}

#[pyfunction]
#[pyo3(signature = (*, relations))]
pub(crate) fn authoritative_fixture_columns<'py>(
    relations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new(relations.py());
    for (key, relation) in relations.iter() {
        let schema = fixture_schema(
            &columns(&relation.getattr("columns")?, false)?,
            relation.getattr("authoritative_names")?.extract()?,
        );
        if let Some(names) = schema.authoritative_names {
            result.set_item(key, PyFrozenSet::new(relations.py(), names)?)?;
        }
    }
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (*, relations))]
pub(crate) fn base_expected_fixture_types<'py>(
    relations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new(relations.py());
    for (key, relation) in relations.iter() {
        let schema = fixture_schema(&columns(&relation.getattr("columns")?, false)?, false);
        let types = PyDict::new(relations.py());
        for (name, sql_type) in schema.expected_types {
            types.set_item(name, sql_type)?;
        }
        result.set_item(key, types)?;
    }
    Ok(result)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_relation_fixture_context, module)?)?;
    module.add_function(wrap_pyfunction!(authoritative_fixture_columns, module)?)?;
    module.add_function(wrap_pyfunction!(base_expected_fixture_types, module)?)
}
