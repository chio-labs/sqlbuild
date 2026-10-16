//! What one migration decision does.

/// The behaviour of one model migration decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DecisionTraits {
    /// The decision clones the origin over the destination.
    pub moves_data: bool,
    /// The decision stops a build regardless of compatibility.
    pub blocks_build: bool,
    /// The decision evaluated the origin against the destination.
    pub checks_compatibility: bool,
}

/// The behaviour of one column migration decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ColumnDecisionTraits {
    pub renames: bool,
    pub records_event: bool,
    pub blocks_build: bool,
    /// The plan label, or `None` for an unknown decision.
    pub label: Option<&'static str>,
}

/// The facts of one planned model migration that decide whether it blocks a build.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ModelMigrationFacts {
    pub origin_missing: bool,
    /// The missing origin has build history in this target.
    pub origin_tracked: bool,
    /// `missing_migration_origin` is `deny`.
    pub deny_missing_origin: bool,
    pub decision: DecisionTraits,
    /// The origin is incompatible with the destination.
    pub incompatible: bool,
}
