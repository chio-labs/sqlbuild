//! Native-hosted relation fixture completion over Python boundary models.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::align_columns::align_columns;
use sqlbuild_analysis::planner_fixtures::models::{AlignmentInput, RequiredColumn};

use crate::bindings::_helpers::planner_strategy::fixture_context::build_relation_fixture_context;
use crate::bindings::_helpers::planner_strategy::fixture_preparation::{PreparedFixtures, prepare};
use crate::bindings::_helpers::planner_strategy::fixture_reads::required_fixture_columns;
use crate::bindings::_helpers::planner_strategy::fixture_selection::{
    fixture_keys_requiring_analysis, unknown_fixture_column_diagnostics,
};
use crate::bindings::_helpers::planner_strategy::fixture_sql::{CompletionSql, render_completed};
use crate::bindings::_helpers::planner_strategy::fixture_types::expected_fixture_types;
use crate::bindings::_helpers::planner_strategy::fixture_values::{
    columns, diagnostic, folded, label, record, strings,
};

#[pyfunction]
#[pyo3(signature = (*, project, adapter, request, planning_context = None))]
pub(crate) fn build_relation_fixture_completion<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    request: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    planning_context: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let (ordered_model_names, fixture_groups) = request;
    let context = match planning_context {
        Some(context) if context.is_truthy()? => context,
        _ => build_relation_fixture_context(project, None)?,
    };
    let relations = context.getattr("relations")?.cast_into::<PyDict>()?;
    let prepared = prepare(
        &fixture_groups,
        &relations,
        adapter,
        &context.getattr("fixture_inferences")?,
    )?;
    let fixture_keys = fixture_keys_requiring_analysis(
        &prepared.inferred,
        &context
            .getattr("authoritative_columns")?
            .cast_into::<PyDict>()?,
    )?;
    let (required, stars) = required_fixture_columns(
        (
            ordered_model_names.extract()?,
            context.getattr("models_by_name")?.cast_into::<PyDict>()?,
        ),
        (
            fixture_keys.into_any(),
            relations.clone(),
            context
                .getattr("authoritative_columns")?
                .cast_into::<PyDict>()?,
        ),
        adapter,
    )?;
    let expected = expected_fixture_types(
        &context.getattr("expected_types")?.cast_into::<PyDict>()?,
        ordered_model_names.extract()?,
        &context.getattr("models_by_name")?.cast_into::<PyDict>()?,
    )?;
    complete_prepared(
        prepared,
        (relations, required, stars.into_any()),
        expected.into_any(),
        adapter,
    )
}

fn complete_prepared<'py>(
    mut prepared: PreparedFixtures<'py>,
    plan: (Bound<'py, PyDict>, Bound<'py, PyDict>, Bound<'py, PyAny>),
    expected: Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = adapter.py();
    let (relations, required, stars) = plan;
    let typed_nulls = PyDict::new(py);
    for (key, names) in prepared.null_names.iter() {
        let types = expected.call_method1("get", (&key, PyDict::new(py)))?;
        let selected = PyDict::new(py);
        for name in names.try_iter()? {
            let name = name?;
            let value = types.call_method1("get", (&name,))?;
            if !value.is_none() {
                selected.set_item(name, value)?;
            }
        }
        if !selected.is_empty() {
            typed_nulls.set_item(key, selected)?;
        }
    }
    for value in unknown_fixture_column_diagnostics(&prepared.inferred, &relations)?.try_iter()? {
        prepared.diagnostics.push(value?);
    }
    let completed_keys = PySet::empty(py)?;
    for (key, required_columns) in required.iter() {
        let Some(inferred) = prepared.inferred.get_item(&key)? else {
            continue;
        };
        let typed = typed_nulls
            .get_item(&key)?
            .map(|value| value.cast_into::<PyDict>())
            .transpose()?
            .unwrap_or_else(|| PyDict::new(py));
        let metadata = match relations.get_item(&key)? {
            Some(relation) => relation.getattr("columns")?,
            None => PyTuple::empty(py).into_any(),
        };
        let requirements = required_columns
            .cast_into::<PyDict>()?
            .iter()
            .map(|(name, readers)| {
                Ok(RequiredColumn {
                    name: name.extract()?,
                    folded_name: folded(&name)?,
                    readers: strings(&readers)?,
                })
            })
            .collect::<PyResult<Vec<_>>>()?;
        let alignment = align_columns(
            &label(&key)?,
            AlignmentInput {
                supplied: &columns(&inferred, true)?,
                metadata: &columns(&metadata, false)?,
                required: &requirements,
                star: stars.contains(&key)?,
                typed_nulls: !typed.is_empty(),
            },
        );
        for message in alignment.diagnostics {
            prepared.diagnostics.push(diagnostic(&key, &message)?);
        }
        let Some(completed) = alignment.completed else {
            continue;
        };
        let completed = completed
            .into_iter()
            .map(|index| metadata.get_item(index))
            .collect::<PyResult<Vec<_>>>()?;
        let sql: String = prepared
            .sql
            .get_item(&key)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("fixture SQL"))?
            .extract()?;
        let quoted = prepared
            .quoted_names
            .get_item(&key)?
            .unwrap_or(PyFrozenSet::empty(py)?.into_any());
        let sql = render_completed(
            CompletionSql {
                sql: &sql,
                inferred,
                typed_nulls: typed,
                quoted_names: quoted,
                completed: PyTuple::new(py, completed)?.into_any(),
            },
            adapter,
        )?;
        prepared.sql.set_item(&key, sql)?;
        completed_keys.add(key)?;
    }
    for (key, typed) in typed_nulls.iter() {
        if completed_keys.contains(&key)? {
            continue;
        }
        let inferred = prepared
            .inferred
            .get_item(&key)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("fixture inference"))?;
        let sql: String = prepared
            .sql
            .get_item(&key)?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("fixture SQL"))?
            .extract()?;
        let quoted = prepared
            .quoted_names
            .get_item(&key)?
            .unwrap_or(PyFrozenSet::empty(py)?.into_any());
        let sql = render_completed(
            CompletionSql {
                sql: &sql,
                inferred,
                typed_nulls: typed.cast_into::<PyDict>()?,
                quoted_names: quoted,
                completed: PyTuple::empty(py).into_any(),
            },
            adapter,
        )?;
        prepared.sql.set_item(key, sql)?;
    }
    let kwargs = PyDict::new(py);
    kwargs.set_item("fixture_sql_by_key", prepared.sql)?;
    kwargs.set_item("inferred_by_fixture", prepared.inferred)?;
    kwargs.set_item("expected_types", expected)?;
    kwargs.set_item("diagnostics", PyTuple::new(py, prepared.diagnostics)?)?;
    record(py, "RelationFixtureCompletion", &kwargs)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_relation_fixture_completion, module)?)
}
