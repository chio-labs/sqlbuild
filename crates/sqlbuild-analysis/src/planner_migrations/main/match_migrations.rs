//! Conservative one-to-one migration matching with rename-map propagation.

use crate::planner_migrations::_helpers::decisions::matching::{contested_details, match_pass};
use crate::planner_migrations::models::{MigrationCandidate, MigrationMatches};
use std::collections::{BTreeMap, BTreeSet};

/// Match ordered models, rejecting every origin claimed by several destinations.
pub fn match_migrations<E>(
    names: &[String],
    seeds: &[BTreeMap<String, String>],
    candidates: &[MigrationCandidate],
    mut fingerprints: impl FnMut(&str, &[BTreeMap<String, String>]) -> Result<Vec<String>, E>,
) -> Result<MigrationMatches, E> {
    let mut blocked: BTreeSet<String> = BTreeSet::new();
    let mut ambiguous: BTreeMap<String, String> = BTreeMap::new();
    if candidates.is_empty() {
        return Ok(MigrationMatches {
            variants: seeds.to_vec(),
            matches: Vec::new(),
            ambiguous,
        });
    }
    for _ in 0..=candidates.len() {
        let pass = match_pass((names, candidates), seeds, &blocked, &mut fingerprints)?;
        ambiguous.extend(pass.result.ambiguous);
        if pass.contested.is_empty() {
            return Ok(MigrationMatches {
                variants: pass.result.variants,
                matches: pass.result.matches,
                ambiguous,
            });
        }
        let (origins, details) = contested_details(pass.contested);
        blocked.extend(origins);
        ambiguous.extend(details);
    }
    Ok(MigrationMatches {
        variants: seeds.to_vec(),
        matches: Vec::new(),
        ambiguous,
    })
}
