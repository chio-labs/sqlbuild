//! Selectors packed into log lines.

/// Selectors joined by spaces into lines of at most `width` characters; longer ones stand alone.
#[must_use]
pub fn wrap_selectors(selectors: &[String], width: usize) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    let mut current: String = String::new();
    for selector in selectors {
        let candidate: String = if current.is_empty() {
            selector.clone()
        } else {
            format!("{current} {selector}")
        };
        if candidate.chars().count() <= width {
            current = candidate;
            continue;
        }
        if !current.is_empty() {
            lines.push(current);
        }
        current = selector.clone();
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
}
