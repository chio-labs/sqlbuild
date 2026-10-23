//! Priority of reasons to omit old-name compatibility steps.

/// Explain why a migration should not create its compatibility view.
pub fn old_name_skip_reason(
    retention: bool,
    reuser: Option<&str>,
    compatibility_view: bool,
    tracked: Option<bool>,
) -> Option<String> {
    if !retention {
        return Some("old_name_view false".to_owned());
    }
    if let Some(name) = reuser {
        return Some(format!("name reused by model:{name}"));
    }
    if compatibility_view {
        return Some("old name is a compatibility view".to_owned());
    }
    if tracked == Some(false) {
        return Some("not built by SQLBuild".to_owned());
    }
    None
}
