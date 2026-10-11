//! `audit_factories` references read as `parse_model_header_audit_factories` reads them.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::text::non_blank_text;
use crate::types::{AuthoredNode, NodeKind};

pub(crate) fn factory_references<N: AuthoredNode>(
    raw: &N,
    model_name: &str,
    path: &str,
    available: &[String],
) -> Result<Vec<String>, ConfigError> {
    if raw.kind() == NodeKind::Null {
        return Ok(Vec::new());
    }
    if raw.kind() != NodeKind::List {
        return Err(ConfigError::compile(format!(
            "{path} model audit_factories must be a list"
        )));
    }
    let mut references: Vec<String> = Vec::new();
    for entry in raw.items() {
        let Some(value) = non_blank_text(&entry) else {
            return Err(ConfigError::compile(format!(
                "{path} model audit_factories entries must be bare identifiers"
            )));
        };
        if !is_bare_identifier(&value) {
            return Err(ConfigError::compile(format!(
                "{path} model audit_factories entry '{value}' must be a bare identifier"
            )));
        }
        if references.contains(&value) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}' in {path} references audit factory '{value}' more than once"
            )));
        }
        references.push(value);
    }
    if let Some(unknown) = references
        .iter()
        .find(|reference| !available.contains(reference))
    {
        let mut names: Vec<&str> = available.iter().map(String::as_str).collect();
        names.sort_unstable();
        let listed: String = if names.is_empty() {
            "none discovered".to_owned()
        } else {
            names.join(", ")
        };
        return Err(ConfigError::compile(format!(
            "model '{model_name}' in {path} references unknown audit factory '{unknown}'. \
             Available audit factories: {listed}"
        )));
    }
    Ok(references)
}

/// The first generated audit whose identity a direct or earlier generated audit already uses.
pub(crate) fn duplicate_identity(
    direct: &[String],
    generated: &[String],
    model_name: &str,
    path: &str,
) -> Result<(), ConfigError> {
    let mut seen: Vec<&str> = direct.iter().map(String::as_str).collect();
    for identity in generated {
        if seen.contains(&identity.as_str()) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}' in {path} has duplicate audit case name '{identity}' across \
                 direct and factory attachments"
            )));
        }
        seen.push(identity);
    }
    Ok(())
}

/// Python's `re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)`.
fn is_bare_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}
