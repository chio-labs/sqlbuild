//! Compile the build plan, show it, gate it and write the compile target.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use sqlbuild_core::build_command::models::PlanSafetyGates;

use crate::bindings::_helpers::build_command::invocation::BuildContext;
use crate::bindings::_helpers::build_command::policies::{enforce_plan_policies, model_limit};
use crate::bindings::_helpers::build_command::support::{
    boolean, emit, joined, keyword_relay, none,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const CONSTANTS_MODULE: &str = "sqlbuild.cli.commands.constants";
const DEFER_CLONE_MODULE: &str = "sqlbuild.cli.commands._helpers.build_planning.defer_clone";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const VERBOSE_INSPECTION_MODULE: &str = "sqlbuild.cli.progress.main.verbose_inspection_output";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const RUNTIME_CONTRACT_MODELS: &str = "sqlbuild.runtime.contracts.models";
const MANIFEST_MODULE: &str = "sqlbuild.compiler.manifest.main.build";
const CONNECTION_TIMING: [&str; 2] = ["connection_count", "elapsed_seconds"];

/// Clone out-of-selection boundaries from the defer-clone origin before planning.
pub(crate) fn run_defer_clone_prephase(context: &BuildContext<'_>) -> PyResult<()> {
    let origin: Bound<'_, PyAny> = context.get("effective_defer_clone_from")?;
    if origin.is_none() {
        return Ok(());
    }
    call_with(
        &imported(
            context.py(),
            DEFER_CLONE_MODULE,
            "run_defer_clone_boundary_prephase",
        )?,
        &[
            ("request", context.request.clone()),
            ("invocation", context.invocation.clone()),
            ("origin_target_name", origin),
        ],
    )?;
    Ok(())
}

fn request_options<'py>(context: &BuildContext<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let request: &Bound<'py, PyAny> = &context.request;
    let field = |name: &str| request.getattr(name);
    let should_load_sources: Bound<'py, PyAny> = context.get("should_load_sources")?;
    let python_selectors: bool =
        context.request_flag("include_python")? || should_load_sources.is_truthy()?;
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            EXTERNAL_REFS_MODULE,
            "resolve_external_sql_reference_resolver",
        )?,
        &[
            ("project_dir", context.get("effective_project_dir")?),
            ("discovered_inputs", context.get("discovered_inputs")?),
        ],
    )?;
    call_with(
        &imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?,
        &[
            ("no_sql_validation", field("no_sql_validation")?),
            ("no_cache", field("no_cache")?),
            ("selected_target", field("selected_target")?),
            ("defer_to", field("defer_to")?),
            ("defer_sources_to", field("defer_sources_to")?),
            ("cursor_overrides", field("cursor_overrides")?),
            ("select", field("select")?),
            ("exclude", field("exclude")?),
            ("full_refresh", field("full_refresh")?),
            ("auto_load_sources", should_load_sources),
            ("reload_sources", field("reload_sources")?),
            ("connection_config", context.get("connection_config")?),
            ("cli_vars", field("cli_vars")?),
            ("external_sql_reference_resolver", resolver),
            (
                "resolve_python_run_selectors",
                boolean(py, python_selectors),
            ),
            ("max_microbatches", field("max_microbatches")?),
            ("selection_diagnostics", field("selection_diagnostics")?),
            ("plan_sql_tests", field("run_tests")?),
            ("accepts_unit_test_selectors", boolean(py, true)),
        ],
    )
}

/// Run the compile pipeline with planning and connection progress.
pub(crate) fn compile_build_plan<'py>(context: &BuildContext<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    emit(&context.stream, "\n")?;
    let connection: Bound<'py, PyAny> = context.get("connection_progress")?;
    let hooks: Bound<'py, PyAny> = call_with(
        &imported(py, RUNTIME_CONTRACT_MODELS, "ConnectionHooks")?,
        &[
            (
                "on_progress",
                context.get("planning_progress")?.getattr("on_progress")?,
            ),
            (
                "on_connection_start",
                connection.getattr("on_connection_start")?,
            ),
            (
                "on_connection_complete",
                keyword_relay(
                    connection.getattr("on_connection_complete")?,
                    &CONNECTION_TIMING,
                )?,
            ),
            (
                "on_connection_error",
                keyword_relay(
                    connection.getattr("on_connection_error")?,
                    &CONNECTION_TIMING,
                )?,
            ),
        ],
    )?;
    let manager: Bound<'py, PyAny> = call_with(
        &imported(py, VERBOSE_INSPECTION_MODULE, "verbose_inspection_output")?,
        &[("enabled", context.request.getattr("verbose")?)],
    )?;
    within(&manager, |_| {
        call_with(
            &imported(py, NATIVE_MODULE, "run_compile_pipeline")?,
            &[
                ("discovered_inputs", context.get("discovered_inputs")?),
                ("adapter", context.get("adapter")?),
                ("options", request_options(context)?),
                ("hooks", hooks),
            ],
        )
    })
}

/// Write the formatted plan to stdout, or stderr for debug and JSON runs.
pub(crate) fn write_plan_text(
    context: &BuildContext<'_>,
    pipeline: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = context.py();
    let machine: bool = context.request_flag("debug")? || context.request_flag("json_output")?;
    let stream: Bound<'_, PyAny> =
        py.import("sys")?
            .getattr(if machine { "stderr" } else { "stdout" })?;
    let plan_text: String = call_with(
        &imported(py, NATIVE_MODULE, "format_plan")?,
        &[
            ("plan", pipeline.getattr("plan_output")?),
            ("full_refresh", context.request.getattr("full_refresh")?),
            ("use_color", boolean(py, context.use_color)),
            (
                "python_plan_entries",
                pipeline.getattr("python_plan_entries")?,
            ),
            ("include_direct_freshness_diagnostics", boolean(py, false)),
        ],
    )?
    .extract()?;
    emit(&stream, &format!("\n{plan_text}\n\n"))
}

fn constant(py: Python<'_>, name: &str) -> PyResult<String> {
    imported(py, CONSTANTS_MODULE, name)?.extract()
}

/// Apply every plan safety gate with the build's allow flags.
pub(crate) fn enforce_build_plan_policies(
    context: &BuildContext<'_>,
    pipeline: &Bound<'_, PyAny>,
) -> Result<(), PyErr> {
    let py: Python<'_> = context.py();
    let gates: PlanSafetyGates = PlanSafetyGates {
        allow_missing_migration_origin: context.request_flag("allow_missing_migration_origin")?,
        allow_snapshot_full_refresh: context.request_flag("allow_snapshot_full_refresh")?,
        allow_table_type_downgrade: context.request_flag("allow_table_type_downgrade")?,
        allow_retention_decrease: context.request_flag("allow_retention_decrease")?,
        missing_origin_help: constant(py, "MISSING_ORIGIN_BUILD_HELP")?,
        snapshot_full_refresh_help: constant(py, "SNAPSHOT_FULL_REFRESH_BUILD_HELP")?,
        table_type_downgrade_help: constant(py, "TABLE_TYPE_DOWNGRADE_BUILD_HELP")?,
        retention_decrease_help: constant(py, "RETENTION_DECREASE_BUILD_HELP")?,
        execution_limit_note: constant(py, "EXECUTION_LIMIT_BUILD_NOTE")?,
    };
    let sys: Bound<'_, PyAny> = py.import("sys")?.into_any();
    enforce_plan_policies(
        &pipeline.getattr("plan_output")?,
        (
            &gates,
            &context
                .get("discovered_inputs")?
                .getattr("project_config")?
                .getattr("snapshots")?,
        ),
        &model_limit(
            &context.get("effective_target_name")?,
            &context.get("execution_limits")?,
        )?,
        (&sys.getattr("stdin")?, &sys.getattr("stdout")?),
    )
}

/// Write the compile target artifacts with the optional manifest payload.
pub(crate) fn write_compile_target(
    context: &BuildContext<'_>,
    pipeline: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = context.py();
    let plan: Bound<'_, PyAny> = pipeline.getattr("plan_output")?;
    let manifest: Bound<'_, PyAny> = if context.request_flag("manifest")? {
        call_with(
            &imported(py, MANIFEST_MODULE, "build_manifest")?,
            &[
                ("project", pipeline.getattr("project")?),
                ("plan_output", plan.clone()),
                (
                    "project_name",
                    context
                        .get("discovered_inputs")?
                        .getattr("project_config")?
                        .getattr("name")?,
                ),
                ("adapter_type", context.get("adapter_name")?),
                ("upstream_deps", plan.getattr("upstream_deps")?),
                ("downstream_deps", plan.getattr("downstream_deps")?),
            ],
        )?
    } else {
        none(py)
    };
    call_with(
        &imported(py, NATIVE_MODULE, "write_compile_target")?,
        &[
            (
                "target_dir",
                joined(&context.get("effective_project_dir")?, &["target"])?,
            ),
            ("adapter", context.get("adapter")?),
            ("plan_output", plan),
            ("manifest", manifest),
        ],
    )?;
    Ok(())
}
