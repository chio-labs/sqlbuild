//! Python's `build_seed_inputs` pairing of seed declarations with seed CSV files.

use std::collections::HashMap;

/// Each declaration's file index by stem (a later stem wins), or the first unmatched declaration.
pub fn pair_seed_declarations(
    declarations: &[String],
    stems: &[String],
) -> Result<Vec<usize>, usize> {
    let files: HashMap<&str, usize> = stems
        .iter()
        .enumerate()
        .map(|(index, stem)| (stem.as_str(), index))
        .collect();
    let mut pairs: Vec<usize> = Vec::with_capacity(declarations.len());
    for (index, name) in declarations.iter().enumerate() {
        pairs.push(*files.get(name.as_str()).ok_or(index)?);
    }
    Ok(pairs)
}
