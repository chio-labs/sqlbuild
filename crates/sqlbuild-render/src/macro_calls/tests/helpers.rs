use sqlbuild_cache::store::main::open_native_store::open_native_store;
use std::path::Path;

use crate::macro_calls::errors::ScanError;
use crate::macro_calls::models::{MacroCallEntry, MacroCallEvent, MacroCallMemo};
use crate::macro_calls::tests::test_types::ExpectedNames;

/// A memo holding one recorded `@py.cents(amount)` call in class 1, and that call's entry.
pub(crate) fn recorded_memo() -> (MacroCallMemo, MacroCallEntry) {
    let mut memo = MacroCallMemo::default();
    let entry = MacroCallEntry {
        sql: "amount * 100".to_owned(),
        relations: vec![("model".to_owned(), "orders".to_owned())],
        events: vec![
            MacroCallEvent::MacroUse {
                name: "cents".to_owned(),
            },
            MacroCallEvent::DeclarationRead {
                kind: "constant".to_owned(),
                name: "scale".to_owned(),
            },
        ],
    };
    memo.record(1, "@py.cents(amount)".to_owned(), entry.clone());
    (memo, entry)
}

/// Record `entry` for `@py.cents(amount)` into a fresh store at `path`, persistent per `class_texts`.
pub(crate) fn saved_memo_store(path: &Path, class_texts: &[&str], entry: &MacroCallEntry) {
    let mut memo = MacroCallMemo::default();
    memo.attach_store(
        open_native_store(path, STORE_KIND, STORE_ENVIRONMENT).expect("opened store"),
    );
    for class_text in class_texts {
        memo.set_persistent_class(1, class_text);
    }
    memo.record(1, "@py.cents(amount)".to_owned(), entry.clone());
    let _ = memo
        .store_mut()
        .expect("attached store")
        .save(path, b"")
        .expect("saved store");
}

pub(crate) const STORE_KIND: &str = "macro-calls";
pub(crate) const STORE_ENVIRONMENT: &str = "environment";

/// An entry with one event of every kind.
pub(crate) fn every_event_entry() -> MacroCallEntry {
    MacroCallEntry {
        sql: "SELECT * FROM __SQLBUILD_RELATION_1__ -- café".to_owned(),
        relations: vec![("model".to_owned(), "orders".to_owned())],
        events: vec![
            MacroCallEvent::MacroUse {
                name: "cents".to_owned(),
            },
            MacroCallEvent::DeclarationRead {
                kind: "enum".to_owned(),
                name: "order_status".to_owned(),
            },
            MacroCallEvent::GeneratedSql {
                macro_name: "cents".to_owned(),
                sql: "__ref(\"orders\")".to_owned(),
            },
            MacroCallEvent::ArgumentReference {
                kind: "source".to_owned(),
                name: "raw.orders".to_owned(),
            },
        ],
    }
}

/// Expected call names as the owned names the scan returns.
pub(crate) fn owned_names(names: ExpectedNames) -> Result<Vec<String>, ScanError> {
    names.map(|names| names.iter().map(|name| (*name).to_owned()).collect())
}
