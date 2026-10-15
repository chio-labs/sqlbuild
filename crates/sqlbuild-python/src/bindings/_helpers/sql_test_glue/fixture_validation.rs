//! Static SQL-test fixture shape validation over native fixture completion.

use std::collections::BTreeSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::planner_fixtures::main::{
    collection_mismatch::collection_mismatch, fixture_line::fixture_line,
};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_strategy::fixture_completion::build_relation_fixture_completion;
use crate::bindings::_helpers::planner_strategy::fixture_context::build_relation_fixture_context;
use crate::bindings::_helpers::planner_strategy::fixture_sql::{
    complete_empty_fixture_sql, complete_typed_null_columns,
};
use crate::bindings::_helpers::sql_test_glue::constants::{COMPILE_TYPES, FIXTURE_PREFIXES};

/// Report every statically provable fixture defect or return the completed fixture SQL groups.
pub(super) fn validated_fixtures<'py>(
    test: &Bound<'py, PyAny>,
    request: (&Bound<'py, PyAny>, [Bound<'py, PyDict>; 4]),
    inputs: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    context: &Bound<'py, PyAny>,
) -> PyResult<Result<[Bound<'py, PyDict>; 4], Vec<String>>> {
    let py = test.py();
    let (chain, [refs, sources, seeds, expected]) = request;
    let (project, adapter) = inputs;
    let resource_types = imported(py, COMPILE_TYPES, "CompiledResourceType")?;
    let model = resource_types.getattr("MODEL")?;
    let kinds = [
        model.clone(),
        resource_types.getattr("SOURCE")?,
        resource_types.getattr("SEED")?,
    ];
    let groups = PyTuple::new(
        py,
        [
            PyTuple::new(py, [kinds[0].clone(), refs.clone().into_any()])?,
            PyTuple::new(py, [kinds[1].clone(), sources.clone().into_any()])?,
            PyTuple::new(py, [kinds[2].clone(), seeds.clone().into_any()])?,
        ],
    )?;
    let context = if context.is_truthy()? {
        context.clone()
    } else {
        build_relation_fixture_context(project, None)?
    };
    let completion = build_relation_fixture_completion(
        project,
        adapter,
        (chain.clone(), groups.into_any()),
        Some(context.clone()),
    )?;
    let mut errors: BTreeSet<String> = BTreeSet::new();
    for diagnostic in completion.getattr("diagnostics")?.try_iter()? {
        let diagnostic = diagnostic?;
        let key = diagnostic.getattr("key")?;
        errors.insert(format!(
            "{}: {}",
            fixture_location(
                test,
                &key.get_item(0)?,
                &key.get_item(1)?.extract::<String>()?
            )?,
            diagnostic.getattr("message")?.extract::<String>()?
        ));
    }
    let expected_types = completion.getattr("expected_types")?;
    let inferred_by_fixture = completion.getattr("inferred_by_fixture")?;
    let completed_expected = expected.copy()?;
    let sql_test = resource_types.getattr("SQL_TEST")?;
    let type_groups = [
        (&kinds[0], &refs),
        (&kinds[1], &sources),
        (&kinds[2], &seeds),
        (&sql_test, &expected),
    ];
    for (kind, fixtures) in type_groups {
        let expected_output = kind.is(&sql_test);
        for (key_name, sql) in fixtures.iter() {
            let name: String = key_name.extract()?;
            let location = || fixture_location(test, kind, &name);
            let inferred = if expected_output {
                let model_key = PyTuple::new(py, [&model, &key_name])?;
                let relation = context
                    .getattr("relations")?
                    .call_method1("get", (&model_key,))?;
                let (completed_sql, empty_error) =
                    complete_empty_fixture_sql(&sql.extract::<String>()?, &relation, adapter)?;
                if let Some(error) = empty_error {
                    errors.insert(format!("{}: expected output '{name}' {error}", location()?));
                }
                completed_expected.set_item(&name, &completed_sql)?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("query_sql", &completed_sql)?;
                kwargs.set_item(
                    "inference_profile",
                    adapter.call_method0("expression_inference_profile")?,
                )?;
                let inference = context.getattr("fixture_inferences")?.call_method(
                    "infer",
                    (),
                    Some(&kwargs),
                )?;
                if inference.is_none() {
                    None
                } else {
                    let types = expected_types
                        .call_method1("get", (&model_key, PyDict::new(py)))?
                        .cast_into::<PyDict>()?;
                    completed_expected.set_item(
                        &name,
                        complete_typed_null_columns(&completed_sql, &inference, &types, adapter)?,
                    )?;
                    Some(inference.getattr("columns")?)
                }
            } else {
                let key = PyTuple::new(py, [kind, &key_name])?;
                Some(inferred_by_fixture.call_method1("get", (key,))?)
                    .filter(|value| !value.is_none())
            };
            let Some(columns) = inferred else {
                continue;
            };
            let type_kind = if expected_output { &model } else { kind };
            let type_key = PyTuple::new(py, [type_kind, &key_name])?;
            let types = expected_types.call_method1("get", (type_key, PyDict::new(py)))?;
            for column in columns.try_iter()? {
                let column = column?;
                let column_name = column.getattr("name")?;
                let expected_type: Option<String> = types
                    .call_method1("get", (column_name.call_method0("casefold")?,))?
                    .extract()?;
                let inferred_type: Option<String> = column.getattr("type")?.extract()?;
                if !collection_mismatch(expected_type.as_deref(), inferred_type.as_deref()) {
                    continue;
                }
                let label = if expected_output {
                    "expected output".to_owned()
                } else {
                    format!("mock {}", kind.getattr("value")?.extract::<String>()?)
                };
                errors.insert(format!(
                    "{}: {label} '{name}' column '{}' has incompatible type {}; resource type is {}. Use an explicit CAST, ARRAY_CONSTRUCT, or PARSE_JSON as appropriate",
                    location()?,
                    column_name.extract::<String>()?,
                    inferred_type.unwrap_or_default(),
                    expected_type.unwrap_or_default(),
                ));
            }
        }
    }
    if !errors.is_empty() {
        let test_name: String = test.getattr("name")?.extract()?;
        return Ok(Err(errors
            .into_iter()
            .map(|error| format!("SQL test '{test_name}': {error}"))
            .collect()));
    }
    let fixture_sql = completion.getattr("fixture_sql_by_key")?;
    let completed =
        |kind: &Bound<'py, PyAny>, fixtures: &Bound<'py, PyDict>| -> PyResult<Bound<'py, PyDict>> {
            let result = PyDict::new(py);
            for (name, sql) in fixtures.iter() {
                let key = PyTuple::new(py, [kind.clone(), name.clone()])?;
                result.set_item(&name, fixture_sql.call_method1("get", (key, sql))?)?;
            }
            Ok(result)
        };
    Ok(Ok([
        completed(&kinds[0], &refs)?,
        completed(&kinds[1], &sources)?,
        completed(&kinds[2], &seeds)?,
        completed_expected,
    ]))
}

/// Return the test file and line that defines one fixture or expected-output CTE.
pub(super) fn fixture_location(
    test: &Bound<'_, PyAny>,
    resource_type: &Bound<'_, PyAny>,
    name: &str,
) -> PyResult<String> {
    let value: String = resource_type.getattr("value")?.extract()?;
    let prefix = FIXTURE_PREFIXES
        .iter()
        .find_map(|(kind, prefix)| (*kind == value).then_some(*prefix))
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(value))?;
    let test_file = test.getattr("test_file")?;
    let line = fixture_line(
        &test_file.getattr("contents")?.extract::<String>()?,
        &format!("{prefix}{name}"),
    )
    .map_err(value_error)?;
    Ok(format!(
        "{}:{line}",
        test_file
            .getattr("relative_path")?
            .call_method0("as_posix")?
            .extract::<String>()?
    ))
}
