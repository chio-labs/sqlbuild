//! Report targets: existing resources, prospective paths, declaration explanations and errors.

use crate::scope_index::main::explain_report_declaration::explain_report_declaration;
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::main::identity_repr::identity_repr;
use crate::scope_index::main::parse_identity::parse_identity;
use crate::scope_index::main::report_target::report_target;
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, DeclarationStanding, OwnershipRoot, QualifiedIdentity,
    ReportTarget, ResourceIdentity, ResourceKind, ResourceRecord, TargetFailure, TargetMatch,
};
use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::declarations::declaration_report;
use crate::scope_report::_helpers::paths::{
    ancestry, default_suffix, looks_like_path, normalized, part_count, resource_path_is_valid,
};
use crate::scope_report::constants::{
    DIRECT_CHILD_STEM, DUPLICATE_DECLARATION, ERROR_SEVERITY, IDENTITY_SEPARATOR,
    INVALID_PROSPECTIVE_PATH, UNKNOWN_TARGET, UNQUALIFIED_TARGET,
};
use crate::scope_report::models::{
    DeclarationTarget, DiagnosticFacts, Explanation, Provenance, QueryTarget, ReportFailure,
    ResourceReport,
};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

/// A diagnostic the query raises, with only a code, message and optional path.
pub(crate) fn diagnostic(code: &str, message: String, path: Option<String>) -> DiagnosticFacts {
    DiagnosticFacts {
        code: code.to_owned(),
        message,
        severity: ERROR_SEVERITY.to_owned(),
        path,
        line: None,
        column: None,
        declaration: None,
        resource: None,
    }
}

/// `_diagnostic`: `{label} {value!r} is not valid for this scope query`.
pub(crate) fn raised(code: &str, label: &str, value: &str) -> DiagnosticFacts {
    let shown: String = python_str_repr(active_python_text(), value);
    diagnostic(
        code,
        format!("{label} {shown} is not valid for this scope query"),
        None,
    )
}

/// `{value!r}` of Python text.
pub(crate) fn shown(value: &str) -> String {
    python_str_repr(active_python_text(), value)
}

/// `str(target)`: identity targets print their dataclass `repr`.
pub(crate) fn target_text(target: &QueryTarget) -> String {
    match target {
        QueryTarget::Identity(identity) => identity_repr(identity),
        QueryTarget::Text(text) | QueryTarget::Path(text) => text.clone(),
    }
}

/// The raw target text a report shows: qualified identity text, or the text itself.
pub(crate) fn raw_target(target: &QueryTarget) -> String {
    match target {
        QueryTarget::Identity(identity) => format_identity(identity),
        QueryTarget::Text(text) | QueryTarget::Path(text) => text.clone(),
    }
}

/// Python's `query_target`: matching resource or declaration positions, or why it raises.
pub(crate) fn query(
    context: &Context<'_>,
    target: &QueryTarget,
) -> Result<TargetMatch, ReportFailure> {
    let (target, text): (ReportTarget, String) = match target {
        QueryTarget::Identity(identity) => {
            (ReportTarget::Identity(identity.clone()), String::new())
        }
        QueryTarget::Text(text) | QueryTarget::Path(text) => {
            (ReportTarget::Text(text.clone()), text.clone())
        }
    };
    report_target(context.source.records, context.source.lookup, &target).map_err(|failure| {
        match failure {
            TargetFailure::Identity(failure) => ReportFailure::Identity(failure, text),
            TargetFailure::Path(rejected) => ReportFailure::Path(rejected),
        }
    })
}

/// The resource positions a query matched; declaration matches name no resource.
pub(crate) fn resource_matches(matched: TargetMatch) -> Vec<usize> {
    match matched {
        TargetMatch::Resources(positions) => positions,
        TargetMatch::Declarations(_) => Vec::new(),
    }
}

/// `_unknown_target_diagnostic`.
pub(crate) fn unknown_target(value: &str) -> DiagnosticFacts {
    let target_type: &str = if looks_like_path(value) {
        "path"
    } else {
        "qualified identity"
    };
    diagnostic(
        crate::scope_report::constants::UNKNOWN_TARGET,
        format!("Unknown {target_type} target {}", shown(value)),
        None,
    )
}

/// Whether text names a declaration kind before its first `:`.
pub(crate) fn names_declaration(text: &str) -> bool {
    let kind: &str = text
        .split_once(IDENTITY_SEPARATOR)
        .map_or(text, |(kind, _)| kind);
    DeclarationKind::parse(kind).is_some()
}

/// `_ownership_roots`: index and resource roots, deepest first, then by path and kind.
pub(crate) fn ownership_roots(context: &Context<'_>) -> Vec<OwnershipRoot> {
    let mut roots: Vec<OwnershipRoot> = Vec::new();
    let candidates = context.canonical_roots().chain(
        context
            .canonical_resources()
            .map(|record| &record.ownership_root),
    );
    for root in candidates {
        if !roots.contains(root) {
            roots.push(root.clone());
        }
    }
    roots.sort_by_cached_key(|root| {
        (
            std::cmp::Reverse(part_count(&root.path)),
            root.path.clone(),
            root.resource_kind
                .map(ResourceKind::as_str)
                .unwrap_or_default(),
        )
    });
    roots
}

/// `_prospective_resource`: the report and stand-in record of a path that may not exist yet.
pub(crate) fn prospective_resource(
    context: &Context<'_>,
    at: &str,
    directory: bool,
) -> Result<(ResourceReport, Option<ResourceRecord>, Vec<DiagnosticFacts>), ReportFailure> {
    let report = |path: Option<String>| ResourceReport {
        target: at.to_owned(),
        identity: None,
        path,
        prospective: true,
        directory,
        duplicate_count: 0,
    };
    let invalid = || raised(INVALID_PROSPECTIVE_PATH, "Target", at);
    let Ok(path) = normalized(at) else {
        return Ok((report(None), None, vec![invalid()]));
    };
    let mut found: Option<OwnershipRoot> = None;
    for root in ownership_roots(context) {
        if ancestry(&path, &root.path).map_err(ReportFailure::Path)? {
            found = Some(root);
            break;
        }
    }
    let Some(root) = found.filter(|root| directory || resource_path_is_valid(&path, root)) else {
        return Ok((report(Some(path)), None, vec![invalid()]));
    };
    let authored: String = if directory {
        format!("{path}/{DIRECT_CHILD_STEM}{}", default_suffix(&root))
    } else {
        path.clone()
    };
    let record: ResourceRecord = ResourceRecord {
        identity: ResourceIdentity {
            kind: root.resource_kind.unwrap_or(ResourceKind::Model),
            name: format!("<path:{path}>"),
        },
        path: authored,
        ownership_root: root,
    };
    Ok((report(Some(path)), Some(record), Vec::new()))
}

/// What `_existing_target` resolved: the report, the resource, or a declaration to explain.
pub(crate) enum ExistingTarget {
    Resource(ResourceReport, usize, Vec<DiagnosticFacts>),
    Declaration(ResourceReport),
    Missing(ResourceReport, DiagnosticFacts),
}

/// `_existing_target` without its declaration explanation, which the caller builds.
pub(crate) fn existing_target(
    context: &Context<'_>,
    target: Option<&QueryTarget>,
) -> Result<ExistingTarget, ReportFailure> {
    let missing = |raw: &str, diagnostic: DiagnosticFacts| {
        ExistingTarget::Missing(
            ResourceReport {
                target: raw.to_owned(),
                ..ResourceReport::default()
            },
            diagnostic,
        )
    };
    let Some(target) = target else {
        return Ok(missing(
            "",
            raised(
                crate::scope_report::constants::UNQUALIFIED_TARGET,
                "Target",
                "",
            ),
        ));
    };
    let raw: String = raw_target(target);
    let declaration: bool = match target {
        QueryTarget::Identity(identity) => matches!(identity, QualifiedIdentity::Declaration(_)),
        QueryTarget::Text(text) => names_declaration(text),
        QueryTarget::Path(_) => false,
    };
    if declaration {
        return Ok(ExistingTarget::Declaration(ResourceReport {
            target: raw.clone(),
            identity: Some(raw),
            ..ResourceReport::default()
        }));
    }
    if let QueryTarget::Text(text) = target
        && !text.contains(IDENTITY_SEPARATOR)
        && !looks_like_path(text)
    {
        return Ok(missing(
            &raw,
            raised(
                crate::scope_report::constants::UNQUALIFIED_TARGET,
                "Target",
                &raw,
            ),
        ));
    }
    let matches: Vec<usize> = match query(context, target) {
        Ok(TargetMatch::Declarations(positions)) if !positions.is_empty() => {
            return Err(ReportFailure::IndexOutOfRange);
        }
        Ok(matched) => resource_matches(matched),
        Err(ReportFailure::Path(_) | ReportFailure::Identity(..)) => {
            return Ok(missing(&raw, unknown_target(&raw)));
        }
        Err(failure) => return Err(failure),
    };
    let Some(first) = matches.first().copied() else {
        return Ok(missing(&raw, unknown_target(&raw)));
    };
    let mut diagnostics: Vec<DiagnosticFacts> = Vec::new();
    if matches.len() > 1 {
        diagnostics.push(diagnostic(
            crate::scope_report::constants::DUPLICATE_RESOURCE,
            format!("Target {} matches {} resources", shown(&raw), matches.len()),
            None,
        ));
    }
    let record: &ResourceRecord = context.resource(first);
    Ok(ExistingTarget::Resource(
        ResourceReport {
            target: raw,
            identity: Some(format_identity(&QualifiedIdentity::Resource(
                record.identity.clone(),
            ))),
            path: Some(crate::scope_report::_helpers::paths::safe_scope_path(
                &record.path,
            )),
            prospective: false,
            directory: false,
            duplicate_count: i64::try_from(matches.len()).unwrap_or(i64::MAX),
        },
        first,
        diagnostics,
    ))
}

/// The explanation of `target` at `at`, with its target diagnostics.
pub(crate) fn explain_declaration(
    context: &Context<'_>,
    target: &DeclarationTarget,
    at: Option<&ResourceRecord>,
) -> Result<(Explanation, Vec<DiagnosticFacts>), ReportFailure> {
    let unexplained = Explanation {
        declaration: None,
        complete: false,
    };
    let identity: Option<DeclarationIdentity> = match target {
        DeclarationTarget::Identity(identity) => Some(identity.clone()),
        DeclarationTarget::Text(text) => match parse_identity(text) {
            Ok(QualifiedIdentity::Declaration(identity)) => Some(identity),
            _ => None,
        },
    };
    let Some(identity) = identity else {
        let text: String = match target {
            DeclarationTarget::Text(text) => text.clone(),
            DeclarationTarget::Identity(identity) => {
                format_identity(&QualifiedIdentity::Declaration(identity.clone()))
            }
        };
        return Ok((
            unexplained,
            vec![raised(UNQUALIFIED_TARGET, "Target", &text)],
        ));
    };
    let qualified: String = format_identity(&QualifiedIdentity::Declaration(identity.clone()));
    let records: &[usize] = context.declarations_of(&identity);
    let Some(first) = records.first().copied() else {
        return Ok((
            unexplained,
            vec![raised(UNKNOWN_TARGET, "Target", &qualified)],
        ));
    };
    let mut diagnostics: Vec<DiagnosticFacts> = Vec::new();
    if records.len() > 1 {
        diagnostics.push(raised(DUPLICATE_DECLARATION, "Target", &qualified));
    }
    let mut visibility: Option<Provenance> = None;
    let mut inaccessible: Option<String> = None;
    if let Some(resource) = at {
        let standing: DeclarationStanding = explain_report_declaration(
            context.source.records,
            context.source.lookup,
            resource,
            context.declaration(first),
        )
        .map_err(ReportFailure::Path)?;
        match standing {
            DeclarationStanding::Visible(reason) => {
                visibility = Some(Provenance {
                    reason: reason.as_str().to_owned(),
                    through: None,
                });
            }
            DeclarationStanding::Granted(reason, through) => {
                visibility = Some(Provenance {
                    reason: reason.as_str().to_owned(),
                    through: Some(through),
                });
            }
            DeclarationStanding::Inaccessible(reason) => {
                inaccessible = Some(reason.as_str().to_owned());
            }
        }
    }
    Ok((
        Explanation {
            declaration: Some(declaration_report(context, first, visibility, inaccessible)),
            complete: context.completeness().placement,
        },
        diagnostics,
    ))
}
