use sqlbuild_cache::store::main::open_native_store::open_native_store;

use crate::macro_calls::models::MacroCallMemo;
use crate::macro_calls::tests::helpers::{
    STORE_ENVIRONMENT, STORE_KIND, every_event_entry, recorded_memo, saved_memo_store,
};
use crate::macro_calls::tests::test_types::{MacroCallMemoTestCase, MacroCallStoreTestCase};

#[test]
fn given_recorded_call_when_looking_up_then_only_same_class_and_text_hit() {
    let test_cases = [
        MacroCallMemoTestCase {
            description: "same class and call text",
            class_id: 1,
            call_text: "@cents(amount)",
            expected_hit: true,
        },
        MacroCallMemoTestCase {
            description: "another call class",
            class_id: 2,
            call_text: "@cents(amount)",
            expected_hit: false,
        },
        MacroCallMemoTestCase {
            description: "another call text",
            class_id: 1,
            call_text: "@cents(total)",
            expected_hit: false,
        },
    ];

    for test_case in test_cases {
        let (mut memo, entry) = recorded_memo();
        let found = memo.lookup(test_case.class_id, test_case.call_text);
        assert_eq!(
            found.as_deref() == Some(&entry),
            test_case.expected_hit,
            "{}",
            test_case.description
        );
        assert_eq!(
            memo.stats(),
            (
                usize::from(test_case.expected_hit),
                usize::from(!test_case.expected_hit),
                1
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_stored_call_when_a_new_memo_looks_it_up_then_only_the_same_persistent_class_hits() {
    let test_cases = [
        MacroCallStoreTestCase {
            description: "same persistent class and call text",
            recorded_class_texts: &["cents@macros/cents.py"],
            looked_up_class_texts: &["cents@macros/cents.py"],
            call_text: "@cents(amount)",
            expected_store_hit: true,
        },
        MacroCallStoreTestCase {
            description: "another persistent class",
            recorded_class_texts: &["cents@macros/cents.py"],
            looked_up_class_texts: &["cents@models/marts/_sqlbuild/_macros/cents.py"],
            call_text: "@cents(amount)",
            expected_store_hit: false,
        },
        MacroCallStoreTestCase {
            description: "another call text",
            recorded_class_texts: &["cents@macros/cents.py"],
            looked_up_class_texts: &["cents@macros/cents.py"],
            call_text: "@cents(total)",
            expected_store_hit: false,
        },
        MacroCallStoreTestCase {
            description: "class not persistent when recorded",
            recorded_class_texts: &[],
            looked_up_class_texts: &["cents@macros/cents.py"],
            call_text: "@cents(amount)",
            expected_store_hit: false,
        },
        MacroCallStoreTestCase {
            description: "class not persistent when looked up",
            recorded_class_texts: &["cents@macros/cents.py"],
            looked_up_class_texts: &[],
            call_text: "@cents(amount)",
            expected_store_hit: false,
        },
    ];

    for test_case in test_cases {
        let folder = tempfile::tempdir().expect("store folder");
        let path = folder.path().join("macro-calls.bin");
        let entry = every_event_entry();
        saved_memo_store(&path, test_case.recorded_class_texts, &entry);
        let mut memo = MacroCallMemo::default();
        memo.attach_store(
            open_native_store(&path, STORE_KIND, STORE_ENVIRONMENT).expect("opened store"),
        );
        for class_text in test_case.looked_up_class_texts {
            memo.set_persistent_class(7, class_text);
        }

        let found = memo.lookup(7, test_case.call_text);

        assert_eq!(
            found.as_deref() == Some(&entry),
            test_case.expected_store_hit,
            "{}",
            test_case.description
        );
        assert_eq!(
            memo.store_stats(),
            (usize::from(test_case.expected_store_hit), 0),
            "{}",
            test_case.description
        );
    }
}
