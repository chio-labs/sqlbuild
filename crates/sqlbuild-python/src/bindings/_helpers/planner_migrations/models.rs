use pyo3::prelude::{Bound, PyAny};
use pyo3::types::PyDict;

#[derive(Debug)]
pub(crate) struct OldNamePlanner<'py> {
    pub runtime: Bound<'py, PyAny>,
    pub models: Vec<Bound<'py, PyAny>>,
    pub histories: Vec<Bound<'py, PyAny>>,
    pub views: Bound<'py, PyAny>,
    pub columns: Bound<'py, PyAny>,
    pub retention: Bound<'py, PyAny>,
    pub now: Bound<'py, PyAny>,
}

#[derive(Debug)]
pub(crate) struct ColumnCandidate<'py> {
    pub model: Bound<'py, PyAny>,
    pub warehouse: Bound<'py, PyDict>,
    pub declared: Bound<'py, PyDict>,
    pub fingerprint: Bound<'py, PyAny>,
    pub previous: Bound<'py, PyAny>,
    pub current: Bound<'py, PyAny>,
}
#[derive(Debug)]
pub(crate) struct CheckedColumns<'py> {
    pub entries: Vec<Bound<'py, PyAny>>,
    pub warnings: Vec<Bound<'py, PyAny>>,
}

/// The planning-phase inputs every migration planner reads.
#[derive(Debug)]
pub(crate) struct MigrationPhase<'py> {
    pub(crate) runtime: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) overrides: Bound<'py, PyAny>,
    pub(crate) deferral: Bound<'py, PyAny>,
}

/// The column migration planning inputs beyond the phase.
#[derive(Debug)]
pub(crate) struct ColumnMigrationInputs<'py> {
    pub(crate) full_refresh_model_names: Bound<'py, PyAny>,
    pub(crate) physical_relations: Bound<'py, PyAny>,
    pub(crate) source_columns: Bound<'py, PyAny>,
}

/// The snapshot after model migrations overlay it, with the planned entries and their warnings.
#[derive(Debug)]
pub(crate) struct ModelMigrationPlanning<'py> {
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) entries: Vec<Bound<'py, PyAny>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}

/// The snapshot after column renames overlay it, with the planned entries, rename hints and warnings.
#[derive(Debug)]
pub(crate) struct ColumnMigrationPlanning<'py> {
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) entries: Vec<Bound<'py, PyAny>>,
    pub(crate) hints: Vec<Bound<'py, PyAny>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}

/// The old-name view steps, the recorded live views and the warnings they raise.
#[derive(Debug)]
pub(crate) struct OldNameViewPlanning<'py> {
    pub(crate) entries: Bound<'py, PyAny>,
    pub(crate) views: Bound<'py, PyAny>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}

/// One destination model whose data should come from an earlier relation.
#[derive(Debug, Clone)]
pub(crate) struct ModelMigrationRequest<'py> {
    pub(crate) model: Bound<'py, PyAny>,
    pub(crate) discovery: Bound<'py, PyAny>,
    pub(crate) raw_origin: Option<Bound<'py, PyAny>>,
    pub(crate) origin_location: Option<Bound<'py, PyAny>>,
    pub(crate) origin_model: Bound<'py, PyAny>,
    pub(crate) force: bool,
    pub(crate) identity_only: bool,
}

/// One project model's explicit migrate_from, resolved to a relation.
#[derive(Debug)]
pub(crate) struct ModelMigrationDeclaration<'py> {
    pub(crate) model_name: Bound<'py, PyAny>,
    pub(crate) origin_location: Bound<'py, PyAny>,
    pub(crate) origin_model: Bound<'py, PyAny>,
}

/// Manual and automatically discovered migration requests for one plan.
#[derive(Debug)]
pub(crate) struct ModelMigrationDiscovery<'py> {
    pub(crate) requests: Vec<ModelMigrationRequest<'py>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
    pub(crate) destination_fingerprints: Bound<'py, PyDict>,
}

/// Compatibility status plus human-readable blocking findings.
#[derive(Debug)]
pub(crate) struct MigrationCompatibilityResult<'py> {
    pub(crate) status: Bound<'py, PyAny>,
    pub(crate) findings: Bound<'py, PyAny>,
}

/// The fingerprint inputs shared by migration matching and destination fingerprints.
#[derive(Debug)]
pub(crate) struct FingerprintInputs<'py> {
    pub(crate) metadata_jsons: Bound<'py, PyAny>,
    pub(crate) dialect: Bound<'py, PyAny>,
    pub(crate) fingerprints: Bound<'py, PyAny>,
}

/// One resolved migration request decided against live state.
#[derive(Debug)]
pub(crate) struct MigrationDecisionRequest<'a, 'py> {
    pub(crate) runtime: Bound<'py, PyAny>,
    pub(crate) request: &'a ModelMigrationRequest<'py>,
    pub(crate) origin: Bound<'py, PyAny>,
    pub(crate) origin_model: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) state: Bound<'py, PyAny>,
    pub(crate) snapshots_config: Bound<'py, PyAny>,
}

/// What checking an origin relation's compatibility with its destination model reads.
#[derive(Debug)]
pub(crate) struct CompatibilityCheck<'py> {
    pub(crate) model: Bound<'py, PyAny>,
    pub(crate) origin_relation: Bound<'py, PyAny>,
    pub(crate) origin_columns: Bound<'py, PyAny>,
    pub(crate) sql_analysis_enabled: Bound<'py, PyAny>,
    pub(crate) column_dialect: Bound<'py, PyAny>,
    pub(crate) snapshots_config: Bound<'py, PyAny>,
}

/// What discovering automatic and manual migration requests reads.
#[derive(Debug)]
pub(crate) struct DiscoveryRequest<'py> {
    pub(crate) runtime: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) manual_requests: Vec<ModelMigrationRequest<'py>>,
    pub(crate) declarations: Vec<ModelMigrationDeclaration<'py>>,
    pub(crate) state: Bound<'py, PyAny>,
    pub(crate) project_schemas: Bound<'py, PyAny>,
    pub(crate) fingerprints: Bound<'py, PyAny>,
}
