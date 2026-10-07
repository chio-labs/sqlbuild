use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;

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
