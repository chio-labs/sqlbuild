//! The metadata projection's view of a cached full index.

use crate::scope_cache::models::CachedIndex;
use crate::scope_report::main::cached_completeness::cached_completeness;
use crate::scope_report::main::cached_declaration_values::cached_declaration_values;
use crate::scope_report::main::cached_diagnostic_facts::cached_diagnostic_facts;
use crate::scope_report::models::{
    ProjectionGrant, ProjectionIndex, ProjectionStanding, ProjectionUsage, ReportValues,
};

/// The metadata projection's view of a full index.
#[must_use]
pub fn cached_projection_index(index: CachedIndex) -> ProjectionIndex {
    ProjectionIndex {
        roots: index.roots,
        resources: index.resources,
        values: ReportValues {
            declarations: index
                .declarations
                .iter()
                .map(cached_declaration_values)
                .collect(),
            completeness: cached_completeness(index.completeness),
        },
        declarations: index
            .declarations
            .into_iter()
            .map(|item| item.record)
            .collect(),
        usages: index
            .usages
            .into_iter()
            .map(|item| ProjectionUsage {
                consumer: item.consumer,
                declaration: item.declaration,
                kind: item.kind,
                through: item.through,
                enum_member: item.enum_member,
            })
            .collect(),
        grants: index
            .grants
            .into_iter()
            .map(|item| ProjectionGrant {
                resource: item.resource,
                declaration: item.declaration,
                through: item.through,
                kind: item.kind,
            })
            .collect(),
        visibility: index
            .visibility
            .into_iter()
            .map(|item| ProjectionStanding {
                resource: item.resource,
                declaration: item.declaration,
                reason: item.reason,
                through: item.through,
            })
            .collect(),
        inaccessible: index
            .inaccessible
            .into_iter()
            .map(|item| ProjectionStanding {
                resource: item.resource,
                declaration: item.declaration,
                reason: item.reason,
                through: None,
            })
            .collect(),
        diagnostics: index
            .diagnostics
            .into_iter()
            .map(cached_diagnostic_facts)
            .collect(),
    }
}
