//! The messages enum and constant expansion raises, worded as the attachment always has.

use crate::compiled_project::constants::{
    DECLARATION_EXPANSION_CONTEXT, INVALID_CONSTANT_REFERENCE_STOP, INVALID_ENUM_REFERENCE_STOP,
    UNCLOSED_BLOCK_COMMENT_STOP,
};
use crate::compiled_project::models::InaccessibleDeclaration;

pub(crate) fn unknown_declaration(
    kind: &str,
    name: &str,
    consumer: &str,
    visible: &[String],
) -> String {
    let scope_help: &str = if name.starts_with('_') {
        " in this model"
    } else {
        ""
    };
    let mut names: Vec<&str> = visible.iter().map(String::as_str).collect();
    names.sort_unstable();
    let listed: String = if names.is_empty() {
        "none".to_owned()
    } else {
        names.join(", ")
    };
    format!("Unknown {kind} '{name}'{scope_help} in '{consumer}'. Visible {kind}s: {listed}")
}

pub(crate) fn unknown_member(
    name: &str,
    member: &str,
    consumer: &str,
    members: &[String],
) -> String {
    format!(
        "Unknown member '{member}' for enum '{name}' in '{consumer}'. Available members: {}",
        members.join(", ")
    )
}

pub(crate) fn inaccessible(
    kind: &str,
    name: &str,
    consumer: &str,
    record: &InaccessibleDeclaration,
) -> String {
    let owner_identity: String = record
        .owner_identity
        .as_ref()
        .map(|(owner_kind, owner_name)| format!(" ({owner_kind} '{owner_name}')"))
        .unwrap_or_default();
    format!(
        "{} '{name}' is known but inaccessible in '{consumer}'. It is defined at {}:{}:{} with \
         {} scope owned by '{}'{owner_identity}; consumer path: '{consumer}'",
        capitalized(kind),
        record.path,
        record.line,
        record.column,
        record.scope,
        record.owner,
    )
}

pub(crate) fn scan_stop(code: u8, consumer: &str) -> String {
    match code {
        INVALID_ENUM_REFERENCE_STOP => format!("Invalid enum reference in '{consumer}'"),
        INVALID_CONSTANT_REFERENCE_STOP => format!("Invalid constant reference in '{consumer}'"),
        UNCLOSED_BLOCK_COMMENT_STOP => {
            format!("{DECLARATION_EXPANSION_CONTEXT} contains an unclosed block comment")
        }
        _ => format!("{DECLARATION_EXPANSION_CONTEXT} contains an unclosed quoted string"),
    }
}

/// `str.capitalize`: the first character upper-cased, the rest lower-cased.
fn capitalized(text: &str) -> String {
    let mut characters = text.chars();
    characters.next().map_or_else(String::new, |first| {
        first
            .to_uppercase()
            .chain(characters.flat_map(char::to_lowercase))
            .collect()
    })
}
