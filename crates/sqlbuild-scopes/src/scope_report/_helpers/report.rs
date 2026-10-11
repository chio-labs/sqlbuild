//! The phases of `query_scope_report`: resolve the target, select its sections, page them.

use std::collections::{HashMap, HashSet};

use crate::scope_index::main::classify_report_resource::classify_report_resource;
use crate::scope_index::models::{
    DeclarationIdentity, QualifiedIdentity, ReportClassification, ResourceRecord, ScopeKind,
};
use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::declarations::declaration_report;
use crate::scope_report::_helpers::selection::{PageSpec, count, page, resolve_cursor};
use crate::scope_report::_helpers::selection::{
    Selected, expand_dependencies, filtered, nearby, report_key, scope_chain,
};
use crate::scope_report::_helpers::targets::explain_declaration;
use crate::scope_report::_helpers::targets::{
    ExistingTarget, diagnostic, existing_target, prospective_resource,
};
use crate::scope_report::constants::{
    AVAILABLE_SECTION, GLOBAL_SUMMARY_POLICY, GLOBAL_USED_POLICY, INCOMPLETE_USAGE, NEARBY_SECTION,
    PROSPECTIVE_USAGE_MESSAGE, RELATIONSHIP_SECTION, USED_SECTION,
};
use crate::scope_report::models::{
    DeclarationReport, DeclarationTarget, DiagnosticFacts, Explanation, Provenance, QueryTarget,
    ReportDiagnostic, ReportFailure, ReportFilters, ReportRequest, ResourceReport, ScopeReport,
    ScopeSection,
};

/// The record a report resolved, or the report it ends with when there is none.
pub(crate) enum Resolved {
    Record(ResourceReport, ResourceRecord, Vec<DiagnosticFacts>),
    Done(
        ResourceReport,
        Option<Box<Explanation>>,
        Vec<DiagnosticFacts>,
    ),
}

/// What a resource uses: everything, directly, and through relationships.
struct Used<'a> {
    all: HashSet<&'a DeclarationIdentity>,
    direct: HashSet<&'a DeclarationIdentity>,
    related: HashSet<&'a DeclarationIdentity>,
}

/// The filtered sections of one report, before paging.
struct Sections {
    direct: Selected<Provenance>,
    used: Selected<Provenance>,
    relationships: Selected<Provenance>,
    nearby: Selected<String>,
    collapsed: i64,
}

/// `_existing_target` or `_prospective_resource` of the request.
pub(crate) fn resolve(
    context: &Context<'_>,
    request: &ReportRequest,
) -> Result<Resolved, ReportFailure> {
    if let Some(at) = &request.at {
        let (resource, record, diagnostics) = prospective_resource(context, at, request.directory)?;
        return Ok(match record {
            Some(record) => Resolved::Record(resource, record, diagnostics),
            None => Resolved::Done(resource, None, diagnostics),
        });
    }
    Ok(match existing_target(context, request.target.as_ref())? {
        ExistingTarget::Resource(resource, position, diagnostics) => {
            Resolved::Record(resource, context.resource(position).clone(), diagnostics)
        }
        ExistingTarget::Missing(resource, diagnostic) => {
            Resolved::Done(resource, None, vec![diagnostic])
        }
        ExistingTarget::Declaration(resource) => {
            let target: DeclarationTarget = match &request.target {
                Some(QueryTarget::Identity(QualifiedIdentity::Declaration(identity))) => {
                    DeclarationTarget::Identity(identity.clone())
                }
                _ => DeclarationTarget::Text(resource.target.clone()),
            };
            let (explanation, diagnostics) = explain_declaration(context, &target, None)?;
            Resolved::Done(resource, Some(Box::new(explanation)), diagnostics)
        }
    })
}

/// The index diagnostics, then the ones this query raised.
pub(crate) fn report_diagnostics(
    context: &Context<'_>,
    raised: Vec<DiagnosticFacts>,
) -> Vec<ReportDiagnostic> {
    (0..context.source.lookup.diagnostics.len())
        .map(ReportDiagnostic::Index)
        .chain(raised.into_iter().map(ReportDiagnostic::Raised))
        .collect()
}

/// The report of a target with no record: its resource, explanation and diagnostics only.
pub(crate) fn unresolved_report(
    context: &Context<'_>,
    filters: &ReportFilters,
    resolved: (
        ResourceReport,
        Option<Box<Explanation>>,
        Vec<DiagnosticFacts>,
    ),
) -> ScopeReport {
    let (resource, explanation, raised) = resolved;
    let complete: bool = explanation.as_ref().is_some_and(|item| item.complete);
    ScopeReport {
        resource,
        scope_chain: Vec::new(),
        available: Vec::new(),
        used: Vec::new(),
        relationship_scope: Vec::new(),
        nearby_unavailable: Vec::new(),
        filters: filters.clone(),
        sections: Vec::new(),
        explanation: explanation.map(|explanation| *explanation),
        move_preview: None,
        diagnostics: report_diagnostics(context, raised),
        complete,
    }
}

fn used_by<'a>(context: &Context<'a>, record: &ResourceRecord) -> Used<'a> {
    let consumer: QualifiedIdentity = QualifiedIdentity::Resource(record.identity.clone());
    let mut used: Used<'a> = Used {
        all: HashSet::new(),
        direct: HashSet::new(),
        related: HashSet::new(),
    };
    for usage in context.usages_of_consumer(&consumer) {
        let usage = context.usage(*usage);
        used.all.insert(&usage.declaration);
        if usage.through.is_none() {
            used.direct.insert(&usage.declaration);
        } else {
            used.related.insert(&usage.declaration);
        }
    }
    used
}

/// Visible declarations the resource uses, keyed by identity, later ones replacing earlier ones.
fn used_records(
    context: &Context<'_>,
    direct: &Selected<Provenance>,
    relationships: &Selected<Provenance>,
    used: &Used<'_>,
) -> Selected<Provenance> {
    let mut order: Vec<&DeclarationIdentity> = Vec::new();
    let mut keyed: HashMap<&DeclarationIdentity, (usize, Provenance)> = HashMap::new();
    let sources = [(direct, &used.direct), (relationships, &used.related)];
    for (values, wanted) in sources {
        for (position, provenance) in values {
            let identity: &DeclarationIdentity = &context.declaration(*position).identity;
            if wanted.contains(identity)
                && keyed
                    .insert(identity, (*position, provenance.clone()))
                    .is_none()
            {
                order.push(identity);
            }
        }
    }
    let mut records: Selected<Provenance> = order
        .into_iter()
        .filter_map(|identity| keyed.remove(identity))
        .collect();
    records.sort_by_cached_key(|(position, _)| report_key(context, *position));
    records
}

fn provenance(reason: &str, through: Option<String>) -> Provenance {
    Provenance {
        reason: reason.to_owned(),
        through,
    }
}

/// The classification as `(position, provenance)` and `(position, reason)` lists.
fn classified(
    classification: ReportClassification,
) -> (Selected<Provenance>, Selected<Provenance>, Selected<String>) {
    let direct: Selected<Provenance> = classification
        .direct
        .into_iter()
        .map(|(position, reason)| (position, provenance(reason.as_str(), None)))
        .collect();
    let relationships: Selected<Provenance> = classification
        .relationships
        .into_iter()
        .map(|entry| {
            (
                entry.position,
                provenance(entry.reason.as_str(), Some(entry.through)),
            )
        })
        .collect();
    let unavailable: Selected<String> = classification
        .unavailable
        .into_iter()
        .map(|(position, reason)| (position, reason.as_str().to_owned()))
        .collect();
    (direct, relationships, unavailable)
}

/// The non-global and used declarations, and how many globals were dropped.
fn without_unused_globals(
    context: &Context<'_>,
    values: Selected<Provenance>,
    used: &HashSet<&DeclarationIdentity>,
) -> (Selected<Provenance>, i64) {
    let before: usize = values.len();
    let kept: Selected<Provenance> = values
        .into_iter()
        .filter(|(position, _)| {
            let record = context.declaration(*position);
            record.scope != ScopeKind::Global || used.contains(&record.identity)
        })
        .collect();
    let dropped: i64 = count(before - kept.len());
    (kept, dropped)
}

/// Every section of `record`, filtered, trimmed to the requested sections and global policy.
fn sections(
    context: &Context<'_>,
    record: &ResourceRecord,
    filters: &ReportFilters,
) -> Result<Sections, ReportFailure> {
    let classification: ReportClassification =
        classify_report_resource(context.source.records, context.source.lookup, record)
            .map_err(ReportFailure::Path)?;
    let (direct, relationships, unavailable) = classified(classification);
    let used: Used<'_> = used_by(context, record);
    let used_values: Selected<Provenance> = used_records(context, &direct, &relationships, &used);
    let nearby_values: Selected<String> =
        nearby(context, record, unavailable, filters.nearby_depth).map_err(ReportFailure::Path)?;
    let includes = |section: &str| filters.sections.iter().any(|name| name == section);
    let mut direct: Selected<Provenance> = filtered(context, direct, filters, &used.all);
    let mut used_values: Selected<Provenance> = filtered(context, used_values, filters, &used.all);
    let mut relationships: Selected<Provenance> =
        filtered(context, relationships, filters, &used.all);
    let nearby_values: Selected<String> = filtered(context, nearby_values, filters, &used.all);
    if !includes(AVAILABLE_SECTION) {
        direct.clear();
    }
    if !includes(USED_SECTION) {
        used_values.clear();
    }
    if !includes(RELATIONSHIP_SECTION) {
        relationships.clear();
    }
    if filters.dependency_depth > 0 {
        used_values = expand_dependencies(context, used_values, filters.dependency_depth);
    }
    let mut collapsed: i64 = 0;
    if filters.globals == GLOBAL_SUMMARY_POLICY || filters.globals == GLOBAL_USED_POLICY {
        let (kept, dropped) = without_unused_globals(context, direct, &used.all);
        direct = kept;
        if filters.globals == GLOBAL_SUMMARY_POLICY {
            collapsed = dropped;
        }
    }
    Ok(Sections {
        direct,
        used: used_values,
        relationships,
        nearby: nearby_values,
        collapsed,
    })
}

/// `len(nearby[:page_size])` with Python's slice semantics for a negative size.
fn nearby_shown(length: usize, page_size: i64) -> usize {
    match usize::try_from(page_size) {
        Ok(size) => size.min(length),
        Err(_) => {
            let dropped: usize = usize::try_from(page_size.unsigned_abs()).unwrap_or(usize::MAX);
            length.saturating_sub(dropped)
        }
    }
}

/// The nearby page and its section.
fn nearby_page(
    context: &Context<'_>,
    nearby: &Selected<String>,
    filters: &ReportFilters,
) -> Result<(Vec<DeclarationReport>, ScopeSection), ReportFailure> {
    let shown: usize = nearby_shown(nearby.len(), filters.page_size);
    if shown == 0 && !nearby.is_empty() {
        return Err(ReportFailure::IndexOutOfRange);
    }
    let reports: Vec<DeclarationReport> = nearby[..shown]
        .iter()
        .map(|(position, reason)| {
            declaration_report(context, *position, None, Some(reason.clone()))
        })
        .collect();
    let truncated: bool = reports.len() < nearby.len();
    let section: ScopeSection = ScopeSection {
        name: NEARBY_SECTION.to_owned(),
        total: count(nearby.len()),
        returned: count(reports.len()),
        collapsed: false,
        collapsed_count: 0,
        truncated,
        complete: context.completeness().static_visibility,
        next_cursor: reports
            .last()
            .filter(|_| truncated)
            .map(|report| report.identity.clone()),
        cursor: None,
        page_size: filters.page_size,
    };
    Ok((reports, section))
}

/// The report of a resolved record: its pages, sections, scope chain and completeness.
pub(crate) fn record_report(
    context: &Context<'_>,
    filters: &ReportFilters,
    resolved: (ResourceReport, ResourceRecord, Vec<DiagnosticFacts>),
) -> Result<ScopeReport, ReportFailure> {
    let (resource, record, mut raised) = resolved;
    let selected: Sections = sections(context, &record, filters)?;
    let (cursor, cursor_diagnostic) = resolve_cursor(
        context,
        filters.cursor.as_deref(),
        &[&selected.direct, &selected.used, &selected.relationships],
    );
    raised.extend(cursor_diagnostic);
    let completeness = context.completeness();
    let spec = |name: &'static str, complete: bool, collapsed: i64| PageSpec {
        name,
        cursor: cursor.as_deref(),
        page_size: filters.page_size,
        complete,
        collapsed,
    };
    let (available, available_section) = page(
        context,
        &selected.direct,
        &spec(
            AVAILABLE_SECTION,
            completeness.static_visibility,
            selected.collapsed,
        ),
    );
    let (used, used_section) = page(
        context,
        &selected.used,
        &spec(USED_SECTION, completeness.runtime_usage, 0),
    );
    let (relationship_scope, relationship_section) = page(
        context,
        &selected.relationships,
        &spec(RELATIONSHIP_SECTION, completeness.relationships, 0),
    );
    let (nearby_reports, nearby_section) = nearby_page(context, &selected.nearby, filters)?;
    let sections: Vec<ScopeSection> = vec![
        available_section,
        used_section,
        relationship_section,
        nearby_section,
    ];
    let complete: bool = sections.iter().all(|section| section.complete) && !resource.prospective;
    if resource.prospective {
        raised.push(diagnostic(
            INCOMPLETE_USAGE,
            PROSPECTIVE_USAGE_MESSAGE.to_owned(),
            resource.path.clone(),
        ));
    }
    Ok(ScopeReport {
        scope_chain: scope_chain(context, &record),
        resource,
        available,
        used,
        relationship_scope,
        nearby_unavailable: if filters.include_nearby {
            nearby_reports
        } else {
            Vec::new()
        },
        filters: filters.clone(),
        sections,
        explanation: None,
        move_preview: None,
        diagnostics: report_diagnostics(context, raised),
        complete,
    })
}
