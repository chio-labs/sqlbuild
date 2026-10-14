use crate::lint_text::_helpers::sites::{DEPENDENCY_SITE_PATTERN, KEYED_RELATION_SITE_PATTERN};
use crate::lint_text::models::{DependencySites, InterpolationSite};

/// Derive dependency sentinels and stable relation identities from interpolation sites.
pub fn dependency_sites(sites: &[InterpolationSite]) -> Result<DependencySites, regex::Error> {
    let dependency = DEPENDENCY_SITE_PATTERN.as_ref().map_err(Clone::clone)?;
    let keyed_relation = KEYED_RELATION_SITE_PATTERN.as_ref().map_err(Clone::clone)?;
    let mut result = DependencySites::default();
    for site in sites {
        if dependency.is_match(&site.original_text) {
            result.identifiers.push(site.sentinel.clone());
        }
        if let Some(captures) = keyed_relation.captures(&site.original_text) {
            result.relations.push((
                site.sentinel.clone(),
                format!("{}:{}", captures[1].to_lowercase(), &captures[2]),
            ));
        }
    }
    Ok(result)
}
