//! `sqb build`: resolve, compile, gate, execute and report one direct build.

use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::build_command::completion::{
    complete_direct_build, finalize_exceptional_cost, finalize_no_work_with_timings,
    record_pending_cost, write_partial_timings,
};
use crate::bindings::_helpers::build_command::execution::execute_direct_build;
use crate::bindings::_helpers::build_command::invocation::{BuildContext, resolve_build_context};
use crate::bindings::_helpers::build_command::planning::{
    compile_build_plan, enforce_build_plan_policies, run_defer_clone_prephase,
    write_compile_target, write_plan_text,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const TIMING_TRACKER_MODULE: &str = "sqlbuild._native";
const RESOURCE_REPORTING_MODULE: &str = "sqlbuild.diagnostics.main.process_resource_reporting";
const DEADLINE_MODULE: &str = "sqlbuild.runtime.execution_limits.main.execution_deadline_scope";
const PROVIDER_SESSION_MODULE: &str = "sqlbuild.provider.main.session";

fn run_with_providers(context: &BuildContext<'_>) -> PyResult<i32> {
    let py: Python<'_> = context.py();
    let session: Bound<'_, PyAny> = call_with(
        &imported(py, PROVIDER_SESSION_MODULE, "build_provider_session")?,
        &[(
            "discovered_providers",
            context.get("discovered_inputs")?.getattr("providers")?,
        )],
    )?;
    let built: PyResult<i32> = run_planned_build(context, &session.getattr("providers")?);
    let closed: PyResult<Bound<'_, PyAny>> = session.call_method0("close");
    let exit_code: i32 = built?;
    closed?;
    Ok(exit_code)
}

fn run_planned_build(context: &BuildContext<'_>, providers: &Bound<'_, PyAny>) -> PyResult<i32> {
    run_defer_clone_prephase(context)?;
    let pipeline: Bound<'_, PyAny> = compile_build_plan(context)?;
    write_plan_text(context, &pipeline)?;
    enforce_build_plan_policies(context, &pipeline)?;
    write_compile_target(context, &pipeline)?;
    if finalize_no_work_with_timings(context, &pipeline)? {
        return Ok(0);
    }
    let started_at: Bound<'_, PyAny> = record_pending_cost(context, &pipeline)?;
    match execute_direct_build(context, &pipeline, providers) {
        Ok((preparation, outcome, checks)) => complete_direct_build(
            context,
            &pipeline,
            (&preparation, &outcome, &checks),
            &started_at,
        ),
        Err(error) => {
            finalize_exceptional_cost(context, &pipeline, (&started_at, &error));
            Err(error)
        }
    }
}

fn run_within_limits(
    request: &Bound<'_, PyAny>,
    tracker: &Bound<'_, PyAny>,
    started: Instant,
) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let context: BuildContext<'_> = resolve_build_context(request, tracker, started)?;
    let limits: Bound<'_, PyAny> = context.get("execution_limits")?;
    let deadline: Bound<'_, PyAny> = call_with(
        &imported(py, DEADLINE_MODULE, "execution_deadline_scope")?,
        &[
            (
                "max_duration_seconds",
                limits.getattr("max_duration_seconds")?,
            ),
            ("max_duration", limits.getattr("max_duration")?),
            ("target_name", context.get("effective_target_name")?),
            ("remediation", limits.getattr("remediation")?),
        ],
    )?;
    within(&deadline, |_| run_with_providers(&context))
}

/// Run one `sqb build` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_build_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let tracker: Bound<'_, PyAny> =
        imported(py, TIMING_TRACKER_MODULE, "BuildPhaseTimingTracker")?.call0()?;
    let reporting: Bound<'_, PyAny> = call_with(
        &imported(py, RESOURCE_REPORTING_MODULE, "process_resource_reporting")?,
        &[("enabled", request.getattr("debug")?)],
    )?;
    within(&reporting, |_| {
        within(&tracker.call_method0("scope")?, |_| {
            let started: Instant = Instant::now();
            run_within_limits(request, &tracker, started).inspect_err(|_| {
                let verbose: bool = request
                    .getattr("verbose")
                    .and_then(|value| value.is_truthy())
                    .unwrap_or(false)
                    || request
                        .getattr("debug")
                        .and_then(|value| value.is_truthy())
                        .unwrap_or(false);
                if verbose {
                    let _ = write_partial_timings(py, &tracker);
                }
            })
        })
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_build_command, module)?)?;
    Ok(())
}
