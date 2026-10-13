use crate::refactor_command::models::RefactorDiagnostic;
use crate::refactoring::models::{FileChange, RefactorOperation, RefactorPlan, RefactorRequest};

/// A model rename plan whose file keeps its folder.
pub(super) fn rename_plan(old_path: &str, new_name: &str) -> RefactorPlan {
    let (folder, file) = old_path.rsplit_once('/').unwrap_or(("", old_path));
    RefactorPlan {
        request: RefactorRequest {
            operation: RefactorOperation::RenameModel,
            model_name: file.trim_end_matches(".sql").to_owned(),
            new_name: new_name.to_owned(),
            column_name: None,
            destination: None,
            cascade: false,
        },
        changes: vec![FileChange {
            path: format!("{folder}/{new_name}.sql"),
            original_path: old_path.to_owned(),
            edits: Vec::new(),
        }],
        manual: Vec::new(),
        blocking: Vec::new(),
        migrations: Vec::new(),
        renamed_columns: Vec::new(),
        help: None,
    }
}

/// One compile error per rule code, reported on `path`.
pub(super) fn rule_diagnostics(codes: &[&str], path: &str) -> Vec<RefactorDiagnostic> {
    codes
        .iter()
        .map(|code| RefactorDiagnostic {
            code: (*code).to_owned(),
            message: format!("{code} failed"),
            path: Some(path.to_owned()),
            line: Some(1),
        })
        .collect()
}
