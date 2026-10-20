//! One of database or schema of a function namespace.

/// The physical, logical and fingerprint names of one of database or schema.
pub(crate) struct Part {
    pub(crate) physical: Option<String>,
    pub(crate) logical: Option<String>,
    pub(crate) fingerprint: Option<String>,
    pub(crate) fingerprint_logical: Option<String>,
}

/// The physical, logical, fingerprint and fingerprint logical names of one namespace part.
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
    Part {
        physical,
        logical,
        fingerprint,
        fingerprint_logical,
    }
}
