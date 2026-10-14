//! Executed SQL statements as runtime artifact text.

use std::path::Path;

use crate::scenario_command::constants::EXPECTATIONS_DIR;
use crate::scenario_command::models::{ExpectationSql, RuntimeArtifact};
use crate::text::main::python_isspace::python_isspace;

/// One statement ending in `;`, or unchanged when it is blank.
pub(crate) fn terminated(statement: &str) -> String {
    let stripped: &str = statement.trim_end_matches(python_isspace);
    if stripped.is_empty() {
        return statement.to_owned();
    }
    if stripped.ends_with(';') {
        return stripped.to_owned();
    }
    format!("{stripped};")
}

/// Statements joined by blank lines, each terminated.
pub(crate) fn statements_text(statements: &[String]) -> String {
    statements
        .iter()
        .map(|statement| terminated(statement))
        .collect::<Vec<String>>()
        .join("\n\n")
}

/// The artifact, unless its statements render to no text.
pub(crate) fn statements_artifact(
    relative_path: &Path,
    statements: &[String],
) -> Option<RuntimeArtifact> {
    let sql: String = statements_text(statements);
    if sql.is_empty() {
        return None;
    }
    Some(RuntimeArtifact {
        relative_path: relative_path.to_path_buf(),
        sql,
    })
}

/// The comparison SQL of each expected model, then the count and sample SQL of each assertion.
pub(crate) fn expectation_artifacts(expectations: &ExpectationSql) -> Vec<RuntimeArtifact> {
    let root: &Path = Path::new(EXPECTATIONS_DIR);
    let mut artifacts: Vec<RuntimeArtifact> = Vec::new();
    for (model_name, sql) in &expectations.expected {
        artifacts.push(RuntimeArtifact {
            relative_path: root.join(format!("expected__{model_name}.sql")),
            sql: sql.clone(),
        });
    }
    for (name, sql) in &expectations.assertions {
        artifacts.push(RuntimeArtifact {
            relative_path: root.join(format!("assertion__{name}.sql")),
            sql: format!(
                "SELECT COUNT(*) FROM ({sql}) AS __scenario_assertion_failures;\n\n\
                 SELECT * FROM ({sql}) AS __scenario_assertion_failures\nLIMIT 10;"
            ),
        });
    }
    artifacts
}
