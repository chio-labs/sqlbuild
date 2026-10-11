//! Report section selection: filters, dependencies, nearby declarations, chains and pages.

use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, QualifiedIdentity, RejectedPath, ResourceRecord,
    ScopeKind,
};
use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::declarations::{declaration_report, declaration_text};
use crate::scope_report::_helpers::paths::{ancestry, normalized, part_count};
use crate::scope_report::_helpers::targets::raised;
use crate::scope_report::constants::{
    CURRENT_PATH, DEPENDENCY_REASON, GLOBAL_CHAIN, IDENTITY_SEPARATOR, INHERITED_CHAIN,
    INVALID_CURSOR, LOCAL_CHAIN,
};
use crate::scope_report::models::{
    DeclarationReport, DiagnosticFacts, Provenance, ReportFilters, ScopeChainEntry, ScopeSection,
};
use sqlbuild_core::posix_path::main::posix_parent::posix_parent;
use sqlbuild_core::text::main::python_fnmatchcase::python_fnmatchcase;
use std::collections::{BTreeSet, HashMap, HashSet};

/// Declarations at input positions with what each carries: a provenance or a hidden reason.
pub(crate) type Selected<T> = Vec<(usize, T)>;

/// `_filter_visible` and `_filter_nearby`: folder, kind, glob and used filters in order.
pub(crate) fn filtered<T>(
    context: &Context<'_>,
    values: Selected<T>,
    filters: &ReportFilters,
    used: &HashSet<&DeclarationIdentity>,
) -> Selected<T> {
    let mut selected: Selected<T> = values;
    if let Some(defined_under) = &filters.defined_under {
        selected = defined_beneath(context, selected, defined_under);
    }
    if !filters.kinds.is_empty() {
        selected.retain(|(position, _)| {
            let kind: &str = context.declaration(*position).identity.kind.as_str();
            filters
                .kinds
                .iter()
                .any(|selected_kind| selected_kind == kind)
        });
    }
    if let Some(glob) = &filters.glob {
        selected.retain(|(position, _)| glob_matches(context.declaration(*position), glob));
    }
    if filters.used_only {
        selected.retain(|(position, _)| used.contains(&context.declaration(*position).identity));
    }
    selected
}

/// The items defined beneath `defined_under`; any path `normalize_path` rejects empties them.
fn defined_beneath<T>(
    context: &Context<'_>,
    values: Selected<T>,
    defined_under: &str,
) -> Selected<T> {
    let Ok(under) = normalized(defined_under) else {
        return Vec::new();
    };
    let mut kept: Selected<T> = Vec::new();
    for item in values {
        match ancestry(&context.declaration(item.0).path, &under) {
            Ok(true) => kept.push(item),
            Ok(false) => {}
            Err(_) => return Vec::new(),
        }
    }
    kept
}

/// Whether the glob matches the declaration's name or qualified identity.
pub(crate) fn glob_matches(record: &DeclarationRecord, glob: &str) -> bool {
    python_fnmatchcase(&record.identity.name, glob)
        || python_fnmatchcase(&declaration_text(record), glob)
}

/// `(format_identity, path)`: the order reports list declarations in.
pub(crate) fn report_key(context: &Context<'_>, position: usize) -> (String, String) {
    let record: &DeclarationRecord = context.declaration(position);
    (declaration_text(record), record.path.clone())
}

/// `_expand_dependencies`: the used declarations with `depth` levels of their dependencies.
pub(crate) fn expand_dependencies(
    context: &Context<'_>,
    values: Selected<Provenance>,
    depth: i64,
) -> Selected<Provenance> {
    let mut order: Vec<&DeclarationIdentity> = Vec::new();
    let mut selected: HashMap<&DeclarationIdentity, (usize, Provenance)> = HashMap::new();
    for (position, provenance) in values {
        let identity: &DeclarationIdentity = &context.declaration(position).identity;
        if selected.insert(identity, (position, provenance)).is_none() {
            order.push(identity);
        }
    }
    let mut frontier: Vec<&DeclarationIdentity> = order.clone();
    for _level in 0..depth.max(0) {
        let mut dependencies: Vec<&DeclarationIdentity> = Vec::new();
        for identity in &frontier {
            for position in context.declarations_of(identity) {
                if let Some(macro_values) = context
                    .values(*position)
                    .and_then(|values| values.macro_values.as_ref())
                {
                    dependencies.extend(macro_values.dependencies.iter());
                }
            }
            let consumer: QualifiedIdentity = QualifiedIdentity::Declaration((*identity).clone());
            dependencies.extend(
                context
                    .usages_of_consumer(&consumer)
                    .iter()
                    .map(|usage| &context.usage(*usage).declaration),
            );
        }
        let mut next: Vec<&DeclarationIdentity> = Vec::new();
        for identity in dependencies {
            if !selected.contains_key(identity) && !next.contains(&identity) {
                next.push(identity);
            }
        }
        for identity in &next {
            for position in context.declarations_of(identity) {
                let provenance: Provenance = Provenance {
                    reason: DEPENDENCY_REASON.to_owned(),
                    through: None,
                };
                if selected.insert(identity, (*position, provenance)).is_none() {
                    order.push(identity);
                }
            }
        }
        frontier = next;
    }
    let mut expanded: Selected<Provenance> = order
        .into_iter()
        .filter_map(|identity| selected.remove(identity))
        .collect();
    expanded.sort_by_cached_key(|(position, _)| report_key(context, *position));
    expanded
}

/// `_nearby`: hidden declarations in the resource's own root, folder line or relationships.
pub(crate) fn nearby(
    context: &Context<'_>,
    resource: &ResourceRecord,
    unavailable: Selected<String>,
    depth: i64,
) -> Result<Selected<String>, RejectedPath> {
    let parent: String = posix_parent(&resource.path);
    let parent_parent: String = posix_parent(&parent);
    let depth: i64 = depth.max(0);
    let parent_parts: i64 = i64::try_from(part_count(&parent)).unwrap_or(i64::MAX);
    let related: HashSet<&DeclarationIdentity> = context
        .grants_of_resource(&resource.identity)
        .iter()
        .map(|grant| &context.grant(*grant).declaration)
        .collect();
    let mut result: Selected<String> = Vec::new();
    for (position, reason) in unavailable {
        let record: &DeclarationRecord = context.declaration(position);
        if record.scope == ScopeKind::Private
            && record.identity.owner.as_ref() != Some(&resource.identity)
        {
            continue;
        }
        let owner: &str = record
            .owning_path
            .as_deref()
            .filter(|path| !path.is_empty())
            .unwrap_or(&record.ownership_root.path);
        let same_root: bool = record.ownership_root.path == resource.ownership_root.path;
        let ancestor: bool = ancestry(&parent, owner)?;
        let connected: bool = related.contains(&record.identity);
        let sibling: bool = depth >= 1 && posix_parent(owner) == parent_parent;
        let descendant: bool = ancestry(owner, &parent)?
            && i64::try_from(part_count(owner)).unwrap_or(i64::MAX) - parent_parts <= depth;
        if connected || (same_root && (ancestor || sibling || descendant)) {
            result.push((position, reason));
        }
    }
    Ok(result)
}

/// `_scope_chain`: the resource's folder, its ancestors to the root, then the global scope.
pub(crate) fn scope_chain(
    context: &Context<'_>,
    resource: &ResourceRecord,
) -> Vec<ScopeChainEntry> {
    let parent: String = posix_parent(&resource.path);
    let root: &str = &resource.ownership_root.path;
    let mut paths: Vec<String> = vec![parent.clone()];
    let mut current: String = parent.clone();
    while current != CURRENT_PATH && current != root {
        let next: String = posix_parent(&current);
        if next == current {
            break;
        }
        current = next;
        paths.push(current.clone());
    }
    paths.push(root.to_owned());
    let mut unique: Vec<String> = Vec::new();
    for path in paths {
        if !unique.contains(&path) {
            unique.push(path);
        }
    }
    unique.sort_by(|left, right| {
        part_count(right)
            .cmp(&part_count(left))
            .then_with(|| left.cmp(right))
    });
    let mut counts: HashMap<&str, i64> = HashMap::new();
    let mut global: i64 = 0;
    for position in context.canonical_declarations() {
        let record: &DeclarationRecord = context.declaration(*position);
        if record.scope == ScopeKind::Global {
            global += 1;
            continue;
        }
        let owner: &str = record
            .owning_path
            .as_deref()
            .filter(|path| !path.is_empty())
            .unwrap_or(&record.ownership_root.path);
        *counts.entry(owner).or_default() += 1;
    }
    let mut entries: Vec<ScopeChainEntry> = unique
        .into_iter()
        .map(|path| ScopeChainEntry {
            kind: if path == parent {
                LOCAL_CHAIN
            } else {
                INHERITED_CHAIN
            }
            .to_owned(),
            declaration_count: counts.get(path.as_str()).copied().unwrap_or(0),
            path,
        })
        .collect();
    entries.push(ScopeChainEntry {
        kind: GLOBAL_CHAIN.to_owned(),
        path: GLOBAL_CHAIN.to_owned(),
        declaration_count: global,
    });
    entries
}

/// A section's name, page size, completeness and collapsed global count.
pub(crate) struct PageSpec<'a> {
    pub(crate) name: &'a str,
    pub(crate) cursor: Option<&'a str>,
    pub(crate) page_size: i64,
    pub(crate) complete: bool,
    pub(crate) collapsed: i64,
}

/// `len(values)` as Python counts it.
pub(crate) fn count(length: usize) -> i64 {
    i64::try_from(length).unwrap_or(i64::MAX)
}

/// The text after the last `:`, as `identity.rsplit(":", 1)[-1]` reads it.
fn bare_name(identity: &str) -> &str {
    identity
        .rsplit_once(IDENTITY_SEPARATOR)
        .map_or(identity, |(_, name)| name)
}

/// The most times `identity` appears in any one section.
fn most_in_one_section(sections: &[Vec<String>], identity: &str) -> usize {
    sections
        .iter()
        .map(|section| occurrences(section, identity))
        .max()
        .unwrap_or(0)
}

/// How many times `identity` appears in one section.
fn occurrences(section: &[String], identity: &str) -> usize {
    section.iter().filter(|item| *item == identity).count()
}

/// The qualified identity text of each declaration in one section.
fn section_texts(context: &Context<'_>, section: &Selected<Provenance>) -> Vec<String> {
    section
        .iter()
        .map(|(position, _)| declaration_text(context.declaration(*position)))
        .collect()
}

/// `_resolve_cursor`: a qualified or uniquely bare identity appearing once per section.
pub(crate) fn resolve_cursor(
    context: &Context<'_>,
    requested: Option<&str>,
    sections: &[&Selected<Provenance>],
) -> (Option<String>, Option<DiagnosticFacts>) {
    let Some(requested) = requested else {
        return (None, None);
    };
    let identities: Vec<Vec<String>> = sections
        .iter()
        .map(|section| section_texts(context, section))
        .collect();
    let unique: BTreeSet<&String> = identities.iter().flatten().collect();
    let qualified: bool = requested.contains(IDENTITY_SEPARATOR);
    if qualified
        && unique.iter().any(|identity| identity.as_str() == requested)
        && most_in_one_section(&identities, requested) == 1
    {
        return (Some(requested.to_owned()), None);
    }
    let bare: Vec<&&String> = unique
        .iter()
        .filter(|identity| bare_name(identity) == requested)
        .collect();
    if let [resolved] = bare.as_slice()
        && !qualified
        && most_in_one_section(&identities, resolved) == 1
    {
        return (Some((**resolved).clone()), None);
    }
    (None, Some(raised(INVALID_CURSOR, "Cursor", requested)))
}

/// `_page`: the reports after the cursor, one page long, and the section describing them.
pub(crate) fn page(
    context: &Context<'_>,
    values: &Selected<Provenance>,
    spec: &PageSpec<'_>,
) -> (Vec<DeclarationReport>, ScopeSection) {
    let size: usize = usize::try_from(spec.page_size.max(0)).unwrap_or(usize::MAX);
    let start: usize = spec
        .cursor
        .and_then(|cursor| {
            values.iter().position(|(position, _)| {
                declaration_text(context.declaration(*position)) == cursor
            })
        })
        .map_or(0, |index| index + 1);
    let end: usize = start.saturating_add(size).min(values.len());
    let selected: &[(usize, Provenance)] = values.get(start..end).unwrap_or_default();
    let reports: Vec<DeclarationReport> = selected
        .iter()
        .map(|(position, provenance)| {
            declaration_report(context, *position, Some(provenance.clone()), None)
        })
        .collect();
    let truncated: bool = start + selected.len() < values.len();
    let next_cursor: Option<String> = reports
        .last()
        .filter(|_| truncated)
        .map(|report| report.identity.clone());
    let section: ScopeSection = ScopeSection {
        name: spec.name.to_owned(),
        total: count(values.len()) + spec.collapsed,
        returned: count(reports.len()),
        collapsed: spec.collapsed > 0,
        collapsed_count: spec.collapsed,
        truncated,
        complete: spec.complete,
        next_cursor,
        cursor: spec.cursor.map(str::to_owned),
        page_size: count(size),
    };
    (reports, section)
}
