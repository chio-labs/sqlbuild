//! The git ref a `--since` value names, reading `@base` from `[git] base_ref`.

use crate::git_revisions::constants::{BASE_REF_ALIAS, BASE_REF_UNSET_CODE};
use crate::git_revisions::errors::GitRevisionError;

/// `value` itself, or the configured base ref when `value` is `@base`.
pub fn resolve_since_reference(
    value: &str,
    configured_base_ref: Option<&str>,
) -> Result<String, GitRevisionError> {
    let value: &str = value.trim();
    if value != BASE_REF_ALIAS {
        return Ok(value.to_owned());
    }
    match configured_base_ref.map(str::trim) {
        Some(base_ref) if !base_ref.is_empty() => Ok(base_ref.to_owned()),
        _ => Err(GitRevisionError {
            message: format!(
                "--since {BASE_REF_ALIAS} needs [git] base_ref in sqlbuild_project.toml"
            ),
            code: BASE_REF_UNSET_CODE,
            help: "Add [git] base_ref = \"origin/main\" (your default branch) to \
                   sqlbuild_project.toml, or pass a ref such as --since origin/main"
                .to_owned(),
        }),
    }
}
