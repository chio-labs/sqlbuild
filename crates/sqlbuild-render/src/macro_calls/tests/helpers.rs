use sqlbuild_cache::store::main::open_native_store::open_native_store;
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;
use std::path::Path;

use crate::macro_calls::models::{MacroCallEntry, MacroCallEvent, MacroCallMemo};

/// A memo holding one recorded `@cents(amount)` call in class 1, and that call's entry.
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
    memo.record(1, "@cents(amount)".to_owned(), entry.clone());
    (memo, entry)
}

/// The character classes of Python 3.12.
pub(crate) fn python_312() -> PythonText {
    python_text((3, 12), "15.0.0").expect("Python 3.12 is supported")
}

/// Record `entry` for `@cents(amount)` into a fresh store at `path`, persistent per `class_texts`.
pub(crate) fn saved_memo_store(path: &Path, class_texts: &[&str], entry: &MacroCallEntry) {
    let mut memo = MacroCallMemo::default();
    memo.attach_store(
        open_native_store(path, STORE_KIND, STORE_ENVIRONMENT).expect("opened store"),
    );
    for class_text in class_texts {
        memo.set_persistent_class(1, class_text);
    }
    memo.record(1, "@cents(amount)".to_owned(), entry.clone());
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
