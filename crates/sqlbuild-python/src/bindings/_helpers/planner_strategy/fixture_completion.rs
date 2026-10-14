//! Native-hosted relation fixture completion over Python boundary models.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::align_columns::align_columns;
use sqlbuild_analysis::planner_fixtures::models::{AlignmentInput, RequiredColumn};

use crate::bindings::_helpers::planner_strategy::fixture_preparation::{PreparedFixtures, prepare};
use crate::bindings::_helpers::planner_strategy::fixture_sql::{CompletionSql, render_completed};
use crate::bindings::_helpers::planner_strategy::fixture_values::{
    COMPLETION, columns, diagnostic, folded, label, record, strings,
};

fn helper<'py>(
    py: Python<'py>,
    name: &str,
    kwargs: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import(COMPLETION)?.getattr(name)?.call((), Some(kwargs))
}

#[pyfunction]
#[pyo3(signature = (*, project, adapter, request, planning_context = None))]
fn build_relation_fixture_completion<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    request: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    planning_context: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let (ordered_model_names, fixture_groups) = request;
    let py = project.py();
    let context = match planning_context {
        Some(context) if context.is_truthy()? => context,
        _ => {
            let kwargs = PyDict::new(py);
            kwargs.set_item("project", project)?;
            helper(py, "build_relation_fixture_context", &kwargs)?
        }
    };
    let relations = context.getattr("relations")?.cast_into::<PyDict>()?;
    let prepared = prepare(
        &fixture_groups,
        &relations,
        adapter,
        &context.getattr("fixture_inferences")?,
    )?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("inferred_by_fixture", &prepared.inferred)?;
    kwargs.set_item(
        "authoritative_columns",
        context.getattr("authoritative_columns")?,
    )?;
    let fixture_keys = helper(py, "_fixture_keys_requiring_analysis", &kwargs)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("ordered_model_names", &ordered_model_names)?;
    kwargs.set_item("model_map", context.getattr("models_by_name")?)?;
    kwargs.set_item("fixture_keys", fixture_keys)?;
    kwargs.set_item("relations", &relations)?;
    kwargs.set_item(
        "authoritative_columns",
        context.getattr("authoritative_columns")?,
    )?;
    kwargs.set_item("adapter", adapter)?;
    let required_and_stars = helper(py, "_required_fixture_columns", &kwargs)?;
    let required = required_and_stars.get_item(0)?.cast_into::<PyDict>()?;
    let stars = required_and_stars.get_item(1)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("base_expected_types", context.getattr("expected_types")?)?;
    kwargs.set_item("ordered_model_names", &ordered_model_names)?;
    kwargs.set_item("model_map", context.getattr("models_by_name")?)?;
    let expected = helper(py, "_expected_fixture_types", &kwargs)?;
    complete_prepared(prepared, (relations, required, stars), expected, adapter)
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
    let kwargs = PyDict::new(py);
    kwargs.set_item("inferred_by_fixture", &prepared.inferred)?;
    kwargs.set_item("relations", &relations)?;
    for value in helper(py, "_unknown_fixture_column_diagnostics", &kwargs)?.try_iter()? {
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
