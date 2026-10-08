use crate::functions::models::{
    FunctionHeader, FunctionLanguage, FunctionNamespace, HeaderValue, NamespaceInputs,
};

pub(super) struct FunctionHeaderTestCase {
    pub(super) description: &'static str,
    pub(super) header: Vec<(String, HeaderValue)>,
    pub(super) language: FunctionLanguage,
    pub(super) expected_header: FunctionHeader,
}

pub(super) struct FunctionNamespaceTestCase {
    pub(super) description: &'static str,
    pub(super) inputs: NamespaceInputs,
    pub(super) expected_namespace: FunctionNamespace,
}
