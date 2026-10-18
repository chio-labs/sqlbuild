//! How a generic audit's SQL uses one argument: spliced in as SQL, quoted, or unknown.

use std::path::Path;

use crate::refactoring::_helpers::scanning::chars::chars;
use crate::refactoring::constants::{
    AUDIT_PARAMETER_SIGIL, GENERIC_AUDIT_DIRECTORY, SQL_STRING_QUOTE,
};
use crate::refactoring::models::{AuthoredFile, SqlFileRole};

/// How every definition of a generic audit renders one argument.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ArgumentUsage {
    /// Every definition splices the argument in as SQL with `@name`.
    Sql,
    /// A definition quotes the argument as a string literal with `@'name'`.
    Literal,
    /// No project SQL definition shows how the argument is used.
    Unknown,
}

/// How the project's SQL definitions of `audit` render argument `key`.
pub(crate) fn argument_usage(files: &[AuthoredFile], audit: &str, key: &str) -> ArgumentUsage {
    let definitions: Vec<&AuthoredFile> = files
        .iter()
        .filter(|file| file.role == SqlFileRole::Audit && defines_generic_audit(&file.path, audit))
        .collect();
    let mut usage = ArgumentUsage::Unknown;
    for definition in definitions {
        let (spliced, quoted) = parameter_uses(&chars(&definition.contents), key);
        if quoted {
            return ArgumentUsage::Literal;
        }
        if !spliced {
            return ArgumentUsage::Unknown;
        }
        usage = ArgumentUsage::Sql;
    }
    usage
}

/// Whether `path` is a generic audit definition file named `audit`.
fn defines_generic_audit(path: &str, audit: &str) -> bool {
    let path = Path::new(path);
    path.file_stem().is_some_and(|stem| stem == audit)
        && path
            .parent()
            .and_then(Path::file_name)
            .is_some_and(|directory| directory == GENERIC_AUDIT_DIRECTORY)
}

/// Whether the SQL uses `@key` unquoted and whether it uses `@'key'`.
fn parameter_uses(text: &[char], key: &str) -> (bool, bool) {
    let key: Vec<char> = chars(key);
    let mut spliced = false;
    let mut quoted = false;
    for (index, character) in text.iter().enumerate() {
        if *character != AUDIT_PARAMETER_SIGIL {
            continue;
        }
        let rest = &text[index + 1..];
        if rest.starts_with(&key) && !rest.get(key.len()).is_some_and(|next| is_word(*next)) {
            spliced = true;
        }
        let quoted_name = rest.first() == Some(&SQL_STRING_QUOTE)
            && rest[1..].starts_with(&key)
            && rest.get(key.len() + 1) == Some(&SQL_STRING_QUOTE);
        quoted = quoted || quoted_name;
    }
    (spliced, quoted)
}

fn is_word(character: char) -> bool {
    character.is_alphanumeric() || character == '_'
}
