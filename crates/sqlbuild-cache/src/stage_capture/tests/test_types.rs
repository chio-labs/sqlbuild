use sqlbuild_core::json::models::JsonValue;

pub(crate) struct MaskTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_masked: &'static str,
}

pub(crate) struct DocumentTestCase {
    pub(crate) description: &'static str,
    pub(crate) shared: &'static [(&'static str, &'static str)],
    pub(crate) root: JsonValue,
    pub(crate) expected_document: &'static str,
}

pub(crate) struct SortKeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) item: JsonValue,
    pub(crate) expected_key: &'static str,
}

pub(crate) struct CaptureNumberTestCase {
    pub(crate) description: &'static str,
    pub(crate) file_names: &'static [&'static str],
    pub(crate) expected_number: u64,
}
