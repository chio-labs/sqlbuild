//! The visibility deltas `preview_scope_move` reports for one resource move.

use std::collections::{BTreeMap, HashMap, HashSet};

use crate::scope_index::main::classify_report_resource::classify_report_resource;
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, OwnershipRoot, QualifiedIdentity, ReportClassification,
    ResourceRecord, ScopeKind,
};
use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::declarations::declaration_report;
use crate::scope_report::_helpers::paths::{ancestry, normalized, resource_path_is_valid};
use crate::scope_report::_helpers::targets::{
    diagnostic, ownership_roots, query, resource_matches, target_text,
};
use crate::scope_report::constants::{INVALID_PROSPECTIVE_PATH, UNKNOWN_TARGET};
use crate::scope_report::models::{
    DeclarationReport, DiagnosticFacts, MovePreview, MoveRequest, Provenance, ReportFailure,
    ReportSource,
};

/// Declarations at input positions with how each is visible.
type Visible = Vec<(usize, Provenance)>;

/// Visible declarations by qualified identity text, later records replacing earlier ones.
type ByIdentity<'a> = BTreeMap<String, (&'a DeclarationIdentity, usize, Provenance)>;

fn invalid_destination(destination: &str) -> DiagnosticFacts {
    diagnostic(
        INVALID_PROSPECTIVE_PATH,
        format!(
            "Move destination {destination} is invalid, outside its authored resource root, \
             or already occupied"
        ),
        None,
    )
}

fn qualified(identity: &DeclarationIdentity) -> String {
    format_identity(&QualifiedIdentity::Declaration(identity.clone()))
}

/// Direct or relationship visibility keyed by identity.
fn keyed<'a>(context: &Context<'a>, values: Visible) -> ByIdentity<'a> {
    let mut keyed: ByIdentity<'a> = BTreeMap::new();
    for (position, provenance) in values {
        let identity: &'a DeclarationIdentity = &context.declaration(position).identity;
        keyed.insert(qualified(identity), (identity, position, provenance));
    }
    keyed
}

/// The classification's direct and relationship visibility.
fn visible(classification: ReportClassification) -> (Visible, Visible) {
    let direct: Visible = classification
        .direct
        .into_iter()
        .map(|(position, reason)| {
            let provenance = Provenance {
                reason: reason.as_str().to_owned(),
                through: None,
            };
            (position, provenance)
        })
        .collect();
    let relationships: Visible = classification
        .relationships
        .into_iter()
        .map(|entry| {
            let provenance = Provenance {
                reason: entry.reason.as_str().to_owned(),
                through: Some(entry.through),
            };
            (entry.position, provenance)
        })
        .collect();
    (direct, relationships)
}

/// Reports of `values` whose identity text satisfies `keep`, in identity order.
fn reports(
    context: &Context<'_>,
    values: &ByIdentity<'_>,
    keep: impl Fn(&str) -> bool,
) -> Vec<DeclarationReport> {
    values
        .iter()
        .filter(|(text, _)| keep(text))
        .map(|(_, (_, position, provenance))| {
            declaration_report(context, *position, Some(provenance.clone()), None)
        })
        .collect()
}

/// The roots that could own `source` at `path`.
fn destination_roots(
    context: &Context<'_>,
    source: &ResourceRecord,
    path: &str,
) -> Result<Vec<OwnershipRoot>, ReportFailure> {
    let mut roots: Vec<OwnershipRoot> = Vec::new();
    for root in ownership_roots(context) {
        if root.resource_kind != Some(source.identity.kind) {
            continue;
        }
        if ancestry(path, &root.path).map_err(ReportFailure::Path)?
            && resource_path_is_valid(path, &root)
            && !roots.contains(&root)
        {
            roots.push(root);
        }
    }
    Ok(roots)
}

/// The move preview of `request`, or why it cannot be previewed.
pub(crate) fn move_preview(
    source: ReportSource<'_>,
    request: &MoveRequest,
) -> Result<(Option<MovePreview>, Vec<DiagnosticFacts>), ReportFailure> {
    let context: Context<'_> = Context::new(source);
    let matches: Vec<usize> = query(&context, &request.resource)
        .map(resource_matches)
        .unwrap_or_default();
    let [position] = matches.as_slice() else {
        let message: String = format!(
            "Move source {} does not resolve to exactly one resource",
            target_text(&request.resource)
        );
        return Ok((None, vec![diagnostic(UNKNOWN_TARGET, message, None)]));
    };
    let moving: &ResourceRecord = context.resource(*position);
    let Ok(path) = normalized(&request.destination) else {
        return Ok((None, vec![invalid_destination(&request.destination)]));
    };
    let roots: Vec<OwnershipRoot> = destination_roots(&context, moving, &path)?;
    let occupied: bool = !context.resources_at(&path).is_empty() && path != moving.path;
    let ([root], false) = (roots.as_slice(), occupied) else {
        return Ok((None, vec![invalid_destination(&request.destination)]));
    };
    let moved: ResourceRecord = ResourceRecord {
        identity: moving.identity.clone(),
        path: path.clone(),
        ownership_root: root.clone(),
    };
    let (old_direct, old_relationships) = visible(
        classify_report_resource(source.records, source.lookup, moving)
            .map_err(ReportFailure::Path)?,
    );
    let (new_direct, new_relationships) = visible(
        classify_report_resource(source.records, source.lookup, &moved)
            .map_err(ReportFailure::Path)?,
    );
    let old: ByIdentity<'_> = keyed(&context, old_direct);
    let new: ByIdentity<'_> = keyed(&context, new_direct);
    let consumer: QualifiedIdentity = QualifiedIdentity::Resource(moving.identity.clone());
    let direct_usages: HashSet<String> = context
        .usages_of_consumer(&consumer)
        .iter()
        .map(|usage| context.usage(*usage))
        .filter(|usage| usage.through.is_none())
        .map(|usage| qualified(&usage.declaration))
        .collect();
    let old_related: ByIdentity<'_> = keyed(&context, old_relationships);
    let new_related: HashSet<String> = keyed(&context, new_relationships).into_keys().collect();
    let private: HashMap<String, &DeclarationIdentity> = context
        .canonical_declarations()
        .iter()
        .map(|position| context.declaration(*position))
        .filter(|record| {
            record.scope == ScopeKind::Private
                && record.identity.owner.as_ref() == Some(&moving.identity)
        })
        .map(|record| (qualified(&record.identity), &record.identity))
        .collect();
    let mut private_order: Vec<(&String, &&DeclarationIdentity)> = private.iter().collect();
    private_order.sort_by(|left, right| left.0.cmp(right.0));
    let private_retained: Vec<DeclarationReport> = private_order
        .into_iter()
        .flat_map(|(_, identity)| context.declarations_of(identity).iter())
        .map(|position| declaration_report(&context, *position, None, None))
        .collect();
    let completeness = context.completeness();
    Ok((
        Some(MovePreview {
            resource: format_identity(&consumer),
            destination: path,
            new_ownership_root: Some(root.path.clone()),
            retained: reports(&context, &old, |text| new.contains_key(text)),
            gained: reports(&context, &new, |text| !old.contains_key(text)),
            lost: reports(&context, &old, |text| !new.contains_key(text)),
            invalidated_usages: old
                .keys()
                .filter(|text| !new.contains_key(*text) && direct_usages.contains(*text))
                .cloned()
                .collect(),
            private_retained,
            relationship_retained: reports(&context, &old_related, |text| {
                new_related.contains(text)
            }),
            complete: completeness.static_visibility
                && completeness.runtime_usage
                && completeness.relationships,
        }),
        Vec::new(),
    ))
}

/// Directly visible positions of each scoped (macro, enum, constant) declaration identity.
fn scoped_bindings(context: &Context<'_>, values: Visible) -> BTreeMap<String, Vec<usize>> {
    let mut bindings: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (position, _) in values {
        let identity: &DeclarationIdentity = &context.declaration(position).identity;
        if matches!(
            identity.kind,
            DeclarationKind::Macro | DeclarationKind::Enum | DeclarationKind::Constant
        ) {
            bindings
                .entry(qualified(identity))
                .or_default()
                .push(position);
        }
    }
    for positions in bindings.values_mut() {
        positions.sort_unstable();
    }
    bindings
}

/// Used scoped declarations that resolve differently from `destination`; `None` if it is invalid.
pub(crate) fn rebound_usages(
    source: ReportSource<'_>,
    (path, destination): (&str, &str),
) -> Result<Option<Vec<String>>, ReportFailure> {
    let context: Context<'_> = Context::new(source);
    let Ok(destination) = normalized(destination) else {
        return Ok(None);
    };
    let mut rebound: Vec<String> = Vec::new();
    for position in context.resources_at(path) {
        let moving: &ResourceRecord = context.resource(*position);
        let roots: Vec<OwnershipRoot> = destination_roots(&context, moving, &destination)?;
        let [root] = roots.as_slice() else {
            return Ok(None);
        };
        let moved: ResourceRecord = ResourceRecord {
            identity: moving.identity.clone(),
            path: destination.clone(),
            ownership_root: root.clone(),
        };
        let (old_direct, _) = visible(
            classify_report_resource(source.records, source.lookup, moving)
                .map_err(ReportFailure::Path)?,
        );
        let (new_direct, _) = visible(
            classify_report_resource(source.records, source.lookup, &moved)
                .map_err(ReportFailure::Path)?,
        );
        let old: BTreeMap<String, Vec<usize>> = scoped_bindings(&context, old_direct);
        let new: BTreeMap<String, Vec<usize>> = scoped_bindings(&context, new_direct);
        let consumer: QualifiedIdentity = QualifiedIdentity::Resource(moving.identity.clone());
        for usage in context.usages_of_consumer(&consumer) {
            let usage = context.usage(*usage);
            let text: String = qualified(&usage.declaration);
            if usage.through.is_none()
                && old.contains_key(&text)
                && old.get(&text) != new.get(&text)
                && !rebound.contains(&text)
            {
                rebound.push(text);
            }
        }
    }
    rebound.sort();
    Ok(Some(rebound))
}
