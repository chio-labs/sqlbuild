//! `test_evidence`: the public-harness cases that statically exercise one custom rule.

use std::collections::BTreeSet;
use std::path::Path;

use crate::rule_evidence::_helpers::evidence::{file_evidence, is_test_file, python_files};
use crate::rule_evidence::_helpers::paths::module_names;
use crate::rule_evidence::constants::TESTS_DIRECTORY_NAME;
use crate::rule_evidence::models::{RuleTarget, RuleTestEvidence};

/// Sorted harness cases under `tests/` naming the rule; `None` when its source is outside `root`.
pub fn test_evidence(
    (source_path, check_name): (&Path, &str),
    (project_dir, root): (&Path, &Path),
    python_version: (u8, u8),
) -> Option<Vec<RuleTestEvidence>> {
    let target = RuleTarget {
        modules: module_names(source_path, project_dir, root)?
            .into_iter()
            .collect(),
        check_name,
    };
    let mut evidence: BTreeSet<RuleTestEvidence> = BTreeSet::new();
    for path in python_files(&project_dir.join(TESTS_DIRECTORY_NAME)) {
        if !is_test_file(&path) {
            continue;
        }
        let relative: String = path
            .strip_prefix(project_dir)
            .unwrap_or(&path)
            .to_string_lossy()
            .into_owned();
        evidence.extend(file_evidence(&path, (&relative, &target), python_version));
    }
    Some(evidence.into_iter().collect())
}
