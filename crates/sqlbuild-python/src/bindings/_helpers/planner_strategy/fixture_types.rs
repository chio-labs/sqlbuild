//! Expected fixture type propagation boundary conversions.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::propagate_types::propagate_types;
use sqlbuild_analysis::planner_fixtures::models::{
    FixtureTypeModel, FixtureTypeProjection, FixtureTypeRead, FixtureTypeState,
};

use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::bindings::_helpers::analysis::model_reads::lineage_facts;
use crate::bindings::_helpers::planner_strategy::constants::DIRECT_TRANSFORM;

#[pyfunction]
#[pyo3(signature = (*, base_expected_types, ordered_model_names, model_map))]
pub(crate) fn expected_fixture_types<'py>(
    base_expected_types: &Bound<'py, PyDict>,
    ordered_model_names: Vec<String>,
    model_map: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut state = FixtureTypeState::default();
    let result = PyDict::new(base_expected_types.py());
    let mut models: Vec<FixtureTypeModel> = Vec::new();
    for name in ordered_model_names {
        let Some(model) = model_map.get_item(&name)? else {
            continue;
        };
        let key = ("model".to_owned(), name);
        let types = base_expected_types
            .get_item(&key)?
            .ok_or_else(|| PyKeyError::new_err(key.clone()))?
            .cast_into::<PyDict>()?
            .copy()?;
        state.known.insert(key.clone(), types.extract()?);
        result.set_item(&key, types)?;
        models.push(FixtureTypeModel {
            key,
            projections: projections(&model)?,
        });
    }
    for model in &models {
        for projection in &model.projections {
            for read in &projection.upstream {
                if state
                    .known
                    .get(&read.key)
                    .is_some_and(|types| types.contains_key(&read.column))
                {
                    continue;
                }
                if let Some(types) = base_expected_types.get_item(&read.key)?
                    && let Some(value) = types.cast_into::<PyDict>()?.get_item(&read.column)?
                {
                    state
                        .known
                        .entry(read.key.clone())
                        .or_default()
                        .insert(read.column.clone(), value.extract()?);
                }
            }
        }
    }
    let state = propagate_types(state, &models);
    for (read, sql_type) in state.additions {
        result
            .get_item(read.key)?
            .ok_or_else(|| PyKeyError::new_err("fixture types"))?
            .set_item(read.column, sql_type)?;
    }
    base_expected_types
        .py()
        .import("collections")?
        .getattr("ChainMap")?
        .call1((result, base_expected_types))
}

fn projections(model: &Bound<'_, PyAny>) -> PyResult<Vec<FixtureTypeProjection>> {
    let mut projections: Vec<FixtureTypeProjection> = Vec::new();
    for (output_column, transform, _, sources) in lineage_facts(model)?.unwrap_or_default() {
        if transform != DIRECT_TRANSFORM {
            continue;
        }
        let mut upstream: Vec<FixtureTypeRead> = Vec::with_capacity(sources.len());
        for (resource_type, resource_name, column_name) in sources {
            upstream.push(FixtureTypeRead {
                key: (resource_type, resource_name),
                column: python_casefold(&column_name),
            });
        }
        projections.push(FixtureTypeProjection {
            output_column: python_casefold(&output_column),
            upstream,
        });
    }
    Ok(projections)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(expected_fixture_types, module)?)
}
