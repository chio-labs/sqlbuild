//! Assemble per-test outcomes around native planning and adapter fixture validation.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, keywords,
};
use crate::bindings::_helpers::planner_strategy::fixture_context::planning_context;
use crate::bindings::_helpers::planner_strategy::models::RelationFixturePlanningContext;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::sql_test_glue::plan_driver::plan_sql_tests_natively;

#[pyfunction(name = "plan_sql_tests")]
#[pyo3(signature = (**kwargs))]
pub(crate) fn assemble_sql_test_plans<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let args = KeywordArguments::read(
        py,
        "plan_sql_tests",
        kwargs,
        (
            &["tests", "project", "adapter"],
            &[
                "sql_analysis_enabled",
                "validate_fixtures",
                "fixture_planning_context",
            ],
        ),
    )?;
    let tests: Vec<Bound<'py, PyAny>> = args.value("tests")?.extract()?;
    let project = args.value("project")?;
    let adapter = args.value("adapter")?;
    let mut context: Option<Bound<'py, RelationFixturePlanningContext>> = None;
    let (planned, diagnostics) = if args.flag("sql_analysis_enabled")?
        && args.flag("validate_fixtures")?
    {
        let given = args.value("fixture_planning_context")?;
        let shared = if given.is_none() {
            Bound::new(py, planning_context(&project, None)?)?
        } else {
            given.cast_into::<RelationFixturePlanningContext>()?
        };
        let validated = super::plan_fixtures::validate(&tests, (&project, &adapter), shared.get())?;
        context = Some(shared);
        validated
    } else {
        (tests.clone(), Default::default())
    };
    let plannable: Vec<_> = planned
        .into_iter()
        .enumerate()
        .filter_map(|(index, test)| (!diagnostics.contains_key(&index)).then_some(test))
        .collect();
    let plans = plan_sql_tests_natively(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("tests", PyTuple::new(py, plannable)?.into_any()),
                ("adapter", adapter),
                (
                    "sql_analysis_enabled",
                    args.value_or_false("sql_analysis_enabled")?,
                ),
                (
                    "render_sql",
                    pyo3::types::PyBool::new(py, false).to_owned().into_any(),
                ),
            ],
        )?),
    )?;
    let plans: Vec<Bound<'py, PyAny>> = plans.extract()?;
    if plans.len() != tests.len() - diagnostics.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "zip() argument lengths differ",
        ));
    }
    let mut plans = plans.into_iter();
    let models = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        models.set_item(model_reads::name_object(&model)?, model)?;
    }
    let result_class = registry::class(py, RecordId::SqlTestPlanResult)?;
    let mut results: Vec<Bound<'py, PyAny>> = Vec::new();
    for (index, test) in tests.iter().enumerate() {
        if let Some(diagnostic) = diagnostics.get(&index) {
            results.push(call_with(
                &result_class,
                &[
                    ("entry", py.None().into_bound(py)),
                    ("fixture_diagnostics", diagnostic.clone()),
                ],
            )?);
            continue;
        }
        let Some(plan) = plans.next() else {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "missing SQL-test plan",
            ));
        };
        let mut errors: Vec<String> = plan.getattr("error_messages")?.extract()?;
        errors.extend(super::plan_entries::expected_diagnostics(
            test,
            &plan,
            context.as_ref().map(Bound::get),
        )?);
        if !errors.is_empty() {
            results.push(call_with(
                &result_class,
                &[
                    ("entry", py.None().into_bound(py)),
                    ("fixture_diagnostics", PyTuple::new(py, errors)?.into_any()),
                ],
            )?);
            continue;
        }
        results.push(call_with(
            &result_class,
            &[
                (
                    "entry",
                    super::plan_entries::entry(
                        test,
                        &plan,
                        (&project, &models),
                        &args.value_or_false("sql_analysis_enabled")?,
                    )?,
                ),
                ("warnings", plan.getattr("warnings")?),
            ],
        )?);
    }
    PyTuple::new(py, results)
}
