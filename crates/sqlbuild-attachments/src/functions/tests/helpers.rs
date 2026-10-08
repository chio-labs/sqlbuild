use crate::functions::models::{
    FunctionHeader, FunctionLanguage, HeaderFailure, HeaderStage, HeaderValue, NamedType,
    NamespaceInputs,
};

pub(super) fn text(value: &str) -> HeaderValue {
    HeaderValue::Text(value.to_owned())
}

pub(super) fn map(entries: &[(&str, HeaderValue)]) -> HeaderValue {
    let mut pairs: Vec<(HeaderValue, HeaderValue)> = Vec::new();
    for (key, value) in entries {
        pairs.push((text(key), value.clone()));
    }
    HeaderValue::Map(pairs)
}

pub(super) fn header(entries: &[(&str, HeaderValue)]) -> Vec<(String, HeaderValue)> {
    let mut pairs: Vec<(String, HeaderValue)> = Vec::new();
    for (key, value) in entries {
        pairs.push(((*key).to_owned(), value.clone()));
    }
    pairs
}

pub(super) fn owned(value: Option<&str>) -> Option<String> {
    value.map(str::to_owned)
}

/// Header `udfs`, defaults `analytics.shared`, target `prod_db` with no target schema.
pub(super) fn namespace_inputs(language: FunctionLanguage, inherit: bool) -> NamespaceInputs {
    NamespaceInputs {
        header_database: None,
        header_schema: owned(Some("udfs")),
        default_database: owned(Some("analytics")),
        default_schema: owned(Some("shared")),
        target_database: owned(Some("prod_db")),
        target_schema: None,
        language,
        inherit_default_namespace: inherit,
    }
}

pub(super) fn named(raw_name: &str, name: &str, type_text: &str) -> NamedType {
    NamedType {
        raw_name: raw_name.to_owned(),
        name: name.to_owned(),
        type_text: type_text.to_owned(),
    }
}

/// A header Python parsed nothing else from.
pub(super) fn empty_header() -> FunctionHeader {
    FunctionHeader {
        arguments: Vec::new(),
        returns: None,
        tags: Vec::new(),
        description: None,
        runtime_version: None,
        entry_point: None,
        packages: Vec::new(),
        failure: None,
    }
}

pub(super) fn failure(stage: HeaderStage, message: &str) -> Option<HeaderFailure> {
    Some(HeaderFailure {
        stage,
        message: message.to_owned(),
    })
}
