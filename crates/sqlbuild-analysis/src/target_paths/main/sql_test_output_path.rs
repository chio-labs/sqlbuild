//! The readable, filesystem-safe path of one SQL test artifact.

use sha2::{Digest, Sha256};

use crate::target_paths::_helpers::path_text::{truncate_utf8, with_suffix};
use crate::target_paths::constants::{
    CHAIN_DIGEST_LENGTH, CHAIN_DIR, CHAIN_EDGE_NAME_BYTES, MAX_CHAIN_COMPONENT_BYTES,
    SQL_FILE_SUFFIX,
};
use crate::target_paths::models::SqlTestPathFacts;

fn chain_folder(name: &str, model_names: &[String]) -> String {
    let mut unique: Vec<&str> = model_names.iter().map(String::as_str).collect();
    unique.sort_unstable();
    unique.dedup();
    match unique.as_slice() {
        [] => return name.to_owned(),
        [only] => return (*only).to_owned(),
        _ => {}
    }
    let chain: String = unique.join("__");
    if chain.len() <= MAX_CHAIN_COMPONENT_BYTES {
        return format!("{CHAIN_DIR}/{chain}");
    }
    let digest: String = Sha256::digest(chain.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()[..CHAIN_DIGEST_LENGTH]
        .to_owned();
    format!(
        "{CHAIN_DIR}/{}__{}__{digest}",
        truncate_utf8(unique[0], CHAIN_EDGE_NAME_BYTES),
        truncate_utf8(unique[unique.len() - 1], CHAIN_EDGE_NAME_BYTES)
    )
}

/// The test's chain folder and name, or its source stem and case for an expanded case.
#[must_use]
pub fn sql_test_output_path(facts: &SqlTestPathFacts) -> String {
    match (&facts.case_name, &facts.source_path) {
        (Some(case_name), Some(source_path)) => format!(
            "{}/block_{}__{case_name}{SQL_FILE_SUFFIX}",
            with_suffix(source_path, ""),
            facts
                .block_index
                .map_or_else(|| "None".to_owned(), |index| index.to_string())
        ),
        _ => format!(
            "{}/{}{SQL_FILE_SUFFIX}",
            chain_folder(&facts.name, &facts.model_names),
            facts.name
        ),
    }
}
