//! Planner value records the native planner builds and reads.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::planner_models::record::FieldDefault;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyDict;

/// Declares a frozen record class over `Py<PyAny>` fields.
macro_rules! planner_record {
    (@convert $py:ident, $values:expr) => {{
        let _ = $py;
        $values
    }};
    (@convert $py:ident, $values:expr, $convert:path) => { $convert($py, $values)? };
    (
        $(#[$meta:meta])*
        $name:ident, $kw_only:literal, [
            $(($field:ident = $field_name:literal, $default:expr, $compare:literal, $repr:literal)),* $(,)?
        ]
        $(, convert = $convert:path)?
        $(, methods { $($methods:tt)* })?
    ) => {
        $(#[$meta])*
        #[pyo3::pyclass(module = "sqlbuild._native", frozen)]
        pub(crate) struct $name {
            $(
                #[pyo3(get)]
                $field: pyo3::Py<pyo3::PyAny>,
            )*
        }

        impl $name {
            const SPEC: $crate::bindings::_helpers::planner_models::record::RecordSpec =
                $crate::bindings::_helpers::planner_models::record::RecordSpec {
                    name: stringify!($name),
                    kw_only: $kw_only,
                    fields: &[$(
                        $crate::bindings::_helpers::planner_models::record::FieldSpec {
                            name: $field_name,
                            default: $default,
                            compare: $compare,
                            repr: $repr,
                        },
                    )*],
                };

            /// Add the class to `module` with its dataclass field table.
            pub(crate) fn register_class(
                module: &pyo3::Bound<'_, pyo3::types::PyModule>,
            ) -> pyo3::PyResult<()> {
                use pyo3::types::{PyAnyMethods, PyModuleMethods};
                module.add_class::<Self>()?;
                $crate::bindings::_helpers::planner_models::record::install_dataclass_fields(
                    &module.getattr(stringify!($name))?,
                    &Self::SPEC,
                )
            }

            fn values<'py>(&self, py: pyo3::Python<'py>) -> Vec<pyo3::Bound<'py, pyo3::PyAny>> {
                vec![$(self.$field.bind(py).clone()),*]
            }

            fn from_values(values: Vec<pyo3::Py<pyo3::PyAny>>) -> pyo3::PyResult<Self> {
                let mut values = values.into_iter();
                Ok(Self {
                    $(
                        $field: values.next().ok_or_else(|| {
                            pyo3::exceptions::PyTypeError::new_err(concat!("missing ", $field_name))
                        })?,
                    )*
                })
            }
        }

        #[pyo3::pymethods]
        impl $name {
            #[new]
            #[pyo3(signature = (*args, **kwargs))]
            fn __new__(
                args: &pyo3::Bound<'_, pyo3::types::PyTuple>,
                kwargs: Option<&pyo3::Bound<'_, pyo3::types::PyDict>>,
            ) -> pyo3::PyResult<Self> {
                let py = args.py();
                let values = $crate::bindings::_helpers::planner_models::record::bind_fields(
                    &Self::SPEC,
                    args,
                    kwargs,
                )?;
                Self::from_values(planner_record!(@convert py, values $(, $convert)?))
            }

            #[pyo3(signature = (**changes))]
            fn __replace__(
                &self,
                py: pyo3::Python<'_>,
                changes: Option<&pyo3::Bound<'_, pyo3::types::PyDict>>,
            ) -> pyo3::PyResult<Self> {
                let values = $crate::bindings::_helpers::planner_models::record::replaced_fields(
                    &Self::SPEC,
                    self.values(py),
                    changes,
                )?;
                Self::from_values(planner_record!(@convert py, values $(, $convert)?))
            }

            fn __eq__(
                &self,
                other: &pyo3::Bound<'_, pyo3::PyAny>,
            ) -> pyo3::PyResult<pyo3::Py<pyo3::PyAny>> {
                let py = other.py();
                let right = match other.cast::<Self>() {
                    Ok(right) => Some(right.get().values(py)),
                    Err(_) => None,
                };
                $crate::bindings::_helpers::planner_models::record::record_eq(
                    &Self::SPEC,
                    (&self.values(py), right.as_deref()),
                    py,
                )
            }

            fn __hash__(&self, py: pyo3::Python<'_>) -> pyo3::PyResult<isize> {
                $crate::bindings::_helpers::planner_models::record::record_hash(
                    &Self::SPEC,
                    &self.values(py),
                    py,
                )
            }

            fn __repr__(&self, py: pyo3::Python<'_>) -> pyo3::PyResult<String> {
                $crate::bindings::_helpers::planner_models::record::record_repr(
                    &Self::SPEC,
                    &self.values(py),
                )
            }

            $($($methods)*)?
        }
    };
}

fn forward_only_backfill(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item(
        "action",
        imported(py, "sqlbuild.compiler.planner.types", "BackfillAction")?
            .getattr("FORWARD_ONLY")?,
    )?;
    imported(py, "sqlbuild._native", "BackfillResult")?.call((), Some(&kwargs))
}

fn utc_now(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, "datetime", "datetime")?.call_method1("now", (imported(py, "datetime", "UTC")?,))
}

fn scenario_artifact_kind(py: Python<'_>, mut values: Vec<Py<PyAny>>) -> PyResult<Vec<Py<PyAny>>> {
    if let Some(kind) = values.first_mut() {
        *kind = imported(
            py,
            "sqlbuild.compiler.planner.types",
            "ScenarioArtifactKind",
        )?
        .call1((kind.bind(py),))?
        .unbind();
    }
    Ok(values)
}

fn rename_hint_message(
    identical: &Bound<'_, PyAny>,
    candidates: &Bound<'_, PyAny>,
    added: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let relation: &str = if identical.is_truthy()? {
        "same expression as"
    } else {
        "similar to"
    };
    let candidates: Vec<String> = candidates
        .try_iter()?
        .map(|candidate| Ok(candidate?.str()?.to_string()))
        .collect::<PyResult<_>>()?;
    let origin: &str = match candidates.as_slice() {
        [only] => only,
        _ => "<column>",
    };
    Ok(format!(
        "{relation} {}; if this is a rename, add {} (migrate_from {origin})",
        candidates.join(", "),
        added.str()?
    ))
}

planner_record! {
    /// One native-planned SQL-test artifact and its distinct planning error messages.
    NativeSqlTestArtifact, false, [
        (sql = "sql", FieldDefault::Required, true, true),
        (model_names = "model_names", FieldDefault::Required, true, true),
        (error_messages = "error_messages", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// One statically provable invalid fixture condition.
    RelationFixtureDiagnostic, false, [
        (key = "key", FieldDefault::Required, true, true),
        (message = "message", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Completed fixture SQL plus metadata reused by SQL-test validation.
    RelationFixtureCompletion, false, [
        (fixture_sql_by_key = "fixture_sql_by_key", FieldDefault::Required, true, true),
        (inferred_by_fixture = "inferred_by_fixture", FieldDefault::Required, true, true),
        (expected_types = "expected_types", FieldDefault::Required, true, true),
        (diagnostics = "diagnostics", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Known type and nullability for one relation fixture column.
    FixtureColumnMetadata, false, [
        (name = "name", FieldDefault::Required, true, true),
        (r#type = "type", FieldDefault::Required, true, true),
        (nullable = "nullable", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Known columns and whether they form an authoritative relation shape.
    FixtureRelationMetadata, false, [
        (columns = "columns", FieldDefault::Required, true, true),
        (authoritative_names = "authoritative_names", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Project-wide fixture metadata shared across test and scenario planning.
    RelationFixturePlanningContext, false, [
        (models_by_name = "models_by_name", FieldDefault::Required, true, true),
        (relations = "relations", FieldDefault::Required, true, true),
        (authoritative_columns = "authoritative_columns", FieldDefault::Required, true, true),
        (expected_types = "expected_types", FieldDefault::Required, true, true),
        (fixture_inferences = "fixture_inferences", FieldDefault::Class(("sqlbuild._native", "FixtureColumnInferences")), false, true),
    ]
}

planner_record! {
    /// One selector split into graph expansion flags and core text.
    SelectorExpansion, false, [
        (core = "core", FieldDefault::Required, true, true),
        (upstream = "upstream", FieldDefault::Bool(false), true, true),
        (downstream = "downstream", FieldDefault::Bool(false), true, true),
    ]
}

planner_record! {
    /// Parsed physical name for one planner-owned scenario artifact.
    ParsedScenarioArtifactName, false, [
        (hash_prefix = "hash_prefix", FieldDefault::Required, true, true),
        (kind = "kind", FieldDefault::Required, true, true),
        (logical_name = "logical_name", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// One upstream dependency missing from both scope and warehouse.
    MissingUpstream, false, [
        (key = "key", FieldDefault::Required, true, true),
        (required_by = "required_by", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Latest direct fingerprints grouped by node type.
    WarehouseFingerprints, false, [
        (models = "models", FieldDefault::EmptyDict, true, true),
        (functions = "functions", FieldDefault::EmptyDict, true, true),
        (seeds = "seeds", FieldDefault::EmptyDict, true, true),
        (python_nodes = "python_nodes", FieldDefault::EmptyDict, true, true),
        (unfiltered_schemas = "unfiltered_schemas", FieldDefault::EmptyDict, false, false),
        (unfiltered_database = "unfiltered_database", FieldDefault::NoneValue, false, false),
    ]
}

planner_record! {
    /// Execution selection used for cursor validation and runtime producer resolution.
    CursorSnapshotScope, false, [
        (model_keys = "model_keys", FieldDefault::Required, true, true),
        (runtime_producer_keys = "runtime_producer_keys", FieldDefault::Required, true, true),
        (invocation_time = "invocation_time", FieldDefault::NoneValue, true, true),
        (start_cursor_config = "start_cursor_config", FieldDefault::NoneValue, true, true),
        (cursor_overrides = "cursor_overrides", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// One model rename that downstream references may have been rewritten for.
    ReferenceRename, false, [
        (new_name = "new_name", FieldDefault::Required, true, true),
        (origin_name = "origin_name", FieldDefault::Required, true, true),
        (recorded_at = "recorded_at", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// Frozen point-in-time picture of warehouse state for planning.
    WarehouseSnapshot, false, [
        (existing_relations = "existing_relations", FieldDefault::EmptyDict, true, true),
        (existing_columns = "existing_columns", FieldDefault::EmptyDict, true, true),
        (fingerprints = "fingerprints", FieldDefault::Class(("sqlbuild._native", "WarehouseFingerprints")), true, true),
        (cursor_snapshots = "cursor_snapshots", FieldDefault::EmptyDict, true, true),
        (source_freshness_state_schemas = "source_freshness_state_schemas", FieldDefault::EmptyFrozenSet, true, true),
        (column_dialect = "column_dialect", FieldDefault::NoneValue, true, true),
        (renamed_models = "renamed_models", FieldDefault::EmptyFrozenSet, true, true),
        (reference_renames = "reference_renames", FieldDefault::EmptyTuple, true, true),
        (migration_state_schemas = "migration_state_schemas", FieldDefault::EmptyFrozenSet, true, true),
        (old_name_view_state_schemas = "old_name_view_state_schemas", FieldDefault::EmptyFrozenSet, true, true),
        (listed_state_schemas = "listed_state_schemas", FieldDefault::EmptyFrozenSet, true, true),
    ]
}

planner_record! {
    /// Neutral node identity for shared selection-aware staleness classification.
    SelectionStalenessNodeKey, false, [
        (resource_type = "resource_type", FieldDefault::Required, true, true),
        (name = "name", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Neutral graph inputs for selected-model stale warning classification.
    SelectionStalenessGraph, false, [
        (upstream_deps = "upstream_deps", FieldDefault::Required, true, true),
        (selected_model_names = "selected_model_names", FieldDefault::Required, true, true),
        (run_model_names = "run_model_names", FieldDefault::Required, true, true),
        (run_seed_names = "run_seed_names", FieldDefault::Required, true, true),
        (run_source_names = "run_source_names", FieldDefault::Required, true, true),
        (changed_model_names = "changed_model_names", FieldDefault::Required, true, true),
        (changed_seed_names = "changed_seed_names", FieldDefault::Required, true, true),
        (changed_source_names = "changed_source_names", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Neutral stale warning classification for one selected model.
    SelectionStalenessWarning, false, [
        (model_name = "model_name", FieldDefault::Required, true, true),
        (trigger_names = "trigger_names", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Resolved backfill action from a change detection policy.
    BackfillResult, false, [
        (action = "action", FieldDefault::Required, true, true),
        (duration = "duration", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// Per-model output from change detection and policy resolution.
    ChangeDetectionResult, false, [
        (model_name = "model_name", FieldDefault::Required, true, true),
        (change_kind = "change_kind", FieldDefault::Required, true, true),
        (query_changed = "query_changed", FieldDefault::Bool(false), true, true),
        (config_changed = "config_changed", FieldDefault::Bool(false), true, true),
        (fingerprint_metadata_json = "fingerprint_metadata_json", FieldDefault::NoneValue, true, true),
        (previous_metadata_json = "previous_metadata_json", FieldDefault::NoneValue, true, true),
        (fingerprint_version_hash = "fingerprint_version_hash", FieldDefault::NoneValue, true, true),
        (previous_version_hash = "previous_version_hash", FieldDefault::NoneValue, true, true),
        (schema_findings = "schema_findings", FieldDefault::EmptyTuple, true, true),
        (backfill = "backfill", FieldDefault::Factory(forward_only_backfill), true, true),
        (recorded_build_relation_missing = "recorded_build_relation_missing", FieldDefault::Bool(false), true, true),
        (changed_functions = "changed_functions", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Resource selectors left after unit-test selectors moved into a test selection.
    UnitTestSelectorSplit, false, [
        (select = "select", FieldDefault::Required, true, true),
        (exclude = "exclude", FieldDefault::Required, true, true),
        (sql_test_selection = "sql_test_selection", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Relation lookups and source columns for building one model plan entry.
    ModelPlanContext, false, [
        (model_locations = "model_locations", FieldDefault::Required, true, true),
        (models_by_name = "models_by_name", FieldDefault::Required, true, true),
        (seed_locations = "seed_locations", FieldDefault::Required, true, true),
        (function_locations = "function_locations", FieldDefault::Required, true, true),
        (source_map = "source_map", FieldDefault::Required, true, true),
        (source_warehouse_columns = "source_warehouse_columns", FieldDefault::Required, true, true),
        (star_exclude_keyword = "star_exclude_keyword", FieldDefault::Required, true, true),
        (functions_by_name = "functions_by_name", FieldDefault::EmptyDict, true, true),
        (runtime_cursor_producer_names = "runtime_cursor_producer_names", FieldDefault::EmptyFrozenSet, true, true),
        (future_cursor_config = "future_cursor_config", FieldDefault::NoneValue, true, true),
        (start_cursor_config = "start_cursor_config", FieldDefault::NoneValue, true, true),
        (invocation_time = "invocation_time", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// Resolved per-model cursor start/end overrides for plan entry construction.
    CursorOverridePair, false, [
        (start_cursor_override = "start_cursor_override", FieldDefault::NoneValue, true, true),
        (end_cursor_override = "end_cursor_override", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// Blocked models and cursor overrides for plan entry building.
    PlanEntryBuildInputs, false, [
        (source_freshness_blocked_model_names = "source_freshness_blocked_model_names", FieldDefault::EmptyFrozenSet, true, true),
        (external_blocked_model_names = "external_blocked_model_names", FieldDefault::EmptyFrozenSet, true, true),
        (start_cursor_override = "start_cursor_override", FieldDefault::NoneValue, true, true),
        (end_cursor_override = "end_cursor_override", FieldDefault::NoneValue, true, true),
        (future_cursor_config = "future_cursor_config", FieldDefault::NoneValue, true, true),
        (start_cursor_config = "start_cursor_config", FieldDefault::NoneValue, true, true),
        (invocation_time = "invocation_time", FieldDefault::NoneValue, true, true),
        (max_microbatches = "max_microbatches", FieldDefault::NoneValue, true, true),
        (max_microbatches_is_override = "max_microbatches_is_override", FieldDefault::Bool(false), true, true),
        (microbatch_limit_action = "microbatch_limit_action", FieldDefault::Member(("sqlbuild.spec.contracts.types", "MicrobatchLimitAction"), "ERROR"), true, true),
    ]
}

planner_record! {
    /// Per-function output from change detection.
    FunctionChangeResult, false, [
        (fingerprint_sql = "fingerprint_sql", FieldDefault::Required, true, true),
        (reason = "reason", FieldDefault::Member(("sqlbuild.compiler.planner.types", "PlanReason"), "NO_CHANGE"), true, true),
    ]
}

planner_record! {
    /// Change detection output for selected planner resources.
    PlannerChangeResults, false, [
        (models = "models", FieldDefault::Required, true, true),
        (functions = "functions", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Effective model change and backfill decided from the model's own change.
    ResolvedModelAction, false, [
        (change = "change", FieldDefault::Required, true, true),
        (backfill = "backfill", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Per-model planning decisions keyed by model name.
    PlannerResolvedActions, false, [
        (models = "models", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Current direct model version identity values by model name.
    DirectModelVersionIdentities, false, [
        (function_local_hashes = "function_local_hashes", FieldDefault::Required, true, true),
        (seed_version_hashes = "seed_version_hashes", FieldDefault::Required, true, true),
        (seed_metadata_jsons = "seed_metadata_jsons", FieldDefault::Required, true, true),
        (model_metadata_jsons = "model_metadata_jsons", FieldDefault::Required, true, true),
        (model_local_hashes = "model_local_hashes", FieldDefault::Required, true, true),
        (model_version_hashes = "model_version_hashes", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Model plan-entry phase output.
    PlannerModelEntryResults, false, [
        (entries = "entries", FieldDefault::Required, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// One concrete schema change action to apply to a target table.
    SchemaAction, false, [
        (kind = "kind", FieldDefault::Required, true, true),
        (column_name = "column_name", FieldDefault::Required, true, true),
        (column_type = "column_type", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// One warning or error produced during plan resolution.
    PlanWarning, false, [
        (model_name = "model_name", FieldDefault::Required, true, true),
        (severity = "severity", FieldDefault::Required, true, true),
        (message = "message", FieldDefault::Required, true, true),
        (code = "code", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// A removed column that an added column may have been renamed from.
    ColumnRenameHint, false, [
        (model_name = "model_name", FieldDefault::Required, true, true),
        (added_column = "added_column", FieldDefault::Required, true, true),
        (candidate_columns = "candidate_columns", FieldDefault::Required, true, true),
        (identical = "identical", FieldDefault::Bool(false), true, true),
    ],
    methods {
        /// The one-line hint shown beside the added column.
        #[getter]
        fn message(&self, py: Python<'_>) -> PyResult<String> {
            rename_hint_message(
                self.identical.bind(py),
                self.candidate_columns.bind(py),
                self.added_column.bind(py),
            )
        }
    }
}

planner_record! {
    /// One named top-level output column of a query and its canonical expression.
    QueryProjection, false, [
        (name = "name", FieldDefault::Required, true, true),
        (expression = "expression", FieldDefault::Required, true, true),
        (references = "references", FieldDefault::Required, true, true),
        (passthrough = "passthrough", FieldDefault::Bool(false), true, true),
    ],
    methods {
        /// The case-insensitive output name.
        #[getter]
        fn key<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
            self.name.bind(py).call_method0("lower")
        }
    }
}

planner_record! {
    /// Canonical top-level projections and the rest of one query, ignoring formatting.
    QueryShape, false, [
        (projections = "projections", FieldDefault::Required, true, true),
        (body = "body", FieldDefault::Required, true, true),
        (alias_clauses = "alias_clauses", FieldDefault::Text("{}"), true, true),
        (positional = "positional", FieldDefault::Bool(false), true, true),
        (input_relations = "input_relations", FieldDefault::NoneValue, true, true),
        (local_input_columns = "local_input_columns", FieldDefault::EmptyFrozenSet, true, true),
        (clause_references = "clause_references", FieldDefault::EmptyFrozenSet, true, true),
    ]
}

planner_record! {
    /// Optional supplemental seed fingerprints and precomputed SQL tests for plan assembly.
    PlanOutputExtras, false, [
        (seed_version_hashes = "seed_version_hashes", FieldDefault::NoneValue, true, true),
        (seed_metadata_jsons = "seed_metadata_jsons", FieldDefault::NoneValue, true, true),
        (seed_plan_reasons = "seed_plan_reasons", FieldDefault::NoneValue, true, true),
        (planned_sql_tests = "planned_sql_tests", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// SQL test entries planned for one selection; reusable only for the same selection.
    PlannedSqlTests, false, [
        (selected_keys = "selected_keys", FieldDefault::Required, true, true),
        (sql_test_selection = "sql_test_selection", FieldDefault::Class(("sqlbuild.compiler.planner.models", "SqlTestSelection")), true, true),
        (entries = "entries", FieldDefault::EmptyTuple, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Native chain and assertion steps for one SQL test, with SQL when rendered.
    NativeSqlTestPlan, false, [
        (chain = "chain", FieldDefault::Required, true, true),
        (assertions = "assertions", FieldDefault::Required, true, true),
        (model_names = "model_names", FieldDefault::Required, true, true),
        (warnings = "warnings", FieldDefault::Required, true, true),
        (error_messages = "error_messages", FieldDefault::Required, true, true),
        (sql = "sql", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// One SQL test's plan entry and warnings, or the fixture diagnostics preventing it.
    SqlTestPlanResult, false, [
        (entry = "entry", FieldDefault::Required, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
        (fixture_diagnostics = "fixture_diagnostics", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Inferred graph slice and fixture boundaries for one SQL scenario.
    ScenarioGraphPlan, false, [
        (key = "key", FieldDefault::Required, true, true),
        (name = "name", FieldDefault::Required, true, true),
        (target_model_names = "target_model_names", FieldDefault::EmptyTuple, true, true),
        (assertion_target_model_names = "assertion_target_model_names", FieldDefault::EmptyTuple, true, true),
        (model_names = "model_names", FieldDefault::EmptyTuple, true, true),
        (source_fixture_names = "source_fixture_names", FieldDefault::EmptyTuple, true, true),
        (ref_fixture_names = "ref_fixture_names", FieldDefault::EmptyTuple, true, true),
        (seed_names = "seed_names", FieldDefault::EmptyTuple, true, true),
        (seed_fixture_names = "seed_fixture_names", FieldDefault::EmptyTuple, true, true),
        (dbt_ref_fixture_names = "dbt_ref_fixture_names", FieldDefault::EmptyTuple, true, true),
        (function_deps = "function_deps", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Logical identity for one scenario-owned physical artifact.
    ScenarioArtifactIdentity, false, [
        (kind = "kind", FieldDefault::Required, true, true),
        (logical_name = "logical_name", FieldDefault::Required, true, true),
    ],
    convert = scenario_artifact_kind
}

planner_record! {
    /// Resolved physical relation name for one scenario artifact.
    ScenarioArtifactName, false, [
        (identity = "identity", FieldDefault::Required, true, true),
        (physical_name = "physical_name", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Provider usage metadata scoped to planned work.
    PlanProviderUsage, false, [
        (provider_name = "provider_name", FieldDefault::Required, true, true),
        (consumer_kind = "consumer_kind", FieldDefault::Required, true, true),
        (consumer_name = "consumer_name", FieldDefault::Required, true, true),
        (parameter_name = "parameter_name", FieldDefault::Required, true, true),
        (annotation_class_name = "annotation_class_name", FieldDefault::NoneValue, true, true),
        (annotation_module = "annotation_module", FieldDefault::NoneValue, true, true),
    ]
}

planner_record! {
    /// Resolved execution environment shared by planner phases.
    PlannerRuntime, false, [
        (project = "project", FieldDefault::Required, true, true),
        (adapter = "adapter", FieldDefault::Required, true, true),
        (connection = "connection", FieldDefault::Required, true, true),
        (project_config = "project_config", FieldDefault::NoneValue, true, true),
        (local_config = "local_config", FieldDefault::NoneValue, true, true),
        (on_progress = "on_progress", FieldDefault::NoneValue, true, true),
        (invocation_time = "invocation_time", FieldDefault::Factory(utc_now), true, true),
    ]
}

planner_record! {
    /// Resolved planner scopes for one plan build.
    PlannerScopeResolution, false, [
        (selected_scope = "selected_scope", FieldDefault::Required, true, true),
        (stale_warning_scope = "stale_warning_scope", FieldDefault::Required, true, true),
        (inspection_scope = "inspection_scope", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Warehouse snapshot and inspection relations gathered once per plan.
    PlannerWarehouseState, false, [
        (snapshot = "snapshot", FieldDefault::Required, true, true),
        (inspection_relations = "inspection_relations", FieldDefault::Required, true, true),
        (migration_entries = "migration_entries", FieldDefault::EmptyTuple, true, true),
        (migration_warnings = "migration_warnings", FieldDefault::EmptyTuple, true, true),
        (column_migration_entries = "column_migration_entries", FieldDefault::EmptyTuple, true, true),
        (column_rename_hints = "column_rename_hints", FieldDefault::EmptyTuple, true, true),
        (old_name_view_entries = "old_name_view_entries", FieldDefault::EmptyTuple, true, true),
        (old_name_views = "old_name_views", FieldDefault::EmptyTuple, true, true),
        (migration_fingerprints = "migration_fingerprints", FieldDefault::Class(("sqlbuild._native", "MigrationFingerprintCache")), true, true),
    ]
}

planner_record! {
    /// One destination model whose data should come from an earlier relation.
    ModelMigrationRequest, false, [
        (model = "model", FieldDefault::Required, true, true),
        (discovery = "discovery", FieldDefault::Required, true, true),
        (raw_origin = "raw_origin", FieldDefault::NoneValue, true, true),
        (origin_location = "origin_location", FieldDefault::NoneValue, true, true),
        (origin_model = "origin_model", FieldDefault::NoneValue, true, true),
        (force = "force", FieldDefault::Bool(false), true, true),
        (identity_only = "identity_only", FieldDefault::Bool(false), true, true),
    ]
}

planner_record! {
    /// One project model's explicit migrate_from, resolved to a relation.
    ModelMigrationDeclaration, false, [
        (model_name = "model_name", FieldDefault::Required, true, true),
        (origin_location = "origin_location", FieldDefault::Required, true, true),
        (origin_model = "origin_model", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Manual and automatically discovered migration requests for one plan.
    ModelMigrationDiscovery, false, [
        (requests = "requests", FieldDefault::EmptyTuple, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
        (destination_fingerprints = "destination_fingerprints", FieldDefault::EmptyDict, true, true),
    ]
}

planner_record! {
    /// Compatibility status plus human-readable blocking findings.
    MigrationCompatibilityResult, false, [
        (status = "status", FieldDefault::Required, true, true),
        (findings = "findings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Migration decisions plus the warehouse snapshot as it will look after moves.
    ModelMigrationPlanning, false, [
        (snapshot = "snapshot", FieldDefault::Required, true, true),
        (entries = "entries", FieldDefault::EmptyTuple, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Old-name steps for this build plus every compatibility view still recorded.
    OldNameViewPlanning, false, [
        (entries = "entries", FieldDefault::EmptyTuple, true, true),
        (views = "views", FieldDefault::EmptyTuple, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Column rename decisions plus the warehouse snapshot as it will look after renames.
    ColumnMigrationPlanning, false, [
        (snapshot = "snapshot", FieldDefault::Required, true, true),
        (entries = "entries", FieldDefault::EmptyTuple, true, true),
        (hints = "hints", FieldDefault::EmptyTuple, true, true),
        (warnings = "warnings", FieldDefault::EmptyTuple, true, true),
    ]
}

planner_record! {
    /// Expected version identities for inspection and stale-warning scopes.
    PlannerIdentityContext, false, [
        (version_identities = "version_identities", FieldDefault::Required, true, true),
        (stale_warning_identities = "stale_warning_identities", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Scope pruning outcome with pruned scopes, actions, and staleness state.
    PlannerScopePruningResult, false, [
        (inspection_scope = "inspection_scope", FieldDefault::Required, true, true),
        (execution_scope = "execution_scope", FieldDefault::Required, true, true),
        (resolved_actions = "resolved_actions", FieldDefault::Required, true, true),
        (pruned_direct_model_names = "pruned_direct_model_names", FieldDefault::Required, true, true),
        (direct_identity_stale_model_names = "direct_identity_stale_model_names", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Write-hash-honest changes merged back into resolved actions.
    PlannerChangeReconciliation, false, [
        (changes = "changes", FieldDefault::Required, true, true),
        (resolved_actions = "resolved_actions", FieldDefault::Required, true, true),
    ]
}

planner_record! {
    /// Model plan entries for one plan build.
    PlannerEntryResults, false, [
        (model_entry_results = "model_entry_results", FieldDefault::Required, true, true),
    ]
}
