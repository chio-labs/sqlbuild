//! `newest_fingerprint`: the latest model fingerprint that built a relation or carries a name.

use crate::events::_helpers::relations::{newest_index, relations_match};
use crate::events::models::{EventRelation, FingerprintKey};

/// The newest fingerprint that built `target`, else the newest named `model_name`; the first wins ties.
#[must_use]
pub fn newest_fingerprint(
    fingerprints: &[FingerprintKey],
    target: Option<&EventRelation>,
    model_name: Option<&str>,
) -> Option<usize> {
    if let Some(target) = target {
        let built: Option<usize> = newest_index(
            fingerprints
                .iter()
                .enumerate()
                .filter(|(_, fingerprint)| {
                    fingerprint
                        .target
                        .as_ref()
                        .is_some_and(|built| relations_match(target, built))
                })
                .map(|(index, fingerprint)| (index, &fingerprint.order)),
        );
        if built.is_some() {
            return built;
        }
    }
    let model_name: &str = model_name?;
    newest_index(
        fingerprints
            .iter()
            .enumerate()
            .filter(|(_, fingerprint)| fingerprint.node_name == model_name)
            .map(|(index, fingerprint)| (index, &fingerprint.order)),
    )
}
