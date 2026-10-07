//! Audit lists and instances, as `parse_audit_instances` reads them with `null_as_empty`.

use crate::header_metadata::_helpers::text::{
    entry, is_snake_case, non_blank_text, optional_bool, optional_count, optional_text,
};
use crate::header_metadata::constants::{AUDIT_OPTION_KEYS, AUDIT_SEVERITIES};
use crate::header_metadata::models::{HeaderMetadataDeferral, ParsedAudit};
use crate::types::{AuthoredNode, NodeKind};

/// Parse an authored audit list; Python's `None` is an empty list.
pub(crate) fn audit_list<N: AuthoredNode>(
    node: &N,
) -> Result<Vec<ParsedAudit<N>>, HeaderMetadataDeferral> {
    match node.kind() {
        NodeKind::Null => Ok(Vec::new()),
        NodeKind::List => node.items().iter().map(audit_instance).collect(),
        _ => Err(HeaderMetadataDeferral::Invalid),
    }
}

fn audit_instance<N: AuthoredNode>(node: &N) -> Result<ParsedAudit<N>, HeaderMetadataDeferral> {
    match node.kind() {
        NodeKind::Str => {
            identity(node)?;
            Ok(bare_audit(node.clone()))
        }
        NodeKind::Map => {
            let entries = node.entries();
            let [(definition_name, arguments)] = entries.as_slice() else {
                return Err(HeaderMetadataDeferral::Invalid);
            };
            identity(definition_name)?;
            match arguments.kind() {
                NodeKind::Null => Ok(bare_audit(definition_name.clone())),
                NodeKind::Map => configured_audit(definition_name, &arguments.entries()),
                _ => Err(HeaderMetadataDeferral::Invalid),
            }
        }
        _ => Err(HeaderMetadataDeferral::Invalid),
    }
}

fn configured_audit<N: AuthoredNode>(
    definition_name: &N,
    options: &[(N, N)],
) -> Result<ParsedAudit<N>, HeaderMetadataDeferral> {
    let name = optional_text(entry(options, "name"))?;
    if let Some(name) = &name {
        identity(name)?;
    }
    let description = optional_text(entry(options, "description"))?;
    let severity = optional_text(entry(options, "severity"))?;
    if let Some(severity) = &severity {
        let text = severity.text().ok_or(HeaderMetadataDeferral::Unsupported)?;
        if !AUDIT_SEVERITIES.contains(&text.as_str()) {
            return Err(HeaderMetadataDeferral::Invalid);
        }
    }
    let run_scope = optional_text(entry(options, "run_scope"))?;
    let always_run = optional_bool(entry(options, "always_run"))?;
    if entry(options, "thresholds").is_some_and(|value| value.kind() != NodeKind::Null) {
        return Err(HeaderMetadataDeferral::Unsupported);
    }
    let minimum_samples = optional_count(entry(options, "minimum_samples"))?;
    let evidence_limit = optional_count(entry(options, "evidence_limit"))?;
    let arguments: Vec<(N, N)> = options
        .iter()
        .filter(|(key, _)| !is_option_key(key))
        .cloned()
        .collect();
    Ok(ParsedAudit {
        definition_name: definition_name.clone(),
        arguments,
        name,
        description,
        severity,
        run_scope,
        always_run,
        minimum_samples,
        evidence_limit,
    })
}

fn bare_audit<N: AuthoredNode>(definition_name: N) -> ParsedAudit<N> {
    ParsedAudit {
        definition_name,
        arguments: Vec::new(),
        name: None,
        description: None,
        severity: None,
        run_scope: None,
        always_run: None,
        minimum_samples: None,
        evidence_limit: None,
    }
}

fn identity<N: AuthoredNode>(node: &N) -> Result<(), HeaderMetadataDeferral> {
    if is_snake_case(&non_blank_text(node)?) {
        Ok(())
    } else {
        Err(HeaderMetadataDeferral::Invalid)
    }
}

fn is_option_key<N: AuthoredNode>(key: &N) -> bool {
    AUDIT_OPTION_KEYS.iter().any(|name| key.is_text(name))
}
