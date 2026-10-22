use std::path::{Path, PathBuf};

use crate::git_revisions::main::export_git_tree::export_git_tree;
use crate::git_revisions::main::resolve_git_base::resolve_git_base;
use crate::git_revisions::main::resolve_since_reference::resolve_since_reference;
use crate::git_revisions::main::short_commit::short_commit;
use crate::git_revisions::models::GitBase;
use crate::git_revisions::tests::helpers::{git, project_repository, scratch_directory, write};
use crate::git_revisions::tests::test_types::{GitBaseFailureTestCase, SinceReferenceTestCase};

#[test]
fn given_since_value_when_resolving_then_reads_base_alias_from_config() {
    let test_cases = [
        SinceReferenceTestCase {
            description: "a plain ref is used as given",
            value: "origin/main",
            configured: Some("origin/release"),
            expected: Ok("origin/main"),
        },
        SinceReferenceTestCase {
            description: "@base reads the configured base ref",
            value: "@base",
            configured: Some("origin/main"),
            expected: Ok("origin/main"),
        },
        SinceReferenceTestCase {
            description: "@base without a configured base ref fails",
            value: "@base",
            configured: None,
            expected: Err("C485"),
        },
        SinceReferenceTestCase {
            description: "@base with a blank base ref fails",
            value: "@base",
            configured: Some("  "),
            expected: Err("C485"),
        },
    ];
    for test_case in test_cases {
        let resolved = resolve_since_reference(test_case.value, test_case.configured);

        assert_eq!(
            resolved.as_deref().map_err(|error| error.code),
            test_case.expected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_project_in_subdirectory_when_resolving_base_then_returns_merge_base_and_prefix() {
    let (root, main) = project_repository();

    let base: GitBase = resolve_git_base(&root.join("warehouse"), "main").expect("main resolves");

    assert_eq!(base.merge_base, main);
    assert_eq!(base.project_prefix, "warehouse/");
    assert_eq!(base.reference, "main");
    assert_eq!(short_commit(&base.merge_base).len(), 10);
}

#[test]
fn given_unresolvable_ref_when_resolving_base_then_fails_with_code() {
    let (root, _) = project_repository();
    git(&root, &["checkout", "--quiet", "--orphan", "unrelated"]);
    git(&root, &["commit", "--quiet", "-m", "unrelated"]);
    git(&root, &["checkout", "--quiet", "feature"]);
    let test_cases = [
        GitBaseFailureTestCase {
            description: "a missing ref",
            reference: "origin/missing",
            expected_code: "C481",
            expected_message_fragment: "'origin/missing' does not name a commit",
        },
        GitBaseFailureTestCase {
            description: "a ref without shared history",
            reference: "unrelated",
            expected_code: "C482",
            expected_message_fragment: "'unrelated' and HEAD",
        },
    ];
    for test_case in test_cases {
        let error = resolve_git_base(&root.join("warehouse"), test_case.reference)
            .expect_err(test_case.description);

        assert_eq!(
            error.code, test_case.expected_code,
            "{}",
            test_case.description
        );
        assert!(
            error.message.contains(test_case.expected_message_fragment),
            "{}: {}",
            test_case.description,
            error.message
        );
    }
}

#[test]
fn given_directory_outside_repository_when_resolving_base_then_fails_with_code() {
    let directory: PathBuf = scratch_directory("plain");

    let error = resolve_git_base(&directory, "main").expect_err("not a repository");

    assert_eq!(error.code, "C480");
}

#[test]
fn given_shallow_clone_without_shared_history_when_resolving_base_then_asks_for_depth() {
    let (root, _) = project_repository();
    let clone: PathBuf = scratch_directory("shallow");
    git(
        &clone,
        &[
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--branch",
            "feature",
            "--no-single-branch",
            &format!("file://{}", root.display()),
            "checkout",
        ],
    );
    let checkout: PathBuf = clone.join("checkout");
    git(
        &checkout,
        &["fetch", "--quiet", "--depth", "1", "origin", "main"],
    );

    let error = resolve_git_base(&checkout.join("warehouse"), "origin/main")
        .expect_err("the merge base is outside the shallow history");

    assert_eq!(error.code, "C482");
    assert!(error.message.contains("shallow clone"), "{}", error.message);
    assert!(error.help.contains("--unshallow"), "{}", error.help);
}

fn read(path: &Path) -> Option<String> {
    std::fs::read_to_string(path).ok()
}

#[test]
fn given_merge_base_when_exporting_tree_then_writes_base_files_and_leaves_checkout_alone() {
    let (root, _) = project_repository();
    write(
        &root,
        "warehouse/models/orders.sql",
        "SELECT 3 AS order_id\n",
    );
    let status_before: String = git(&root, &["status", "--porcelain"]);
    let base: GitBase = resolve_git_base(&root.join("warehouse"), "main").expect("main resolves");
    let destination: PathBuf = scratch_directory("export").join("base");

    let exported: bool = export_git_tree(&base, &destination).expect("the tree exports");

    assert!(exported);
    assert_eq!(
        read(&destination.join("models/orders.sql")).as_deref(),
        Some("SELECT 1 AS order_id\n")
    );
    assert_eq!(read(&destination.join("models/customers.sql")), None);
    assert_eq!(
        read(&root.join("warehouse/models/orders.sql")).as_deref(),
        Some("SELECT 3 AS order_id\n")
    );
    assert_eq!(git(&root, &["status", "--porcelain"]), status_before);
    assert!(!destination.with_extension("index").exists());
}

#[test]
fn given_project_absent_at_merge_base_when_exporting_tree_then_reports_no_project() {
    let (root, main) = project_repository();
    write(
        &root,
        "billing/sqlbuild_project.toml",
        "name = \"billing\"\n",
    );
    git(&root, &["add", "."]);
    git(&root, &["commit", "--quiet", "-m", "billing"]);
    let base: GitBase = GitBase {
        reference: "main".to_owned(),
        merge_base: main,
        repository_root: root.clone(),
        project_prefix: "billing/".to_owned(),
    };

    let exported: bool = export_git_tree(&base, &scratch_directory("absent").join("base"))
        .expect("an absent tree is not an error");

    assert!(!exported);
}
