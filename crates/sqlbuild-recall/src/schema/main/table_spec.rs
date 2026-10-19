//! `table_spec`: the definition of one Recall table.

use crate::schema::constants::{
    ARTIFACT_REFS_TABLE, ARTIFACTS_TABLE, CONFLICTS_TABLE, DELIVERY_TABLE, DIAGNOSTICS_TABLE,
    EVENTS_TABLE, HEARTBEATS_TABLE, INVOCATIONS_TABLE, META_TABLE, OUTPUT_TABLE,
};
use crate::schema::models::{Table, TableSpec};

/// The physical definition of `table`.
#[must_use]
pub fn table_spec(table: Table) -> &'static TableSpec {
    match table {
        Table::Invocations => &INVOCATIONS_TABLE,
        Table::Output => &OUTPUT_TABLE,
        Table::Events => &EVENTS_TABLE,
        Table::Diagnostics => &DIAGNOSTICS_TABLE,
        Table::Artifacts => &ARTIFACTS_TABLE,
        Table::ArtifactRefs => &ARTIFACT_REFS_TABLE,
        Table::Heartbeats => &HEARTBEATS_TABLE,
        Table::Delivery => &DELIVERY_TABLE,
        Table::Meta => &META_TABLE,
        Table::Conflicts => &CONFLICTS_TABLE,
    }
}
