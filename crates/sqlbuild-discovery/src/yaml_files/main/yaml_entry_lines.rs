//! The 1-based line of each outermost `- name:` entry of an authored YAML declaration file.

use crate::yaml_files::_helpers::entry_names::{entry_names, entry_prefix};

/// Every entry name with the line of its least-indented entry, earliest line on ties.
#[must_use]
pub fn yaml_entry_lines(contents: &str) -> Vec<(String, usize)> {
    let mut best: Vec<(String, usize, usize)> = Vec::new();
    let mut positions: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for (index, line) in contents.lines().enumerate() {
        let characters: Vec<char> = line.chars().collect();
        let Some((indent, value_start)) = entry_prefix(&characters) else {
            continue;
        };
        for name in entry_names(&characters[value_start..]) {
            match positions.get(&name) {
                Some(position) if indent < best[*position].1 => {
                    best[*position] = (name, indent, index + 1);
                }
                Some(_) => {}
                None => {
                    positions.insert(name.clone(), best.len());
                    best.push((name, indent, index + 1));
                }
            }
        }
    }
    best.into_iter()
        .map(|(name, _, line)| (name, line))
        .collect()
}
