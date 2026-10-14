//! Host SQL-test request preparation, native planning, and Python result conversion.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::sql_test_glue::constants::PLAN_MODELS;
use crate::bindings::_helpers::sql_test_glue::plan_values::tuple;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python, pyfunction};
use pyo3::types::{PyBool, PyDict, PyTuple};

pub(super) fn chains<'py>(
    project: &Bound<'py, PyAny>,
    tests: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    if !tests.is_truthy()? {
        return Ok(PyTuple::empty(py).into_any());
    }
    let request = call_with(
        &imported(
            py,
            "sqlbuild.compiler.sql_test_glue.models",
            "NativeSqlTestChainRequest",
        )?,
        &[
            ("models", project.getattr("models")?),
            ("tests", tests.clone()),
            (
                "lexical_syntax",
                project
                    .getattr("sql_lexical_syntax")?
                    .getattr("native_mapping")?,
            ),
        ],
    )?;
    let native =
        imported(py, "sqlbuild._native", "resolve_compiled_sql_test_chains")?.call1((request,));
    let native = match native {
        Ok(value) => value,
        Err(error) if error.is_instance_of::<pyo3::exceptions::PyValueError>(py) => {
            return Err(super::plan_errors::planning_error(py, error, tests)?);
        }
        Err(error) => return Err(error),
    };
    let mut result: Vec<Bound<'py, PyAny>> = Vec::new();
    for chain in native.try_iter()? {
        result.push(tuple(&chain?)?);
    }
    Ok(PyTuple::new(py, result)?.into_any())
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn resolve_sql_test_model_chains<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_sql_test_model_chains",
        kwargs,
        (&["project", "tests"], &[]),
    )?;
    chains(&args.value("project")?, &args.value("tests")?)
}

fn planned<'py>(args: &KeywordArguments<'py>, artifact: bool) -> PyResult<Bound<'py, PyTuple>> {
    let project = args.value("project")?;
    let py = project.py();
    let tests = args.value("tests")?;
    if !tests.is_truthy()? {
        return Ok(PyTuple::empty(py));
    }
    let start: u64 = imported(py, "time", "perf_counter_ns")?
        .call0()?
        .extract()?;
    let adapter = args.value("adapter")?;
    let model_sql = super::plan_rendering::models(&project, &adapter)?;
    let functions = super::plan_rendering::functions(&project, &adapter)?;
    let overrides = super::plan_rendering::overrides(&project, &tests, &adapter)?;
    let request = call_with(
        &imported(
            py,
            "sqlbuild.compiler.sql_test_glue.models",
            "NativeSqlTestPlanningRequest",
        )?,
        &[
            ("models", project.getattr("models")?),
            ("rendered_model_sql", model_sql.into_any()),
            ("functions", functions.into_any()),
            ("tests", tests.clone()),
            ("rendered_test_overrides", overrides.into_any()),
            ("sql_analysis_enabled", args.value("sql_analysis_enabled")?),
            (
                "sql_analysis_dialect",
                adapter.call_method0("sql_analysis_dialect")?,
            ),
            (
                "set_difference_operator",
                adapter.call_method0("render_set_difference_operator")?,
            ),
            (
                "requires_derived_table_aliases",
                adapter.call_method0("requires_derived_table_aliases")?,
            ),
            (
                "lexical_syntax",
                project
                    .getattr("sql_lexical_syntax")?
                    .getattr("native_mapping")?,
            ),
            (
                "render_sql",
                PyBool::new(py, artifact || args.flag("render_sql")?)
                    .to_owned()
                    .into_any(),
            ),
            (
                "include_plan",
                PyBool::new(
                    py,
                    !artifact && (!args.passed("include_plan")? || args.flag("include_plan")?),
                )
                .to_owned()
                .into_any(),
            ),
        ],
    )?;
    let native = imported(py, "sqlbuild._native", "plan_compiled_sql_tests")?.call1((request,));
    let native = match native {
        Ok(value) => value,
        Err(error) if error.is_instance_of::<pyo3::exceptions::PyValueError>(py) => {
            return Err(super::plan_errors::planning_error(py, error, &tests)?);
        }
        Err(error) => return Err(error),
    };
    let planning_ns: u64 = native.get_item(1)?.extract()?;
    let rendering_ns: u64 = native.get_item(2)?.extract()?;
    let end: u64 = imported(py, "time", "perf_counter_ns")?
        .call0()?
        .extract()?;
    let collector = imported(
        py,
        "sqlbuild.compiler.profiling.classes.context",
        "CompileTimingContext",
    )?
    .getattr("active")?
    .call_method0("get")?;
    if !collector.is_none() {
        use pyo3::IntoPyObject;
        for (phase, elapsed) in [
            (
                "test_planning_ms",
                planning_ns
                    + end
                        .saturating_sub(start)
                        .saturating_sub(planning_ns)
                        .saturating_sub(rendering_ns),
            ),
            ("comparison_render_ms", rendering_ns),
        ] {
            call_with(
                &collector.getattr("add")?,
                &[
                    ("phase", super::plan_values::string(py, phase)),
                    ("elapsed_ns", elapsed.into_pyobject(py)?.into_any()),
                ],
            )?;
        }
    }
    let mut plans: Vec<Bound<'py, PyAny>> = Vec::new();
    for row in native.get_item(0)?.try_iter()? {
        let plan = super::plan_rows::plan(&row?)?;
        if artifact {
            let sql = plan.getattr("sql")?;
            if sql.is_none() {
                return Err(PyErr::from_value(
                    imported(
                        py,
                        "sqlbuild.compiler.planner.exceptions",
                        "NativeSqlTestPlanningError",
                    )?
                    .call1(("native SQL-test planning omitted rendered SQL",))?,
                ));
            }
            plans.push(call_with(
                &imported(py, PLAN_MODELS, "NativeSqlTestArtifact")?,
                &[
                    ("sql", sql),
                    ("model_names", plan.getattr("model_names")?),
                    ("error_messages", plan.getattr("error_messages")?),
                ],
            )?);
        } else {
            plans.push(plan);
        }
    }
    PyTuple::new(py, plans)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn plan_sql_tests_natively<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let args = KeywordArguments::read(
        py,
        "plan_sql_tests_natively",
        kwargs,
        (
            &[
                "project",
                "tests",
                "adapter",
                "sql_analysis_enabled",
                "render_sql",
            ],
            &["include_plan"],
        ),
    )?;
    planned(&args, false)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
pub(crate) fn plan_compiled_sql_test_artifacts<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let args = KeywordArguments::read(
        py,
        "plan_compiled_sql_test_artifacts",
        kwargs,
        (
            &["project", "tests", "adapter", "sql_analysis_enabled"],
            &[],
        ),
    )?;
    planned(&args, true)
}

#[pyfunction]
#[pyo3(signature = (*, warnings))]
pub(crate) fn sql_test_plan_error_messages<'py>(
    warnings: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let mut messages: Vec<String> = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for warning in warnings.try_iter()? {
        let warning = warning?;
        let message: String = warning.getattr("message")?.extract()?;
        if warning
            .getattr("severity")?
            .getattr("value")?
            .extract::<String>()?
            == super::constants::ERROR_SEVERITY
            && seen.insert(message.clone())
        {
            messages.push(message);
        }
    }
    PyTuple::new(warnings.py(), messages)
}
