use crate::store::errors::StoreDecodeError;
use crate::store::main::open_native_store::open_native_store;
use crate::store::tests::helpers::{
    ENVIRONMENT, KIND, METADATA, VALUE, damage, key, open, read_record, record, saved_store,
};
use crate::store::tests::test_types::{
    NativeStoreDiscardTestCase, NativeStoreOpenTestCase, NativeStoreRetentionTestCase,
    RecordReaderTestCase,
};

#[test]
fn given_saved_store_when_opening_then_only_the_same_kind_and_environment_load() {
    let test_cases = [
        NativeStoreOpenTestCase {
            description: "same kind and environment",
            kind: KIND,
            environment: ENVIRONMENT,
            edit: |_| {},
            expected_value: Some(VALUE),
            expected_metadata: METADATA,
        },
        NativeStoreOpenTestCase {
            description: "another environment",
            kind: KIND,
            environment: "environment-b",
            edit: |_| {},
            expected_value: None,
            expected_metadata: b"",
        },
        NativeStoreOpenTestCase {
            description: "another kind",
            kind: "inventory",
            environment: ENVIRONMENT,
            edit: |_| {},
            expected_value: None,
            expected_metadata: b"",
        },
        NativeStoreOpenTestCase {
            description: "damaged file",
            kind: KIND,
            environment: ENVIRONMENT,
            edit: damage,
            expected_value: None,
            expected_metadata: b"",
        },
        NativeStoreOpenTestCase {
            description: "truncated file",
            kind: KIND,
            environment: ENVIRONMENT,
            edit: |path| std::fs::write(path, b"SQBSTORE").expect("truncated"),
            expected_value: None,
            expected_metadata: b"",
        },
        NativeStoreOpenTestCase {
            description: "missing file",
            kind: KIND,
            environment: ENVIRONMENT,
            edit: |path| std::fs::remove_file(path).expect("removed"),
            expected_value: None,
            expected_metadata: b"",
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("cache/macro-calls.bin");
        saved_store(&path);
        (test_case.edit)(&path);

        let mut store =
            open_native_store(&path, test_case.kind, test_case.environment).expect("opened store");

        assert_eq!(
            store.get(&key("cents")).map(<[u8]>::to_vec),
            test_case.expected_value.map(<[u8]>::to_vec),
            "{}",
            test_case.description
        );
        assert_eq!(
            store.metadata(),
            test_case.expected_metadata,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_entry_unused_for_many_saves_when_saving_then_it_is_dropped_after_the_limit() {
    let test_cases = [
        NativeStoreRetentionTestCase {
            description: "unused for the retained number of saves",
            unused_saves: 64,
            expected_retained: true,
        },
        NativeStoreRetentionTestCase {
            description: "unused for one save more",
            unused_saves: 65,
            expected_retained: false,
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("macro-calls.bin");
        saved_store(&path);
        for _ in 0..test_case.unused_saves {
            let mut store = open(&path);
            store.put(key("fresh"), VALUE.to_vec());
            let _ = store.save(&path, METADATA).expect("saved");
        }

        let mut store = open(&path);

        assert_eq!(
            store.get(&key("cents")).is_some(),
            test_case.expected_retained,
            "{}",
            test_case.description
        );
        assert!(
            store.get(&key("fresh")).is_some(),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_loaded_store_when_saving_new_entries_then_only_discarded_entries_are_lost() {
    let test_cases = [
        NativeStoreDiscardTestCase {
            description: "kept",
            prepare: |_| {},
            expected_old_entry: true,
        },
        NativeStoreDiscardTestCase {
            description: "discarded",
            prepare: |store| store.discard(),
            expected_old_entry: false,
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("macro-calls.bin");
        saved_store(&path);
        let mut store = open(&path);
        (test_case.prepare)(&mut store);
        store.put(key("fresh"), VALUE.to_vec());
        let _ = store.save(&path, b"").expect("saved");

        let mut reopened = open(&path);

        assert_eq!(
            reopened.get(&key("cents")).is_some(),
            test_case.expected_old_entry,
            "{}",
            test_case.description
        );
        assert!(
            reopened.get(&key("fresh")).is_some(),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_record_bytes_when_reading_then_only_complete_records_decode() {
    let test_cases = [
        RecordReaderTestCase {
            description: "complete record",
            bytes: record,
            expected_record: Ok(("café".to_owned(), 7)),
        },
        RecordReaderTestCase {
            description: "truncated record",
            bytes: || record()[..10].to_vec(),
            expected_record: Err(StoreDecodeError),
        },
        RecordReaderTestCase {
            description: "trailing byte",
            bytes: || [record(), vec![0]].concat(),
            expected_record: Err(StoreDecodeError),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            read_record(&(test_case.bytes)()),
            test_case.expected_record,
            "{}",
            test_case.description
        );
    }
}
