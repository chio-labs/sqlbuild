use std::collections::BTreeSet;

use crate::fix_verification::constants::{
    COLUMNS_CHANGED, COLUMNS_UNKNOWN, DEPENDENCIES_CHANGED, LINEAGE_CHANGED, NEW_DIAGNOSTICS,
};
use crate::fix_verification::models::{DiagnosticComparison, FixComparisonResult, ModelComparison};

/// Attribute changed compile invariants while allowing edited owners to lose diagnostics.
pub fn compare(
    same_models: bool,
    models: &[ModelComparison],
    diagnostics: &[DiagnosticComparison],
) -> FixComparisonResult {
    let mut result = FixComparisonResult::default();
    if !same_models {
        result.unattributed = true;
        return result;
    }
    for model in models {
        let reason = if model.edited && !model.columns_known {
            Some(COLUMNS_UNKNOWN)
        } else if !model.columns_equal {
            Some(COLUMNS_CHANGED)
        } else if !model.dependencies_equal {
            Some(DEPENDENCIES_CHANGED)
        } else if !model.lineage_equal {
            Some(LINEAGE_CHANGED)
        } else {
            None
        };
        if let Some(reason) = reason {
            if model.edited {
                result
                    .failing
                    .entry(model.owner)
                    .or_insert_with(|| reason.to_owned());
            } else {
                result.unattributed = true;
            }
        }
    }
    for diagnostic in diagnostics {
        if !diagnostic.edited {
            if diagnostic.before != diagnostic.after {
                result.unattributed = true;
            }
            continue;
        }
        let codes: BTreeSet<&str> = diagnostic
            .after
            .iter()
            .filter_map(|(identity, count)| {
                (*count > *diagnostic.before.get(identity).unwrap_or(&0))
                    .then_some(identity.0.as_str())
            })
            .collect();
        if !codes.is_empty() {
            result.failing.entry(diagnostic.owner).or_insert_with(|| {
                format!(
                    "{NEW_DIAGNOSTICS}{}",
                    codes.into_iter().collect::<Vec<_>>().join(", ")
                )
            });
        }
    }
    result
}
