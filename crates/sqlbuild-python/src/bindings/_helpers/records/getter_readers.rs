//! The per-class readers behind `getters::getter_field`, one per native pyclass.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyResult, Python};

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
use crate::bindings::_helpers::result_output::integration_envelope::{
    IntegrationAssetResult, IntegrationCheckResult, IntegrationResultEnvelope,
};
use crate::bindings::_helpers::result_output::terminal_index::TerminalEventClaim;
use crate::bindings::_helpers::rules::early_sql_lint::EarlySqlLint;
use crate::bindings::_helpers::scopes::scope_index::NativeScopeIndex;
use crate::bindings::models::NativeDirectorySnapshot;

pub(crate) fn read_binding_catalog<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<BindingCatalog>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "schemas" => (&this.schemas).into_bound_py_any(py),
        "dialect" => (&this.dialect).into_bound_py_any(py),
        "quoted_ignore_case" => (&this.quoted_ignore_case).into_bound_py_any(py),
        "analysis_shapes" => (&this.analysis_shapes).into_bound_py_any(py),
        "expression_shapes" => (&this.expression_shapes).into_bound_py_any(py),
        "native" => (&this.native).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_model_analysis_session<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeModelAnalysisSession>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "fact_models" => this.fact_models().into_bound_py_any(py),
        "cache_stats" => this.cache_stats().into_bound_py_any(py),
        "sharing" => this.sharing().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_build_progress_callbacks<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<BuildProgressCallbacks>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "elapsed" => this.elapsed().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_transient_line_coordinator<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<TransientLineCoordinator>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "lock" => (&this.lock).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_compile_reuse_attempt<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<CompileReuseAttempt>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "outcome" => (&this.outcome).into_bound_py_any(py),
        "project_dir" => (&this.project_dir).into_bound_py_any(py),
        "started" => (&this.started).into_bound_py_any(py),
        "check_ms" => (&this.check_ms).into_bound_py_any(py),
        "exit_code" => (&this.exit_code).into_bound_py_any(py),
        "entry_path" => (&this.entry_path).into_bound_py_any(py),
        "native" => (&this.native).into_bound_py_any(py),
        "selected_target" => (&this.selected_target).into_bound_py_any(py),
        "json_output" => (&this.json_output).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_prepared_compile_artifacts<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PreparedCompileArtifacts>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "enabled" => this.enabled().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_compile_artifact_writes<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<CompileArtifactWrites>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "artifacts" => this
            .artifacts(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_recorded_compile_output<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<RecordedCompileOutput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "stderr_lines" => this.stderr_lines(py).into_bound_py_any(py),
        "stdout" => this.stdout(py).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_collected_compile_diagnostics<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<CollectedCompileDiagnostics>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "diagnostics" => this
            .diagnostics(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_compile_input_reads<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<CompileInputReads>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "environment_names" => this
            .environment_names(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "settings_classes" => this
            .settings_classes(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "read_run_id" => this.read_run_id().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_audit_input<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeAuditInput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "audit_file" => this
            .audit_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "audit_block" => this
            .audit_block(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "sql_body" => this
            .sql_body(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evaluation_mode" => this
            .evaluation_mode(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "measurement_contract" => this
            .measurement_contract(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "thresholds" => this
            .thresholds(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "minimum_samples" => this
            .minimum_samples(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "measure_sql" => this
            .measure_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evidence_sql" => this
            .evidence_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evidence_limit" => this
            .evidence_limit(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_target_kind" => this
            .attached_target_kind(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_target_name" => this
            .attached_target_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_column_name" => this
            .attached_column_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "severity" => this
            .severity(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "run_scope" => this
            .run_scope(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "always_run" => this
            .always_run(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "description" => this
            .description(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "declaration_usages" => this
            .declaration_usages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "assembly_row" => this
            .assembly_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_compiled_audit<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeCompiledAudit>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "audit_file" => this
            .audit_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "audit_block" => this
            .audit_block(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "sql_body" => this
            .sql_body(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evaluation_mode" => this
            .evaluation_mode(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "measurement_contract" => this
            .measurement_contract(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "thresholds" => this
            .thresholds(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "minimum_samples" => this
            .minimum_samples(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "measure_sql" => this
            .measure_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evidence_sql" => this
            .evidence_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "evidence_limit" => this
            .evidence_limit(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_target_kind" => this
            .attached_target_kind(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_target_name" => this
            .attached_target_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_column_name" => this
            .attached_column_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "severity" => this
            .severity(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "run_scope" => this
            .run_scope(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "always_run" => this
            .always_run(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "description" => this
            .description(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "key" => this.key(py).and_then(|value| value.into_bound_py_any(py)),
        "scope_deps" => this
            .scope_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "definition_name" => this
            .definition_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_compiled_model<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeCompiledModel>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "key" => this.key(py).and_then(|value| value.into_bound_py_any(py)),
        "deps" => this.deps(py).and_then(|value| value.into_bound_py_any(py)),
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "relative_path" => this
            .relative_path(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "query_sql" => this
            .query_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "config" => this
            .config(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "destination" => this
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "reference_rows" => this
            .reference_rows(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "relation_key_row" => this
            .relation_key_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "key_row" => this
            .key_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "dep_rows" => this
            .dep_rows(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "destination_row" => this
            .destination_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "inferred_rows" => this
            .inferred_rows(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_column_rows" => this
            .schema_column_rows(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "has_dynamic_columns" => this
            .dynamic_columns_declared(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "output_column_count" => this
            .output_column_count(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_entry" => this
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "inferred_columns" => this
            .inferred_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fast_lineage_columns" => this
            .fast_lineage_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fast_lineage_has_star" => this
            .fast_lineage_has_star(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fast_lineage_star_resolved" => this
            .fast_lineage_star_resolved(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "authored_sql" => this
            .authored_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "authored_query_sql" => this
            .authored_query_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "output_column_locations" => this
            .output_column_locations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "extract_implicit_alias_columns" => this
            .extract_implicit_alias_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "macro_deps" => this
            .macro_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "enum_declarations" => this
            .enum_declarations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "constant_declarations" => this
            .constant_declarations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "enum_columns" => this
            .enum_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "binding_diagnostics" => this
            .binding_diagnostics(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "binding_validated" => this
            .binding_validated(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "dynamic_column_contract" => this
            .dynamic_column_contract(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "unchecked_output_columns" => this
            .unchecked_output_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "rejected_sql_analysis_opt_out" => this
            .rejected_sql_analysis_opt_out(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_compiled_function<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeCompiledFunction>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "arguments" => this
            .arguments(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "returns" => this
            .returns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "body_sql" => this
            .body_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "return_columns" => this
            .return_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "language" => this
            .language(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "runtime_version" => this
            .runtime_version(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "entry_point" => this
            .entry_point(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "packages" => this
            .packages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "tags" => this.tags(py).and_then(|value| value.into_bound_py_any(py)),
        "description" => this
            .description(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "key" => this.key(py).and_then(|value| value.into_bound_py_any(py)),
        "deps" => this.deps(py).and_then(|value| value.into_bound_py_any(py)),
        "relative_path" => this
            .relative_path(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "source_file_path" => this
            .source_file_path(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "destination" => this
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fingerprint_destination" => this
            .fingerprint_destination(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_function_input<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeFunctionInput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "arguments" => this
            .arguments(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "returns" => this
            .returns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "body_sql" => this
            .body_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "return_columns" => this
            .return_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "language" => this
            .language(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "runtime_version" => this
            .runtime_version(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "entry_point" => this
            .entry_point(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "packages" => this
            .packages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "tags" => this.tags(py).and_then(|value| value.into_bound_py_any(py)),
        "description" => this
            .description(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "function_file" => this
            .function_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "database" => this
            .database(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema" => this
            .schema(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "logical_database" => this
            .logical_database(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "logical_schema" => this
            .logical_schema(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fingerprint_database" => this
            .fingerprint_database(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fingerprint_schema" => this
            .fingerprint_schema(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fingerprint_logical_database" => this
            .fingerprint_logical_database(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "fingerprint_logical_schema" => this
            .fingerprint_logical_schema(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "declaration_usages" => this
            .declaration_usages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "assembly_row" => this
            .assembly_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_inputs_view<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeInputsView>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "run_id" => this.run_id().into_bound_py_any(py),
        "effective_target_name" => this.effective_target_name().into_bound_py_any(py),
        "no_sql_validation" => this.is_sql_validation_skipped().into_bound_py_any(py),
        "model_inputs" => this.model_inputs(py).into_bound_py_any(py),
        "native_project" => this.native_project(py).into_bound_py_any(py),
        "project_config" => this.project_config(py).into_bound_py_any(py),
        "local_config" => this.local_config(py).into_bound_py_any(py),
        "discovered_inputs" => this.discovered_inputs(py).into_bound_py_any(py),
        "sql_lexical_syntax" => this.sql_lexical_syntax(py).into_bound_py_any(py),
        "effective_target" => this.effective_target(py).into_bound_py_any(py),
        "compile_cache_dir" => this.compile_cache_dir(py).into_bound_py_any(py),
        "effective_connection" => this.effective_connection(py).into_bound_py_any(py),
        "effective_vars" => this.effective_vars(py).into_bound_py_any(py),
        "macro_context" => this.macro_context(py).into_bound_py_any(py),
        "loaded_macros" => this.loaded_macros(py).into_bound_py_any(py),
        "public_enums" => this.public_enums(py).into_bound_py_any(py),
        "public_constants" => this.public_constants(py).into_bound_py_any(py),
        "external_sql_reference_resolver" => this
            .external_sql_reference_resolver(py)
            .into_bound_py_any(py),
        "effective_settings" => this.effective_settings(py).into_bound_py_any(py),
        "seed_inputs" => this.seed_inputs(py).into_bound_py_any(py),
        "source_inputs" => this.source_inputs(py).into_bound_py_any(py),
        "sql_function_inputs" => this.sql_function_inputs(py).into_bound_py_any(py),
        "test_inputs" => this.test_inputs(py).into_bound_py_any(py),
        "scenario_inputs" => this.scenario_inputs(py).into_bound_py_any(py),
        "audit_inputs" => this.audit_inputs(py).into_bound_py_any(py),
        "diagnostics" => this.diagnostics(py).into_bound_py_any(py),
        "scope_index" => this.scope_index(py).into_bound_py_any(py),
        "declaration_scope" => this.declaration_scope(py).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_model_input<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeModelInput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "model_file" => this
            .model_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "config" => this
            .config(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "query_sql" => this
            .query_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "macro_source_sql" => this
            .macro_source_sql(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "references" => this
            .references(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_entry" => this
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "reference_rows" => this
            .reference_rows(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "relation_key_row" => this
            .relation_key_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "attached_schema_name" => this
            .attached_schema_name(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_file" => this.schema_file(py).into_bound_py_any(py),
        "sql_validation_enabled" => this
            .sql_validation_enabled(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "rejected_sql_analysis_opt_out" => this
            .rejected_sql_analysis_opt_out(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "enum_declarations" => this
            .enum_declarations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "constant_declarations" => this
            .constant_declarations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "enum_columns" => this
            .enum_columns(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "macro_deps" => this
            .macro_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "macro_usages" => this
            .macro_usages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "declaration_usages" => this
            .declaration_usages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "sql_expansion" => this
            .sql_expansion(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "lint_expansion" => this
            .lint_expansion(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_project_view<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeProjectView>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "run_id" => this.run_id().into_bound_py_any(py),
        "effective_target_name" => this.effective_target_name().into_bound_py_any(py),
        "effective_target_database" => this.effective_target_database().into_bound_py_any(py),
        "effective_target_schema" => this.effective_target_schema().into_bound_py_any(py),
        "sql_analysis_dialect" => this.sql_analysis_dialect().into_bound_py_any(py),
        "enforce_explicit_references" => {
            this.is_explicit_reference_enforced().into_bound_py_any(py)
        }
        "models" => this.models(py).into_bound_py_any(py),
        "native_project" => this.native_project(py).into_bound_py_any(py),
        "effective_connection" => this.effective_connection(py).into_bound_py_any(py),
        "effective_vars" => this.effective_vars(py).into_bound_py_any(py),
        "binding_catalog" => this.binding_catalog(py).into_bound_py_any(py),
        "sql_lexical_syntax" => this.sql_lexical_syntax(py).into_bound_py_any(py),
        "compile_cache_dir" => this.compile_cache_dir(py).into_bound_py_any(py),
        "loader_functions" => this.loader_functions(py).into_bound_py_any(py),
        "hook_functions" => this.hook_functions(py).into_bound_py_any(py),
        "sql_hook_files" => this.sql_hook_files(py).into_bound_py_any(py),
        "materialization_files" => this.materialization_files(py).into_bound_py_any(py),
        "public_enums" => this.public_enums(py).into_bound_py_any(py),
        "public_constants" => this.public_constants(py).into_bound_py_any(py),
        "loaded_macros" => this.loaded_macros(py).into_bound_py_any(py),
        "external_sql_reference_resolver" => this
            .external_sql_reference_resolver(py)
            .into_bound_py_any(py),
        "native_session" => this.native_session(py).into_bound_py_any(py),
        "settings" => this.settings(py).into_bound_py_any(py),
        "scenario" => this.scenario(py).into_bound_py_any(py),
        "sources" => this.sources(py).into_bound_py_any(py),
        "seeds" => this.seeds(py).into_bound_py_any(py),
        "functions" => this.functions(py).into_bound_py_any(py),
        "audits" => this.audits(py).into_bound_py_any(py),
        "sql_tests" => this.sql_tests(py).into_bound_py_any(py),
        "sql_scenarios" => this.sql_scenarios(py).into_bound_py_any(py),
        "diagnostics" => this.diagnostics(py).into_bound_py_any(py),
        "unmatched_literal_sql_relations" => this
            .unmatched_literal_sql_relations(py)
            .into_bound_py_any(py),
        "scope_index" => this.scope_index(py).into_bound_py_any(py),
        "sql_expansions" => this
            .sql_expansions(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "lineage_graph" => this
            .lineage_graph(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_compiled_seed<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeCompiledSeed>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "key" => this.key(py).and_then(|value| value.into_bound_py_any(py)),
        "deps" => this.deps(py).into_bound_py_any(py),
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "seed_file" => this
            .seed_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_entry" => this
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_file" => this
            .schema_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "destination" => this
            .destination(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "external" => this.is_external().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_seed_input<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeSeedInput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "seed_file" => this
            .seed_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_entry" => this
            .schema_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "schema_file" => this
            .schema_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_compiled_source<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeCompiledSource>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "key" => this.key(py).and_then(|value| value.into_bound_py_any(py)),
        "deps" => this.deps(py).into_bound_py_any(py),
        "name" => this.name(py).and_then(|value| value.into_bound_py_any(py)),
        "source_entry" => this
            .source_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "source_file" => this
            .source_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_source_input<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeSourceInput>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "source_entry" => this
            .source_entry(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "source_file" => this
            .source_file(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "declaration_usages" => this
            .declaration_usages(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "assembly_row" => this
            .assembly_row(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_local_filesystem_compute_log_storage<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<LocalFilesystemComputeLogStorage>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "root" => this.root(py).and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_dbt_event_stream_update<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<DbtEventStreamUpdate>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "status_message" => (&this.status_message).into_bound_py_any(py),
        "result" => (&this.result).into_bound_py_any(py),
        "row" => (&this.row).into_bound_py_any(py),
        "finished" => (&this.finished).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_dbt_combined_graph<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<DbtCombinedGraph>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "nodes" => this.nodes(py).and_then(|value| value.into_bound_py_any(py)),
        "upstream_deps" => this
            .upstream_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "downstream_deps" => this
            .downstream_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_dbt_compile_reference_resolver<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<DbtCompileReferenceResolver>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "_dbt_manifest" => this.dbt_manifest(py).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_dbt_runner<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<DbtRunner>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "dbt_executable" => (&this.dbt_executable).into_bound_py_any(py),
        "invoker" => (&this.invoker).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_build_phase_timing_tracker<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<BuildPhaseTimingTracker>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "compile_seconds" => (&this.compile_seconds).into_bound_py_any(py),
        "planning_seconds" => (&this.planning_seconds).into_bound_py_any(py),
        "connection_preparation_seconds" => {
            (&this.connection_preparation_seconds).into_bound_py_any(py)
        }
        "schema_preparation_seconds" => (&this.schema_preparation_seconds).into_bound_py_any(py),
        "execution_seconds" => (&this.execution_seconds).into_bound_py_any(py),
        "cost_collection_seconds" => (&this.cost_collection_seconds).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_model_file<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeModelFile>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "file_path" => this
            .file_path(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "relative_path" => this
            .relative_path(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "contents" => this.contents(py).into_bound_py_any(py),
        "header_values" => this
            .header_values(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "header_column_locations" => this
            .header_column_locations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "output_column_locations" => this
            .output_column_locations(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "query_sql" => this.query_sql(py).into_bound_py_any(py),
        "enum_declarations" => this.enum_declarations(py).into_bound_py_any(py),
        "constant_declarations" => this.constant_declarations(py).into_bound_py_any(py),
        "extract_implicit_alias_columns" => {
            this.extract_implicit_alias_columns().into_bound_py_any(py)
        }
        _ => return None,
    })
}

pub(crate) fn read_native_directory_snapshot<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeDirectorySnapshot>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "project_dir" => this.project_dir(py).into_bound_py_any(py),
        "memo" => this.memo(py).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_event_exporter_dispatcher<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExporterDispatcher>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "thread" => this.thread(py).into_bound_py_any(py),
        "notification_thread" => this.notification_thread(py).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_bound_event_exporter<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<BoundEventExporter>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "name" => this.name().into_bound_py_any(py),
        "function" => this.function(py).into_bound_py_any(py),
        "provider_arguments" => this.provider_arguments(py).into_bound_py_any(py),
        "event_kinds" => this
            .event_kinds(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "min_severity" => this
            .min_severity(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_event_export_summary<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExportSummary>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "aggregate" => this.aggregate().into_bound_py_any(py),
        "per_exporter" => this
            .per_exporter(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "queue_depth" => this.queue_depth().into_bound_py_any(py),
        "queue_capacity" => this.queue_capacity().into_bound_py_any(py),
        "flush_complete" => this.flush_complete().into_bound_py_any(py),
        "accepted" => this.accepted().into_bound_py_any(py),
        "filtered" => this.filtered().into_bound_py_any(py),
        "delivered" => this.delivered().into_bound_py_any(py),
        "failed" => this.failed().into_bound_py_any(py),
        "dropped" => this.dropped().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_event_exporter_accounting<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExporterAccounting>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "exporter_name" => this.exporter_name().into_bound_py_any(py),
        "counts" => this.counts().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_event_exporter_counts<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExporterCounts>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "accepted" => this.accepted().into_bound_py_any(py),
        "filtered" => this.filtered().into_bound_py_any(py),
        "delivered" => this.delivered().into_bound_py_any(py),
        "failed" => this.failed().into_bound_py_any(py),
        "dropped" => this.dropped().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_event_exporter_failure<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExporterFailure>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "exporter_name" => this.exporter_name().into_bound_py_any(py),
        "error_type" => this.error_type().into_bound_py_any(py),
        "event_kind" => this.event_kind().into_bound_py_any(py),
        "event_severity" => this
            .event_severity(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_event_exporter_command_scope<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EventExporterCommandScope>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "dispatcher" => this.dispatcher(py).into_bound_py_any(py),
        "provider_session" => this
            .provider_session(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "project_dir" => this
            .project_dir(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "providers" => this
            .providers(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "event_exporters" => this
            .event_exporters(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "command_output_sinks" => this
            .command_output_sinks(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_postgres_execution_history<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PostgresExecutionHistory>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "project_calls" => this.project_calls().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_sqlite_execution_history<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<SqliteExecutionHistory>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "path" => this.path(py).and_then(|value| value.into_bound_py_any(py)),
        "project_calls" => this.project_calls().into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_compiled_project_graph<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<CompiledProjectGraph>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "project" => this.project_attribute(py).into_bound_py_any(py),
        "native" => this.native_attribute(py).into_bound_py_any(py),
        "lineage_views" => this
            .lineage_views(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "upstream_deps" => this
            .upstream_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "downstream_deps" => this
            .downstream_deps(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "tag_index" => this
            .tag_index(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "path_index" => this
            .path_index(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "all_keys" => this
            .all_keys(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_native_config_error<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeConfigError>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "class_name" => (&this.class_name).into_bound_py_any(py),
        "message" => (&this.message).into_bound_py_any(py),
        "code" => (&this.code).into_bound_py_any(py),
        "help" => (&this.help).into_bound_py_any(py),
        "key" => (&this.key).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_model_plan_context<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<ModelPlanContext>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "model_locations" => (&this.model_locations).into_bound_py_any(py),
        "models_by_name" => (&this.models_by_name).into_bound_py_any(py),
        "seed_locations" => (&this.seed_locations).into_bound_py_any(py),
        "function_locations" => (&this.function_locations).into_bound_py_any(py),
        "source_map" => (&this.source_map).into_bound_py_any(py),
        "source_warehouse_columns" => (&this.source_warehouse_columns).into_bound_py_any(py),
        "star_exclude_keyword" => (&this.star_exclude_keyword).into_bound_py_any(py),
        "functions_by_name" => (&this.functions_by_name).into_bound_py_any(py),
        "runtime_cursor_producer_names" => {
            (&this.runtime_cursor_producer_names).into_bound_py_any(py)
        }
        "future_cursor_config" => (&this.future_cursor_config).into_bound_py_any(py),
        "start_cursor_config" => (&this.start_cursor_config).into_bound_py_any(py),
        "invocation_time" => (&this.invocation_time).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_plan_entry_build_inputs<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlanEntryBuildInputs>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "source_freshness_blocked_model_names" => {
            (&this.source_freshness_blocked_model_names).into_bound_py_any(py)
        }
        "external_blocked_model_names" => {
            (&this.external_blocked_model_names).into_bound_py_any(py)
        }
        "start_cursor_override" => (&this.start_cursor_override).into_bound_py_any(py),
        "end_cursor_override" => (&this.end_cursor_override).into_bound_py_any(py),
        "future_cursor_config" => (&this.future_cursor_config).into_bound_py_any(py),
        "start_cursor_config" => (&this.start_cursor_config).into_bound_py_any(py),
        "invocation_time" => (&this.invocation_time).into_bound_py_any(py),
        "max_microbatches" => (&this.max_microbatches).into_bound_py_any(py),
        "max_microbatches_is_override" => {
            (&this.max_microbatches_is_override).into_bound_py_any(py)
        }
        "microbatch_limit_action" => (&this.microbatch_limit_action).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_planner_relations_context<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlannerRelationsContext>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "model_locations" => (&this.model_locations).into_bound_py_any(py),
        "seed_locations" => (&this.seed_locations).into_bound_py_any(py),
        "function_locations" => (&this.function_locations).into_bound_py_any(py),
        "source_map" => (&this.source_map).into_bound_py_any(py),
        "source_read_map" => (&this.source_read_map).into_bound_py_any(py),
        "python_source_read_map" => (&this.python_source_read_map).into_bound_py_any(py),
        "source_warehouse_columns" => (&this.source_warehouse_columns).into_bound_py_any(py),
        "star_exclude_keyword" => (&this.star_exclude_keyword).into_bound_py_any(py),
        "listed_source_names" => (&this.listed_source_names).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_migration_state_inspection<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<MigrationStateInspection>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "database" => this.database(py).into_bound_py_any(py),
        "events" => this
            .events(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "column_events" => this
            .column_events(py)
            .and_then(|value| value.into_bound_py_any(py)),
        "old_name_histories" => this
            .old_name_histories(py)
            .and_then(|value| value.into_bound_py_any(py)),
        _ => return None,
    })
}

pub(crate) fn read_planner_identity_context<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlannerIdentityContext>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "version_identities" => (&this.version_identities).into_bound_py_any(py),
        "stale_warning_identities" => (&this.stale_warning_identities).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_planner_runtime<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlannerRuntime>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "project" => (&this.project).into_bound_py_any(py),
        "adapter" => (&this.adapter).into_bound_py_any(py),
        "connection" => (&this.connection).into_bound_py_any(py),
        "project_config" => (&this.project_config).into_bound_py_any(py),
        "local_config" => (&this.local_config).into_bound_py_any(py),
        "on_progress" => (&this.on_progress).into_bound_py_any(py),
        "invocation_time" => (&this.invocation_time).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_planner_scope_resolution<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlannerScopeResolution>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "selected_scope" => (&this.selected_scope).into_bound_py_any(py),
        "stale_warning_scope" => (&this.stale_warning_scope).into_bound_py_any(py),
        "inspection_scope" => (&this.inspection_scope).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_planner_warehouse_state<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PlannerWarehouseState>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "snapshot" => (&this.snapshot).into_bound_py_any(py),
        "inspection_relations" => (&this.inspection_relations).into_bound_py_any(py),
        "migration_entries" => (&this.migration_entries).into_bound_py_any(py),
        "migration_warnings" => (&this.migration_warnings).into_bound_py_any(py),
        "column_migration_entries" => (&this.column_migration_entries).into_bound_py_any(py),
        "column_rename_hints" => (&this.column_rename_hints).into_bound_py_any(py),
        "old_name_view_entries" => (&this.old_name_view_entries).into_bound_py_any(py),
        "old_name_views" => (&this.old_name_views).into_bound_py_any(py),
        "migration_fingerprints" => (&this.migration_fingerprints).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_python_cli_style<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<PythonCliStyle>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "use_color" => (&this.use_color).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_model_facts<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeModelFacts>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "deps" => (&this.deps).into_bound_py_any(py),
        "dynamic_contract" => (&this.dynamic_contract).into_bound_py_any(py),
        "syntax_valid" => (&this.syntax_valid).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_project_facts<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeProjectFacts>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "models" => (&this.models).into_bound_py_any(py),
        "resources" => (&this.resources).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_project_resources<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeProjectResources>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "model_deps" => (&this.model_deps).into_bound_py_any(py),
        "model_syntax_valid" => (&this.model_syntax_valid).into_bound_py_any(py),
        "source_namespaces" => (&this.source_namespaces).into_bound_py_any(py),
        "seed_namespaces" => (&this.seed_namespaces).into_bound_py_any(py),
        "function_deps" => (&this.function_deps).into_bound_py_any(py),
        "audit_scope_deps" => (&this.audit_scope_deps).into_bound_py_any(py),
        "failure" => (&this.failure).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_resource_failure<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeResourceFailure>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "slot" => (&this.slot).into_bound_py_any(py),
        "index" => (&this.index).into_bound_py_any(py),
        "error" => (&this.error).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_integration_asset_result<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<IntegrationAssetResult>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "as_dict" => return None,
        _ => this.__getattr__(py, name).map(|value| value.into_bound(py)),
    })
}

pub(crate) fn read_integration_check_result<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<IntegrationCheckResult>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "as_dict" | "decoded" | "parsed" => return None,
        _ => this.__getattr__(py, name).map(|value| value.into_bound(py)),
    })
}

pub(crate) fn read_integration_result_envelope<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<IntegrationResultEnvelope>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "asset" => this.asset(py).into_bound_py_any(py),
        "checks" => this.checks(py).into_bound_py_any(py),
        "from_json" | "from_json_without_optional_enrichment" | "register" | "to_json" => {
            return None;
        }
        _ => this.__getattr__(py, name).map(|value| value.into_bound(py)),
    })
}

pub(crate) fn read_terminal_event_claim<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<TerminalEventClaim>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "terminal" => (&this.terminal).into_bound_py_any(py),
        "event_sequence" => (&this.event_sequence).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_early_sql_lint<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<EarlySqlLint>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "enabled" => (&this.enabled).into_bound_py_any(py),
        _ => return None,
    })
}

pub(crate) fn read_native_scope_index<'py>(
    value: &Bound<'py, PyAny>,
    name: &str,
) -> Option<PyResult<Bound<'py, PyAny>>> {
    let py: Python<'py> = value.py();
    let Ok(cell) = value.cast::<NativeScopeIndex>() else {
        return None;
    };
    let Ok(this) = cell.try_borrow() else {
        return None;
    };
    Some(match name {
        "index" => this.index(py).into_bound_py_any(py),
        "has_scoped_relationship_declarations" => this
            .has_scoped_relationship_declarations()
            .into_bound_py_any(py),
        _ => return None,
    })
}
