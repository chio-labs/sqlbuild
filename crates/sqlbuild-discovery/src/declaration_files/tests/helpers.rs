use crate::declaration_files::main::discover_declaration_collection::discover_declaration_collection;
use crate::declaration_files::main::parse_declaration_text::parse_declaration_text;
use crate::declaration_files::main::retained_collection::retained_collection;
use crate::declaration_files::models::{
    CollectionKind, CollectionRequest, DeclarationCollection, DeclarationFileOptions,
    DiscoverySession,
};
use crate::models::ProjectRoot;
use crate::tree::models::ProjectTree;
use sqlbuild_core::text::main::python_text::python_text;
use std::fs;
use std::sync::Arc;

pub(super) const FILE_PATH: &str = "/project/declarations/orders.sql";
const FUNCTION_KEYS: [&str; 3] = ["arguments", "description", "returns"];
const AUDIT_KEYS: [&str; 7] = [
    "always_run",
    "evaluation",
    "name",
    "sample_unit",
    "severity",
    "sql_analysis",
    "value",
];

fn owned(keys: &[&str]) -> Vec<String> {
    keys.iter().map(|key| (*key).to_owned()).collect()
}

fn options() -> DeclarationFileOptions {
    DeclarationFileOptions {
        function_keys: owned(&FUNCTION_KEYS),
        audit_keys: owned(&AUDIT_KEYS),
        hook_keys: owned(&["description"]),
        python: python_text((3, 12), "15.0.0").expect("Python 3.12 is supported"),
    }
}

/// The debug text of `contents` parsed as a `kind` file named `FILE_PATH` and hook `orders`.
pub(super) fn parsed_debug(kind: CollectionKind, contents: &str) -> String {
    format!(
        "{:?}",
        parse_declaration_text(kind, (FILE_PATH, "orders"), contents.to_owned(), &options())
    )
}

/// Each collection's file count, the layouts walked and whether re-reads reuse the first read.
pub(super) fn session_reads(
    files: &[(&str, &str)],
    requests: &[CollectionRequest],
) -> (Vec<usize>, usize, bool) {
    let project = tempfile::tempdir().expect("temporary project");
    for (relative_path, contents) in files {
        let path = project.path().join(relative_path);
        fs::create_dir_all(path.parent().expect("parent directory")).expect("directories");
        fs::write(path, contents).expect("file");
    }
    let session = DiscoverySession::new(
        ProjectRoot {
            directory: project.path().to_path_buf(),
            display_prefix: project.path().display().to_string(),
        },
        options(),
    );
    let tree = ProjectTree::new(project.path());
    let read = |request: CollectionRequest| {
        retained_collection(&session, request, || {
            discover_declaration_collection(&session, &tree, request)
        })
    };
    let counts: Vec<usize> = requests
        .iter()
        .map(|request| collection_len(&read(*request)))
        .collect();
    let reused: bool = requests
        .iter()
        .all(|request| Arc::ptr_eq(&read(*request), &read(*request)));
    let layouts: usize = session.layouts.lock().expect("layouts").len();
    (counts, layouts, reused)
}

fn collection_len(collection: &DeclarationCollection) -> usize {
    format!("{collection:?}").matches("ScopedFile {").count()
}

/// The debug text of the failure a header nested too deeply reports at `(statement, line)`.
pub(super) fn nesting_failure_debug((statement, line): (&str, usize)) -> String {
    format!(
        "Some(Failed(DiscoveryFailure {{ kind: {}, message: \"{statement}(...) in '{FILE_PATH}:{line}' \
         contains invalid SQLBuild header syntax: values nest deeper than 256 levels\", help: \
         Some(\"flatten the value so it nests at most 256 levels deep\") }}))",
        match statement {
            "CONSTANT" => "Declaration",
            "HOOK" => "SqlHook",
            "AUDIT" => "SqlAudit",
            _ => "ModelSql",
        }
    )
}
