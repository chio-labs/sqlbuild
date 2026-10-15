//! Boundary conversion for native fixture read analysis.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PySet};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::required_columns::required_columns;
use sqlbuild_analysis::planner_fixtures::main::star_keys::star_keys;
use sqlbuild_analysis::planner_fixtures::models::{
    FixtureReadKey, FixtureReadModel, FixtureReadSchemas, FixtureStarRelation,
};
use sqlbuild_analysis::planner_fixtures::types::FixtureReadReference;
use sqlbuild_analysis::required_columns::models::ColumnRead;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;
use std::collections::{HashMap, HashSet};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::planner_strategy::fixture_values::columns;
use crate::bindings::_helpers::planner_strategy::models::FixtureReadCacheHost;
use crate::bindings::types::CompilerDetach;

#[pyfunction]
#[pyo3(signature = (*, model_inputs, fixture_inputs, adapter))]
pub(crate) fn required_fixture_columns<'py>(
    model_inputs: (Vec<String>, Bound<'py, PyDict>),
    fixture_inputs: (Bound<'py, PyAny>, Bound<'py, PyDict>, Bound<'py, PyDict>),
    adapter: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyFrozenSet>)> {
    let (ordered_model_names, model_map) = model_inputs;
    let (fixture_keys, relations, authoritative_columns) = fixture_inputs;
    let py = adapter.py();
    let mut keys: HashMap<(String, String), Bound<'py, PyAny>> = HashMap::new();
    for key in fixture_keys.try_iter()? {
        let key = key?;
        keys.insert(key.extract::<(String, String)>()?, key);
    }
    let mut schema: Vec<FixtureStarRelation> = Vec::new();
    let mut authoritative: HashMap<(String, String), HashSet<String>> = HashMap::new();
    for (key, original) in &keys {
        if let Some(value) = relations.get_item(original)? {
            schema.push(FixtureStarRelation {
                key: key.clone(),
                columns: columns(&value.getattr("columns")?, false)?,
                authoritative: value.getattr("authoritative_names")?.extract()?,
            });
        } else {
            schema.push(FixtureStarRelation {
                key: key.clone(),
                columns: Vec::new(),
                authoritative: false,
            });
        }
        if let Some(value) = authoritative_columns.get_item(original)? {
            authoritative.insert(key.clone(), value.extract()?);
        }
    }
    let dialect = adapter
        .call_method0("expression_inference_profile")?
        .getattr("sql_analysis_dialect")?
        .extract::<Option<String>>()?;
    let mut models: Vec<FixtureReadModel> = Vec::new();
    for name in ordered_model_names {
        let Some(model) = model_map.get_item(&name)? else {
            continue;
        };
        let mut references: Vec<FixtureReadReference> = Vec::new();
        for reference in model.getattr("references")?.try_iter()? {
            let reference = reference?;
            references.push((
                reference.getattr("ref_kind")?.extract()?,
                reference.getattr("ref_name")?.extract()?,
                reference.getattr("ref_package")?.extract()?,
                reference.getattr("call_argument_count")?.extract()?,
            ));
        }
        models.push(FixtureReadModel {
            name,
            key: FixtureReadKey {
                sql: model.getattr("query_sql")?.extract()?,
                references,
                dialect: dialect.clone(),
            },
            high_confidence: lineage_reads(&model)?,
            stars: model_stars(&model, &schema, adapter)?,
        });
    }
    let owner = py
        .import("sqlbuild._native")?
        .getattr("_fixture_read_cache")?
        .cast_into::<FixtureReadCacheHost>()?;
    let mut owner = owner.borrow_mut();
    let cache = std::mem::take(&mut owner.cache);
    let fixture_keys: HashSet<(String, String)> = keys.keys().cloned().collect();
    let (cache, result) = catch_compiler_panic(|| {
        Ok(required_columns(
            cache,
            &models,
            FixtureReadSchemas {
                keys: &fixture_keys,
                authoritative: &authoritative,
                relations: &schema,
            },
        ))
    })
    .map_err(value_error)?;
    owner.cache = cache;
    let result = result.map_err(|error| value_error(format!("{error:?}")))?;
    let required = PyDict::new(py);
    for (key, columns) in result.columns {
        let values = PyDict::new(py);
        for column in columns {
            values.set_item(column.name, PySet::new(py, column.readers)?)?;
        }
        required.set_item(&keys[&key], values)?;
    }
    let stars = PyFrozenSet::new(py, result.stars.iter().map(|key| &keys[key]))?;
    Ok((required, stars))
}

fn lineage_reads(model: &Bound<'_, PyAny>) -> PyResult<Vec<ColumnRead>> {
    let mut reads: Vec<ColumnRead> = Vec::new();
    let facts = model.getattr("fast_lineage_columns")?;
    if facts.is_none() {
        return Ok(reads);
    }
    for fact in facts.try_iter()? {
        let fact = fact?;
        if !fact.getattr("confidence")?.eq(model
            .py()
            .import("sqlbuild._native")?
            .getattr("ColumnLineageConfidence")?
            .getattr("HIGH")?)?
        {
            continue;
        }
        for source in fact.getattr("upstream_columns")?.try_iter()? {
            let source = source?;
            reads.push(ColumnRead {
                resource_type: source.getattr("resource_type")?.extract()?,
                resource_name: source.getattr("resource_name")?.extract()?,
                column_name: source.getattr("column_name")?.extract()?,
            });
        }
    }
    Ok(reads)
}

fn model_stars(
    model: &Bound<'_, PyAny>,
    schema: &[FixtureStarRelation],
    adapter: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, String)>> {
    if !model.getattr("fast_lineage_has_star")?.is_truthy()? {
        return Ok(Vec::new());
    }
    let mut deps: Vec<(String, String)> = Vec::new();
    for dependency in model.getattr("deps")?.try_iter()? {
        let dependency = dependency?;
        let key = (
            dependency.getattr("resource_type")?.extract::<String>()?,
            dependency.getattr("name")?.extract::<String>()?,
        );
        if schema.iter().any(|relation| relation.key == key) {
            deps.push(key);
        }
    }
    let dependencies = PyFrozenSet::new(model.py(), deps)?;
    let mut selected: Vec<FixtureStarRelation> = Vec::new();
    for dependency in dependencies.try_iter()? {
        let dependency: (String, String) = dependency?.extract()?;
        if let Some(relation) = schema.iter().find(|relation| relation.key == dependency) {
            selected.push(FixtureStarRelation {
                key: relation.key.clone(),
                columns: relation.columns.clone(),
                authoritative: relation.authoritative,
            });
        }
    }
    let contract = model.getattr("dynamic_column_contract")?;
    let inputs: Option<Vec<String>> =
        if !contract.is_none() && contract.getattr("output_proven")?.is_truthy()? {
            Some(contract.getattr("input_relations")?.extract()?)
        } else {
            None
        };
    let dialect: Option<String> =
        if inputs.is_none() && selected.iter().any(|relation| !relation.columns.is_empty()) {
            adapter
                .call_method0("expression_inference_profile")?
                .getattr("sql_analysis_dialect")?
                .extract()?
        } else {
            None
        };
    let sql: String = model.getattr("query_sql")?.extract()?;
    model
        .py()
        .compiler_detach(|| {
            Ok(star_keys(
                &sql,
                &selected,
                dialect.as_deref(),
                inputs.as_deref(),
            ))
        })
        .map_err(value_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add(
        "_fixture_read_cache",
        pyo3::Py::new(module.py(), FixtureReadCacheHost::default())?,
    )?;
    module.add_function(wrap_pyfunction!(fixture_read_cache_info, module)?)?;
    module.add_function(wrap_pyfunction!(required_fixture_columns, module)?)
}

/// Report resolver misses and retained entries, optionally clearing prior fixture reuse.
#[pyfunction]
#[pyo3(signature = (*, reset = false))]
fn fixture_read_cache_info(py: pyo3::Python<'_>, reset: bool) -> PyResult<(u64, usize)> {
    let owner = py
        .import("sqlbuild._native")?
        .getattr("_fixture_read_cache")?
        .cast_into::<FixtureReadCacheHost>()?;
    let mut owner = owner.borrow_mut();
    if reset {
        owner.cache = Default::default();
    }
    Ok((owner.cache.misses, owner.cache.entries.len()))
}
