//! Project native planning failures into existing located diagnostic exceptions.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::sql_test_glue::plan_values::string;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};

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
        let kwargs = pyo3::types::PyDict::new(py);
        use pyo3::types::PyDictMethods;
        kwargs.set_item("help", help)?;
        let class = if let Some(test) = found {
            kwargs.set_item(
                "location",
                call_with(
                    &imported(
                        py,
                        "sqlbuild.compiler.compile.classes.sql_test_cte_locator",
                        "SqlTestCteLocator",
                    )?
                    .getattr("locate")?,
                    &[
                        ("test_file", test.getattr("test_file")?),
                        ("test_block", test.getattr("test_block")?),
                        ("cte_name", cte),
                        ("call", call),
                    ],
                )?,
            )?;
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
