//! Stable function definition text used for change fingerprints.

use crate::planner_identity::models::FunctionFingerprintFields;

/// The language, signature, runtime fields and body, one field per line.
pub fn function_fingerprint_sql(fields: &FunctionFingerprintFields) -> String {
    let render = |pairs: &[(String, String)]| -> String {
        pairs
            .iter()
            .map(|(name, kind)| format!("{name}:{kind}"))
            .collect::<Vec<String>>()
            .join(",")
    };
    [
        format!("language={}", fields.language),
        format!("arguments={}", render(&fields.arguments)),
        format!("returns={}", fields.returns),
        format!("return_columns={}", render(&fields.return_columns)),
        format!("runtime_version={}", fields.runtime_version),
        format!("entry_point={}", fields.entry_point),
        format!("packages={}", fields.packages.join(",")),
        "body=".to_owned(),
        fields.body_sql.clone(),
    ]
    .join("\n")
}
