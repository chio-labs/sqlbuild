//! Project native planning failures into existing located diagnostic exceptions.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::sql_test_glue::plan_values::string;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_analysis::sql_test_attachment::main::sql_test_cte_location::sql_test_cte_location;
use sqlbuild_analysis::sql_test_attachment::models::CteLocation;

const SOURCE_LOCATION_MODULE: &str = "sqlbuild.spec.contracts.models";

/// The location of `call` inside one CTE of a SQL test block, else the CTE header, else the block.
fn cte_call_location<'py>(
    py: Python<'py>,
    test: &Bound<'py, PyAny>,
    (cte, call): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let test_file: Bound<'py, PyAny> = test.getattr("test_file")?;
    let call: Option<String> = call.extract()?;
    let located: CteLocation = sql_test_cte_location(
        &test_file.getattr("contents")?.extract::<String>()?,
        &test
            .getattr("test_block")?
            .getattr("sql_body")?
            .extract::<String>()?,
        &cte.extract::<String>()?,
        call.as_deref(),
    );
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("path", test_file.getattr("relative_path")?)?;
    arguments.set_item("line", located.line)?;
    arguments.set_item("column", located.column)?;
    arguments.set_item("end_line", located.end_line)?;
    arguments.set_item("end_column", located.end_column)?;
    imported(py, SOURCE_LOCATION_MODULE, "SourceLocation")?.call((), Some(&arguments))
}

pub(super) fn planning_error(
    py: Python<'_>,
    error: PyErr,
    tests: &Bound<'_, PyAny>,
) -> PyResult<PyErr> {
    let message = error.value(py).str()?.to_string();
    if let Some(payload) = message.strip_prefix("sql_test_reference:") {
        let payload = imported(py, "orjson", "loads")?.call1((payload,))?;
        let mut found = None;
        for test in tests.try_iter()? {
            let test = test?;
            if test.getattr("name")?.eq(payload.get_item("testName")?)?
                && test
                    .getattr("test_file")?
                    .getattr("relative_path")?
                    .str()?
                    .into_any()
                    .eq(payload.get_item("fileLabel")?)?
            {
                found = Some(test);
                break;
            }
        }
        let cte = payload.get_item("cteName")?;
        let call = payload.get_item("call")?;
        let message = format!(
            "SQL test CTE '{}' calls {}, which the test query cannot resolve",
            cte.extract::<String>()?,
            call.extract::<String>()?
        );
        let help = format!(
            "Mock it in the test, for example {} AS (SELECT ...), or call __ref(\"<model>\") on a model the test runs.",
            payload.get_item("mockCte")?.extract::<String>()?
        );
        let kwargs = PyDict::new(py);
        kwargs.set_item("help", help)?;
        let class = if let Some(test) = found {
            kwargs.set_item("location", cte_call_location(py, &test, (&cte, &call))?)?;
            "SqlTestReferenceError"
        } else {
            kwargs.set_item(
                "code",
                imported(
                    py,
                    "sqlbuild.compiler.compile.constants",
                    "SQL_TEST_HELPER_REFERENCE_CODE",
                )?,
            )?;
            "CompileInputError"
        };
        return Ok(PyErr::from_value(
            imported(py, "sqlbuild.compiler.compile.exceptions", class)?
                .call((message,), Some(&kwargs))?,
        ));
    }
    let (module, class, message) = if let Some(message) = message.strip_prefix("compile_input:") {
        (
            "sqlbuild.compiler.compile.exceptions",
            "CompileInputError",
            message.to_owned(),
        )
    } else if let Some(message) = message.strip_prefix("planner_input:") {
        (
            "sqlbuild.compiler.planner.exceptions",
            "PlannerInputError",
            message.to_owned(),
        )
    } else {
        (
            "sqlbuild.compiler.planner.exceptions",
            "NativeSqlTestPlanningError",
            format!("native SQL-test planning failed: {message}"),
        )
    };
    Ok(PyErr::from_value(
        imported(py, module, class)?.call1((string(py, &message),))?,
    ))
}
