use std::path::PathBuf;

use crate::git_revisions::main::export_git_tree::export_git_tree;
use crate::git_revisions::main::resolve_git_base::resolve_git_base;
use crate::git_revisions::main::resolve_since_reference::resolve_since_reference;
use crate::git_revisions::models::GitBase;
use crate::git_revisions::tests::helpers::{
    git, project_repository, read, scratch_directory, write,
};
use crate::git_revisions::tests::test_types::{
    AbsentProjectTestCase, ExportTreeTestCase, GitBaseFailureTestCase, GitBaseTestCase,
    SinceReferenceTestCase,
};

#[test]
fn given_since_value_when_resolving_then_reads_base_alias_from_config() {
    let test_cases = [
        SinceReferenceTestCase {
            description: "a plain ref is used as given",
            value: "origin/main",
            configured: Some("origin/release"),
            expected_reference: Ok("origin/main"),
        },
        SinceReferenceTestCase {
            description: "@base reads the configured base ref",
            value: "@base",
            configured: Some("origin/main"),
            expected_reference: Ok("origin/main"),
        },
        SinceReferenceTestCase {
            description: "@base without a configured base ref fails",
            value: "@base",
            configured: None,
            expected_reference: Err("C485"),
        },
        SinceReferenceTestCase {
            description: "@base with a blank base ref fails",
            value: "@base",
            configured: Some("  "),
            expected_reference: Err("C485"),
        },
    ];
    for test_case in test_cases {
        let resolved = resolve_since_reference(test_case.value, test_case.configured);

        assert_eq!(
            resolved.as_deref().map_err(|error| error.code),
            test_case.expected_reference,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_project_directory_when_resolving_base_then_returns_merge_base_and_prefix() {
    let (root, main) = project_repository();
    let test_cases = [
        GitBaseTestCase {
            description: "a project in a subdirectory",
            project_directory: "warehouse",
            reference: "main",
            expected_prefix: "warehouse/",
        },
        GitBaseTestCase {
            description: "a nested directory of the project",
            project_directory: "warehouse/models",
            reference: "main",
            expected_prefix: "warehouse/models/",
        },
    ];
    for test_case in test_cases {
        let base: GitBase =
            resolve_git_base(&root.join(test_case.project_directory), test_case.reference)
                .expect(test_case.description);

        assert_eq!(base.merge_base, main, "{}", test_case.description);
        assert_eq!(
            base.project_prefix, test_case.expected_prefix,
            "{}",
            test_case.description
        );
    }
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
            expected_help_fragment: "git fetch origin <branch>",
        },
        GitBaseFailureTestCase {
            description: "a ref without shared history",
            reference: "unrelated",
            expected_code: "C482",
            expected_message_fragment: "'unrelated' and HEAD",
            expected_help_fragment: "shares history with HEAD",
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
            error.message.contains(test_case.expected_message_fragment)
                && error.help.contains(test_case.expected_help_fragment),
            "{}: {} ({})",
            test_case.description,
            error.message,
            error.help
        );
    }
}

#[test]
fn given_directory_outside_repository_when_resolving_base_then_fails_with_code() {
    let directory: PathBuf = scratch_directory("plain");
    let test_cases = [GitBaseFailureTestCase {
        description: "a plain directory",
        reference: "main",
        expected_code: "C480",
        expected_message_fragment: "is not inside one",
        expected_help_fragment: "drop --since",
    }];
    for test_case in test_cases {
        let error =
            resolve_git_base(&directory, test_case.reference).expect_err(test_case.description);

        assert_eq!(
            error.code, test_case.expected_code,
            "{}",
            test_case.description
        );
        assert!(
            error.message.contains(test_case.expected_message_fragment)
                && error.help.contains(test_case.expected_help_fragment),
            "{}: {}",
            test_case.description,
            error.message
        );
    }
}

#[test]
fn given_shallow_clone_without_shared_history_when_resolving_base_then_asks_for_depth() {
    let (root, _) = project_repository();
    let clone: PathBuf = scratch_directory("shallow");
    let origin: String = format!("file://{}", root.display());
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
            &origin,
            "checkout",
        ],
    );
    let checkout: PathBuf = clone.join("checkout");
    git(
        &checkout,
        &["fetch", "--quiet", "--depth", "1", "origin", "main"],
    );
    let test_cases = [GitBaseFailureTestCase {
        description: "the merge base is outside the shallow history",
        reference: "origin/main",
        expected_code: "C482",
        expected_message_fragment: "shallow clone",
        expected_help_fragment: "--unshallow",
    }];
    for test_case in test_cases {
        let error = resolve_git_base(&checkout.join("warehouse"), test_case.reference)
            .expect_err(test_case.description);

        assert_eq!(
            error.code, test_case.expected_code,
            "{}",
            test_case.description
        );
        assert!(
            error.message.contains(test_case.expected_message_fragment)
                && error.help.contains(test_case.expected_help_fragment),
            "{}: {} ({})",
            test_case.description,
            error.message,
            error.help
        );
    }
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
    assert_eq!(git(&root, &["status", "--porcelain"]), status_before);
    let test_cases = [
        ExportTreeTestCase {
            description: "an edited model is exported as committed at the base",
            relative_path: "models/orders.sql",
            expected_exported: Some("SELECT 1 AS order_id\n"),
            expected_working_tree: Some("SELECT 3 AS order_id\n"),
        },
        ExportTreeTestCase {
            description: "a model added after the base is not exported",
            relative_path: "models/customers.sql",
            expected_exported: None,
            expected_working_tree: Some("SELECT 1 AS customer_id\n"),
        },
        ExportTreeTestCase {
            description: "the private index file is removed",
            relative_path: "../base.index",
            expected_exported: None,
            expected_working_tree: None,
        },
    ];
    for test_case in test_cases {
        let exported_text: Option<String> = read(&destination.join(test_case.relative_path));
        let working_text: Option<String> =
            read(&root.join("warehouse").join(test_case.relative_path));

        assert_eq!(
            exported_text.as_deref(),
            test_case.expected_exported,
            "{}",
            test_case.description
        );
        assert_eq!(
            working_text.as_deref(),
            test_case.expected_working_tree,
            "{}",
            test_case.description
        );
    }
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
    let test_cases = [
        AbsentProjectTestCase {
            description: "a project added after the base",
            project_prefix: "billing/",
            expected_exported: false,
        },
        AbsentProjectTestCase {
            description: "a project present at the base",
            project_prefix: "warehouse/",
            expected_exported: true,
        },
    ];
    for test_case in test_cases {
        let base: GitBase = GitBase {
            reference: "main".to_owned(),
            merge_base: main.clone(),
            repository_root: root.clone(),
            project_prefix: test_case.project_prefix.to_owned(),
        };

        let exported: bool = export_git_tree(&base, &scratch_directory("absent").join("base"))
            .expect(test_case.description);

        assert_eq!(
            exported, test_case.expected_exported,
            "{}",
            test_case.description
        );
    }
}
