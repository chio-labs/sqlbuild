//! Ordered options and explanations for contested migration origins.

use crate::planner_migrations::models::{MigrationCandidate, MigrationMatchPass, MigrationMatches};
use std::collections::{BTreeMap, BTreeSet};

fn match_options(
    hashes: &[String],
    indexed: (&[MigrationCandidate], &BTreeMap<&str, Vec<usize>>),
    blocked: &BTreeSet<String>,
) -> Vec<usize> {
    let (candidates, by_fingerprint) = indexed;
    let mut options: Vec<usize> = Vec::new();
    for hash in hashes {
        for index in by_fingerprint
            .get(hash.as_str())
            .into_iter()
            .flatten()
            .copied()
        {
            let candidate = &candidates[index];
            if blocked.contains(&candidate.name) {
                continue;
            }
            if let Some(existing) = options
                .iter_mut()
                .find(|previous| candidates[**previous].name == candidate.name)
            {
                *existing = index;
            } else {
                options.push(index);
            }
        }
    }
    options
}

pub(crate) fn contested_details(
    contested: Vec<(String, Vec<String>)>,
) -> (BTreeSet<String>, BTreeMap<String, String>) {
    let mut blocked: BTreeSet<String> = BTreeSet::new();
    let mut ambiguous: BTreeMap<String, String> = BTreeMap::new();
    for (origin, mut names) in contested {
        blocked.insert(origin.clone());
        names.sort();
        for name in &names {
            let others: Vec<String> = names
                .iter()
                .filter(|other| *other != name)
                .map(|other| format!("'{other}'"))
                .collect();
            ambiguous.insert(
                name.clone(),
                format!(
                    "earlier model '{origin}', which also matches {}",
                    others.join(", ")
                ),
            );
        }
    }
    (blocked, ambiguous)
}

fn multiple_origins(options: &[usize], candidates: &[MigrationCandidate]) -> String {
    let mut names: Vec<&str> = options
        .iter()
        .map(|index| candidates[*index].name.as_str())
        .collect();
    names.sort_unstable();
    format!("several earlier models ({})", names.join(", "))
}

pub(crate) fn match_pass<E>(
    inputs: (&[String], &[MigrationCandidate]),
    seeds: &[BTreeMap<String, String>],
    blocked: &BTreeSet<String>,
    mut fingerprints: impl FnMut(&str, &[BTreeMap<String, String>]) -> Result<Vec<String>, E>,
) -> Result<MigrationMatchPass, E> {
    let (names, candidates) = inputs;
    let index = candidate_index(candidates);
    let mut variants = seeds.to_vec();
    let mut matches: Vec<(String, usize)> = Vec::new();
    let mut ambiguous: BTreeMap<String, String> = BTreeMap::new();
    let mut claims: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for name in names {
        let hashes = fingerprints(name, &variants)?;
        let options = match_options(&hashes, (candidates, &index), blocked);
        if options.len() > 1 {
            ambiguous.insert(name.clone(), multiple_origins(&options, candidates));
        } else if let Some(index) = options.first() {
            let origin = &candidates[*index].name;
            for variant in &mut variants {
                variant.insert(name.clone(), origin.clone());
            }
            matches.push((name.clone(), *index));
            claims.entry(origin.clone()).or_default().push(name.clone());
        }
    }
    Ok(MigrationMatchPass {
        result: MigrationMatches {
            variants,
            matches,
            ambiguous,
        },
        contested: claims
            .into_iter()
            .filter(|(_, names)| names.len() > 1)
            .collect(),
    })
}

fn candidate_index(candidates: &[MigrationCandidate]) -> BTreeMap<&str, Vec<usize>> {
    let mut index: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
    for (position, candidate) in candidates.iter().enumerate() {
        index
            .entry(&candidate.fingerprint)
            .or_default()
            .push(position);
    }
    index
}
