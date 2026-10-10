use crate::project_reuse::_helpers::entry::{read_entry, write_entry};
use crate::project_reuse::_helpers::timings::{compile_timings_span, replace_compile_timings};
use crate::project_reuse::tests::helpers::{
    damage, slot_names, store_aged_slots, stored_inputs, stored_output,
};
use crate::project_reuse::tests::test_types::{
    EntryReadTestCase, NonUnicodeNameTestCase, SlotPruneTestCase, TimingsSpanTestCase,
};
use crate::project_snapshot::main::snapshot_project_files::snapshot_project_files;
use crate::project_snapshot::main::text_path::text_path;
use crate::project_snapshot::models::SnapshotRules;

#[test]
fn given_stored_compile_when_reading_then_only_an_intact_slot_round_trips() {
    let test_cases = [
        EntryReadTestCase {
            description: "intact slot",
            edit: |_| {},
            expected_read: true,
        },
        EntryReadTestCase {
            description: "damaged slot",
            edit: damage,
            expected_read: false,
        },
        EntryReadTestCase {
            description: "truncated slot",
            edit: |path| std::fs::write(path, b"SQBSTORE").expect("truncated"),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "missing slot",
            edit: |path| std::fs::remove_file(path).expect("removed"),
            expected_read: false,
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("reuse/slot.store");
        write_entry(&path, &stored_inputs(), &stored_output(), 8).expect("stored compile");
        (test_case.edit)(&path);

        let read = read_entry(&path);

        assert_eq!(
            read,
            test_case
                .expected_read
                .then(|| (stored_inputs(), stored_output())),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_more_slots_than_retained_when_storing_then_the_oldest_are_pruned() {
    let test_cases = [
        SlotPruneTestCase {
            description: "within the limit",
            slots: 2,
            max_entries: 8,
            expected_kept: &["slot0.store", "slot1.store"],
        },
        SlotPruneTestCase {
            description: "over the limit",
            slots: 4,
            max_entries: 2,
            expected_kept: &["slot2.store", "slot3.store"],
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let directory = folder.path().join("reuse");

        store_aged_slots(&directory, test_case.slots, test_case.max_entries);

        assert_eq!(
            slot_names(&directory),
            test_case.expected_kept,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_report_when_replaying_then_only_a_flat_top_level_timings_object_is_replaced() {
    let test_cases = [
        TimingsSpanTestCase {
            description: "flat timings object",
            stdout: "{\n  \"compile_timings\": {\n    \"total_ms\": 900\n  },\n  \"models\": []\n}\n",
            expected_replayed: Some(
                "{\n  \"compile_timings\": {\n    \"project_reuse_hits\": 1,\n    \"total_ms\": 4\n  },\n  \"models\": []\n}\n",
            ),
        },
        TimingsSpanTestCase {
            description: "nested timings object",
            stdout: "{\n  \"compile_timings\": {\n    \"phases\": {}\n  }\n}\n",
            expected_replayed: None,
        },
        TimingsSpanTestCase {
            description: "no timings object",
            stdout: "{\n  \"models\": []\n}\n",
            expected_replayed: None,
        },
    ];

    for test_case in test_cases {
        let timings = [
            ("project_reuse_hits".to_owned(), 1),
            ("total_ms".to_owned(), 4),
        ];

        let replayed = compile_timings_span(test_case.stdout)
            .and_then(|span| replace_compile_timings(test_case.stdout, span, &timings));

        assert_eq!(
            replayed.as_deref(),
            test_case.expected_replayed,
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_file_names_when_snapshotting_then_each_stamp_names_its_exact_file() {
    use std::os::unix::ffi::OsStrExt;

    let test_cases = [
        NonUnicodeNameTestCase {
            description: "unicode name",
            name: "orders_é.sql".as_bytes(),
            expected_escaped: false,
        },
        NonUnicodeNameTestCase {
            description: "name that is not UTF-8",
            name: b"orders_\xff.sql",
            expected_escaped: true,
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("project folder");
        let name = std::ffi::OsStr::from_bytes(test_case.name);
        std::fs::write(folder.path().join(name), b"SELECT 1").expect("model file");

        let stamps = snapshot_project_files(folder.path(), &SnapshotRules::default());

        assert_eq!(stamps.len(), 1, "{}", test_case.description);
        assert_eq!(
            stamps[0].relative_path.starts_with('\0'),
            test_case.expected_escaped,
            "{}",
            test_case.description
        );
        assert_eq!(
            std::fs::read(folder.path().join(text_path(&stamps[0].relative_path)))
                .expect("file named by the stamp"),
            b"SELECT 1",
            "{}",
            test_case.description
        );
    }
}
