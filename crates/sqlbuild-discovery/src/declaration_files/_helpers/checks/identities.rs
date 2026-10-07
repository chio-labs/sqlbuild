//! Python's `validate_resource_identity` for declaration names that are already SQL identifiers.

use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::models::{DiscoveryFailure, FailureKind};

const IDENTITY_HELP: &str = "Rename the authored identity and update its references, selectors, \
                             and integration keys. SQLBuild does not silently normalize resource \
                             identities. Double underscores remain valid.";
const FALLBACK_IDENTITY: &str = "resource_name";

/// Reject a public identity unless it is lowercase snake_case; `name` matches `[A-Za-z_]\w*`.
pub(crate) fn validate_public_identity(
    name: &str,
    kind: &str,
    file_path: &str,
) -> Result<(), ParseStop> {
    if is_snake_case(name) {
        return Ok(());
    }
    Err(ParseStop::Failed(DiscoveryFailure {
        kind: FailureKind::ResourceIdentity,
        message: format!(
            "Invalid public {kind} identity '{name}' in {file_path}; use snake_case '{}'",
            suggested_identity(name)
        ),
        help: Some(IDENTITY_HELP.to_owned()),
    }))
}

/// `^[a-z](?:[a-z0-9_]*[a-z0-9])?$`.
fn is_snake_case(name: &str) -> bool {
    let bytes = name.as_bytes();
    let tail_ok = |byte: &u8| byte.is_ascii_lowercase() || byte.is_ascii_digit();
    match bytes {
        [] => false,
        [first] => first.is_ascii_lowercase(),
        [first, middle @ .., last] => {
            first.is_ascii_lowercase()
                && middle.iter().all(|byte| tail_ok(byte) || *byte == b'_')
                && tail_ok(last)
        }
    }
}

/// `suggest_resource_identity` for an ASCII identifier: split acronyms and words, then lowercase.
fn suggested_identity(name: &str) -> String {
    let characters: Vec<char> = name.chars().collect();
    let mut acronyms: Vec<char> = Vec::with_capacity(characters.len() * 2);
    for (index, character) in characters.iter().enumerate() {
        let splits = index > 0
            && characters[index - 1].is_ascii_uppercase()
            && character.is_ascii_uppercase()
            && characters
                .get(index + 1)
                .is_some_and(char::is_ascii_lowercase);
        if splits {
            acronyms.push('_');
        }
        acronyms.push(*character);
    }
    let mut words: String = String::with_capacity(acronyms.len() * 2);
    for (index, character) in acronyms.iter().enumerate() {
        if index > 0
            && (acronyms[index - 1].is_ascii_lowercase() || acronyms[index - 1].is_ascii_digit())
            && character.is_ascii_uppercase()
        {
            words.push('_');
        }
        words.push(character.to_ascii_lowercase());
    }
    let corrected: &str = words.trim_matches('_');
    if corrected.is_empty() {
        FALLBACK_IDENTITY.to_owned()
    } else {
        corrected.to_owned()
    }
}
