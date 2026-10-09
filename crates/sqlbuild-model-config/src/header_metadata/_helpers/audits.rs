//! Audit lists and instances, as `parse_audit_instances` reads them with `null_as_empty`.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::identity::check_identity;
use crate::header_metadata::_helpers::text::{
    Site, entry, non_blank_text, optional_bool, optional_count, optional_text,
};
use crate::header_metadata::_helpers::thresholds::thresholds;
use crate::header_metadata::constants::{AUDIT_OPTION_KEYS, AUDIT_SEVERITIES};
use crate::header_metadata::models::ParsedAudit;
use crate::types::{AuthoredNode, NodeKind};

/// Parse an authored audit list; Python's `None` is an empty list.
pub(crate) fn audit_list<N: AuthoredNode>(
    node: &N,
    site: Site<'_>,
) -> Result<Vec<ParsedAudit<N>>, ConfigError> {
    match node.kind() {
        NodeKind::Null => Ok(Vec::new()),
        NodeKind::List => node
            .items()
            .iter()
            .map(|item| audit_instance(item, site))
            .collect(),
        _ => Err(site.error("audits must be a list")),
    }
}

fn audit_instance<N: AuthoredNode>(
    node: &N,
    site: Site<'_>,
) -> Result<ParsedAudit<N>, ConfigError> {
    let definition_kind = format!("{} audit definition", site.label);
    if node.kind() == NodeKind::Str {
        let Some(text) = non_blank_text(node) else {
            return Err(site.error("audits must not contain empty names"));
        };
        check_identity(&text, &definition_kind, site.path)?;
        return Ok(bare_audit(node.clone()));
    }
    let entries = node.entries();
    let [(definition_name, arguments)] = entries.as_slice() else {
        return Err(site.error("audits must be strings or single-key mappings"));
    };
    if node.kind() != NodeKind::Map {
        return Err(site.error("audits must be strings or single-key mappings"));
    }
    let Some(definition) = non_blank_text(definition_name) else {
        return Err(site.error("audit names must be non-empty strings"));
    };
    check_identity(&definition, &definition_kind, site.path)?;
    match arguments.kind() {
        NodeKind::Null => Ok(bare_audit(definition_name.clone())),
        NodeKind::Map => configured_audit(definition_name, &definition, &arguments.entries(), site),
        _ => Err(site.error(&format!("audit '{definition}' arguments must be a mapping"))),
    }
}

fn configured_audit<N: AuthoredNode>(
    definition_name: &N,
    definition: &str,
    options: &[(N, N)],
    site: Site<'_>,
) -> Result<ParsedAudit<N>, ConfigError> {
    let option_label = format!("{} audit '{definition}'", site.label);
    let option_site = Site {
        path: site.path,
        label: &option_label,
        column: site.column,
    };
    let name = optional_text(entry(options, "name"), option_site, "name")?;
    if let Some(name) = &name {
        let text = name.text().unwrap_or_default();
        check_identity(&text, &format!("{} audit instance", site.label), site.path)?;
    }
    let description = optional_text(entry(options, "description"), option_site, "description")?;
    let severity = optional_text(entry(options, "severity"), option_site, "severity")?;
    if let Some(severity) = &severity
        && !AUDIT_SEVERITIES.iter().any(|value| severity.is_text(value))
    {
        return Err(option_site.error(&format!(
            "'severity' must be one of: {}",
            AUDIT_SEVERITIES.join(", ")
        )));
    }
    let run_scope = optional_text(entry(options, "run_scope"), option_site, "run_scope")?;
    let always_run = optional_bool(entry(options, "always_run"), option_site, "always_run")?;
    let thresholds = thresholds(entry(options, "thresholds"), option_site)?;
    let minimum_samples = optional_count(
        entry(options, "minimum_samples"),
        option_site,
        (definition, "minimum_samples"),
    )?;
    let evidence_limit = optional_count(
        entry(options, "evidence_limit"),
        option_site,
        (definition, "evidence_limit"),
    )?;
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
        thresholds,
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
        thresholds: None,
        minimum_samples: None,
        evidence_limit: None,
    }
}

fn is_option_key<N: AuthoredNode>(key: &N) -> bool {
    AUDIT_OPTION_KEYS.iter().any(|name| key.is_text(name))
}
