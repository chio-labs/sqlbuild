//! One of database or schema of a function namespace.

pub(crate) type Part = (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);

/// `(physical, logical, fingerprint, fingerprint logical)` for one of database or schema.
pub(crate) fn part(
    header: Option<&String>,
    default: Option<&String>,
    target: Option<&String>,
    inherit: bool,
) -> Part {
    let logical: Option<String> = match header {
        Some(value) => Some(value.clone()),
        None if inherit => default.cloned(),
        None => None,
    };
    let physical: Option<String> = match target {
        None => logical.clone(),
        Some(value) if header.is_some() || inherit => Some(value.clone()),
        Some(_) => None,
    };
    let fingerprint_logical: Option<String> = header.or(default).cloned();
    let fingerprint: Option<String> = target.cloned().or_else(|| fingerprint_logical.clone());
    (physical, logical, fingerprint, fingerprint_logical)
}
