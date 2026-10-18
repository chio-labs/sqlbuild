use crate::project_reuse::_helpers::entry::{read_entry, read_slot, rewrite_inputs, write_entry};
use crate::project_reuse::_helpers::identity::search_path_stamps;
use crate::project_reuse::_helpers::timings::{compile_timings_span, replace_compile_timings};
use crate::project_reuse::models::{ReuseRules, StoredInputs};
use crate::project_reuse::tests::helpers::{
    add_slot_section, damage, leave_orphaned_outputs, output_file, previous_format_slot,
    replace_output, slot_names, slot_section, store_aged_slots, stored_inputs, stored_output,
    truncate,
};
use crate::project_reuse::tests::test_types::{
    EntryReadTestCase, NonUnicodeNameTestCase, SlotPruneTestCase, SlotRefreshTestCase,
    TimingsSpanTestCase,
};
use crate::project_snapshot::main::path_text::path_text;
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
            edit: |path| truncate(path, 40),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "missing slot",
            edit: |path| std::fs::remove_file(path).expect("removed"),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "damaged output",
            edit: |path| damage(&output_file(path)),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "truncated output",
            edit: |path| truncate(&output_file(path), 60),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "missing output",
            edit: |path| std::fs::remove_file(output_file(path)).expect("removed"),
            expected_read: false,
        },
        EntryReadTestCase {
            description: "output of another compile",
            edit: replace_output,
            expected_read: false,
        },
        EntryReadTestCase {
            description: "slot of the previous single-file format",
            edit: |path| std::fs::write(path, previous_format_slot()).expect("old slot"),
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
            orphaned_outputs: &[],
            expected_kept: &["slot0.output", "slot0.store", "slot1.output", "slot1.store"],
        },
        SlotPruneTestCase {
            description: "over the limit",
            slots: 4,
            max_entries: 2,
            orphaned_outputs: &[],
            expected_kept: &["slot2.output", "slot2.store", "slot3.output", "slot3.store"],
        },
        SlotPruneTestCase {
            description: "outputs left without a slot",
            slots: 2,
            max_entries: 8,
            orphaned_outputs: &[("crashed.output", 3_600), ("in_flight.output", 0)],
            expected_kept: &[
                "in_flight.output",
                "slot0.output",
                "slot0.store",
                "slot1.output",
                "slot1.store",
            ],
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let directory = folder.path().join("reuse");
        leave_orphaned_outputs(&directory, test_case.orphaned_outputs);

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

#[cfg(unix)]
#[test]
fn given_search_path_entry_that_is_not_utf8_when_stamping_then_its_real_folder_is_stamped() {
    use std::os::unix::ffi::OsStrExt;

    let test_cases = [
        NonUnicodeNameTestCase {
            description: "unicode folder",
            name: "site_é".as_bytes(),
            expected_escaped: false,
        },
        NonUnicodeNameTestCase {
            description: "folder that is not UTF-8",
            name: b"site_\xff",
            expected_escaped: true,
        },
    ];
    let rules = ReuseRules {
        missing_path_mtime_ns: -1,
        project_root_path_mtime_ns: -2,
        ..ReuseRules::default()
    };

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("search path parent");
        let entry = folder
            .path()
            .join(std::ffi::OsStr::from_bytes(test_case.name));
        std::fs::create_dir(&entry).expect("search path folder");
        let text = path_text(entry.as_os_str());

        let stamps = search_path_stamps(std::slice::from_ref(&text), folder.path(), &rules);

        assert_eq!(
            text.starts_with('\0'),
            test_case.expected_escaped,
            "{}",
            test_case.description
        );
        assert!(stamps[0].1 > 0, "{}", test_case.description);
    }
}

#[test]
fn given_stored_compile_when_refreshing_inputs_then_only_the_slot_file_is_rewritten() {
    let test_cases = [SlotRefreshTestCase {
        description: "slot carrying a section this release does not read",
        extra_section: ("project-image", b"orders index"),
        expected_output_rewritten: false,
    }];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("reuse/slot.store");
        write_entry(&path, &stored_inputs(), &stored_output(), 8).expect("stored compile");
        let (name, bytes) = test_case.extra_section;
        add_slot_section(&path, name, bytes);
        let output_before = std::fs::read(output_file(&path)).expect("output bytes");
        let slot = read_slot(&path).expect("slot");
        let refreshed = StoredInputs {
            invocation_digest: "b3:refreshed".to_owned(),
            ..stored_inputs()
        };

        rewrite_inputs(&path, &slot, &refreshed);

        assert_eq!(
            read_entry(&path),
            Some((refreshed, stored_output())),
            "{}: refreshed inputs read back with the kept output",
            test_case.description
        );
        assert_eq!(
            std::fs::read(output_file(&path)).expect("output bytes") != output_before,
            test_case.expected_output_rewritten,
            "{}: output file",
            test_case.description
        );
        assert_eq!(
            slot_section(&path, name),
            Some(bytes.to_vec()),
            "{}: unread sections are carried forward",
            test_case.description
        );
    }
}
