use std::collections::HashSet;
use std::path::PathBuf;

use crate::artifacts::main::remove_stale_unless_unchanged::remove_stale_unless_unchanged;
use crate::artifacts::tests::helpers::{place, tree_files};
use crate::artifacts::tests::test_types::StampedTreeTestCase;

const MANAGED: [&str; 3] = [
    "models/orders.sql",
    "models/marts/customers.sql",
    "tests/t.sql",
];

#[test]
fn given_stamped_tree_when_cleaning_again_then_only_changed_trees_are_walked() {
    let test_cases = [
        StampedTreeTestCase {
            description: "nothing changed",
            change: |_| {},
            managed_after: &MANAGED,
            racy_window_ns: 0,
            expected_stamped: true,
            expected_removed: 0,
            expected_files: &[
                "models/marts/customers.sql",
                "models/orders.sql",
                "tests/t.sql",
            ],
        },
        StampedTreeTestCase {
            description: "a stale file added to a stamped folder",
            change: |root| place(&root.join("compiled/models/marts/old.sql"), b"select 0\n"),
            managed_after: &MANAGED,
            racy_window_ns: 0,
            expected_stamped: true,
            expected_removed: 1,
            expected_files: &[
                "models/marts/customers.sql",
                "models/orders.sql",
                "tests/t.sql",
            ],
        },
        StampedTreeTestCase {
            description: "a stale file in a new folder",
            change: |root| place(&root.join("compiled/models/new/old.sql"), b"select 0\n"),
            managed_after: &MANAGED,
            racy_window_ns: 0,
            expected_stamped: true,
            expected_removed: 1,
            expected_files: &[
                "models/marts/customers.sql",
                "models/orders.sql",
                "tests/t.sql",
            ],
        },
        StampedTreeTestCase {
            description: "a managed file no longer managed",
            change: |_| {},
            managed_after: &["models/orders.sql", "models/marts/customers.sql"],
            racy_window_ns: 0,
            expected_stamped: true,
            expected_removed: 1,
            expected_files: &["models/marts/customers.sql", "models/orders.sql"],
        },
        StampedTreeTestCase {
            description: "the stamp file damaged",
            change: |root| {
                std::fs::write(root.join("cache/compiled-tree.bin"), b"garbage").expect("damaged");
                place(&root.join("compiled/models/old.sql"), b"select 0\n");
            },
            managed_after: &MANAGED,
            racy_window_ns: 0,
            expected_stamped: true,
            expected_removed: 1,
            expected_files: &[
                "models/marts/customers.sql",
                "models/orders.sql",
                "tests/t.sql",
            ],
        },
        StampedTreeTestCase {
            description: "folders inside the racy window",
            change: |root| place(&root.join("compiled/models/marts/old.sql"), b"select 0\n"),
            managed_after: &MANAGED,
            racy_window_ns: i64::MAX / 2,
            expected_stamped: false,
            expected_removed: 1,
            expected_files: &[
                "models/marts/customers.sql",
                "models/orders.sql",
                "tests/t.sql",
            ],
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("target folder");
        let compiled: PathBuf = folder.path().join("compiled");
        let stamp: PathBuf = folder.path().join("cache/compiled-tree.bin");
        for path in MANAGED {
            place(&compiled.join(path), b"select 1\n");
        }
        place(&compiled.join("models/stale.sql"), b"select 0\n");
        let first: HashSet<PathBuf> = MANAGED.iter().map(|path| compiled.join(path)).collect();
        let removed =
            remove_stale_unless_unchanged(&compiled, &first, &stamp, test_case.racy_window_ns)
                .expect("first pass");
        let stamped: bool = stamp.is_file();
        std::thread::sleep(std::time::Duration::from_millis(30));
        (test_case.change)(folder.path());
        let second: HashSet<PathBuf> = test_case
            .managed_after
            .iter()
            .map(|path| compiled.join(path))
            .collect();

        let removed_again =
            remove_stale_unless_unchanged(&compiled, &second, &stamp, test_case.racy_window_ns)
                .expect("second pass");

        assert_eq!(
            (removed, stamped),
            (1, test_case.expected_stamped),
            "{}: first pass",
            test_case.description
        );
        assert_eq!(
            (removed_again, tree_files(&compiled)),
            (
                test_case.expected_removed,
                test_case
                    .expected_files
                    .iter()
                    .map(|path| (*path).to_owned())
                    .collect::<Vec<String>>()
            ),
            "{}",
            test_case.description
        );
    }
}
