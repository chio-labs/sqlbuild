//! Recognize persisted scenario relation names.

/// Parse a scenario artifact name using the original fixed hash length and accepted kinds.
pub fn parse_artifact_name(name: &str) -> Option<(&str, &str, &str)> {
    let (hash, rest) = name.strip_prefix("__sqb_")?.split_once("__")?;
    if hash.len() != crate::planner_scenario::constants::HASH_LENGTH
        || !hash
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return None;
    }
    let (kind, logical) = rest.split_once("__")?;
    if !["model", "source", "ref", "seed", "dbt_ref"].contains(&kind)
        || logical.is_empty()
        || logical.contains('\n')
    {
        return None;
    }
    Some((hash, kind, logical))
}
