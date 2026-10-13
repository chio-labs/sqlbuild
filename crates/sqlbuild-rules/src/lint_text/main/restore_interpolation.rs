//! `restore_interpolation`: sentinels swapped back to the text they stand in for.

use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::InterpolationSite;

/// Swap each sentinel, matched case-insensitively, back to its original text exactly once.
pub fn restore_interpolation(
    fixed: &str,
    sites: &[InterpolationSite],
) -> Result<String, LintTextError> {
    let mut restored: String = fixed.to_string();
    for site in sites {
        let needle: String = site.sentinel.to_ascii_lowercase();
        let folded: String = restored.to_ascii_lowercase();
        let occurrences: Vec<usize> = folded
            .match_indices(&needle)
            .map(|(index, _)| index)
            .collect();
        let [start] = occurrences[..] else {
            return Err(LintTextError::Restoration(format!(
                "formatted SQL contains {} occurrences of sentinel '{}' standing in for '{}'; expected exactly 1",
                occurrences.len(),
                site.sentinel,
                site.original_text
            )));
        };
        restored.replace_range(start..start + needle.len(), &site.original_text);
    }
    Ok(restored)
}
