//! The relationship facts of every SQL test block and scenario, and the faults of the rest.

use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::_helpers::cte_scan::{ScanText, expected_names};
use crate::relationship_names::_helpers::facts::{block_fact, scanned_names};
use crate::relationship_names::models::{
    RelationshipScan, RelationshipSource, ScenarioInput, TestFileInput,
};
use crate::scope_index::models::{RelationshipFact, ResourceIdentity, ResourceKind};

/// Each test block's and scenario's expected models, called and tested macros, or its fault.
#[must_use]
pub fn relationship_facts(
    files: &[TestFileInput<'_>],
    scenarios: &[ScenarioInput<'_>],
    syntax: &LexicalSyntax,
    python: PythonText,
) -> RelationshipScan {
    let mut scan: RelationshipScan = RelationshipScan::default();
    for (position, file) in files.iter().enumerate() {
        let names: Vec<Result<Vec<String>, String>> = match &file.stored {
            Some(stored) => stored.iter().cloned().map(Ok).collect(),
            None => scanned_names(file, syntax),
        };
        if file.stored.is_none() && names.iter().all(Result::is_ok) {
            let complete: Vec<Vec<String>> = names.iter().flatten().cloned().collect();
            scan.scanned_files.push((position, complete));
        }
        for (block, names) in file.blocks.iter().zip(names) {
            match block_fact(block, names, file.relative_path, (syntax, python)) {
                Ok(fact) => scan.facts.push(fact),
                Err(message) => scan.faults.push((file.relative_path.to_owned(), message)),
            }
        }
    }
    for scenario in scenarios {
        let text: ScanText<'_> = ScanText {
            sql: scenario.sql,
            file: scenario.relative_path,
            source: RelationshipSource::Scenario,
        };
        match expected_names(&text, syntax) {
            Ok(expected_models) => scan.facts.push(RelationshipFact {
                resource: ResourceIdentity {
                    kind: ResourceKind::Scenario,
                    name: scenario.name.to_owned(),
                },
                expected_models,
                called_macros: Vec::new(),
                tested_macros: Vec::new(),
            }),
            Err(message) => scan
                .faults
                .push((scenario.relative_path.to_owned(), message)),
        }
    }
    scan
}
