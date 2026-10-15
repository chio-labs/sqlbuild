//! Registers the planner value records.

use crate::bindings::_helpers::planner_models::enums::register_enums;
use crate::bindings::_helpers::planner_models::fixture_inferences::FixtureColumnInferences;
use crate::bindings::_helpers::planner_models::records::{
    BackfillResult, ChangeDetectionResult, ColumnMigrationPlanning, ColumnRenameHint,
    CursorOverridePair, CursorSnapshotScope, DirectModelVersionIdentities, FixtureColumnMetadata,
    FixtureRelationMetadata, FunctionChangeResult, MigrationCompatibilityResult, MissingUpstream,
    ModelMigrationDeclaration, ModelMigrationDiscovery, ModelMigrationPlanning,
    ModelMigrationRequest, ModelPlanContext, NativeSqlTestArtifact, NativeSqlTestPlan,
    OldNameViewPlanning, ParsedScenarioArtifactName, PlanEntryBuildInputs, PlanOutputExtras,
    PlanProviderUsage, PlanWarning, PlannedSqlTests, PlannerChangeReconciliation,
    PlannerChangeResults, PlannerEntryResults, PlannerIdentityContext, PlannerModelEntryResults,
    PlannerResolvedActions, PlannerRuntime, PlannerScopePruningResult, PlannerScopeResolution,
    PlannerWarehouseState, QueryProjection, QueryShape, ReferenceRename, RelationFixtureCompletion,
    RelationFixtureDiagnostic, RelationFixturePlanningContext, ResolvedModelAction,
    ScenarioArtifactIdentity, ScenarioArtifactName, ScenarioGraphPlan, SchemaAction,
    SelectionStalenessGraph, SelectionStalenessNodeKey, SelectionStalenessWarning,
    SelectorExpansion, SqlTestPlanResult, UnitTestSelectorSplit, WarehouseFingerprints,
    WarehouseSnapshot,
};
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    register_enums(module)?;
    module.add_class::<FixtureColumnInferences>()?;
    NativeSqlTestArtifact::register_class(module)?;
    RelationFixtureDiagnostic::register_class(module)?;
    RelationFixtureCompletion::register_class(module)?;
    FixtureColumnMetadata::register_class(module)?;
    FixtureRelationMetadata::register_class(module)?;
    RelationFixturePlanningContext::register_class(module)?;
    SelectorExpansion::register_class(module)?;
    ParsedScenarioArtifactName::register_class(module)?;
    MissingUpstream::register_class(module)?;
    WarehouseFingerprints::register_class(module)?;
    CursorSnapshotScope::register_class(module)?;
    ReferenceRename::register_class(module)?;
    WarehouseSnapshot::register_class(module)?;
    SelectionStalenessNodeKey::register_class(module)?;
    SelectionStalenessGraph::register_class(module)?;
    SelectionStalenessWarning::register_class(module)?;
    BackfillResult::register_class(module)?;
    ChangeDetectionResult::register_class(module)?;
    UnitTestSelectorSplit::register_class(module)?;
    ModelPlanContext::register_class(module)?;
    CursorOverridePair::register_class(module)?;
    PlanEntryBuildInputs::register_class(module)?;
    FunctionChangeResult::register_class(module)?;
    PlannerChangeResults::register_class(module)?;
    ResolvedModelAction::register_class(module)?;
    PlannerResolvedActions::register_class(module)?;
    DirectModelVersionIdentities::register_class(module)?;
    PlannerModelEntryResults::register_class(module)?;
    SchemaAction::register_class(module)?;
    PlanWarning::register_class(module)?;
    ColumnRenameHint::register_class(module)?;
    QueryProjection::register_class(module)?;
    QueryShape::register_class(module)?;
    PlanOutputExtras::register_class(module)?;
    PlannedSqlTests::register_class(module)?;
    NativeSqlTestPlan::register_class(module)?;
    SqlTestPlanResult::register_class(module)?;
    ScenarioGraphPlan::register_class(module)?;
    ScenarioArtifactIdentity::register_class(module)?;
    ScenarioArtifactName::register_class(module)?;
    PlanProviderUsage::register_class(module)?;
    PlannerRuntime::register_class(module)?;
    PlannerScopeResolution::register_class(module)?;
    PlannerWarehouseState::register_class(module)?;
    ModelMigrationRequest::register_class(module)?;
    ModelMigrationDeclaration::register_class(module)?;
    ModelMigrationDiscovery::register_class(module)?;
    MigrationCompatibilityResult::register_class(module)?;
    ModelMigrationPlanning::register_class(module)?;
    OldNameViewPlanning::register_class(module)?;
    ColumnMigrationPlanning::register_class(module)?;
    PlannerIdentityContext::register_class(module)?;
    PlannerScopePruningResult::register_class(module)?;
    PlannerChangeReconciliation::register_class(module)?;
    PlannerEntryResults::register_class(module)?;
    Ok(())
}
