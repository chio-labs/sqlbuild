use sqlbuild_core::json::models::JsonValue;

use crate::diff_report::models::{
    DiffColumnFacts, DiffDocumentOptions, DiffExampleOptions, DiffModelFacts, DiffRowFacts,
    DiffValue,
};

pub(crate) fn changed_rows(unequal: i64) -> DiffRowFacts {
    DiffRowFacts {
        left_count: 3,
        right_count: 3,
        joined_count: 3,
        equal_count: 3 - unequal,
        unequal_count: unequal,
        columns: vec![DiffColumnFacts {
            name: "amount".to_owned(),
            mismatched_count: unequal,
            tolerance: None,
        }],
        population_count: 3,
        compared_count: 3,
        exhaustive: true,
        ..DiffRowFacts::default()
    }
}

pub(crate) fn model(rows: Option<DiffRowFacts>, added_columns: &[&str]) -> DiffModelFacts {
    DiffModelFacts {
        name: "orders".to_owned(),
        left_relation: "prod.orders".to_owned(),
        right_relation: "dev.orders".to_owned(),
        added_columns: added_columns
            .iter()
            .map(|name| (*name).to_owned())
            .collect(),
        unique_key: vec!["order_id".to_owned()],
        rows,
        input_kind: "model".to_owned(),
        ..DiffModelFacts::default()
    }
}

pub(crate) fn document() -> DiffDocumentOptions {
    DiffDocumentOptions {
        from_label: "prod".to_owned(),
        to_label: "dev".to_owned(),
        examples: DiffExampleOptions {
            max_value_length: Some(160),
            suppress_values: false,
        },
        ..DiffDocumentOptions::default()
    }
}

pub(crate) fn cursor_rows() -> DiffRowFacts {
    DiffRowFacts {
        cursor_column: Some("ts".to_owned()),
        cursor_start: Some(DiffValue {
            text: "nan".to_owned(),
            json: JsonValue::Float(f64::NAN),
        }),
        ..changed_rows(1)
    }
}
