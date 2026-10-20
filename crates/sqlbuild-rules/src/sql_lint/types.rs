use crate::lint_text::models::InterpolationSite;

/// Lint text with sentinels, its interpolation sites and the CTEs interpolation references.
pub type PreparedSql = (String, Vec<InterpolationSite>, Vec<String>);
