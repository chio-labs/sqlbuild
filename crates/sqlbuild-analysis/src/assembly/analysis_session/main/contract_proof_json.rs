//! A dynamic pivot proof as `json.dumps(asdict(proof), sort_keys=True, separators=(",", ":"))`.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::assembly::analysis_session::models::ContractProof;

/// The proof's canonical JSON text, as the SQL rule cache keys a model's contract.
pub fn contract_proof_json(proof: &ContractProof) -> String {
    let text = |value: &str| JsonValue::String(value.to_owned());
    let optional = |value: Option<&String>| value.map_or(JsonValue::Null, |value| text(value));
    let fixed: Vec<JsonValue> = proof
        .fixed_columns
        .iter()
        .map(|column| {
            JsonValue::Object(vec![
                ("name".to_owned(), text(&column.name)),
                ("nullability".to_owned(), text(&column.nullability)),
                ("type".to_owned(), optional(column.data_type.as_ref())),
            ])
        })
        .collect();
    let families: Vec<JsonValue> = proof
        .families
        .iter()
        .map(|(name, inferred_type)| {
            JsonValue::Object(vec![
                ("inferred_type".to_owned(), optional(inferred_type.as_ref())),
                ("name".to_owned(), text(name)),
            ])
        })
        .collect();
    let value: JsonValue = JsonValue::Object(vec![
        (
            "bare_dynamic_pivot".to_owned(),
            JsonValue::Bool(proof.bare_dynamic_pivot),
        ),
        (
            "failure_reason".to_owned(),
            optional(proof.failure_reason.as_ref()),
        ),
        ("families".to_owned(), JsonValue::Array(families)),
        ("fixed_columns".to_owned(), JsonValue::Array(fixed)),
        (
            "input_relations".to_owned(),
            JsonValue::Array(
                proof
                    .input_relations
                    .iter()
                    .map(|name| text(name))
                    .collect(),
            ),
        ),
        (
            "output_proven".to_owned(),
            JsonValue::Bool(proof.output_proven),
        ),
    ]);
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    dumps(&value, &JsonDialect::Stdlib(options)).unwrap_or_default()
}
