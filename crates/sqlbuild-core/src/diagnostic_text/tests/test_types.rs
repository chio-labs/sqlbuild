use crate::diagnostic_text::models::DiagnosticRecordText;

pub(crate) struct DiagnosticRecordTestCase {
    pub(crate) description: &'static str,
    pub(crate) record: DiagnosticRecordText,
    pub(crate) use_color: bool,
    pub(crate) expected_text: &'static str,
}
