//! `--drop-old-name-view` requests matched against recorded old names.

/// Whether the dotted request names the trailing parts of the recorded old name, ignoring case.
#[must_use]
pub fn old_name_request_matches(
    request: &str,
    (database, schema, name): (Option<&str>, Option<&str>, &str),
) -> bool {
    let parts: Vec<String> = request
        .split('.')
        .map(|part| part.trim().trim_matches('"').to_lowercase())
        .collect();
    let spelled: Vec<String> = [database, schema, Some(name)]
        .into_iter()
        .flatten()
        .map(str::to_lowercase)
        .collect();
    spelled.len() >= parts.len() && spelled[spelled.len() - parts.len()..] == parts[..]
}
