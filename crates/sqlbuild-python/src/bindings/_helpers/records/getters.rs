//! Direct reads of native pyclass `#[getter]` attributes by name; anything absent falls back to `getattr`.

use std::collections::HashMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;

use crate::bindings::_helpers::analysis::binding_catalog::BindingCatalog;
use crate::bindings::_helpers::analysis_session::session::NativeModelAnalysisSession;
use crate::bindings::_helpers::build_progress::build_callbacks::BuildProgressCallbacks;
use crate::bindings::_helpers::build_progress::transient_lines::TransientLineCoordinator;
use crate::bindings::_helpers::compile_command::models::CompileReuseAttempt;
use crate::bindings::_helpers::compile_command::prepared_artifacts::PreparedCompileArtifacts;
use crate::bindings::_helpers::compile_command::reuse_recording::{
    CompileArtifactWrites, RecordedCompileOutput,
};
use crate::bindings::_helpers::compile_driver::diagnostic_collector::CollectedCompileDiagnostics;
use crate::bindings::_helpers::compile_driver::input_reads::CompileInputReads;
use crate::bindings::_helpers::compiled_project::audit_views::{
    NativeAuditInput, NativeCompiledAudit,
};
use crate::bindings::_helpers::compiled_project::compiled_model_view::NativeCompiledModel;
use crate::bindings::_helpers::compiled_project::function_views::{
    NativeCompiledFunction, NativeFunctionInput,
};
use crate::bindings::_helpers::compiled_project::inputs_view::NativeInputsView;
use crate::bindings::_helpers::compiled_project::model_input_view::NativeModelInput;
use crate::bindings::_helpers::compiled_project::project_view::NativeProjectView;
use crate::bindings::_helpers::compiled_project::seed_views::{
    NativeCompiledSeed, NativeSeedInput,
};
use crate::bindings::_helpers::compiled_project::source_views::{
    NativeCompiledSource, NativeSourceInput,
};
use crate::bindings::_helpers::compute_logs::storage::LocalFilesystemComputeLogStorage;
use crate::bindings::_helpers::dbt_events::stream::DbtEventStreamUpdate;
use crate::bindings::_helpers::dbt_interop::graph::DbtCombinedGraph;
use crate::bindings::_helpers::dbt_interop::reference_resolver::DbtCompileReferenceResolver;
use crate::bindings::_helpers::dbt_interop::runner::DbtRunner;
use crate::bindings::_helpers::diagnostics::trackers::BuildPhaseTimingTracker;
use crate::bindings::_helpers::discovery::model_file_record::NativeModelFile;
use crate::bindings::_helpers::event_exporting::dispatcher::EventExporterDispatcher;
use crate::bindings::_helpers::event_exporting::models::{
    BoundEventExporter, EventExportSummary, EventExporterAccounting, EventExporterCounts,
    EventExporterFailure,
};
use crate::bindings::_helpers::event_exporting::scope::EventExporterCommandScope;
use crate::bindings::_helpers::execution_history::postgres::PostgresExecutionHistory;
use crate::bindings::_helpers::execution_history::sqlite::SqliteExecutionHistory;
use crate::bindings::_helpers::graph::project_graph::CompiledProjectGraph;
use crate::bindings::_helpers::model_config::errors::NativeConfigError;
use crate::bindings::_helpers::planner_entries::models::{
    ModelPlanContext, PlanEntryBuildInputs, PlannerRelationsContext,
};
use crate::bindings::_helpers::planner_migrations::state_inspection::MigrationStateInspection;
use crate::bindings::_helpers::planner_phases::models::{
    PlannerIdentityContext, PlannerRuntime, PlannerScopeResolution, PlannerWarehouseState,
};
use crate::bindings::_helpers::presentation_text::style::PythonCliStyle;
use crate::bindings::_helpers::project_assembly::models::{
    NativeModelFacts, NativeProjectFacts, NativeProjectResources, NativeResourceFailure,
};
use crate::bindings::_helpers::records::getter_readers::{
    read_binding_catalog, read_bound_event_exporter, read_build_phase_timing_tracker,
    read_build_progress_callbacks, read_collected_compile_diagnostics,
    read_compile_artifact_writes, read_compile_input_reads, read_compile_reuse_attempt,
    read_compiled_project_graph, read_dbt_combined_graph, read_dbt_compile_reference_resolver,
    read_dbt_event_stream_update, read_dbt_runner, read_early_sql_lint, read_event_export_summary,
    read_event_exporter_accounting, read_event_exporter_command_scope, read_event_exporter_counts,
    read_event_exporter_dispatcher, read_event_exporter_failure, read_integration_asset_result,
    read_integration_check_result, read_integration_result_envelope,
    read_local_filesystem_compute_log_storage, read_migration_state_inspection,
    read_model_plan_context, read_native_audit_input, read_native_compiled_audit,
    read_native_compiled_function, read_native_compiled_model, read_native_compiled_seed,
    read_native_compiled_source, read_native_config_error, read_native_directory_snapshot,
    read_native_function_input, read_native_inputs_view, read_native_model_analysis_session,
    read_native_model_facts, read_native_model_file, read_native_model_input,
    read_native_project_facts, read_native_project_resources, read_native_project_view,
    read_native_resource_failure, read_native_scope_index, read_native_seed_input,
    read_native_source_input, read_plan_entry_build_inputs, read_planner_identity_context,
    read_planner_relations_context, read_planner_runtime, read_planner_scope_resolution,
    read_planner_warehouse_state, read_postgres_execution_history, read_prepared_compile_artifacts,
    read_python_cli_style, read_recorded_compile_output, read_sqlite_execution_history,
    read_terminal_event_claim, read_transient_line_coordinator,
};
use crate::bindings::_helpers::result_output::integration_envelope::{
    IntegrationAssetResult, IntegrationCheckResult, IntegrationResultEnvelope,
};
use crate::bindings::_helpers::result_output::terminal_index::TerminalEventClaim;
use crate::bindings::_helpers::rules::early_sql_lint::EarlySqlLint;
use crate::bindings::_helpers::scopes::scope_index::NativeScopeIndex;
use crate::bindings::models::NativeDirectorySnapshot;

type Dispatch = for<'py> fn(&Bound<'py, PyAny>, &str) -> Option<PyResult<Bound<'py, PyAny>>>;

static DISPATCH: PyOnceLock<HashMap<usize, Dispatch>> = PyOnceLock::new();

/// The `#[getter]` `name` of a native pyclass instance read in Rust, or `None` when not generated here.
pub(crate) fn getter_field<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let table: &HashMap<usize, Dispatch> = DISPATCH.get_or_init(py, || {
        let mut table: HashMap<usize, Dispatch> = HashMap::new();
        let _ = table.insert(
            py.get_type::<BindingCatalog>().as_ptr() as usize,
            read_binding_catalog,
        );
        let _ = table.insert(
            py.get_type::<NativeModelAnalysisSession>().as_ptr() as usize,
            read_native_model_analysis_session,
        );
        let _ = table.insert(
            py.get_type::<BuildProgressCallbacks>().as_ptr() as usize,
            read_build_progress_callbacks,
        );
        let _ = table.insert(
            py.get_type::<TransientLineCoordinator>().as_ptr() as usize,
            read_transient_line_coordinator,
        );
        let _ = table.insert(
            py.get_type::<CompileReuseAttempt>().as_ptr() as usize,
            read_compile_reuse_attempt,
        );
        let _ = table.insert(
            py.get_type::<PreparedCompileArtifacts>().as_ptr() as usize,
            read_prepared_compile_artifacts,
        );
        let _ = table.insert(
            py.get_type::<CompileArtifactWrites>().as_ptr() as usize,
            read_compile_artifact_writes,
        );
        let _ = table.insert(
            py.get_type::<RecordedCompileOutput>().as_ptr() as usize,
            read_recorded_compile_output,
        );
        let _ = table.insert(
            py.get_type::<CollectedCompileDiagnostics>().as_ptr() as usize,
            read_collected_compile_diagnostics,
        );
        let _ = table.insert(
            py.get_type::<CompileInputReads>().as_ptr() as usize,
            read_compile_input_reads,
        );
        let _ = table.insert(
            py.get_type::<NativeAuditInput>().as_ptr() as usize,
            read_native_audit_input,
        );
        let _ = table.insert(
            py.get_type::<NativeCompiledAudit>().as_ptr() as usize,
            read_native_compiled_audit,
        );
        let _ = table.insert(
            py.get_type::<NativeCompiledModel>().as_ptr() as usize,
            read_native_compiled_model,
        );
        let _ = table.insert(
            py.get_type::<NativeCompiledFunction>().as_ptr() as usize,
            read_native_compiled_function,
        );
        let _ = table.insert(
            py.get_type::<NativeFunctionInput>().as_ptr() as usize,
            read_native_function_input,
        );
        let _ = table.insert(
            py.get_type::<NativeInputsView>().as_ptr() as usize,
            read_native_inputs_view,
        );
        let _ = table.insert(
            py.get_type::<NativeModelInput>().as_ptr() as usize,
            read_native_model_input,
        );
        let _ = table.insert(
            py.get_type::<NativeProjectView>().as_ptr() as usize,
            read_native_project_view,
        );
        let _ = table.insert(
            py.get_type::<NativeCompiledSeed>().as_ptr() as usize,
            read_native_compiled_seed,
        );
        let _ = table.insert(
            py.get_type::<NativeSeedInput>().as_ptr() as usize,
            read_native_seed_input,
        );
        let _ = table.insert(
            py.get_type::<NativeCompiledSource>().as_ptr() as usize,
            read_native_compiled_source,
        );
        let _ = table.insert(
            py.get_type::<NativeSourceInput>().as_ptr() as usize,
            read_native_source_input,
        );
        let _ = table.insert(
            py.get_type::<LocalFilesystemComputeLogStorage>().as_ptr() as usize,
            read_local_filesystem_compute_log_storage,
        );
        let _ = table.insert(
            py.get_type::<DbtEventStreamUpdate>().as_ptr() as usize,
            read_dbt_event_stream_update,
        );
        let _ = table.insert(
            py.get_type::<DbtCombinedGraph>().as_ptr() as usize,
            read_dbt_combined_graph,
        );
        let _ = table.insert(
            py.get_type::<DbtCompileReferenceResolver>().as_ptr() as usize,
            read_dbt_compile_reference_resolver,
        );
        let _ = table.insert(
            py.get_type::<DbtRunner>().as_ptr() as usize,
            read_dbt_runner,
        );
        let _ = table.insert(
            py.get_type::<BuildPhaseTimingTracker>().as_ptr() as usize,
            read_build_phase_timing_tracker,
        );
        let _ = table.insert(
            py.get_type::<NativeModelFile>().as_ptr() as usize,
            read_native_model_file,
        );
        let _ = table.insert(
            py.get_type::<NativeDirectorySnapshot>().as_ptr() as usize,
            read_native_directory_snapshot,
        );
        let _ = table.insert(
            py.get_type::<EventExporterDispatcher>().as_ptr() as usize,
            read_event_exporter_dispatcher,
        );
        let _ = table.insert(
            py.get_type::<BoundEventExporter>().as_ptr() as usize,
            read_bound_event_exporter,
        );
        let _ = table.insert(
            py.get_type::<EventExportSummary>().as_ptr() as usize,
            read_event_export_summary,
        );
        let _ = table.insert(
            py.get_type::<EventExporterAccounting>().as_ptr() as usize,
            read_event_exporter_accounting,
        );
        let _ = table.insert(
            py.get_type::<EventExporterCounts>().as_ptr() as usize,
            read_event_exporter_counts,
        );
        let _ = table.insert(
            py.get_type::<EventExporterFailure>().as_ptr() as usize,
            read_event_exporter_failure,
        );
        let _ = table.insert(
            py.get_type::<EventExporterCommandScope>().as_ptr() as usize,
            read_event_exporter_command_scope,
        );
        let _ = table.insert(
            py.get_type::<PostgresExecutionHistory>().as_ptr() as usize,
            read_postgres_execution_history,
        );
        let _ = table.insert(
            py.get_type::<SqliteExecutionHistory>().as_ptr() as usize,
            read_sqlite_execution_history,
        );
        let _ = table.insert(
            py.get_type::<CompiledProjectGraph>().as_ptr() as usize,
            read_compiled_project_graph,
        );
        let _ = table.insert(
            py.get_type::<NativeConfigError>().as_ptr() as usize,
            read_native_config_error,
        );
        let _ = table.insert(
            py.get_type::<ModelPlanContext>().as_ptr() as usize,
            read_model_plan_context,
        );
        let _ = table.insert(
            py.get_type::<PlanEntryBuildInputs>().as_ptr() as usize,
            read_plan_entry_build_inputs,
        );
        let _ = table.insert(
            py.get_type::<PlannerRelationsContext>().as_ptr() as usize,
            read_planner_relations_context,
        );
        let _ = table.insert(
            py.get_type::<MigrationStateInspection>().as_ptr() as usize,
            read_migration_state_inspection,
        );
        let _ = table.insert(
            py.get_type::<PlannerIdentityContext>().as_ptr() as usize,
            read_planner_identity_context,
        );
        let _ = table.insert(
            py.get_type::<PlannerRuntime>().as_ptr() as usize,
            read_planner_runtime,
        );
        let _ = table.insert(
            py.get_type::<PlannerScopeResolution>().as_ptr() as usize,
            read_planner_scope_resolution,
        );
        let _ = table.insert(
            py.get_type::<PlannerWarehouseState>().as_ptr() as usize,
            read_planner_warehouse_state,
        );
        let _ = table.insert(
            py.get_type::<PythonCliStyle>().as_ptr() as usize,
            read_python_cli_style,
        );
        let _ = table.insert(
            py.get_type::<NativeModelFacts>().as_ptr() as usize,
            read_native_model_facts,
        );
        let _ = table.insert(
            py.get_type::<NativeProjectFacts>().as_ptr() as usize,
            read_native_project_facts,
        );
        let _ = table.insert(
            py.get_type::<NativeProjectResources>().as_ptr() as usize,
            read_native_project_resources,
        );
        let _ = table.insert(
            py.get_type::<NativeResourceFailure>().as_ptr() as usize,
            read_native_resource_failure,
        );
        let _ = table.insert(
            py.get_type::<IntegrationAssetResult>().as_ptr() as usize,
            read_integration_asset_result,
        );
        let _ = table.insert(
            py.get_type::<IntegrationCheckResult>().as_ptr() as usize,
            read_integration_check_result,
        );
        let _ = table.insert(
            py.get_type::<IntegrationResultEnvelope>().as_ptr() as usize,
            read_integration_result_envelope,
        );
        let _ = table.insert(
            py.get_type::<TerminalEventClaim>().as_ptr() as usize,
            read_terminal_event_claim,
        );
        let _ = table.insert(
            py.get_type::<EarlySqlLint>().as_ptr() as usize,
            read_early_sql_lint,
        );
        let _ = table.insert(
            py.get_type::<NativeScopeIndex>().as_ptr() as usize,
            read_native_scope_index,
        );
        table
    });
    let dispatch: &Dispatch = table.get(&(value.get_type().as_ptr() as usize))?;
    dispatch(value, name)
}
