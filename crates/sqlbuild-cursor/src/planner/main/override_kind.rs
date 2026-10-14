//! Untyped override selection and mixed-model diagnostics.

use std::collections::BTreeMap;

/// Resolve the selected type or return the mixed-selection diagnostic.
pub fn override_kind(
    models: &[(String, String)],
    integer_literals: bool,
) -> Result<String, String> {
    let mut grouped: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for (name, kind) in models {
        grouped.entry(kind).or_default().push(name);
    }
    if grouped.len() <= 1 {
        return Ok(grouped
            .keys()
            .next()
            .copied()
            .unwrap_or(if integer_literals {
                "integer"
            } else {
                "timestamp"
            })
            .into());
    }
    let mut descriptions: Vec<String> = Vec::new();
    for (kind, mut names) in grouped {
        names.sort_unstable();
        let shown = names.iter().take(3).copied().collect::<Vec<_>>().join(", ");
        let hidden = names.len().saturating_sub(3);
        let names = if hidden > 0 {
            format!("{shown} and {hidden} more")
        } else {
            shown
        };
        descriptions.push(format!("{kind} cursor models ({names})"));
    }
    Err(format!(
        "--start-cursor and --end-cursor need one cursor type, but the selection mixes {}",
        descriptions.join(" and ")
    ))
}
