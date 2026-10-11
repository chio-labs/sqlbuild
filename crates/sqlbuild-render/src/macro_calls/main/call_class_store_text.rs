/// `call_class_store_text`: the JSON naming a persistent call class by its tokens and relations.
pub fn call_class_store_text(
    macro_tokens: &[String],
    context_token: Option<&str>,
    prior_relations: Option<&[(String, String)]>,
) -> String {
    let relations: serde_json::Value = prior_relations.map_or(serde_json::Value::Null, |items| {
        serde_json::Value::Array(
            items
                .iter()
                .map(|(kind, name)| serde_json::json!([kind, name]))
                .collect(),
        )
    });
    serde_json::Value::Array(vec![
        serde_json::json!(macro_tokens),
        serde_json::json!(context_token),
        relations,
    ])
    .to_string()
}
