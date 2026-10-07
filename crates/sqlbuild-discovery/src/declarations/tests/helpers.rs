use crate::declarations::main::declaration_layout::declaration_layout;
use crate::declarations::models::{DeclarationFileFact, DeclarationGroup, DeclarationLayout};
use crate::declarations::tests::test_types::{FactRow, LayoutTestCase};
use crate::models::DiscoveryFailure;
use crate::tree::models::ProjectTree;
use std::fs;

type Outcome<T> = Result<Vec<T>, String>;

/// The case's layout as owned fact rows and group pairs, or the failure messages.
pub(super) fn layout_rows(
    test_case: &LayoutTestCase,
) -> (Outcome<OwnedFactRow>, Outcome<(String, String)>) {
    let project = tempfile::tempdir().expect("temporary project");
    for relative_path in test_case.files {
        let path = project.path().join(relative_path);
        fs::create_dir_all(path.parent().expect("parent directory")).expect("directories");
        fs::write(path, "").expect("file");
    }
    for relative_path in test_case.directories {
        fs::create_dir_all(project.path().join(relative_path)).expect("directory");
    }
    let layout: DeclarationLayout =
        declaration_layout(&ProjectTree::new(project.path())).expect("no deferral");
    (
        rows(layout.file_facts, fact_row),
        rows(layout.named_groups, group_pair),
    )
}

/// Expected fact rows in the owned shape `layout_rows` returns.
pub(super) fn owned_facts(
    expected: Result<&'static [FactRow], &'static str>,
) -> Outcome<OwnedFactRow> {
    expected
        .map(|facts| facts.iter().map(owned_fact).collect())
        .map_err(str::to_owned)
}

/// Expected group pairs in the owned shape `layout_rows` returns.
pub(super) fn owned_groups(
    expected: Result<&'static [(&'static str, &'static str)], &'static str>,
) -> Outcome<(String, String)> {
    expected
        .map(|groups| groups.iter().map(owned_group).collect())
        .map_err(str::to_owned)
}

fn owned_group(group: &(&str, &str)) -> (String, String) {
    (group.0.to_owned(), group.1.to_owned())
}

pub(super) type OwnedFactRow = (String, String, String, String, Option<String>, String);

fn rows<T, R>(outcome: Result<Vec<T>, DiscoveryFailure>, row: fn(T) -> R) -> Outcome<R> {
    outcome
        .map(|items| items.into_iter().map(row).collect())
        .map_err(|failure| failure.message)
}

fn fact_row(fact: DeclarationFileFact) -> OwnedFactRow {
    (
        fact.relative_path,
        fact.kind.as_str().to_owned(),
        fact.scope_kind.as_str().to_owned(),
        fact.ownership_root,
        fact.owning_path,
        fact.declaration_root,
    )
}

fn owned_fact(fact: &FactRow) -> OwnedFactRow {
    (
        fact.0.to_owned(),
        fact.1.to_owned(),
        fact.2.to_owned(),
        fact.3.to_owned(),
        fact.4.map(str::to_owned),
        fact.5.to_owned(),
    )
}

fn group_pair(group: DeclarationGroup) -> (String, String) {
    (group.root, group.directory)
}
